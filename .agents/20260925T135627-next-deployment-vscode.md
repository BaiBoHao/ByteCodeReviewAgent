# 下一部署形态决策

## 结论

下一部署形态选择 VS Code 插件与本地 Runner sidecar，不立即开发 Edge 扩展、JetBrains
插件或云端多租户服务。

## 依据

- 当前 FastAPI 可以直接作为 Runner API。
- 当前 React/Ant Design 页面可作为 VS Code Webview 基础。
- IDE 插件能提供本地 diff、文件跳转和 LEFT/RIGHT Diff 体验。
- 本地模式保持代码和 SQLite 数据在个人电脑中。
- VS Code TypeScript 开发与现有 React 技术栈一致，交付速度最快。

## 前置安全工作

- 本地 API 增加随机会话令牌和 Origin/Host 校验。
- API Key 改用 VS Code SecretStorage 或系统凭证库。
- 限制本地文件读取范围。
- 明确插件启动与停止 Runner 的生命周期。

## 后续顺序

1. VS Code 插件。
2. Edge/Chrome 扩展。
3. JetBrains 插件。
4. 云端团队版。

详细方案见 `docs/下一部署形态.md`。
