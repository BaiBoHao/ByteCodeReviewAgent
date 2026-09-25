import * as vscode from "vscode";
import { RunnerManager } from "./runner";

export const CONTEXT_SCHEME = "review-agent-context";

export class ReviewContextProvider implements vscode.TextDocumentContentProvider {
  constructor(private readonly runner: RunnerManager) {}

  async provideTextDocumentContent(uri: vscode.Uri): Promise<string> {
    const params = new URLSearchParams(uri.query);
    const runId = params.get("run");
    const side = params.get("side");
    const filePath = uri.path.replace(/^\//, "");
    if (!runId || (side !== "base" && side !== "head") || !filePath) {
      throw new Error("无效的 Review Agent 上下文 URI");
    }
    const result = await (await this.runner.api()).context(runId, filePath, side);
    return result.content;
  }
}

export function contextUri(
  runId: string,
  filePath: string,
  side: "base" | "head",
): vscode.Uri {
  return vscode.Uri.from({
    scheme: CONTEXT_SCHEME,
    path: `/${filePath.replace(/\\/g, "/")}`,
    query: new URLSearchParams({ run: runId, side }).toString(),
  });
}
