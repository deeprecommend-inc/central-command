"""
CCP API Server - FastAPI-based REST/WebSocket API

Features:
- REST endpoints for task execution
- WebSocket for real-time event streaming
- Background task processing
- Experience store API
- Replay/simulation API
- LangGraph workflow execution (v2)
- Human-in-the-Loop approval API (v2)
- Thought Log API (v2)
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from contextlib import asynccontextmanager
import uuid

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    TaskRequest,
    TaskResponse,
    BatchTaskRequest,
    BatchTaskResponse,
    TaskStatus,
    StatsResponse,
    HealthResponse,
    ExperienceResponse,
    ExperienceListResponse,
    ReplayRequest,
    ReplayResultResponse,
    EventMessage,
    ErrorResponse,
    # v2 models
    WorkflowRequest,
    WorkflowResponse,
    WorkflowPhase,
    ThoughtStepResponse,
    ApprovalRequestResponse,
    ApprovalListResponse,
    ApprovalDecisionRequest,
    ApprovalStatsResponse,
    ApprovalStatusEnum,
    ThoughtChainResponse,
    ThoughtChainListResponse,
    ThoughtLogStatsResponse,
    TransitionResponse,
    # Channel models
    ChannelSendRequest,
    BroadcastRequest,
    ChannelSendResponse,
    ChannelHealthResponse,
)
from ..learn import ExperienceStore, ReplayEngine, ReplayConfig
from ..sense import EventBus, Event
from ..command.channels import ChannelRegistry, SlackChannel, TeamsChannel, EmailChannel, WebhookChannel
from ..config_reload import ConfigReloader
from ..think import (
    CCPGraphWorkflow,
    LLMConfig,
    ApprovalConfig,
    HumanApprovalManager,
    ThoughtLogger,
    ApprovalStatus,
    CCPPhase,
)


# =============================================================================
# Global State
# =============================================================================

class CCPState:
    """Global CCP state container (Singleton)"""

    _instance: "CCPState | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # Core components
        self.experience_store = ExperienceStore(max_size=10000)
        self.event_bus = EventBus()
        self.start_time = datetime.now()

        # Task tracking
        self.task_count = 0
        self.success_count = 0
        self.fail_count = 0
        self.total_duration_ms = 0.0
        self.active_tasks: dict[str, TaskResponse] = {}
        self.active_workflows: dict[str, WorkflowResponse] = {}
        self.websocket_clients: list[WebSocket] = []
        self._lock = asyncio.Lock()

        # v2: LangGraph Workflow (reads LLM config from settings)
        try:
            from config.settings import settings as _settings
            _llm_config = LLMConfig(
                provider=_settings.llm_provider,
                model=_settings.llm_model,
                base_url=_settings.llm_base_url if _settings.llm_provider == "local" else "",
                api_key=_settings.llm_api_key or _settings.openai_api_key or "",
            )
        except Exception:
            _llm_config = LLMConfig(provider="openai", model="gpt-4o")
        self.workflow = CCPGraphWorkflow(
            llm_config=_llm_config,
            approval_config=ApprovalConfig(confidence_threshold=0.7),
            thought_log_dir="logs/thoughts",
        )

        # v2: Human-in-the-Loop (shared with workflow)
        self.approval_manager = self.workflow.approval_manager

        # v2: Thought Logger (shared with workflow)
        self.thought_logger = self.workflow.thought_logger

        # Channels
        self.channel_registry = ChannelRegistry()
        self._setup_channels()

        # Config reloader
        self.config_reloader = ConfigReloader()

        # Set up workflow executors
        self._setup_workflow_executors()

    def _setup_channels(self):
        """Auto-register channels from settings"""
        try:
            from config.settings import settings
        except Exception:
            return

        if settings.slack_webhook_url or settings.slack_bot_token:
            self.channel_registry.register(SlackChannel(
                webhook_url=settings.slack_webhook_url,
                bot_token=settings.slack_bot_token,
                default_channel=settings.slack_default_channel,
            ))
        if settings.teams_webhook_url:
            self.channel_registry.register(TeamsChannel(
                webhook_url=settings.teams_webhook_url,
            ))
        if settings.email_smtp_host:
            self.channel_registry.register(EmailChannel(
                smtp_host=settings.email_smtp_host,
                smtp_port=settings.email_smtp_port,
                smtp_user=settings.email_smtp_user,
                smtp_password=settings.email_smtp_password,
                from_address=settings.email_from,
            ))
        if settings.webhook_urls:
            for i, url in enumerate(settings.webhook_urls.split(",")):
                url = url.strip()
                if url:
                    self.channel_registry.register(WebhookChannel(
                        url=url,
                        channel_id=f"webhook_{i}",
                        label=f"Webhook {i}",
                    ))

    def _setup_workflow_executors(self):
        """Configure workflow layer executors"""
        from ..sense import SystemState

        async def sense_executor(state):
            # Get current system state
            return {
                "system_state": SystemState(
                    success_count=self.success_count,
                    error_count=self.fail_count,
                    active_tasks=len(self.active_tasks),
                ),
                "recent_events": [],
                "metrics_summary": self.get_stats(),
            }

        async def command_executor(state):
            # Simulate command execution (replace with actual WebAgent)
            target = state.get("target", "")
            await asyncio.sleep(0.1)  # Simulated work
            return {
                "success": True,
                "data": {"url": target, "title": f"Result for {target}"},
                "error": None,
            }

        async def control_executor(state):
            return {
                "state": "completed" if state.get("command_success") else "failed",
                "feedback": [],
            }

        async def learn_executor(state):
            return {"patterns": [], "knowledge_updates": []}

        self.workflow.set_sense_executor(sense_executor)
        self.workflow.set_command_executor(command_executor)
        self.workflow.set_control_executor(control_executor)
        self.workflow.set_learn_executor(learn_executor)

    async def record_task_result(self, task: TaskResponse) -> None:
        async with self._lock:
            self.task_count += 1
            self.total_duration_ms += task.duration_ms
            if task.status == TaskStatus.COMPLETED:
                self.success_count += 1
            elif task.status == TaskStatus.FAILED:
                self.fail_count += 1

    def get_stats(self) -> dict[str, Any]:
        uptime = (datetime.now() - self.start_time).total_seconds()
        workflow_stats = self.workflow.get_stats()
        return {
            "uptime_seconds": uptime,
            "total_tasks": self.task_count,
            "successful_tasks": self.success_count,
            "failed_tasks": self.fail_count,
            "success_rate": self.success_count / self.task_count if self.task_count > 0 else 0.0,
            "avg_duration_ms": self.total_duration_ms / self.task_count if self.task_count > 0 else 0.0,
            "active_tasks": len(self.active_tasks),
            "active_workflows": len(self.active_workflows),
            "experience_count": len(self.experience_store),
            "thought_logger": workflow_stats.get("thought_logger", {}),
            "approval_manager": workflow_stats.get("approval_manager", {}),
        }


# Global state instance
_ccp_state: CCPState | None = None


def get_ccp() -> CCPState:
    """Get global CCP state"""
    global _ccp_state
    if _ccp_state is None:
        _ccp_state = CCPState()
    return _ccp_state


# =============================================================================
# WebSocket Manager
# =============================================================================

class WebSocketManager:
    """Manage WebSocket connections for event streaming"""

    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.connections:
            self.connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        disconnected = []
        for connection in self.connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


ws_manager = WebSocketManager()


# =============================================================================
# Event Bus Integration
# =============================================================================

async def broadcast_event(event: Event) -> None:
    """Broadcast event to WebSocket clients"""
    message = EventMessage(
        event_type=event.event_type,
        source=event.source,
        data=event.data,
        timestamp=event.timestamp,
    )
    await ws_manager.broadcast(message.model_dump(mode="json"))


# =============================================================================
# App Factory
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    ccp = get_ccp()

    # Subscribe to events for WebSocket broadcast
    async def event_handler(event: Event):
        await broadcast_event(event)

    ccp.event_bus.subscribe("*", event_handler)

    # Start config reloader
    async def on_config_reload(plan):
        if plan.reload_channels:
            ccp.channel_registry = ChannelRegistry()
            ccp._setup_channels()

    ccp.config_reloader.on_reload(on_config_reload)
    await ccp.config_reloader.start()

    yield

    # Shutdown
    await ccp.config_reloader.stop()


def create_app() -> FastAPI:
    """Create FastAPI application"""
    app = FastAPI(
        title="CCP API",
        description="Central Command Platform - AI-driven automation orchestrator",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    register_routes(app)

    return app


def register_routes(app: FastAPI) -> None:
    """Register all API routes"""

    # =========================================================================
    # Health & Info
    # =========================================================================

    @app.get("/", tags=["Info"])
    async def root():
        return {"name": "CCP API", "version": "2.0.0", "status": "running"}

    @app.get("/health", response_model=HealthResponse, tags=["Info"])
    async def health():
        return HealthResponse(
            status="healthy",
            version="2.0.0",
            timestamp=datetime.now(),
            components={
                "api": "healthy",
                "experience_store": "healthy",
                "event_bus": "healthy",
            },
        )

    @app.get("/stats", response_model=StatsResponse, tags=["Info"])
    async def stats():
        ccp = get_ccp()
        data = ccp.get_stats()
        return StatsResponse(**data)

    # =========================================================================
    # Task Execution
    # =========================================================================

    @app.post("/tasks", response_model=TaskResponse, tags=["Tasks"])
    async def create_task(request: TaskRequest, background_tasks: BackgroundTasks):
        """Create and execute a new task"""
        ccp = get_ccp()
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        created_at = datetime.now()

        # Create initial response
        response = TaskResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            target=request.target,
            created_at=created_at,
        )

        # Store as active task
        ccp.active_tasks[task_id] = response

        # Publish event
        await ccp.event_bus.publish(Event(
            event_type="task.created",
            source="api",
            data={"task_id": task_id, "target": request.target},
        ))

        # Execute task in background
        background_tasks.add_task(execute_task, task_id, request)

        return response

    @app.get("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
    async def get_task(task_id: str):
        """Get task status and result"""
        ccp = get_ccp()
        if task_id not in ccp.active_tasks:
            raise HTTPException(status_code=404, detail="Task not found")
        return ccp.active_tasks[task_id]

    @app.post("/tasks/batch", response_model=BatchTaskResponse, tags=["Tasks"])
    async def create_batch_tasks(request: BatchTaskRequest):
        """Execute multiple tasks"""
        ccp = get_ccp()
        batch_id = f"batch-{uuid.uuid4().hex[:8]}"
        results: list[TaskResponse] = []

        if request.parallel:
            # Execute in parallel with semaphore
            semaphore = asyncio.Semaphore(request.max_concurrent)

            async def run_with_semaphore(task_req: TaskRequest) -> TaskResponse:
                async with semaphore:
                    return await execute_task_sync(task_req)

            tasks = [run_with_semaphore(t) for t in request.tasks]
            results = await asyncio.gather(*tasks)
        else:
            # Execute sequentially
            for task_req in request.tasks:
                result = await execute_task_sync(task_req)
                results.append(result)

        completed = sum(1 for r in results if r.status == TaskStatus.COMPLETED)
        failed = sum(1 for r in results if r.status == TaskStatus.FAILED)

        return BatchTaskResponse(
            batch_id=batch_id,
            total=len(results),
            completed=completed,
            failed=failed,
            results=results,
        )

    # =========================================================================
    # Experience Store
    # =========================================================================

    @app.get("/experiences", response_model=ExperienceListResponse, tags=["Experiences"])
    async def list_experiences(limit: int = 100, offset: int = 0):
        """List recent experiences"""
        ccp = get_ccp()
        all_experiences = list(ccp.experience_store)
        total = len(all_experiences)

        # Apply pagination
        experiences = all_experiences[offset:offset + limit]

        return ExperienceListResponse(
            total=total,
            experiences=[
                ExperienceResponse(
                    id=e.id,
                    state=e.state.to_dict(),
                    action=e.action.to_dict(),
                    outcome=e.outcome.to_dict(),
                    reward=e.reward,
                    timestamp=e.state.timestamp,
                )
                for e in experiences
            ],
            statistics=ccp.experience_store.get_statistics(),
        )

    @app.get("/experiences/{experience_id}", response_model=ExperienceResponse, tags=["Experiences"])
    async def get_experience(experience_id: str):
        """Get a specific experience"""
        ccp = get_ccp()
        exp = ccp.experience_store.get(experience_id)
        if not exp:
            raise HTTPException(status_code=404, detail="Experience not found")

        return ExperienceResponse(
            id=exp.id,
            state=exp.state.to_dict(),
            action=exp.action.to_dict(),
            outcome=exp.outcome.to_dict(),
            reward=exp.reward,
            timestamp=exp.state.timestamp,
        )

    @app.post("/experiences/export", tags=["Experiences"])
    async def export_experiences(file_path: str = "experiences.json"):
        """Export experiences to file"""
        ccp = get_ccp()
        ccp.experience_store.save_to_file(file_path)
        return {"status": "exported", "path": file_path, "count": len(ccp.experience_store)}

    @app.post("/experiences/import", tags=["Experiences"])
    async def import_experiences(file_path: str):
        """Import experiences from file"""
        ccp = get_ccp()
        try:
            count = ccp.experience_store.load_from_file(file_path)
            return {"status": "imported", "path": file_path, "count": count}
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    # =========================================================================
    # Replay / Simulation
    # =========================================================================

    @app.post("/replay", response_model=ReplayResultResponse, tags=["Simulation"])
    async def run_replay(request: ReplayRequest):
        """Run replay simulation with a policy"""
        ccp = get_ccp()

        # Load experiences from file if provided
        store = ExperienceStore()
        try:
            store.load_from_file(request.experience_file)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"File not found: {request.experience_file}")

        if len(store) == 0:
            raise HTTPException(status_code=400, detail="No experiences to replay")

        engine = ReplayEngine(store)

        # Create policy based on request
        from .policies import create_policy
        policy = create_policy(request.policy, engine)

        # Run replay
        result = await engine.replay(
            policy=policy,
            episodes=request.episodes,
            config=ReplayConfig(max_steps=50),
        )

        return ReplayResultResponse(
            policy_id=result.policy_id,
            total_episodes=result.total_episodes,
            success_rate=result.success_rate,
            avg_reward=result.avg_reward,
            avg_duration_ms=result.avg_duration_ms,
            metrics=result.metrics,
        )

    # =========================================================================
    # WebSocket
    # =========================================================================

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        """WebSocket endpoint for real-time event streaming"""
        await ws_manager.connect(websocket)
        try:
            while True:
                # Keep connection alive, handle client messages if needed
                data = await websocket.receive_text()
                # Echo or handle commands
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    # =========================================================================
    # LangGraph Workflow (v2)
    # =========================================================================

    @app.post("/workflow", response_model=WorkflowResponse, tags=["Workflow"])
    async def run_workflow(request: WorkflowRequest, background_tasks: BackgroundTasks):
        """Execute a LangGraph workflow"""
        ccp = get_ccp()
        task_id = f"wf-{uuid.uuid4().hex[:8]}"
        created_at = datetime.now()

        # Configure approval threshold if needed
        if not request.enable_approval:
            ccp.workflow.approval_manager.config.confidence_threshold = 1.1  # Disable

        # Create initial response
        response = WorkflowResponse(
            task_id=task_id,
            cycle_id=f"cycle_{task_id}",
            status=WorkflowPhase.SENSE,
            target=request.target,
            success=False,
            created_at=created_at,
        )

        ccp.active_workflows[task_id] = response

        # Execute workflow in background
        background_tasks.add_task(execute_workflow, task_id, request)

        await ccp.event_bus.publish(Event(
            event_type="workflow.created",
            source="api",
            data={"task_id": task_id, "target": request.target},
        ))

        return response

    @app.get("/workflow/{task_id}", response_model=WorkflowResponse, tags=["Workflow"])
    async def get_workflow(task_id: str):
        """Get workflow status and result"""
        ccp = get_ccp()
        if task_id not in ccp.active_workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return ccp.active_workflows[task_id]

    @app.get("/workflows", tags=["Workflow"])
    async def list_workflows(limit: int = 100):
        """List active workflows"""
        ccp = get_ccp()
        workflows = list(ccp.active_workflows.values())[-limit:]
        return {
            "total": len(ccp.active_workflows),
            "workflows": workflows,
        }

    # =========================================================================
    # Human-in-the-Loop (v2)
    # =========================================================================

    @app.get("/approvals", response_model=ApprovalListResponse, tags=["Approvals"])
    async def list_approvals():
        """List all approval requests"""
        ccp = get_ccp()
        pending = ccp.approval_manager.get_pending_requests()
        stats = ccp.approval_manager.get_stats()

        return ApprovalListResponse(
            total=stats["pending_count"] + stats["resolved_count"],
            pending=stats["pending_count"],
            resolved=stats["resolved_count"],
            requests=[
                ApprovalRequestResponse(
                    request_id=r.request_id,
                    task_id=r.task_id,
                    decision_action=r.decision.action,
                    decision_confidence=r.decision.confidence,
                    decision_reasoning=r.decision.reasoning,
                    state_summary=r.state_summary,
                    status=ApprovalStatusEnum(r.status.value),
                    priority=r.priority,
                    context=r.context,
                    created_at=r.created_at,
                    resolved_at=r.resolved_at,
                    resolved_by=r.resolved_by,
                    resolution_reason=r.resolution_reason,
                )
                for r in pending
            ],
        )

    @app.get("/approvals/{request_id}", response_model=ApprovalRequestResponse, tags=["Approvals"])
    async def get_approval(request_id: str):
        """Get a specific approval request"""
        ccp = get_ccp()
        request = ccp.approval_manager.get_request(request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Approval request not found")

        return ApprovalRequestResponse(
            request_id=request.request_id,
            task_id=request.task_id,
            decision_action=request.decision.action,
            decision_confidence=request.decision.confidence,
            decision_reasoning=request.decision.reasoning,
            state_summary=request.state_summary,
            status=ApprovalStatusEnum(request.status.value),
            priority=request.priority,
            context=request.context,
            created_at=request.created_at,
            resolved_at=request.resolved_at,
            resolved_by=request.resolved_by,
            resolution_reason=request.resolution_reason,
        )

    @app.post("/approvals/{request_id}/approve", tags=["Approvals"])
    async def approve_request(request_id: str, decision: ApprovalDecisionRequest):
        """Approve a pending request"""
        ccp = get_ccp()
        success = ccp.approval_manager.approve(
            request_id,
            approved_by=decision.approved_by,
            reason=decision.reason,
        )
        if not success:
            raise HTTPException(status_code=404, detail="Request not found or already resolved")

        await ccp.event_bus.publish(Event(
            event_type="approval.approved",
            source="api",
            data={"request_id": request_id, "approved_by": decision.approved_by},
        ))

        return {"status": "approved", "request_id": request_id}

    @app.post("/approvals/{request_id}/reject", tags=["Approvals"])
    async def reject_request(request_id: str, decision: ApprovalDecisionRequest):
        """Reject a pending request"""
        ccp = get_ccp()
        success = ccp.approval_manager.reject(
            request_id,
            rejected_by=decision.approved_by,
            reason=decision.reason,
        )
        if not success:
            raise HTTPException(status_code=404, detail="Request not found or already resolved")

        await ccp.event_bus.publish(Event(
            event_type="approval.rejected",
            source="api",
            data={"request_id": request_id, "rejected_by": decision.approved_by},
        ))

        return {"status": "rejected", "request_id": request_id}

    @app.get("/approvals/stats", response_model=ApprovalStatsResponse, tags=["Approvals"])
    async def get_approval_stats():
        """Get approval statistics"""
        ccp = get_ccp()
        stats = ccp.approval_manager.get_stats()
        return ApprovalStatsResponse(**stats)

    # =========================================================================
    # Thought Log (v2)
    # =========================================================================

    @app.get("/thoughts", response_model=ThoughtChainListResponse, tags=["Thoughts"])
    async def list_thought_chains(limit: int = 100, task_id: str | None = None):
        """List thought chains"""
        ccp = get_ccp()
        chains = ccp.thought_logger.get_completed_chains(limit=limit, task_id=task_id)

        return ThoughtChainListResponse(
            total=len(chains),
            chains=[
                _thought_chain_to_response(c)
                for c in chains
            ],
        )

    @app.get("/thoughts/{cycle_id}", response_model=ThoughtChainResponse, tags=["Thoughts"])
    async def get_thought_chain(cycle_id: str):
        """Get a specific thought chain"""
        ccp = get_ccp()
        chain = ccp.thought_logger.get_chain(cycle_id)
        if not chain:
            raise HTTPException(status_code=404, detail="Thought chain not found")

        return _thought_chain_to_response(chain)

    @app.get("/thoughts/stats", response_model=ThoughtLogStatsResponse, tags=["Thoughts"])
    async def get_thought_stats():
        """Get thought log statistics"""
        ccp = get_ccp()
        stats = ccp.thought_logger.get_stats()
        return ThoughtLogStatsResponse(
            active_count=stats.get("active_count", 0),
            completed_count=stats.get("completed_count", 0),
            avg_duration_ms=stats.get("avg_duration_ms", 0),
            avg_steps=stats.get("avg_steps", 0),
            max_duration_ms=stats.get("max_duration_ms", 0),
            min_duration_ms=stats.get("min_duration_ms", 0),
        )

    # =========================================================================
    # Channels
    # =========================================================================

    @app.get("/channels", tags=["Channels"])
    async def list_channels():
        """List registered notification channels"""
        ccp = get_ccp()
        return {"channels": ccp.channel_registry.list_channels()}

    @app.post(
        "/channels/{channel_id}/send",
        response_model=ChannelSendResponse,
        tags=["Channels"],
    )
    async def send_channel_message(channel_id: str, request: ChannelSendRequest):
        """Send a message via a specific channel"""
        ccp = get_ccp()
        try:
            result = await ccp.channel_registry.send_to(
                channel_id,
                request.to,
                request.text,
                thread_id=request.thread_id or "",
            )
            return ChannelSendResponse(
                channel_id=result.channel_id,
                success=result.success,
                message_id=result.message_id,
                error=result.error,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")

    @app.post("/channels/broadcast", tags=["Channels"])
    async def broadcast_message(request: BroadcastRequest):
        """Broadcast a message to multiple channels"""
        ccp = get_ccp()
        results = await ccp.channel_registry.broadcast(
            request.channel_ids, request.to, request.text,
        )
        return {
            "results": [
                {
                    "channel_id": r.channel_id,
                    "success": r.success,
                    "message_id": r.message_id,
                    "error": r.error,
                }
                for r in results
            ]
        }

    @app.get(
        "/channels/health",
        response_model=ChannelHealthResponse,
        tags=["Channels"],
    )
    async def channel_health():
        """Check health of all registered channels"""
        ccp = get_ccp()
        statuses = await ccp.channel_registry.health_check_all()
        return ChannelHealthResponse(
            channels={cid: status.value for cid, status in statuses.items()}
        )

    @app.post("/thoughts/export", tags=["Thoughts"])
    async def export_thoughts(output_path: str = "thoughts_export.json", limit: int = 1000):
        """Export thought chains to file"""
        ccp = get_ccp()
        count = ccp.thought_logger.export_chains(output_path, limit=limit)
        return {"status": "exported", "path": output_path, "count": count}


# =============================================================================
# Task Execution Helpers
# =============================================================================

async def execute_task(task_id: str, request: TaskRequest) -> None:
    """Execute a task in the background"""
    ccp = get_ccp()
    start_time = datetime.now()

    # Update status to running
    ccp.active_tasks[task_id].status = TaskStatus.RUNNING
    await ccp.event_bus.publish(Event(
        event_type="task.started",
        source="api",
        data={"task_id": task_id},
    ))

    try:
        # Simulate task execution (replace with actual WebAgent call)
        await asyncio.sleep(0.5)  # Simulated work

        result = {
            "url": request.target,
            "title": f"Result for {request.target}",
            "status_code": 200,
        }

        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000

        # Update task response
        task_response = ccp.active_tasks[task_id]
        task_response.status = TaskStatus.COMPLETED
        task_response.result = result
        task_response.completed_at = end_time
        task_response.duration_ms = duration_ms

        await ccp.record_task_result(task_response)

        # Record experience
        from ..learn import StateSnapshot, Action, Outcome, OutcomeStatus
        state = StateSnapshot(timestamp=start_time, features={"target": request.target})
        action = Action(action_type=request.task_type, params={"url": request.target})
        outcome = Outcome(status=OutcomeStatus.SUCCESS, result=result, duration_ms=duration_ms)
        ccp.experience_store.record(state, action, outcome)

        await ccp.event_bus.publish(Event(
            event_type="task.completed",
            source="api",
            data={"task_id": task_id, "duration_ms": duration_ms},
        ))

    except Exception as e:
        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000

        task_response = ccp.active_tasks[task_id]
        task_response.status = TaskStatus.FAILED
        task_response.error = str(e)
        task_response.completed_at = end_time
        task_response.duration_ms = duration_ms

        await ccp.record_task_result(task_response)

        await ccp.event_bus.publish(Event(
            event_type="task.failed",
            source="api",
            data={"task_id": task_id, "error": str(e)},
        ))


async def execute_task_sync(request: TaskRequest) -> TaskResponse:
    """Execute a task synchronously and return result"""
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    ccp = get_ccp()

    response = TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        target=request.target,
        created_at=datetime.now(),
    )
    ccp.active_tasks[task_id] = response

    await execute_task(task_id, request)
    return ccp.active_tasks[task_id]


# =============================================================================
# Workflow Execution Helpers (v2)
# =============================================================================

async def execute_workflow(task_id: str, request: WorkflowRequest) -> None:
    """Execute a LangGraph workflow in the background"""
    ccp = get_ccp()
    start_time = datetime.now()

    # Update status to running
    ccp.active_workflows[task_id].status = WorkflowPhase.SENSE

    await ccp.event_bus.publish(Event(
        event_type="workflow.started",
        source="api",
        data={"task_id": task_id},
    ))

    try:
        # Run the LangGraph workflow
        result = await ccp.workflow.run(
            task_id=task_id,
            task_type=request.task_type,
            target=request.target,
            params=request.metadata,
            max_retries=request.max_retries,
        )

        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000

        # Update workflow response
        response = ccp.active_workflows[task_id]
        response.cycle_id = result.get("cycle_id", "")
        response.status = WorkflowPhase(result.get("current_phase", CCPPhase.COMPLETED).value)
        response.success = result.get("final_success", False)
        response.decision_action = result.get("decision_action")
        response.decision_confidence = result.get("decision_confidence", 0.0)
        response.decision_reasoning = result.get("decision_reasoning")
        response.error = result.get("final_error")
        response.retry_count = result.get("retry_count", 0)
        response.duration_ms = duration_ms
        response.completed_at = end_time

        # Convert thought chain
        thought_chain = result.get("thought_chain", [])
        response.thought_chain = [
            ThoughtStepResponse(
                step_id=s.step_id if hasattr(s, 'step_id') else s.get("step_id", ""),
                phase=WorkflowPhase(s.phase.value if hasattr(s, 'phase') else s.get("phase", "think")),
                timestamp=s.timestamp if hasattr(s, 'timestamp') else datetime.fromisoformat(s.get("timestamp", datetime.now().isoformat())),
                reasoning=s.reasoning if hasattr(s, 'reasoning') else s.get("reasoning", ""),
                confidence=s.confidence if hasattr(s, 'confidence') else s.get("confidence", 0.0),
                duration_ms=s.duration_ms if hasattr(s, 'duration_ms') else s.get("duration_ms", 0.0),
                inputs=s.inputs if hasattr(s, 'inputs') else s.get("inputs", {}),
                outputs=s.outputs if hasattr(s, 'outputs') else s.get("outputs", {}),
            )
            for s in thought_chain
        ]

        # Record experience
        from ..learn import StateSnapshot, Action, Outcome, OutcomeStatus
        state = StateSnapshot(timestamp=start_time, features={"target": request.target})
        action = Action(action_type=request.task_type, params={"url": request.target})
        outcome = Outcome(
            status=OutcomeStatus.SUCCESS if response.success else OutcomeStatus.FAILURE,
            result={"decision": response.decision_action},
            duration_ms=duration_ms,
        )
        ccp.experience_store.record(state, action, outcome)

        # Update stats
        if response.success:
            ccp.success_count += 1
        else:
            ccp.fail_count += 1
        ccp.task_count += 1
        ccp.total_duration_ms += duration_ms

        await ccp.event_bus.publish(Event(
            event_type="workflow.completed",
            source="api",
            data={
                "task_id": task_id,
                "success": response.success,
                "duration_ms": duration_ms,
            },
        ))

    except Exception as e:
        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000

        response = ccp.active_workflows[task_id]
        response.status = WorkflowPhase.ABORTED
        response.success = False
        response.error = str(e)
        response.duration_ms = duration_ms
        response.completed_at = end_time

        ccp.fail_count += 1
        ccp.task_count += 1
        ccp.total_duration_ms += duration_ms

        await ccp.event_bus.publish(Event(
            event_type="workflow.failed",
            source="api",
            data={"task_id": task_id, "error": str(e)},
        ))


def _thought_chain_to_response(chain) -> ThoughtChainResponse:
    """Convert ThoughtChain to API response"""
    from ..think import ThoughtChain

    return ThoughtChainResponse(
        cycle_id=chain.cycle_id,
        task_id=chain.task_id,
        started_at=chain.started_at,
        completed_at=chain.completed_at,
        steps=[
            ThoughtStepResponse(
                step_id=s.step_id,
                phase=WorkflowPhase(s.phase.value),
                timestamp=s.timestamp,
                reasoning=s.reasoning,
                confidence=s.confidence,
                duration_ms=s.duration_ms,
                inputs=s.inputs,
                outputs=s.outputs,
            )
            for s in chain.steps
        ],
        transitions=[
            TransitionResponse(
                from_phase=WorkflowPhase(t.from_phase.value),
                to_phase=WorkflowPhase(t.to_phase.value),
                reason=t.reason.value if hasattr(t.reason, 'value') else str(t.reason),
                timestamp=t.timestamp,
                metadata=t.metadata,
            )
            for t in chain.transitions
        ],
        final_decision=chain.final_decision,
        final_outcome=chain.final_outcome,
        duration_ms=chain.get_total_duration_ms(),
        metadata=chain.metadata,
    )


# =============================================================================
# App Instance
# =============================================================================

app = create_app()
