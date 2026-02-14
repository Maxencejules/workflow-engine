"""Shared fixtures for workflow engine tests."""

from __future__ import annotations

import pytest

from workflow_engine import WorkflowDefinition, parse_workflow

SIMPLE_WORKFLOW_JSON: dict = {
    "name": "simple",
    "version": "1.0.0",
    "description": "A minimal two-step workflow",
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "do_task", "type": "task", "label": "Do the thing"},
        {"id": "end", "type": "end"},
    ],
    "transitions": [
        {"from_node": "start", "to_node": "do_task"},
        {"from_node": "do_task", "to_node": "end"},
    ],
}


APPROVAL_WORKFLOW_JSON: dict = {
    "name": "approval_flow",
    "version": "1.0.0",
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "submit", "type": "task", "label": "Submit Request"},
        {"id": "approve", "type": "approval", "label": "Manager Approval"},
        {"id": "end", "type": "end"},
    ],
    "transitions": [
        {"from_node": "start", "to_node": "submit"},
        {"from_node": "submit", "to_node": "approve"},
        {"from_node": "approve", "to_node": "end"},
    ],
}


DECISION_WORKFLOW_JSON: dict = {
    "name": "decision_flow",
    "version": "2.0.0",
    "description": "Workflow with a decision branch",
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "collect", "type": "task", "label": "Collect Data"},
        {"id": "decide", "type": "decision", "label": "High or Low?"},
        {"id": "high_path", "type": "task", "label": "High-Value Processing"},
        {"id": "low_path", "type": "task", "label": "Low-Value Processing"},
        {"id": "end", "type": "end"},
    ],
    "transitions": [
        {"from_node": "start", "to_node": "collect"},
        {"from_node": "collect", "to_node": "decide"},
        {
            "from_node": "decide",
            "to_node": "high_path",
            "condition": {"field": "amount", "operator": "gt", "value": 1000},
        },
        {
            "from_node": "decide",
            "to_node": "low_path",
            "condition": {"field": "amount", "operator": "lte", "value": 1000},
        },
        {"from_node": "high_path", "to_node": "end"},
        {"from_node": "low_path", "to_node": "end"},
    ],
}


@pytest.fixture
def simple_workflow() -> WorkflowDefinition:
    return parse_workflow(SIMPLE_WORKFLOW_JSON)


@pytest.fixture
def approval_workflow() -> WorkflowDefinition:
    return parse_workflow(APPROVAL_WORKFLOW_JSON)


@pytest.fixture
def decision_workflow() -> WorkflowDefinition:
    return parse_workflow(DECISION_WORKFLOW_JSON)
