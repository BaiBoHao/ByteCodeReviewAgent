# 架构说明

## 产品边界

ByteCodeReviewAgent 是本地优先的个人 Code Review Agent。Python Runner 是唯一业务内核，
CLI、本地 Web、Edge 和 VS Code 都是适配层。系统不提供公网、多租户或团队账号能力。

## 分层结构

```text
CLI / Web / Edge / VS Code
            |
      localhost FastAPI
            |
       ReviewService
   /      /   |   \       \
Source Context Tools Model Publisher
   \      \   |   /       /
       SQLite + Artifacts
```

- `SourceLoader`：读取 diff、GitHub PR、GitLab MR 和 base/head 上下文。
- `SecretRedactor`：在模型调用前处理常见凭证和敏感赋值。
- `ContextSelector`：选择完整文件、Python AST 函数或通用行窗口。
- `ToolRegistry`：运行不执行仓库代码的确定性分析工具。
- `ReviewerClient`：连接 OpenAI-compatible JSON 模型接口。
- `BudgetGuard`：模型调用前预留预算，响应后记录实际 Token 与费用。
- `SQLiteStorage`：保存 Run、Chunk、Checkpoint、Trace 和 Finding。
- `GitHubCommentPublisher`：执行评论预览、head SHA 校验和幂等发布。

## Run 状态机

```text
pending -> running -> completed
                   -> failed -> running（resume）
                   -> budget_exhausted -> running（提高预算后 resume）
```

Source 加载、脱敏、上下文选择、diff 分块、Chunk 开始和完成、失败、恢复与终态都会写入
Checkpoint。只有 Trace 与 Finding 在同一事务中保存成功后，`next_chunk_index` 才会前进。

## Trace 设计

每条 Finding 持有 `trace_id`，可以追踪到：

- Run、Chunk 和文件路径；
- 原始 diff 的本地路径与 SHA-256；
- 脱敏 Prompt 的路径与 SHA-256；
- 工具观察结果；
- 模型名称、Provider Request ID 与原始响应；
- 输入/输出 Token、人民币费用；
- 解析失败或网络错误。

SQLite 保存可查询状态，文件系统保存原始证据。默认 Trace 命令不会直接输出原始 diff。

## 上下文与行号

系统同时获取 base/head 文件内容。Python 文件优先使用 AST 选择相关函数；其他语言使用变更行附近的
窗口。模型返回 RIGHT/LEFT：

- RIGHT 必须命中新增行；
- LEFT 必须命中删除行；
- 文件和行号无法验证时自动降低置信度。

## 置信度策略

高置信度 Finding 必须同时满足：模型置信度为 high、文件正确、行号属于对应 diff 侧、包含具体证据。
只有高有效置信度结果进入 `accept`，其他结果保留为 `reference`。

## GitHub 发布

Run 保存评审时的 head SHA。发布前重新读取当前 PR head；发生变化时拒绝发布。评论正文包含隐藏
fingerprint，重复执行时创建、更新或保持不变，因此可以从部分网络失败中安全恢复。

## 扩展原则

新增 Provider、工具、模型或输出形态时只实现对应接口，不改变 ReviewService 的主流程。前端通过
本地 API 访问同一份状态，避免复制评审逻辑。
