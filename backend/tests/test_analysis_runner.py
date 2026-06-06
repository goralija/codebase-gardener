from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.utils import timezone
from moto import mock_aws

from apps.accounts.models import CustomerOrganization
from apps.analysis import runner, storage_service
from apps.analysis.models import RepositoryAnalysis
from apps.common import storage
from apps.github_app.models import GitHubInstallation
from apps.repositories.models import ManagedRepository


BUCKET = "gardener-analysis"


@pytest.fixture(autouse=True)
def _storage_settings(settings):
    settings.OBJECT_STORAGE_ENDPOINT_URL = None
    settings.OBJECT_STORAGE_ACCESS_KEY = "local"
    settings.OBJECT_STORAGE_SECRET_KEY = "localpass123"
    settings.OBJECT_STORAGE_BUCKET = BUCKET
    settings.OBJECT_STORAGE_REGION = "us-east-1"
    storage.reset_client_cache()
    yield
    storage.reset_client_cache()


@pytest.mark.django_db
@mock_aws
def test_run_repository_analysis_stores_artifacts_and_cleans_clone(monkeypatch, caplog):
    repository = create_repository(1)
    clone_roots: list[Path] = []
    _stub_analysis_chain(monkeypatch, repository)
    caplog.set_level(logging.INFO, logger="apps.analysis.runner")

    def clone(_repository, token, destination):
        assert token == "installation-token"
        destination.mkdir(parents=True)
        (destination / "README.md").write_text("# test\n", encoding="utf-8")
        runner.subprocess.run(
            ["git", "-C", str(destination), "init"],
            check=True,
            capture_output=True,
            text=True,
        )
        runner.subprocess.run(
            ["git", "-C", str(destination), "add", "."],
            check=True,
            capture_output=True,
            text=True,
        )
        runner.subprocess.run(
            [
                "git",
                "-C",
                str(destination),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-m",
                "Initial",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        clone_roots.append(destination.parent)

    result = runner.run_repository_analysis(
        repository=repository,
        client=FakeGitHubClient(),
        clone_repository=clone,
    )

    assert RepositoryAnalysis.objects.filter(repository=repository).count() == 1
    assert result.analysis.commit_sha == "abc123"
    report = storage_service.load_first_report(result.analysis)
    assert report["repository_constitution"]["repository_id"] == str(repository.id)
    assert report["analysis_snapshot"]["repository_id"] == str(repository.id)
    assert report["entropy_report"]["score"]["overall"] == 12.3
    assert report["maintenance_opportunities"][0]["maintenance_opportunity_id"] == "opp_docs"
    assert clone_roots and not clone_roots[0].exists()
    messages = [record.message for record in caplog.records]
    assert "analysis.snapshot.completed" in messages
    assert "analysis.run.completed" in messages


@pytest.mark.django_db
def test_run_repository_analysis_cleans_clone_on_failure(monkeypatch):
    repository = create_repository(1)
    clone_roots: list[Path] = []

    def clone(_repository, _token, destination):
        destination.mkdir(parents=True)
        clone_roots.append(destination.parent)
        raise runner.AnalysisRunError("observe", "clone failed")

    with pytest.raises(runner.AnalysisRunError):
        runner.run_repository_analysis(
            repository=repository,
            client=FakeGitHubClient(),
            clone_repository=clone,
        )

    assert clone_roots and not clone_roots[0].exists()
    assert not RepositoryAnalysis.objects.filter(repository=repository).exists()


@pytest.mark.django_db
def test_run_repository_analysis_rejects_empty_repository():
    repository = create_repository(1)

    def clone(_repository, _token, destination):
        destination.mkdir(parents=True)
        runner.subprocess.run(
            ["git", "-C", str(destination), "init"],
            check=True,
            capture_output=True,
            text=True,
        )

    with pytest.raises(runner.AnalysisRunError) as excinfo:
        runner.run_repository_analysis(
            repository=repository,
            client=FakeGitHubClient(),
            clone_repository=clone,
        )

    assert excinfo.value.phase == "observe"
    assert str(excinfo.value) == "Repository has no commits on the cloned default branch."
    assert not RepositoryAnalysis.objects.filter(repository=repository).exists()


@pytest.mark.django_db
def test_run_repository_analysis_rejects_inactive_repository():
    repository = create_repository(1)
    ManagedRepository.objects.filter(id=repository.id).update(unselected_at=timezone.now())

    with pytest.raises(runner.AnalysisRunError) as excinfo:
        runner.run_repository_analysis(repository=repository, client=FakeGitHubClient())

    assert excinfo.value.phase == "observe"
    assert str(excinfo.value) == "Repository is not active."


def test_clone_repository_redacts_token_from_errors(monkeypatch, tmp_path, settings):
    settings.GITHUB_WEB_BASE_URL = "https://github.com"
    repository = SimpleNamespace(full_name="acme/api")

    def fail_clone(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=128,
            stdout="",
            stderr="fatal: https://x-access-token:secret-token@github.com/acme/api.git",
        )

    monkeypatch.setattr(runner.subprocess, "run", fail_clone)

    with pytest.raises(runner.AnalysisRunError) as excinfo:
        runner._clone_repository(repository, "secret-token", tmp_path / "repo")

    assert "secret-token" not in str(excinfo.value)
    assert "[redacted]" in str(excinfo.value)


class FakeGitHubClient:
    def create_installation_token(self, installation_id):
        assert installation_id
        return "installation-token"


def _stub_analysis_chain(monkeypatch, repository):
    index = SimpleNamespace(
        knowledge_graph={"nodes": []},
        health={"metrics": []},
        dead_code=[],
    )
    snapshot = {
        "schema_version": "1.0",
        "analysis_snapshot_id": "snap_abc123",
        "repository_id": str(repository.id),
        "commit_sha": "abc123",
        "created_at": "2026-06-06T00:00:00Z",
        "logical_systems": [],
        "signals": {
            "dependency_cycles": [],
            "hotspots": [],
            "dead_code_candidates": [],
            "ownership_risks": [],
            "test_gaps": [],
            "dependency_risks": [],
            "ci_failures": [],
        },
        "constitution_id": f"constitution_{repository.id}",
    }
    constitution = {
        "schema_version": "1.0",
        "repository_id": str(repository.id),
        "commit_sha": "abc123",
        "completeness_score": 1.0,
        "protected_modules": [],
        "never_touch": [],
        "allowed_fixes": {"autonomous": [], "assisted": [], "advisory": []},
        "architecture_boundaries": [],
        "ignored_paths": [],
        "open_questions": [],
    }
    entropy = {
        "schema_version": "1.0",
        "entropy_report_id": "entropy_abc123",
        "repository_id": str(repository.id),
        "analysis_snapshot_id": "snap_abc123",
        "commit_sha": "abc123",
        "score": {
            "overall": 12.3,
            "classification": "healthy",
            "components": {
                "architecture": 0,
                "maintainability": 0,
                "knowledge": 0,
                "testing": 0,
                "dependency": 0,
                "operational": 0,
            },
        },
        "scopes": [],
        "top_contributors": [],
        "forecast": {
            "horizon_days": 90,
            "predicted_overall": 12.3,
            "confidence": 0.5,
            "summary": "Stable.",
        },
    }
    opportunities = [
        {
            "schema_version": "1.0",
            "maintenance_opportunity_id": "opp_docs",
            "repository_id": str(repository.id),
            "analysis_snapshot_id": "snap_abc123",
            "category": "docs",
            "risk_tier": "tier_1_autonomous",
            "confidence": 0.94,
            "title": "Refresh docs",
            "summary": "Docs need refresh.",
            "affected_paths": ["README.md"],
            "blocked_by": [],
            "expected_entropy_delta": -1.0,
            "required_checks": ["docs_review"],
            "evidence": [],
        }
    ]

    monkeypatch.setattr(runner, "index_repository", lambda *_args, **_kwargs: index)
    monkeypatch.setattr(
        runner,
        "discover_source_truth",
        lambda *_args, **_kwargs: SimpleNamespace(files=()),
    )
    monkeypatch.setattr(runner, "build_analysis_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(
        runner,
        "build_repository_constitution",
        lambda *_args, **_kwargs: constitution,
    )
    monkeypatch.setattr(runner, "build_entropy_report", lambda *_args, **_kwargs: entropy)
    monkeypatch.setattr(
        runner,
        "generate_maintenance_opportunities",
        lambda *_args, **_kwargs: opportunities,
    )


def create_repository(identifier: int) -> ManagedRepository:
    organization = CustomerOrganization.objects.create(
        name=f"Organization {identifier}",
        github_account_id=1000 + identifier,
        github_login=f"org-{identifier}",
        github_account_type=CustomerOrganization.GitHubAccountType.ORGANIZATION,
    )
    installation = GitHubInstallation.objects.create(
        organization=organization,
        github_installation_id=2000 + identifier,
        github_account_id=organization.github_account_id,
        github_account_login=organization.github_login,
        github_account_type=GitHubInstallation.GitHubAccountType.ORGANIZATION,
        repository_selection=GitHubInstallation.RepositorySelection.SELECTED,
        permissions={"metadata": "read", "contents": "read"},
        events=["installation", "repository"],
    )
    return ManagedRepository.objects.create(
        organization=organization,
        github_installation=installation,
        github_repository_id=3000 + identifier,
        name=f"repo-{identifier}",
        full_name=f"org-{identifier}/repo-{identifier}",
        owner_login=f"org-{identifier}",
        private=True,
        default_branch="main",
        html_url=f"https://github.com/org-{identifier}/repo-{identifier}",
    )
