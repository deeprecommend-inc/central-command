"""
API Models - Pydantic schemas for request/response
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from enum import Enum
from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class TaskStatus(str, Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProxyType(str, Enum):
    """Proxy type options"""
    RESIDENTIAL = "residential"
    MOBILE = "mobile"
    DATACENTER = "datacenter"
    ISP = "isp"
    NONE = "none"


# =============================================================================
# Request Models
# =============================================================================

class TaskRequest(BaseModel):
    """Request to execute a task"""
    target: str = Field(..., description="Target URL or task identifier")
    task_type: str = Field(default="navigate", description="Type of task")
    proxy_type: ProxyType = Field(default=ProxyType.NONE, description="Proxy type to use")
    priority: int = Field(default=0, ge=0, le=10, description="Task priority (0-10)")
    timeout_seconds: float = Field(default=30.0, gt=0, description="Task timeout")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = {"json_schema_extra": {"example": {
        "target": "https://example.com",
        "task_type": "navigate",
        "proxy_type": "none",
        "priority": 5,
        "timeout_seconds": 30.0,
    }}}


class BatchTaskRequest(BaseModel):
    """Request to execute multiple tasks"""
    tasks: list[TaskRequest] = Field(..., min_length=1, max_length=100)
    parallel: bool = Field(default=True, description="Execute in parallel")
    max_concurrent: int = Field(default=5, ge=1, le=20)


class ReplayRequest(BaseModel):
    """Request to run simulation replay"""
    experience_file: str = Field(..., description="Path to experience JSON file")
    episodes: int = Field(default=10, ge=1, le=1000)
    policy: str = Field(default="default", description="Policy to use")


# =============================================================================
# Response Models
# =============================================================================

class TaskResponse(BaseModel):
    """Response for a task execution"""
    task_id: str
    status: TaskStatus
    target: str
    result: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"json_schema_extra": {"example": {
        "task_id": "task-123",
        "status": "completed",
        "target": "https://example.com",
        "result": {"title": "Example Domain", "url": "https://example.com/"},
        "duration_ms": 1523.5,
        "created_at": "2025-01-01T12:00:00Z",
        "completed_at": "2025-01-01T12:00:01Z",
    }}}


class BatchTaskResponse(BaseModel):
    """Response for batch task execution"""
    batch_id: str
    total: int
    completed: int
    failed: int
    results: list[TaskResponse]


class StatsResponse(BaseModel):
    """System statistics response"""
    uptime_seconds: float
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    success_rate: float
    avg_duration_ms: float
    active_tasks: int
    experience_count: int
    proxy_stats: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = "healthy"
    version: str = "2.0.0"
    timestamp: datetime
    components: dict[str, str] = Field(default_factory=dict)


class ExperienceResponse(BaseModel):
    """Experience data response"""
    id: str
    state: dict[str, Any]
    action: dict[str, Any]
    outcome: dict[str, Any]
    reward: float
    timestamp: datetime


class ExperienceListResponse(BaseModel):
    """List of experiences response"""
    total: int
    experiences: list[ExperienceResponse]
    statistics: dict[str, Any]


class ReplayResultResponse(BaseModel):
    """Replay simulation result"""
    policy_id: str
    total_episodes: int
    success_rate: float
    avg_reward: float
    avg_duration_ms: float
    metrics: dict[str, float]


class EventMessage(BaseModel):
    """WebSocket event message"""
    event_type: str
    source: str
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)


# =============================================================================
# Error Models
# =============================================================================

class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    detail: str | None = None
    code: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


# =============================================================================
# LangGraph Workflow Models (v2)
# =============================================================================

class WorkflowPhase(str, Enum):
    """CCP workflow phases"""
    SENSE = "sense"
    THINK = "think"
    COMMAND = "command"
    CONTROL = "control"
    LEARN = "learn"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    ABORTED = "aborted"


class WorkflowRequest(BaseModel):
    """Request to execute a LangGraph workflow"""
    target: str = Field(..., description="Target URL or identifier")
    task_type: str = Field(default="navigate")
    proxy_type: ProxyType = Field(default=ProxyType.NONE)
    max_retries: int = Field(default=3, ge=1, le=10)
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    enable_approval: bool = Field(default=True, description="Enable human-in-the-loop")
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"json_schema_extra": {"example": {
        "target": "https://example.com",
        "task_type": "navigate",
        "max_retries": 3,
        "confidence_threshold": 0.7,
        "enable_approval": True,
    }}}


class ThoughtStepResponse(BaseModel):
    """A single thought step in the chain"""
    step_id: str
    phase: WorkflowPhase
    timestamp: datetime
    reasoning: str
    confidence: float
    duration_ms: float
    inputs: dict[str, Any]
    outputs: dict[str, Any]


class WorkflowResponse(BaseModel):
    """Response for workflow execution"""
    task_id: str
    cycle_id: str
    status: WorkflowPhase
    target: str
    success: bool
    decision_action: str | None = None
    decision_confidence: float = 0.0
    decision_reasoning: str | None = None
    error: str | None = None
    thought_chain: list[ThoughtStepResponse] = Field(default_factory=list)
    retry_count: int = 0
    duration_ms: float = 0.0
    created_at: datetime
    completed_at: datetime | None = None


# =============================================================================
# Human-in-the-Loop Models (v2)
# =============================================================================

class ApprovalStatusEnum(str, Enum):
    """Approval request status"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    ESCALATED = "escalated"


class ApprovalRequestResponse(BaseModel):
    """Response for an approval request"""
    request_id: str
    task_id: str
    decision_action: str
    decision_confidence: float
    decision_reasoning: str
    state_summary: dict[str, Any]
    status: ApprovalStatusEnum
    priority: int
    context: str
    created_at: datetime
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_reason: str | None = None


class ApprovalListResponse(BaseModel):
    """List of pending approval requests"""
    total: int
    pending: int
    resolved: int
    requests: list[ApprovalRequestResponse]


class ApprovalDecisionRequest(BaseModel):
    """Request to approve or reject"""
    approved_by: str = Field(..., description="Identifier of the approver")
    reason: str = Field(default="", description="Reason for decision")


class ApprovalStatsResponse(BaseModel):
    """Approval statistics"""
    pending_count: int
    resolved_count: int
    approved_count: int
    rejected_count: int
    timeout_count: int
    approval_rate: float


# =============================================================================
# Thought Log Models (v2)
# =============================================================================

class TransitionResponse(BaseModel):
    """A phase transition record"""
    from_phase: WorkflowPhase
    to_phase: WorkflowPhase
    reason: str
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ThoughtChainResponse(BaseModel):
    """Complete thought chain for a workflow"""
    cycle_id: str
    task_id: str
    started_at: datetime
    completed_at: datetime | None = None
    steps: list[ThoughtStepResponse]
    transitions: list[TransitionResponse]
    final_decision: dict[str, Any] | None = None
    final_outcome: dict[str, Any] | None = None
    duration_ms: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class ThoughtChainListResponse(BaseModel):
    """List of thought chains"""
    total: int
    chains: list[ThoughtChainResponse]


class ThoughtLogStatsResponse(BaseModel):
    """Thought log statistics"""
    active_count: int
    completed_count: int
    avg_duration_ms: float
    avg_steps: float
    max_duration_ms: float
    min_duration_ms: float


# =============================================================================
# Channel Models
# =============================================================================

class ChannelSendRequest(BaseModel):
    """Request to send a message via a channel"""
    to: str = Field(..., description="Recipient (channel name, email, URL)")
    text: str = Field(..., description="Message text")
    media_url: str | None = Field(default=None, description="Optional media URL")
    thread_id: str | None = Field(default=None, description="Optional thread ID")


class BroadcastRequest(BaseModel):
    """Request to broadcast a message to multiple channels"""
    channel_ids: list[str] = Field(..., min_length=1, description="Target channel IDs")
    to: str = Field(..., description="Recipient")
    text: str = Field(..., description="Message text")


class ChannelSendResponse(BaseModel):
    """Response for a channel send operation"""
    channel_id: str
    success: bool
    message_id: str = ""
    error: str = ""


class ChannelHealthResponse(BaseModel):
    """Health status of all channels"""
    channels: dict[str, str]
