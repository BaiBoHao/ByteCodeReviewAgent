# GitHub PR 评论发布后端

## 背景

产品范围收敛为本地后端、CLI、Edge 扩展和 Windows 产品包，不再实现 JetBrains 或公网
服务。本节点先实现 GitHub PR 自动评论，真实写入保持显式确认。

## 本次完成

- 新增 GitHub Review Comment 发布模块。
- CLI 新增 `review-agent publish RUN_ID`，默认只输出 dry-run 计划。
- 只有 `--apply` 才会创建或更新真实评论。
- 本地 API 新增 `POST /api/runs/{run_id}/publish`，请求体默认 dry-run。
- 只发布高有效置信度、`accept` 且有有效 diff 行号的 Finding。
- LEFT 使用旧文件行号，RIGHT 使用新文件行号。
- 每条评论包含隐藏 fingerprint，重复运行时执行创建、更新或保持不变。
- 发布前校验当前 PR head SHA 与评审时 SHA 一致，代码变化后拒绝发布。
- 单次评论数默认限制为 20，可通过环境变量调整。
- `GITHUB_TOKEN` 只在显式发布时要求，dry-run 不访问 GitHub。

## 验证

- 完整 Python 测试 39 项通过。
- Python 编译检查通过。
- 新增测试覆盖无 Token dry-run、创建、更新、幂等跳过、LEFT/RIGHT、head 变化拒绝、
  Token 缺失和 API 默认安全模式。
- 新增发布模块与测试通过 Ruff 检查；历史文件按既有基线规则检查通过。
- 未向真实 GitHub PR 发布任何评论。

## 下一步

- 在 Edge 扩展增加评论预览与明确的发布确认界面。
- 用户确认后，在测试仓库 PR #1 执行一次真实发布验收。
- GitHub 验收完成后，以相同安全策略实现 GitLab MR Discussion。
