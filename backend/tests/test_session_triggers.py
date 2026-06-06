from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import CustomerOrganization, Membership
from apps.common.models import AuditEvent
from apps.github_app.models import GitHubInstallation
from apps.repositories.models import ManagedRepository
from apps.sessions.models import GardeningSession
from apps.triggers import registry
from apps.triggers.models import RepositoryCommitTracker
from apps.triggers.policy import TriggerNotPermittedError, ensure_trigger_permitted
from apps.triggers.service import (
    SessionEnqueueError,
    enqueue_session_for_trigger,
    evaluate_push_triggers,
    trigger_manual_session,
)
from apps.triggers.tasks import dispatch_scheduled_sessions
from apps.triggers.thresholds import (
    DEFAULT_COMMIT_THRESHOLD,
    changed_paths_hit_protected,
    commit_threshold,
)

User = get_user_model()


@pytest.fixture(autouse=True)
def _eager_celery(settings, monkeypatch):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    monkeypatch.setattr(
        "apps.sessions.tasks.run_repository_analysis",
        lambda repository: _analysis_result(),
    )
    monkeypatch.setattr(
        "apps.sessions.tasks.storage_service.load_first_report",
        lambda _analysis: _first_report_fixture(),
    )
    monkeypatch.setattr(
        "apps.sessions.tasks.maybe_open_constitution_pr",
        lambda **_kwargs: {"created": False},
    )


# --------------------------------------------------------------------------- #
# Creation
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_each_trigger_kind_enqueues_scoped_session():
    repository = create_repository(1)
    kinds = [
        registry.SCHEDULE,
        registry.N_COMMITS,
        registry.RISKY_MODULE,
        registry.PR_OPENED,
        registry.CI_FAILURE,
        registry.PUSH,
        registry.FIRST_SCAN,
    ]
    for index, kind in enumerate(kinds):
        result = enqueue_session_for_trigger(
            repository=repository,
            kind=kind,
            subject_type="subject",
            subject_id=f"subject-{index}",
            source="test",
        )
        assert result["deduped"] is False
        session = GardeningSession.objects.get(id=result["gardening_session_id"])
        assert session.repository_id == repository.id
        assert session.trigger["type"] == kind
        assert session.trigger["subject_id"] == f"subject-{index}"
        assert session.task_id


@pytest.mark.django_db
def test_unknown_trigger_kind_rejected():
    repository = create_repository(1)
    with pytest.raises(ValueError):
        enqueue_session_for_trigger(
            repository=repository,
            kind="not_a_kind",
            subject_type="x",
            subject_id="y",
            source="test",
        )


# --------------------------------------------------------------------------- #
# Deduplication
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_active_session_is_deduplicated(monkeypatch):
    _keep_sessions_queued(monkeypatch)
    repository = create_repository(1)
    first = enqueue_session_for_trigger(
        repository=repository,
        kind=registry.SCHEDULE,
        subject_type="schedule",
        subject_id="2026-06-06",
        source="schedule",
    )
    second = enqueue_session_for_trigger(
        repository=repository,
        kind=registry.SCHEDULE,
        subject_type="schedule",
        subject_id="2026-06-06",
        source="schedule",
    )
    assert second["deduped"] is True
    assert second["gardening_session_id"] == first["gardening_session_id"]
    assert GardeningSession.objects.filter(repository=repository).count() == 1


@pytest.mark.django_db
def test_completed_session_does_not_dedupe_new_trigger():
    repository = create_repository(1)
    first = enqueue_session_for_trigger(
        repository=repository,
        kind=registry.SCHEDULE,
        subject_type="schedule",
        subject_id="2026-06-06",
        source="schedule",
    )
    GardeningSession.objects.filter(id=first["gardening_session_id"]).update(
        status=GardeningSession.Status.COMPLETED
    )
    second = enqueue_session_for_trigger(
        repository=repository,
        kind=registry.SCHEDULE,
        subject_type="schedule",
        subject_id="2026-06-06",
        source="schedule",
    )
    assert second["deduped"] is False
    assert GardeningSession.objects.filter(repository=repository).count() == 2


# --------------------------------------------------------------------------- #
# Permission policy (manual)
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_manual_trigger_requires_actor():
    repository = create_repository(1)
    with pytest.raises(TriggerNotPermittedError):
        enqueue_session_for_trigger(
            repository=repository,
            kind=registry.MANUAL,
            subject_type="manual",
            subject_id="x",
            source="manual",
            actor=None,
        )


@pytest.mark.django_db
def test_manual_trigger_rejects_non_member():
    repository = create_repository(1)
    outsider = User.objects.create_user(email="outsider@example.com", password="pw")
    with pytest.raises(TriggerNotPermittedError):
        trigger_manual_session(repository=repository, actor=outsider)
    assert not GardeningSession.objects.filter(repository=repository).exists()


@pytest.mark.django_db
def test_manual_trigger_rejects_insufficient_role():
    repository = create_repository(1)
    viewer = User.objects.create_user(email="viewer@example.com", password="pw")
    Membership.objects.create(
        user=viewer,
        organization=repository.organization,
        role=Membership.Role.VIEWER,
    )
    with pytest.raises(TriggerNotPermittedError):
        trigger_manual_session(repository=repository, actor=viewer)


@pytest.mark.django_db
def test_manual_trigger_allows_maintainer_and_audits():
    repository = create_repository(1)
    maintainer = User.objects.create_user(email="maint@example.com", password="pw")
    Membership.objects.create(
        user=maintainer,
        organization=repository.organization,
        role=Membership.Role.MAINTAINER,
    )
    result = trigger_manual_session(repository=repository, actor=maintainer)
    assert result["deduped"] is False
    session = GardeningSession.objects.get(id=result["gardening_session_id"])
    assert session.trigger["type"] == registry.MANUAL
    assert session.trigger["subject_id"] == str(maintainer.id)
    audit = AuditEvent.objects.get(
        event_type=AuditEvent.EventType.SESSION_TRIGGER_ENQUEUED
    )
    assert audit.actor_id == maintainer.id
    assert audit.metadata["kind"] == registry.MANUAL


@pytest.mark.django_db
def test_inactive_repository_blocks_trigger():
    repository = create_repository(1)
    from django.utils import timezone

    ManagedRepository.objects.filter(id=repository.id).update(unselected_at=timezone.now())
    repository.refresh_from_db()
    with pytest.raises(TriggerNotPermittedError):
        ensure_trigger_permitted(repository=repository, kind=registry.SCHEDULE)


# --------------------------------------------------------------------------- #
# Threshold helpers
# --------------------------------------------------------------------------- #


def test_commit_threshold_defaults_and_constitution():
    assert commit_threshold(None) == DEFAULT_COMMIT_THRESHOLD
    assert commit_threshold({}) == DEFAULT_COMMIT_THRESHOLD
    assert commit_threshold({"risk_policies": {"commit_session_threshold": 3}}) == 3
    assert commit_threshold({"n_commits_threshold": 5}) == 5


def test_changed_paths_hit_protected_constitution_and_fallback():
    constitution = {
        "protected_modules": [{"name": "billing", "paths": ["src/billing/*"]}],
    }
    assert changed_paths_hit_protected(["src/billing/charge.py"], constitution)
    assert changed_paths_hit_protected(["src/util.py"], constitution) is None
    # Fallback used only when no protected definitions exist.
    assert changed_paths_hit_protected(["app/auth/login.py"], {})
    assert changed_paths_hit_protected(["app/auth/login.py"], constitution) is None
    assert changed_paths_hit_protected(["README.md"], {}) is None


# --------------------------------------------------------------------------- #
# After-N-commits trigger
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_n_commits_trigger_fires_only_at_threshold():
    repository = create_repository(1)
    ref = "refs/heads/main"
    constitution = {"risk_policies": {"commit_session_threshold": 3}}

    first = evaluate_push_triggers(
        repository=repository,
        ref=ref,
        payload=push_payload(commit_count=2),
        base_trigger_extra={"source": "github_webhook"},
        constitution=constitution,
    )
    assert not any(r for r in first if _kind_of(r) == registry.N_COMMITS)
    assert RepositoryCommitTracker.objects.get(repository=repository).commits_since_session == 2

    second = evaluate_push_triggers(
        repository=repository,
        ref=ref,
        payload=push_payload(commit_count=1),
        base_trigger_extra={"source": "github_webhook"},
        constitution=constitution,
    )
    assert any(_kind_of(r) == registry.N_COMMITS for r in second)
    # Counter reset after firing.
    assert RepositoryCommitTracker.objects.get(repository=repository).commits_since_session == 0


@pytest.mark.django_db
def test_risky_module_trigger_fires_for_protected_paths():
    repository = create_repository(1)
    ref = "refs/heads/main"
    constitution = {"protected_modules": [{"name": "auth", "paths": ["src/auth/*"]}]}

    payload = push_payload(commit_count=1, modified=["src/auth/session.py"])
    results = evaluate_push_triggers(
        repository=repository,
        ref=ref,
        payload=payload,
        base_trigger_extra={"source": "github_webhook"},
        constitution=constitution,
    )
    risky = [r for r in results if _kind_of(r) == registry.RISKY_MODULE]
    assert len(risky) == 1
    session = GardeningSession.objects.get(id=risky[0]["gardening_session_id"])
    assert "src/auth/session.py" in session.trigger["reason"]

    safe = evaluate_push_triggers(
        repository=repository,
        ref=ref,
        payload=push_payload(commit_count=1, modified=["docs/readme.md"]),
        base_trigger_extra={"source": "github_webhook"},
        constitution=constitution,
    )
    assert not any(_kind_of(r) == registry.RISKY_MODULE for r in safe)


# --------------------------------------------------------------------------- #
# Scheduled dispatch
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_dispatch_scheduled_sessions_one_per_active_repo(monkeypatch):
    _keep_sessions_queued(monkeypatch)
    active_one = create_repository(1)
    active_two = create_repository(2)
    inactive = create_repository(3)
    from django.utils import timezone

    ManagedRepository.objects.filter(id=inactive.id).update(unselected_at=timezone.now())

    result = dispatch_scheduled_sessions()
    assert result["dispatched"] == 2

    assert GardeningSession.objects.filter(repository=active_one).count() == 1
    assert GardeningSession.objects.filter(repository=active_two).count() == 1
    assert GardeningSession.objects.filter(repository=inactive).count() == 0

    # Second run within the same period dedupes.
    second = dispatch_scheduled_sessions()
    assert second["dispatched"] == 0
    assert second["deduped"] == 2


@pytest.mark.django_db
def test_enqueue_failure_marks_session_failed(monkeypatch):
    repository = create_repository(1)

    def boom(_session_id):
        raise RuntimeError("broker down")

    monkeypatch.setattr("apps.triggers.service.run_gardening_session.delay", boom)

    with pytest.raises(SessionEnqueueError):
        enqueue_session_for_trigger(
            repository=repository,
            kind=registry.SCHEDULE,
            subject_type="schedule",
            subject_id="2026-06-06",
            source="schedule",
        )
    session = GardeningSession.objects.get(repository=repository)
    assert session.status == GardeningSession.Status.FAILED
    assert session.result["status"] == "failed"
    audit = AuditEvent.objects.get(
        event_type=AuditEvent.EventType.SESSION_TRIGGER_FAILED
    )
    assert audit.repository_id == repository.id
    assert audit.metadata["kind"] == registry.SCHEDULE
    assert "broker down" in audit.metadata["error"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_audit_failure_does_not_mask_trigger_outcome(monkeypatch):
    repository = create_repository(1)
    maintainer = User.objects.create_user(email="maint@example.com", password="pw")
    Membership.objects.create(
        user=maintainer,
        organization=repository.organization,
        role=Membership.Role.MAINTAINER,
    )

    def boom(*_args, **_kwargs):
        raise RuntimeError("audit table unavailable")

    monkeypatch.setattr(AuditEvent.objects, "create", boom)

    result = trigger_manual_session(repository=repository, actor=maintainer)
    assert result["deduped"] is False
    assert GardeningSession.objects.filter(id=result["gardening_session_id"]).exists()


@pytest.mark.django_db
def test_enqueue_failure_still_raises_when_audit_also_fails(monkeypatch):
    repository = create_repository(1)

    def boom_delay(_session_id):
        raise RuntimeError("broker down")

    def boom_audit(*_args, **_kwargs):
        raise RuntimeError("audit table unavailable")

    monkeypatch.setattr("apps.triggers.service.run_gardening_session.delay", boom_delay)
    monkeypatch.setattr(AuditEvent.objects, "create", boom_audit)

    with pytest.raises(SessionEnqueueError):
        enqueue_session_for_trigger(
            repository=repository,
            kind=registry.SCHEDULE,
            subject_type="schedule",
            subject_id="2026-06-06",
            source="schedule",
        )


def _keep_sessions_queued(monkeypatch):
    """Stop the eager worker from running so sessions stay QUEUED for dedup."""

    class _FakeResult:
        id = "fake-task-id"

    monkeypatch.setattr(
        "apps.triggers.service.run_gardening_session.delay",
        lambda _session_id: _FakeResult(),
    )


def _kind_of(result: dict) -> str:
    return GardeningSession.objects.get(id=result["gardening_session_id"]).trigger["type"]


def _first_report_fixture() -> dict:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "fixtures/contracts/first_report_fixture.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _analysis_result():
    return SimpleNamespace(analysis=object(), artifacts={"constitution": {"open_questions": []}})


def push_payload(*, commit_count: int, modified=None) -> dict:
    commits = []
    for index in range(commit_count):
        commit = {"added": [], "modified": [], "removed": []}
        if modified and index == 0:
            commit["modified"] = list(modified)
        commits.append(commit)
    return {"ref": "refs/heads/main", "commits": commits, "after": "abc123"}


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
