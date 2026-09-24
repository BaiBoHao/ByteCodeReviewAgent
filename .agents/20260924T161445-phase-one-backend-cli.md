# Phase-one backend and CLI

## Background

The take-home requires an AI code review agent that accepts GitHub PR, GitLab MR, or Git diff
input and produces review comments or a Markdown report. The first product phase is a headless
backend and CLI; platform bots and UI are deferred.

## Implemented

- Created a Python 3.11+ package and `review-agent` CLI.
- Added local diff/stdin, GitHub PR, and GitLab MR source adapters.
- Added exact-host allowlisting, HTTPS enforcement, URL credential/query rejection, diff size
  limits, and local secret redaction.
- Added safe deterministic tool registration with built-ins and Python entry-point discovery.
- Added OpenAI-compatible structured review calls, configurable CNY pricing, pre-call budget
  reservation, and actual usage accounting.
- Added SQLite runs, checkpoints, traces, findings, resume support, and local artifacts.
- Added location/evidence-based confidence grading and Markdown reporting.
- Added architecture, threat-model, AI-usage, setup, and CLI documentation.

## Important files

- `src/bytecode_review_agent/service.py`: orchestration and resume flow
- `src/bytecode_review_agent/storage.py`: SQLite checkpoints and traces
- `src/bytecode_review_agent/cli.py`: CLI interface
- `src/bytecode_review_agent/providers.py`: input adapters and URL controls
- `src/bytecode_review_agent/security.py`: pre-model secret redaction
- `tests/`: deterministic unit and integration-style service tests

## Verification

- `python -m unittest discover -s tests -v`: 13 tests passed.
- `python -m compileall -q src tests`: passed.
- Wheel build completed successfully with no project dependencies downloaded.
- Built wheel installed in a temporary virtual environment; `review-agent version` and
  `review-agent tools` passed.
- Long-line and credential-pattern scans returned no production-code findings.

## Risks and next steps

- No live LLM, GitHub, or GitLab call was run because credentials and an endpoint were not
  provided; adapters are covered only by local safety tests in this phase.
- Regex redaction is defense in depth and cannot prove that arbitrary diffs contain no secrets.
- Inline PR/MR publication remains a later reporter and will need per-comment idempotency.
- Ruff and mypy are declared as development extras but were not present in the local runtime.
