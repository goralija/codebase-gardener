"""Persist and retrieve repository analysis runs.

Large blobs go to object storage (per-tenant key); small contracts are stored
inline on the RepositoryAnalysis row. The producer (E05-T01 worker, or the
local ``ingest_analysis`` command) supplies an ``artifacts`` mapping.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.analysis.models import RepositoryAnalysis
from apps.common import storage
from apps.common.models import AuditEvent


JsonObject = dict[str, Any]

# Artifact name -> (model key field, model checksum field). These are the large
# blobs uploaded to object storage.
_BLOB_FIELDS = {
    "snapshot": ("snapshot_key", "snapshot_checksum"),
    "knowledge_graph": ("knowledge_graph_key", "knowledge_graph_checksum"),
    "health": ("health_key", "health_checksum"),
    "dead_code": ("dead_code_key", "dead_code_checksum"),
}


@transaction.atomic
def store_analysis(
    *,
    organization,
    repository,
    commit_sha: str,
    artifacts: JsonObject,
    source: str = RepositoryAnalysis.Source.SESSION,
    actor=None,
) -> RepositoryAnalysis:
    """Store one analysis run.

    ``artifacts`` may contain: constitution, entropy, opportunities (inline)
    and snapshot, knowledge_graph, health, dead_code (uploaded to storage).
    Re-storing the same (repository, commit) overwrites the prior row + blobs.
    """
    storage.ensure_bucket()

    blob_values: dict[str, str] = {}
    for artifact, (key_field, checksum_field) in _BLOB_FIELDS.items():
        if artifact not in artifacts or artifacts[artifact] is None:
            continue
        key = storage.tenant_key(
            str(organization.id), str(repository.id), commit_sha, artifact
        )
        checksum = storage.put_json(key, artifacts[artifact])
        blob_values[key_field] = key
        blob_values[checksum_field] = checksum

    analysis, _created = RepositoryAnalysis.objects.update_or_create(
        repository=repository,
        commit_sha=commit_sha,
        defaults={
            "organization": organization,
            "source": source,
            "constitution": artifacts.get("constitution") or {},
            "entropy": artifacts.get("entropy") or {},
            "opportunities": artifacts.get("opportunities") or [],
            **blob_values,
        },
    )

    AuditEvent.objects.create(
        actor=actor,
        organization=organization,
        repository=repository,
        event_type=AuditEvent.EventType.ANALYSIS_STORED,
        source="analysis_storage",
        metadata={"commit_sha": commit_sha, "analysis_id": str(analysis.id)},
    )
    from apps.billing.services import refresh_repository_complexity

    refresh_repository_complexity(
        repository=repository,
        analysis=analysis,
        artifacts=artifacts,
        actor=actor,
    )
    return analysis


def get_latest(repository) -> RepositoryAnalysis | None:
    return repository.analyses.order_by("-created_at").first()


def get_latest_relevant_baseline(repository) -> RepositoryAnalysis | None:
    return (
        repository.analyses.filter(baseline_promoted_at__isnull=False)
        .order_by("-baseline_promoted_at", "-created_at")
        .first()
    )


def promote_relevant_baseline(analysis: RepositoryAnalysis) -> RepositoryAnalysis:
    analysis.baseline_promoted_at = timezone.now()
    analysis.save(update_fields=["baseline_promoted_at", "updated_at"])
    return analysis


def list_history(repository) -> list[RepositoryAnalysis]:
    return list(repository.analyses.order_by("-created_at"))


def get_latest_any() -> RepositoryAnalysis | None:
    """Most recent stored analysis across all repositories (dev/demo convenience)."""
    return RepositoryAnalysis.objects.order_by("-created_at").first()


def load_first_report(analysis: RepositoryAnalysis) -> JsonObject:
    """Assemble a FirstReport-shaped payload the dashboard already renders."""
    snapshot = storage.get_json(analysis.snapshot_key) if analysis.snapshot_key else {}
    session_result, maintenance_pr_plans = _latest_session_outputs(analysis.repository)
    return {
        "repository_constitution": analysis.constitution or {},
        "analysis_snapshot": snapshot or {},
        "entropy_report": analysis.entropy or {},
        "gardening_session_result": session_result or _empty_session(str(analysis.repository_id)),
        "maintenance_opportunities": analysis.opportunities or [],
        "maintenance_pr_plans": maintenance_pr_plans,
    }


def load_snapshot(analysis: RepositoryAnalysis) -> JsonObject:
    return storage.get_json(analysis.snapshot_key) if analysis.snapshot_key else {}


def _latest_session_outputs(repository) -> tuple[JsonObject | None, list[JsonObject]]:
    from apps.maintenance_prs.models import MaintenancePRPlan
    from apps.sessions.models import GardeningSession

    session = (
        GardeningSession.objects.filter(
            repository=repository,
            status=GardeningSession.Status.COMPLETED,
        )
        .order_by("-finished_at", "-created_at")
        .first()
    )
    if session is None or not session.result:
        return None, []

    plans = [
        plan.to_contract()
        for plan in MaintenancePRPlan.objects.for_session(str(session.id))
        .prefetch_related("opportunity_links")
        .order_by("created_at", "id")
    ]
    return session.result, plans


def _empty_session(repository_id: str) -> JsonObject:
    return {
        "schema_version": "1.0",
        "gardening_session_id": "",
        "repository_id": repository_id,
        "trigger": {"type": "none", "actor": "system"},
        "status": "not_run",
        "started_at": "",
        "finished_at": "",
        "phase_results": [],
        "opportunities_selected": [],
        "opportunities_deferred": [],
        "maintenance_pr_plans": [],
        "errors": [],
    }


def load_report(analysis: RepositoryAnalysis) -> JsonObject:
    """Assemble a FirstReport-shaped dict: inline contracts + blobs on demand."""
    report: JsonObject = {
        "repository_id": str(analysis.repository_id),
        "commit_sha": analysis.commit_sha,
        "repository_constitution": analysis.constitution,
        "entropy_report": analysis.entropy,
        "maintenance_opportunities": analysis.opportunities,
    }
    for artifact, (key_field, _checksum) in _BLOB_FIELDS.items():
        key = getattr(analysis, key_field)
        report[artifact] = storage.get_json(key) if key else None
    return report
