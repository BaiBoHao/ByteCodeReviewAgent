import { execFile } from "node:child_process";
import { promisify } from "node:util";
import * as path from "node:path";
import * as vscode from "vscode";
import { RunnerManager } from "./runner";
import { RunsTreeProvider } from "./tree";
import type { Finding, ReviewJob } from "./types";

const execFileAsync = promisify(execFile);

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const runner = new RunnerManager(context);
  const tree = new RunsTreeProvider(runner);
  context.subscriptions.push(runner);
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("reviewAgent.runs", tree),
  );

  const register = (command: string, callback: (...args: never[]) => unknown) =>
    context.subscriptions.push(vscode.commands.registerCommand(command, callback));

  register("reviewAgent.refresh", () => tree.refresh());
  register("reviewAgent.restartRunner", async () => {
    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: "正在重启 Review Agent Runner" },
      () => runner.restart(),
    );
    tree.refresh();
  });
  register("reviewAgent.setApiKey", async () => {
    const key = await vscode.window.showInputBox({
      prompt: "输入模型 API Key（仅保存到 VS Code SecretStorage）",
      password: true,
      ignoreFocusOut: true,
    });
    if (!key) return;
    await context.secrets.store("reviewAgent.llmApiKey", key);
    await runner.restart();
    tree.refresh();
    void vscode.window.showInformationMessage("API Key 已安全保存并重启 Runner");
  });
  register("reviewAgent.openDashboard", async () => openDashboard(runner));
  register("reviewAgent.reviewWorkingTree", async () => {
    await reviewGitDiff(context, runner, tree, ["diff", "--no-ext-diff", "--unified=3"]);
  });
  register("reviewAgent.reviewStaged", async () => {
    await reviewGitDiff(context, runner, tree, [
      "diff",
      "--cached",
      "--no-ext-diff",
      "--unified=3",
    ]);
  });
  register("reviewAgent.reviewPullRequest", async () => {
    const source = await vscode.window.showInputBox({
      prompt: "输入 GitHub PR 或 GitLab MR 链接",
      placeHolder: "https://github.com/org/repo/pull/123",
      ignoreFocusOut: true,
    });
    if (source) await submitReview(runner, tree, source);
  });
  register("reviewAgent.openFinding", async (finding: Finding) => {
    await openFinding(runner, finding);
  });

  void runner
    .ensureRunning()
    .then(() => tree.refresh())
    .catch((error: Error) => runner.output.appendLine(error.message));
}

export function deactivate(): void {}

async function reviewGitDiff(
  context: vscode.ExtensionContext,
  runner: RunnerManager,
  tree: RunsTreeProvider,
  gitArgs: string[],
): Promise<void> {
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
  if (!workspaceFolder) {
    void vscode.window.showWarningMessage("请先打开一个 Git 工作区");
    return;
  }
  try {
    const { stdout } = await execFileAsync("git", gitArgs, {
      cwd: workspaceFolder.uri.fsPath,
      maxBuffer: 10 * 1024 * 1024,
    });
    if (!stdout.trim()) {
      void vscode.window.showInformationMessage("当前范围没有可评审的 diff");
      return;
    }
    const reviewsDir = vscode.Uri.joinPath(context.globalStorageUri, "reviews");
    await vscode.workspace.fs.createDirectory(reviewsDir);
    const diffPath = vscode.Uri.joinPath(reviewsDir, `review-${Date.now()}.diff`);
    await vscode.workspace.fs.writeFile(diffPath, Buffer.from(stdout, "utf8"));
    await submitReview(runner, tree, diffPath.fsPath);
  } catch (error) {
    void vscode.window.showErrorMessage(`读取 Git diff 失败：${(error as Error).message}`);
  }
}

async function submitReview(
  runner: RunnerManager,
  tree: RunsTreeProvider,
  source: string,
): Promise<void> {
  const budget = vscode.workspace
    .getConfiguration("reviewAgent")
    .get<number>("defaultBudgetCny", 10);
  try {
    const job = await (await runner.api()).createReview(source, budget);
    await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "Review Agent 正在评审",
        cancellable: false,
      },
      async (progress) => pollJob(runner, job, progress),
    );
    tree.refresh();
  } catch (error) {
    void vscode.window.showErrorMessage(`评审失败：${(error as Error).message}`);
  }
}

async function pollJob(
  runner: RunnerManager,
  initial: ReviewJob,
  progress: vscode.Progress<{ message?: string; increment?: number }>,
): Promise<void> {
  let job = initial;
  while (job.status === "queued" || job.status === "running") {
    progress.report({ message: job.status === "queued" ? "等待执行" : "正在分析代码" });
    await new Promise((resolve) => setTimeout(resolve, 900));
    job = await (await runner.api()).job(job.id);
  }
  if (job.status === "failed") throw new Error(job.error || "评审任务失败");
  void vscode.window.showInformationMessage(`评审完成：${job.run_id}`);
}

async function openDashboard(runner: RunnerManager): Promise<void> {
  try {
    const url = await runner.dashboardUrl();
    const panel = vscode.window.createWebviewPanel(
      "reviewAgent.dashboard",
      "Review Agent",
      vscode.ViewColumn.One,
      { enableScripts: true, retainContextWhenHidden: true },
    );
    panel.webview.html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src ${url}; style-src 'unsafe-inline';">
<style>html,body,iframe{width:100%;height:100%;margin:0;border:0;overflow:hidden;background:#f5f7fb}</style>
</head><body><iframe src="${url}" title="Review Agent Dashboard"></iframe></body></html>`;
  } catch (error) {
    void vscode.window.showErrorMessage(`无法打开控制台：${(error as Error).message}`);
  }
}

async function openFinding(runner: RunnerManager, finding: Finding): Promise<void> {
  if (finding.side === "LEFT") {
    void vscode.window.showInformationMessage(
      "该问题位于删除侧，已打开控制台查看 base/head 证据。",
    );
    await openDashboard(runner);
    return;
  }
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
  if (!workspaceFolder) return;
  const uri = vscode.Uri.joinPath(workspaceFolder.uri, finding.file_path);
  try {
    const document = await vscode.workspace.openTextDocument(uri);
    const editor = await vscode.window.showTextDocument(document);
    const line = Math.max(0, (finding.new_line || finding.line) - 1);
    const selection = new vscode.Selection(line, 0, line, 0);
    editor.selection = selection;
    editor.revealRange(selection, vscode.TextEditorRevealType.InCenter);
  } catch (error) {
    void vscode.window.showErrorMessage(
      `无法打开 ${path.normalize(finding.file_path)}：${(error as Error).message}`,
    );
  }
}
