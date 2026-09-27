# GitHub 真实评论发布验收

## Token 配置

- 用户亲自完成 GitHub sudo 身份验证，并明确确认创建 Fine-grained Token。
- Token 名称为 `Review Agent Local`，有效期 30 天。
- 资源范围仅包含 `BaiBoHao/ReviewProjectTest`。
- 权限仅包含 GitHub 强制的 `Metadata: Read-only` 与 `Pull requests: Read and write`。
- Token 从 GitHub 一次性展示页经本机 CDP 回环直接写入 `.env`，未出现在聊天、工具输出、
  日志、代码、SQLite、Trace 或 Git 提交中。
- `.env` 已确认被 Git 忽略，GitHub 只读 PR API 返回 200。

## 真实发布

- 发布 Run：`run_0ab122ea28bb4870`。
- 发布前确认 PR #1 仍为 Open，当前 head SHA 与评审时一致。
- 预览包含 4 条中文高置信度评论，跳过 0 条。
- 首次 POST 遇到 GitHub 连接复用断开，远端最初无评论。
- 后续一次请求实际创建前三条后在第四条中断；fingerprint 幂等机制在修复后识别前三条
  为未变化，只补建最后一条，没有产生重复评论。
- 最终远端只读核验得到 4 条 Review Agent 评论和 4 个唯一 fingerprint。
- 评论覆盖两个 RIGHT 新增行、一个 LEFT 删除行和另一个 RIGHT 新增行。

## 兼容修复

- GitHub API 请求增加固定 `User-Agent: ByteCodeReviewAgent/0.1.0`。
- GitHub API 请求增加 `Connection: close`，避免当前 Windows 网络环境复用连接时断开。
- MockTransport 测试新增对应请求头断言。
- 完整 Python 测试 42 项、Ruff 定向检查和 Python 编译检查通过。
- Windows Runner one-folder 已重建；EXE 启动后确认 DeepSeek 与 GitHub Token 均已配置，
  评论 dry-run 返回 4 条可发布、0 条跳过。

## 评论链接

- `discount_rules.py:8`：`discussion_r4115979038`
- `discount_rules.py:14`：`discussion_r4115979088`
- `order_service.py:20`：`discussion_r4115979151`
- `profile_loader.py:10`：`discussion_r4115985269`

## 下一步

- 再执行一次显式同步，验证最终稳定状态为 4 条 `unchanged`，该动作需要用户确认。
- GitHub 完整验收后实现 GitLab MR Discussion。
- 最后进入 Windows 托盘 Runner、凭据存储和安装器阶段。
