"""Workflow execution engine with deterministic replay."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from workflow_engine.exceptions import (
    ConditionEvaluationError,
    DuplicateEventError,
    InvalidEventError,
    TransitionError,
    WorkflowCompletedError,
)
from workflow_engine.models import (
    NODE_EVENT_MAP,
    Event,
    EventType,
    Node,
    NodeType,
    RunStatus,
    WorkflowDefinition,
    WorkflowRun,
)


class WorkflowEngine:
    """Executes workflows defined by a WorkflowDefinition.

    Usage::

        engine = WorkflowEngine()
        run = engine.start(definition, context={"amount": 500})
        run = engine.submit_event(run, EventType.TASK_COMPLETED, payload={...})
        run = engine.replay(definition, run.events)
    """

    def start(
        self,
        definition: WorkflowDefinition,
        context: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> WorkflowRun:
        """Start a new workflow run.

        Creates a WorkflowRun positioned at the start node, records a
        ``WORKFLOW_STARTED`` event, then auto-advances through the start
        node's outgoing transition.

        Args:
            definition: The workflow definition to execute.
            context: Initial context data for the run.
            run_id: Optional explicit run ID (generated if not provided).

        Returns:
            A WorkflowRun positioned at the first actionable node.
        """
        ctx = dict(context) if context else {}
        rid = run_id or uuid.uuid4().hex

        run = WorkflowRun(
            run_id=rid,
            definition=definition,
            context=ctx,
            current_node_id=definition.start_node.id,
        )

        start_event = Event(
            event_type=EventType.WORKFLOW_STARTED,
            timestamp=datetime.now(timezone.utc),
            payload={"context": ctx},
            node_id=definition.start_node.id,
        )
        run.record_event(start_event)

        # Auto-advance past the start node.
        self._advance(run)
        return run

    def submit_event(
        self,
        run: WorkflowRun,
        event_type: EventType,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> WorkflowRun:
        """Submit an event to advance the workflow.

        Args:
            run: The current workflow run.
            event_type: The type of event being submitted.
            payload: Optional data associated with the event.
            idempotency_key: Optional key for deduplication.

        Returns:
            The updated WorkflowRun (same object, mutated in place).

        Raises:
            WorkflowCompletedError: If the workflow has already finished.
            DuplicateEventError: If the idempotency key was already used.
            InvalidEventError: If the event type doesn't match the current node.
        """
        if run.status != RunStatus.RUNNING:
            raise WorkflowCompletedError(
                f"Cannot submit events to a {run.status.value} workflow run."
            )

        if idempotency_key and run.has_seen_key(idempotency_key):
            raise DuplicateEventError(
                f"Event with idempotency key '{idempotency_key}' has already been processed."
            )

        current_node = run.definition.nodes[run.current_node_id]
        expected = NODE_EVENT_MAP.get(current_node.type)
        if expected is None or event_type != expected:
            raise InvalidEventError(
                f"Node '{current_node.id}' (type={current_node.type.value}) "
                f"expects event '{expected.value if expected else 'N/A'}', "
                f"got '{event_type.value}'."
            )

        event = Event(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            payload=dict(payload) if payload else {},
            idempotency_key=idempotency_key or uuid.uuid4().hex,
            node_id=current_node.id,
        )
        run.record_event(event)

        # Merge payload into context so transition conditions can reference it.
        if event.payload:
            run.context.update(event.payload)

        self._advance(run)
        return run

    def replay(
        self,
        definition: WorkflowDefinition,
        events: list[Event],
        run_id: str | None = None,
    ) -> WorkflowRun:
        """Deterministically replay a workflow from its event log.

        Given the same definition and events, this always produces the
        same final state.

        Args:
            definition: The workflow definition.
            events: The ordered event log to replay.
            run_id: Optional run ID (defaults to the first event's idempotency key).

        Returns:
            A WorkflowRun in the replayed state.
        """
        if not events:
            raise ValueError("Cannot replay an empty event log.")

        first = events[0]
        if first.event_type != EventType.WORKFLOW_STARTED:
            raise ValueError("Event log must start with a WORKFLOW_STARTED event.")

        ctx = dict(first.payload.get("context", {}))
        rid = run_id or uuid.uuid4().hex

        run = WorkflowRun(
            run_id=rid,
            definition=definition,
            context=ctx,
            current_node_id=definition.start_node.id,
        )
        run.record_event(first)
        self._advance(run)

        for event in events[1:]:
            if run.status != RunStatus.RUNNING:
                break
            run.record_event(event)
            if event.payload:
                run.context.update(event.payload)
            self._advance(run)

        return run

    def _advance(self, run: WorkflowRun) -> None:
        """Advance the run through transitions until an actionable node is reached.

        An actionable node is one that requires an external event (task, approval,
        decision) or an end node.
        """
        max_steps = len(run.definition.nodes) + 1  # guard against infinite loops
        for _ in range(max_steps):
            current_node = run.definition.nodes[run.current_node_id]

            if current_node.type == NodeType.END:
                run.status = RunStatus.COMPLETED
                return

            if current_node.type in (NodeType.TASK, NodeType.APPROVAL, NodeType.DECISION):
                # These need an external event to proceed — only auto-advance
                # if the last recorded event already targets this node.
                last_event = run.events[-1] if run.events else None
                if last_event is None:
                    return
                # If the last event was the one that brought us here (WORKFLOW_STARTED
                # or a previous node's event), we stop and wait for user input.
                expected = NODE_EVENT_MAP.get(current_node.type)
                if last_event.event_type != expected or last_event.node_id != current_node.id:
                    return

            # Find the first matching transition.
            next_node_id = self._resolve_transition(run, current_node)
            run.current_node_id = next_node_id

        raise TransitionError("Maximum transition depth exceeded — possible cycle in workflow.")

    def _resolve_transition(self, run: WorkflowRun, node: Node) -> str:
        """Find the first transition from ``node`` whose condition is satisfied."""
        outgoing = [t for t in run.definition.transitions if t.from_node == node.id]
        if not outgoing:
            raise TransitionError(f"No outgoing transitions from node '{node.id}'.")

        for t in outgoing:
            try:
                if t.can_fire(run.context):
                    return t.to_node
            except Exception as exc:
                raise ConditionEvaluationError(
                    f"Error evaluating condition on transition "
                    f"'{t.from_node}' -> '{t.to_node}': {exc}"
                ) from exc

        raise TransitionError(
            f"No transition condition matched for node '{node.id}'. Context: {run.context}"
        )
