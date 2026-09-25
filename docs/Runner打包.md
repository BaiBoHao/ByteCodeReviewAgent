# Runner EXE 打包

## 目标

将 Python 后端、FastAPI、CLI 和本地 Web 静态资源打包为 Windows one-folder sidecar，
使 VS Code 插件不要求最终用户手动安装 Python。

## 构建

```powershell
scripts\build_runner.ps1
```

脚本会创建 `.runner-build-venv` 隔离环境，只安装项目和 `runner` 可选依赖，再执行
PyInstaller。这样不会扫描或打包用户全局 Python 环境中的无关库。

输出：

```text
dist/review-agent-runner/review-agent-runner.exe
dist/review-agent-runner/_internal/...
```

当前采用 one-folder 而不是单文件模式，原因是启动更快、FastAPI 与静态资源定位更稳定，
也方便插件安装时按目录复制 sidecar。

## 验证

```powershell
dist\review-agent-runner\review-agent-runner.exe version

dist\review-agent-runner\review-agent-runner.exe serve `
  --port 8765 `
  --data-dir .review-agent\runner-smoke
```

然后访问：

```text
http://127.0.0.1:8765
```

## VS Code 配置

开发阶段可以显式指定：

```json
{
  "reviewAgent.runnerPath": "E:\\ByteCodeReviewAgent\\dist\\review-agent-runner\\review-agent-runner.exe"
}
```

如果 `runnerPath` 为空，插件会依次尝试：

1. VSIX 内的 `runner/review-agent-runner.exe`。
2. `reviewAgent.pythonPath -m bytecode_review_agent`。

## 发布阶段

正式发布 VSIX 时，应将整个 `dist/review-agent-runner` 目录复制到扩展制品中。当前源码
仓库忽略构建目录和扩展内 runner 目录，避免提交大型二进制文件。
