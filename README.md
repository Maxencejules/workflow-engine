# workflow-engine

A reusable workflow engine that executes workflows defined in JSON, with deterministic replay and an event log.

## Installation

```bash
pip install workflow-engine
```

For development:

```bash
pip install -e ".[dev]"
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

#### `engine.replay(definition, events, run_id=None) -> WorkflowRun`

Deterministically replay a workflow from its event log. Given the same definition and events, always produces the same final state.

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
