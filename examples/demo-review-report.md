# 代码评审报告

- 运行 ID：`run_c3a2e25591534513`
- 状态：`completed`
- 来源：`stdin`
- Diff SHA-256：`9ab2ffd21a749bb2d81d49b3b25572fbede08f6cb6b57274cff59b0b26e4ecbd`
- 预算：`1 CNY`
- 记录费用：`0.007000 CNY`
- 进度：`7/7` 分块

## 高置信度问题

### [CRITICAL] Untrusted expression reaches eval

- 位置：`src/review_project_test/discount_rules.py:8`（RIGHT/新增侧）
- 类别：`security`
- 置信度：`high`
- Trace：`trace_e08d410970a542ee`

The expression is executed as Python code, allowing a caller to access builtins and execute arbitrary operations.

修复建议：Replace eval with an allowlisted expression parser.

证据：

- The added line passes the caller-controlled expression to eval.

### [HIGH] Credential is hard-coded in source

- 位置：`src/review_project_test/discount_rules.py:13`（RIGHT/新增侧）
- 类别：`security`
- 置信度：`high`
- Trace：`trace_e08d410970a542ee`

A password literal is stored in the source tree and can be recovered from repository history or packaged artifacts.

修复建议：Load the value from a secret store or runtime environment.

证据：

- The added line assigns a password literal in application code.

### [HIGH] Empty orders cause division by zero

- 位置：`src/review_project_test/order_service.py:20`（LEFT/删除侧）
- 类别：`correctness`
- 置信度：`high`
- Trace：`trace_6f43454688f24361`

Removing the empty-order guard makes the divisor zero for Order(()).

修复建议：Restore an explicit empty-order result before division.

证据：

- The deleted guard was the only zero-length protection.

### [MEDIUM] Profile file handle is never closed

- 位置：`src/review_project_test/profile_loader.py:9`（RIGHT/新增侧）
- 类别：`resource-management`
- 置信度：`high`
- Trace：`trace_b035123f019d400f`

The open file is returned from neither a context manager nor an explicit close, so repeated calls can exhaust file descriptors.

修复建议：Open the profile with a with statement.

证据：

- path.open() is assigned to handle and json.load returns immediately.

### [MEDIUM] Missing display name raises KeyError

- 位置：`src/review_project_test/profile_loader.py:14`（RIGHT/新增侧）
- 类别：`correctness`
- 置信度：`high`
- Trace：`trace_b035123f019d400f`

Profiles without display_name crash instead of using a fallback.

修复建议：Use profile.get('display_name', 'anonymous') before normalization.

证据：

- Direct dictionary indexing is used for an optional profile field.

## 仅供参考

无问题。

## 可追踪性

每条 Finding 都包含 Trace ID。使用 `review-agent trace <TRACE_ID>` 查看模型请求、确定性工具观察和已保存响应。
