# base/head 完整文件与函数级上下文

## 本次完成

- GitHub PR Provider 获取 base/head SHA、变更文件列表与两侧完整文件。
- GitLab MR Provider 获取 diff refs 与两侧完整文件。
- 新增文件、删除文件、二进制和超大文件按安全规则跳过无效侧。
- Python 使用 AST 选择变更相关函数或类。
- 删除行通过 base 符号名称在 head 文件匹配同名函数或类。
- 非 Python 文件使用合并行窗口降级策略。
- 完整文件和选中上下文在发送模型前完成脱敏。
- 脱敏上下文写入 `contexts.json`，支持异常恢复且不重复请求 Provider。
- Trace 记录上下文策略、符号、行范围与完整内容哈希。
- Web 详情增加上下文文件数与单分块上下文上限。

## 测试

- Provider 成功路径验证 GitHub/GitLab base/head 文件获取与鉴权头。
- AST 测试验证删除保护代码时同时选择 base/head 的同名函数。
- 上下文字符预算截断测试通过。
- Service 测试验证上下文 Secret 脱敏、Prompt 标签、恢复制品和 Trace 工具记录。
- 完整测试套件当前 29 项全部通过。

## 后续

下一笔提交扩展 Finding 的 `LEFT/RIGHT`、`old_line/new_line`，使删除行问题通过高置信度
校验，并同步更新 SQLite、Markdown、API 和 Web 页面。
