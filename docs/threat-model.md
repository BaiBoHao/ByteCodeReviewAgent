# Threat model

## Protected assets

- Repository source and unpublished diffs
- Provider and model credentials
- Review integrity and trace evidence
- Cost budget
- The machine running the agent

## Implemented controls

- Only HTTPS PR/MR URLs are accepted.
- URL hosts must exactly match an explicit allowlist before any request, reducing SSRF exposure.
- Provider and model tokens are read from environment variables and are not persisted in run data.
- Known secret formats and secret assignments are redacted locally before prompt construction.
- Diff text is explicitly delimited and labelled untrusted in the system prompt.
- Repository code is never checked out or executed.
- Diff byte limits, chunk limits, output-token limits, and a pre-call monetary reservation constrain
  resource and cost abuse.
- Original diffs are local artifacts and are not returned by the normal trace command.
- Failed and partial runs retain checkpoints rather than silently restarting.

## Residual risks

- Regex redaction cannot guarantee detection of every secret format.
- A model can still produce incorrect or malicious-looking content; location and confidence
  validation reduce but do not eliminate this risk.
- Local artifacts are plaintext and rely on operating-system filesystem permissions.
- OpenAI-compatible endpoints differ; operators must verify that their provider honours requested
  data-handling and JSON-mode behavior.
- A future code-executing tool would create a new trust boundary and must use an explicit,
  network-disabled, read-only, time- and memory-limited sandbox.
