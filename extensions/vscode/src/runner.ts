import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { createServer } from "node:net";
import * as path from "node:path";
import * as vscode from "vscode";
import { ReviewAgentApi } from "./api";

async function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

export class RunnerManager implements vscode.Disposable {
  private process: ChildProcessWithoutNullStreams | undefined;
  private apiClient: ReviewAgentApi | undefined;
  private port: number | undefined;
  private token: string | undefined;
  readonly output = vscode.window.createOutputChannel("Review Agent");

  constructor(private readonly context: vscode.ExtensionContext) {}

  async api(): Promise<ReviewAgentApi> {
    await this.ensureRunning();
    if (!this.apiClient) throw new Error("Runner 尚未就绪");
    return this.apiClient;
  }

  async dashboardUrl(): Promise<string> {
    await this.ensureRunning();
    return `http://127.0.0.1:${this.port}/#session=${encodeURIComponent(this.token || "")}`;
  }

  async ensureRunning(): Promise<void> {
    if (this.apiClient) {
      try {
        await this.apiClient.health();
        return;
      } catch {
        this.stopProcess();
      }
    }

    const configuration = vscode.workspace.getConfiguration("reviewAgent");
    const pythonPath = configuration.get<string>("pythonPath", "python");
    const configuredRunner = configuration.get<string>("runnerPath", "").trim();
    const bundledRunner = this.context.asAbsolutePath(
      path.join("runner", "review-agent-runner.exe"),
    );
    const runnerPath = configuredRunner || (existsSync(bundledRunner) ? bundledRunner : "");
    const envFile = configuration.get<string>("envFile", "").trim();
    const apiKey = await this.context.secrets.get("reviewAgent.llmApiKey");
    this.port = await freePort();
    this.token = randomBytes(32).toString("base64url");
    const dataDir = path.join(this.context.globalStorageUri.fsPath, "data");
    await vscode.workspace.fs.createDirectory(vscode.Uri.file(dataDir));

    const runnerArgs = [
      "serve",
      "--port",
      String(this.port),
      "--data-dir",
      dataDir,
    ];
    if (envFile) runnerArgs.push("--env-file", envFile);
    const executable = runnerPath || pythonPath;
    const args = runnerPath
      ? runnerArgs
      : ["-m", "bytecode_review_agent", ...runnerArgs];

    const environment = {
      ...process.env,
      REVIEW_AGENT_SESSION_TOKEN: this.token,
      ...(apiKey ? { REVIEW_AGENT_LLM_API_KEY: apiKey } : {}),
    };
    this.output.appendLine(`启动 Runner：${executable} ${args.join(" ")}`);
    this.process = spawn(executable, args, {
      cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
      env: environment,
      windowsHide: true,
    });
    this.process.stdout.on("data", (value) => this.output.append(value.toString()));
    this.process.stderr.on("data", (value) => this.output.append(value.toString()));
    this.process.once("exit", (code) => {
      this.output.appendLine(`Runner 已退出，代码：${code ?? "unknown"}`);
      this.apiClient = undefined;
      this.process = undefined;
    });

    const baseUrl = `http://127.0.0.1:${this.port}`;
    const api = new ReviewAgentApi(baseUrl, this.token);
    for (let attempt = 0; attempt < 40; attempt += 1) {
      try {
        await api.health();
        this.apiClient = api;
        return;
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
    }
    this.stopProcess();
    throw new Error("本地 Runner 启动超时，请检查 Review Agent 输出日志");
  }

  async restart(): Promise<void> {
    this.stopProcess();
    await this.ensureRunning();
  }

  dispose(): void {
    this.stopProcess();
    this.output.dispose();
  }

  private stopProcess(): void {
    if (this.process && !this.process.killed) this.process.kill();
    this.process = undefined;
    this.apiClient = undefined;
    this.port = undefined;
    this.token = undefined;
  }
}
