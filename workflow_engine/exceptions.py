"""Workflow engine exceptions."""


class WorkflowError(Exception):
    """Base exception for all workflow engine errors."""


class WorkflowDefinitionError(WorkflowError):
    """Raised when a workflow definition is invalid."""


class WorkflowValidationError(WorkflowDefinitionError):
    """Raised when a workflow definition fails JSON schema validation."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        self.errors = errors or []
        super().__init__(message)


class WorkflowRuntimeError(WorkflowError):
    """Raised when a workflow execution encounters an error."""


class InvalidEventError(WorkflowRuntimeError):
    """Raised when an event cannot be applied to the current workflow state."""


class DuplicateEventError(WorkflowRuntimeError):
    """Raised when an event with a duplicate idempotency key is submitted."""


class WorkflowCompletedError(WorkflowRuntimeError):
    """Raised when an event is submitted to a completed workflow."""


class TransitionError(WorkflowRuntimeError):
    """Raised when no valid transition can be found."""


class ConditionEvaluationError(WorkflowRuntimeError):
    """Raised when a transition condition fails to evaluate."""
