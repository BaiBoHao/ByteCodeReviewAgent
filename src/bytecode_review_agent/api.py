from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hmac import compare_digest
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from bytecode_review_agent import __version__
from bytecode_review_agent.config import Settings
from bytecode_review_agent.errors import ConfigurationError, RunNotFound
from bytecode_review_agent.llm import OpenAICompatibleReviewer
from bytecode_review_agent.providers import SourceLoader
from bytecode_review_agent.service import ReviewService
from bytecode_review_agent.storage import SQLiteStorage
from bytecode_review_agent.tools import default_registry


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ReviewCreateRequest(BaseModel):
    source: str = Field(min_length=1, max_length=2_048)
    budget_cny: Decimal = Field(default=Decimal("10"), gt=0)


class ReviewResumeRequest(BaseModel):
    budget_cny: Decimal | None = Field(default=None, gt=0)


@dataclass(slots=True)
class Job:
    id: str
    run_id: str
    operation: Literal["review", "resume"]
    status: Literal["queued", "running", "completed", "failed"]
    created_at: str
    updated_at: str
    error: str | None = None


ServiceFactory = Callable[[Settings, SQLiteStorage], ReviewService]


def _default_service(settings: Settings, storage: SQLiteStorage) -> ReviewService:
    settings.validate_for_review()
    reviewer = OpenAICompatibleReviewer(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key or "",
        model=settings.llm_model or "",
        timeout_seconds=settings.request_timeout_seconds,
    )
    return ReviewService(
        settings=settings,
        reviewer=reviewer,
        storage=storage,
        sources=SourceLoader(settings),
        tools=default_registry(),
    )


class JobManager:
    def __init__(
        self,
        *,
        settings: Settings,
        storage: SQLiteStorage,
        service_factory: ServiceFactory,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.service_factory = service_factory
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="review-agent")
        self._jobs: dict[str, Job] = {}
        self._lock = RLock()

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)

    def start_review(self, request: ReviewCreateRequest) -> Job:
        run_id = f"run_{uuid4().hex[:16]}"
        job = self._new_job(run_id=run_id, operation="review")
        self.executor.submit(self._review_worker, job.id, request)
        return job

    def resume_review(self, run_id: str, request: ReviewResumeRequest) -> Job:
        self.storage.get_run(run_id)
        job = self._new_job(run_id=run_id, operation="resume")
        self.executor.submit(self._resume_worker, job.id, request)
        return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return job

    def snapshot(self, job: Job) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": job.id,
            "run_id": job.run_id,
            "operation": job.operation,
            "status": job.status,
            "error": job.error,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }
        try:
            run = self.storage.get_run(job.run_id)
            payload["run"] = run.model_dump(mode="json")
        except RunNotFound:
            payload["run"] = None
        return payload

    def _new_job(self, *, run_id: str, operation: Literal["review", "resume"]) -> Job:
        timestamp = _now()
        job = Job(
            id=f"job_{uuid4().hex[:16]}",
            run_id=run_id,
            operation=operation,
            status="queued",
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def _set_status(
        self,
        job_id: str,
        status: Literal["running", "completed", "failed"],
        error: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = status
            job.error = error
            job.updated_at = _now()

    def _review_worker(self, job_id: str, request: ReviewCreateRequest) -> None:
        job = self.get(job_id)
        self._set_status(job_id, "running")
        try:
            service = self.service_factory(self.settings, self.storage)
            report_path = self.settings.data_dir / "reports" / f"{job.run_id}.md"
            service.start(
                request.source,
                budget_cny=request.budget_cny,
                output_path=report_path,
                run_id=job.run_id,
            )
        except Exception as exc:  # The job endpoint exposes the persisted failure safely.
            self._set_status(job_id, "failed", str(exc))
        else:
            self._set_status(job_id, "completed")

    def _resume_worker(self, job_id: str, request: ReviewResumeRequest) -> None:
        job = self.get(job_id)
        self._set_status(job_id, "running")
        try:
            service = self.service_factory(self.settings, self.storage)
            report_path = self.settings.data_dir / "reports" / f"{job.run_id}.md"
            service.resume(
                job.run_id,
                budget_cny=request.budget_cny,
                output_path=report_path,
            )
        except Exception as exc:
            self._set_status(job_id, "failed", str(exc))
        else:
            self._set_status(job_id, "completed")


def _default_static_dir() -> Path:
    return Path(__file__).resolve().parent / "web_dist"


def create_app(
    *,
    settings: Settings | None = None,
    service_factory: ServiceFactory = _default_service,
    static_dir: Path | None = None,
    session_token: str | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()
    storage = SQLiteStorage(active_settings.database_path)
    manager = JobManager(
        settings=active_settings,
        storage=storage,
        service_factory=service_factory,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        manager.close()

    app = FastAPI(
        title="ByteCodeReviewAgent Local API",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = active_settings
    app.state.storage = storage
    app.state.jobs = manager
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )

    @app.middleware("http")
    async def local_security(request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path.startswith("/api/") and path != "/api/bootstrap" and session_token:
            provided = request.headers.get("X-Review-Agent-Token") or request.cookies.get(
                "review_agent_session"
            )
            if not provided or not compare_digest(provided, session_token):
                return JSONResponse(status_code=401, content={"detail": "invalid session token"})

        origin = request.headers.get("Origin")
        if origin and request.method not in {"GET", "HEAD", "OPTIONS"}:
            allowed_origins = (
                "http://127.0.0.1:",
                "http://localhost:",
                "vscode-webview://",
            )
            if not origin.startswith(allowed_origins):
                return JSONResponse(status_code=403, content={"detail": "origin not allowed"})
        return await call_next(request)

    @app.get("/api/bootstrap")
    def bootstrap(response: Response) -> dict[str, object]:
        if session_token:
            response.set_cookie(
                "review_agent_session",
                session_token,
                httponly=True,
                samesite="strict",
                secure=False,
            )
        return {"status": "ok", "version": __version__}

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "version": __version__, "local_only": True}

    @app.get("/api/config")
    def config_status() -> dict[str, object]:
        try:
            active_settings.validate_for_review()
            ready = True
            error = None
        except ConfigurationError as exc:
            ready = False
            error = str(exc)
        return {
            "ready": ready,
            "error": error,
            "env_file": str(active_settings.env_file_path)
            if active_settings.env_file_path
            else None,
            "model": active_settings.llm_model,
            "base_url": active_settings.llm_base_url,
            "api_key_configured": bool(active_settings.llm_api_key),
            "input_price_cny_per_million": str(
                active_settings.input_price_cny_per_million
            ),
            "output_price_cny_per_million": str(
                active_settings.output_price_cny_per_million
            ),
            "data_dir": str(active_settings.data_dir.expanduser().resolve()),
        }

    @app.get("/api/tools")
    def tools() -> dict[str, list[str]]:
        return {"tools": default_registry().names()}

    @app.get("/api/runs")
    def runs(limit: int = Query(default=20, ge=1, le=200)) -> list[dict[str, object]]:
        return [
            {
                "run": run.model_dump(mode="json"),
                "finding_count": len(storage.list_findings(run.id)),
            }
            for run in storage.list_runs(limit=limit)
        ]

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, object]:
        try:
            run = storage.get_run(run_id)
        except RunNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "run": run.model_dump(mode="json"),
            "findings": [item.model_dump(mode="json") for item in storage.list_findings(run_id)],
            "checkpoints": storage.list_checkpoints(run_id),
            "traces": storage.list_traces(run_id),
        }

    @app.get("/api/traces/{trace_id}")
    def trace_detail(trace_id: str, include_content: bool = False) -> dict[str, object]:
        try:
            trace = storage.get_trace(trace_id)
        except RunNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if include_content:
            for key in ("prompt_path", "response_path"):
                path = Path(str(trace[key]))
                trace[f"{key}_content"] = path.read_text(encoding="utf-8")
        return trace

    @app.post("/api/reviews", status_code=202)
    def create_review(request: ReviewCreateRequest) -> dict[str, object]:
        try:
            active_settings.validate_for_review()
        except ConfigurationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        job = manager.start_review(request)
        return manager.snapshot(job)

    @app.post("/api/runs/{run_id}/resume", status_code=202)
    def resume_review(run_id: str, request: ReviewResumeRequest) -> dict[str, object]:
        try:
            active_settings.validate_for_review()
            job = manager.resume_review(run_id, request)
        except (ConfigurationError, RunNotFound, ValueError) as exc:
            status_code = 404 if isinstance(exc, RunNotFound) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        return manager.snapshot(job)

    @app.get("/api/jobs/{job_id}")
    def job_detail(job_id: str) -> dict[str, object]:
        try:
            job = manager.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        return manager.snapshot(job)

    resolved_static = (static_dir or _default_static_dir()).resolve()
    if resolved_static.is_dir() and (resolved_static / "index.html").is_file():
        assets_dir = resolved_static / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def web_app(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API route not found")
            return FileResponse(resolved_static / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def api_only_root() -> dict[str, str]:
            return {
                "message": "本地 API 已启动；请先在 web 目录执行 npm run build。"
            }

    return app
