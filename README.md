# ByteCodeReviewAgent

> 一个可恢复、可追踪、可控成本，并能真正把评审意见发布到 GitHub PR 的本地 AI Code Review Agent。

ByteCodeReviewAgent 不是一次性的“把 diff 丢给大模型”脚本，而是一套可以在个人电脑上长期使用的
本地评审产品：它接收 GitHub PR、GitLab MR 或 git diff，在代码离开电脑前完成 Secret 脱敏，
结合 base/head 文件与函数上下文调用模型，保存 Checkpoint、Trace、Token 和费用，最后通过 CLI、
本地 Web 或 Edge 侧边栏展示结果，并可在用户确认后发布 GitHub 行级评论。

## 60 秒产品介绍

### 解决什么问题

Code Review 很重要，但人工评审通常重复、耗时，也容易因上下文切换产生疲劳。直接使用通用聊天工具
又会带来三个问题：不知道代码是否泄露、模型结论难以追踪、失败后只能从头再来。

### 我做了什么

我把评审流程做成了一个本地优先的 Agent 后端，并提供多种使用入口：

- 开发者可以在终端使用 CLI；
- 普通用户可以打开本地 Web 页面；
- 在 GitHub PR 页面中，可以直接使用 Edge 侧边栏；
- Windows 用户可以运行打包后的 Runner，不必理解 Python 项目结构；
- VS Code 形态保留为实验性扩展，证明同一后端可以被不同前端复用。

### 最终效果

- 使用真实 DeepSeek 模型完成测试 PR 的 7/7 分块评审；
- 生成 4 条中文高置信度 Finding，实际记录费用约 0.0206 元；
- 在真实 GitHub PR 上发布 4 条中文行级评论；
- 正确定位 3 条新增侧问题和 1 条删除侧问题；
- 网络中断后依靠 fingerprint 恢复发布，没有产生重复评论；
- 42 项自动化测试通过，Edge 前端依赖审计为 0 个已知漏洞。

真实评论可以直接查看：

- [任意代码执行问题](https://github.com/BaiBoHao/ReviewProjectTest/pull/1#discussion_r4115979038)
- [硬编码管理员口令](https://github.com/BaiBoHao/ReviewProjectTest/pull/1#discussion_r4115979088)
- [删除空列表保护](https://github.com/BaiBoHao/ReviewProjectTest/pull/1#discussion_r4115979151)
- [文件句柄资源泄漏](https://github.com/BaiBoHao/ReviewProjectTest/pull/1#discussion_r4115985269)

## 一、题目介绍

题目要求实现一个 **Code Review Agent**：

- 输入 GitHub PR、GitLab MR 链接或 git diff；
- 输出评审评论或 Markdown 报告；
- 异常后能够从 Checkpoint 恢复；
- 每条评论能够追踪模型输入、工具调用和模型输出；
- 工具和能力可以扩展；
- 能够控制 Token 与费用预算；
- 区分高置信度问题与仅供参考的问题；
- 不把 Secret 暴露给模型，不在用户仓库中任意执行代码；
- 使用 AI 完成项目，并展示对 AI 工具的理解和工程化使用能力。

这道题表面上是在“调用模型评审代码”，实际考查的是：如何把不稳定的模型能力约束在一套可靠、
安全、可验证的工程系统中。

## 二、题目分析

### 1. 真正困难的不是 Prompt，而是评审闭环

一个能演示的 Prompt 很容易，但一个可使用的评审产品还必须回答：

- 模型看到的是不是完整而且正确的上下文？
- 评论中的文件和行号是否真的存在于这次变更？
- 删除代码导致的问题应该评论在旧文件还是新文件？
- 模型调用失败或预算耗尽后，能否继续而不是全部重跑？
- 用户为什么应该相信某条 Finding？
- 重复发布时，怎样避免在 PR 中刷出重复评论？
- API Key、仓库 Token 和源码如何避免被泄露？

因此我把需求拆成了六个稳定边界：

| 能力 | 设计目标 | 当前实现 |
|---|---|---|
| 输入 | 同一引擎支持不同代码来源 | diff、stdin、GitHub PR、GitLab MR |
| 上下文 | 不只看新增行 | base/head 完整文件、Python AST 函数级上下文、通用窗口上下文 |
| Agent | 可控而不是无限自主循环 | 确定性编排、声明式工具、结构化 JSON 输出 |
| 可靠性 | 失败不从头开始 | SQLite Run、Chunk Checkpoint、Resume |
| 可解释性 | 每条结论都能还原 | Trace ID、Prompt/Response、工具观察、Token、费用、Diff Hash |
| 输出 | 同一后端服务不同用户入口 | Markdown、CLI、本地 Web、Edge、VS Code MVP、GitHub 评论 |

### 2. 为什么选择 Python 后端

本题第一优先级是快速建立稳定的 Agent 编排、Provider 接入、SQLite 状态和 CLI。Python 在 HTTP、
数据校验、模型生态、测试和 Windows 打包方面代码量较小，适合先做稳定内核。

前端使用 React + TypeScript + Ant Design；后端使用 FastAPI 提供只监听 localhost 的本地 API。
这种组合既能快速完成 Take-Home，也能自然扩展到浏览器侧边栏和 IDE 插件。

### 3. 为什么不做云端服务

当前产品面向个人电脑使用。将 Runner 放在本地有三个直接收益：

- 原始 diff、Token、Trace 和历史 Run 默认不离开电脑；
- 不需要设计账号、租户、计费和云端数据库；
- CLI、Web、Edge 和 IDE 可以共享同一个本地 Agent 内核。

## 三、实现思路

### 1. 一次评审如何运行

```mermaid
sequenceDiagram
    participant U as 用户
    participant UI as CLI / Web / Edge
    participant R as 本地 Runner
    participant S as Source Adapter
    participant M as DeepSeek / 兼容模型
    participant DB as SQLite + Artifacts
    participant G as GitHub

    U->>UI: 输入 PR/MR/diff 与预算
    UI->>R: 创建评审任务
    R->>S: 获取 diff 与 base/head 上下文
    R->>R: Secret 脱敏、分块、工具分析
    R->>M: 发送脱敏后的结构化评审请求
    M-->>R: 返回 JSON Finding
    R->>R: 校验文件、LEFT/RIGHT 行号和证据
    R->>DB: 原子保存 Trace、Finding、Checkpoint、费用
    R-->>UI: 展示高置信度与参考项
    U->>UI: 预览并确认发布
    UI->>R: apply=true
    R->>G: 创建或幂等更新行级评论
```

### 2. Agent 为什么可恢复

评审被切分为文件级 Chunk。只有当某个 Chunk 的 Trace 和 Finding 在同一事务中保存成功，
`next_chunk_index` 才会前进。

```mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Running
    Running --> Completed
    Running --> Failed: 模型/网络/解析失败
    Running --> BudgetExhausted: 预算不足
    Failed --> Running: resume
    BudgetExhausted --> Running: 提高预算后 resume
```

真实 DeepSeek 验证中，首次请求因为思考模式耗尽输出额度而返回空内容。系统记录了失败 Trace 和费用，
关闭思考模式后从原 Run 恢复，最终完成 7/7 分块。这不是只在单元测试里模拟的能力。

### 3. Agent 为什么可追踪

每条 Finding 都包含 Trace ID。Trace 可以关联：

- Run、Chunk、文件路径；
- 原始 diff 路径与 SHA-256；
- 脱敏 Prompt 路径与 SHA-256；
- 确定性工具观察；
- 模型、Provider Request ID 和原始响应；
- 输入/输出 Token 与人民币费用；
- 失败时的解析或网络错误。

### 4. Agent 如何判断置信度

模型说“高置信度”并不代表系统直接相信它。只有同时满足以下条件才会成为 `accept`：

1. 模型给出 high confidence；
2. 文件路径与当前 Chunk 完全一致；
3. RIGHT 行号属于新增行，或 LEFT 行号属于删除行；
4. Finding 包含具体证据。

其他结果不会被丢弃，而是降级为 `reference`，供用户参考但不自动发布。

### 5. GitHub 评论如何避免重复

每条评论包含不可见的 Finding fingerprint。再次运行时：

- 没有相同 fingerprint：创建评论；
- fingerprint 相同但正文改变：更新评论；
- fingerprint 和正文都相同：保持不变；
- 发布前发现 PR head SHA 已变化：拒绝发布，要求重新评审。

真实发布过程中发生网络中断，前三条评论已到达 GitHub、第四条未完成。再次执行后，系统识别前三条
为 `unchanged`，只补建第四条，证明幂等策略能够处理真实的部分失败。

## 四、总体架构

```mermaid
flowchart TB
    subgraph Entry[前端与入口层]
        CLI[CLI 命令行]
        WEB[React 本地 Web]
        EDGE[Edge Side Panel]
        VSCODE[VS Code MVP]
    end

    subgraph Local[本地 Runner / Agent 后端]
        API[FastAPI localhost API]
        SERVICE[ReviewService 编排器]
        SOURCE[SourceLoader\nGitHub / GitLab / diff]
        REDACT[Secret Redactor]
        CONTEXT[Context Selector\nbase / head / AST]
        TOOLS[Tool Registry]
        MODEL[OpenAI-compatible Reviewer]
        BUDGET[Budget Guard]
        PUBLISH[GitHub Comment Publisher]
    end

    subgraph State[本地状态]
        SQLITE[(SQLite)]
        FILES[(Diff / Prompt / Response / Report)]
    end

    PROVIDERS[GitHub / GitLab]
    LLM[DeepSeek / 兼容模型]

    CLI --> API
    WEB --> API
    EDGE --> API
    VSCODE --> API
    API --> SERVICE
    SERVICE --> SOURCE
    SERVICE --> REDACT
    SERVICE --> CONTEXT
    SERVICE --> TOOLS
    SERVICE --> BUDGET
    SERVICE --> MODEL
    SERVICE --> SQLITE
    SERVICE --> FILES
    SOURCE --> PROVIDERS
    MODEL --> LLM
    PUBLISH --> PROVIDERS
    API --> PUBLISH
```

核心原则是：**前端可以变化，评审逻辑只有一份。** CLI、Web、Edge 和 VS Code 都通过同一个
ReviewService 与本地 API 工作，不复制 Agent 编排代码。

## 五、后端能力

- GitHub PR、GitLab MR、本地 diff、stdin 输入；
- HTTPS 与 Host Allowlist，拒绝 URL 凭证、Query 和未知来源；
- Secret 本地脱敏；
- 大 diff 文件级分块；
- base/head 完整文件与 Python 函数级上下文；
- LEFT/RIGHT 删除行与新增行定位；
- OpenAI-compatible JSON 模型接口；
- DeepSeek 思考模式兼容；
- Token 用量与人民币预算保护；
- SQLite Checkpoint、失败恢复与 Trace；
- 声明式安全工具注册；
- Markdown 中文报告；
- GitHub 评论 dry-run、显式发布、head SHA 校验和幂等更新；
- 本地 API 会话令牌、配对码、Host/Origin/CORS 限制。

## 六、前端与部署形态

| 形态 | 面向用户 | 能力 | 状态 |
|---|---|---|---|
| CLI | 开发者、自动化脚本 | review、resume、trace、runs、doctor、publish | 完成 |
| 本地 Web | 不习惯命令行的用户 | 创建评审、进度、历史 Run、Finding、Trace | 完成 |
| Edge 扩展 | GitHub/GitLab 网页用户 | 自动识别 PR/MR、评审、双语、评论预览与发布 | 主要产品形态 |
| Windows Runner | Windows 用户 | 无需手工管理 Python，运行后端和内置 Web | 完成 one-folder 构建 |
| VS Code MVP | IDE 用户 | Runner 生命周期、Tree View、Diff Editor、Webview | 实验性产物 |

本项目不部署公网服务，也不实现多租户平台。JetBrains 插件不在最终范围内。

## 七、我如何使用 AI 完成这个项目

这个项目想证明的不是“我会让 AI 生成代码”，而是我能够管理一个跨模块、跨会话、可验证的
AI 协作工程。我重点建立了三种工作习惯。

### 1. 我自己管理索引上下文

我没有把所有历史内容堆进一个越来越长的文档，也没有依赖某一次聊天记住全部细节。

项目使用 `.agents/index.md` 作为唯一短索引，每个关键节点单独记录到带时间戳的详情文件：

```text
.agents/
├─ index.md
├─ 20260924T161445-phase-one-backend-cli.md
├─ 20260925T133635-local-api-web-ui.md
├─ 20260925T152602-edge-extension.md
├─ 20260927T161437-github-comment-publisher.md
├─ 20260927T165537-deepseek-live-smoke.md
└─ 20260927T235758-github-live-publish.md
```

每次开始工作先读索引，再按任务读取一到两个相关详情。这样既能恢复上下文，又不会让旧信息污染当前判断。
这也是我对 AI 长上下文问题的工程化回答：**不是无限增加上下文，而是建立可检索的上下文路由。**

### 2. 我自己进行版本管理

我把需求拆成可以独立测试和回滚的 Git 节点，而不是让 AI 在主分支一次性生成整个项目。

主要阶段包括：

```text
codex/phase-one-backend-cli
codex/local-web-ui
codex/context-aware-review
codex/vscode-extension
codex/vscode-sidecar
codex/edge-extension
codex/github-comment-publisher
```

每个节点遵循同一流程：查看工作区、限定修改范围、测试、敏感信息扫描、提交，再进入下一阶段。
真实模型、真实浏览器、真实 GitHub 评论验证也都在独立节点完成。

这说明我使用 AI 时仍然保持工程控制权：AI 可以加速实现，但分支策略、验收标准、风险边界和是否发布
由我管理。

### 3. 我习惯进行跨会话交流

项目经历了需求分析、CLI、Web、上下文增强、删除行定位、VS Code、Runner、Edge、真实模型和
GitHub 评论等多个会话。每次结束时，我都会把以下信息写入仓库：

- 用户新增需求与范围变化；
- 已完成的架构决策；
- 修改文件；
- 测试命令和结果；
- 失败原因与修复；
- 当前风险和下一步。

因此下一次会话不需要依赖“聊天记忆”，而是从版本化事实恢复工作。AI、用户或新的协作者都可以读取
同一份进展记录。这种方式让跨会话协作可审计、可移交，也显著降低重复解释和错误假设。

### AI 与人的职责边界

AI 参与了需求拆解、架构讨论、代码实现、测试生成、浏览器验收和错误定位；人的判断始终控制：

- 产品范围与优先级；
- 哪些行为允许自动执行；
- Secret 与账号权限；
- 是否调用付费模型；
- 是否向真实 PR 发布评论；
- 最终验收和版本节点。

详细记录见 [AI 使用说明](docs/ai-usage.md) 与 `.agents/`。

## 八、安全设计

- 仓库内容始终被视为不可信数据，不会被当作指令执行；
- 不 checkout 或执行用户仓库代码；
- Secret 在模型调用前本地脱敏；
- 模型 Key 和平台 Token 不写入数据库、Trace、报告或 API 响应；
- `.env` 被 Git 忽略，并在提交前扫描凭证特征；
- Provider URL 仅允许 HTTPS 与精确 Host Allowlist；
- Runner 只监听 `127.0.0.1`；
- 本地 API 使用随机会话令牌和 8 位配对码；
- Edge 会话 Token 只保存在 `chrome.storage.session`；
- GitHub Token 只授权测试仓库与 Pull requests 写权限；
- 评论默认 dry-run，真实发布需要用户再次明确确认；
- 单次评论数有限制，避免模型异常造成评论洪泛。

更完整的边界见 [威胁模型](docs/threat-model.md)。

## 九、快速开始

### 方式 A：CLI

要求 Python 3.11+。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item .env.example .env
```

在 `.env` 中填写兼容模型配置后检查：

```powershell
review-agent doctor
```

评审本地 diff：

```powershell
git diff | review-agent review - --budget 10 --output review-report.md
```

评审 PR/MR：

```powershell
review-agent review https://github.com/org/repo/pull/123 --budget 10
review-agent review https://gitlab.com/group/project/-/merge_requests/123 --budget 10
```

失败后恢复：

```powershell
review-agent resume RUN_ID
```

预览与发布 GitHub 评论：

```powershell
review-agent publish RUN_ID
review-agent publish RUN_ID --apply
```

### 方式 B：本地 Web

```powershell
review-agent serve --open
```

页面默认地址：`http://127.0.0.1:8765`。

### 方式 C：Windows Runner

构建：

```powershell
scripts\build_runner.ps1
```

运行时必须保留整个 one-folder 目录：

```powershell
dist\review-agent-runner\review-agent-runner.exe serve --open
```

### 方式 D：Edge 侧边栏

```powershell
npm install --prefix extensions\browser
npm run package --prefix extensions\browser
```

然后在 `edge://extensions` 开启开发人员模式，加载 `extensions/browser/dist`。启动 Runner 后，
输入终端或本地 Web 显示的 8 位配对码即可连接。

详细步骤见 [Edge 扩展说明](extensions/browser/README.md) 和 [配置说明](docs/配置说明.md)。

## 十、测试与真实验收

运行完整后端测试：

```powershell
python -m unittest discover -s tests -v
```

构建前端：

```powershell
npm run build --prefix web
npm run build --prefix extensions\browser
```

当前验收结果：

| 项目 | 结果 |
|---|---|
| Python 自动化测试 | 42 项通过 |
| Python 编译检查 | 通过 |
| Edge TypeScript + Vite | 通过 |
| Edge 依赖审计 | 0 个已知漏洞 |
| Windows Runner EXE | version、doctor、API、Web、评论预览通过 |
| DeepSeek 真实 PR 评审 | 7/7 分块、4 条中文 Finding、约 0.0206 元 |
| GitHub 真实评论 | 4 条、4 个唯一 fingerprint、无重复 |
| Secret 扫描 | Key 未进入 Git 提交 |

## 十一、项目结构

```text
ByteCodeReviewAgent/
├─ src/bytecode_review_agent/   # Agent 内核、API、CLI、Provider、发布器
├─ web/                         # React + Ant Design 本地 Web
├─ extensions/browser/          # Edge/Chrome Manifest V3 Side Panel
├─ extensions/vscode/           # VS Code MVP
├─ packaging/                   # PyInstaller Runner 配置
├─ scripts/                     # Runner 构建脚本
├─ tests/                       # 单元与集成测试
├─ examples/                    # 确定性演示与示例报告
├─ docs/                        # 架构、安全、配置与使用文档
└─ .agents/                     # 跨会话上下文索引与进展记录
```

## 十二、当前范围与边界

- GitHub PR 已支持真实行级评论；
- GitLab MR 已支持读取、上下文和 Markdown 报告，尚未实现 Discussion 自动发布；
- 当前是本地个人工具，不提供公网、多租户或团队账号系统；
- Edge 采用开发者模式加载，未发布到扩展商店；
- Windows Runner 是 one-folder 产物，不提供安装器、托盘程序和自动升级；
- VS Code 已完成 MVP 构建，但未在真实 Extension Host 中做最终安装验收；
- `.env` 适合个人电脑与演示，正式商业产品应迁移到 Windows Credential Manager；
- Secret 脱敏属于纵深防御，不能数学上证明任意文本中绝对没有秘密信息。

这些边界是主动的产品取舍：本项目优先证明 Agent 内核、可靠性、安全性、可扩展前端和真实发布闭环，
而不是扩张为云端平台。

## 延伸文档

- [配置说明](docs/配置说明.md)
- [GitHub 自动评论](docs/GitHub自动评论.md)
- [本地 Web](docs/本地Web界面.md)
- [Runner 打包](docs/Runner打包.md)
- [上下文增强](docs/上下文增强.md)
- [删除行定位](docs/删除行定位.md)
- [VS Code 插件](docs/VSCode插件.md)
- [架构说明](docs/architecture.md)
- [威胁模型](docs/threat-model.md)
- [AI 使用说明](docs/ai-usage.md)

## 总结

ByteCodeReviewAgent 展示了从题目理解、需求拆解、Agent 架构、模型接入到多前端形态和真实平台发布的
完整过程。更重要的是，它保留了索引化上下文、Git 版本节点、跨会话进展、Trace、测试和真实验收证据。

我希望这份项目证明：我不只是会使用 AI 生成代码，也能够把 AI 纳入一套有范围、有安全边界、
有版本管理、有验收标准、可以持续协作的工程流程中。
