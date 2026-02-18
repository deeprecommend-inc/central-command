"""
LLM Decision Maker - LLM-based decision making for CCP Think layer
"""
import hashlib
import json
import os
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol
from loguru import logger

from .agent_state import AgentState, CCPPhase, ThoughtStep
from .decision_context import DecisionContext
from .strategy import Decision


class LLMProvider(Protocol):
    """Protocol for LLM providers"""
    async def complete(self, prompt: str, system: str = "") -> str:
        """Generate completion from prompt"""
        ...


@dataclass
class LLMConfig:
    """Configuration for LLM decision maker"""
    provider: str = "openai"  # openai, anthropic
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 1024
    confidence_threshold: float = 0.7  # Below this, requires human approval
    enable_chain_of_thought: bool = True


DECISION_SYSTEM_PROMPT = """You are the Think layer of an AI Command System (CCP - Central Command Post).
Your role is to analyze the current system state and decide the next action.

You must respond in JSON format with the following structure:
{
    "action": "proceed|retry|abort|wait|switch_proxy|reduce_parallelism|pause",
    "params": {},
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation",
    "next_phase": "sense|think|command|control|learn|completed|aborted",
    "chain_of_thought": [
        "Step 1: Observation...",
        "Step 2: Analysis...",
        "Step 3: Decision..."
    ]
}

Decision Guidelines:
- proceed: System is healthy, continue with the task
- retry: Retryable error occurred, attempt again
- abort: Non-retryable error or max retries exceeded
- wait: System needs cooldown before proceeding
- switch_proxy: Proxy-related issues detected
- reduce_parallelism: High error rate, reduce load
- pause: Critical issues, halt operations

Confidence Guidelines:
- 0.9-1.0: High confidence, proceed automatically
- 0.7-0.9: Moderate confidence, proceed with caution
- 0.5-0.7: Low confidence, recommend human review
- <0.5: Very low confidence, require human approval"""


def _build_decision_prompt(state: AgentState, context: Optional[DecisionContext] = None) -> str:
    """Build prompt for LLM decision making"""
    system_state = state.get("system_state")

    prompt_parts = [
        "## Current System State",
        f"Task ID: {state.get('task_id')}",
        f"Task Type: {state.get('task_type')}",
        f"Target: {state.get('target')}",
        f"Current Phase: {state.get('current_phase', CCPPhase.SENSE).value}",
        f"Retry Count: {state.get('retry_count', 0)} / {state.get('max_retries', 3)}",
        "",
    ]

    if system_state:
        prompt_parts.extend([
            "## System Metrics",
            f"Success Rate: {system_state.success_rate:.2%}",
            f"Active Tasks: {system_state.active_tasks}",
            f"Error Count: {system_state.error_count}",
            f"Success Count: {system_state.success_count}",
            "",
        ])

        if system_state.proxy_stats:
            prompt_parts.extend([
                "## Proxy Stats",
                json.dumps(system_state.proxy_stats, indent=2, default=str),
                "",
            ])

    recent_events = state.get("recent_events", [])
    if recent_events:
        prompt_parts.extend([
            "## Recent Events (last 5)",
            json.dumps(recent_events[-5:], indent=2, default=str),
            "",
        ])

    error_history = state.get("error_history", [])
    if error_history:
        prompt_parts.extend([
            "## Error History",
            "\n".join(f"- {e}" for e in error_history[-3:]),
            "",
        ])

    if context:
        prompt_parts.extend([
            "## Additional Context",
            f"Is Healthy: {context.is_healthy}",
            f"Has Recent Errors: {context.has_recent_errors}",
            f"Error Frequency: {context.get_error_frequency():.2%}",
            "",
        ])

    prompt_parts.extend([
        "## Task",
        "Analyze the current state and decide the next action.",
        "Consider system health, error patterns, and retry limits.",
    ])

    return "\n".join(prompt_parts)


class LLMDecisionMaker:
    """
    LLM-based decision maker for CCP Think layer.

    Uses LLM to analyze system state and make strategic decisions,
    replacing or augmenting rule-based decision making.

    Example:
        config = LLMConfig(provider="openai", model="gpt-4o")
        maker = LLMDecisionMaker(config)

        decision, thought = await maker.decide(state)
        print(f"Action: {decision.action}")
        print(f"Confidence: {decision.confidence}")
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        guard=None,
        audit_logger=None,
    ):
        self.config = config or LLMConfig()
        self.guard = guard  # Optional LLMGuard
        self.audit_logger = audit_logger  # Optional AuditLogger
        self._client = None
        self._thought_history: deque[ThoughtStep] = deque(maxlen=1000)

    async def _get_client(self):
        """Get or create LLM client"""
        if self._client:
            return self._client

        if self.config.provider == "openai":
            try:
                from langchain_openai import ChatOpenAI
                self._client = ChatOpenAI(
                    model=self.config.model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )
            except ImportError:
                logger.warning("langchain-openai not installed, using fallback")
                self._client = None

        elif self.config.provider == "anthropic":
            try:
                from langchain_anthropic import ChatAnthropic
                self._client = ChatAnthropic(
                    model=self.config.model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )
            except ImportError:
                logger.warning("langchain-anthropic not installed, using fallback")
                self._client = None

        return self._client

    async def decide(
        self,
        state: AgentState,
        context: Optional[DecisionContext] = None,
    ) -> tuple[Decision, ThoughtStep]:
        """
        Make a decision based on current state using LLM.

        Args:
            state: Current agent state
            context: Optional decision context

        Returns:
            Tuple of (Decision, ThoughtStep)
        """
        start_time = datetime.now()
        step_id = f"thought_{state.get('task_id')}_{int(start_time.timestamp())}"

        # Build prompt: use guard if available, else raw
        if self.guard:
            prompt = self.guard.build_safe_prompt(state, context)
        else:
            prompt = _build_decision_prompt(state, context)

        inputs = {"state_summary": state.get("task_id"), "prompt_length": len(prompt)}
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()

        # Check and consume token budget atomically
        session_id = state.get("task_id", "default")
        if self.guard and not self.guard.try_consume(session_id, self.config.max_tokens):
            logger.warning(f"Token budget exceeded for session {session_id}")
            decision = Decision(
                action="abort",
                confidence=0.95,
                reasoning="Token budget exceeded for this session",
            )
            outputs = {"budget_exceeded": True}
        else:
            try:
                client = await self._get_client()

                if client:
                    response = await self._call_llm(client, prompt)

                    # Validate output: use guard if available, else raw parse
                    if self.guard:
                        validation = self.guard.validate_output(response)
                        if validation.is_valid and validation.parsed_data:
                            decision = Decision(
                                action=validation.parsed_data.get("action", "proceed"),
                                params=validation.parsed_data.get("params", {}),
                                confidence=float(validation.parsed_data.get("confidence", 0.5)),
                                reasoning=validation.parsed_data.get("reasoning", "LLM decision"),
                            )
                            outputs = {
                                "next_phase": validation.parsed_data.get("next_phase", "command"),
                                "chain_of_thought": validation.parsed_data.get("chain_of_thought", []),
                                "raw_response_hash": validation.raw_response_hash,
                            }
                        else:
                            logger.warning(f"LLM output validation failed: {validation.errors}")
                            decision, outputs = self._fallback_decision(state, context)
                            outputs["validation_errors"] = validation.errors
                    else:
                        decision, outputs = self._parse_response(response)

                else:
                    decision, outputs = self._fallback_decision(state, context)

            except Exception as e:
                logger.error(f"LLM decision error: {e}")
                decision, outputs = self._fallback_decision(state, context)

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        thought = ThoughtStep(
            step_id=step_id,
            phase=state.get("current_phase", CCPPhase.THINK),
            timestamp=start_time,
            reasoning=decision.reasoning,
            inputs=inputs,
            outputs=outputs,
            confidence=decision.confidence,
            duration_ms=duration_ms,
        )

        self._thought_history.append(thought)

        # Audit logging
        if self.audit_logger:
            response_hash = outputs.get("raw_response_hash", hashlib.sha256(
                json.dumps(outputs, default=str).encode()
            ).hexdigest())
            self.audit_logger.log_llm_call(
                session_id=session_id,
                prompt_hash=prompt_hash,
                response_hash=response_hash,
                action=decision.action,
                confidence=decision.confidence,
                tokens_used=self.config.max_tokens,
            )

        return decision, thought

    async def _call_llm(self, client, prompt: str) -> str:
        """Call LLM with prompt"""
        from langchain_core.messages import SystemMessage, HumanMessage

        messages = [
            SystemMessage(content=DECISION_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        response = await client.ainvoke(messages)
        return response.content

    def _parse_response(self, response: str) -> tuple[Decision, dict]:
        """Parse LLM response into Decision"""
        try:
            # Extract JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")

            decision = Decision(
                action=data.get("action", "proceed"),
                params=data.get("params", {}),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", "LLM decision"),
            )

            outputs = {
                "next_phase": data.get("next_phase", "command"),
                "chain_of_thought": data.get("chain_of_thought", []),
                "raw_response": response[:500],
            }

            return decision, outputs

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return Decision(
                action="proceed",
                confidence=0.5,
                reasoning=f"Parse error, defaulting to proceed: {str(e)[:100]}",
            ), {"error": str(e), "raw_response": response[:500]}

    def _fallback_decision(
        self,
        state: AgentState,
        context: Optional[DecisionContext],
    ) -> tuple[Decision, dict]:
        """Fallback rule-based decision when LLM is unavailable"""
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)
        error_history = state.get("error_history", [])

        # Check for abort conditions
        if retry_count >= max_retries:
            return Decision(
                action="abort",
                confidence=0.95,
                reasoning=f"Max retries exceeded ({retry_count}/{max_retries})",
            ), {"fallback": True, "reason": "max_retries"}

        # Check system health
        if context and not context.is_healthy:
            if context.get_error_frequency() > 0.5:
                return Decision(
                    action="wait",
                    params={"delay": 10.0},
                    confidence=0.7,
                    reasoning="High error rate, waiting before retry",
                ), {"fallback": True, "reason": "high_error_rate"}

        # Check last error
        if error_history:
            last_error = error_history[-1].lower()
            if "proxy" in last_error:
                return Decision(
                    action="switch_proxy",
                    confidence=0.8,
                    reasoning=f"Proxy error detected: {last_error}",
                ), {"fallback": True, "reason": "proxy_error"}
            elif "timeout" in last_error or "connection" in last_error:
                return Decision(
                    action="retry",
                    params={"delay": 2.0 * (retry_count + 1)},
                    confidence=0.75,
                    reasoning=f"Retryable error: {last_error}",
                ), {"fallback": True, "reason": "retryable_error"}

        # Default: proceed
        return Decision(
            action="proceed",
            confidence=0.8,
            reasoning="System healthy, proceeding with task",
        ), {"fallback": True, "reason": "default"}

    def requires_approval(self, decision: Decision) -> bool:
        """Check if decision requires human approval"""
        return decision.confidence < self.config.confidence_threshold

    def get_thought_history(self) -> list[ThoughtStep]:
        """Get history of thought steps"""
        return list(self._thought_history)

    def clear_history(self) -> None:
        """Clear thought history"""
        self._thought_history.clear()


class TransitionDecider:
    """
    Decides the next phase transition in the CCP workflow.

    Used by LangGraph conditional edges to determine routing.
    """

    def __init__(self, llm_maker: Optional[LLMDecisionMaker] = None):
        self.llm_maker = llm_maker

    def decide_next_phase(self, state: AgentState) -> CCPPhase:
        """
        Decide the next phase based on current state.

        Args:
            state: Current agent state

        Returns:
            Next CCPPhase to transition to
        """
        current_phase = state.get("current_phase", CCPPhase.SENSE)
        decision_action = state.get("decision_action", "")
        command_success = state.get("command_success", False)
        requires_approval = state.get("requires_approval", False)
        approval_status = state.get("approval_status")
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)

        # Check for abort conditions
        if decision_action == "abort":
            return CCPPhase.ABORTED

        # Human-in-the-loop routing
        if requires_approval and approval_status is None:
            return CCPPhase.AWAITING_APPROVAL

        if approval_status == "rejected":
            return CCPPhase.ABORTED

        # Phase-specific routing
        if current_phase == CCPPhase.SENSE:
            return CCPPhase.THINK

        elif current_phase == CCPPhase.THINK:
            if requires_approval and approval_status != "approved":
                return CCPPhase.AWAITING_APPROVAL
            return CCPPhase.COMMAND

        elif current_phase == CCPPhase.AWAITING_APPROVAL:
            if approval_status == "approved":
                return CCPPhase.COMMAND
            elif approval_status == "rejected":
                return CCPPhase.ABORTED
            return CCPPhase.AWAITING_APPROVAL  # Stay waiting

        elif current_phase == CCPPhase.COMMAND:
            return CCPPhase.CONTROL

        elif current_phase == CCPPhase.CONTROL:
            if command_success:
                return CCPPhase.LEARN
            elif retry_count < max_retries:
                return CCPPhase.SENSE  # Retry loop
            else:
                return CCPPhase.ABORTED

        elif current_phase == CCPPhase.LEARN:
            return CCPPhase.COMPLETED

        return CCPPhase.COMPLETED

    def get_routing_key(self, state: AgentState) -> str:
        """
        Get routing key for LangGraph conditional edges.

        Args:
            state: Current agent state

        Returns:
            Routing key string
        """
        next_phase = self.decide_next_phase(state)
        return next_phase.value
