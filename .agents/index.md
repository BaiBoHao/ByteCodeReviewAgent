# Project

- Root: `E:\ByteCodeReviewAgent`
- Main branch: `main`
- Active implementation branch: `codex/edge-extension`

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
- [下一部署形态决策](20260925T135627-next-deployment-vscode.md) - 下一阶段选择 VS Code 插件与本地 Runner sidecar，优先补会话令牌和 SecretStorage。
- [本地 API 会话安全](20260925T140849-local-api-session-security.md) - 随机会话令牌、HttpOnly Cookie、Host 与 Origin 校验完成，32 项测试通过。
- [VS Code 插件 MVP](20260925T141655-vscode-extension-mvp.md) - Runner 生命周期、SecretStorage、Activity Bar、评审命令、Webview 与 VSIX 打包完成。
- [Windows Runner sidecar](20260925T144751-runner-sidecar.md) - PyInstaller 隔离构建、36.1 MB EXE、实际 API 与内置页面烟雾测试通过。
- [LEFT 虚拟文档与 Diff Editor](20260925T145312-left-diff-editor.md) - Run 脱敏上下文 API、VS Code 虚拟文档与 LEFT Diff Editor 完成，33 项测试通过。
- [Edge 侧边栏扩展与安全配对](20260925T152602-edge-extension.md) - Manifest V3 Side Panel、安全配对、Runner EXE 重建和浏览器联调完成。
