from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from bytecode_review_agent.config import Settings
from bytecode_review_agent.errors import SourceError
from bytecode_review_agent.models import FileContext, SourceKind, SourceSnapshot
from bytecode_review_agent.utils import sha256_text


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
        headers = {"Accept": "application/vnd.github+json"}
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"
        endpoint = f"{api_base}/repos/{quote(owner)}/{quote(repository)}/pulls/{number}"
        metadata = self._get_json(endpoint, headers, "GitHub PR")
        diff_headers = {**headers, "Accept": "application/vnd.github.v3.diff"}
        diff = self._get_text(endpoint, diff_headers, "GitHub PR")
        contexts = self._load_github_contexts(
            api_base=api_base,
            owner=owner,
            repository=repository,
            number=number,
            base_sha=str(metadata["base"]["sha"]),
            head_sha=str(metadata["head"]["sha"]),
            headers=headers,
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
                "base_sha": str(metadata["base"]["sha"]),
                "head_sha": str(metadata["head"]["sha"]),
            },
            file_contexts=contexts,
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
        payload = self._get_json(endpoint, headers, "GitLab MR")
        try:
            changes = payload["changes"]
            diff_refs = payload.get("diff_refs") or {}
            base_sha = str(diff_refs.get("base_sha") or "") or None
            head_sha = str(diff_refs.get("head_sha") or "") or None
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(f"failed to parse GitLab MR: {exc}") from exc

        patches: list[str] = []
        contexts: list[FileContext] = []
        for change in changes:
            old_path = change["old_path"]
            new_path = change["new_path"]
            old_header = "/dev/null" if change.get("new_file") else f"a/{old_path}"
            new_header = "/dev/null" if change.get("deleted_file") else f"b/{new_path}"
            patches.append(
                f"diff --git a/{old_path} b/{new_path}\n"
                f"--- {old_header}\n+++ {new_header}\n{change.get('diff', '')}\n"
            )
            if len(contexts) < self.settings.max_context_files:
                base_content = None
                head_content = None
                if base_sha and not change.get("new_file"):
                    base_content = self._load_gitlab_file(
                        scheme=scheme,
                        host=host,
                        project=project,
                        file_path=old_path,
                        ref=base_sha,
                        headers=headers,
                    )
                if head_sha and not change.get("deleted_file"):
                    head_content = self._load_gitlab_file(
                        scheme=scheme,
                        host=host,
                        project=project,
                        file_path=new_path,
                        ref=head_sha,
                        headers=headers,
                    )
                contexts.append(
                    self._file_context(
                        old_path=old_path,
                        new_path=new_path,
                        status=(
                            "added"
                            if change.get("new_file")
                            else "deleted"
                            if change.get("deleted_file")
                            else "modified"
                        ),
                        base_sha=base_sha,
                        head_sha=head_sha,
                        base_content=base_content,
                        head_content=head_content,
                    )
                )
        diff = "".join(patches)
        self._validate_diff(diff)
        return SourceSnapshot(
            kind=SourceKind.GITLAB,
            reference=reference,
            provider="gitlab",
            diff=diff,
            metadata={
                "host": host,
                "project": project,
                "iid": int(iid),
                "base_sha": base_sha,
                "head_sha": head_sha,
            },
            file_contexts=contexts,
        )

    def _load_github_contexts(
        self,
        *,
        api_base: str,
        owner: str,
        repository: str,
        number: str,
        base_sha: str,
        head_sha: str,
        headers: dict[str, str],
    ) -> list[FileContext]:
        files_endpoint = (
            f"{api_base}/repos/{quote(owner)}/{quote(repository)}/pulls/{number}/files"
        )
        files: list[dict[str, object]] = []
        page = 1
        while len(files) < self.settings.max_context_files:
            response = self._get_json(
                files_endpoint,
                headers,
                "GitHub PR files",
                params={"per_page": 100, "page": page},
            )
            if not isinstance(response, list):
                raise SourceError("failed to parse GitHub PR files: expected a list")
            files.extend(response)
            if len(response) < 100:
                break
            page += 1

        contexts: list[FileContext] = []
        for item in files[: self.settings.max_context_files]:
            new_path = str(item["filename"])
            old_path = str(item.get("previous_filename") or new_path)
            status = str(item.get("status") or "modified")
            base_content = None
            head_content = None
            if status != "added":
                base_content = self._load_github_file(
                    api_base=api_base,
                    owner=owner,
                    repository=repository,
                    file_path=old_path,
                    ref=base_sha,
                    headers=headers,
                )
            if status != "removed":
                head_content = self._load_github_file(
                    api_base=api_base,
                    owner=owner,
                    repository=repository,
                    file_path=new_path,
                    ref=head_sha,
                    headers=headers,
                )
            contexts.append(
                self._file_context(
                    old_path=old_path,
                    new_path=new_path,
                    status=status,
                    base_sha=base_sha,
                    head_sha=head_sha,
                    base_content=base_content,
                    head_content=head_content,
                )
            )
        return contexts

    def _load_github_file(
        self,
        *,
        api_base: str,
        owner: str,
        repository: str,
        file_path: str,
        ref: str,
        headers: dict[str, str],
    ) -> str | None:
        endpoint = (
            f"{api_base}/repos/{quote(owner)}/{quote(repository)}/contents/"
            f"{quote(file_path, safe='/')}"
        )
        raw_headers = {**headers, "Accept": "application/vnd.github.raw+json"}
        try:
            content = self._get_text(
                endpoint,
                raw_headers,
                "GitHub file context",
                params={"ref": ref},
            )
        except SourceError:
            return None
        return self._safe_context(content)

    def _load_gitlab_file(
        self,
        *,
        scheme: str,
        host: str,
        project: str,
        file_path: str,
        ref: str,
        headers: dict[str, str],
    ) -> str | None:
        endpoint = (
            f"{scheme}://{host}/api/v4/projects/{quote(project, safe='')}"
            f"/repository/files/{quote(file_path, safe='')}/raw"
        )
        try:
            content = self._get_text(
                endpoint,
                headers,
                "GitLab file context",
                params={"ref": ref},
            )
        except SourceError:
            return None
        return self._safe_context(content)

    def _file_context(
        self,
        *,
        old_path: str,
        new_path: str,
        status: str,
        base_sha: str | None,
        head_sha: str | None,
        base_content: str | None,
        head_content: str | None,
    ) -> FileContext:
        canonical_path = old_path if status in {"removed", "deleted"} else new_path
        return FileContext(
            file_path=canonical_path,
            old_path=old_path,
            new_path=new_path,
            status=status,
            base_commit_sha=base_sha,
            head_commit_sha=head_sha,
            base_content=base_content,
            head_content=head_content,
            base_content_sha256=sha256_text(base_content) if base_content else None,
            head_content_sha256=sha256_text(head_content) if head_content else None,
        )

    def _safe_context(self, content: str) -> str | None:
        if "\x00" in content:
            return None
        if len(content.encode("utf-8")) > self.settings.max_context_file_bytes:
            return None
        return content

    def _get_text(
        self,
        endpoint: str,
        headers: dict[str, str],
        label: str,
        params: dict[str, object] | None = None,
    ) -> str:
        try:
            response = httpx.get(
                endpoint,
                headers=headers,
                params=params,
                timeout=self.settings.request_timeout_seconds,
            )
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            raise SourceError(f"failed to fetch {label}: {exc}") from exc

    def _get_json(
        self,
        endpoint: str,
        headers: dict[str, str],
        label: str,
        params: dict[str, object] | None = None,
    ) -> object:
        try:
            response = httpx.get(
                endpoint,
                headers=headers,
                params=params,
                timeout=self.settings.request_timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise SourceError(f"failed to fetch {label}: {exc}") from exc

    def _validate_diff(self, diff: str) -> None:
        if not diff.strip():
            raise SourceError("review source contains an empty diff")
        size = len(diff.encode("utf-8"))
        if size > self.settings.max_diff_bytes:
            raise SourceError(
                f"diff is {size} bytes, above configured limit {self.settings.max_diff_bytes}"
            )
