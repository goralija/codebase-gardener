from __future__ import annotations

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
        )

    def _json_request(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = httpx.request(
                    method,
                    url,
                    data=data,
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

        if not isinstance(payload, dict):
            raise GitHubAPIError("GitHub response was not a JSON object.")
        if payload.get("error"):
            raise GitHubAPIError("GitHub OAuth exchange failed.")
        return payload

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
