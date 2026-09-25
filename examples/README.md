# 确定性评审演示

该演示使用 `ReviewProjectTest` 的合成 diff，通过真实 ByteCodeReviewAgent CLI 管线生成报告。
模型端由本机确定性 OpenAI-compatible HTTP 服务代替，因此代码和凭证不会离开电脑。

它用于展示产品流程，不代表外部大模型的实际评审质量。

## 运行

在 ByteCodeReviewAgent 项目根目录执行：

```powershell
$env:PYTHONPATH = "src"
git -C E:\ReviewProjectTest diff main...codex/review-agent-validation |
  python examples/generate_demo_report.py
```

生成内容：

- `examples/demo-review-report.md`：面向用户的中文评审报告。
- `.review-agent/demo/agent.sqlite3`：Run、checkpoint、Finding 和 Trace 状态。
- `.review-agent/demo/artifacts/`：原始 diff、脱敏 Prompt、上下文和模型响应。

当前报告包含五条高置信度问题，其中一条使用 `LEFT/删除侧` 定位被删除的保护代码，
其余四条使用 `RIGHT/新增侧` 定位新增代码。

演示还验证：

- 虚构密码在发送模型前被脱敏。
- 每条 Finding 包含 Trace ID。
- 输入、输出 Token 和费用写入本地账本。
- 七个分块逐个保存 checkpoint。
- 删除行可以通过旧文件行号进行高置信度校验。
