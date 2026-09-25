import * as path from "node:path";
import * as vscode from "vscode";
import { RunnerManager } from "./runner";
import type { Finding, RunListItem } from "./types";

type TreeNode = RunNode | FindingNode | StatusNode;

class StatusNode {
  readonly kind = "status";
  constructor(readonly label: string, readonly description?: string) {}
}

class RunNode {
  readonly kind = "run";
  constructor(readonly item: RunListItem) {}
}

class FindingNode {
  readonly kind = "finding";
  constructor(readonly runId: string, readonly finding: Finding) {}
}

export class RunsTreeProvider implements vscode.TreeDataProvider<TreeNode> {
  private readonly changed = new vscode.EventEmitter<TreeNode | undefined>();
  readonly onDidChangeTreeData = this.changed.event;

  constructor(private readonly runner: RunnerManager) {}

  refresh(): void {
    this.changed.fire(undefined);
  }

  getTreeItem(element: TreeNode): vscode.TreeItem {
    if (element.kind === "status") {
      const item = new vscode.TreeItem(element.label);
      item.description = element.description;
      item.iconPath = new vscode.ThemeIcon("info");
      return item;
    }
    if (element.kind === "run") {
      const run = element.item.run;
      const item = new vscode.TreeItem(
        path.basename(run.source_ref) || run.source_ref,
        element.item.finding_count
          ? vscode.TreeItemCollapsibleState.Collapsed
          : vscode.TreeItemCollapsibleState.None,
      );
      item.description = `${run.status} · ${element.item.finding_count} 个问题`;
      item.tooltip = `${run.source_ref}\n${run.id}`;
      item.iconPath = new vscode.ThemeIcon(
        run.status === "completed" ? "pass-filled" : run.status === "failed" ? "error" : "sync~spin",
      );
      item.command = {
        command: "reviewAgent.openDashboard",
        title: "打开控制台",
      };
      return item;
    }

    const finding = element.finding;
    const item = new vscode.TreeItem(finding.title);
    const side = finding.side === "LEFT" ? "删除侧" : "新增侧";
    item.description = `${finding.severity} · ${side}`;
    item.tooltip = `${finding.file_path}:${finding.line}\n${finding.trace_id}`;
    item.iconPath = new vscode.ThemeIcon(
      finding.severity === "critical" || finding.severity === "high" ? "warning" : "info",
    );
    item.command = {
      command: "reviewAgent.openFinding",
      title: "打开 Finding",
      arguments: [element.runId, finding],
    };
    return item;
  }

  async getChildren(element?: TreeNode): Promise<TreeNode[]> {
    try {
      const api = await this.runner.api();
      if (!element) {
        const runs = await api.runs();
        return runs.length
          ? runs.map((item) => new RunNode(item))
          : [new StatusNode("还没有评审记录", "请从命令面板发起评审")];
      }
      if (element.kind === "run") {
        const detail = await api.run(element.item.run.id);
        return detail.findings.map(
          (finding) => new FindingNode(element.item.run.id, finding),
        );
      }
      return [];
    } catch (error) {
      return [new StatusNode("Runner 不可用", (error as Error).message)];
    }
  }
}
