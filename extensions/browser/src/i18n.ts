export type Language = "zh-CN" | "en-US";

export const DEFAULT_LANGUAGE: Language = "zh-CN";

const zhCNMessages = {
  language: "语言",
  chinese: "中文",
  english: "English",
  switchLanguage: "切换语言",
  subtitle: "PR / MR 本地评审",
  pairTitle: "连接本地 Review Agent",
  pairBeforeCommand: "先运行",
  pairAfterCommand: "，再输入页面显示的 8 位配对码。",
  runnerAddress: "Runner 地址",
  pairingCode: "配对码",
  secureConnect: "安全连接",
  sessionPrivacy: "令牌只保存在当前浏览器会话",
  connected: "已连接本地 Runner",
  reviewComplete: "评审完成",
  reviewFailed: "评审失败",
  reviewSubmitted: "评审任务已提交",
  refresh: "刷新",
  disconnect: "断开连接",
  modelIncomplete: "模型配置未完成",
  modelIncompleteDescription: "请在本地 Runner 的 .env 中配置模型 API Key。",
  currentReview: "当前评审",
  ready: "就绪",
  sourceUrl: "PR / MR 链接",
  budget: "预算（CNY）",
  startReview: "开始评审",
  openChanges: "打开变更页面",
  model: "模型",
  notConfigured: "未配置",
  runHistory: "历史运行",
  recentFindings: "最近 Findings",
  noFindings: "暂无评审结果",
  deletedSide: "删除侧",
  addedSide: "新增侧",
  viewTrace: "查看 Trace",
  trace: "Trace",
  severityCritical: "严重",
  severityHigh: "高",
  severityMedium: "中",
  severityLow: "低",
  severityInfo: "提示",
  categorySecurity: "安全",
  categoryCorrectness: "正确性",
  categoryResourceManagement: "资源管理",
  categoryPerformance: "性能",
  categoryMaintainability: "可维护性",
  categoryStyle: "代码风格",
  categoryTesting: "测试",
  invalidPairingCode: "配对码无效",
  tooManyPairingAttempts: "配对失败次数过多，请重启 Runner 后重试",
  pairingDisabled: "Runner 未启用浏览器扩展配对",
  requestFailed: "无法连接本地 Runner",
} as const;

export type MessageKey = keyof typeof zhCNMessages;

const messages: Record<Language, Record<MessageKey, string>> = {
  "zh-CN": zhCNMessages,
  "en-US": {
    language: "Language",
    chinese: "中文",
    english: "English",
    switchLanguage: "Switch language",
    subtitle: "Local PR / MR review",
    pairTitle: "Connect to local Review Agent",
    pairBeforeCommand: "Run",
    pairAfterCommand: " first, then enter the 8-character pairing code shown by Runner.",
    runnerAddress: "Runner URL",
    pairingCode: "Pairing code",
    secureConnect: "Connect securely",
    sessionPrivacy: "The token is stored only for this browser session",
    connected: "Connected to local Runner",
    reviewComplete: "Review completed",
    reviewFailed: "Review failed",
    reviewSubmitted: "Review submitted",
    refresh: "Refresh",
    disconnect: "Disconnect",
    modelIncomplete: "Model configuration incomplete",
    modelIncompleteDescription: "Configure the model API key in the local Runner .env file.",
    currentReview: "Current review",
    ready: "Ready",
    sourceUrl: "PR / MR URL",
    budget: "Budget (CNY)",
    startReview: "Start review",
    openChanges: "Open changes",
    model: "Model",
    notConfigured: "Not configured",
    runHistory: "Review history",
    recentFindings: "Recent findings",
    noFindings: "No review findings yet",
    deletedSide: "Deleted side",
    addedSide: "Added side",
    viewTrace: "View trace",
    trace: "Trace",
    severityCritical: "Critical",
    severityHigh: "High",
    severityMedium: "Medium",
    severityLow: "Low",
    severityInfo: "Info",
    categorySecurity: "Security",
    categoryCorrectness: "Correctness",
    categoryResourceManagement: "Resource management",
    categoryPerformance: "Performance",
    categoryMaintainability: "Maintainability",
    categoryStyle: "Code style",
    categoryTesting: "Testing",
    invalidPairingCode: "Invalid pairing code",
    tooManyPairingAttempts: "Too many pairing attempts. Restart Runner and try again.",
    pairingDisabled: "Browser extension pairing is disabled in Runner",
    requestFailed: "Unable to connect to local Runner",
  },
};

export function translate(language: Language, key: MessageKey): string {
  return messages[language][key];
}

const severityKeys: Record<string, MessageKey> = {
  critical: "severityCritical",
  high: "severityHigh",
  medium: "severityMedium",
  low: "severityLow",
  info: "severityInfo",
};

const categoryKeys: Record<string, MessageKey> = {
  security: "categorySecurity",
  correctness: "categoryCorrectness",
  "resource-management": "categoryResourceManagement",
  performance: "categoryPerformance",
  maintainability: "categoryMaintainability",
  style: "categoryStyle",
  testing: "categoryTesting",
};

export function severityLabel(language: Language, severity: string): string {
  const key = severityKeys[severity.toLowerCase()];
  return key ? translate(language, key) : severity;
}

export function categoryLabel(language: Language, category: string): string {
  const key = categoryKeys[category.toLowerCase()];
  return key ? translate(language, key) : category;
}

export function localizedError(language: Language, error: unknown): string {
  const value = error instanceof Error ? error.message : String(error);
  const normalized = value.toLowerCase();
  if (normalized.includes("invalid pairing code")) return translate(language, "invalidPairingCode");
  if (normalized.includes("too many pairing attempts")) {
    return translate(language, "tooManyPairingAttempts");
  }
  if (normalized.includes("browser pairing is disabled")) return translate(language, "pairingDisabled");
  if (normalized.includes("failed to fetch") || normalized.includes("networkerror")) {
    return translate(language, "requestFailed");
  }
  return value;
}
