# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-02-14

### Added

- Workflow definition model with JSON schema validation.
- Five node types: `start`, `task`, `approval`, `decision`, `end`.
- Conditional transitions with 9 operators (`eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `contains`).
- Workflow versioning via semantic version strings.
- Structural validation (single start, end nodes, valid references).
- `WorkflowEngine` with `start()`, `submit_event()`, and `replay()`.
- Idempotency key support for event deduplication.
- Deterministic replay from event log.
- Event log with type, timestamp, payload, and idempotency key.
- Clear exception hierarchy for all error conditions.
- Example workflow JSON and runner script.
- GitHub Actions CI with lint, typecheck, and multi-version tests.
- 42 unit tests with 97% code coverage.
