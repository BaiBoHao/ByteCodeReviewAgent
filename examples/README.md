# Deterministic review demo

This demo runs the real ByteCodeReviewAgent CLI pipeline against the synthetic
`ReviewProjectTest` diff. It uses a local deterministic OpenAI-compatible HTTP endpoint so no
source code or credentials leave the machine. It demonstrates product behavior, not external
model quality.

From the ByteCodeReviewAgent repository in PowerShell:

```powershell
$env:PYTHONPATH = "src"
git -C E:\ReviewProjectTest diff main...codex/review-agent-validation |
  python examples/generate_demo_report.py
```

The command generates:

- `examples/demo-review-report.md`: user-facing review report
- `.review-agent/demo/agent.sqlite3`: run, checkpoint, finding, and trace state
- `.review-agent/demo/artifacts/`: raw diff, redacted prompts, and model responses

The included report contains four accepted findings and one reference-only finding. The latter
intentionally targets a deletion-induced defect that cannot be validated against an added line,
showing that the confidence gate does not blindly trust model confidence.
