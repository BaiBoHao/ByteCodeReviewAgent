# ByteCodeReviewAgent

ByteCodeReviewAgent is the first-stage backend and CLI for a recoverable, traceable,
budget-aware AI code review product. It reviews a local Git diff, GitHub pull request, or
GitLab merge request and produces a Markdown report. It does not execute repository code.

## What is implemented

- Local diff, standard input, GitHub PR, and GitLab MR source adapters
- HTTPS-only source URLs with an explicit host allowlist
- Local secret redaction before model calls
- File-aware diff chunking and added-line validation
- OpenAI-compatible Chat Completions client with structured JSON results
- Configurable CNY budget with pre-call cost reservation and actual usage accounting
- SQLite run state, checkpoints, failure recovery, and per-finding traces
- High-confidence versus reference-only findings
- Declarative built-in and third-party tool registration
- Markdown reports and a programmatic Python service API

Publishing inline PR/MR comments and the product UI are intentionally deferred. Markdown is
the supported output required by this phase.

## Quick start

Python 3.11 or newer is required.

```bash
python -m venv .venv
python -m pip install -e .
```

Configure the model endpoint and its current prices in the shell. Prices are never hard-coded
because providers change them independently.

```powershell
$env:REVIEW_AGENT_LLM_BASE_URL = "https://your-compatible-endpoint/v1"
$env:REVIEW_AGENT_LLM_API_KEY = "..."
$env:REVIEW_AGENT_LLM_MODEL = "your-model"
$env:REVIEW_AGENT_INPUT_PRICE_CNY_PER_MILLION = "..."
$env:REVIEW_AGENT_OUTPUT_PRICE_CNY_PER_MILLION = "..."
```

Review a local diff:

```bash
git diff > changes.diff
review-agent review changes.diff --budget 10 --output review-report.md
```

Or pipe a diff without creating a file:

```bash
git diff | review-agent review - --budget 10
```

Review a pull/merge request:

```bash
review-agent review https://github.com/org/repo/pull/123
review-agent review https://gitlab.com/group/project/-/merge_requests/123
```

Use `GITHUB_TOKEN` or `GITLAB_TOKEN` for private repositories. A self-hosted provider must be
explicitly allowlisted, for example:

```powershell
$env:REVIEW_AGENT_ALLOWED_HOSTS = "github.com,gitlab.com,git.example.internal"
```

## Recovery and trace inspection

A failure message includes its run ID. Resume from the last completed chunk:

```bash
review-agent resume run_0123456789abcdef
review-agent resume run_0123456789abcdef --budget 20
```

Inspect recent runs or the evidence behind one finding:

```bash
review-agent runs
review-agent run run_0123456789abcdef
review-agent trace trace_0123456789abcdef
review-agent trace trace_0123456789abcdef --include-content
```

Raw diffs, redacted prompts, model responses, and SQLite state are stored under
`.review-agent/`, which is ignored by Git. Raw diff content is referenced by each trace but is
not printed by default.

## Architecture

The CLI is only an interface layer. Product integrations can invoke `ReviewService.start()` and
`ReviewService.resume()` directly without copying orchestration logic.

```text
CLI / future HTTP or webhook adapter
                |
          ReviewService
       /       |        \
source       tools      LLM
adapter     registry   adapter
       \       |        /
       SQLite + local artifacts
                |
        Markdown reporter
```

See [Architecture](docs/architecture.md) and [Threat model](docs/threat-model.md) for the
state machine, extension boundaries, and security decisions.

## Tool extensions

Built-in tools are pure, non-executing analyzers. Third-party packages may expose a tool through
the `bytecode_review_agent.tools` Python entry-point group. A tool implements a `name` attribute
and `run(DiffChunk) -> ToolObservation`; the orchestration flow remains unchanged.

```toml
[project.entry-points."bytecode_review_agent.tools"]
my_safe_tool = "my_package:MySafeTool"
```

List discovered tools with `review-agent tools`.

## Tests

The core test suite uses the standard library so it can run before development extras are
installed:

```bash
$env:PYTHONPATH = "src"  # PowerShell
python -m unittest discover -s tests -v
```

Tests cover diff parsing, large-hunk chunking, secret redaction, source URL controls, budget
enforcement, trace linkage, failure checkpoints, and resume behavior. Model calls are replaced
with a deterministic fake.

## Current boundaries

- The endpoint must support OpenAI-compatible Chat Completions and JSON response mode.
- Secret scanning is defense in depth, not a proof that arbitrary text contains no secret.
- Raw diffs remain sensitive local artifacts and should be protected by host filesystem access.
- Repository code is not checked out or executed. A future typecheck tool must run only in an
  explicitly enabled, network-disabled and resource-limited sandbox.
- Inline GitHub/GitLab publishing will be a separate reporter with idempotent comment tracking.
