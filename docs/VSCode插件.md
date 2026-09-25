# VS Code 插件

## 产品形态

VS Code 插件作为本地 Review Agent Runner 的第一个 IDE 外壳。插件不复制 Python 评审
逻辑，而是负责 Runner 生命周期、SecretStorage、工作区 Git diff、Activity Bar、文件跳转
和 Dashboard Webview。

## 已实现能力

- 随机选择空闲回环端口。
- 生成 256 位随机会话令牌并注入 Runner 环境。
- 自动启动、健康检查、重启和停止 Python Runner。
- 使用 VS Code SecretStorage 保存模型 API Key。
- 支持可配置 Python 路径、env 文件和默认预算。
- Activity Bar 展示最近 Run 与 Finding。
- 评审未提交修改和已暂存修改。
- 输入 GitHub PR 或 GitLab MR 链接评审。
- Webview 复用现有 React/Ant Design 控制台。
- RIGHT Finding 跳转到当前工作区文件和新文件行号。
- LEFT Finding 打开控制台查看 base/head 证据。

## 会话令牌

插件通过 URL Fragment 将短期令牌传给 localhost 页面：

```text
http://127.0.0.1:PORT/#session=TOKEN
```

React 启动时读取令牌到内存，立即通过 `history.replaceState` 清除 Fragment，后续使用
`X-Review-Agent-Token` 请求头访问 API。令牌不写入 LocalStorage 或配置文件。

普通浏览器继续通过 `/api/bootstrap` 获取 HttpOnly、SameSite=Strict Cookie。

## 开发与打包

```powershell
npm install --prefix extensions\vscode
npm run build --prefix extensions\vscode
npm run package --prefix extensions\vscode
```

生成：

```text
extensions/vscode/bytecode-review-agent-0.1.0.vsix
```

VSIX 被 Git 忽略，不作为源码提交。

## 使用前提

开发版本要求 Python 包可用：

```powershell
python -m pip install -e .
```

正式产品阶段应将 Runner 打包为 `review-agent-runner.exe`，插件不应要求用户手动安装
Python 环境。

## 当前限制

- 当前机器没有 `code` CLI，尚未在真实 VS Code Extension Host 中安装运行。
- Webview 通过 localhost iframe 复用页面，尚未拆分为共享前端组件包。
- LEFT Finding 暂时打开控制台，没有创建 Git base revision 虚拟文档。
- Runner 尚未打包为独立 EXE sidecar。
- Tree View 只展示最近 Run 和 Finding，不直接展示完整 Trace。

## 下一步

1. 在安装 VS Code 的环境执行 VSIX 安装验收。
2. 将 Python Runner 打包为 Windows sidecar。
3. 为 LEFT Finding 实现 Git revision 虚拟文档与 Diff Editor 跳转。
4. 将 React 页面拆成可供 Web、VS Code 和浏览器扩展共享的组件包。
5. 增加扩展自动更新和 Runner 版本兼容检查。
