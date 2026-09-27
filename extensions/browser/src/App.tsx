import {
  ApiOutlined,
  CheckCircleFilled,
  CodeOutlined,
  DisconnectOutlined,
  FileSearchOutlined,
  GlobalOutlined,
  LinkOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  ConfigProvider,
  Divider,
  Dropdown,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Space,
  Tag,
  Typography,
} from "antd";
import enUS from "antd/locale/en_US";
import zhCN from "antd/locale/zh_CN";
import { useCallback, useEffect, useMemo, useState } from "react";
import { LocalRunnerApi } from "./api";
import {
  categoryLabel,
  DEFAULT_LANGUAGE,
  localizedError,
  severityLabel,
  translate,
} from "./i18n";
import type { Language, MessageKey } from "./i18n";
import {
  activeTabUrl,
  loadLocal,
  loadSession,
  openTab,
  saveLocal,
  saveSession,
} from "./storage";
import type { ConfigStatus, Finding, ReviewJob, RunDetail, RunListItem } from "./types";

const { Title, Paragraph, Text } = Typography;
const DEFAULT_RUNNER = "http://127.0.0.1:8765";

function supportedReviewUrl(value: string): boolean {
  return (
    /^https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/\d+/.test(value) ||
    /^https:\/\/gitlab\.com\/.+\/-\/merge_requests\/\d+/.test(value)
  );
}

function changesUrl(value: string): string {
  const github = value.match(/^(https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/\d+)/);
  if (github) return `${github[1]}/files`;
  const gitlab = value.match(/^(https:\/\/gitlab\.com\/.+\/-\/merge_requests\/\d+)/);
  return gitlab ? `${gitlab[1]}/diffs` : value;
}

function App() {
  const [language, setLanguage] = useState<Language>(DEFAULT_LANGUAGE);

  useEffect(() => {
    void loadLocal<Language>("language", DEFAULT_LANGUAGE).then((storedLanguage) => {
      if (storedLanguage === "zh-CN" || storedLanguage === "en-US") {
        setLanguage(storedLanguage);
      }
    });
  }, []);

  const changeLanguage = async (nextLanguage: Language) => {
    setLanguage(nextLanguage);
    await saveLocal("language", nextLanguage);
  };

  return (
    <ConfigProvider
      locale={language === "zh-CN" ? zhCN : enUS}
      theme={{
        token: {
          colorPrimary: "#3157d5",
          colorSuccess: "#168f70",
          borderRadius: 10,
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif',
        },
      }}
    >
      <AntApp>
        <SidePanel language={language} onLanguageChange={changeLanguage} />
      </AntApp>
    </ConfigProvider>
  );
}

interface SidePanelProps {
  language: Language;
  onLanguageChange: (language: Language) => Promise<void>;
}

function SidePanel({ language, onLanguageChange }: SidePanelProps) {
  const { message } = AntApp.useApp();
  const t = useCallback((key: MessageKey) => translate(language, key), [language]);
  const [baseUrl, setBaseUrl] = useState(DEFAULT_RUNNER);
  const [token, setToken] = useState<string | null>(null);
  const [source, setSource] = useState("");
  const [config, setConfig] = useState<ConfigStatus | null>(null);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [job, setJob] = useState<ReviewJob | null>(null);
  const [pairing, setPairing] = useState(false);
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null);

  const api = useMemo(() => new LocalRunnerApi(baseUrl, token), [baseUrl, token]);

  const refresh = useCallback(async () => {
    if (!token) return;
    const [nextConfig, nextRuns] = await Promise.all([api.config(), api.runs()]);
    setConfig(nextConfig);
    setRuns(nextRuns);
    if (nextRuns[0]) setDetail(await api.run(nextRuns[0].run.id));
  }, [api, token]);

  useEffect(() => {
    void (async () => {
      const [storedUrl, storedToken, tabUrl] = await Promise.all([
        loadLocal("runnerBaseUrl", DEFAULT_RUNNER),
        loadSession("runnerSessionToken"),
        activeTabUrl(),
      ]);
      setBaseUrl(storedUrl);
      setToken(storedToken);
      if (supportedReviewUrl(tabUrl)) setSource(tabUrl);
    })();
  }, []);

  useEffect(() => {
    if (token) {
      refresh().catch(async () => {
        await saveSession("runnerSessionToken", null);
        setToken(null);
      });
    }
  }, [refresh, token]);

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api.job(job.id);
        setJob(next);
        if (next.status === "completed") {
          window.clearInterval(timer);
          message.success(t("reviewComplete"));
          await refresh();
        } else if (next.status === "failed") {
          window.clearInterval(timer);
          message.error(next.error || t("reviewFailed"));
        }
      } catch (error) {
        window.clearInterval(timer);
        message.error(localizedError(language, error));
      }
    }, 900);
    return () => window.clearInterval(timer);
  }, [api, job, language, message, refresh, t]);

  const pair = async (values: { baseUrl: string; code: string }) => {
    const normalized = values.baseUrl.replace(/\/$/, "");
    try {
      const result = await new LocalRunnerApi(normalized, null).pair(values.code);
      await saveLocal("runnerBaseUrl", normalized);
      await saveSession("runnerSessionToken", result.session_token);
      setBaseUrl(normalized);
      setToken(result.session_token);
      message.success(t("connected"));
    } catch (error) {
      message.error(localizedError(language, error));
    } finally {
      setPairing(false);
    }
  };

  const disconnect = async () => {
    await saveSession("runnerSessionToken", null);
    setToken(null);
    setConfig(null);
    setRuns([]);
    setDetail(null);
  };

  const review = async (values: { source: string; budget: number }) => {
    try {
      const created = await api.createReview(values.source.trim(), values.budget);
      setJob(created);
      message.success(t("reviewSubmitted"));
    } catch (error) {
      message.error(localizedError(language, error));
    }
  };

  const languageMenu = {
    selectable: true,
    selectedKeys: [language],
    items: [
      { key: "zh-CN", label: t("chinese") },
      { key: "en-US", label: t("english") },
    ],
    onClick: ({ key }: { key: string }) => {
      void onLanguageChange(key as Language);
    },
  };

  const languageButton = (
    <Dropdown menu={languageMenu} trigger={["click"]} placement="bottomRight">
      <Button
        type="text"
        icon={<GlobalOutlined />}
        aria-label={t("switchLanguage")}
        title={t("switchLanguage")}
      >
        {language === "zh-CN" ? "中" : "EN"}
      </Button>
    </Dropdown>
  );

  if (!token) {
    return (
      <main className="panel-shell centered">
        <div className="pair-language">{languageButton}</div>
        <div className="brand-mark"><CodeOutlined /></div>
        <Title level={2}>{t("pairTitle")}</Title>
        <Paragraph type="secondary">
          {t("pairBeforeCommand")} <Text code>review-agent serve</Text>
          {t("pairAfterCommand")}
        </Paragraph>
        <Card className="pair-card" variant="borderless">
          <Form
            layout="vertical"
            initialValues={{ baseUrl, code: "" }}
            onFinish={(values) => {
              setPairing(true);
              void pair({ ...values, code: values.code.trim().toUpperCase() });
            }}
          >
            <Form.Item name="baseUrl" label={t("runnerAddress")} rules={[{ required: true }]}>
              <Input prefix={<ApiOutlined />} />
            </Form.Item>
            <Form.Item name="code" label={t("pairingCode")} rules={[{ required: true, len: 8 }]}>
              <Input
                autoComplete="off"
                maxLength={8}
                className="pairing-input"
                onInput={(event) => {
                  event.currentTarget.value = event.currentTarget.value.toUpperCase();
                }}
              />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={pairing}>
              {t("secureConnect")}
            </Button>
          </Form>
        </Card>
        <Text type="secondary" className="privacy-note">
          <SafetyCertificateOutlined /> {t("sessionPrivacy")}
        </Text>
      </main>
    );
  }

  return (
    <main className="panel-shell">
      <header className="panel-header">
        <div className="brand-line">
          <div className="mini-mark"><CodeOutlined /></div>
          <div>
            <Text strong>Review Agent</Text>
            <div className="subtitle">{t("subtitle")}</div>
          </div>
        </div>
        <Space size={4}>
          {languageButton}
          <Button
            type="text"
            icon={<ReloadOutlined />}
            aria-label={t("refresh")}
            title={t("refresh")}
            onClick={() => refresh()}
          />
          <Button
            type="text"
            icon={<DisconnectOutlined />}
            aria-label={t("disconnect")}
            title={t("disconnect")}
            onClick={disconnect}
          />
        </Space>
      </header>

      {!config?.ready && (
        <Alert
          type="warning"
          showIcon
          title={t("modelIncomplete")}
          description={t("modelIncompleteDescription")}
        />
      )}

      <Card className="review-card" variant="borderless">
        <div className="card-heading">
          <FileSearchOutlined />
          <Text strong>{t("currentReview")}</Text>
          {config?.ready && (
            <Tag color="success" icon={<CheckCircleFilled />}>
              {t("ready")}
            </Tag>
          )}
        </div>
        <Form
          layout="vertical"
          initialValues={{ source, budget: 10 }}
          fields={[{ name: ["source"], value: source }]}
          onValuesChange={(_, values) => setSource(values.source)}
          onFinish={review}
        >
          <Form.Item name="source" label={t("sourceUrl")} rules={[{ required: true }]}>
            <Input.TextArea autoSize={{ minRows: 2, maxRows: 3 }} />
          </Form.Item>
          <div className="action-row">
            <Form.Item name="budget" label={t("budget")}>
              <InputNumber min={0.01} precision={2} />
            </Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              disabled={!config?.ready || !supportedReviewUrl(source)}
            >
              {t("startReview")}
            </Button>
          </div>
        </Form>
        {job && (
          <Progress
            percent={job.status === "completed" ? 100 : job.status === "failed" ? 100 : 35}
            status={job.status === "failed" ? "exception" : "active"}
            size="small"
          />
        )}
        {supportedReviewUrl(source) && (
          <Button type="link" icon={<LinkOutlined />} onClick={() => openTab(changesUrl(source))}>
            {t("openChanges")}
          </Button>
        )}
      </Card>

      <div className="summary-line">
        <Text type="secondary">{t("model")}</Text>
        <Text strong>{config?.model || t("notConfigured")}</Text>
        <Text type="secondary">{t("runHistory")}</Text>
        <Text strong>{runs.length}</Text>
      </div>

      <Divider titlePlacement="start">{t("recentFindings")}</Divider>
      {!detail?.findings.length ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("noFindings")} />
      ) : (
        <div className="findings-list">
          {detail.findings.map((finding: Finding) => (
            <Card key={finding.id} className="finding-card" variant="borderless">
              <Space wrap size={4}>
                <Tag
                  color={
                    finding.severity === "critical"
                      ? "red"
                      : finding.severity === "high"
                        ? "volcano"
                        : "gold"
                  }
                >
                  {severityLabel(language, finding.severity)}
                </Tag>
                <Tag color={finding.side === "LEFT" ? "magenta" : "blue"}>
                  {finding.side === "LEFT" ? t("deletedSide") : t("addedSide")}
                </Tag>
                <Tag>{categoryLabel(language, finding.category)}</Tag>
              </Space>
              <Title level={5}>{finding.title}</Title>
              <Text type="secondary" className="location">
                {finding.file_path}:{finding.side === "LEFT" ? finding.old_line : finding.new_line}
              </Text>
              <Paragraph ellipsis={{ rows: 3, expandable: true }}>{finding.explanation}</Paragraph>
              <Button
                type="link"
                size="small"
                onClick={async () => setTrace(await api.trace(finding.trace_id))}
              >
                {t("viewTrace")}
              </Button>
            </Card>
          ))}
        </div>
      )}

      <Modal
        title={t("trace")}
        open={Boolean(trace)}
        footer={null}
        onCancel={() => setTrace(null)}
        width={420}
      >
        <pre className="trace-view">{trace ? JSON.stringify(trace, null, 2) : ""}</pre>
      </Modal>
    </main>
  );
}

export default App;
