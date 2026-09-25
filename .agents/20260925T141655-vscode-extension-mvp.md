# VS Code 插件 MVP

## 本次完成

- 创建 `extensions/vscode` TypeScript 扩展工程。
- Activity Bar 提供最近 Run 与 Finding Tree View。
- 支持未提交、已暂存和 PR/MR 评审命令。
- 使用 VS Code SecretStorage 保存模型 API Key。
- 自动选择端口、生成令牌并启动本地 Runner。
- 提供 Runner 健康检查、重启和扩展停用时清理。
- Webview 复用本地 React 控制台。
- RIGHT Finding 支持文件和行号跳转。
- LEFT Finding 打开 Dashboard 查看 base/head 证据。
- Webview Fragment 令牌读入内存后立即清除，并改用请求头鉴权。

## 构建与安全验证

- `npm run build --prefix extensions/vscode`：通过。
- `npm run package --prefix extensions/vscode`：通过。
- VSIX 大小约 13.5 KB。
- 扩展依赖审计：0 个已知漏洞。
- Python 完整测试：32 项全部通过。
- React 生产构建：通过。
- Playwright 验证 Fragment 被清除、历史运行加载成功、控制台 0 错误。
- VSIX 包含 LICENSE、manifest、bundle 和 Activity Bar 图标。

## 残留风险

当前环境没有 `code` CLI，无法执行真实 VS Code Extension Host 安装测试。VSIX 构建和
打包已验证，但 Runner 子进程、Activity Bar 与 Webview iframe 仍需在安装 VS Code 的环境
进行最终验收。

## 后续

- 真实 VS Code 安装验收。
- Runner EXE sidecar 打包。
- LEFT Git revision Diff Editor。
- 共享前端组件包。
