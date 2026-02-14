#!/usr/bin/env python3
"""Example: run the expense approval workflow end-to-end."""

from __future__ import annotations

import json
from pathlib import Path

from workflow_engine import EventType, WorkflowEngine, parse_workflow

WORKFLOW_PATH = Path(__file__).parent / "example_workflow.json"


def main() -> None:
    # 1. Load and validate the workflow definition
    with open(WORKFLOW_PATH) as f:
        definition = parse_workflow(json.load(f))
    print(f"Loaded workflow: {definition.name} v{definition.version}")
    print(f"  Nodes: {', '.join(definition.nodes)}")
    print()

    engine = WorkflowEngine()

    # --- Scenario A: Low-value expense (auto-approved) ---
    print("=== Scenario A: $500 expense (auto-approved) ===")
    run = engine.start(definition, context={"amount": 500, "employee": "Alice"})
    print(f"  Started run {run.run_id[:8]}... at node '{run.current_node_id}'")

    run = engine.submit_event(run, EventType.TASK_COMPLETED, payload={"report_id": "EXP-001"})
    print(f"  Submitted expense → now at '{run.current_node_id}'")

    run = engine.submit_event(
        run, EventType.APPROVAL_SUBMITTED, payload={"manager_approved": True}
    )
    print(f"  Manager approved → now at '{run.current_node_id}'")

    run = engine.submit_event(run, EventType.DECISION_MADE)
    print(f"  Decision evaluated → status={run.status.value}, node='{run.current_node_id}'")
    print()

    # --- Scenario B: High-value expense (VP rejects) ---
    print("=== Scenario B: $5000 expense (VP rejects) ===")
    run2 = engine.start(definition, context={"amount": 5000, "employee": "Bob"})
    print(f"  Started run {run2.run_id[:8]}... at node '{run2.current_node_id}'")

    run2 = engine.submit_event(run2, EventType.TASK_COMPLETED)
    print(f"  Submitted expense → now at '{run2.current_node_id}'")

    run2 = engine.submit_event(run2, EventType.APPROVAL_SUBMITTED)
    print(f"  Manager approved → now at '{run2.current_node_id}'")

    run2 = engine.submit_event(run2, EventType.DECISION_MADE)
    print(f"  Decision: amount > $1000 → VP review at '{run2.current_node_id}'")

    run2 = engine.submit_event(run2, EventType.APPROVAL_SUBMITTED, payload={"vp_approved": False})
    print(f"  VP submitted decision → now at '{run2.current_node_id}'")

    run2 = engine.submit_event(run2, EventType.DECISION_MADE)
    print(f"  Final: status={run2.status.value}, node='{run2.current_node_id}'")
    print()

    # --- Replay demonstration ---
    print("=== Replay: reconstruct Scenario B from event log ===")
    print(f"  Original event log has {len(run2.events)} events")
    replayed = engine.replay(definition, run2.events)
    print(f"  Replayed status: {replayed.status.value}")
    print(f"  Replayed node:   {replayed.current_node_id}")
    print(f"  Replayed context: {replayed.context}")
    assert replayed.status == run2.status
    assert replayed.current_node_id == run2.current_node_id
    assert replayed.context == run2.context
    print("  Replay matches original state!")
    print()

    # --- Event log dump ---
    print("=== Event Log (Scenario A) ===")
    for i, event in enumerate(run.events):
        print(
            f"  [{i}] {event.event_type.value:25s} "
            f"node={event.node_id:20s} "
            f"key={event.idempotency_key[:8]}... "
            f"payload={event.payload}"
        )


if __name__ == "__main__":
    main()
