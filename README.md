# workflow-engine

A reusable workflow engine that executes workflows defined in JSON, with deterministic replay and an event log.

## Installation

```bash
git clone https://github.com/Maxencejules/workflow-engine.git
cd workflow-engine
python -m pip install .
```

Install from this checkout; a PyPI release is not assumed. Use a virtual environment
to keep dependencies separate. For development, from the same directory:

```bash
python -m pip install -e ".[dev]"
```

## Quick Start

### 1. Define a workflow in JSON

```json
{
  "name": "expense_approval",
  "version": "1.0.0",
  "description": "Expense report approval workflow",
  "nodes": [
    {"id": "start", "type": "start", "label": "Begin"},
    {"id": "submit_expense", "type": "task", "label": "Submit Expense Report"},
    {"id": "review", "type": "approval", "label": "Manager Review"},
    {"id": "check_amount", "type": "decision", "label": "Check Amount"},
    {"id": "auto_approved", "type": "end", "label": "Auto-Approved"},
    {"id": "needs_vp", "type": "task", "label": "VP Approval Required"},
    {"id": "done", "type": "end", "label": "Complete"}
  ],
  "transitions": [
    {"from_node": "start", "to_node": "submit_expense"},
    {"from_node": "submit_expense", "to_node": "review"},
    {"from_node": "review", "to_node": "check_amount"},
    {
      "from_node": "check_amount",
      "to_node": "auto_approved",
      "condition": {"field": "amount", "operator": "lte", "value": 1000}
    },
    {
      "from_node": "check_amount",
      "to_node": "needs_vp",
      "condition": {"field": "amount", "operator": "gt", "value": 1000}
    },
    {"from_node": "needs_vp", "to_node": "done"}
  ]
}
```

### 2. Run the workflow in Python

```python
import json
from workflow_engine import WorkflowEngine, EventType, parse_workflow

# Load and validate the definition
with open("expense_workflow.json") as f:
    definition = parse_workflow(json.load(f))

engine = WorkflowEngine()

# Start a run
run = engine.start(definition, context={"amount": 500})
print(f"Current node: {run.current_node_id}")  # submit_expense

# Complete the task
run = engine.submit_event(run, EventType.TASK_COMPLETED, payload={"report_id": "EXP-001"})
print(f"Current node: {run.current_node_id}")  # review

# Submit approval
run = engine.submit_event(run, EventType.APPROVAL_SUBMITTED, payload={"approved": True})
print(f"Current node: {run.current_node_id}")  # check_amount

# Make decision (auto-advances through decision node)
run = engine.submit_event(run, EventType.DECISION_MADE)
print(f"Status: {run.status}")  # completed (amount <= 1000 → auto_approved)
```

### 3. Replay from event log

```python
# Deterministic replay: same events → same final state
replayed = engine.replay(definition, run.events)
assert replayed.current_node_id == run.current_node_id
assert replayed.status == run.status
assert replayed.context == run.context
```

### 4. Save and reload in separate processes

The standard-library example stores the original workflow definition, run ID and
events in a plain JSON file, then rebuilds the run in a new Python process:

```bash
python scripts/replay_json.py save work/expense-run.json
python scripts/replay_json.py replay work/expense-run.json
```

Both commands print the same reconstructed state, including event timestamps and
idempotency keys. The sample takes the high-value branch, then changes the amount,
so replay must preserve the earlier routing decision.

This example's payloads and context use JSON objects with string keys, arrays,
strings, integers, finite floats, booleans and `null`, including nested values.
Convert Python-specific values such as `datetime`, `Decimal`, tuples and sets to
those types before saving; non-finite floats are rejected. Event timestamps are
stored as ISO 8601 strings and restored separately from payloads.

The file's `format_version` is `1`. Replay uses the exact definition snapshot
saved in that file, including its workflow version. Keep historical definitions
unchanged and assign a new workflow version when nodes, conditions or transition
order change. A matching version string alone does not prove definitions are
identical. This is a storage example for the current engine; log/definition
migrations between incompatible engine versions are not provided.

## API Reference

### `parse_workflow(data: dict) -> WorkflowDefinition`

Parse and validate a JSON dict into a `WorkflowDefinition`. Raises `WorkflowValidationError` for schema errors or `WorkflowDefinitionError` for structural problems.

### `validate_schema(data: dict) -> None`

Validate raw JSON data against the workflow JSON schema without parsing.

### `WorkflowEngine`

#### `engine.start(definition, context=None, run_id=None) -> WorkflowRun`

Start a new workflow run. The run is positioned at the first actionable node after the start node.

#### `engine.submit_event(run, event_type, payload=None, idempotency_key=None) -> WorkflowRun`

Submit an event to advance the workflow. The `event_type` must match the current node type:
- `task` nodes expect `EventType.TASK_COMPLETED`
- `approval` nodes expect `EventType.APPROVAL_SUBMITTED`
- `decision` nodes expect `EventType.DECISION_MADE`

Payloads are copied, including nested values, so later changes to caller-owned data
or the live context do not alter recorded events. If validation or a transition
fails, the run, event log, and idempotency keys are unchanged; the same key can be
used for a corrected submission.

#### `engine.replay(definition, events, run_id=None) -> WorkflowRun`

Deterministically replay a workflow from its event log. Given the same definition and events, always produces the same final state.

Replay validates event types, target nodes, and duplicate idempotency keys using
the same rules as live submissions. It rejects events after completion and creates
independent copies of the input log and context. A valid partial log can be replayed
and continued with `submit_event()`.

Event payload dictionaries remain accessible to callers; treat recorded logs and
workflow definitions as read-only when relying on deterministic replay. Logs
already altered by earlier versions cannot be reconstructed automatically.

### Node Types

| Type       | Description                          | Required Event            |
|------------|--------------------------------------|---------------------------|
| `start`    | Entry point (exactly one per workflow) | Auto-advances            |
| `task`     | Work to be done                      | `TASK_COMPLETED`          |
| `approval` | Requires approval/rejection          | `APPROVAL_SUBMITTED`      |
| `decision` | Routes based on context conditions   | `DECISION_MADE`           |
| `end`      | Terminal node                        | N/A (completes workflow)  |

### Transition Conditions

Conditions evaluate `context[field] <operator> value`. Supported operators:

| Operator   | Description          |
|------------|----------------------|
| `eq`       | Equal                |
| `neq`      | Not equal            |
| `gt`       | Greater than         |
| `gte`      | Greater or equal     |
| `lt`       | Less than            |
| `lte`      | Less or equal        |
| `in`       | Value in list        |
| `not_in`   | Value not in list    |
| `contains` | Collection contains  |

### Exceptions

| Exception                  | When                                          |
|----------------------------|-----------------------------------------------|
| `WorkflowValidationError`  | JSON schema validation failure                |
| `WorkflowDefinitionError`  | Structural issues (no start node, bad refs)   |
| `InvalidEventError`        | Wrong event type for current node             |
| `DuplicateEventError`      | Idempotency key already used                  |
| `WorkflowCompletedError`   | Event submitted to finished workflow          |
| `TransitionError`          | No matching transition found                  |
| `ConditionEvaluationError` | Condition evaluation error                    |

### Event Log

Every workflow run maintains an ordered list of `Event` objects:

```python
for event in run.events:
    print(f"{event.timestamp} | {event.event_type.value} | {event.node_id} | {event.payload}")
```

Each event has:
- `event_type`: The type of event
- `timestamp`: UTC datetime of when the event was recorded
- `payload`: Arbitrary dict of event data (merged into context)
- `idempotency_key`: Unique key for deduplication
- `node_id`: The node this event was recorded at

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy workflow_engine

# Linting
ruff check .
```

## License

MIT
