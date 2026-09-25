# 本地 API 会话安全

## 本次完成

- `review-agent serve` 每次启动生成随机会话令牌。
- 支持通过 `REVIEW_AGENT_SESSION_TOKEN` 注入由 IDE 插件生成的令牌。
- `/api/bootstrap` 使用 HttpOnly、SameSite=Strict Cookie 建立浏览器会话。
- 插件可以通过 `X-Review-Agent-Token` 请求头访问 API。
- 除 bootstrap 外的 API 在启用令牌时统一要求鉴权。
- TrustedHost 只允许回环地址、localhost 和测试 Host。
- 非回环或非 VS Code Webview Origin 的写请求被拒绝。
- React 页面启动时先调用 bootstrap，再读取配置、工具和历史运行。

## 测试

- 未携带令牌访问 API 返回 401。
- bootstrap 后 Cookie 鉴权成功。
- 恶意 Origin 写请求返回 403。
- 非法 Host 返回 400。
- 原有 API、CLI、上下文与删除行测试继续通过。
- 完整测试套件当前 32 项全部通过。

## 后续

VS Code 插件将使用 `crypto.randomBytes` 生成令牌，通过 Runner 环境变量注入，并在扩展进程
内使用请求头访问 API。模型 Key 使用 VS Code SecretStorage，不写入普通配置。
