from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import typer

from bytecode_review_agent import __version__
from bytecode_review_agent.config import Settings
from bytecode_review_agent.errors import ConfigurationError, ReviewAgentError
from bytecode_review_agent.llm import OpenAICompatibleReviewer
from bytecode_review_agent.publisher import GitHubCommentPublisher
from bytecode_review_agent.providers import SourceLoader
from bytecode_review_agent.service import ReviewService
from bytecode_review_agent.storage import SQLiteStorage
from bytecode_review_agent.tools import default_registry

app = typer.Typer(
    no_args_is_help=True,
    help="Recoverable, traceable and budget-aware AI code review backend.",
)


def _decimal(value: str, label: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise typer.BadParameter(f"{label} must be a decimal number") from exc
    if parsed <= 0:
        raise typer.BadParameter(f"{label} must be greater than zero")
    return parsed


def _language(value: str) -> str:
    if value not in {"zh-CN", "en-US"}:
        raise typer.BadParameter("language must be zh-CN or en-US")
    return value


def _settings(
    data_dir: Path,
    model: Optional[str],
    base_url: Optional[str],
    input_price: Optional[str],
    output_price: Optional[str],
    allowed_hosts: list[str],
    env_file: Optional[Path],
) -> Settings:
    settings = Settings.from_env(data_dir=data_dir, env_file=env_file)
    changes: dict[str, object] = {}
    if model:
        changes["llm_model"] = model
    if base_url:
        changes["llm_base_url"] = base_url
    if input_price:
        changes["input_price_cny_per_million"] = _decimal(input_price, "input price")
    if output_price:
        changes["output_price_cny_per_million"] = _decimal(output_price, "output price")
    if allowed_hosts:
        changes["allowed_hosts"] = tuple(host.lower() for host in allowed_hosts)
    return settings.with_overrides(**changes) if changes else settings


def _service(settings: Settings) -> ReviewService:
    settings.validate_for_review()
    reviewer = OpenAICompatibleReviewer(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key or "",
        model=settings.llm_model or "",
        timeout_seconds=settings.request_timeout_seconds,
        thinking=settings.llm_thinking,
    )
    storage = SQLiteStorage(settings.database_path)
    return ReviewService(
        settings=settings,
        reviewer=reviewer,
        storage=storage,
        sources=SourceLoader(settings),
        tools=default_registry(),
    )


def _fail(exc: Exception) -> None:
    typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


@app.command()
def review(
    source: str = typer.Argument(..., help="PR/MR HTTPS URL, UTF-8 diff path, or '-' for stdin."),
    budget: str = typer.Option("10", "--budget", help="Maximum run cost in CNY."),
    output: Path = typer.Option(Path("review-report.md"), "--output", "-o"),
    data_dir: Path = typer.Option(Path(".review-agent"), "--data-dir"),
    model: Optional[str] = typer.Option(None, "--model"),
    base_url: Optional[str] = typer.Option(None, "--base-url"),
    input_price: Optional[str] = typer.Option(None, "--input-price", help="CNY per 1M tokens."),
    output_price: Optional[str] = typer.Option(None, "--output-price", help="CNY per 1M tokens."),
    allowed_host: Optional[list[str]] = typer.Option(None, "--allowed-host"),
    env_file: Optional[Path] = typer.Option(None, "--env-file", help="Local environment file."),
    language: str = typer.Option("zh-CN", "--language", help="zh-CN or en-US."),
) -> None:
    """Start a new review run and write a Markdown report."""
    try:
        settings = _settings(
            data_dir,
            model,
            base_url,
            input_price,
            output_price,
            allowed_host or [],
            env_file,
        )
        result = _service(settings).start(
            source,
            budget_cny=_decimal(budget, "budget"),
            output_path=output,
            output_language=_language(language),
        )
        typer.secho(f"Run: {result.run.id}", fg=typer.colors.GREEN)
        typer.echo(f"Status: {result.run.status.value}")
        typer.echo(f"Findings: {len(result.findings)}")
        typer.echo(f"Cost: {result.run.spent_cny}/{result.run.budget_cny} CNY")
        typer.echo(f"Report: {result.report_path}")
    except (ReviewAgentError, ValueError) as exc:
        _fail(exc)


@app.command()
def resume(
    run_id: str = typer.Argument(...),
    budget: Optional[str] = typer.Option(None, "--budget", help="Optional increased total budget."),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    data_dir: Path = typer.Option(Path(".review-agent"), "--data-dir"),
    model: Optional[str] = typer.Option(None, "--model"),
    base_url: Optional[str] = typer.Option(None, "--base-url"),
    input_price: Optional[str] = typer.Option(None, "--input-price"),
    output_price: Optional[str] = typer.Option(None, "--output-price"),
    env_file: Optional[Path] = typer.Option(None, "--env-file"),
) -> None:
    """Resume a failed or budget-exhausted run from its last completed chunk."""
    try:
        settings = _settings(
            data_dir,
            model,
            base_url,
            input_price,
            output_price,
            [],
            env_file,
        )
        report_path = output or Path(f"review-report-{run_id}.md")
        result = _service(settings).resume(
            run_id,
            budget_cny=_decimal(budget, "budget") if budget else None,
            output_path=report_path,
        )
        typer.secho(f"Status: {result.run.status.value}", fg=typer.colors.GREEN)
        typer.echo(f"Progress: {result.run.next_chunk_index}/{result.run.total_chunks}")
        typer.echo(f"Report: {result.report_path}")
    except (ReviewAgentError, ValueError) as exc:
        _fail(exc)


@app.command("trace")
def show_trace(
    trace_id: str = typer.Argument(...),
    data_dir: Path = typer.Option(Path(".review-agent"), "--data-dir"),
    include_content: bool = typer.Option(False, "--include-content"),
) -> None:
    """Inspect one trace and optionally its redacted prompt/model response."""
    try:
        storage = SQLiteStorage(Settings.from_env(data_dir=data_dir).database_path)
        trace = storage.get_trace(trace_id)
        if include_content:
            for key in ("prompt_path", "response_path"):
                path = Path(str(trace[key]))
                trace[f"{key}_content"] = path.read_text(encoding="utf-8")
        typer.echo(json.dumps(trace, ensure_ascii=False, indent=2, default=str))
    except (ReviewAgentError, OSError, ValueError) as exc:
        _fail(exc)


@app.command("runs")
def list_runs(
    data_dir: Path = typer.Option(Path(".review-agent"), "--data-dir"),
    limit: int = typer.Option(20, min=1, max=200),
) -> None:
    """List recent review runs."""
    storage = SQLiteStorage(Settings.from_env(data_dir=data_dir).database_path)
    for run in storage.list_runs(limit=limit):
        typer.echo(
            f"{run.id}\t{run.status.value}\t{run.next_chunk_index}/{run.total_chunks}"
            f"\t{run.spent_cny}/{run.budget_cny} CNY\t{run.source_ref}"
        )


@app.command("run")
def show_run(
    run_id: str = typer.Argument(...),
    data_dir: Path = typer.Option(Path(".review-agent"), "--data-dir"),
) -> None:
    """Inspect one run, including its checkpoints and successful or failed traces."""
    try:
        storage = SQLiteStorage(Settings.from_env(data_dir=data_dir).database_path)
        run = storage.get_run(run_id)
        payload = {
            "run": run.model_dump(mode="json"),
            "checkpoints": storage.list_checkpoints(run_id),
            "traces": storage.list_traces(run_id),
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    except (ReviewAgentError, OSError, ValueError) as exc:
        _fail(exc)


@app.command("publish")
def publish_run(
    run_id: str = typer.Argument(..., help="Completed GitHub review run ID."),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Create or update GitHub comments. Omit for a safe dry-run preview.",
    ),
    data_dir: Path = typer.Option(Path(".review-agent"), "--data-dir"),
    env_file: Optional[Path] = typer.Option(None, "--env-file"),
) -> None:
    """Preview or idempotently publish high-confidence findings to a GitHub PR."""
    publisher: GitHubCommentPublisher | None = None
    try:
        settings = Settings.from_env(data_dir=data_dir, env_file=env_file)
        storage = SQLiteStorage(settings.database_path)
        run = storage.get_run(run_id)
        publisher = GitHubCommentPublisher(settings)
        result = publisher.publish(run, storage.list_findings(run_id), apply=apply)
        typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
        if not apply:
            typer.secho(
                "Dry run only. Re-run with --apply to write GitHub comments.",
                fg=typer.colors.YELLOW,
            )
    except (ReviewAgentError, OSError, ValueError) as exc:
        _fail(exc)
    finally:
        if publisher is not None:
            publisher.close()


@app.command("tools")
def list_tools() -> None:
    """List built-in and installed declarative review tools."""
    for name in default_registry().names():
        typer.echo(name)


@app.command()
def doctor(
    env_file: Optional[Path] = typer.Option(None, "--env-file"),
    data_dir: Optional[Path] = typer.Option(None, "--data-dir"),
) -> None:
    """检查本地配置，但绝不输出 API Key 内容。"""
    try:
        settings = Settings.from_env(data_dir=data_dir, env_file=env_file)
        typer.echo(
            f"配置文件: {settings.env_file_path if settings.env_file_path else '未使用'}"
        )
        typer.echo(f"模型地址: {settings.llm_base_url}")
        typer.echo(f"模型名称: {settings.llm_model or '未配置'}")
        typer.echo(f"模型思考模式: {settings.llm_thinking or '由服务端决定'}")
        typer.echo(f"API Key: {'已配置' if settings.llm_api_key else '未配置'}")
        typer.echo(
            f"GitHub 发布 Token: {'已配置' if settings.github_token else '未配置'}"
        )
        typer.echo(f"单次最大发布评论数: {settings.max_publish_comments}")
        typer.echo(
            "输入价格: "
            f"{settings.input_price_cny_per_million} CNY / 1M tokens"
        )
        typer.echo(
            "输出价格: "
            f"{settings.output_price_cny_per_million} CNY / 1M tokens"
        )
        typer.echo(f"数据目录: {settings.data_dir.expanduser().resolve()}")
        settings.validate_for_review()
        typer.secho("配置状态: 可以执行评审", fg=typer.colors.GREEN)
    except (ConfigurationError, OSError, ValueError) as exc:
        typer.secho(f"配置状态: 未完成 - {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command()
def serve(
    port: int = typer.Option(8765, min=1024, max=65535),
    data_dir: Path = typer.Option(Path(".review-agent"), "--data-dir"),
    env_file: Optional[Path] = typer.Option(None, "--env-file"),
    open_page: bool = typer.Option(False, "--open", help="启动后打开本地页面。"),
) -> None:
    """启动仅监听本机回环地址的 API 与 Web 页面。"""
    import os
    import secrets
    import threading
    import webbrowser

    import uvicorn

    from bytecode_review_agent.api import create_app

    settings = Settings.from_env(data_dir=data_dir, env_file=env_file)
    session_token = os.getenv("REVIEW_AGENT_SESSION_TOKEN") or secrets.token_urlsafe(32)
    pairing_code = os.getenv("REVIEW_AGENT_PAIRING_CODE") or secrets.token_hex(4).upper()
    api = create_app(
        settings=settings,
        session_token=session_token,
        pairing_code=pairing_code,
    )
    url = f"http://127.0.0.1:{port}"
    typer.echo(f"Review Agent 本地服务: {url}")
    typer.echo(f"浏览器扩展配对码: {pairing_code}")
    if open_page:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(api, host="127.0.0.1", port=port, log_level="info")


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)
