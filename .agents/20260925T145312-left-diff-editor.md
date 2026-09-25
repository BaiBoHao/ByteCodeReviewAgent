# LEFT 虚拟文档与 Diff Editor

## 本次完成

- 本地 API 新增 Run 范围上下文读取接口。
- 接口只读取固定的脱敏 `contexts.json`，不接受任意文件系统路径。
- 文件路径必须精确匹配该 Run 的 file_path、old_path 或 new_path。
- API 支持读取 base 或 head 内容及对应 SHA-256。
- VS Code 注册 `review-agent-context` 只读虚拟文档 Provider。
- Tree View 传递 runId 与 Finding。
- LEFT Finding 打开 base 虚拟文档与工作区 head 文件的 Diff Editor。
- head 文件不存在时，两侧都使用 Runner 脱敏虚拟文档。
- RIGHT Finding 继续跳转当前工作区文件和新文件行号。

## 验证

- 上下文 API 正常返回 Run 范围内 base 内容。
- 路径穿越形式 `../secret.txt` 返回 404。
- VS Code TypeScript 检查与 esbuild bundle 通过。
- VSIX 重新打包成功，大小约 14.24 KB。
- Python 完整测试增至 33 项，全部通过。

## 环境限制

本机没有安装 VS Code，因此无法在真实 Extension Host 点击 LEFT Finding 验收 Diff Editor。
类型、打包、API 与虚拟文档数据路径已验证，最终 UI 行为仍需在安装 VS Code 的环境确认。
