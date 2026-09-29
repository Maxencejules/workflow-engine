"""Save and replay a workflow in separate processes using only plain JSON."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

from workflow_engine import Event, EventType, WorkflowEngine, parse_workflow

if TYPE_CHECKING:
    from workflow_engine import WorkflowRun

WORKFLOW_PATH = Path(__file__).parent / "example_workflow.json"


def reject_nonfinite(value: str) -> NoReturn:
    raise ValueError(f"Non-finite number is not supported in JSON logs: {value}")


def save_demo(path: Path) -> WorkflowRun:
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    definition = parse_workflow(workflow)
    engine = WorkflowEngine()
    run = engine.start(
        definition,
        context={"amount": 5000, "details": {"employee": "Zoë", "items": [1.5, True, None]}},
    )
    engine.submit_event(
        run, EventType.TASK_COMPLETED, payload={"report_id": "EXP-001"}, idempotency_key="submit"
    )
    engine.submit_event(run, EventType.APPROVAL_SUBMITTED, idempotency_key="manager")
    engine.submit_event(run, EventType.DECISION_MADE, idempotency_key="route")
    # The original amount selected VP review; a later update must not change that history.
    engine.submit_event(
        run,
        EventType.APPROVAL_SUBMITTED,
        payload={"vp_approved": True, "amount": 500},
        idempotency_key="vp",
    )
    engine.submit_event(run, EventType.DECISION_MADE, idempotency_key="finish")
    document = {
        "format_version": 1,
        "workflow": workflow,
        "run_id": run.run_id,
        "events": [
            {
                "event_type": event.event_type.value,
                "timestamp": event.timestamp.isoformat(),
                "payload": event.payload,
                "idempotency_key": event.idempotency_key,
                "node_id": event.node_id,
            }
            for event in run.events
        ],
    }
    encoded = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded + "\n", encoding="utf-8")
    return run


def replay_saved(path: Path) -> WorkflowRun:
    document = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_nonfinite)
    if document["format_version"] != 1:
        raise ValueError("Unsupported JSON log format_version; expected 1.")
    definition = parse_workflow(document["workflow"])
    events = [
        Event(
            event_type=EventType(event["event_type"]),
            timestamp=datetime.fromisoformat(event["timestamp"]),
            payload=event["payload"],
            idempotency_key=event["idempotency_key"],
            node_id=event["node_id"],
        )
        for event in document["events"]
    ]
    return WorkflowEngine().replay(definition, events, run_id=document["run_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("save", "replay"))
    parser.add_argument("path", type=Path, help="Path to the plain JSON event log")
    args = parser.parse_args()
    run = save_demo(args.path) if args.mode == "save" else replay_saved(args.path)
    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "status": run.status.value,
                "node": run.current_node_id,
                "context": run.context,
                "idempotency_keys": [event.idempotency_key for event in run.events],
                "timestamps": [event.timestamp.isoformat() for event in run.events],
            },
            ensure_ascii=True,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
