from __future__ import annotations

import re
from enum import StrEnum
from urllib.parse import quote, urlparse

import httpx
from pydantic import BaseModel, Field

from bytecode_review_agent.config import Settings
from bytecode_review_agent.errors import ConfigurationError, PublicationError
from bytecode_review_agent.models import (
    Confidence,
    DiffSide,
    Disposition,
    Finding,
    RunRecord,
    RunStatus,
    SourceKind,
)

GITHUB_API_VERSION = "2026-03-10"
_GITHUB_PULL = re.compile(r"^/([^/]+)/([^/]+)/pull/(\d+)(?:/.*)?$")
_MARKER_PATTERN = re.compile(
    r"<!--\s*bytecode-review-agent:finding:([a-f0-9]{64})\s*-->"
)
_MAX_COMMENT_BODY_CHARS = 60_000


class PublishAction(StrEnum):
    PREVIEW = "preview"
    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"


class PlannedComment(BaseModel):
    finding_id: str
    fingerprint: str
    path: str
    line: int = Field(ge=1)
    side: DiffSide
    title: str
    body: str
    action: PublishAction = PublishAction.PREVIEW
    remote_comment_id: int | None = None
    remote_url: str | None = None


class PublicationResult(BaseModel):
    provider: str = "github"
    source_ref: str
    dry_run: bool
    reviewed_head_sha: str
    eligible_count: int
    skipped_count: int
    created_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    comments: list[PlannedComment] = Field(default_factory=list)


class GitHubTarget(BaseModel):
    host: str
    owner: str
    repository: str
    number: int
    api_base: str


def _target_from_run(run: RunRecord, settings: Settings) -> GitHubTarget:
    if run.source_kind != SourceKind.GITHUB or run.provider != "github":
        raise PublicationError("only GitHub PR runs can be published by this command")
    parsed = urlparse(run.source_ref)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in settings.allowed_hosts:
        raise PublicationError("GitHub PR host is not safely allowlisted")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise PublicationError("GitHub PR URL contains unsupported credentials or parameters")
    match = _GITHUB_PULL.fullmatch(parsed.path)
    if not match:
        raise PublicationError("run source is not a recognised GitHub pull request URL")
    owner, repository, number = match.groups()
    api_base = "https://api.github.com" if host == "github.com" else f"https://{host}/api/v3"
    return GitHubTarget(
        host=host,
        owner=owner,
        repository=repository,
        number=int(number),
        api_base=api_base,
    )


def _reviewed_head_sha(run: RunRecord) -> str:
    source_metadata = run.config.get("source_metadata")
    if not isinstance(source_metadata, dict):
        raise PublicationError(
            "run predates publish metadata; review the PR again before publishing"
        )
    head_sha = source_metadata.get("head_sha")
    if not isinstance(head_sha, str) or not head_sha:
        raise PublicationError("reviewed GitHub head SHA is unavailable")
    return head_sha


def _marker(fingerprint: str) -> str:
    return f"<!-- bytecode-review-agent:finding:{fingerprint} -->"


def _comment_body(finding: Finding, output_language: str) -> str:
    suggestion_label = "Suggestion" if output_language == "en-US" else "建议"
    evidence_label = "Evidence" if output_language == "en-US" else "证据"
    sections = [
        f"**[{finding.severity.value.upper()}] {finding.title}**",
        finding.explanation,
    ]
    if finding.suggestion:
        sections.append(f"**{suggestion_label}**\n\n{finding.suggestion}")
    if finding.evidence:
        evidence = "\n".join(f"- {item}" for item in finding.evidence[:5])
        sections.append(f"**{evidence_label}**\n\n{evidence}")
    marker = _marker(finding.fingerprint)
    visible = "\n\n".join(sections)
    available = _MAX_COMMENT_BODY_CHARS - len(marker) - 4
    if len(visible) > available:
        visible = visible[: available - 1].rstrip() + "…"
    return f"{visible}\n\n{marker}"


def _eligible_comments(
    findings: list[Finding], max_comments: int, output_language: str
) -> tuple[list[PlannedComment], int]:
    eligible: list[PlannedComment] = []
    skipped = 0
    for finding in findings:
        line = finding.old_line if finding.side == DiffSide.LEFT else finding.new_line
        if (
            finding.effective_confidence != Confidence.HIGH
            or finding.disposition != Disposition.ACCEPT
            or line is None
        ):
            skipped += 1
            continue
        if len(eligible) >= max_comments:
            skipped += 1
            continue
        eligible.append(
            PlannedComment(
                finding_id=finding.id,
                fingerprint=finding.fingerprint,
                path=finding.file_path,
                line=line,
                side=finding.side,
                title=finding.title,
                body=_comment_body(finding, output_language),
            )
        )
    return eligible, skipped


class GitHubCommentPublisher:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.request_timeout_seconds)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def publish(
        self,
        run: RunRecord,
        findings: list[Finding],
        *,
        apply: bool = False,
    ) -> PublicationResult:
        if run.status != RunStatus.COMPLETED:
            raise PublicationError("only completed review runs can be published")
        target = _target_from_run(run, self.settings)
        reviewed_head_sha = _reviewed_head_sha(run)
        comments, skipped = _eligible_comments(
            findings,
            max(1, self.settings.max_publish_comments),
            str(run.config.get("output_language") or "zh-CN"),
        )
        result = PublicationResult(
            source_ref=run.source_ref,
            dry_run=not apply,
            reviewed_head_sha=reviewed_head_sha,
            eligible_count=len(comments),
            skipped_count=skipped,
            comments=comments,
        )
        if not apply:
            return result
        if not self.settings.github_token:
            raise ConfigurationError(
                "GITHUB_TOKEN with Pull requests: write permission is required for --apply"
            )

        endpoint = self._pull_endpoint(target)
        pull = self._request("GET", endpoint, label="GitHub pull request")
        current_head_sha = self._head_sha(pull)
        if current_head_sha != reviewed_head_sha:
            raise PublicationError(
                "pull request head changed after review; run a new review before publishing"
            )

        existing = self._existing_comments(target)
        published: list[PlannedComment] = []
        for comment in comments:
            previous = existing.get(comment.fingerprint)
            if previous is None:
                payload = {
                    "body": comment.body,
                    "commit_id": reviewed_head_sha,
                    "path": comment.path,
                    "line": comment.line,
                    "side": comment.side.value,
                }
                response = self._request(
                    "POST",
                    f"{endpoint}/comments",
                    label="GitHub review comment creation",
                    json=payload,
                )
                published.append(
                    comment.model_copy(
                        update={
                            "action": PublishAction.CREATE,
                            "remote_comment_id": self._comment_id(response),
                            "remote_url": self._optional_string(response, "html_url"),
                        }
                    )
                )
                result.created_count += 1
                continue

            comment_id = self._comment_id(previous)
            remote_url = self._optional_string(previous, "html_url")
            if str(previous.get("body") or "") == comment.body:
                published.append(
                    comment.model_copy(
                        update={
                            "action": PublishAction.UNCHANGED,
                            "remote_comment_id": comment_id,
                            "remote_url": remote_url,
                        }
                    )
                )
                result.unchanged_count += 1
                continue

            response = self._request(
                "PATCH",
                f"{target.api_base}/repos/{quote(target.owner)}/{quote(target.repository)}"
                f"/pulls/comments/{comment_id}",
                label="GitHub review comment update",
                json={"body": comment.body},
            )
            published.append(
                comment.model_copy(
                    update={
                        "action": PublishAction.UPDATE,
                        "remote_comment_id": comment_id,
                        "remote_url": self._optional_string(response, "html_url") or remote_url,
                    }
                )
            )
            result.updated_count += 1

        result.comments = published
        return result

    def _pull_endpoint(self, target: GitHubTarget) -> str:
        return (
            f"{target.api_base}/repos/{quote(target.owner)}/{quote(target.repository)}"
            f"/pulls/{target.number}"
        )

    def _existing_comments(self, target: GitHubTarget) -> dict[str, dict[str, object]]:
        endpoint = f"{self._pull_endpoint(target)}/comments"
        found: dict[str, dict[str, object]] = {}
        page = 1
        while True:
            response = self._request(
                "GET",
                endpoint,
                label="GitHub review comments",
                params={"per_page": 100, "page": page},
            )
            if not isinstance(response, list):
                raise PublicationError("GitHub review comments response is not a list")
            for item in response:
                if not isinstance(item, dict):
                    continue
                match = _MARKER_PATTERN.search(str(item.get("body") or ""))
                if match:
                    found[match.group(1)] = item
            if len(response) < 100:
                return found
            page += 1

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"
        return headers

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        label: str,
        params: dict[str, object] | None = None,
        json: dict[str, object] | None = None,
    ) -> object:
        try:
            response = self.client.request(
                method,
                endpoint,
                headers=self._headers(),
                params=params,
                json=json,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise PublicationError(f"{label} failed: {exc}") from exc

    @staticmethod
    def _head_sha(payload: object) -> str:
        try:
            if not isinstance(payload, dict):
                raise TypeError
            head = payload["head"]
            if not isinstance(head, dict):
                raise TypeError
            sha = head["sha"]
            if not isinstance(sha, str) or not sha:
                raise TypeError
            return sha
        except (KeyError, TypeError) as exc:
            raise PublicationError("GitHub pull request response has no head SHA") from exc

    @staticmethod
    def _comment_id(payload: object) -> int:
        if not isinstance(payload, dict) or not isinstance(payload.get("id"), int):
            raise PublicationError("GitHub review comment response has no integer ID")
        return int(payload["id"])

    @staticmethod
    def _optional_string(payload: object, key: str) -> str | None:
        if not isinstance(payload, dict):
            return None
        value = payload.get(key)
        return value if isinstance(value, str) else None
