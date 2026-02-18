"""
Signed Audit Logger

Tamper-proof audit trail for LLM calls and decisions.
Entries are signed with PQC (or Ed25519 fallback) when a PQCEngine is provided.
"""
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger


@dataclass
class AuditEntry:
    """Single audit log entry"""
    entry_id: str
    timestamp: float
    event_type: str
    input_hash: str
    output_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)
    signature: Optional[Any] = None  # Signature dataclass or None

    def to_dict(self) -> dict:
        d = {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "metadata": self.metadata,
        }
        if self.signature is not None:
            d["signature"] = self.signature.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AuditEntry":
        sig = None
        if data.get("signature"):
            from .pqc import Signature
            sig = Signature.from_dict(data["signature"])
        return cls(
            entry_id=data["entry_id"],
            timestamp=data["timestamp"],
            event_type=data["event_type"],
            input_hash=data["input_hash"],
            output_hash=data["output_hash"],
            metadata=data.get("metadata", {}),
            signature=sig,
        )

    def signable_bytes(self) -> bytes:
        """Deterministic bytes for signing"""
        payload = {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "metadata": self.metadata,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


class AuditLogger:
    """
    Audit logger with optional PQC signing and file persistence.

    Works in unsigned mode when no PQC engine is provided.
    """

    def __init__(
        self,
        pqc_engine=None,
        signing_keypair=None,
        log_file: Optional[str] = None,
    ):
        self._pqc = pqc_engine
        self._signing_keypair = signing_keypair
        self._log_file = log_file
        self._entries: list[AuditEntry] = []

        if log_file and os.path.exists(log_file):
            self._load_from_file()

    def log_llm_call(
        self,
        session_id: str,
        prompt_hash: str,
        response_hash: str,
        action: str,
        confidence: float,
        tokens_used: int,
    ) -> AuditEntry:
        """Log an LLM call"""
        return self.log_event(
            event_type="llm_call",
            input_hash=prompt_hash,
            output_hash=response_hash,
            metadata={
                "session_id": session_id,
                "action": action,
                "confidence": confidence,
                "tokens_used": tokens_used,
            },
        )

    def log_decision(
        self,
        decision: Any,
        state_hash: str,
        session_id: str,
    ) -> AuditEntry:
        """Log a decision"""
        decision_dict = decision.to_dict() if hasattr(decision, "to_dict") else {"action": str(decision)}
        decision_hash = hashlib.sha256(
            json.dumps(decision_dict, sort_keys=True).encode()
        ).hexdigest()
        return self.log_event(
            event_type="decision",
            input_hash=state_hash,
            output_hash=decision_hash,
            metadata={
                "session_id": session_id,
                "decision": decision_dict,
            },
        )

    def log_event(
        self,
        event_type: str,
        input_hash: str,
        output_hash: str,
        metadata: Optional[dict] = None,
    ) -> AuditEntry:
        """Log a generic event"""
        entry = AuditEntry(
            entry_id=uuid.uuid4().hex[:16],
            timestamp=time.time(),
            event_type=event_type,
            input_hash=input_hash,
            output_hash=output_hash,
            metadata=metadata or {},
        )

        # Sign if PQC engine available
        if self._pqc and self._signing_keypair:
            entry.signature = self._pqc.sign(
                entry.signable_bytes(), self._signing_keypair,
            )

        self._entries.append(entry)

        # Persist
        if self._log_file:
            self._append_to_file(entry)

        return entry

    def verify_entry(self, entry: AuditEntry) -> bool:
        """Verify a single entry's signature"""
        if entry.signature is None:
            return True  # Unsigned mode

        if not self._pqc or not self._signing_keypair:
            logger.warning("Cannot verify: no PQC engine or keypair")
            return False

        from .pqc import PQCKeyPair
        verify_key = PQCKeyPair(
            algorithm=self._signing_keypair.algorithm,
            public_key=self._signing_keypair.public_key,
            secret_key=b"",
            key_id=self._signing_keypair.key_id,
        )
        return self._pqc.verify(entry.signable_bytes(), entry.signature, verify_key)

    def verify_all(self) -> tuple[int, int]:
        """Verify all entries. Returns (valid_count, invalid_count)."""
        valid = 0
        invalid = 0
        for entry in self._entries:
            if self.verify_entry(entry):
                valid += 1
            else:
                invalid += 1
        return valid, invalid

    def get_entries(
        self,
        event_type: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
    ) -> list[AuditEntry]:
        """Query entries with optional filters"""
        results = self._entries
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if since is not None:
            results = [e for e in results if e.timestamp >= since]
        if until is not None:
            results = [e for e in results if e.timestamp <= until]
        return results

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def _append_to_file(self, entry: AuditEntry) -> None:
        try:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(entry.to_dict(), default=str) + "\n")
        except OSError as e:
            logger.error(f"Failed to write audit log: {e}")

    def _load_from_file(self) -> None:
        try:
            with open(self._log_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._entries.append(AuditEntry.from_dict(json.loads(line)))
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load audit log: {e}")
