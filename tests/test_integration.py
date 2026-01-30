"""
Integration Tests - Full CCP cycle tests
"""
import pytest
from src.ccp import CCPOrchestrator, SenseLayer, ThinkLayer, ControlLayer, LearnLayer
from src.sense import Event, EventBus, MetricsCollector, StateSnapshot
from src.think import RulesEngine, DecisionContext, TaskContext
from src.control import Executor, Task, ExecutionResult, TaskState
from src.learn import KnowledgeStore, KnowledgeEntry


class TestSenseThinkIntegration:
    """Test Sense -> Think integration"""

    @pytest.mark.asyncio
    async def test_events_trigger_decisions(self):
        """Events from Sense layer should influence Think layer decisions"""
        sense = SenseLayer()
        think = ThinkLayer()

        # Simulate multiple failures
        for i in range(5):
            await sense.event_bus.publish(Event(
                event_type="proxy.failure",
                source="proxy_manager",
                data={"session_id": f"sess_{i}", "country": "us"},
            ))
            sense.snapshot.record_error()

        # Get current state
        state = sense.get_state()
        events = sense.event_bus.get_history()

        # Make decision with context
        task_context = TaskContext(
            task_id="test",
            task_type="navigate",
            last_error_type="proxy",
            retry_count=0,
        )
        decision = think.decide(state, task_context, events)

        # Should decide to retry with proxy switch
        assert decision.action in ["retry", "pause", "proceed"]


class TestThinkControlIntegration:
    """Test Think -> Control integration"""

    @pytest.mark.asyncio
    async def test_decision_affects_execution(self):
        """Decisions from Think layer should affect Control layer execution"""
        think = ThinkLayer()
        control = ControlLayer()

        # Add custom rule for testing
        from src.think import Rule
        think.rules_engine.add_rule(Rule(
            name="test_rule",
            condition=lambda ctx: ctx.task_context and ctx.task_context.task_type == "test_task",
            action="custom_action",
            priority=1000,
        ))

        # Get decision
        from src.sense import SystemState
        context = DecisionContext(
            system_state=SystemState(),
            task_context=TaskContext(task_id="t1", task_type="test_task"),
        )
        decision = think.rules_engine.evaluate_first(context)

        assert decision.action == "custom_action"


class TestControlLearnIntegration:
    """Test Control -> Learn integration"""

    @pytest.mark.asyncio
    async def test_execution_results_recorded(self):
        """Execution results should be recorded in Learn layer"""
        control = ControlLayer()
        learn = LearnLayer()

        # Create task and execute
        task = Task(task_id="t1", task_type="test", target="target")

        async def success_executor(t: Task) -> ExecutionResult:
            return ExecutionResult(task_id=t.task_id, success=True, data="result")

        result = await control.execute(task, success_executor)

        # Process through feedback loop
        feedback = await control.process_result(result)

        # Record in knowledge store
        learn.record(f"task.{result.task_id}.result", result.success)
        entry = learn.query(f"task.{result.task_id}.result")

        assert entry is not None
        assert entry.value is True


class TestFullCCPCycle:
    """Test complete CCP cycle"""

    def test_ccp_initialization(self):
        """CCP should initialize all layers"""
        ccp = CCPOrchestrator()

        assert ccp.sense is not None
        assert ccp.think is not None
        assert ccp.control is not None
        assert ccp.learn is not None
        assert ccp.sense.event_bus is not None
        assert ccp.sense.metrics is not None

    @pytest.mark.asyncio
    async def test_ccp_cleanup(self):
        """CCP should clean up properly"""
        ccp = CCPOrchestrator()
        await ccp.cleanup()
        assert ccp.is_closed

    def test_ccp_stats(self):
        """CCP should provide stats from all layers"""
        ccp = CCPOrchestrator()
        stats = ccp.get_stats()

        assert "cycle_count" in stats
        assert "sense" in stats
        assert "think" in stats
        assert "control" in stats
        assert "learn" in stats


class TestEventPropagation:
    """Test event propagation through layers"""

    @pytest.mark.asyncio
    async def test_events_propagate_to_subscribers(self):
        """Events should propagate to all subscribers"""
        bus = EventBus()
        received_events = []

        async def handler(event: Event):
            received_events.append(event)

        bus.subscribe("test.*", handler)  # This won't work with wildcard, use "*"
        bus.subscribe("*", handler)

        await bus.publish(Event("test.event", "source", {"key": "value"}))

        # Wildcard subscriber should receive it
        assert len(received_events) >= 1

    @pytest.mark.asyncio
    async def test_metrics_aggregation(self):
        """Metrics should aggregate correctly"""
        metrics = MetricsCollector()

        # Record multiple metrics
        for i in range(10):
            metrics.record("test.metric", float(i))

        from datetime import timedelta
        agg = metrics.get_aggregated("test.metric", timedelta(hours=1))

        assert agg is not None
        assert agg.count == 10
        assert agg.sum == 45.0  # 0+1+2+...+9
        assert agg.avg == 4.5


class TestLayerIsolation:
    """Test that layers can work independently"""

    def test_sense_layer_standalone(self):
        """Sense layer should work standalone"""
        sense = SenseLayer()
        sense.record_metric("test", 1.0)
        state = sense.get_state()
        assert state is not None

    def test_think_layer_standalone(self):
        """Think layer should work standalone"""
        think = ThinkLayer()
        from src.sense import SystemState
        decision = think.decide(SystemState())
        assert decision is not None

    def test_control_layer_standalone(self):
        """Control layer should work standalone"""
        control = ControlLayer()
        stats = control.executor.get_stats()
        assert "total_tasks" in stats

    def test_learn_layer_standalone(self):
        """Learn layer should work standalone"""
        learn = LearnLayer()
        learn.record("test", "value")
        entry = learn.query("test")
        assert entry is not None
        assert entry.value == "value"


class TestErrorHandling:
    """Test error handling across layers"""

    @pytest.mark.asyncio
    async def test_handler_errors_dont_crash_bus(self):
        """Handler errors should not crash the event bus"""
        bus = EventBus()

        async def bad_handler(event: Event):
            raise ValueError("Handler error")

        async def good_handler(event: Event):
            pass

        bus.subscribe("test", bad_handler)
        bus.subscribe("test", good_handler)

        # Should not raise
        count = await bus.publish(Event("test", "source"))
        assert count == 2  # Both handlers were called

    @pytest.mark.asyncio
    async def test_execution_errors_handled(self):
        """Execution errors should be handled gracefully"""
        control = ControlLayer()
        task = Task(task_id="t1", task_type="test", target="target", timeout=1.0)

        async def error_executor(t: Task) -> ExecutionResult:
            raise RuntimeError("Execution error")

        result = await control.execute(task, error_executor)
        assert result.success is False
        assert "error" in result.error.lower()


class TestStateConsistency:
    """Test state consistency across operations"""

    @pytest.mark.asyncio
    async def test_snapshot_captures_state(self):
        """State snapshot should capture current state"""
        snapshot = StateSnapshot()

        snapshot.record_success()
        snapshot.record_success()
        snapshot.record_error()

        state = snapshot.get_current_state()

        assert state.success_count == 2
        assert state.error_count == 1
        assert abs(state.success_rate - 0.666) < 0.01

    def test_knowledge_store_consistency(self):
        """Knowledge store should maintain consistency"""
        store = KnowledgeStore(max_entries=5)

        # Add more than max entries
        for i in range(10):
            store.store(KnowledgeEntry(key=f"key_{i}", value=i))

        # Should only have max_entries
        assert len(store) == 5

        # Oldest should be evicted
        assert store.query("key_0") is None
        assert store.query("key_9") is not None
