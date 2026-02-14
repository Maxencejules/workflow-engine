"""Tests for workflow_engine.schema validation."""

from __future__ import annotations

import copy

import pytest

from tests.conftest import DECISION_WORKFLOW_JSON, SIMPLE_WORKFLOW_JSON
from workflow_engine import (
    WorkflowDefinitionError,
    WorkflowValidationError,
    parse_workflow,
    validate_schema,
)


class TestValidateSchema:
    def test_valid_schema_passes(self) -> None:
        validate_schema(SIMPLE_WORKFLOW_JSON)  # should not raise

    def test_missing_name_fails(self) -> None:
        data = {k: v for k, v in SIMPLE_WORKFLOW_JSON.items() if k != "name"}
        with pytest.raises(WorkflowValidationError, match="name"):
            validate_schema(data)

    def test_bad_version_format_fails(self) -> None:
        data = {**SIMPLE_WORKFLOW_JSON, "version": "v1"}
        with pytest.raises(WorkflowValidationError, match="version"):
            validate_schema(data)

    def test_empty_nodes_fails(self) -> None:
        data = {**SIMPLE_WORKFLOW_JSON, "nodes": []}
        with pytest.raises(WorkflowValidationError):
            validate_schema(data)

    def test_unknown_node_type_fails(self) -> None:
        data = copy.deepcopy(SIMPLE_WORKFLOW_JSON)
        data["nodes"][1]["type"] = "unknown_type"
        with pytest.raises(WorkflowValidationError):
            validate_schema(data)

    def test_invalid_condition_operator_fails(self) -> None:
        data = copy.deepcopy(DECISION_WORKFLOW_JSON)
        data["transitions"][2]["condition"]["operator"] = "bad_op"
        with pytest.raises(WorkflowValidationError):
            validate_schema(data)


class TestParseWorkflow:
    def test_parse_simple_workflow(self) -> None:
        defn = parse_workflow(SIMPLE_WORKFLOW_JSON)
        assert defn.name == "simple"
        assert defn.version == "1.0.0"
        assert len(defn.nodes) == 3
        assert len(defn.transitions) == 2
        assert defn.start_node.id == "start"
        assert len(defn.end_nodes) == 1

    def test_no_start_node_fails(self) -> None:
        data = {
            "name": "no_start",
            "version": "1.0.0",
            "nodes": [
                {"id": "task1", "type": "task"},
                {"id": "end", "type": "end"},
            ],
            "transitions": [{"from_node": "task1", "to_node": "end"}],
        }
        with pytest.raises(WorkflowDefinitionError, match="start node"):
            parse_workflow(data)

    def test_no_end_node_fails(self) -> None:
        data = {
            "name": "no_end",
            "version": "1.0.0",
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "task1", "type": "task"},
            ],
            "transitions": [{"from_node": "start", "to_node": "task1"}],
        }
        with pytest.raises(WorkflowDefinitionError, match="end node"):
            parse_workflow(data)

    def test_duplicate_node_id_fails(self) -> None:
        data = {
            "name": "dup",
            "version": "1.0.0",
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "start", "type": "end"},
            ],
            "transitions": [{"from_node": "start", "to_node": "start"}],
        }
        with pytest.raises(WorkflowDefinitionError, match="Duplicate node id"):
            parse_workflow(data)

    def test_transition_referencing_unknown_node_fails(self) -> None:
        data = copy.deepcopy(SIMPLE_WORKFLOW_JSON)
        data["transitions"].append({"from_node": "do_task", "to_node": "nonexistent"})
        with pytest.raises(WorkflowDefinitionError, match="unknown.*nonexistent"):
            parse_workflow(data)

    def test_incoming_transition_to_start_fails(self) -> None:
        data = copy.deepcopy(SIMPLE_WORKFLOW_JSON)
        data["transitions"].append({"from_node": "do_task", "to_node": "start"})
        with pytest.raises(WorkflowDefinitionError, match="Start node.*incoming"):
            parse_workflow(data)

    def test_outgoing_transition_from_end_fails(self) -> None:
        data = copy.deepcopy(SIMPLE_WORKFLOW_JSON)
        data["transitions"].append({"from_node": "end", "to_node": "do_task"})
        with pytest.raises(WorkflowDefinitionError, match="End node.*outgoing"):
            parse_workflow(data)

    def test_multiple_start_nodes_fails(self) -> None:
        data = {
            "name": "multi_start",
            "version": "1.0.0",
            "nodes": [
                {"id": "s1", "type": "start"},
                {"id": "s2", "type": "start"},
                {"id": "end", "type": "end"},
            ],
            "transitions": [
                {"from_node": "s1", "to_node": "end"},
                {"from_node": "s2", "to_node": "end"},
            ],
        }
        with pytest.raises(WorkflowDefinitionError, match="exactly one start"):
            parse_workflow(data)
