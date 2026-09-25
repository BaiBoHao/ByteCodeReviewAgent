# CLI 本地配置与节点提交

## 背景

用户希望将当前后端、CLI 和可填写 API Key 的配置入口作为一个阶段节点提交并推送，
再讨论后续部署与插件形态。

## 本次修改

- CLI 默认读取当前目录 `.env`。
- 支持通过 `--env-file` 指定其他配置文件。
- 支持通过 `REVIEW_AGENT_ENV_FILE` 指定长期配置位置。
- 当前进程环境变量优先于文件配置，CLI 显式参数优先级最高。
- 新增 `review-agent doctor`，只显示 API Key 是否已配置，绝不输出 Key 内容。
- 拒绝将 `replace-me` 等示例占位符识别为有效配置。
- 将 `.env.example` 注释改为中文并强化安全提示。
- 新增中文配置文档 `docs/配置说明.md`。

## 安全边界

- `.env` 已在 `.gitignore` 中，不会被正常提交。
- `.env` 仍是本机明文文件，只适用于当前 CLI 开发阶段。
- 后续 IDE 插件应使用操作系统或 IDE Secret Storage。
- 配置检查、日志、SQLite 和 Trace 均不会输出或保存 API Key。

## 测试与验证

- `python -m unittest discover -s tests -v`：22 项测试全部通过。
- `python -m compileall -q src tests examples`：通过。
- Python 长行检查：无超过 100 字符的代码行。
- 凭证模式扫描：未发现生产凭证。
- 覆盖默认 `.env`、显式文件、环境变量覆盖、缺失文件、占位符和脱敏检查。

## 工具状态

按要求尝试使用 Codex Memory MCP，但当前工具目录仍未提供 Memory/Qdrant 能力，因此
本文件与 `.agents/index.md` 继续作为权威进展记录。
