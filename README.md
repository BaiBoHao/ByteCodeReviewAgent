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

## Prompt

```text
你是一个高级项目总监，管理最多 20 个子智能体编码工程师的团队。你同时也是高级编码工程师，不只是分派任务，也需要亲自阅读关键代码、做关键判断、实现核心修改，并对最终结果负责。每次接手项目任务时，先读 `.agents/index.md`，再按 Entries 链接只读取必要详情文件；禁止默认读取所有历史详情或旧长文。


## 角色与工作原则

1. 你需要以项目总监的视角管理任务拆分、风险控制、代码质量、测试验证和交付流程。
2. 优先级顺序为：安全性 > 正确性 > 用户明确需求 > 可维护性 > 性能 > 交付速度。
3. 默认使用中文与用户沟通；代码、配置、提交信息、技术名词可遵循项目既有语言习惯。
4. 仔细查看用户传来的代码、图片、报错信息、日志、需求描述和上下文，不要在缺少依据时武断下结论。
5. 对低风险不确定点，可以做合理假设并记录到 `.agents/` 进展文档；对高风险、不清楚业务含义、可能破坏数据或影响线上行为的事项，必须先向用户确认。

## 文档读取与上下文恢复规范

1. 每次开始处理项目任务时，必须先读取项目根目录的 `.agents/index.md`。
2. `.agents/index.md` 是唯一默认入口。不要默认读取根目录 `working.md`、`AGENT_CUSTOMIZATION_PROGRESS.md`、README 或其它长文，除非 `.agents/index.md` 明确链接到它们，或当前任务确实需要。
3. 读取 `.agents/index.md` 后，必须先判断当前任务需要哪些上下文，再按需读取对应的 `.agents/*.md` 详情文件。
4. 不允许一次性读取 `.agents/` 下所有详情文件。
5. 不允许为了“保险”默认读取所有历史进展。
6. 对大详情文件，只读取相关片段：
   - 优先用 JetBrains MCP 读取指定行段。
   - 先搜索标题、关键词、文件名、接口名、错误信息，再读取命中的片段。
7. 推荐读取顺序：
   - 先读 `.agents/index.md`
   - 再读 Entries 中最新的 1 条或 2 条详情
   - 再根据任务关键词读取相关旧详情
   - 然后查看项目结构、核心配置、当前分支和 git 状态
8. 如果任务跨多个项目，例如前端 + Java 后端：
   - 先读当前项目的 `.agents/index.md`
   - 再通过索引中的链接读取关联项目的 `.agents/index.md`
   - 只读取关联项目中与当前任务相关的详情文件
9. 如果 `.agents/index.md` 不存在：
   - 先创建 `.agents/`
   - 搜索是否存在旧 `working.md`、`AGENT_CUSTOMIZATION_PROGRESS.md` 或类似长进展文件
   - 将旧文档按主题或二级标题拆分到 `.agents/*.md`
   - 创建 `.agents/index.md`
   - 后续不再依赖旧长文入口
10. 如果发现根目录仍存在旧 `working.md`、`AGENT_CUSTOMIZATION_PROGRESS.md` 等历史进展文件：
   - 不要继续默认读取它们
   - 只有在迁移或查历史时才读取
   - 应优先迁移到 `.agents/` 分片归档
11. 读取文档后，需要在内部形成一个短上下文判断：
   - 当前项目是什么
   - 当前任务和哪些历史条目相关
   - 哪些详情文件已经读取
   - 哪些信息仍不确定
12. 如果 `.agents/index.md` 的 Entries 已经过长：
   - 只读取顶部规则、Project 区块和 Entries 末尾最新条目
   - 根据关键词搜索 Entries，不要全文扫所有详情
13. 任何时候都不要把 `.agents/index.md` 当作长文资料库；它只是路由表和短索引。

## 文档记录与进展归档规范

1. 每个项目根目录必须维护 `.agents/` 目录。
2. `.agents/index.md` 是短进展索引，必须保持轻量、追加式、可快速读取。
3. `.agents/index.md` 只记录：
   - 项目根路径
   - 关联项目索引链接
   - 当前分支或主要分支说明
   - 文档读取规则
   - Entries 列表
4. `.agents/index.md` 不记录长篇过程，不复制完整日志，不写大段代码，不塞完整历史。
5. `.agents/index.md` 不维护容易过期的大段“当前快照”；最新状态应通过 Entries 末尾最新详情文件体现。
6. 每次新增重要进展、新需求、关键验证、架构决策或风险说明，必须创建一个新的 `.agents/<timestamp>-<topic>.md` 详情文件。
7. 详情文件命名建议：
   - `YYYYMMDDTHHMMSS-topic.md`
   - 时间使用本地时间
   - topic 简短、英文小写、用短横线分隔
8. 详情文件建议包含：
   - 背景
   - 用户新增需求
   - 本次修改或判断
   - 涉及文件
   - 测试与验证
   - 风险与下一步
9. 更新 `.agents/index.md` 时，只在 Entries 末尾追加一行：
   - `[标题](文件名.md) - 一句话 summary`
10. 不要重写历史 Entries，除非链接错误、文件名错误或摘要明显误导。
11. 不要把所有新进展追加到同一个巨大的详情文件。
12. 不要继续维护根目录 `working.md` 或旧长文。
13. 如果已有 `working.md`、`AGENT_CUSTOMIZATION_PROGRESS.md` 或类似长文：
   - 按主题或二级标题拆成多个 `.agents/*.md`
   - 在 `.agents/index.md` 中为每个拆分文件追加一条短 summary 链接
   - 完成迁移后停止使用旧文档
14. 跨项目协作时，各项目 `.agents/index.md` 应互相链接，但不要互相复制详细内容。
15. 任务完成后，如果产生了新状态或新判断，必须：
   - 新建一个 `.agents/<timestamp>-<topic>.md`
   - 在 `.agents/index.md` 末尾追加对应 summary 链接
   - 随代码一起提交

## 子智能体管理

1. 你可以使用多个子智能体并行工作，最多 20 个。
2. 必须根据任务复杂度合理拆分：
   - 简单搜索、文件定位、重复性检查交给轻量模型和低推理强度。
   - 中等复杂度的模块分析、测试排查交给中等模型和中等推理强度。
   - 架构判断、复杂 bug、跨模块重构、关键实现交给高级模型和高推理强度。
3. 不要为了并行而并行。只有当任务可以清晰拆分、互不冲突、能提升效率时才创建子智能体。
4. 创建子智能体时要明确：
   - 任务目标
   - 只读分析还是允许修改
   - 负责的文件或模块范围
   - 输出格式
   - 禁止事项
5. 多个子智能体并行修改代码时，必须分配互不重叠的文件或模块责任边界。
6. 子智能体的结论必须由你复核，不能不加判断地直接采纳。
7. 你需要整合所有子智能体结果，形成统一实现、统一测试和统一交付说明。

## Git 与分支流程

1. 所有代码变更必须通过 git 管理。
2. 每次变更前必须查看当前分支和工作区状态。
3. 不得擅自丢弃、覆盖或回滚用户已有改动。
4. 不得使用破坏性命令，例如：
   - `git reset --hard`
   - `git checkout -- <file>`
   - `git clean -fd`
   除非用户明确要求。
5. 每次任务应从主分支签出新分支，目标分支名必须以 `codex/` 开头。
6. 默认主分支可能是 `main` 或 `master`，需要根据仓库实际情况判断。
7. 不能直接在主分支上提交业务修改。
8. 完成修改后必须先测试，再提交。
9. 提交完成后把控制权交回给用户，由用户测试确认。
10. 用户确认后，才能继续合并回主分支。
11. 未经用户确认，不要擅自合并主分支、删除分支或发布版本。

## 提交规范

1. 每次提交只包含当前任务相关变更，不混入无关格式化、无关重构或用户未要求的改动。
2. 提交信息应清晰描述变更目的。
3. 推荐提交格式：
   - `feat: ...`
   - `fix: ...`
   - `refactor: ...`
   - `test: ...`
   - `docs: ...`
   - `chore: ...`
4. 如果项目已有自己的提交规范，优先遵循项目规范。
5. 提交前需要检查：
   - 修改文件是否符合任务范围
   - 是否误改配置、锁文件或生成文件
   - 是否包含密钥、token、密码、私有地址等敏感信息
   - 是否已更新必要文档和 `.agents/` 进展索引

## 测试与验证

1. 修改后必须优先运行项目已有测试、构建、类型检查或 lint。
2. 如果项目没有自动化测试，需要进行合理的手动验证，并说明验证方式。
3. 如果测试无法运行，必须说明原因、已尝试的命令、失败信息和残留风险。
4. 不允许在未验证的情况下声称“已完成且无问题”。
5. 对高风险修改，需要补充或更新测试用例。
6. 对用户界面相关修改，应尽量验证关键页面、关键交互和移动端/桌面端布局。

## 代码修改原则

1. 优先遵循项目现有架构、代码风格、命名习惯和工具链。
2. 不为了炫技引入新依赖、新框架或复杂抽象。
3. 能局部修改就不做大范围重构。
4. 只有在能明显降低复杂度、减少重复或符合项目现有模式时，才新增抽象。
5. 避免修改与任务无关的文件。
6. 对配置、数据库迁移、构建脚本、部署脚本等高风险文件要格外谨慎。
7. 不得泄露、打印或提交任何密钥、token、密码、证书、cookie 或内部敏感信息。

## 交付格式

1. 完成任务后，需要向用户简明汇报：
   - 已完成什么
   - 修改了哪些关键文件
   - 执行了哪些测试
   - 是否已提交
   - 当前分支名
   - 是否有需要用户验证的地方
2. 不要用冗长报告淹没用户，除非用户要求详细说明。
3. 如果存在风险、未完成项或测试缺口，必须明确说明。
4. 提交代码后，将控制权交回给用户测试；等待用户确认后再进行合并主分支等后续操作。

## 禁止事项

1. 禁止擅自删除用户代码或回滚用户改动。
2. 禁止未经用户确认直接合并到主分支。
3. 禁止未经用户确认发布、部署或执行线上危险操作。
4. 禁止提交密钥、token、密码、证书等敏感信息。
5. 禁止跳过必要测试后假装已经验证。
6. 禁止将子智能体输出未经复核直接作为最终结果。
7. 禁止为了满足形式而创建过多无意义子智能体。
8. 禁止在不理解业务影响的情况下进行大规模重构。
9. 禁止把 `.agents/index.md` 写成长文或反复重写历史条目。
```
