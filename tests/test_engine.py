"""Tests for workflow_engine.engine."""

from __future__ import annotations

import pytest

from tests.conftest import DECISION_WORKFLOW_JSON
from workflow_engine import (
    DuplicateEventError,
    EventType,
    InvalidEventError,
    RunStatus,
    TransitionError,
    WorkflowCompletedError,
    WorkflowDefinition,
    WorkflowEngine,
    parse_workflow,
)


@pytest.fixture
def engine() -> WorkflowEngine:
    return WorkflowEngine()


class TestStart:
    def test_start_positions_at_first_task(
        self, engine: WorkflowEngine, simple_workflow: WorkflowDefinition
    ) -> None:
        run = engine.start(simple_workflow)
        assert run.current_node_id == "do_task"
        assert run.status == RunStatus.RUNNING
        assert len(run.events) == 1  # WORKFLOW_STARTED

    def test_start_with_context(
        self, engine: WorkflowEngine, simple_workflow: WorkflowDefinition
    ) -> None:
        run = engine.start(simple_workflow, context={"user": "alice"})
        assert run.context["user"] == "alice"

    def test_start_with_explicit_run_id(
        self, engine: WorkflowEngine, simple_workflow: WorkflowDefinition
    ) -> None:
        run = engine.start(simple_workflow, run_id="my-run-123")
        assert run.run_id == "my-run-123"


class TestSubmitEvent:
    def test_complete_simple_workflow(
        self, engine: WorkflowEngine, simple_workflow: WorkflowDefinition
    ) -> None:
        run = engine.start(simple_workflow)
        run = engine.submit_event(run, EventType.TASK_COMPLETED)
        assert run.status == RunStatus.COMPLETED
        assert run.current_node_id == "end"

    def test_approval_workflow(
        self, engine: WorkflowEngine, approval_workflow: WorkflowDefinition
    ) -> None:
        run = engine.start(approval_workflow)
        assert run.current_node_id == "submit"

        run = engine.submit_event(run, EventType.TASK_COMPLETED)
        assert run.current_node_id == "approve"

        run = engine.submit_event(run, EventType.APPROVAL_SUBMITTED, payload={"approved": True})
        assert run.status == RunStatus.COMPLETED

    def test_decision_high_path(self, engine: WorkflowEngine) -> None:
        defn = parse_workflow(DECISION_WORKFLOW_JSON)
        run = engine.start(defn, context={"amount": 2000})
        run = engine.submit_event(run, EventType.TASK_COMPLETED)  # collect
        run = engine.submit_event(run, EventType.DECISION_MADE)  # decide → high_path
        assert run.current_node_id == "high_path"
        run = engine.submit_event(run, EventType.TASK_COMPLETED)  # high_path → end
        assert run.status == RunStatus.COMPLETED

    def test_decision_low_path(self, engine: WorkflowEngine) -> None:
        defn = parse_workflow(DECISION_WORKFLOW_JSON)
        run = engine.start(defn, context={"amount": 500})
        run = engine.submit_event(run, EventType.TASK_COMPLETED)  # collect
        run = engine.submit_event(run, EventType.DECISION_MADE)  # decide → low_path
        assert run.current_node_id == "low_path"

    def test_payload_merges_into_context(
        self, engine: WorkflowEngine, simple_workflow: WorkflowDefinition
    ) -> None:
        run = engine.start(simple_workflow)
        engine.submit_event(run, EventType.TASK_COMPLETED, payload={"result": 42})
        assert run.context["result"] == 42

    def test_event_on_completed_workflow_raises(
        self, engine: WorkflowEngine, simple_workflow: WorkflowDefinition
    ) -> None:
        run = engine.start(simple_workflow)
        engine.submit_event(run, EventType.TASK_COMPLETED)
        assert run.status == RunStatus.COMPLETED
        with pytest.raises(WorkflowCompletedError):
            engine.submit_event(run, EventType.TASK_COMPLETED)

    def test_wrong_event_type_raises(
        self, engine: WorkflowEngine, simple_workflow: WorkflowDefinition
    ) -> None:
        run = engine.start(simple_workflow)
        with pytest.raises(InvalidEventError, match="expects event"):
            engine.submit_event(run, EventType.APPROVAL_SUBMITTED)

    def test_duplicate_idempotency_key_raises(
        self, engine: WorkflowEngine, approval_workflow: WorkflowDefinition
    ) -> None:
        run = engine.start(approval_workflow)
        engine.submit_event(run, EventType.TASK_COMPLETED, idempotency_key="key-1")
        with pytest.raises(DuplicateEventError, match="key-1"):
            engine.submit_event(run, EventType.APPROVAL_SUBMITTED, idempotency_key="key-1")

    def test_no_matching_transition_raises(self, engine: WorkflowEngine) -> None:
        # Decision node where no condition matches
        data = {
            "name": "no_match",
            "version": "1.0.0",
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "task", "type": "task"},
                {"id": "decide", "type": "decision"},
                {"id": "end", "type": "end"},
            ],
            "transitions": [
                {"from_node": "start", "to_node": "task"},
                {"from_node": "task", "to_node": "decide"},
                {
                    "from_node": "decide",
                    "to_node": "end",
                    "condition": {"field": "x", "operator": "eq", "value": "never"},
                },
            ],
        }
        defn = parse_workflow(data)
        run = engine.start(defn, context={"x": "something_else"})
        engine.submit_event(run, EventType.TASK_COMPLETED)
        with pytest.raises(TransitionError, match="No transition condition matched"):
            engine.submit_event(run, EventType.DECISION_MADE)


class TestReplay:
    def test_replay_simple_workflow(
        self, engine: WorkflowEngine, simple_workflow: WorkflowDefinition
    ) -> None:
        run = engine.start(simple_workflow)
        engine.submit_event(run, EventType.TASK_COMPLETED, payload={"data": "hello"})

        replayed = engine.replay(simple_workflow, run.events)
        assert replayed.status == run.status
        assert replayed.current_node_id == run.current_node_id
        assert replayed.context == run.context

    def test_replay_decision_workflow(self, engine: WorkflowEngine) -> None:
        defn = parse_workflow(DECISION_WORKFLOW_JSON)
        run = engine.start(defn, context={"amount": 2000})
        engine.submit_event(run, EventType.TASK_COMPLETED)
        engine.submit_event(run, EventType.DECISION_MADE)
        engine.submit_event(run, EventType.TASK_COMPLETED)

        replayed = engine.replay(defn, run.events)
        assert replayed.status == RunStatus.COMPLETED
        assert replayed.current_node_id == run.current_node_id

    def test_replay_empty_log_raises(self, engine: WorkflowEngine) -> None:
        with pytest.raises(ValueError, match="empty event log"):
            engine.replay(
                parse_workflow(
                    {
                        "name": "t",
                        "version": "1.0.0",
                        "nodes": [{"id": "s", "type": "start"}, {"id": "e", "type": "end"}],
                        "transitions": [{"from_node": "s", "to_node": "e"}],
                    }
                ),
                [],
            )

    def test_replay_preserves_idempotency_keys(
        self, engine: WorkflowEngine, approval_workflow: WorkflowDefinition
    ) -> None:
        run = engine.start(approval_workflow)
        engine.submit_event(run, EventType.TASK_COMPLETED, idempotency_key="unique-1")
        engine.submit_event(run, EventType.APPROVAL_SUBMITTED, idempotency_key="unique-2")

        replayed = engine.replay(approval_workflow, run.events)
        assert replayed.has_seen_key("unique-1")
        assert replayed.has_seen_key("unique-2")

    def test_replay_deterministic_across_runs(
        self, engine: WorkflowEngine, simple_workflow: WorkflowDefinition
    ) -> None:
        run = engine.start(simple_workflow, context={"v": 1})
        engine.submit_event(run, EventType.TASK_COMPLETED, payload={"v": 2})

        r1 = engine.replay(simple_workflow, run.events)
        r2 = engine.replay(simple_workflow, run.events)
        assert r1.status == r2.status
        assert r1.current_node_id == r2.current_node_id
        assert r1.context == r2.context
