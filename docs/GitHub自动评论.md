# GitHub PR 自动评论

## 安全默认值

自动评论采用两阶段流程：先预览，后显式发布。默认命令只生成 dry-run 计划，不会向
GitHub 写入任何内容。只有传入 `--apply` 才会创建或更新评论。

发布范围仅包含：

- 有效置信度为 `high`；
- 处置结果为 `accept`；
- 能定位到 PR diff 的 LEFT 删除行或 RIGHT 新增行；
- 未超过 `REVIEW_AGENT_MAX_PUBLISH_COMMENTS` 限制。

## Token 权限

在 `.env` 中配置 Fine-grained GitHub Token：

```dotenv
GITHUB_TOKEN=你的本地Token
```

Token 只需授权目标仓库，并启用：

```text
Pull requests: Read and write
```

Token 不会写入 SQLite、Trace、报告或 API 响应。

## 预览评论

评审完成后执行：

```powershell
review-agent publish RUN_ID
```

输出包含文件、LEFT/RIGHT 侧别、行号、正文以及预计动作。该命令不要求 GitHub Token，
也不会访问 GitHub。

## 正式发布

确认预览后执行：

```powershell
review-agent publish RUN_ID --apply
```

发布前会重新读取 PR 当前 head SHA。如果代码在评审后发生变化，发布会被拒绝，必须先
重新评审，避免把评论附加到错误代码上。

## 幂等机制

每条评论包含不可见的 Finding fingerprint 标识：

```html
<!-- bytecode-review-agent:finding:... -->
```

重复发布时：

- 没有相同标识：创建评论；
- 标识相同但正文变化：更新原评论；
- 标识和正文都相同：保持不变；
- 不会自动删除历史评论。

## 本地 API

本地 Runner 提供：

```text
POST /api/runs/{run_id}/publish
```

请求体默认为安全预览：

```json
{}
```

显式发布请求：

```json
{"apply": true}
```

该接口仍受 Runner 会话令牌、Origin 与 Host 校验保护。
