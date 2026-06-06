import json
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from jsonschema import Draft202012Validator
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from apps.billing.models import Subscription
from apps.common.models import AuditEvent
from apps.maintenance_prs.models import MaintenancePRPlan
from apps.sessions.models import GardeningSession
from apps.triggers.models import RepositoryAutomationPolicy
from tests.test_product_models import (
    create_installation,
    create_organization,
    create_repository,
)

User = get_user_model()


@pytest.mark.django_db
def test_owner_can_view_and_update_repository_automation_policy():
    owner = User.objects.create_user("owner@example.com", password="secret")
    repository = create_repo_with_member(owner, Membership.Role.OWNER)
    Subscription.objects.create(
        organization=repository.organization,
        autonomous_pr_add_on_enabled=True,
    )
    GardeningSession.objects.create(
        repository=repository,
        trigger={"type": "schedule", "subject_id": "2026-06-06"},
    )
    MaintenancePRPlan.objects.create(
        repository=repository,
        gardening_session_id="session-1",
        branch_name="gardener/docs-refresh",
        title="Refresh docs",
        category="docs",
        risk_tier="tier_1_autonomous",
        confidence=0.94,
        changed_paths=["docs/api.md"],
        pr_body_sections={"goal": "Refresh stale docs."},
        required_checks=["docs_review"],
    )
    client = APIClient()
    client.force_authenticate(user=owner)

    get_response = client.get(automation_url(repository))

    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["schema_version"] == "1.0"
    assert_repository_automation_settings_contract(payload)
    assert payload["repository"]["full_name"] == repository.full_name
    assert payload["policy"]["autonomy_mode"] == "autonomous"
    assert payload["policy"]["scheduled_trigger_enabled"] is True
    assert payload["effective"] == {
        "autonomous_pr_add_on_enabled": True,
        "can_create_autonomous_prs": True,
        "pr_creation_status": "Autonomous PR creation is enabled.",
        "default_commit_threshold": 10,
        "confidence_threshold": 0.9,
    }
    assert payload["permissions"] == {
        "can_edit": True,
        "can_trigger_manual_session": True,
    }
    assert payload["recent_sessions"][0]["trigger"]["type"] == "schedule"
    assert payload["recent_pr_plans"][0]["title"] == "Refresh docs"

    patch_response = client.patch(
        automation_url(repository),
        {
            "autonomy_mode": "conservative",
            "scheduled_trigger_enabled": False,
            "commit_threshold": 3,
        },
        format="json",
    )

    assert patch_response.status_code == 200
    updated = patch_response.json()
    assert updated["policy"]["autonomy_mode"] == "conservative"
    assert updated["policy"]["scheduled_trigger_enabled"] is False
    assert updated["policy"]["commit_threshold"] == 3
    assert updated["effective"]["can_create_autonomous_prs"] is False
    audit = AuditEvent.objects.get(
        event_type=AuditEvent.EventType.AUTOMATION_POLICY_UPDATED
    )
    assert audit.actor_id == owner.id
    assert audit.repository_id == repository.id
    assert audit.metadata["changed_fields"] == [
        "autonomy_mode",
        "scheduled_trigger_enabled",
        "commit_threshold",
    ]


@pytest.mark.django_db
def test_viewer_can_view_but_not_update_repository_automation_policy():
    viewer = User.objects.create_user("viewer@example.com", password="secret")
    repository = create_repo_with_member(viewer, Membership.Role.VIEWER)
    client = APIClient()
    client.force_authenticate(user=viewer)

    get_response = client.get(automation_url(repository))
    patch_response = client.patch(
        automation_url(repository),
        {"manual_trigger_enabled": False},
        format="json",
    )

    assert get_response.status_code == 200
    assert get_response.json()["permissions"] == {
        "can_edit": False,
        "can_trigger_manual_session": False,
    }
    assert patch_response.status_code == 403


@pytest.mark.django_db
def test_manual_trigger_endpoint_enqueues_session(monkeypatch):
    maintainer = User.objects.create_user("maintainer@example.com", password="secret")
    repository = create_repo_with_member(maintainer, Membership.Role.MAINTAINER)

    class FakeResult:
        id = "task-1"

    monkeypatch.setattr(
        "apps.triggers.service.run_gardening_session.delay",
        lambda _session_id: FakeResult(),
    )
    client = APIClient()
    client.force_authenticate(user=maintainer)

    response = client.post(f"{automation_url(repository)}trigger/", {}, format="json")

    assert response.status_code == 202
    session = GardeningSession.objects.get(repository=repository)
    assert session.trigger["type"] == "manual"
    assert session.trigger["source_view"] == "repository_automation"
    assert response.json()["trigger"]["gardening_session_id"] == str(session.id)


@pytest.mark.django_db
def test_manual_trigger_endpoint_respects_disabled_policy(monkeypatch):
    maintainer = User.objects.create_user("maintainer@example.com", password="secret")
    repository = create_repo_with_member(maintainer, Membership.Role.MAINTAINER)
    policy = RepositoryAutomationPolicy.get_or_create_for_repository(repository)
    policy.manual_trigger_enabled = False
    policy.save(update_fields=["manual_trigger_enabled", "updated_at"])
    client = APIClient()
    client.force_authenticate(user=maintainer)

    response = client.post(f"{automation_url(repository)}trigger/", {}, format="json")

    assert response.status_code == 403
    assert response.json()["code"] == "trigger_not_permitted"
    assert not GardeningSession.objects.filter(repository=repository).exists()


def create_repo_with_member(user, role):
    organization = create_organization(1)
    Membership.objects.create(user=user, organization=organization, role=role)
    installation = create_installation(organization, 1)
    return create_repository(organization, installation, 1)


def automation_url(repository):
    return (
        f"/api/v1/organizations/{repository.organization_id}/repositories/"
        f"{repository.id}/automation/"
    )


def assert_repository_automation_settings_contract(payload):
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "schemas"
        / "repository_automation_settings.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: error.json_path,
    )
    assert not errors, [f"{error.json_path}: {error.message}" for error in errors]
