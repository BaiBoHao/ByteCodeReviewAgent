# Edge GitHub 评论预览

## 本次完成

- Edge 侧边栏仅在当前 GitHub PR 与已完成 Run 完全匹配时显示评论预览入口。
- 旧 Run 缺少评审时 head SHA 时不显示发布入口，避免误用历史数据。
- 预览弹窗显示可发布数量、已跳过数量、标题、文件、行号和 LEFT/RIGHT 侧别。
- 弹窗明确提示发布会通知 PR 参与者，并代表本地 GitHub Token 写入评论。
- 未配置 `GITHUB_TOKEN` 时仍可预览，但“发布到 GitHub”按钮保持禁用。
- 用户明确点击发布后才向本地 API 发送 `apply=true`。
- 发布结果显示创建、更新与未变化的评论数量。
- 中文和 English 词典补充完整的发布界面文案。

## 验证

- TypeScript 类型检查和 Vite 生产构建通过。
- 使用公共测试 PR 和本地确定性模型生成新 Run，确认 source metadata 保存 head SHA。
- 新 Run 生成 5 条高置信度 Finding，评论预览显示 5 条，跳过 0 条。
- 未配置 GitHub Token 时真实发布按钮不可点击。
- Playwright 在 420×900 侧边栏尺寸完成视觉验收，浏览器控制台无错误或警告。
- 重新打包 Edge ZIP，并重建 Windows Runner one-folder。
- 新 Runner EXE 的评论预览 API 返回 dry-run、5 条可发布评论和 0 条跳过项。
- 未向真实 GitHub PR 发布任何评论。

## 下一步

- 用户提供最小权限测试 Token 并明确确认后，在测试 PR 执行真实创建验收。
- 重复执行一次，验证五条评论全部进入幂等“未变化”状态。
- GitHub 验收通过后实现 GitLab MR Discussion。
