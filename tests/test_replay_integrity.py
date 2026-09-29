"""Regression tests for historical snapshots and rejected events."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from workflow_engine import (
    ConditionEvaluationError,
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


def test_replay_preserves_branch_before_later_context_update(
    decision_workflow: WorkflowDefinition,
) -> None:
    engine = WorkflowEngine()
    run = engine.start(decision_workflow, context={"amount": 2000})
    engine.submit_event(run, EventType.TASK_COMPLETED)
    engine.submit_event(run, EventType.DECISION_MADE)
    assert run.current_node_id == "high_path"
    engine.submit_event(run, EventType.TASK_COMPLETED, payload={"amount": 500})

    replayed = engine.replay(decision_workflow, run.events)

    assert replayed.status == run.status == RunStatus.COMPLETED
    assert replayed.current_node_id == run.current_node_id == "end"
    assert replayed.context == run.context == {"amount": 500}
    assert run.events[0].payload == {"context": {"amount": 2000}}


def test_initial_context_is_independent_of_input_and_history(
    simple_workflow: WorkflowDefinition,
) -> None:
    initial = {"items": ["original"]}
    run = WorkflowEngine().start(simple_workflow, context=initial)
    initial["items"].append("external")
    assert run.context == {"items": ["original"]}

    run.context["items"].append("live")
    assert run.events[0].payload == {"context": {"items": ["original"]}}


def test_submitted_payload_is_independent_of_input_and_live_context(
    approval_workflow: WorkflowDefinition,
) -> None:
    engine = WorkflowEngine()
    run = engine.start(approval_workflow)
    payload = {"items": ["original"]}
    engine.submit_event(run, EventType.TASK_COMPLETED, payload=payload)

    payload["items"].append("external")
    assert run.context == {"items": ["original"]}
    run.context["items"].append("live")
    assert run.events[1].payload == {"items": ["original"]}


def test_replay_does_not_share_context_or_events_with_source(
    approval_workflow: WorkflowDefinition,
) -> None:
    engine = WorkflowEngine()
    run = engine.start(approval_workflow, context={"initial": [1]})
    engine.submit_event(run, EventType.TASK_COMPLETED, payload={"result": [2]})
    original_events = deepcopy(run.events)

    replayed = engine.replay(approval_workflow, run.events)
    replayed.context["initial"].append(3)
    replayed.context["result"].append(4)
    assert replayed.events == original_events
    replayed.events[1].payload["result"].append(5)
    assert run.events == original_events
    assert run.context == {"initial": [1], "result": [2]}


@pytest.mark.parametrize(
    ("operator", "value", "rejected", "accepted", "error"),
    [
        ("eq", "yes", "no", "yes", TransitionError),
        ("gt", 10, "invalid", 11, ConditionEvaluationError),
    ],
)
def test_rejected_transition_leaves_run_unchanged_and_key_reusable(
    operator: str,
    value: object,
    rejected: object,
    accepted: object,
    error: type[Exception],
) -> None:
    definition = parse_workflow(
        {
            "name": "conditional_task",
            "version": "1.0.0",
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "task", "type": "task"},
                {"id": "end", "type": "end"},
            ],
            "transitions": [
                {"from_node": "start", "to_node": "task"},
                {
                    "from_node": "task",
                    "to_node": "end",
                    "condition": {"field": "value", "operator": operator, "value": value},
                },
            ],
        }
    )
    engine = WorkflowEngine()
    run = engine.start(definition, context={"original": [1]})
    original = deepcopy(run)
    context_reference = run.context
    events_reference = run.events

    with pytest.raises(error):
        engine.submit_event(
            run,
            EventType.TASK_COMPLETED,
            payload={"value": rejected},
            idempotency_key="retryable",
        )

    assert run == original
    assert run.context is context_reference
    assert run.events is events_reference
    assert not run.has_seen_key("retryable")
    result = engine.submit_event(
        run,
        EventType.TASK_COMPLETED,
        payload={"value": accepted},
        idempotency_key="retryable",
    )
    assert result is run
    assert run.status == RunStatus.COMPLETED
    assert run.context is context_reference
    assert run.events is events_reference


@pytest.mark.parametrize(
    "invalid", ["type", "unknown_type", "node", "duplicate", "duplicate_start"]
)
def test_replay_rejects_invalid_event_without_changing_source(
    approval_workflow: WorkflowDefinition, invalid: str
) -> None:
    engine = WorkflowEngine()
    run = engine.start(approval_workflow)
    engine.submit_event(run, EventType.TASK_COMPLETED, idempotency_key="task")
    engine.submit_event(run, EventType.APPROVAL_SUBMITTED, idempotency_key="approval")
    events = deepcopy(run.events)
    error: type[Exception] = InvalidEventError
    if invalid == "type":
        events[1] = replace(events[1], event_type=EventType.APPROVAL_SUBMITTED)
    elif invalid == "unknown_type":
        events[1] = replace(events[1], event_type="unknown")
    elif invalid == "node":
        events[1] = replace(events[1], node_id="approve")
    elif invalid == "duplicate":
        events[2] = replace(events[2], idempotency_key="task")
        error = DuplicateEventError
    else:
        events[1] = replace(events[1], idempotency_key=events[0].idempotency_key)
        error = DuplicateEventError
    original_events = deepcopy(events)

    with pytest.raises(error):
        engine.replay(approval_workflow, events)

    assert events == original_events


def test_replay_rejects_wrong_start_node(simple_workflow: WorkflowDefinition) -> None:
    engine = WorkflowEngine()
    run = engine.start(simple_workflow)
    events = [replace(run.events[0], node_id="unknown")]
    with pytest.raises(InvalidEventError):
        engine.replay(simple_workflow, events)


def test_replay_rejects_trailing_events_after_completion(
    simple_workflow: WorkflowDefinition,
) -> None:
    engine = WorkflowEngine()
    run = engine.start(simple_workflow)
    engine.submit_event(run, EventType.TASK_COMPLETED)
    events = [*run.events, replace(run.events[-1], idempotency_key="extra")]
    with pytest.raises(WorkflowCompletedError):
        engine.replay(simple_workflow, events)


def test_replay_rejects_non_start_first_event(simple_workflow: WorkflowDefinition) -> None:
    engine = WorkflowEngine()
    run = engine.start(simple_workflow)
    event = replace(run.events[0], event_type=EventType.TASK_COMPLETED)
    with pytest.raises(ValueError, match="WORKFLOW_STARTED"):
        engine.replay(simple_workflow, [event])


def test_replay_rejects_invalid_initial_context(simple_workflow: WorkflowDefinition) -> None:
    engine = WorkflowEngine()
    run = engine.start(simple_workflow)
    event = replace(run.events[0], payload={"context": [1]})
    with pytest.raises(ValueError, match="context"):
        engine.replay(simple_workflow, [event])


@pytest.mark.parametrize("index", [0, 1])
def test_replay_rejects_invalid_payload(simple_workflow: WorkflowDefinition, index: int) -> None:
    engine = WorkflowEngine()
    run = engine.start(simple_workflow)
    engine.submit_event(run, EventType.TASK_COMPLETED)
    events = run.events.copy()
    events[index] = replace(events[index], payload=None)
    with pytest.raises(ValueError, match="payload"):
        engine.replay(simple_workflow, events)


def test_rejected_cycle_restores_state(simple_workflow: WorkflowDefinition) -> None:
    definition = replace(
        simple_workflow,
        transitions=[
            replace(simple_workflow.transitions[0]),
            replace(simple_workflow.transitions[1], to_node="do_task"),
        ],
    )
    engine = WorkflowEngine()
    run = engine.start(definition)
    original = deepcopy(run)
    with pytest.raises(TransitionError, match="Maximum transition depth"):
        engine.submit_event(run, EventType.TASK_COMPLETED, idempotency_key="cycle")
    assert run == original
