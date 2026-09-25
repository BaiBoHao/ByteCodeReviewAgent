# Project

- Root: `E:\ByteCodeReviewAgent`
- Main branch: `main`
- Active implementation branch: `codex/context-aware-review`

# Reading Rules

- Use this file only as a routing index.
- Read only the latest or task-relevant entry files.
- Do not load every historical detail file by default.

# Entries

- [Phase-one backend and CLI](20260924T161445-phase-one-backend-cli.md) - Python review engine, CLI, recovery, trace, budget, security controls, tests, and documentation implemented.
- [Live GitHub PR validation progress](20260924T170707-github-pr-validation.md) - Fixture repository and PR #1 created; GitHub input, diff parsing, redaction, tools, and tests validated pending real model configuration.
- [CLI end-to-end and provider success tests](20260924T171407-cli-e2e-tests.md) - Loopback model server validates the real CLI pipeline; GitHub/GitLab success adapters covered; 16 tests pass.
- [Deterministic product demo report](20260924T183016-demo-report.md) - Reproducible CLI demo produces five findings, Trace IDs, confidence tiers, redaction evidence, and cost output.
- [CLI 本地配置与节点提交](20260925T112918-cli-config-and-release-node.md) - 新增 `.env`、`--env-file` 与脱敏 `doctor` 检查，22 项测试通过，准备提交并推送阶段分支。
- [阶段分支已推送](20260925T113048-stage-branch-pushed.md) - `codex/phase-one-backend-cli` 已保留完整提交历史推送至 GitHub，未合并主分支。
- [本地 API 与 Web 界面](20260925T133635-local-api-web-ui.md) - FastAPI、本地后台任务、React/Ant Design 页面、26 项测试和 Playwright 视觉验收完成。
- [base/head 完整文件与函数级上下文](20260925T134750-base-head-context.md) - GitHub/GitLab 完整文件、Python AST 上下文、脱敏恢复制品和 Trace 哈希完成，29 项测试通过。
- [LEFT/RIGHT 与删除行定位](20260925T135248-left-right-deleted-lines.md) - 新增左右侧行号、SQLite 迁移、中文报告与 Web 侧别展示，31 项测试通过。
