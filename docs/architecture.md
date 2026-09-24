# Architecture

## Phase-one boundary

The phase-one deliverable is a headless Python review engine plus CLI. It deliberately excludes
authentication, multi-tenancy, a web UI, queues, and inline comment publication. Future GitHub
Apps, GitLab bots, HTTP APIs, and dashboards should call the same application service.

## Run state machine

```text
pending -> running -> completed
                   -> budget_exhausted -> running (after budget increase)
                   -> failed           -> running (resume)
```

Source loading, redaction, chunk creation, each chunk attempt, each completed chunk, resume, and
terminal state are checkpoints. A chunk is advanced only after its trace and findings are stored
in the same SQLite transaction. A failed model call leaves `next_chunk_index` unchanged.

## Trace model

Every finding has a `trace_id`. A trace links:

- Run and chunk identity
- Original raw diff path and SHA-256 via its run
- Redacted prompt path and SHA-256
- Deterministic tool observations
- Model, provider request ID, and raw response path
- Input/output tokens and calculated CNY cost
- Parsing errors for unsuccessful model responses

Raw artifacts are content evidence, while SQLite holds queryable state. Prompt files contain only
the redacted diff.

## Confidence policy

The model's confidence is not accepted on its own. A finding is high confidence only if:

1. The model labels it high confidence.
2. Its file matches the reviewed file.
3. Its line is an added line in the supplied diff.
4. It includes concrete evidence.

Only high-confidence findings are marked `accept`; all others are retained as `reference` so
uncertain output remains inspectable without being presented as fact.

## Extension points

- `SourceLoader`: local diff, GitHub, and GitLab input adapters
- `ReviewerClient`: model provider adapter
- `ToolRegistry`: safe deterministic tools and Python entry-point plugins
- `MarkdownReporter`: first output adapter; inline providers can be added later
- `SQLiteStorage`: checkpoint and trace persistence

No adapter decides the review workflow. `ReviewService` owns orchestration and calls the stable
interfaces.
