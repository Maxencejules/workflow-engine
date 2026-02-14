"""JSON schema for workflow definitions and validation utilities."""

from __future__ import annotations

from typing import Any

import jsonschema

from workflow_engine.exceptions import (
    WorkflowDefinitionError,
    WorkflowValidationError,
)
from workflow_engine.models import (
    Condition,
    Node,
    NodeType,
    Transition,
    WorkflowDefinition,
)

CONDITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "field": {"type": "string", "minLength": 1},
        "operator": {
            "type": "string",
            "enum": sorted(Condition.OPERATORS),
        },
        "value": {},
    },
    "required": ["field", "operator", "value"],
    "additionalProperties": False,
}

TRANSITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "from_node": {"type": "string", "minLength": 1},
        "to_node": {"type": "string", "minLength": 1},
        "condition": CONDITION_SCHEMA,
    },
    "required": ["from_node", "to_node"],
    "additionalProperties": False,
}

NODE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "type": {"type": "string", "enum": [t.value for t in NodeType]},
        "label": {"type": "string"},
        "config": {"type": "object"},
    },
    "required": ["id", "type"],
    "additionalProperties": False,
}

WORKFLOW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
        "description": {"type": "string"},
        "nodes": {
            "type": "array",
            "items": NODE_SCHEMA,
            "minItems": 2,
        },
        "transitions": {
            "type": "array",
            "items": TRANSITION_SCHEMA,
            "minItems": 1,
        },
    },
    "required": ["name", "version", "nodes", "transitions"],
    "additionalProperties": False,
}


def validate_schema(data: dict[str, Any]) -> None:
    """Validate raw JSON data against the workflow JSON schema.

    Raises:
        WorkflowValidationError: If the data does not conform to the schema.
    """
    validator = jsonschema.Draft7Validator(WORKFLOW_SCHEMA)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        messages = [f"  - {e.json_path}: {e.message}" for e in errors]
        raise WorkflowValidationError(
            f"Workflow schema validation failed with {len(errors)} error(s):\n"
            + "\n".join(messages),
            errors=messages,
        )


def _validate_structure(definition: WorkflowDefinition) -> None:
    """Validate structural constraints beyond the JSON schema.

    Checks:
    - Exactly one start node.
    - At least one end node.
    - All transition references point to existing nodes.
    - Start node has no incoming transitions.
    - End nodes have no outgoing transitions.
    """
    errors: list[str] = []

    start_nodes = [n for n in definition.nodes.values() if n.type == NodeType.START]
    if len(start_nodes) == 0:
        errors.append("Workflow must have exactly one start node; found 0.")
    elif len(start_nodes) > 1:
        ids = ", ".join(n.id for n in start_nodes)
        msg = f"Workflow must have exactly one start node; found {len(start_nodes)}: {ids}"
        errors.append(msg)

    end_nodes = definition.end_nodes
    if not end_nodes:
        errors.append("Workflow must have at least one end node.")

    node_ids = set(definition.nodes.keys())
    for t in definition.transitions:
        if t.from_node not in node_ids:
            errors.append(f"Transition references unknown from_node '{t.from_node}'.")
        if t.to_node not in node_ids:
            errors.append(f"Transition references unknown to_node '{t.to_node}'.")

    start_id = start_nodes[0].id if start_nodes else None
    end_ids = {n.id for n in end_nodes}

    for t in definition.transitions:
        if t.to_node == start_id:
            errors.append(f"Start node '{start_id}' must not have incoming transitions.")
        if t.from_node in end_ids:
            errors.append(f"End node '{t.from_node}' must not have outgoing transitions.")

    if errors:
        raise WorkflowDefinitionError(
            "Workflow structural validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        )


def parse_workflow(data: dict[str, Any]) -> WorkflowDefinition:
    """Parse and validate a raw JSON dict into a WorkflowDefinition.

    This is the primary entry point for loading workflows.

    Raises:
        WorkflowValidationError: If JSON schema validation fails.
        WorkflowDefinitionError: If structural validation fails.
    """
    validate_schema(data)

    nodes: dict[str, Node] = {}
    for node_data in data["nodes"]:
        node = Node(
            id=node_data["id"],
            type=NodeType(node_data["type"]),
            label=node_data.get("label", ""),
            config=node_data.get("config", {}),
        )
        if node.id in nodes:
            raise WorkflowDefinitionError(f"Duplicate node id: '{node.id}'")
        nodes[node.id] = node

    transitions: list[Transition] = []
    for t_data in data["transitions"]:
        condition = None
        if "condition" in t_data:
            c = t_data["condition"]
            condition = Condition(field=c["field"], operator=c["operator"], value=c["value"])
        transitions.append(
            Transition(
                from_node=t_data["from_node"],
                to_node=t_data["to_node"],
                condition=condition,
            )
        )

    definition = WorkflowDefinition(
        name=data["name"],
        version=data["version"],
        nodes=nodes,
        transitions=transitions,
        description=data.get("description", ""),
    )

    _validate_structure(definition)
    return definition
