# Review Agent Edge/Chrome 扩展

## 功能

- 使用 Chromium Side Panel，不向 GitHub/GitLab 页面注入 DOM。
- 自动读取当前活动标签页的 GitHub PR 或 GitLab MR URL。
- 通过 8 位配对码连接本地 Runner。
- 会话令牌只保存在 `chrome.storage.session`，浏览器重启后需要重新配对。
- 发起评审、轮询进度并展示最近 Findings。
- 显示新增侧/删除侧、严重程度、文件和行号。
- 查看 Trace。
- 打开 GitHub Files changed 或 GitLab Diffs 页面。

## 构建

```powershell
npm install --prefix extensions\browser
npm run build --prefix extensions\browser
npm run package --prefix extensions\browser
```

构建目录：

```text
extensions/browser/dist
```

压缩包：

```text
extensions/browser/review-agent-edge-0.1.0.zip
```

## 配对

先启动：

```powershell
review-agent serve --port 8765 --open
```

Runner 终端与本地 Web 页面都会显示 8 位扩展配对码。在 Side Panel 输入 Runner 地址和
配对码，扩展会换取进程级会话令牌。

连续输入错误配对码 5 次后，Runner 会拒绝继续尝试；重启 Runner 会生成新配对码和令牌。

## 安全边界

- 扩展不保存模型 API Key。
- 扩展不读取仓库文件，只读取活动标签页 URL。
- 所有评审与 Secret 脱敏由 localhost Runner 执行。
- 不使用 content script，不依赖 GitHub/GitLab DOM 结构。
- Host 权限仅覆盖 localhost、GitHub 和 GitLab。

## 加载未打包扩展

1. 打开 `edge://extensions`。
2. 开启开发人员模式。
3. 选择“加载解压缩的扩展”。
4. 选择 `extensions/browser/dist`。

加载扩展会改变浏览器状态，执行前应由用户明确确认。
