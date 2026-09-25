# LEFT/RIGHT 与删除行定位

## 本次完成

- 新增 `DiffSide.LEFT` 与 `DiffSide.RIGHT`。
- Finding 增加 `side`、`old_line` 和 `new_line`。
- diff parser 同时收集新增行和删除行集合。
- Prompt 要求模型明确返回 LEFT/RIGHT。
- 置信度验证根据侧别校验对应新增或删除行。
- Fingerprint 加入侧别，避免左右侧同号行冲突。
- SQLite 自动迁移旧 findings 表并兼容历史数据。
- Markdown 报告改为中文并显示新增侧/删除侧。
- API 与 React 页面显示侧别和对应 old/new 行号。
- 确定性演示报告重新生成，五条问题全部为高置信度。

## 测试

- 新增删除行号解析测试。
- 新增 LEFT 删除行高置信度验证测试。
- 原有 RIGHT、新增行、非法行号和恢复测试继续通过。
- 完整测试套件当前 31 项全部通过。

## 后续

核心评审上下文与删除行定位已完成。下一阶段应评估部署形态，推荐优先实现 VS Code 插件，
复用当前本地 Runner、HTTP API 和 React 组件；随后实现 Edge 扩展与 JetBrains 外壳。
