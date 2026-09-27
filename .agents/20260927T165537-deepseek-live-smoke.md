# DeepSeek 真实模型与输出语言

## 背景

用户提供了新购买的 DeepSeek API Key，并明确授权用于真实模型验证。Key 只写入 Git 已忽略的
本地 `.env`，没有写入代码、文档、SQLite、Trace、报告或提交。

## 配置

- 官方 OpenAI 兼容地址：`https://api.deepseek.com`。
- 模型：`deepseek-flash`。
- 预算价格采用官方高峰价：输入 2 元、输出 8 元/百万 Token。
- 新增可选 `REVIEW_AGENT_LLM_THINKING=enabled|disabled` 配置。
- DeepSeek 结构化评审使用 `disabled`，避免输出额度全部消耗在思考内容。

## 真实验证

- 首次真实调用在默认思考模式下返回空 `content`，Run 保存失败 Trace 和 Checkpoint，费用
  记录为 0.012126 元，没有从头丢失状态。
- 增加思考模式兼容配置后，从同一 Run 的第 0 分块恢复，最终完成 7/7 分块。
- 恢复后的 Run 产生 4 条高置信度 Finding，总记录费用 0.031672 元。
- 单独执行中文默认 Run，完成 7/7 分块、4 条中文 Finding，费用 0.020570 元。
- Secret 脱敏计数为 2，报告中虚构密码保持 `[REDACTED_SECRET]`。
- 中文 Run 的评论 dry-run 生成 4 条精确行级评论，未写入 GitHub。

## 输出语言

- ReviewService 新增 `zh-CN` 与 `en-US` 输出语言。
- CLI 新增 `--language`，默认 `zh-CN`。
- 本地 API 校验语言枚举。
- Edge 扩展把当前界面语言随评审请求传给 Runner。
- GitHub 评论的“建议/证据”标签跟随 Run 的输出语言。

## 验证与安全

- 完整 Python 测试 42 项通过。
- TypeScript 类型检查与 Edge 生产构建通过。
- Python 编译检查通过。
- Edge ZIP 与 Windows Runner one-folder 已重新打包，Runner `version` 与脱敏 `doctor` 通过。
- `.env` 已确认被 Git 忽略，Git 状态中不包含 Key。
- Key 曾出现在聊天消息中，完成验证后建议用户在 DeepSeek 控制台旋转。
