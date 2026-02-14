"""Core data models for the workflow engine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime


class NodeType(str, Enum):
    """Types of nodes in a workflow."""

    START = "start"
    TASK = "task"
    APPROVAL = "approval"
    DECISION = "decision"
    END = "end"


class RunStatus(str, Enum):
    """Status of a workflow run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EventType(str, Enum):
    """Types of events that can be submitted."""

    WORKFLOW_STARTED = "workflow_started"
    TASK_COMPLETED = "task_completed"
    APPROVAL_SUBMITTED = "approval_submitted"
    DECISION_MADE = "decision_made"


# Maps node types to the event types that can advance them.
NODE_EVENT_MAP: dict[NodeType, EventType] = {
    NodeType.TASK: EventType.TASK_COMPLETED,
    NodeType.APPROVAL: EventType.APPROVAL_SUBMITTED,
    NodeType.DECISION: EventType.DECISION_MADE,
}


@dataclass(frozen=True)
class Condition:
    """A condition that must be met for a transition to fire.

    Evaluates ``context[field] operator value``.
    Supported operators: eq, neq, gt, gte, lt, lte, in, not_in, contains.
    """

    field: str
    operator: str
    value: Any

    OPERATORS: frozenset[str] = frozenset(
        {"eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "contains"}
    )

    def evaluate(self, context: dict[str, Any]) -> bool:
        """Evaluate this condition against a context dict."""
        actual = context.get(self.field)
        op = self.operator
        if op == "eq":
            return bool(actual == self.value)
        if op == "neq":
            return bool(actual != self.value)
        if op == "gt":
            return bool(actual > self.value)
        if op == "gte":
            return bool(actual >= self.value)
        if op == "lt":
            return bool(actual < self.value)
        if op == "lte":
            return bool(actual <= self.value)
        if op == "in":
            return bool(actual in self.value)
        if op == "not_in":
            return bool(actual not in self.value)
        if op == "contains":
            return bool(self.value in actual)  # type: ignore[operator]
        raise ValueError(f"Unknown operator: {op}")


@dataclass(frozen=True)
class Transition:
    """A transition between two nodes in a workflow."""

    from_node: str
    to_node: str
    condition: Condition | None = None

    def can_fire(self, context: dict[str, Any]) -> bool:
        """Return True if this transition's condition is met (or has no condition)."""
        if self.condition is None:
            return True
        return self.condition.evaluate(context)


@dataclass(frozen=True)
class Node:
    """A node in a workflow definition."""

    id: str
    type: NodeType
    label: str = ""
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowDefinition:
    """An immutable workflow definition."""

    name: str
    version: str
    nodes: dict[str, Node]
    transitions: list[Transition]
    description: str = ""

    @property
    def start_node(self) -> Node:
        """Return the single start node."""
        for node in self.nodes.values():
            if node.type == NodeType.START:
                return node
        raise ValueError("No start node found")  # pragma: no cover – validated earlier

    @property
    def end_nodes(self) -> list[Node]:
        """Return all end nodes."""
        return [n for n in self.nodes.values() if n.type == NodeType.END]


@dataclass(frozen=True)
class Event:
    """An immutable event in the workflow event log."""

    event_type: EventType
    timestamp: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = field(default_factory=lambda: uuid.uuid4().hex)
    node_id: str = ""


@dataclass
class WorkflowRun:
    """Mutable state of a running workflow instance."""

    run_id: str
    definition: WorkflowDefinition
    context: dict[str, Any]
    current_node_id: str
    status: RunStatus = RunStatus.RUNNING
    events: list[Event] = field(default_factory=list)
    _seen_keys: set[str] = field(default_factory=set, repr=False)

    def record_event(self, event: Event) -> None:
        """Append an event and track its idempotency key."""
        self.events.append(event)
        if event.idempotency_key:
            self._seen_keys.add(event.idempotency_key)

    def has_seen_key(self, key: str) -> bool:
        """Check whether an idempotency key has already been used."""
        return key in self._seen_keys
