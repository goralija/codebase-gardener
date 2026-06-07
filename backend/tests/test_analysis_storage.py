import pytest
from django.utils import timezone
from moto import mock_aws

from apps.accounts.models import CustomerOrganization
from apps.analysis import storage_service
from apps.analysis.models import RepositoryAnalysis
from apps.common import storage
from apps.common.models import AuditEvent
from apps.github_app.models import GitHubInstallation
from apps.maintenance_prs.models import MaintenancePRPlan, MaintenancePRPlanOpportunity
from apps.repositories.models import ManagedRepository
from apps.sessions.models import GardeningSession


BUCKET = "gardener-analysis"


@pytest.fixture(autouse=True)
def _storage_settings(settings):
    # moto intercepts boto3 at the AWS default endpoint, so endpoint_url=None.
    settings.OBJECT_STORAGE_ENDPOINT_URL = None
    settings.OBJECT_STORAGE_ACCESS_KEY = "local"
    settings.OBJECT_STORAGE_SECRET_KEY = "localpass123"
    settings.OBJECT_STORAGE_BUCKET = BUCKET
    settings.OBJECT_STORAGE_REGION = "us-east-1"
    storage.reset_client_cache()
    yield
    storage.reset_client_cache()


def _org(n=1):
    return CustomerOrganization.objects.create(
        name=f"Org {n}",
        github_account_id=1000 + n,
        github_login=f"org{n}",
        github_account_type=CustomerOrganization.GitHubAccountType.ORGANIZATION,
    )


def _repo(org, n=1):
    installation = GitHubInstallation.objects.create(
        organization=org,
        github_installation_id=2000 + n,
        github_account_id=org.github_account_id,
        github_account_login=org.github_login,
        github_account_type=GitHubInstallation.GitHubAccountType.ORGANIZATION,
    )
    return ManagedRepository.objects.create(
        organization=org,
        github_installation=installation,
        github_repository_id=3000 + n,
        name=f"repo{n}",
        full_name=f"{org.github_login}/repo{n}",
        owner_login=org.github_login,
    )


def _artifacts(commit="abc123"):
    return {
        "constitution": {"completeness_score": 0.5},
        "entropy": {"score": {"overall": 42.0}},
        "opportunities": [{"category": "docs"}],
        "snapshot": {"commit_sha": commit, "signals": {}},
        "knowledge_graph": {"nodes": [1, 2, 3]},
        "health": {"metrics": []},
        "dead_code": [{"path": "x.py"}],
    }


# --- storage client --------------------------------------------------------


@mock_aws
def test_put_get_json_roundtrip_and_checksum():
    storage.ensure_bucket()

    checksum = storage.put_json("k/a.json.gz", {"b": 2, "a": 1})
    assert storage.get_json("k/a.json.gz") == {"b": 2, "a": 1}
    # checksum is sha256 of canonical JSON, stable across calls
    assert storage.put_json("k/a.json.gz", {"a": 1, "b": 2}) == checksum


@mock_aws
def test_delete_prefix_scoped():
    storage.ensure_bucket()
    storage.put_json("org_a/x.json.gz", {"x": 1})
    storage.put_json("org_a/y.json.gz", {"y": 1})
    storage.put_json("org_b/z.json.gz", {"z": 1})

    deleted = storage.delete_prefix("org_a/")
    assert deleted == 2
    assert storage.get_json("org_b/z.json.gz") == {"z": 1}


def test_tenant_key_format():
    assert (
        storage.tenant_key("O", "R", "deadbeef", "snapshot")
        == "org_O/repo_R/deadbeef/snapshot.json.gz"
    )


# --- store_analysis --------------------------------------------------------


@pytest.mark.django_db
@mock_aws
def test_store_analysis_uploads_blobs_inlines_contracts():

    org = _org()
    repo = _repo(org)
    analysis = storage_service.store_analysis(
        organization=org, repository=repo, commit_sha="abc123", artifacts=_artifacts()
    )

    # inline small contracts
    assert analysis.entropy == {"score": {"overall": 42.0}}
    assert analysis.opportunities == [{"category": "docs"}]
    # blob keys are per-tenant
    assert analysis.snapshot_key == f"org_{org.id}/repo_{repo.id}/abc123/snapshot.json.gz"
    assert analysis.knowledge_graph_key.endswith("knowledge_graph.json.gz")
    assert analysis.snapshot_checksum
    # blob actually retrievable
    assert storage.get_json(analysis.knowledge_graph_key) == {"nodes": [1, 2, 3]}
    # audit trail
    assert AuditEvent.objects.filter(
        organization=org, event_type=AuditEvent.EventType.ANALYSIS_STORED
    ).exists()


@pytest.mark.django_db
@mock_aws
def test_store_analysis_source_and_baseline_promotion():
    org = _org()
    repo = _repo(org)
    first = storage_service.store_analysis(
        organization=org,
        repository=repo,
        commit_sha="c1",
        artifacts=_artifacts("c1"),
        source=RepositoryAnalysis.Source.FIRST_SCAN,
    )
    second = storage_service.store_analysis(
        organization=org,
        repository=repo,
        commit_sha="c2",
        artifacts=_artifacts("c2"),
        source=RepositoryAnalysis.Source.SESSION,
    )

    assert first.source == RepositoryAnalysis.Source.FIRST_SCAN
    assert storage_service.get_latest_relevant_baseline(repo) is None

    storage_service.promote_relevant_baseline(first)
    assert storage_service.get_latest_relevant_baseline(repo).id == first.id

    storage_service.promote_relevant_baseline(second)
    assert storage_service.get_latest_relevant_baseline(repo).id == second.id


@pytest.mark.django_db
@mock_aws
def test_history_and_get_latest():

    org = _org()
    repo = _repo(org)
    storage_service.store_analysis(
        organization=org, repository=repo, commit_sha="c1", artifacts=_artifacts("c1")
    )
    storage_service.store_analysis(
        organization=org, repository=repo, commit_sha="c2", artifacts=_artifacts("c2")
    )

    history = storage_service.list_history(repo)
    assert {a.commit_sha for a in history} == {"c1", "c2"}
    assert RepositoryAnalysis.objects.filter(repository=repo).count() == 2
    assert storage_service.get_latest(repo).commit_sha == "c2"


@pytest.mark.django_db
@mock_aws
def test_re_store_same_commit_overwrites():

    org = _org()
    repo = _repo(org)
    storage_service.store_analysis(
        organization=org, repository=repo, commit_sha="c1", artifacts=_artifacts("c1")
    )
    storage_service.store_analysis(
        organization=org, repository=repo, commit_sha="c1", artifacts=_artifacts("c1")
    )
    assert RepositoryAnalysis.objects.filter(repository=repo).count() == 1


@pytest.mark.django_db
@mock_aws
def test_tenancy_isolation():

    org_a, org_b = _org(1), _org(2)
    repo_a, repo_b = _repo(org_a, 1), _repo(org_b, 2)
    a = storage_service.store_analysis(
        organization=org_a, repository=repo_a, commit_sha="c", artifacts=_artifacts()
    )
    storage_service.store_analysis(
        organization=org_b, repository=repo_b, commit_sha="c", artifacts=_artifacts()
    )

    # org A history never includes org B rows
    assert all(x.organization_id == org_a.id for x in storage_service.list_history(repo_a))
    assert a.snapshot_key.startswith(f"org_{org_a.id}/")
    # purging org A leaves org B intact
    storage.delete_prefix(f"org_{org_a.id}/")
    b_latest = storage_service.get_latest(repo_b)
    assert storage.get_json(b_latest.snapshot_key)["commit_sha"] == "abc123"


@pytest.mark.django_db
@mock_aws
def test_load_report_assembles_inline_plus_blobs():

    org = _org()
    repo = _repo(org)
    analysis = storage_service.store_analysis(
        organization=org, repository=repo, commit_sha="abc123", artifacts=_artifacts()
    )
    report = storage_service.load_report(analysis)

    assert report["entropy_report"] == {"score": {"overall": 42.0}}
    assert report["maintenance_opportunities"] == [{"category": "docs"}]
    assert report["knowledge_graph"] == {"nodes": [1, 2, 3]}
    assert report["snapshot"]["commit_sha"] == "abc123"


@pytest.mark.django_db
@mock_aws
def test_load_first_report_includes_latest_completed_session_and_pr_plans():
    org = _org()
    repo = _repo(org)
    analysis = storage_service.store_analysis(
        organization=org, repository=repo, commit_sha="abc123", artifacts=_artifacts()
    )
    session = GardeningSession.objects.create(
        repository=repo,
        status=GardeningSession.Status.COMPLETED,
        finished_at=timezone.now(),
        trigger={"type": "first_scan"},
        result={
            "schema_version": "1.0",
            "gardening_session_id": "session_123",
            "repository_id": str(repo.id),
            "trigger": {"type": "first_scan"},
            "status": "completed",
            "started_at": "2026-06-06T12:00:00Z",
            "finished_at": "2026-06-06T12:01:00Z",
            "phase_results": [],
            "opportunities_selected": ["opp_docs"],
            "opportunities_deferred": [],
            "maintenance_pr_plans": [],
            "errors": [],
        },
    )
    plan = MaintenancePRPlan.objects.create(
        repository=repo,
        gardening_session_id=str(session.id),
        branch_name="gardener/docs-refresh",
        title="Refresh docs",
        category="docs",
        risk_tier="tier_1_autonomous",
        confidence=0.94,
        changed_paths=["README.md"],
        pr_body_sections={
            "goal": "Refresh docs.",
            "evidence": "Docs opportunity.",
            "entropy_impact": "Expected -1.0 entropy.",
            "verification": "Docs review.",
        },
        required_checks=["docs_review"],
    )
    MaintenancePRPlanOpportunity.objects.create(
        plan=plan,
        maintenance_opportunity_id="opp_docs",
    )

    report = storage_service.load_first_report(analysis)

    assert report["gardening_session_result"] == session.result
    assert len(report["maintenance_pr_plans"]) == 1
    assert report["maintenance_pr_plans"][0]["maintenance_pr_plan_id"] == str(plan.id)
    assert report["maintenance_pr_plans"][0]["maintenance_opportunity_ids"] == ["opp_docs"]


@pytest.mark.django_db
@mock_aws
def test_load_first_report_keeps_empty_session_when_no_completed_session_exists():
    org = _org()
    repo = _repo(org)
    analysis = storage_service.store_analysis(
        organization=org, repository=repo, commit_sha="abc123", artifacts=_artifacts()
    )

    report = storage_service.load_first_report(analysis)

    assert report["gardening_session_result"]["status"] == "not_run"
    assert report["gardening_session_result"]["repository_id"] == str(repo.id)
    assert report["maintenance_pr_plans"] == []
