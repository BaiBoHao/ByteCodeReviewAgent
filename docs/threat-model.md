# 威胁模型

## 保护对象

- 未公开的仓库源码与 diff；
- 模型 API Key 和 GitHub/GitLab Token；
- 评审结论、Trace 与发布完整性；
- 模型费用预算；
- 运行 Agent 的个人电脑。

## 信任边界

- 仓库内容、diff、README、代码注释均为不可信数据；
- 模型输出是不可信建议，必须经过结构和位置校验；
- localhost 前端是受会话令牌约束的客户端；
- DeepSeek/GitHub/GitLab 是外部 Provider；
- `.env` 和本地 Artifact 依赖操作系统文件权限保护。

## 已实现控制

- PR/MR URL 只允许 HTTPS，并在请求前精确匹配 Host Allowlist；
- 拒绝 URL 中的用户名、密码、Query 和 Fragment；
- Secret 在本地脱敏后才进入 Prompt；
- Prompt 明确把代码标记为不可信数据；
- 不 checkout 或执行用户仓库代码；
- 限制 diff 大小、Chunk 大小、输出 Token、上下文和评论数量；
- 模型调用前进行费用预留，超出预算时不发请求；
- 模型 Finding 必须通过文件、LEFT/RIGHT 行号和证据校验；
- Runner 固定监听 `127.0.0.1`；
- 本地 API 校验 Host、Origin、随机会话令牌和配对码；
- 配对连续失败五次后锁定到 Runner 重启；
- Edge 不保存模型或 Provider Key，会话令牌只保存在 `chrome.storage.session`；
- GitHub 评论默认 dry-run，真实写入需要显式确认；
- 发布前校验 PR head SHA，fingerprint 保证幂等；
- Key 不保存到 SQLite、Trace、报告或 API 响应；
- `.env`、`.review-agent/` 和构建产物均被 Git 忽略。

## 残余风险

- 正则脱敏无法保证识别任意秘密格式；
- 模型仍可能给出错误结论，高置信度策略只能降低风险；
- `.env` 与本地 Artifact 是明文文件，个人电脑被入侵后无法提供强隔离；
- 不同 OpenAI-compatible Provider 对 JSON、思考模式和数据处理承诺存在差异；
- Fine-grained Token 在有效期内仍可代表用户操作已授权仓库；
- 开发者模式加载的浏览器扩展没有商店签名与自动更新；
- PyInstaller Runner 尚未代码签名。

## 正式产品化建议

如果进入商业交付阶段，应把 Key 迁移到 Windows Credential Manager，签名 EXE/安装器，建立自动更新，
并对任何代码执行类工具使用网络禁用、只读、限时和限内存的独立沙箱。
