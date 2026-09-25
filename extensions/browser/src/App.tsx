import {
  ApiOutlined,
  CheckCircleFilled,
  CodeOutlined,
  DisconnectOutlined,
  FileSearchOutlined,
  LinkOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Descriptions,
  Divider,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Progress,
  Space,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { LocalRunnerApi } from "./api";
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
  return (
    <AntApp>
      <SidePanel />
    </AntApp>
  );
}

function SidePanel() {
  const { message } = AntApp.useApp();
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
          message.success("评审完成");
          await refresh();
        } else if (next.status === "failed") {
          window.clearInterval(timer);
          message.error(next.error || "评审失败");
        }
      } catch (error) {
        window.clearInterval(timer);
        message.error((error as Error).message);
      }
    }, 900);
    return () => window.clearInterval(timer);
  }, [api, job, message, refresh]);

  const pair = async (values: { baseUrl: string; code: string }) => {
    const normalized = values.baseUrl.replace(/\/$/, "");
    try {
      const result = await new LocalRunnerApi(normalized, null).pair(values.code);
      await saveLocal("runnerBaseUrl", normalized);
      await saveSession("runnerSessionToken", result.session_token);
      setBaseUrl(normalized);
      setToken(result.session_token);
      message.success("已连接本地 Runner");
    } catch (error) {
      message.error((error as Error).message);
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
      message.success("评审任务已提交");
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  if (!token) {
    return (
      <main className="panel-shell centered">
        <div className="brand-mark"><CodeOutlined /></div>
        <Title level={2}>连接本地 Review Agent</Title>
        <Paragraph type="secondary">
          先运行 <Text code>review-agent serve</Text>，再输入页面显示的 8 位配对码。
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
            <Form.Item name="baseUrl" label="Runner 地址" rules={[{ required: true }]}>
              <Input prefix={<ApiOutlined />} />
            </Form.Item>
            <Form.Item name="code" label="配对码" rules={[{ required: true, len: 8 }]}>
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
              安全连接
            </Button>
          </Form>
        </Card>
        <Text type="secondary" className="privacy-note">
          <SafetyCertificateOutlined /> 令牌只保存在当前浏览器会话
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
            <div className="subtitle">PR / MR 本地评审</div>
          </div>
        </div>
        <Space size={4}>
          <Button type="text" icon={<ReloadOutlined />} onClick={() => refresh()} />
          <Button type="text" icon={<DisconnectOutlined />} onClick={disconnect} />
        </Space>
      </header>

      {!config?.ready && (
        <Alert
          type="warning"
          showIcon
          title="模型配置未完成"
          description="请在本地 Runner 的 .env 中配置模型 API Key。"
        />
      )}

      <Card className="review-card" variant="borderless">
        <div className="card-heading">
          <FileSearchOutlined />
          <Text strong>当前评审</Text>
          {config?.ready && <Tag color="success" icon={<CheckCircleFilled />}>就绪</Tag>}
        </div>
        <Form
          layout="vertical"
          initialValues={{ source, budget: 10 }}
          fields={[{ name: ["source"], value: source }]}
          onValuesChange={(_, values) => setSource(values.source)}
          onFinish={review}
        >
          <Form.Item name="source" label="PR / MR 链接" rules={[{ required: true }]}>
            <Input.TextArea autoSize={{ minRows: 2, maxRows: 3 }} />
          </Form.Item>
          <div className="action-row">
            <Form.Item name="budget" label="预算（CNY）">
              <InputNumber min={0.01} precision={2} />
            </Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              disabled={!config?.ready || !supportedReviewUrl(source)}
            >
              开始评审
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
            打开变更页面
          </Button>
        )}
      </Card>

      <div className="summary-line">
        <Text type="secondary">模型</Text>
        <Text strong>{config?.model || "未配置"}</Text>
        <Text type="secondary">历史运行</Text>
        <Text strong>{runs.length}</Text>
      </div>

      <Divider titlePlacement="start">最近 Findings</Divider>
      {!detail?.findings.length ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无评审结果" />
      ) : (
        <List
          dataSource={detail.findings}
          split={false}
          renderItem={(finding: Finding) => (
            <List.Item>
              <Card className="finding-card" variant="borderless">
                <Space wrap size={4}>
                  <Tag color={finding.severity === "critical" ? "red" : finding.severity === "high" ? "volcano" : "gold"}>
                    {finding.severity}
                  </Tag>
                  <Tag color={finding.side === "LEFT" ? "magenta" : "blue"}>
                    {finding.side === "LEFT" ? "删除侧" : "新增侧"}
                  </Tag>
                  <Tag>{finding.category}</Tag>
                </Space>
                <Title level={5}>{finding.title}</Title>
                <Text type="secondary" className="location">
                  {finding.file_path}:{finding.side === "LEFT" ? finding.old_line : finding.new_line}
                </Text>
                <Paragraph ellipsis={{ rows: 3, expandable: true }}>{finding.explanation}</Paragraph>
                <Button type="link" size="small" onClick={async () => setTrace(await api.trace(finding.trace_id))}>
                  查看 Trace
                </Button>
              </Card>
            </List.Item>
          )}
        />
      )}

      <Modal title="Trace" open={Boolean(trace)} footer={null} onCancel={() => setTrace(null)} width={420}>
        <pre className="trace-view">{trace ? JSON.stringify(trace, null, 2) : ""}</pre>
      </Modal>
    </main>
  );
}

export default App;
