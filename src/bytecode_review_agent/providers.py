from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from bytecode_review_agent.config import Settings
from bytecode_review_agent.errors import SourceError
from bytecode_review_agent.models import SourceKind, SourceSnapshot


_GITHUB_PULL = re.compile(r"^/([^/]+)/([^/]+)/pull/(\d+)(?:/.*)?$")
_GITLAB_MERGE = re.compile(r"^/(.+)/-/merge_requests/(\d+)(?:/.*)?$")


class SourceLoader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def load(self, source: str, stdin_text: str | None = None) -> SourceSnapshot:
        if source == "-":
            content = stdin_text if stdin_text is not None else sys.stdin.read()
            return self._local_snapshot("stdin", content)
        if source.startswith("https://") or source.startswith("http://"):
            return self._load_url(source)
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise SourceError(f"diff file does not exist: {path}")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise SourceError("diff file must be UTF-8 text") from exc
        return self._local_snapshot(str(path), content)

    def _local_snapshot(self, reference: str, content: str) -> SourceSnapshot:
        self._validate_diff(content)
        return SourceSnapshot(
            kind=SourceKind.DIFF,
            reference=reference,
            provider="local",
            diff=content,
        )

    def _load_url(self, value: str) -> SourceSnapshot:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https":
            raise SourceError("only HTTPS PR/MR URLs are accepted")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise SourceError("source URLs cannot contain credentials, query strings, or fragments")
        if host not in self.settings.allowed_hosts:
            raise SourceError(
                f"source host {host!r} is not allowlisted; configure REVIEW_AGENT_ALLOWED_HOSTS"
            )

        github = _GITHUB_PULL.match(parsed.path)
        if github:
            return self._load_github(value, host, *github.groups())
        gitlab = _GITLAB_MERGE.match(parsed.path)
        if gitlab:
            return self._load_gitlab(value, parsed.scheme, host, *gitlab.groups())
        raise SourceError("URL is not a recognised GitHub PR or GitLab MR")

    def _load_github(
        self, reference: str, host: str, owner: str, repository: str, number: str
    ) -> SourceSnapshot:
        api_base = "https://api.github.com" if host == "github.com" else f"https://{host}/api/v3"
        headers = {"Accept": "application/vnd.github.v3.diff"}
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"
        diff = self._get_text(
            f"{api_base}/repos/{quote(owner)}/{quote(repository)}/pulls/{number}", headers
        )
        self._validate_diff(diff)
        return SourceSnapshot(
            kind=SourceKind.GITHUB,
            reference=reference,
            provider="github",
            diff=diff,
            metadata={
                "host": host,
                "owner": owner,
                "repository": repository,
                "number": int(number),
            },
        )

    def _load_gitlab(
        self, reference: str, scheme: str, host: str, project: str, iid: str
    ) -> SourceSnapshot:
        headers: dict[str, str] = {}
        if self.settings.gitlab_token:
            headers["PRIVATE-TOKEN"] = self.settings.gitlab_token
        endpoint = (
            f"{scheme}://{host}/api/v4/projects/{quote(project, safe='')}"
            f"/merge_requests/{iid}/changes"
        )
        try:
            response = httpx.get(
                endpoint, headers=headers, timeout=self.settings.request_timeout_seconds
            )
            response.raise_for_status()
            changes = response.json()["changes"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise SourceError(f"failed to fetch GitLab MR: {exc}") from exc

        patches: list[str] = []
        for change in changes:
            old_path = change["old_path"]
            new_path = change["new_path"]
            old_header = "/dev/null" if change.get("new_file") else f"a/{old_path}"
            new_header = "/dev/null" if change.get("deleted_file") else f"b/{new_path}"
            patches.append(
                f"diff --git a/{old_path} b/{new_path}\n"
                f"--- {old_header}\n+++ {new_header}\n{change.get('diff', '')}\n"
            )
        diff = "".join(patches)
        self._validate_diff(diff)
        return SourceSnapshot(
            kind=SourceKind.GITLAB,
            reference=reference,
            provider="gitlab",
            diff=diff,
            metadata={"host": host, "project": project, "iid": int(iid)},
        )

    def _get_text(self, endpoint: str, headers: dict[str, str]) -> str:
        try:
            response = httpx.get(
                endpoint, headers=headers, timeout=self.settings.request_timeout_seconds
            )
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            raise SourceError(f"failed to fetch GitHub PR: {exc}") from exc

    def _validate_diff(self, diff: str) -> None:
        if not diff.strip():
            raise SourceError("review source contains an empty diff")
        size = len(diff.encode("utf-8"))
        if size > self.settings.max_diff_bytes:
            raise SourceError(
                f"diff is {size} bytes, above configured limit {self.settings.max_diff_bytes}"
            )
