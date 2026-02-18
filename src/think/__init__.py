"""
Think Layer - Decision Making

v2: LangGraph-based stateful workflow with LLM decision making
"""
from .decision_context import DecisionContext, TaskContext
from .strategy import Strategy, Decision, RetryStrategy, ProxySelectionStrategy, AdaptiveStrategy
from .rules_engine import RulesEngine, Rule

# v2: Agent State
from .agent_state import (
    AgentState,
    CCPPhase,
    TransitionReason,
    ThoughtStep,
    TransitionRecord,
    create_initial_state,
    state_to_summary,
)

# v2: LLM Decision Maker
from .llm_decision import (
    LLMDecisionMaker,
    LLMConfig,
    TransitionDecider,
)

# v2: Human-in-the-Loop
from .human_in_loop import (
    HumanApprovalManager,
    ApprovalConfig,
    ApprovalRequest,
    ApprovalStatus,
    update_state_for_approval,
    update_state_after_approval,
)

# v2: Thought Logging
from .thought_log import (
    ThoughtLogger,
    ThoughtChain,
    extract_thought_chain_from_state,
)

# v2: Graph Workflow
from .graph_workflow import CCPGraphWorkflow

# Security Layer
from ..security import LLMGuard, GuardConfig, PQCEngine, AuditLogger

__all__ = [
    # v1 exports
    "DecisionContext",
    "TaskContext",
    "Strategy",
    "Decision",
    "RetryStrategy",
    "ProxySelectionStrategy",
    "AdaptiveStrategy",
    "RulesEngine",
    "Rule",
    # v2: Agent State
    "AgentState",
    "CCPPhase",
    "TransitionReason",
    "ThoughtStep",
    "TransitionRecord",
    "create_initial_state",
    "state_to_summary",
    # v2: LLM Decision
    "LLMDecisionMaker",
    "LLMConfig",
    "TransitionDecider",
    # v2: Human-in-the-Loop
    "HumanApprovalManager",
    "ApprovalConfig",
    "ApprovalRequest",
    "ApprovalStatus",
    "update_state_for_approval",
    "update_state_after_approval",
    # v2: Thought Logging
    "ThoughtLogger",
    "ThoughtChain",
    "extract_thought_chain_from_state",
    # v2: Graph Workflow
    "CCPGraphWorkflow",
    # Security
    "LLMGuard",
    "GuardConfig",
    "PQCEngine",
    "AuditLogger",
]
