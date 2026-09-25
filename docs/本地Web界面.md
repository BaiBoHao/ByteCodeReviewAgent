# 本地 Web 界面说明

## 产品定位

本地 Web 界面是 ByteCodeReviewAgent 的第一个图形化入口。它复用现有 Python
`ReviewService`、SQLite、预算、checkpoint、Trace 和 Markdown 报告能力，不复制评审逻辑。

页面默认通过 `127.0.0.1` 访问本地 API，适合个人电脑和后续 IDE 插件复用。

## 功能

- 输入本地 diff 路径、GitHub PR 或 GitLab MR。
- 配置单次评审预算。
- 查看模型配置是否完整，但不显示 API Key 内容。
- 后台创建评审任务并轮询进度。
- 查看历史运行、累计问题和记录费用。
- 区分高置信度与仅供参考问题。
- 查看 Finding 详情和 Trace 证据链。
- 从 SQLite 恢复历史运行数据。

## 安装与构建

安装 Python 依赖：

```powershell
python -m pip install -e .
```

安装前端依赖并构建：

```powershell
npm install --prefix web
npm run build --prefix web
```

构建产物写入 `src/bytecode_review_agent/web_dist`，并通过 Python package data 一起打包。

## 启动

完成 `.env` 配置后运行：

```powershell
review-agent serve --open
```

或者：

```powershell
$env:PYTHONPATH = "src"
python -m bytecode_review_agent serve --port 8765 --open
```

页面地址：

```text
http://127.0.0.1:8765
```

读取其他配置文件：

```powershell
review-agent serve --env-file E:\secure\review-agent.env --open
```

读取已有演示数据：

```powershell
review-agent serve --data-dir .review-agent\demo --open
```

## 前端开发

终端一：

```powershell
review-agent serve --port 8765
```

终端二：

```powershell
npm run dev --prefix web
```

Vite 开发服务器会将 `/api` 转发到 `http://127.0.0.1:8765`。

## 本地 API

主要接口：

```text
GET  /api/health
GET  /api/config
GET  /api/tools
GET  /api/runs
GET  /api/runs/{run_id}
GET  /api/traces/{trace_id}
GET  /api/jobs/{job_id}
POST /api/reviews
POST /api/runs/{run_id}/resume
```

FastAPI 自动文档：

```text
http://127.0.0.1:8765/docs
```

## 安全边界

- `serve` 固定监听 `127.0.0.1`，CLI 不提供公网监听参数。
- 每次启动生成随机会话令牌；也可由插件通过 `REVIEW_AGENT_SESSION_TOKEN` 注入。
- 浏览器先调用 `/api/bootstrap`，服务通过 HttpOnly、SameSite=Strict Cookie 建立会话。
- 插件可以通过 `X-Review-Agent-Token` 请求头访问 API。
- Host 只允许 `127.0.0.1`、`localhost` 和测试环境。
- 外部 Origin 的写请求会被拒绝。
- 未启用 CORS，中间网页不能直接通过跨域请求调用 API。
- API 配置状态只返回 Key 是否存在，不返回 Key 内容。
- 前端不保存模型 Key 或 GitHub/GitLab Token。
- 原始 diff、脱敏 Prompt、模型响应和 Trace 保存在本地数据目录。
- Runner 不执行用户仓库代码。

## 当前限制

- 后台任务状态通过短轮询刷新，尚未使用 SSE。
- 任务队列保存在当前进程内，服务重启后历史 Run 仍在，但临时 Job 状态会丢失。
- 当前仍以 diff 和局部上下文为主，base/head 完整文件增强尚未实现。
- 当前没有直接发布 GitHub/GitLab 行级评论。
- 云端部署、多租户、OAuth 和团队权限不属于本地版本范围。
