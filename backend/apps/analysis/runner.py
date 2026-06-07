from __future__ import annotations

import subprocess
import logging
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from urllib.parse import quote, urlsplit, urlunsplit

from django.conf import settings

from apps.analysis.models import RepositoryAnalysis
from apps.analysis.storage_service import store_analysis
from apps.github_app.client import GitHubAppClient
from apps.repositories.models import ManagedRepository
from gardener_analysis import (
    RepowiseIndexOptions,
    build_analysis_snapshot,
    build_entropy_report,
    build_repository_constitution,
    discover_source_truth,
    generate_maintenance_opportunities,
    index_repository,
)


JsonObject = dict[str, Any]
CloneRepository = Callable[[ManagedRepository, str, Path], None]
logger = logging.getLogger(__name__)


class AnalysisRunError(Exception):
    def __init__(self, phase: str, message: str) -> None:
        self.phase = phase
        self.message = message
        super().__init__(phase, message)

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class AnalysisRunResult:
    analysis: RepositoryAnalysis
    artifacts: JsonObject


def run_repository_analysis(
    *,
    repository: ManagedRepository,
    source: str = RepositoryAnalysis.Source.SESSION,
    actor=None,
    client: GitHubAppClient | None = None,
    clone_repository: CloneRepository | None = None,
) -> AnalysisRunResult:
    repository = ManagedRepository.objects.select_related(
        "organization",
        "github_installation",
    ).get(id=repository.id)
    if not repository.is_active:
        raise AnalysisRunError("observe", "Repository is not active.")

    github_client = client or GitHubAppClient()
    clone_repository = clone_repository or _clone_repository

    logger.info(
        "analysis.run.start",
        extra=_repo_log_extra(repository),
    )
    token = github_client.create_installation_token(
        repository.github_installation.github_installation_id
    )
    try:
        with TemporaryDirectory(prefix="gardener-analysis-") as clone_root:
            repo_path = Path(clone_root) / "repo"
            logger.info("analysis.clone.start", extra=_repo_log_extra(repository))
            clone_repository(repository, token, repo_path)
            _ensure_repository_has_head(repo_path)
            logger.info("analysis.clone.completed", extra=_repo_log_extra(repository))
            artifacts = _build_analysis_artifacts(repository, repo_path)
    finally:
        token = ""

    logger.info(
        "analysis.storage.start",
        extra={
            **_repo_log_extra(repository),
            "commit_sha": artifacts["snapshot"]["commit_sha"],
        },
    )
    analysis = store_analysis(
        organization=repository.organization,
        repository=repository,
        commit_sha=artifacts["snapshot"]["commit_sha"],
        artifacts=artifacts,
        source=source,
        actor=actor,
    )
    logger.info(
        "analysis.run.completed",
        extra={
            **_repo_log_extra(repository),
            "analysis_id": str(analysis.id),
            "commit_sha": analysis.commit_sha,
            "signal_counts": _signal_counts(artifacts["snapshot"]),
            "entropy_score": artifacts["entropy"].get("score", {}),
            "opportunity_count": len(artifacts["opportunities"]),
        },
    )
    return AnalysisRunResult(analysis=analysis, artifacts=artifacts)


def _build_analysis_artifacts(repository: ManagedRepository, repo_path: Path) -> JsonObject:
    try:
        logger.info("analysis.repowise.start", extra=_repo_log_extra(repository))
        index = index_repository(
            repo_path,
            RepowiseIndexOptions(repowise_project=_repowise_project_path()),
        )
        logger.info(
            "analysis.repowise.completed",
            extra={
                **_repo_log_extra(repository),
                "health_metric_count": len(index.health.get("metrics", [])),
                "health_finding_count": len(index.health.get("findings", [])),
                "dead_code_count": len(index.dead_code)
                if isinstance(index.dead_code, list)
                else len(index.dead_code.get("findings", [])),
                "has_knowledge_graph": bool(index.knowledge_graph),
            },
        )
        logger.info("analysis.discovery.start", extra=_repo_log_extra(repository))
        discovery = discover_source_truth(repo_path)
        logger.info(
            "analysis.discovery.completed",
            extra={
                **_repo_log_extra(repository),
                "source_truth_count": len(discovery.files),
            },
        )
        constitution_id = f"constitution_{repository.id}"
        logger.info("analysis.snapshot.start", extra=_repo_log_extra(repository))
        snapshot = build_analysis_snapshot(
            index,
            repository_id=str(repository.id),
            constitution_id=constitution_id,
        )
        logger.info(
            "analysis.snapshot.completed",
            extra={
                **_repo_log_extra(repository),
                "commit_sha": snapshot["commit_sha"],
                "logical_system_count": len(snapshot.get("logical_systems", [])),
                "signal_counts": _signal_counts(snapshot),
            },
        )
        logger.info("analysis.constitution.start", extra=_repo_log_extra(repository))
        constitution = build_repository_constitution(
            repo_path,
            repository_id=str(repository.id),
            commit_sha=snapshot["commit_sha"],
            discovery=discovery,
        )
        logger.info(
            "analysis.constitution.completed",
            extra={
                **_repo_log_extra(repository),
                "completeness_score": constitution.get("completeness_score"),
                "open_question_count": len(constitution.get("open_questions", [])),
                "blocking_question_count": sum(
                    1
                    for question in constitution.get("open_questions", [])
                    if question.get("severity") == "blocking"
                ),
            },
        )
        logger.info("analysis.entropy.start", extra=_repo_log_extra(repository))
        entropy = build_entropy_report(snapshot, constitution)
        logger.info(
            "analysis.entropy.completed",
            extra={
                **_repo_log_extra(repository),
                "entropy_score": entropy.get("score", {}),
            },
        )
        logger.info("analysis.opportunities.start", extra=_repo_log_extra(repository))
        opportunities = generate_maintenance_opportunities(
            snapshot,
            entropy,
            constitution,
            top_n=1000,
        )
        logger.info(
            "analysis.opportunities.completed",
            extra={
                **_repo_log_extra(repository),
                "opportunity_count": len(opportunities),
                "opportunity_categories": sorted(
                    {str(opportunity.get("category", "")) for opportunity in opportunities}
                ),
            },
        )
    except Exception as exc:
        logger.exception(
            "analysis.run.failed",
            extra={**_repo_log_extra(repository), "phase": "diagnose"},
        )
        raise AnalysisRunError("diagnose", str(exc) or exc.__class__.__name__) from exc

    return {
        "snapshot": snapshot,
        "constitution": constitution,
        "entropy": entropy,
        "opportunities": opportunities,
        "knowledge_graph": index.knowledge_graph or {},
        "health": index.health,
        "dead_code": index.dead_code,
    }


def _clone_repository(repository: ManagedRepository, token: str, destination: Path) -> None:
    clone_url = _clone_url(repository.full_name, token)
    command = [
        "git",
        "clone",
        "--depth",
        str(getattr(settings, "ANALYSIS_CLONE_DEPTH", 100)),
        clone_url,
        str(destination),
    ]
    timeout = getattr(settings, "ANALYSIS_CLONE_TIMEOUT_SECONDS", 600)
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
    )
    if result.returncode != 0:
        details = _sanitize_token(result.stderr or result.stdout or "git clone failed", token)
        raise AnalysisRunError("observe", details)


def _ensure_repository_has_head(repo_path: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--verify", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise AnalysisRunError(
            "observe",
            "Repository has no commits on the cloned default branch.",
        )


def _clone_url(full_name: str, token: str) -> str:
    web_base_url = getattr(settings, "GITHUB_WEB_BASE_URL", "https://github.com")
    parsed = urlsplit(web_base_url.rstrip("/"))
    netloc = f"x-access-token:{quote(token, safe='')}@{parsed.netloc}"
    path = f"{parsed.path.rstrip('/')}/{full_name}.git"
    return urlunsplit((parsed.scheme, netloc, path, "", ""))


def _sanitize_token(value: str, token: str) -> str:
    sanitized = value
    if token:
        sanitized = sanitized.replace(token, "[redacted]")
        sanitized = sanitized.replace(quote(token, safe=""), "[redacted]")
    return sanitized.strip() or "git clone failed"


def _repowise_project_path() -> Path:
    configured = getattr(settings, "ANALYSIS_REPOWISE_PROJECT_DIR", "")
    if configured:
        return Path(configured).resolve()
    return (Path(settings.BASE_DIR).parent / "RepoWise").resolve()


def _repo_log_extra(repository: ManagedRepository) -> dict[str, str]:
    return {
        "repository_id": str(repository.id),
        "repository_full_name": repository.full_name,
        "organization_id": str(repository.organization_id),
        "github_installation_id": str(repository.github_installation.github_installation_id),
    }


def _signal_counts(snapshot: JsonObject) -> dict[str, int]:
    signals = snapshot.get("signals", {})
    if not isinstance(signals, dict):
        return {}
    return {
        str(bucket): len(value) if isinstance(value, list) else 0
        for bucket, value in signals.items()
    }
