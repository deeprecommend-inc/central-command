"""
Thought Log - Chain of Thought logging and storage
"""
import json
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from loguru import logger

from .agent_state import AgentState, CCPPhase, ThoughtStep, TransitionRecord


@dataclass
class ThoughtChain:
    """Complete chain of thought for a CCP cycle"""
    cycle_id: str
    task_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    steps: list[ThoughtStep] = field(default_factory=list)
    transitions: list[TransitionRecord] = field(default_factory=list)
    final_decision: Optional[dict] = None
    final_outcome: Optional[dict] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_step(self, step: ThoughtStep) -> None:
        """Add a thought step to the chain"""
        self.steps.append(step)

    def add_transition(self, transition: TransitionRecord) -> None:
        """Add a transition record to the chain"""
        self.transitions.append(transition)

    def complete(
        self,
        decision: dict,
        outcome: dict,
    ) -> None:
        """Mark the chain as complete"""
        self.completed_at = datetime.now()
        self.final_decision = decision
        self.final_outcome = outcome

    def get_reasoning_summary(self) -> str:
        """Get a summary of the reasoning chain"""
        if not self.steps:
            return "No reasoning steps recorded"

        lines = [f"Thought Chain for {self.cycle_id}:"]
        for i, step in enumerate(self.steps, 1):
            lines.append(
                f"  {i}. [{step.phase.value}] {step.reasoning} "
                f"(confidence: {step.confidence:.2f})"
            )

        if self.final_decision:
            action = self.final_decision.get("action", "unknown")
            lines.append(f"  Final Decision: {action}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "cycle_id": self.cycle_id,
            "task_id": self.task_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "steps": [s.to_dict() for s in self.steps],
            "transitions": [t.to_dict() for t in self.transitions],
            "final_decision": self.final_decision,
            "final_outcome": self.final_outcome,
            "metadata": self.metadata,
            "duration_ms": self.get_total_duration_ms(),
            "step_count": len(self.steps),
        }

    def get_total_duration_ms(self) -> float:
        """Calculate total duration in milliseconds"""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return sum(s.duration_ms for s in self.steps)

    @classmethod
    def from_dict(cls, data: dict) -> "ThoughtChain":
        """Create from dictionary"""
        chain = cls(
            cycle_id=data["cycle_id"],
            task_id=data["task_id"],
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=(
                datetime.fromisoformat(data["completed_at"])
                if data.get("completed_at") else None
            ),
            final_decision=data.get("final_decision"),
            final_outcome=data.get("final_outcome"),
            metadata=data.get("metadata", {}),
        )

        for step_data in data.get("steps", []):
            step = ThoughtStep(
                step_id=step_data["step_id"],
                phase=CCPPhase(step_data["phase"]),
                timestamp=datetime.fromisoformat(step_data["timestamp"]),
                reasoning=step_data["reasoning"],
                inputs=step_data["inputs"],
                outputs=step_data["outputs"],
                confidence=step_data["confidence"],
                duration_ms=step_data["duration_ms"],
            )
            chain.steps.append(step)

        for trans_data in data.get("transitions", []):
            trans = TransitionRecord(
                from_phase=CCPPhase(trans_data["from_phase"]),
                to_phase=CCPPhase(trans_data["to_phase"]),
                reason=trans_data["reason"],
                timestamp=datetime.fromisoformat(trans_data["timestamp"]),
                metadata=trans_data.get("metadata", {}),
            )
            chain.transitions.append(trans)

        return chain


class ThoughtLogger:
    """
    Logger for Chain of Thought in CCP cycles.

    Records all reasoning steps, transitions, and decisions
    for later analysis and debugging.

    Example:
        thought_logger = ThoughtLogger(log_dir="logs/thoughts")

        # Start logging a cycle
        chain = thought_logger.start_chain(task_id="task_001")

        # Log reasoning steps
        thought_logger.log_step(chain.cycle_id, step)

        # Log transitions
        thought_logger.log_transition(chain.cycle_id, transition)

        # Complete the chain
        thought_logger.complete_chain(chain.cycle_id, decision, outcome)

        # Save to file
        thought_logger.save_chain(chain.cycle_id)
    """

    def __init__(
        self,
        log_dir: Optional[str] = None,
        max_chains: int = 1000,
        auto_save: bool = True,
    ):
        self.log_dir = Path(log_dir) if log_dir else None
        self.max_chains = max_chains
        self.auto_save = auto_save
        self._active_chains: dict[str, ThoughtChain] = {}
        self._completed_chains: deque[ThoughtChain] = deque(maxlen=max_chains)

        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def start_chain(
        self,
        task_id: str,
        metadata: Optional[dict] = None,
    ) -> ThoughtChain:
        """
        Start a new thought chain.

        Args:
            task_id: Task identifier
            metadata: Optional metadata

        Returns:
            New ThoughtChain
        """
        now = datetime.now()
        cycle_id = f"chain_{task_id}_{int(now.timestamp())}"

        chain = ThoughtChain(
            cycle_id=cycle_id,
            task_id=task_id,
            started_at=now,
            metadata=metadata or {},
        )

        self._active_chains[cycle_id] = chain
        logger.debug(f"Started thought chain: {cycle_id}")

        return chain

    def log_step(
        self,
        cycle_id: str,
        step: ThoughtStep,
    ) -> None:
        """
        Log a thought step to a chain.

        Args:
            cycle_id: Chain identifier
            step: ThoughtStep to log
        """
        chain = self._active_chains.get(cycle_id)
        if not chain:
            logger.warning(f"Chain {cycle_id} not found for step logging")
            return

        chain.add_step(step)
        logger.debug(
            f"Logged step to {cycle_id}: [{step.phase.value}] "
            f"{step.reasoning[:50]}..."
        )

    def log_transition(
        self,
        cycle_id: str,
        from_phase: CCPPhase,
        to_phase: CCPPhase,
        reason: str,
        metadata: Optional[dict] = None,
    ) -> TransitionRecord:
        """
        Log a phase transition.

        Args:
            cycle_id: Chain identifier
            from_phase: Source phase
            to_phase: Target phase
            reason: Transition reason
            metadata: Optional metadata

        Returns:
            TransitionRecord
        """
        chain = self._active_chains.get(cycle_id)

        transition = TransitionRecord(
            from_phase=from_phase,
            to_phase=to_phase,
            reason=reason,
            timestamp=datetime.now(),
            metadata=metadata or {},
        )

        if chain:
            chain.add_transition(transition)
            logger.debug(
                f"Logged transition in {cycle_id}: "
                f"{from_phase.value} -> {to_phase.value}"
            )
        else:
            logger.warning(f"Chain {cycle_id} not found for transition logging")

        return transition

    def complete_chain(
        self,
        cycle_id: str,
        decision: dict,
        outcome: dict,
    ) -> Optional[ThoughtChain]:
        """
        Complete a thought chain.

        Args:
            cycle_id: Chain identifier
            decision: Final decision
            outcome: Execution outcome

        Returns:
            Completed ThoughtChain or None
        """
        chain = self._active_chains.pop(cycle_id, None)
        if not chain:
            logger.warning(f"Chain {cycle_id} not found for completion")
            return None

        chain.complete(decision, outcome)
        self._completed_chains.append(chain)

        logger.info(
            f"Completed thought chain {cycle_id}: "
            f"{len(chain.steps)} steps, "
            f"{chain.get_total_duration_ms():.0f}ms"
        )

        if self.auto_save and self.log_dir:
            self.save_chain(cycle_id)

        return chain

    def save_chain(self, cycle_id: str) -> Optional[Path]:
        """
        Save a chain to file.

        Args:
            cycle_id: Chain identifier

        Returns:
            Path to saved file or None
        """
        if not self.log_dir:
            return None

        chain = self.get_chain(cycle_id)
        if not chain:
            logger.warning(f"Chain {cycle_id} not found for saving")
            return None

        # Create date-based subdirectory
        date_dir = self.log_dir / chain.started_at.strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)

        file_path = date_dir / f"{cycle_id}.json"

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(chain.to_dict(), f, indent=2, ensure_ascii=False)

        logger.debug(f"Saved thought chain to {file_path}")
        return file_path

    def load_chain(self, file_path: str) -> Optional[ThoughtChain]:
        """
        Load a chain from file.

        Args:
            file_path: Path to chain file

        Returns:
            Loaded ThoughtChain or None
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ThoughtChain.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load chain from {file_path}: {e}")
            return None

    def get_chain(self, cycle_id: str) -> Optional[ThoughtChain]:
        """Get a chain by ID"""
        if cycle_id in self._active_chains:
            return self._active_chains[cycle_id]
        return next(
            (c for c in self._completed_chains if c.cycle_id == cycle_id),
            None
        )

    def get_active_chains(self) -> list[ThoughtChain]:
        """Get all active chains"""
        return list(self._active_chains.values())

    def get_completed_chains(
        self,
        limit: int = 100,
        task_id: Optional[str] = None,
    ) -> list[ThoughtChain]:
        """Get completed chains with optional filtering"""
        if task_id:
            chains = [c for c in self._completed_chains if c.task_id == task_id]
            return chains[-limit:]
        return list(self._completed_chains)[-limit:]

    def get_stats(self) -> dict:
        """Get logger statistics"""
        completed = self._completed_chains

        if not completed:
            return {
                "active_count": len(self._active_chains),
                "completed_count": 0,
            }

        durations = [c.get_total_duration_ms() for c in completed]
        step_counts = [len(c.steps) for c in completed]

        return {
            "active_count": len(self._active_chains),
            "completed_count": len(completed),
            "avg_duration_ms": sum(durations) / len(durations),
            "avg_steps": sum(step_counts) / len(step_counts),
            "max_duration_ms": max(durations),
            "min_duration_ms": min(durations),
        }

    def export_chains(
        self,
        output_path: str,
        limit: int = 1000,
    ) -> int:
        """
        Export multiple chains to a single JSON file.

        Args:
            output_path: Output file path
            limit: Maximum chains to export

        Returns:
            Number of chains exported
        """
        chains = list(self._completed_chains)[-limit:]

        data = {
            "exported_at": datetime.now().isoformat(),
            "chain_count": len(chains),
            "chains": [c.to_dict() for c in chains],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported {len(chains)} chains to {output_path}")
        return len(chains)


def extract_thought_chain_from_state(state: AgentState) -> ThoughtChain:
    """
    Extract thought chain from agent state.

    Args:
        state: Agent state with thought_chain

    Returns:
        ThoughtChain
    """
    task_id = state.get("task_id", "unknown")
    cycle_id = state.get("cycle_id", f"chain_{task_id}")

    chain = ThoughtChain(
        cycle_id=cycle_id,
        task_id=task_id,
        started_at=state.get("start_time", datetime.now()),
        completed_at=state.get("end_time"),
    )

    # Add steps from state
    for step in state.get("thought_chain", []):
        if isinstance(step, ThoughtStep):
            chain.add_step(step)
        elif isinstance(step, dict):
            chain.add_step(ThoughtStep(
                step_id=step.get("step_id", ""),
                phase=CCPPhase(step.get("phase", "think")),
                timestamp=datetime.fromisoformat(step["timestamp"]),
                reasoning=step.get("reasoning", ""),
                inputs=step.get("inputs", {}),
                outputs=step.get("outputs", {}),
                confidence=step.get("confidence", 0.0),
                duration_ms=step.get("duration_ms", 0.0),
            ))

    # Add transitions from state
    for trans in state.get("transitions", []):
        if isinstance(trans, TransitionRecord):
            chain.add_transition(trans)

    # Set final decision and outcome
    if state.get("decision_action"):
        chain.final_decision = {
            "action": state.get("decision_action"),
            "params": state.get("decision_params", {}),
            "confidence": state.get("decision_confidence", 0.0),
            "reasoning": state.get("decision_reasoning", ""),
        }

    if state.get("command_result") is not None or state.get("final_success") is not None:
        chain.final_outcome = {
            "success": state.get("final_success", False),
            "result": state.get("command_result"),
            "error": state.get("final_error"),
        }

    return chain
