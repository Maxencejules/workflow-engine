"""Tests for workflow_engine.models."""

from __future__ import annotations

import pytest

from workflow_engine import (
    Condition,
    Event,
    EventType,
    Node,
    NodeType,
    Transition,
    WorkflowDefinition,
    WorkflowRun,
)


class TestCondition:
    def test_eq(self) -> None:
        c = Condition(field="status", operator="eq", value="active")
        assert c.evaluate({"status": "active"}) is True
        assert c.evaluate({"status": "inactive"}) is False

    def test_neq(self) -> None:
        c = Condition(field="role", operator="neq", value="admin")
        assert c.evaluate({"role": "user"}) is True
        assert c.evaluate({"role": "admin"}) is False

    def test_gt_and_lte(self) -> None:
        c_gt = Condition(field="amount", operator="gt", value=100)
        c_lte = Condition(field="amount", operator="lte", value=100)
        assert c_gt.evaluate({"amount": 200}) is True
        assert c_gt.evaluate({"amount": 50}) is False
        assert c_lte.evaluate({"amount": 100}) is True
        assert c_lte.evaluate({"amount": 101}) is False

    def test_gte_and_lt(self) -> None:
        c_gte = Condition(field="x", operator="gte", value=10)
        c_lt = Condition(field="x", operator="lt", value=10)
        assert c_gte.evaluate({"x": 10}) is True
        assert c_gte.evaluate({"x": 9}) is False
        assert c_lt.evaluate({"x": 9}) is True
        assert c_lt.evaluate({"x": 10}) is False

    def test_in_and_not_in(self) -> None:
        c_in = Condition(field="tier", operator="in", value=["gold", "platinum"])
        c_not_in = Condition(field="tier", operator="not_in", value=["gold", "platinum"])
        assert c_in.evaluate({"tier": "gold"}) is True
        assert c_in.evaluate({"tier": "silver"}) is False
        assert c_not_in.evaluate({"tier": "silver"}) is True

    def test_contains(self) -> None:
        c = Condition(field="tags", operator="contains", value="urgent")
        assert c.evaluate({"tags": ["urgent", "billing"]}) is True
        assert c.evaluate({"tags": ["billing"]}) is False

    def test_unknown_operator_raises(self) -> None:
        c = Condition(field="x", operator="invalid", value=1)
        with pytest.raises(ValueError, match="Unknown operator"):
            c.evaluate({"x": 1})

    def test_missing_field_returns_none_comparison(self) -> None:
        c = Condition(field="missing", operator="eq", value=None)
        assert c.evaluate({}) is True


class TestTransition:
    def test_unconditional_always_fires(self) -> None:
        t = Transition(from_node="a", to_node="b")
        assert t.can_fire({}) is True
        assert t.can_fire({"anything": "here"}) is True

    def test_conditional_fires_when_met(self) -> None:
        t = Transition(
            from_node="a",
            to_node="b",
            condition=Condition(field="approved", operator="eq", value=True),
        )
        assert t.can_fire({"approved": True}) is True
        assert t.can_fire({"approved": False}) is False


class TestWorkflowRun:
    def test_idempotency_key_tracking(self) -> None:
        defn = WorkflowDefinition(
            name="test",
            version="1.0.0",
            nodes={"s": Node(id="s", type=NodeType.START), "e": Node(id="e", type=NodeType.END)},
            transitions=[Transition(from_node="s", to_node="e")],
        )
        run = WorkflowRun(run_id="r1", definition=defn, context={}, current_node_id="s")
        event = Event(
            event_type=EventType.WORKFLOW_STARTED,
            timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            idempotency_key="key-1",
        )
        assert run.has_seen_key("key-1") is False
        run.record_event(event)
        assert run.has_seen_key("key-1") is True
        assert run.has_seen_key("key-2") is False
