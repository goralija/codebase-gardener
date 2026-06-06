from __future__ import annotations

import logging
from typing import Any

from apps.common.models import AuditEvent
from apps.github_app.client import GitHubAPIError, GitHubAppClient
from apps.repositories.models import ManagedRepository


JsonObject = dict[str, Any]
logger = logging.getLogger(__name__)

BRANCH_PREFIX = "gardener/constitution"
GARDENER_PATH = "GARDENER.md"
PROPOSAL_MARKER = "<!-- gardener-constitution-proposal: v1 -->"
AUDIT_SOURCE = "constitution_proposal_worker"


def maybe_open_constitution_pr(
    *,
    repository: ManagedRepository,
    artifacts: JsonObject,
    client: GitHubAppClient | None = None,
) -> dict[str, Any]:
    constitution = artifacts.get("constitution") or {}
    if not _needs_gardener_pr(constitution):
        return {"created": False, "reason": "constitution_not_missing"}

    client = client or GitHubAppClient()
    token = client.create_installation_token(
        repository.github_installation.github_installation_id
    )
    owner = repository.owner_login
    repo = repository.name
    base_branch = repository.default_branch or "main"
    branch = f"{BRANCH_PREFIX}-{str(repository.id)[:8]}"
    content = render_gardener_md(
        repository=repository,
        artifacts=artifacts,
    )
    body = _pr_body(repository, artifacts)

    try:
        base_sha = client.get_branch_ref(owner, repo, base_branch, token=token)
        try:
            client.create_branch_ref(owner, repo, branch=branch, sha=base_sha, token=token)
        except GitHubAPIError as exc:
            if exc.status_code != 422:
                raise
            _verify_existing_constitution_branch(client, owner, repo, branch, token)

        existing_sha = client.get_file_sha(
            owner,
            repo,
            GARDENER_PATH,
            branch=branch,
            token=token,
        )
        client.put_file_contents(
            owner,
            repo,
            GARDENER_PATH,
            message="Add Repository Constitution",
            content=content,
            branch=branch,
            token=token,
            sha=existing_sha,
        )
        pull_request = _create_or_find_pull_request(
            client,
            owner,
            repo,
            title="Add Repository Constitution",
            head=branch,
            base=base_branch,
            body=body,
            token=token,
        )
        pr_number = pull_request.get("number")
        pr_url = pull_request.get("html_url")
        result = {
            "created": True,
            "branch": branch,
            "pr_number": pr_number,
            "pr_url": pr_url,
        }
        _audit(repository, AuditEvent.EventType.MAINTENANCE_PR_CREATED, result)
        logger.info(
            "constitution.pr.created",
            extra={
                "repository_id": str(repository.id),
                "repository_full_name": repository.full_name,
                "branch": branch,
                "pr_number": pr_number,
                "pr_url": pr_url,
            },
        )
        return result
    except Exception as exc:
        _audit(
            repository,
            AuditEvent.EventType.MAINTENANCE_PR_CREATION_FAILED,
            {"error": str(exc), "branch": branch, "path": GARDENER_PATH},
        )
        logger.exception(
            "constitution.pr.failed",
            extra={
                "repository_id": str(repository.id),
                "repository_full_name": repository.full_name,
                "branch": branch,
            },
        )
        raise


def render_gardener_md(*, repository: ManagedRepository, artifacts: JsonObject) -> str:
    snapshot = artifacts.get("snapshot") or {}
    entropy = artifacts.get("entropy") or {}
    signals = snapshot.get("signals") or {}
    protected_paths = _protected_paths(signals)
    ignored_paths = [
        ".repowise/**",
        ".venv/**",
        "node_modules/**",
        "dist/**",
        "build/**",
        "staticfiles/**",
        "media/**",
    ]
    if any(path.endswith("/migrations/**") for path in protected_paths):
        ignored_paths.append("**/migrations/**")

    lines = [
        PROPOSAL_MARKER,
        "# GARDENER.md",
        "",
        "## Product Purpose",
        "",
        f"- Maintained repository: `{repository.full_name}`.",
        "- Review and edit this draft before merging; merging makes these rules source truth.",
        "",
        "## Protected Modules",
        "",
    ]
    if protected_paths:
        for path in protected_paths:
            lines.append(f"- `{path}` because it appears security-sensitive or business-critical.")
    else:
        lines.append("- `auth/**` because authentication and authorization are sensitive.")
        lines.append("- `permissions/**` because permission behavior is sensitive.")
    lines.extend(
        [
            "",
            "## Never-Touch Paths",
            "",
            "- `**/.env*` because secrets must never be modified by Gardener.",
            "- `**/secrets/**` because secret material requires human handling.",
            "- `**/migrations/**` because database migrations require explicit review.",
            "",
            "## Autonomous Fixes Allowed",
            "",
            "- documentation updates",
            "- lint and format-only changes",
            "- dependency patch updates with passing checks",
            "",
            "## Assisted Fixes Allowed",
            "",
            "- tests",
            "- dead code removal",
            "- complexity reduction",
            "- layer violation repair",
            "",
            "## Advisory-Only Areas",
            "",
            "- auth",
            "- permissions",
            "- tenancy",
            "- payroll",
            "- credentials",
            "- security-sensitive code",
            "- migrations",
            "",
            "## Architecture Boundaries",
            "",
            "- Runtime code must not import from `tests/**`.",
            "- Presentation/API layers must not bypass service/domain modules for persistence behavior.",
            "",
            "## Test Rules",
            "",
            "- Run the repository's default backend test suite before backend changes.",
            "- Run relevant targeted tests for changed modules.",
            "",
            "## Ignored Paths",
            "",
        ]
    )
    lines.extend(f"- `{path}`" for path in _unique(ignored_paths))
    lines.extend(
        [
            "",
            "## Health Priorities",
            "",
            f"- Current entropy classification: `{(entropy.get('score') or {}).get('classification', 'unknown')}`.",
            f"- Current entropy score: `{(entropy.get('score') or {}).get('overall', 'unknown')}`.",
            "- Prefer focused, reviewable maintenance PRs.",
            "",
            "## Trigger and PR Preferences",
            "",
            "- Prefer small PRs scoped to one maintenance category.",
            "- Do not auto-merge Gardener PRs.",
            "",
        ]
    )
    return "\n".join(lines)


def _needs_gardener_pr(constitution: JsonObject) -> bool:
    for question in constitution.get("open_questions") or []:
        if not isinstance(question, dict):
            continue
        if question.get("severity") != "blocking":
            continue
        if "No repository constitution (GARDENER.md) found" in str(question.get("question")):
            return True
    return False


def _protected_paths(signals: JsonObject) -> list[str]:
    candidates: list[str] = []
    sensitive = (
        "auth",
        "permission",
        "tenant",
        "payroll",
        "credential",
        "secret",
        "security",
        "billing",
        "payment",
    )
    for bucket in ("hotspots", "dependency_cycles", "ownership_risks", "test_gaps"):
        for signal in signals.get(bucket) or []:
            if not isinstance(signal, dict):
                continue
            path = signal.get("path")
            if not isinstance(path, str) or not path:
                continue
            lowered = path.lower()
            if not any(word in lowered for word in sensitive):
                continue
            candidates.append(_module_glob(path))
            if len(candidates) >= 8:
                return _unique(candidates)
    return _unique(candidates)


def _module_glob(path: str) -> str:
    parts = path.split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}/**"
    if parts:
        return f"{parts[0]}"
    return path


def _verify_existing_constitution_branch(
    client: GitHubAppClient,
    owner: str,
    repo: str,
    branch: str,
    token: str,
) -> None:
    try:
        content = client.get_file_contents(
            owner,
            repo,
            GARDENER_PATH,
            branch=branch,
            token=token,
        )
    except GitHubAPIError as exc:
        if exc.status_code == 404:
            return
        raise
    if PROPOSAL_MARKER not in content:
        raise GitHubAPIError(
            "Constitution proposal branch exists but does not contain a Gardener marker.",
            status_code=422,
        )


def _create_or_find_pull_request(
    client: GitHubAppClient,
    owner: str,
    repo: str,
    *,
    title: str,
    head: str,
    base: str,
    body: str,
    token: str,
) -> dict[str, Any]:
    try:
        return client.create_pull_request(
            owner,
            repo,
            title=title,
            head=head,
            base=base,
            body=body,
            token=token,
            draft=True,
        )
    except GitHubAPIError as exc:
        if exc.status_code != 422:
            raise
        existing = client.find_pull_request(owner, repo, head=head, base=base, token=token)
        if existing is None:
            raise
        return existing


def _pr_body(repository: ManagedRepository, artifacts: JsonObject) -> str:
    entropy = artifacts.get("entropy") or {}
    score = entropy.get("score") or {}
    return (
        "## Goal\n\n"
        "Add a customer-reviewable Repository Constitution so Gardener can replace "
        "`no_autonomy` with explicit source truth.\n\n"
        "## Evidence\n\n"
        "The latest analysis found no `GARDENER.md`, which creates a blocking "
        "constitution question.\n\n"
        "## Risk tier\n\n"
        "Tier 1 autonomous: documentation/source-truth proposal only. This PR must "
        "be reviewed before merge.\n\n"
        "## Entropy impact\n\n"
        f"Current classification: `{score.get('classification', 'unknown')}`. "
        f"Current score: `{score.get('overall', 'unknown')}`.\n\n"
        "## Changed paths\n\n"
        "- `GARDENER.md`\n\n"
        "## Verification\n\n"
        "After merge, rerun a Gardening Session and verify no blocking missing-"
        "constitution question remains.\n\n"
        "## Rollback\n\n"
        "Revert this PR or edit `GARDENER.md` if the proposed rules do not match "
        f"`{repository.full_name}`."
    )


def _audit(repository: ManagedRepository, event_type: str, metadata: dict[str, Any]) -> None:
    AuditEvent.objects.create(
        organization=repository.organization,
        github_installation=repository.github_installation,
        repository=repository,
        event_type=event_type,
        source=AUDIT_SOURCE,
        metadata={**metadata, "path": GARDENER_PATH},
    )


def _unique(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique
