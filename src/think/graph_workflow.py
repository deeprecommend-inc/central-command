"""
Graph Workflow - LangGraph-based stateful workflow for CCP
"""
import asyncio
from datetime import datetime
from typing import Any, Callable, Optional, Literal
from loguru import logger

from .agent_state import (
    AgentState, CCPPhase, ThoughtStep, TransitionRecord,
    TransitionReason, create_initial_state, state_to_summary
)
from .llm_decision import LLMDecisionMaker, LLMConfig, TransitionDecider
from .human_in_loop import (
    HumanApprovalManager, ApprovalConfig, ApprovalStatus,
    update_state_for_approval, update_state_after_approval
)
from .thought_log import ThoughtLogger, extract_thought_chain_from_state
from .strategy import Decision
from ..sense import SystemState


# Type alias for routing
RouteType = Literal[
    "sense", "think", "command", "control", "learn",
    "awaiting_approval", "completed", "aborted"
]


class CCPGraphWorkflow:
    """
    LangGraph-based workflow for CCP cycle.

    Implements a stateful graph that routes through:
    Sense -> Think -> (Approval?) -> Command -> Control -> Learn

    Example:
        workflow = CCPGraphWorkflow()

        # Optional: Configure LLM
        workflow.configure_llm(LLMConfig(provider="openai"))

        # Register approval handler
        workflow.on_approval_request(my_handler)

        # Run the workflow
        result = await workflow.run(
            task_id="task_001",
            task_type="navigate",
            target="https://example.com"
        )
    """

    def __init__(
        self,
        llm_config: Optional[LLMConfig] = None,
        approval_config: Optional[ApprovalConfig] = None,
        thought_log_dir: Optional[str] = None,
        llm_guard=None,
        pqc_engine=None,
        audit_logger=None,
    ):
        self.llm_guard = llm_guard
        self.pqc_engine = pqc_engine
        self.audit_logger = audit_logger
        self._signing_keypair = None

        # Generate signing keypair if PQC engine provided
        if self.pqc_engine:
            self._signing_keypair = self.pqc_engine.generate_signing_keypair()

        self.llm_maker = LLMDecisionMaker(
            llm_config, guard=llm_guard, audit_logger=audit_logger,
        )
        self.approval_manager = HumanApprovalManager(approval_config)
        self.thought_logger = ThoughtLogger(log_dir=thought_log_dir)
        self.transition_decider = TransitionDecider(self.llm_maker)

        # External layer executors (injected)
        self._sense_executor: Optional[Callable] = None
        self._command_executor: Optional[Callable] = None
        self._control_executor: Optional[Callable] = None
        self._learn_executor: Optional[Callable] = None

        # Graph compiled flag
        self._graph = None

    def _add_thought_step(self, state: AgentState, step: ThoughtStep) -> None:
        """Add thought step, compatible with both LangGraph and fallback modes."""
        if self._graph:
            state["thought_chain"] = [step]
        else:
            chain = state.get("thought_chain", [])
            chain.append(step)
            state["thought_chain"] = chain

    def _log_phase(
        self,
        state: AgentState,
        step: ThoughtStep,
        prev_phase: CCPPhase,
        to_phase: CCPPhase,
        reason: str,
    ) -> None:
        """Unified thought step + transition logging."""
        self._add_thought_step(state, step)
        self.thought_logger.log_step(state.get("cycle_id", ""), step)
        self.thought_logger.log_transition(
            state.get("cycle_id", ""), prev_phase, to_phase, reason,
        )

    def configure_llm(self, config: LLMConfig) -> None:
        """Configure LLM for decision making"""
        self.llm_maker = LLMDecisionMaker(
            config, guard=self.llm_guard, audit_logger=self.audit_logger,
        )
        self.transition_decider = TransitionDecider(self.llm_maker)

    def on_approval_request(self, handler: Callable) -> None:
        """Register approval request handler"""
        self.approval_manager.register_handler(handler)

    def set_sense_executor(self, executor: Callable) -> None:
        """Set the Sense layer executor"""
        self._sense_executor = executor

    def set_command_executor(self, executor: Callable) -> None:
        """Set the Command layer executor"""
        self._command_executor = executor

    def set_control_executor(self, executor: Callable) -> None:
        """Set the Control layer executor"""
        self._control_executor = executor

    def set_learn_executor(self, executor: Callable) -> None:
        """Set the Learn layer executor"""
        self._learn_executor = executor

    def _compile_graph(self):
        """Compile the LangGraph workflow"""
        try:
            from langgraph.graph import StateGraph, END

            # Create the graph
            workflow = StateGraph(AgentState)

            # Add nodes
            workflow.add_node("sense", self._sense_node)
            workflow.add_node("think", self._think_node)
            workflow.add_node("awaiting_approval", self._approval_node)
            workflow.add_node("command", self._command_node)
            workflow.add_node("control", self._control_node)
            workflow.add_node("learn", self._learn_node)

            # Set entry point
            workflow.set_entry_point("sense")

            # Add conditional edges
            workflow.add_conditional_edges(
                "sense",
                self._route_from_sense,
                {
                    "think": "think",
                    "aborted": END,
                }
            )

            workflow.add_conditional_edges(
                "think",
                self._route_from_think,
                {
                    "command": "command",
                    "awaiting_approval": "awaiting_approval",
                    "aborted": END,
                }
            )

            workflow.add_conditional_edges(
                "awaiting_approval",
                self._route_from_approval,
                {
                    "command": "command",
                    "aborted": END,
                    "awaiting_approval": "awaiting_approval",
                }
            )

            workflow.add_conditional_edges(
                "command",
                self._route_from_command,
                {
                    "control": "control",
                    "aborted": END,
                }
            )

            workflow.add_conditional_edges(
                "control",
                self._route_from_control,
                {
                    "learn": "learn",
                    "sense": "sense",  # Retry loop
                    "aborted": END,
                }
            )

            workflow.add_conditional_edges(
                "learn",
                self._route_from_learn,
                {
                    "completed": END,
                }
            )

            self._graph = workflow.compile()
            logger.info("LangGraph workflow compiled successfully")

        except ImportError:
            logger.warning("langgraph not installed, using fallback workflow")
            self._graph = None

    async def run(
        self,
        task_id: str,
        task_type: str,
        target: str,
        params: Optional[dict] = None,
        max_retries: int = 3,
    ) -> AgentState:
        """
        Run the CCP workflow.

        Args:
            task_id: Unique task identifier
            task_type: Type of task
            target: Target URL or identifier
            params: Additional parameters
            max_retries: Maximum retry attempts

        Returns:
            Final AgentState
        """
        # Create initial state
        state = create_initial_state(
            task_id=task_id,
            task_type=task_type,
            target=target,
            params=params,
            max_retries=max_retries,
        )

        # Start thought chain
        chain = self.thought_logger.start_chain(
            task_id=task_id,
            metadata={"task_type": task_type, "target": target}
        )
        state["cycle_id"] = chain.cycle_id

        logger.info(f"Starting CCP workflow: {task_id} -> {target}")

        try:
            if self._graph is None:
                self._compile_graph()

            if self._graph:
                # Run through LangGraph
                final_state = await self._graph.ainvoke(state)
            else:
                # Fallback to manual execution
                final_state = await self._run_fallback(state)

        except Exception as e:
            logger.error(f"Workflow error: {e}")
            state["final_success"] = False
            state["final_error"] = str(e)
            state["current_phase"] = CCPPhase.ABORTED
            final_state = state

        # Complete thought chain
        self.thought_logger.complete_chain(
            cycle_id=chain.cycle_id,
            decision={
                "action": final_state.get("decision_action", ""),
                "confidence": final_state.get("decision_confidence", 0),
            },
            outcome={
                "success": final_state.get("final_success", False),
                "error": final_state.get("final_error"),
            }
        )

        # Set timing
        final_state["end_time"] = datetime.now()
        if final_state.get("start_time"):
            duration = (final_state["end_time"] - final_state["start_time"]).total_seconds() * 1000
            final_state["total_duration_ms"] = duration

        logger.info(
            f"Workflow completed: {task_id} -> "
            f"{'success' if final_state.get('final_success') else 'failed'}"
        )

        return final_state

    async def _run_fallback(self, state: AgentState) -> AgentState:
        """Fallback workflow without LangGraph"""
        while True:
            phase = state.get("current_phase", CCPPhase.SENSE)

            if phase == CCPPhase.SENSE:
                state = await self._sense_node(state)
                next_route = self._route_from_sense(state)
            elif phase == CCPPhase.THINK:
                state = await self._think_node(state)
                next_route = self._route_from_think(state)
            elif phase == CCPPhase.AWAITING_APPROVAL:
                state = await self._approval_node(state)
                next_route = self._route_from_approval(state)
            elif phase == CCPPhase.COMMAND:
                state = await self._command_node(state)
                next_route = self._route_from_command(state)
            elif phase == CCPPhase.CONTROL:
                state = await self._control_node(state)
                next_route = self._route_from_control(state)
            elif phase == CCPPhase.LEARN:
                state = await self._learn_node(state)
                next_route = self._route_from_learn(state)
            else:
                break

            if next_route in ("completed", "aborted"):
                break

            # Update phase for next iteration
            state["current_phase"] = CCPPhase(next_route)

        return state

    # ========== Node Implementations ==========

    async def _sense_node(self, state: AgentState) -> AgentState:
        """Sense layer node - collect system state"""
        start_time = datetime.now()
        prev_phase = state.get("current_phase", CCPPhase.SENSE)

        logger.debug(f"[SENSE] Collecting system state for {state.get('task_id')}")

        # Execute sense layer
        if self._sense_executor:
            try:
                sense_result = await self._sense_executor(state)
                state["system_state"] = sense_result.get("system_state")
                state["recent_events"] = sense_result.get("recent_events", [])
                state["metrics_summary"] = sense_result.get("metrics_summary", {})
            except Exception as e:
                logger.error(f"Sense executor error: {e}")
                errors = state.get("error_history", [])
                errors.append(f"sense_error: {e}")
                state["error_history"] = errors
        else:
            # Default: create empty system state
            state["system_state"] = SystemState()

        state["current_phase"] = CCPPhase.SENSE

        # Log thought step
        step = ThoughtStep(
            step_id=f"sense_{state.get('task_id')}_{int(start_time.timestamp())}",
            phase=CCPPhase.SENSE,
            timestamp=start_time,
            reasoning="Collected system state and metrics",
            inputs={"task_id": state.get("task_id")},
            outputs={"has_system_state": state.get("system_state") is not None},
            confidence=1.0,
            duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
        )
        self._log_phase(state, step, prev_phase, CCPPhase.SENSE, TransitionReason.INITIAL.value)

        return state

    async def _think_node(self, state: AgentState) -> AgentState:
        """Think layer node - make decision using LLM"""
        start_time = datetime.now()
        prev_phase = state.get("current_phase", CCPPhase.SENSE)

        logger.debug(f"[THINK] Making decision for {state.get('task_id')}")

        # Use LLM to make decision
        decision, thought = await self.llm_maker.decide(state)

        state["decision_action"] = decision.action
        state["decision_params"] = decision.params
        state["decision_confidence"] = decision.confidence
        state["decision_reasoning"] = decision.reasoning
        state["current_phase"] = CCPPhase.THINK

        # Sign decision with PQC if engine provided
        if self.pqc_engine and self._signing_keypair:
            decision.signature = self.pqc_engine.sign(
                decision.signable_bytes(), self._signing_keypair,
            )

        # Check if approval is needed
        if self.llm_maker.requires_approval(decision):
            state["requires_approval"] = True
            logger.info(
                f"Decision requires approval: {decision.action} "
                f"(confidence: {decision.confidence:.2f})"
            )
        else:
            state["requires_approval"] = False

        self._log_phase(state, thought, prev_phase, CCPPhase.THINK, TransitionReason.DATA_COLLECTED.value)

        return state

    async def _approval_node(self, state: AgentState) -> AgentState:
        """Approval node - wait for human approval"""
        start_time = datetime.now()
        prev_phase = state.get("current_phase", CCPPhase.THINK)

        logger.debug(f"[APPROVAL] Waiting for approval on {state.get('task_id')}")

        decision = Decision(
            action=state.get("decision_action", ""),
            params=state.get("decision_params", {}),
            confidence=state.get("decision_confidence", 0),
            reasoning=state.get("decision_reasoning", ""),
        )

        # Create approval request
        request = self.approval_manager.create_request(
            task_id=state.get("task_id", ""),
            decision=decision,
            state=state,
            context=f"Low confidence decision: {decision.confidence:.2f}",
        )

        state = update_state_for_approval(state, decision, request)

        # Wait for approval
        status = await self.approval_manager.wait_for_approval(request)

        # Update state based on approval
        state = update_state_after_approval(
            state,
            status,
            request.resolution_reason or "",
        )

        # Log thought step
        step = ThoughtStep(
            step_id=f"approval_{state.get('task_id')}_{int(start_time.timestamp())}",
            phase=CCPPhase.AWAITING_APPROVAL,
            timestamp=start_time,
            reasoning=f"Approval {status.value}: {request.resolution_reason or 'No reason'}",
            inputs={"request_id": request.request_id, "confidence": decision.confidence},
            outputs={"status": status.value},
            confidence=1.0 if status == ApprovalStatus.APPROVED else 0.0,
            duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
        )
        self._log_phase(state, step, prev_phase, CCPPhase.AWAITING_APPROVAL, TransitionReason.LOW_CONFIDENCE.value)

        return state

    async def _command_node(self, state: AgentState) -> AgentState:
        """Command layer node - execute the command"""
        start_time = datetime.now()
        prev_phase = state.get("current_phase", CCPPhase.THINK)

        logger.debug(f"[COMMAND] Executing command for {state.get('task_id')}")

        state["current_phase"] = CCPPhase.COMMAND

        if self._command_executor:
            try:
                result = await self._command_executor(state)
                state["command_result"] = result.get("data")
                state["command_success"] = result.get("success", False)
                state["command_error"] = result.get("error")

                if not state["command_success"] and result.get("error"):
                    errors = state.get("error_history", [])
                    errors.append(result["error"])
                    state["error_history"] = errors

            except Exception as e:
                logger.error(f"Command executor error: {e}")
                state["command_success"] = False
                state["command_error"] = str(e)
                errors = state.get("error_history", [])
                errors.append(str(e))
                state["error_history"] = errors
        else:
            # No executor - mark as failed
            state["command_success"] = False
            state["command_error"] = "No command executor configured"

        # Log thought step
        step = ThoughtStep(
            step_id=f"command_{state.get('task_id')}_{int(start_time.timestamp())}",
            phase=CCPPhase.COMMAND,
            timestamp=start_time,
            reasoning=f"Command {'succeeded' if state['command_success'] else 'failed'}",
            inputs={"action": state.get("decision_action")},
            outputs={"success": state["command_success"], "error": state.get("command_error")},
            confidence=1.0 if state["command_success"] else 0.5,
            duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
        )
        reason = (TransitionReason.APPROVED.value if state.get("approval_status") == "approved"
                  else TransitionReason.DECISION_MADE.value)
        self._log_phase(state, step, prev_phase, CCPPhase.COMMAND, reason)

        return state

    async def _control_node(self, state: AgentState) -> AgentState:
        """Control layer node - monitor execution"""
        start_time = datetime.now()
        prev_phase = state.get("current_phase", CCPPhase.COMMAND)

        logger.debug(f"[CONTROL] Monitoring execution for {state.get('task_id')}")

        state["current_phase"] = CCPPhase.CONTROL

        if self._control_executor:
            try:
                control_result = await self._control_executor(state)
                state["execution_state"] = control_result.get("state", "completed")
                state["feedback"] = control_result.get("feedback", [])
            except Exception as e:
                logger.error(f"Control executor error: {e}")
                state["execution_state"] = "error"
        else:
            state["execution_state"] = "completed" if state.get("command_success") else "failed"

        # Check for retry
        if not state.get("command_success"):
            retry_count = state.get("retry_count", 0)
            max_retries = state.get("max_retries", 3)
            if retry_count < max_retries:
                state["retry_count"] = retry_count + 1
                logger.info(f"Retry {state['retry_count']}/{max_retries}")

        # Log thought step
        step = ThoughtStep(
            step_id=f"control_{state.get('task_id')}_{int(start_time.timestamp())}",
            phase=CCPPhase.CONTROL,
            timestamp=start_time,
            reasoning=f"Execution state: {state['execution_state']}",
            inputs={"command_success": state.get("command_success")},
            outputs={"execution_state": state["execution_state"], "retry_count": state.get("retry_count", 0)},
            confidence=1.0,
            duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
        )
        self._log_phase(state, step, prev_phase, CCPPhase.CONTROL, TransitionReason.COMMAND_ISSUED.value)

        return state

    async def _learn_node(self, state: AgentState) -> AgentState:
        """Learn layer node - record learning"""
        start_time = datetime.now()
        prev_phase = state.get("current_phase", CCPPhase.CONTROL)

        logger.debug(f"[LEARN] Recording learning for {state.get('task_id')}")

        state["current_phase"] = CCPPhase.LEARN

        if self._learn_executor:
            try:
                learn_result = await self._learn_executor(state)
                state["patterns_detected"] = learn_result.get("patterns", [])
                state["knowledge_updates"] = learn_result.get("knowledge_updates", [])
            except Exception as e:
                logger.error(f"Learn executor error: {e}")

        # Set final outcome
        state["final_success"] = state.get("command_success", False)
        if not state["final_success"] and not state.get("final_error"):
            state["final_error"] = state.get("command_error")

        state["current_phase"] = CCPPhase.COMPLETED

        # Log thought step
        step = ThoughtStep(
            step_id=f"learn_{state.get('task_id')}_{int(start_time.timestamp())}",
            phase=CCPPhase.LEARN,
            timestamp=start_time,
            reasoning="Learning recorded, cycle completed",
            inputs={"success": state["final_success"]},
            outputs={"patterns": len(state.get("patterns_detected", []))},
            confidence=1.0,
            duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
        )
        self._log_phase(state, step, prev_phase, CCPPhase.LEARN, TransitionReason.EXECUTION_COMPLETED.value)

        return state

    # ========== Routing Functions ==========

    def _route_from_sense(self, state: AgentState) -> RouteType:
        """Route from Sense node"""
        # Check for critical errors
        error_history = state.get("error_history", [])
        if len(error_history) > 5:
            return "aborted"
        return "think"

    def _route_from_think(self, state: AgentState) -> RouteType:
        """Route from Think node"""
        decision_action = state.get("decision_action", "")

        if decision_action == "abort":
            return "aborted"

        if state.get("requires_approval", False):
            return "awaiting_approval"

        return "command"

    def _route_from_approval(self, state: AgentState) -> RouteType:
        """Route from Approval node"""
        approval_status = state.get("approval_status")

        if approval_status == "approved":
            return "command"
        elif approval_status in ("rejected", "timeout"):
            return "aborted"
        return "awaiting_approval"

    def _route_from_command(self, state: AgentState) -> RouteType:
        """Route from Command node"""
        return "control"

    def _route_from_control(self, state: AgentState) -> RouteType:
        """Route from Control node"""
        if state.get("command_success", False):
            return "learn"

        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)

        if retry_count < max_retries:
            return "sense"  # Retry loop

        return "aborted"

    def _route_from_learn(self, state: AgentState) -> RouteType:
        """Route from Learn node"""
        return "completed"

    def get_stats(self) -> dict:
        """Get workflow statistics"""
        return {
            "thought_logger": self.thought_logger.get_stats(),
            "approval_manager": self.approval_manager.get_stats(),
        }
