# Tasks

## Milestone 1: Project Setup
- [x] Create directory structure
- [x] Write pyproject.toml

## Milestone 2: Core Models & Types
- [x] Define node types (start, task, approval, decision, end)
- [x] Define transition model with conditions
- [x] Define workflow definition model with versioning
- [x] Define event and event log models
- [x] Define workflow run state

## Milestone 3: Validation
- [x] JSON schema for workflow definitions
- [x] Structural validation (reachability, single start, etc.)

## Milestone 4: Execution Engine
- [x] Start workflow runs
- [x] Submit events to advance state
- [x] Evaluate conditional transitions
- [x] Idempotency key handling
- [x] Deterministic replay from event log

## Milestone 5: Tests
- [x] Model tests
- [x] Validation tests
- [x] Engine tests (happy path)
- [x] Engine tests (edge cases)
- [x] Replay tests
- [x] Error handling tests

## Milestone 6: Documentation & CI
- [x] README with API docs and examples
- [x] Example workflow JSON
- [x] Example Python script
- [x] GitHub Actions CI workflow
- [x] CHANGELOG
