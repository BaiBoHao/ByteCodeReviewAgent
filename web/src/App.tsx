import {
  ApiOutlined,
  ArrowRightOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  CodeOutlined,
  FileSearchOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App as AntApp,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Layout,
  List,
  Modal,
  Progress,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type {
  ConfigStatus,
  Finding,
  ReviewJob,
  RunDetail,
  RunListItem,
  RunRecord,
} from "./types";

const { Header, Content } = Layout;
const { Title, Paragraph, Text } = Typography;

const severityMeta: Record<
  Finding["severity"],
  { label: string; color: string }
> = {
  critical: { label: "严重", color: "red" },
  high: { label: "高", color: "volcano" },
  medium: { label: "中", color: "gold" },
  low: { label: "低", color: "blue" },
};

const statusMeta: Record<RunRecord["status"], { label: string; color: string }> = {
  pending: { label: "等待中", color: "default" },
  running: { label: "分析中", color: "processing" },
  completed: { label: "已完成", color: "success" },
  budget_exhausted: { label: "预算已用尽", color: "warning" },
  failed: { label: "失败", color: "error" },
};

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function App() {
  return (
    <AntApp>
      <ReviewDashboard />
    </AntApp>
  );
}

function ReviewDashboard() {
  const { message } = AntApp.useApp();
  const [form] = Form.useForm();
  const [health, setHealth] = useState<{ version: string } | null>(null);
  const [config, setConfig] = useState<ConfigStatus | null>(null);
  const [tools, setTools] = useState<string[]>([]);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [job, setJob] = useState<ReviewJob | null>(null);
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null);
  const [traceOpen, setTraceOpen] = useState(false);
  const [loadingRun, setLoadingRun] = useState(false);

  const refresh = useCallback(async () => {
    const [healthValue, configValue, toolsValue, runValues] = await Promise.all([
      api.health(),
      api.config(),
      api.tools(),
      api.runs(),
    ]);
    setHealth(healthValue);
    setConfig(configValue);
    setTools(toolsValue.tools);
    setRuns(runValues);
  }, []);

  useEffect(() => {
    refresh().catch((error: Error) => message.error(error.message));
  }, [message, refresh]);

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api.job(job.id);
        setJob(next);
        if (next.status === "completed") {
          window.clearInterval(timer);
          message.success("评审已完成");
          await refresh();
          await openRun(next.run_id);
        } else if (next.status === "failed") {
          window.clearInterval(timer);
          message.error(next.error || "评审失败");
          await refresh();
        }
      } catch (error) {
        window.clearInterval(timer);
        message.error((error as Error).message);
      }
    }, 900);
    return () => window.clearInterval(timer);
  }, [job, message, refresh]);

  const openRun = async (runId: string) => {
    setLoadingRun(true);
    try {
      setSelectedRun(await api.run(runId));
      setDrawerOpen(true);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setLoadingRun(false);
    }
  };

  const openTrace = async (traceId: string) => {
    try {
      setTrace(await api.trace(traceId));
      setTraceOpen(true);
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  const submitReview = async (values: { source: string; budget: number }) => {
    try {
      const created = await api.createReview(values.source.trim(), values.budget);
      setJob(created);
      message.success("评审任务已进入后台");
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  const summary = useMemo(() => {
    const completed = runs.filter((item) => item.run.status === "completed").length;
    const findings = runs.reduce((total, item) => total + item.finding_count, 0);
    const cost = runs.reduce((total, item) => total + Number(item.run.spent_cny), 0);
    return { completed, findings, cost };
  }, [runs]);

  const jobProgress = job?.run
    ? Math.round((job.run.next_chunk_index / Math.max(job.run.total_chunks, 1)) * 100)
    : job?.status === "running"
      ? 12
      : 0;

  const columns: ColumnsType<RunListItem> = [
    {
      title: "状态",
      width: 108,
      render: (_, item) => {
        const meta = statusMeta[item.run.status];
        return <Badge status={meta.color as never} text={meta.label} />;
      },
    },
    {
      title: "评审来源",
      dataIndex: ["run", "source_ref"],
      ellipsis: true,
      render: (value: string, item) => (
        <Space direction="vertical" size={1}>
          <Text strong ellipsis={{ tooltip: value }} className="source-text">
            {value}
          </Text>
          <Text type="secondary" className="mono-small">
            {item.run.id}
          </Text>
        </Space>
      ),
    },
    {
      title: "问题",
      dataIndex: "finding_count",
      width: 80,
      align: "center",
      render: (value: number) => <Text strong>{value}</Text>,
    },
    {
      title: "费用",
      width: 116,
      render: (_, item) => `${item.run.spent_cny} CNY`,
    },
    {
      title: "更新时间",
      width: 128,
      render: (_, item) => formatTime(item.run.updated_at),
    },
    {
      title: "",
      width: 72,
      render: (_, item) => (
        <Button type="text" onClick={() => openRun(item.run.id)}>
          查看
        </Button>
      ),
    },
  ];

  return (
    <Layout className="app-shell">
      <Header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <CodeOutlined />
          </div>
          <div>
            <div className="brand-name">Review Agent</div>
            <div className="brand-subtitle">本地优先的 AI 代码评审</div>
          </div>
        </div>
        <Space size={18}>
          <Tooltip title="后端仅监听本机回环地址">
            <Tag bordered={false} color="green" icon={<SafetyCertificateOutlined />}>
              本地服务
            </Tag>
          </Tooltip>
          <Text type="secondary">v{health?.version || "--"}</Text>
        </Space>
      </Header>

      <Content className="page-content">
        <section className="hero-panel">
          <div className="hero-copy">
            <Tag bordered={false} className="eyebrow-tag">
              可恢复 · 可追踪 · 可控制预算
            </Tag>
            <Title level={1}>让每一次代码评审，都有证据可循</Title>
            <Paragraph>
              从本地 diff 到 GitHub PR，在发送模型前完成脱敏，并为每条结论保留完整 Trace。
            </Paragraph>
            <Space wrap size={8}>
              {tools.map((tool) => (
                <Tag key={tool} className="tool-tag">
                  {tool}
                </Tag>
              ))}
            </Space>
          </div>
          <div className="hero-orbit" aria-hidden="true">
            <div className="orbit-core">
              <FileSearchOutlined />
            </div>
            <div className="orbit-chip chip-one">Trace</div>
            <div className="orbit-chip chip-two">Budget</div>
            <div className="orbit-chip chip-three">Resume</div>
          </div>
        </section>

        {!config?.ready && (
          <Alert
            className="config-alert"
            type="warning"
            showIcon
            message="模型配置尚未完成"
            description={config?.error || "请复制 .env.example 为 .env，并运行 review-agent doctor。"}
          />
        )}

        <Row gutter={[20, 20]}>
          <Col xs={24} xl={15}>
            <Card className="review-card" bordered={false}>
              <div className="section-heading">
                <div>
                  <Text className="section-kicker">NEW REVIEW</Text>
                  <Title level={3}>开始一次评审</Title>
                </div>
                <ThunderboltOutlined className="section-icon" />
              </div>
              <Form
                form={form}
                layout="vertical"
                initialValues={{
                  source: "https://github.com/BaiBoHao/ReviewProjectTest/pull/1",
                  budget: 10,
                }}
                onFinish={submitReview}
              >
                <Form.Item
                  name="source"
                  label="评审来源"
                  rules={[{ required: true, message: "请输入 diff 路径或 PR/MR 链接" }]}
                >
                  <Input.TextArea
                    autoSize={{ minRows: 2, maxRows: 4 }}
                    placeholder="本地 diff 路径、GitHub PR 或 GitLab MR 链接"
                  />
                </Form.Item>
                <div className="review-actions">
                  <Form.Item name="budget" label="最高预算（CNY）" className="budget-field">
                    <InputNumber min={0.01} precision={2} step={1} />
                  </Form.Item>
                  <Button
                    htmlType="submit"
                    type="primary"
                    size="large"
                    icon={<ArrowRightOutlined />}
                    disabled={!config?.ready || ["queued", "running"].includes(job?.status || "")}
                  >
                    开始评审
                  </Button>
                </div>
              </Form>

              {job && (
                <div className="job-progress">
                  <div className="job-progress-head">
                    <Space>
                      <ClockCircleOutlined />
                      <Text strong>
                        {job.status === "completed"
                          ? "评审完成"
                          : job.status === "failed"
                            ? "评审失败"
                            : "正在分析代码"}
                      </Text>
                    </Space>
                    <Text type="secondary">{job.run_id}</Text>
                  </div>
                  <Progress
                    percent={job.status === "completed" ? 100 : jobProgress}
                    status={job.status === "failed" ? "exception" : "active"}
                    strokeColor={{ from: "#3157d5", to: "#6e7ff1" }}
                  />
                </div>
              )}
            </Card>
          </Col>

          <Col xs={24} xl={9}>
            <Card className="config-card" bordered={false}>
              <div className="section-heading compact">
                <div>
                  <Text className="section-kicker">RUNTIME</Text>
                  <Title level={3}>运行环境</Title>
                </div>
                <ApiOutlined className="section-icon" />
              </div>
              <Descriptions column={1} size="small" colon={false}>
                <Descriptions.Item label="配置状态">
                  {config?.ready ? (
                    <Tag color="success" bordered={false} icon={<CheckCircleFilled />}>
                      可以评审
                    </Tag>
                  ) : (
                    <Tag color="warning" bordered={false}>
                      待配置
                    </Tag>
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="模型">
                  <Text strong>{config?.model || "未配置"}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="API Key">
                  {config?.api_key_configured ? "已安全配置" : "未配置"}
                </Descriptions.Item>
                <Descriptions.Item label="数据目录">
                  <Text ellipsis={{ tooltip: config?.data_dir }} className="config-path">
                    {config?.data_dir || "--"}
                  </Text>
                </Descriptions.Item>
              </Descriptions>
              <Button icon={<ReloadOutlined />} onClick={() => refresh()} block>
                刷新状态
              </Button>
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]} className="stats-row">
          <Col xs={12} md={6}>
            <Card bordered={false} className="stat-card">
              <Statistic title="历史运行" value={runs.length} />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card bordered={false} className="stat-card">
              <Statistic title="成功完成" value={summary.completed} />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card bordered={false} className="stat-card">
              <Statistic title="累计问题" value={summary.findings} />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card bordered={false} className="stat-card">
              <Statistic title="记录费用" value={summary.cost} precision={4} suffix="CNY" />
            </Card>
          </Col>
        </Row>

        <Card className="runs-card" bordered={false}>
          <div className="section-heading table-heading">
            <div>
              <Text className="section-kicker">HISTORY</Text>
              <Title level={3}>最近评审</Title>
            </div>
            <Button type="text" icon={<ReloadOutlined />} onClick={() => refresh()}>
              刷新
            </Button>
          </div>
          <Table
            rowKey={(item) => item.run.id}
            columns={columns}
            dataSource={runs}
            loading={loadingRun}
            pagination={{ pageSize: 8, hideOnSinglePage: true }}
            locale={{ emptyText: <Empty description="还没有评审记录" /> }}
            scroll={{ x: 760 }}
          />
        </Card>
      </Content>

      <RunDrawer
        detail={selectedRun}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onTrace={openTrace}
      />
      <Modal
        title="Trace 证据链"
        open={traceOpen}
        onCancel={() => setTraceOpen(false)}
        footer={null}
        width={760}
      >
        <pre className="trace-json">{trace ? JSON.stringify(trace, null, 2) : ""}</pre>
      </Modal>
    </Layout>
  );
}

function RunDrawer({
  detail,
  open,
  onClose,
  onTrace,
}: {
  detail: RunDetail | null;
  open: boolean;
  onClose: () => void;
  onTrace: (traceId: string) => void;
}) {
  const accepted = detail?.findings.filter((item) => item.disposition === "accept") || [];
  const references = detail?.findings.filter((item) => item.disposition === "reference") || [];
  return (
    <Drawer
      title="评审详情"
      width={720}
      open={open}
      onClose={onClose}
      destroyOnHidden
      extra={
        detail && (
          <Tag color={statusMeta[detail.run.status].color}>
            {statusMeta[detail.run.status].label}
          </Tag>
        )
      }
    >
      {!detail ? (
        <Empty />
      ) : (
        <Space direction="vertical" size={24} className="drawer-content">
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="运行 ID" span={2}>
              <Text copyable className="mono-small">
                {detail.run.id}
              </Text>
            </Descriptions.Item>
            <Descriptions.Item label="进度">
              {detail.run.next_chunk_index}/{detail.run.total_chunks}
            </Descriptions.Item>
            <Descriptions.Item label="费用">
              {detail.run.spent_cny} / {detail.run.budget_cny} CNY
            </Descriptions.Item>
            <Descriptions.Item label="上下文文件">
              {String(detail.run.config.context_file_count ?? 0)}
            </Descriptions.Item>
            <Descriptions.Item label="上下文上限">
              {String(detail.run.config.max_context_chars ?? "--")} 字符
            </Descriptions.Item>
            <Descriptions.Item label="来源" span={2}>
              {detail.run.source_ref}
            </Descriptions.Item>
          </Descriptions>

          <FindingSection title="高置信度问题" findings={accepted} onTrace={onTrace} />
          <FindingSection title="仅供参考" findings={references} onTrace={onTrace} />
        </Space>
      )}
    </Drawer>
  );
}

function FindingSection({
  title,
  findings,
  onTrace,
}: {
  title: string;
  findings: Finding[];
  onTrace: (traceId: string) => void;
}) {
  return (
    <section className="finding-section">
      <div className="finding-title-row">
        <Title level={4}>{title}</Title>
        <Badge count={findings.length} showZero color="#3157d5" />
      </div>
      {findings.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有问题" />
      ) : (
        <List
          dataSource={findings}
          split={false}
          renderItem={(finding) => (
            <List.Item className="finding-item">
              <div className="finding-card">
                <div className="finding-meta">
                  <Space wrap>
                    <Tag color={severityMeta[finding.severity].color}>
                      {severityMeta[finding.severity].label}
                    </Tag>
                    <Tag>{finding.category}</Tag>
                    <Tag color={finding.side === "LEFT" ? "magenta" : "blue"}>
                      {finding.side === "LEFT" ? "删除侧" : "新增侧"}
                    </Tag>
                    <Text type="secondary">
                      {finding.file_path}:
                      {finding.side === "LEFT" ? finding.old_line : finding.new_line}
                    </Text>
                  </Space>
                  <Button size="small" type="link" onClick={() => onTrace(finding.trace_id)}>
                    查看 Trace
                  </Button>
                </div>
                <Title level={5}>{finding.title}</Title>
                <Paragraph>{finding.explanation}</Paragraph>
                {finding.suggestion && (
                  <div className="suggestion">
                    <Text strong>建议：</Text> {finding.suggestion}
                  </div>
                )}
              </div>
            </List.Item>
          )}
        />
      )}
    </section>
  );
}

export default App;
