# 移除 README GitLab 流程

## 用户需求

从 README 最后的 Prompt 章节中删除“GitLab 流程”及其六条规则，然后重新提交并推送。

## 修改与验证

- 仅修改 `README.md` 的 Prompt 代码块。
- 精确删除“GitLab 流程”标题及其完整内容，共删除 15 行、新增 0 行。
- README 其他内容保持不变。
- 搜索确认自建 GitLab 地址、GitLab 流程标题和对应合并规则不再存在。
- Markdown 围栏共 38 行，数量成对。
- `git diff --check` 通过。
