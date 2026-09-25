# Review Agent VS Code 插件

## 当前能力

- 自动启动和停止本地 Python Runner。
- 为 Runner 选择随机回环端口并注入随机会话令牌。
- 使用 VS Code SecretStorage 保存模型 API Key。
- Activity Bar 显示最近运行和最新 Finding。
- 评审未提交修改、已暂存修改和 PR/MR。
- Webview 复用现有 React/Ant Design 本地控制台。
- Webview 通过 URL Fragment 接收短期会话令牌，页面读入内存后立即清除 Fragment。
- RIGHT/新增侧 Finding 可以跳转到当前工作区文件。
- LEFT/删除侧 Finding 打开控制台查看 base/head 证据。

## 开发环境

先确保 Python Runner 可以启动：

```powershell
cd E:\ByteCodeReviewAgent
python -m pip install -e .
```

安装扩展依赖并构建：

```powershell
npm install --prefix extensions\vscode
npm run build --prefix extensions\vscode
```

打包 VSIX：

```powershell
npm run package --prefix extensions\vscode
```

## 配置

VS Code Settings：

```json
{
  "reviewAgent.pythonPath": "python",
  "reviewAgent.runnerPath": "E:\\ByteCodeReviewAgent\\dist\\review-agent-runner\\review-agent-runner.exe",
  "reviewAgent.envFile": "E:\\ByteCodeReviewAgent\\.env",
  "reviewAgent.defaultBudgetCny": 10
}
```

API Key 通过命令 `Review Agent: 安全配置 API Key` 写入 SecretStorage，不要放进 settings.json。

`runnerPath` 有值时直接启动 EXE；为空时优先查找 VSIX 内置 Runner，最后回退到
`python -m bytecode_review_agent`。

## 当前边界

- Runner 需要提前安装 Python 包，尚未打包为独立 EXE sidecar。
- Webview 当前通过本机 iframe 复用控制台，后续可改成共享前端组件直接构建。
- LEFT 删除侧暂时打开控制台，尚未创建 VS Code Git revision 虚拟文档。
- Tree View 当前展示最近 Run 及其 Finding，不包含完整 Trace 内容。
