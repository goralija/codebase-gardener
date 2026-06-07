from __future__ import annotations

from base64 import b64decode, b64encode
from datetime import UTC, datetime, timedelta
from time import sleep
from typing import Any
from urllib.parse import quote

import httpx
import jwt
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class GitHubAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class GitHubAppClient:
    def __init__(
        self,
        *,
        api_base_url: str | None = None,
        web_base_url: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.25,
    ):
        self.api_base_url = (api_base_url or settings.GITHUB_API_BASE_URL).rstrip("/")
        self.web_base_url = (web_base_url or settings.GITHUB_WEB_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    def exchange_oauth_code(self, code: str) -> str:
        payload = self._json_request(
            "POST",
            self._web_url("/login/oauth/access_token"),
            data={
                "client_id": self._required_setting("GITHUB_APP_CLIENT_ID"),
                "client_secret": self._required_setting("GITHUB_APP_CLIENT_SECRET"),
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise GitHubAPIError("GitHub OAuth response did not include an access token.")
        return access_token

    def get_authenticated_user(self, user_token: str) -> dict[str, Any]:
        return self._api_request("GET", "/user", token=user_token)

    def list_user_installation_repositories(
        self,
        user_token: str,
        installation_id: int,
    ) -> list[dict[str, Any]]:
        return self._paginate_repositories(
            f"/user/installations/{installation_id}/repositories",
            token=user_token,
        )

    def get_installation(self, installation_id: int) -> dict[str, Any]:
        return self._api_request(
            "GET",
            f"/app/installations/{installation_id}",
            token=self.create_app_jwt(),
        )

    def get_organization_membership(
        self,
        user_token: str,
        *,
        org_login: str,
        username: str,
    ) -> dict[str, Any]:
        return self._api_request(
            "GET",
            f"/orgs/{quote(org_login)}/memberships/{quote(username)}",
            token=user_token,
        )

    def create_installation_token(self, installation_id: int) -> str:
        payload = self._api_request(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            token=self.create_app_jwt(),
        )
        access_token = payload.get("token")
        if not isinstance(access_token, str) or not access_token:
            raise GitHubAPIError(
                "GitHub installation token response did not include a token."
            )
        return access_token

    def list_installation_repositories(
        self,
        installation_token: str,
    ) -> list[dict[str, Any]]:
        return self._paginate_repositories(
            "/installation/repositories",
            token=installation_token,
        )

    def get_branch_ref(
        self,
        owner: str,
        repo: str,
        branch: str,
        *,
        token: str,
    ) -> str:
        payload = self._api_request(
            "GET",
            f"/repos/{quote(owner)}/{quote(repo)}/git/ref/heads/{quote(branch)}",
            token=token,
        )
        sha = payload.get("object", {}).get("sha")
        if not isinstance(sha, str) or not sha:
            raise GitHubAPIError("GitHub branch ref response did not include a sha.")
        return sha

    def create_branch_ref(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        sha: str,
        token: str,
    ) -> dict[str, Any]:
        return self._api_request(
            "POST",
            f"/repos/{quote(owner)}/{quote(repo)}/git/refs",
            token=token,
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )

    def put_file_contents(
        self,
        owner: str,
        repo: str,
        path: str,
        *,
        message: str,
        content: str,
        branch: str,
        token: str,
        sha: str | None = None,
    ) -> dict[str, Any]:
        encoded_content = b64encode(content.encode("utf-8")).decode("ascii")
        segments = "/".join(quote(part) for part in path.split("/"))
        payload = {"message": message, "content": encoded_content, "branch": branch}
        if sha:
            payload["sha"] = sha
        return self._api_request(
            "PUT",
            f"/repos/{quote(owner)}/{quote(repo)}/contents/{segments}",
            token=token,
            json=payload,
        )

    def get_file_sha(
        self,
        owner: str,
        repo: str,
        path: str,
        *,
        branch: str,
        token: str,
    ) -> str | None:
        segments = "/".join(quote(part) for part in path.split("/"))
        try:
            payload = self._api_request(
                "GET",
                f"/repos/{quote(owner)}/{quote(repo)}/contents/{segments}",
                token=token,
                params={"ref": branch},
            )
        except GitHubAPIError as exc:
            if exc.status_code == 404:
                return None
            raise
        sha = payload.get("sha")
        if sha is not None and not isinstance(sha, str):
            raise GitHubAPIError("GitHub contents response included an invalid sha.")
        return sha

    def get_file_contents(
        self,
        owner: str,
        repo: str,
        path: str,
        *,
        branch: str,
        token: str,
    ) -> str:
        segments = "/".join(quote(part) for part in path.split("/"))
        payload = self._api_request(
            "GET",
            f"/repos/{quote(owner)}/{quote(repo)}/contents/{segments}",
            token=token,
            params={"ref": branch},
        )
        encoded_content = payload.get("content")
        encoding = payload.get("encoding")
        if not isinstance(encoded_content, str) or encoding != "base64":
            raise GitHubAPIError("GitHub contents response did not include base64 content.")
        try:
            return b64decode(encoded_content).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubAPIError("GitHub contents response could not be decoded.") from exc

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str,
        token: str,
        draft: bool = False,
    ) -> dict[str, Any]:
        return self._api_request(
            "POST",
            f"/repos/{quote(owner)}/{quote(repo)}/pulls",
            token=token,
            json={
                "title": title,
                "head": head,
                "base": base,
                "body": body,
                "draft": draft,
            },
        )

    def add_labels(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        labels: list[str],
        *,
        token: str,
    ) -> dict[str, Any]:
        # GitHub auto-creates labels that do not yet exist on the repository.
        return self._api_request(
            "POST",
            f"/repos/{quote(owner)}/{quote(repo)}/issues/{issue_number}/labels",
            token=token,
            json={"labels": labels},
        )

    def list_check_runs_for_ref(
        self,
        owner: str,
        repo: str,
        ref: str,
        *,
        token: str,
    ) -> list[dict[str, Any]]:
        payload = self._api_request(
            "GET",
            f"/repos/{quote(owner)}/{quote(repo)}/commits/{quote(ref, safe='')}/check-runs",
            token=token,
            params={"per_page": 100},
        )
        check_runs = payload.get("check_runs")
        if not isinstance(check_runs, list):
            raise GitHubAPIError("GitHub check-runs response was invalid.")
        return check_runs

    def list_workflow_run_jobs(
        self,
        owner: str,
        repo: str,
        run_id: int,
        *,
        token: str,
    ) -> list[dict[str, Any]]:
        payload = self._api_request(
            "GET",
            f"/repos/{quote(owner)}/{quote(repo)}/actions/runs/{run_id}/jobs",
            token=token,
            params={"per_page": 100},
        )
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            raise GitHubAPIError("GitHub workflow jobs response was invalid.")
        return jobs

    def get_workflow_job_logs(
        self,
        owner: str,
        repo: str,
        job_id: int,
        *,
        token: str,
    ) -> str:
        return self._text_request(
            "GET",
            self._api_url(
                f"/repos/{quote(owner)}/{quote(repo)}/actions/jobs/{job_id}/logs"
            ),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": settings.GITHUB_API_VERSION,
            },
        )

    def find_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        head: str,
        base: str,
        token: str,
    ) -> dict[str, Any] | None:
        payload = self._json_request(
            "GET",
            self._api_url(f"/repos/{quote(owner)}/{quote(repo)}/pulls"),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": settings.GITHUB_API_VERSION,
            },
            params={"head": f"{owner}:{head}", "base": base, "state": "open"},
            expect_list=True,
        )
        pulls = payload.get("items", [])
        return pulls[0] if pulls else None

    def create_app_jwt(self) -> str:
        app_id = self._required_setting("GITHUB_APP_ID")
        private_key = self._required_setting("GITHUB_APP_PRIVATE_KEY").replace("\\n", "\n")
        issued_at = datetime.now(UTC) - timedelta(seconds=60)
        expires_at = issued_at + timedelta(minutes=10)
        return jwt.encode(
            {
                "iat": int(issued_at.timestamp()),
                "exp": int(expires_at.timestamp()),
                "iss": app_id,
            },
            private_key,
            algorithm="RS256",
        )

    def _paginate_repositories(
        self,
        path: str,
        *,
        token: str,
    ) -> list[dict[str, Any]]:
        repositories: list[dict[str, Any]] = []
        page = 1

        while True:
            payload = self._api_request(
                "GET",
                path,
                params={"per_page": 100, "page": page},
                token=token,
            )
            page_repositories = payload.get("repositories")
            if not isinstance(page_repositories, list):
                raise GitHubAPIError("GitHub repositories response was invalid.")

            repositories.extend(page_repositories)
            if len(page_repositories) < 100:
                return repositories
            page += 1

    def _api_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        token: str,
    ) -> dict[str, Any]:
        return self._json_request(
            method,
            self._api_url(path),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": settings.GITHUB_API_VERSION,
            },
            params=params,
            json=json,
        )

    def _json_request(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        expect_list: bool = False,
    ) -> dict[str, Any]:
        response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = httpx.request(
                    method,
                    url,
                    data=data,
                    json=json,
                    headers=headers,
                    params=params,
                    timeout=self.timeout,
                )
            except httpx.HTTPError as exc:
                if attempt < self.max_retries:
                    self._sleep_before_retry(attempt)
                    continue
                raise GitHubAPIError("GitHub request failed.") from exc

            if (
                response.status_code in RETRYABLE_STATUS_CODES
                and attempt < self.max_retries
            ):
                self._sleep_before_retry(attempt)
                continue
            break

        if response is None:
            raise GitHubAPIError("GitHub request failed.")

        if response.status_code >= 400:
            raise GitHubAPIError(
                "GitHub request failed.",
                status_code=response.status_code,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise GitHubAPIError("GitHub response was not valid JSON.") from exc

        if expect_list:
            if not isinstance(payload, list):
                raise GitHubAPIError("GitHub response was not a JSON array.")
            return {"items": payload}

        if not isinstance(payload, dict):
            raise GitHubAPIError("GitHub response was not a JSON object.")
        if payload.get("error"):
            raise GitHubAPIError("GitHub OAuth exchange failed.")
        return payload

    def _text_request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = httpx.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    timeout=self.timeout,
                    follow_redirects=True,
                )
            except httpx.HTTPError as exc:
                if attempt < self.max_retries:
                    self._sleep_before_retry(attempt)
                    continue
                raise GitHubAPIError("GitHub request failed.") from exc

            if (
                response.status_code in RETRYABLE_STATUS_CODES
                and attempt < self.max_retries
            ):
                self._sleep_before_retry(attempt)
                continue
            break

        if response is None:
            raise GitHubAPIError("GitHub request failed.")
        if response.status_code >= 400:
            raise GitHubAPIError(
                "GitHub request failed.",
                status_code=response.status_code,
            )
        return response.text

    def _api_url(self, path: str) -> str:
        return f"{self.api_base_url}/{path.lstrip('/')}"

    def _web_url(self, path: str) -> str:
        return f"{self.web_base_url}/{path.lstrip('/')}"

    def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_backoff_seconds <= 0:
            return
        sleep(self.retry_backoff_seconds * (2**attempt))

    def _required_setting(self, name: str) -> str:
        value = getattr(settings, name, "")
        if not isinstance(value, str) or not value.strip():
            raise ImproperlyConfigured(f"{name} is required for GitHub App onboarding.")
        return value.strip()
