# AI-assisted development record

This repository is intentionally designed to demonstrate more than a single LLM prompt. The
development process used AI for requirement decomposition, architecture exploration, security
review, implementation support, test generation, and debugging. Human judgment retained control
of scope, trust boundaries, acceptance criteria, and final verification.

## Decisions made during development

- Selected a deterministic orchestration pipeline instead of an unbounded autonomous loop.
- Chose Python for the first-stage backend because it minimises integration code while preserving
  clear provider, model, storage, tool, and reporter boundaries.
- Kept Markdown as the phase-one output because the assignment allows Markdown or direct platform
  comments; inline publication adds a separate idempotency problem and is deferred.
- Required configurable model prices instead of embedding values that can become stale.
- Treated repository content as untrusted data and prohibited repository code execution.
- Used evidence and line validation to constrain model-provided confidence.

## Repository evidence

- `docs/architecture.md` explains checkpoints, trace linkage, confidence policy, and extension
  points.
- `docs/threat-model.md` records implemented controls and residual risk rather than claiming that
  prompt instructions alone provide security.
- The test suite uses deterministic fake model responses to exercise budget exhaustion, transient
  failures, malformed responses, resume behavior, secret redaction, and confidence downgrading.
- Every accepted finding links back to stored prompt/response artifacts, tool observations, token
  usage, cost, and the original diff hash.

## Suggested take-home submission package

- Source repository and commit history
- README plus architecture and threat-model documents
- Passing test output
- One short terminal recording showing review, trace inspection, forced failure, and resume
- A sanitized example diff, generated report, and trace export produced with the configured model
- This AI usage record, including which AI suggestions were accepted or rejected

Raw assistant transcripts, API keys, private diffs, and provider credentials should not be part of
the submission package.
