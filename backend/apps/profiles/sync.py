from __future__ import annotations

from typing import Any

import yaml

from apps.common.models import AuditEvent
from apps.github_app.client import GitHubAPIError, GitHubAppClient
from apps.maintenance_prs.executor import _create_or_find_pull_request
from apps.profiles.models import GardenerProfile

PROFILE_FILE_PATH = ".gardener/profile.yaml"
PROFILE_SYNC_BRANCH = "gardener/profile-sync"
PROFILE_SYNC_TITLE = "chore(gardener): sync learned profile to .gardener/profile.yaml"
SYNC_AUDIT_SOURCE = "gardening_worker"
# Cap rendered notes so an append-only outcome history does not bloat the file
# (and its diffs) without bound; aggregated counts retain the full signal.
PROFILE_NOTES_LIMIT = 20

# outcome -> doc-16 outcomes.<bucket>_categories field. Mirrors the learning
# module's category buckets so the proposed file matches the DB signals.
_OUTCOME_BUCKET = {
    "merged": "accepted_categories",
    "accepted": "accepted_categories",
    "rejected": "rejected_categories",
    "closed": "rejected_categories",
    "reverted": "reverted_categories",
}


def build_profile_document(profile: GardenerProfile) -> dict[str, Any]:
    """Build the doc-16 ``.gardener/profile.yaml`` document (pre-serialization).

    Source of truth is :meth:`GardenerProfile.to_contract` (schema-validated).
    Outcome category maps hold counts derived from ``updated_from_pr_outcomes``.
    """

    contract = profile.to_contract()
    return {
        "version": 1,
        "repository": {
            "repository_id": contract["repository_id"],
            "preferred_pr_size": contract["preferred_pr_size"],
            "preferred_pr_categories": {
                "accepted": contract["accepted_categories"],
                "rejected": contract["rejected_categories"],
            },
            "protected_patterns_learned": contract["learned_protected_patterns"],
            "review_preferences": contract["review_preferences"],
        },
        "outcomes": _outcome_counts(contract["updated_from_pr_outcomes"]),
        "notes": _notes(contract["updated_from_pr_outcomes"]),
    }


def render_profile_yaml(profile: GardenerProfile) -> str:
    """Serialize :func:`build_profile_document` to YAML."""

    return yaml.safe_dump(
        build_profile_document(profile), sort_keys=False, default_flow_style=False
    )


def _outcome_counts(entries: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {
        "accepted_categories": {},
        "rejected_categories": {},
        "reverted_categories": {},
    }
    for entry in entries:
        bucket = _OUTCOME_BUCKET.get(entry.get("outcome"))
        category = entry.get("category")
        if not bucket or not category:
            continue
        counts[bucket][category] = counts[bucket].get(category, 0) + 1
    return counts


def _notes(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    # Keep only the most recent entries; the list is append-only and grows for
    # the life of the repository.
    for entry in entries[-PROFILE_NOTES_LIMIT:]:
        outcome = entry.get("outcome") or "unknown"
        category = entry.get("category") or "unknown"
        notes.append(
            {
                "source": "pr-outcome",
                "text": f"PR outcome '{outcome}' for category '{category}'.",
            }
        )
    return notes


def sync_profile_to_repo(
    profile: GardenerProfile,
    *,
    client: GitHubAppClient | None = None,
) -> dict[str, Any]:
    """Propose the learned profile to ``.gardener/profile.yaml`` via a PR.

    Idempotent: a no-op when the rendered file already matches the repo, and it
    reuses the open profile-sync PR instead of opening duplicates. Learned
    memory only ever writes ``profile.yaml``; it never touches the constitution
    (``GARDENER.md``), so it cannot override explicit rules (doc-16).
    """

    repository = profile.repository

    # Never act on a repository the customer unselected, or one whose
    # installation/org is suspended or deactivated (mirrors the executor's
    # guard so memory PRs honor the same isolation boundary).
    if not repository.is_active:
        return {
            "repository_id": str(repository.id),
            "proposed": False,
            "reason": "repository_inactive",
        }

    client = client or GitHubAppClient()
    installation = repository.github_installation
    owner = repository.owner_login
    repo = repository.name
    base_branch = repository.default_branch

    document = build_profile_document(profile)
    rendered = yaml.safe_dump(document, sort_keys=False, default_flow_style=False)

    try:
        token = client.create_installation_token(installation.github_installation_id)

        current = _read_current_profile(client, owner, repo, base_branch, token=token)
        # Compare parsed documents so a hand-edited file with equivalent content
        # but different formatting does not churn a needless PR.
        if current is not None and _parse_yaml(current) == document:
            return {
                "repository_id": str(repository.id),
                "proposed": False,
                "reason": "up_to_date",
            }

        base_sha = client.get_branch_ref(owner, repo, base_branch, token=token)
        _ensure_branch(
            client, owner, repo, branch=PROFILE_SYNC_BRANCH, sha=base_sha, token=token
        )

        file_sha = client.get_file_sha(
            owner, repo, PROFILE_FILE_PATH, branch=PROFILE_SYNC_BRANCH, token=token
        )
        client.put_file_contents(
            owner,
            repo,
            PROFILE_FILE_PATH,
            message=PROFILE_SYNC_TITLE,
            content=rendered,
            branch=PROFILE_SYNC_BRANCH,
            token=token,
            sha=file_sha,
        )

        pull_request = _create_or_find_pull_request(
            client,
            owner,
            repo,
            title=PROFILE_SYNC_TITLE,
            head=PROFILE_SYNC_BRANCH,
            base=base_branch,
            body=_pr_body(),
            token=token,
        )
    except Exception as exc:
        _audit(
            repository,
            AuditEvent.EventType.GARDENER_PROFILE_PR_FAILED,
            {"error": str(exc), "branch": PROFILE_SYNC_BRANCH},
        )
        raise

    pr_number = pull_request.get("number")
    pr_url = pull_request.get("html_url")

    _audit(
        repository,
        AuditEvent.EventType.GARDENER_PROFILE_PR_PROPOSED,
        {"pr_number": pr_number, "pr_url": pr_url, "branch": PROFILE_SYNC_BRANCH},
    )

    return {
        "repository_id": str(repository.id),
        "proposed": True,
        "pr_number": pr_number,
        "pr_url": pr_url,
    }


def _parse_yaml(content: str) -> Any:
    try:
        return yaml.safe_load(content)
    except yaml.YAMLError:
        # Unparseable existing file: treat as "different" so we propose a fix.
        return None


def _read_current_profile(
    client: GitHubAppClient,
    owner: str,
    repo: str,
    branch: str,
    *,
    token: str,
) -> str | None:
    try:
        return client.get_file_contents(
            owner, repo, PROFILE_FILE_PATH, branch=branch, token=token
        )
    except GitHubAPIError as exc:
        if exc.status_code == 404:
            return None
        raise


def _ensure_branch(
    client: GitHubAppClient,
    owner: str,
    repo: str,
    *,
    branch: str,
    sha: str,
    token: str,
) -> None:
    try:
        client.create_branch_ref(owner, repo, branch=branch, sha=sha, token=token)
    except GitHubAPIError as exc:
        # 422 = the profile-sync branch already exists from a prior run; reuse it.
        if exc.status_code != 422:
            raise


def _pr_body() -> str:
    return (
        "## Goal\n\n"
        "Sync the learned `GardenerProfile` to `.gardener/profile.yaml`.\n\n"
        "## Evidence\n\n"
        "Generated from PR-outcome learning (doc-16 memory rules). Learned "
        "memory influences ranking only and never overrides explicit "
        "constitution rules in `GARDENER.md`.\n"
    )


def _audit(repository, event_type: str, metadata: dict[str, Any]) -> None:
    AuditEvent.objects.create(
        organization=repository.organization,
        github_installation=repository.github_installation,
        repository=repository,
        event_type=event_type,
        source=SYNC_AUDIT_SOURCE,
        metadata={"repository_id": str(repository.id), **metadata},
    )
