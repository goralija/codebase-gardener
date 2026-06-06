import pytest

from apps.common.models import AuditEvent
from apps.maintenance_prs.models import MaintenancePRPlan
from apps.profiles.learning import (
    Outcome,
    OutcomeLearningError,
    find_plan_for_pull_request,
    record_pr_outcome,
)
from apps.profiles.models import GardenerProfile
from tests.test_product_models import (
    create_installation,
    create_organization,
    create_repository,
)


def demo_repository(identifier: int = 700):
    organization = create_organization(identifier)
    installation = create_installation(organization, identifier)
    return create_repository(organization, installation, identifier)


def make_plan(
    repository,
    *,
    category="docs",
    pr_number=42,
    branch="gardener/docs-refresh",
    title="Refresh docs",
    changed_paths=None,
):
    return MaintenancePRPlan.objects.create(
        repository=repository,
        gardening_session_id="session_learn",
        branch_name=branch,
        title=title,
        category=category,
        risk_tier="tier_1_autonomous",
        confidence=0.95,
        confidence_threshold=0.9,
        changed_paths=changed_paths or ["docs/a.md"],
        pr_body_sections={},
        required_checks=[],
        created_pr_number=pr_number,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("outcome", "field"),
    [
        (Outcome.MERGED, "accepted_categories"),
        (Outcome.ACCEPTED, "accepted_categories"),
        (Outcome.REJECTED, "rejected_categories"),
        (Outcome.CLOSED, "rejected_categories"),
        (Outcome.REVERTED, "reverted_categories"),
    ],
)
def test_outcome_maps_category_to_profile_field(outcome, field):
    repository = demo_repository()
    plan = make_plan(repository, category="docs")

    result = record_pr_outcome(plan=plan, outcome=outcome)

    profile = GardenerProfile.objects.get(repository=repository)
    assert result.recorded is True
    assert getattr(profile, field) == ["docs"]
    assert profile.updated_from_pr_outcomes == [
        {"maintenance_pr_id": str(plan.id), "outcome": outcome, "category": "docs"}
    ]


@pytest.mark.django_db
def test_edited_outcome_records_review_preference_not_category():
    repository = demo_repository()
    plan = make_plan(repository, category="docs")

    record_pr_outcome(plan=plan, outcome=Outcome.EDITED)

    profile = GardenerProfile.objects.get(repository=repository)
    assert profile.accepted_categories == []
    assert profile.rejected_categories == []
    assert len(profile.review_preferences) == 1
    assert "docs" in profile.review_preferences[0]


@pytest.mark.django_db
def test_failed_outcome_is_ranking_only_signal():
    repository = demo_repository()
    plan = make_plan(repository, category="docs")

    record_pr_outcome(plan=plan, outcome=Outcome.FAILED)

    profile = GardenerProfile.objects.get(repository=repository)
    assert profile.accepted_categories == []
    assert profile.rejected_categories == []
    assert profile.reverted_categories == []
    assert profile.review_preferences == []
    # Still logged for traceability.
    assert profile.updated_from_pr_outcomes[0]["outcome"] == Outcome.FAILED


@pytest.mark.django_db
def test_reverted_outcome_learns_protected_patterns():
    repository = demo_repository()
    plan = make_plan(repository, category="docs", changed_paths=["docs/a.md", "docs/b.md"])

    record_pr_outcome(plan=plan, outcome=Outcome.REVERTED)

    profile = GardenerProfile.objects.get(repository=repository)
    patterns = {entry["pattern"] for entry in profile.learned_protected_patterns}
    assert patterns == {"docs/a.md", "docs/b.md"}
    assert profile.reverted_categories == ["docs"]


@pytest.mark.django_db
def test_record_outcome_is_idempotent_on_redelivery():
    repository = demo_repository()
    plan = make_plan(repository, category="docs")

    first = record_pr_outcome(plan=plan, outcome=Outcome.MERGED)
    second = record_pr_outcome(plan=plan, outcome=Outcome.MERGED)

    profile = GardenerProfile.objects.get(repository=repository)
    assert first.recorded is True
    assert second.recorded is False
    assert profile.accepted_categories == ["docs"]
    assert len(profile.updated_from_pr_outcomes) == 1


@pytest.mark.django_db
def test_distinct_outcomes_for_same_plan_are_each_recorded():
    repository = demo_repository()
    plan = make_plan(repository, category="docs")

    record_pr_outcome(plan=plan, outcome=Outcome.MERGED)
    record_pr_outcome(plan=plan, outcome=Outcome.REVERTED)

    profile = GardenerProfile.objects.get(repository=repository)
    assert profile.accepted_categories == ["docs"]
    assert profile.reverted_categories == ["docs"]
    assert {entry["outcome"] for entry in profile.updated_from_pr_outcomes} == {
        Outcome.MERGED,
        Outcome.REVERTED,
    }


@pytest.mark.django_db
def test_record_outcome_emits_audit_events():
    repository = demo_repository()
    plan = make_plan(repository, category="docs")

    record_pr_outcome(plan=plan, outcome=Outcome.MERGED)

    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.MAINTENANCE_PR_OUTCOME_RECORDED,
        repository=repository,
    ).exists()
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.GARDENER_PROFILE_UPDATED,
        repository=repository,
    ).exists()


@pytest.mark.django_db
def test_unsupported_outcome_raises():
    repository = demo_repository()
    plan = make_plan(repository)

    with pytest.raises(OutcomeLearningError):
        record_pr_outcome(plan=plan, outcome="exploded")


@pytest.mark.django_db
def test_profile_contract_validates_against_schema():
    repository = demo_repository()
    plan = make_plan(repository, category="docs")
    record_pr_outcome(plan=plan, outcome=Outcome.MERGED)

    profile = GardenerProfile.objects.get(repository=repository)
    contract = profile.to_contract()  # raises if it does not match the schema

    assert contract["schema_version"] == "1.0"
    assert contract["repository_id"] == str(repository.id)
    assert contract["accepted_categories"] == ["docs"]


@pytest.mark.django_db
def test_find_plan_matches_by_pr_number_then_branch():
    repository = demo_repository()
    plan = make_plan(repository, pr_number=99, branch="gardener/docs-x")

    by_number = find_plan_for_pull_request(repository=repository, pr_number=99)
    by_branch = find_plan_for_pull_request(
        repository=repository, branch_name="gardener/docs-x"
    )
    missing = find_plan_for_pull_request(repository=repository, pr_number=1234)

    assert by_number == plan
    assert by_branch == plan
    assert missing is None


@pytest.mark.django_db(transaction=True)
def test_profile_change_enqueues_profile_sync(monkeypatch):
    repository = demo_repository()
    plan = make_plan(repository, category="docs")

    enqueued = []
    monkeypatch.setattr(
        "apps.profiles.tasks.sync_profile_pr.delay",
        lambda repository_id: enqueued.append(repository_id),
    )

    record_pr_outcome(plan=plan, outcome=Outcome.MERGED)

    assert enqueued == [str(repository.id)]


@pytest.mark.django_db(transaction=True)
def test_log_only_outcome_does_not_enqueue_profile_sync(monkeypatch):
    repository = demo_repository()
    # No category => no ranking signal changes, so it is log-only.
    plan = make_plan(repository, category="")

    enqueued = []
    monkeypatch.setattr(
        "apps.profiles.tasks.sync_profile_pr.delay",
        lambda repository_id: enqueued.append(repository_id),
    )

    record_pr_outcome(plan=plan, outcome=Outcome.FAILED)

    assert enqueued == []
