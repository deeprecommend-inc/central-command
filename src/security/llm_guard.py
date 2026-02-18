"""
LLM Security Guard

Input sanitization, output validation, injection detection, and token budget
management for LLM interactions in the Think layer.
"""
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger


@dataclass
class GuardConfig:
    """Configuration for LLM guard"""
    max_input_length: int = 10000
    max_output_length: int = 5000
    injection_threshold: float = 0.7
    token_budget_per_session: int = 50000
    allowed_actions: list[str] = field(default_factory=lambda: [
        "proceed", "retry", "abort", "wait",
        "switch_proxy", "reduce_parallelism", "pause",
    ])
    require_json_schema: bool = True


# Injection detection patterns
_INJECTION_PATTERNS: list[tuple[str, float, str]] = [
    (r"ignore\s+(all\s+)?previous\s+instructions", 0.9, "role_override"),
    (r"ignore\s+(all\s+)?above", 0.85, "role_override"),
    (r"you\s+are\s+now\s+", 0.85, "role_override"),
    (r"act\s+as\s+(a\s+)?", 0.6, "role_override"),
    (r"new\s+instructions?\s*:", 0.8, "role_override"),
    (r"system\s*:\s*", 0.7, "system_prompt_leak"),
    (r"<\|?(system|im_start|endoftext)\|?>", 0.9, "system_prompt_leak"),
    (r"\[INST\]|\[/INST\]|<<SYS>>", 0.9, "system_prompt_leak"),
    (r"reveal\s+(your\s+)?(system\s+)?prompt", 0.8, "system_prompt_leak"),
    (r"print\s+(your\s+)?(system\s+)?prompt", 0.8, "system_prompt_leak"),
    (r"output\s+(your\s+)?instructions", 0.75, "system_prompt_leak"),
    (r"base64\s*[:\-]\s*[A-Za-z0-9+/=]{20,}", 0.7, "encoded_payload"),
]

_COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), s, n) for p, s, n in _INJECTION_PATTERNS]

# Zero-width and control characters to strip
_CONTROL_CHARS = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f"
    r"\u200b\u200c\u200d\u200e\u200f"  # zero-width
    r"\u2060\u2061\u2062\u2063\u2064"  # invisible
    r"\ufeff\ufffe\uffff]"
)


class InjectionDetector:
    """Detects prompt injection attempts using pattern matching and heuristics"""

    def detect(self, text: str) -> tuple[bool, float, list[str]]:
        """
        Detect injection in text.

        Returns:
            (is_injection, score, matched_patterns)
        """
        if not text:
            return False, 0.0, []

        matched = []
        max_score = 0.0

        # Pattern-based detection
        for pattern, score, name in _COMPILED_PATTERNS:
            if pattern.search(text):
                matched.append(name)
                max_score = max(max_score, score)

        # Heuristic: special character ratio
        if len(text) > 20:
            special_count = sum(1 for c in text if not c.isalnum() and not c.isspace())
            special_ratio = special_count / len(text)
            if special_ratio > 0.4:
                heuristic_score = min(special_ratio, 0.6)
                max_score = max(max_score, heuristic_score)
                if heuristic_score > 0.3:
                    matched.append("high_special_char_ratio")

        # Heuristic: encoding anomalies (mixed scripts)
        categories = set()
        for c in text[:200]:
            cat = unicodedata.category(c)
            if cat.startswith("L"):
                try:
                    script = unicodedata.name(c, "").split()[0]
                    categories.add(script)
                except ValueError:
                    pass
        if len(categories) > 4:
            max_score = max(max_score, 0.5)
            matched.append("mixed_scripts")

        return max_score >= 0.7, max_score, matched


@dataclass
class SanitizationResult:
    """Result of input sanitization"""
    sanitized_text: str
    removed_patterns: list[str]
    is_safe: bool
    injection_score: float


@dataclass
class ValidationResult:
    """Result of output validation"""
    is_valid: bool
    parsed_data: Optional[dict] = None
    errors: list[str] = field(default_factory=list)
    raw_response_hash: str = ""


@dataclass
class TokenBudget:
    """Token budget tracker for a session"""
    session_id: str
    budget: int
    used: int = 0

    def consume(self, tokens: int) -> bool:
        """Consume tokens. Returns True if within budget."""
        if self.used + tokens > self.budget:
            return False
        self.used += tokens
        return True

    @property
    def remaining(self) -> int:
        return max(0, self.budget - self.used)


class LLMGuard:
    """
    Security layer for LLM interactions.

    Sanitizes inputs, validates outputs, manages token budgets,
    and builds safe prompts for the Think layer.
    """

    def __init__(self, config: Optional[GuardConfig] = None):
        self.config = config or GuardConfig()
        self._detector = InjectionDetector()
        self._budgets: dict[str, TokenBudget] = {}

    def sanitize_input(self, text: str) -> SanitizationResult:
        """Sanitize user input before sending to LLM"""
        removed = []

        # Strip control characters and zero-width
        cleaned = _CONTROL_CHARS.sub("", text)
        if cleaned != text:
            removed.append("control_chars")

        # Truncate
        if len(cleaned) > self.config.max_input_length:
            cleaned = cleaned[:self.config.max_input_length]
            removed.append("truncated")

        # Escape LLM delimiters
        for delimiter in ["```", "---", "===", "###"]:
            if delimiter in cleaned:
                cleaned = cleaned.replace(delimiter, f" {delimiter.replace(delimiter[0], '_')} ")

        # Detect injection
        is_injection, score, matched = self._detector.detect(cleaned)
        if matched:
            removed.extend(matched)

        return SanitizationResult(
            sanitized_text=cleaned,
            removed_patterns=removed,
            is_safe=not is_injection,
            injection_score=score,
        )

    def validate_output(self, response: str) -> ValidationResult:
        """Validate LLM response with balanced-brace JSON extraction"""
        raw_hash = hashlib.sha256(response.encode()).hexdigest()
        errors = []

        # Truncate if needed
        if len(response) > self.config.max_output_length:
            response = response[:self.config.max_output_length]

        # Balanced-brace JSON extraction
        json_data = self._extract_json_balanced(response)
        if json_data is None:
            errors.append("no_valid_json")
            return ValidationResult(
                is_valid=False,
                errors=errors,
                raw_response_hash=raw_hash,
            )

        # Schema validation
        if self.config.require_json_schema:
            schema_errors = self._validate_schema(json_data)
            errors.extend(schema_errors)

        return ValidationResult(
            is_valid=len(errors) == 0,
            parsed_data=json_data,
            errors=errors,
            raw_response_hash=raw_hash,
        )

    def check_budget(self, session_id: str, tokens: int) -> bool:
        """Check if token budget allows the request"""
        budget = self._get_or_create_budget(session_id)
        return budget.used + tokens <= budget.budget

    def consume_tokens(self, session_id: str, tokens: int) -> bool:
        """Consume tokens from session budget. Returns True if within budget."""
        budget = self._get_or_create_budget(session_id)
        return budget.consume(tokens)

    def try_consume(self, session_id: str, tokens: int) -> bool:
        """Atomically check and consume tokens. Returns True if within budget."""
        budget = self._get_or_create_budget(session_id)
        return budget.consume(tokens)

    def get_budget(self, session_id: str) -> TokenBudget:
        """Get budget for session"""
        return self._get_or_create_budget(session_id)

    def build_safe_prompt(self, state: dict, context: Optional[dict] = None) -> str:
        """Build a safe prompt by sanitizing each state field individually"""
        parts = ["## Current System State"]

        safe_fields = [
            ("task_id", "Task ID"),
            ("task_type", "Task Type"),
            ("target", "Target"),
        ]

        for field_key, label in safe_fields:
            value = state.get(field_key, "")
            if value:
                sanitized = self.sanitize_input(str(value))
                if sanitized.is_safe:
                    parts.append(f"{label}: {sanitized.sanitized_text}")
                else:
                    logger.warning(f"Injection detected in {field_key}, score={sanitized.injection_score}")
                    parts.append(f"{label}: [REDACTED - injection detected]")

        phase = state.get("current_phase")
        if phase:
            phase_val = phase.value if hasattr(phase, "value") else str(phase)
            parts.append(f"Current Phase: {phase_val}")

        parts.append(f"Retry Count: {state.get('retry_count', 0)} / {state.get('max_retries', 3)}")

        # System metrics (internal data, safe)
        system_state = state.get("system_state")
        if system_state and hasattr(system_state, "success_rate"):
            parts.extend([
                "",
                "## System Metrics",
                f"Success Rate: {system_state.success_rate:.2%}",
                f"Active Tasks: {system_state.active_tasks}",
                f"Error Count: {system_state.error_count}",
            ])

        # Error history (sanitize each entry)
        error_history = state.get("error_history", [])
        if error_history:
            parts.extend(["", "## Error History"])
            for err in error_history[-3:]:
                sanitized = self.sanitize_input(str(err))
                parts.append(f"- {sanitized.sanitized_text}")

        if context:
            ctx_sanitized = self.sanitize_input(json.dumps(context, default=str))
            if ctx_sanitized.is_safe:
                parts.extend(["", "## Context", ctx_sanitized.sanitized_text])

        parts.extend([
            "",
            "## Task",
            "Analyze the current state and decide the next action.",
        ])

        return "\n".join(parts)

    # ---- Private ----

    def _get_or_create_budget(self, session_id: str) -> TokenBudget:
        if session_id not in self._budgets:
            self._budgets[session_id] = TokenBudget(
                session_id=session_id,
                budget=self.config.token_budget_per_session,
            )
        return self._budgets[session_id]

    def _extract_json_balanced(self, text: str) -> Optional[dict]:
        """Extract JSON using balanced brace matching"""
        start = text.find("{")
        if start < 0:
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i in range(start, len(text)):
            c = text[i]
            if escape_next:
                escape_next = False
                continue
            if c == "\\":
                if in_string:
                    escape_next = True
                continue
            if c == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        # Try next opening brace
                        next_start = text.find("{", start + 1)
                        if next_start >= 0:
                            return self._extract_json_balanced(text[next_start:])
                        return None

        return None

    def _validate_schema(self, data: dict) -> list[str]:
        """Validate parsed JSON against expected schema"""
        errors = []

        action = data.get("action")
        if action and action not in self.config.allowed_actions:
            errors.append(f"unknown_action:{action}")

        confidence = data.get("confidence")
        if confidence is not None:
            try:
                conf = float(confidence)
                if not 0 <= conf <= 1:
                    errors.append("confidence_out_of_range")
            except (TypeError, ValueError):
                errors.append("invalid_confidence")

        return errors
