from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.utils import timezone

from apps.billing.models import RepositoryComplexity, Subscription
from apps.common import storage
from apps.common.models import AuditEvent


JsonObject = dict[str, Any]

INPUT_FIELDS = ("loc", "module_count", "contributor_count")
LOC_BANDS = (25_000, 100_000, 250_000)
MODULE_BANDS = (3, 8, 20)
CONTRIBUTOR_BANDS = (5, 20, 50)
SCORE_VALUES = (0.0, 0.33, 0.66, 1.0)
AUTONOMOUS_PR_ADD_ON_DISABLED_REASON = (
    "Autonomous PR add-on is disabled for this organization."
)


@dataclass(frozen=True)
class ComplexityCalculation:
    input_status: str
    loc: int | None
    module_count: int | None
    contributor_count: int | None
    loc_score: float
    module_score: float
    contributor_score: float
    weighted_score: float
    multiplier: float
    missing_inputs: list[str]
    calculation_version: str = RepositoryComplexity.CALCULATION_VERSION


def calculate_complexity(
    *,
    loc: int | None,
    module_count: int | None,
    contributor_count: int | None,
) -> ComplexityCalculation:
    inputs = {
        "loc": _positive_int_or_none(loc),
        "module_count": _positive_int_or_none(module_count),
        "contributor_count": _positive_int_or_none(contributor_count),
    }
    missing_inputs = [name for name, value in inputs.items() if value is None]
    input_status = _input_status(missing_inputs)
    loc_score = _band_score(inputs["loc"], LOC_BANDS)
    module_score = _band_score(inputs["module_count"], MODULE_BANDS)
    contributor_score = _band_score(inputs["contributor_count"], CONTRIBUTOR_BANDS)

    if input_status == RepositoryComplexity.InputStatus.COMPLETE:
        weighted_score = round((loc_score + module_score + contributor_score) / 3, 2)
        multiplier = round(1 + (2 * weighted_score), 2)
    else:
        weighted_score = 0.0
        multiplier = 1.0

    return ComplexityCalculation(
        input_status=input_status,
        loc=inputs["loc"],
        module_count=inputs["module_count"],
        contributor_count=inputs["contributor_count"],
        loc_score=loc_score,
        module_score=module_score,
        contributor_score=contributor_score,
        weighted_score=weighted_score,
        multiplier=multiplier,
        missing_inputs=missing_inputs,
    )


def calculate_complexity_from_artifacts(artifacts: JsonObject) -> ComplexityCalculation:
    return calculate_complexity(
        loc=_extract_loc(artifacts),
        module_count=_extract_module_count(artifacts),
        contributor_count=_extract_contributor_count(artifacts),
    )


def refresh_repository_complexity(
    *,
    repository,
    analysis=None,
    artifacts: JsonObject | None = None,
    actor=None,
) -> RepositoryComplexity:
    analysis = analysis or repository.analyses.order_by("-created_at").first()
    artifacts = artifacts if artifacts is not None else _load_analysis_artifacts(analysis)
    calculation = calculate_complexity_from_artifacts(artifacts)
    previous = RepositoryComplexity.objects.filter(repository=repository).first()
    previous_values = _audit_values(previous)

    complexity, _created = RepositoryComplexity.objects.update_or_create(
        repository=repository,
        defaults={
            "organization": repository.organization,
            "source_analysis": analysis,
            "input_status": calculation.input_status,
            "loc": calculation.loc,
            "module_count": calculation.module_count,
            "contributor_count": calculation.contributor_count,
            "loc_score": calculation.loc_score,
            "module_score": calculation.module_score,
            "contributor_score": calculation.contributor_score,
            "weighted_score": calculation.weighted_score,
            "multiplier": calculation.multiplier,
            "missing_inputs": calculation.missing_inputs,
            "calculation_version": calculation.calculation_version,
            "calculated_at": timezone.now(),
        },
    )
    current_values = _audit_values(complexity)
    if previous_values != current_values:
        AuditEvent.objects.create(
            actor=actor,
            organization=repository.organization,
            repository=repository,
            event_type=AuditEvent.EventType.REPOSITORY_COMPLEXITY_UPDATED,
            source="billing_complexity",
            metadata={
                "previous": previous_values,
                "current": current_values,
                "source_analysis_id": (
                    str(complexity.source_analysis_id)
                    if complexity.source_analysis_id
                    else None
                ),
            },
        )
    return complexity


def repository_complexity_payload(
    complexity: RepositoryComplexity | None,
    *,
    include_details: bool = True,
) -> JsonObject:
    if not include_details:
        return _restricted_payload()
    if complexity is None:
        return _pending_payload()

    return {
        "input_status": complexity.input_status,
        "loc": complexity.loc,
        "module_count": complexity.module_count,
        "contributor_count": complexity.contributor_count,
        "loc_score": complexity.loc_score,
        "module_score": complexity.module_score,
        "contributor_score": complexity.contributor_score,
        "weighted_score": complexity.weighted_score,
        "multiplier": complexity.multiplier,
        "calculation_version": complexity.calculation_version,
        "source_analysis_id": (
            str(complexity.source_analysis_id) if complexity.source_analysis_id else None
        ),
        "source_commit_sha": (
            complexity.source_analysis.commit_sha if complexity.source_analysis_id else None
        ),
        "missing_inputs": complexity.missing_inputs,
        "calculated_at": (
            complexity.calculated_at.isoformat().replace("+00:00", "Z")
            if complexity.calculated_at
            else None
        ),
    }


def get_or_create_subscription(organization) -> Subscription:
    subscription, _created = Subscription.objects.get_or_create(
        organization=organization,
        defaults={
            "plan_code": Subscription.PLAN_CODE,
            "currency": Subscription.CURRENCY,
            "base_price_cents": Subscription.DEFAULT_BASE_PRICE_CENTS,
            "autonomous_pr_add_on_enabled": False,
            "autonomous_pr_add_on_price_cents": (
                Subscription.DEFAULT_AUTONOMOUS_PR_ADD_ON_PRICE_CENTS
            ),
        },
    )
    return subscription


def billing_summary_payload(organization) -> JsonObject:
    subscription = get_or_create_subscription(organization)
    repositories = list(
        organization.managed_repositories.active()
        .select_related("complexity", "complexity__source_analysis")
        .order_by("full_name")
    )
    repository_payloads = [
        _repository_billing_payload(repository, subscription)
        for repository in repositories
    ]
    base_subtotal_cents = sum(
        int(repository["base_monthly_cents"]) for repository in repository_payloads
    )
    add_on_subtotal_cents = (
        subscription.autonomous_pr_add_on_price_cents
        if subscription.autonomous_pr_add_on_enabled
        else 0
    )
    billable_units = sum(
        (Decimal(str(repository["billable_units"])) for repository in repository_payloads),
        Decimal("0"),
    )

    return {
        "subscription": subscription_payload(subscription),
        "billing": {
            "active_managed_repository_count": len(repository_payloads),
            "billable_repository_units": _decimal_number(billable_units),
            "base_subtotal_cents": base_subtotal_cents,
            "autonomous_pr_add_on_subtotal_cents": add_on_subtotal_cents,
            "monthly_estimate_cents": base_subtotal_cents + add_on_subtotal_cents,
        },
        "repositories": repository_payloads,
    }


def subscription_payload(subscription: Subscription) -> JsonObject:
    return {
        "id": str(subscription.id),
        "plan_code": subscription.plan_code,
        "currency": subscription.currency,
        "base_price_cents": subscription.base_price_cents,
        "autonomous_pr_add_on_enabled": subscription.autonomous_pr_add_on_enabled,
        "autonomous_pr_add_on_price_cents": (
            subscription.autonomous_pr_add_on_price_cents
        ),
        "created_at": subscription.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": subscription.updated_at.isoformat().replace("+00:00", "Z"),
    }


def update_subscription(
    *,
    organization,
    values: JsonObject,
    actor=None,
) -> Subscription:
    subscription = get_or_create_subscription(organization)
    previous = _subscription_audit_values(subscription)

    changed_fields: list[str] = []
    for field, value in values.items():
        if getattr(subscription, field) != value:
            setattr(subscription, field, value)
            changed_fields.append(field)

    if not changed_fields:
        return subscription

    update_fields = [*changed_fields, "updated_at"]
    subscription.save(update_fields=update_fields)
    AuditEvent.objects.create(
        actor=actor,
        organization=organization,
        event_type=AuditEvent.EventType.BILLING_SUBSCRIPTION_UPDATED,
        source="billing_api",
        metadata={
            "previous": previous,
            "current": _subscription_audit_values(subscription),
            "changed_fields": changed_fields,
        },
    )
    return subscription


def autonomous_pr_add_on_enabled(organization) -> bool:
    return get_or_create_subscription(organization).autonomous_pr_add_on_enabled


def _repository_billing_payload(repository, subscription: Subscription) -> JsonObject:
    try:
        complexity = repository.complexity
    except RepositoryComplexity.DoesNotExist:
        complexity = None

    multiplier = Decimal(str(complexity.multiplier if complexity else 1.0))
    base_monthly_cents = _price_for_multiplier(
        subscription.base_price_cents,
        multiplier,
    )
    return {
        "id": str(repository.id),
        "full_name": repository.full_name,
        "billable_units": _decimal_number(multiplier),
        "base_monthly_cents": base_monthly_cents,
        "complexity": repository_complexity_payload(complexity, include_details=True),
    }


def _price_for_multiplier(price_cents: int, multiplier: Decimal) -> int:
    cents = Decimal(price_cents) * multiplier
    return int(cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _decimal_number(value: Decimal) -> float:
    normalized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(normalized)


def _subscription_audit_values(subscription: Subscription) -> JsonObject:
    return {
        "plan_code": subscription.plan_code,
        "currency": subscription.currency,
        "base_price_cents": subscription.base_price_cents,
        "autonomous_pr_add_on_enabled": subscription.autonomous_pr_add_on_enabled,
        "autonomous_pr_add_on_price_cents": (
            subscription.autonomous_pr_add_on_price_cents
        ),
    }


def _pending_payload() -> JsonObject:
    return {
        "input_status": RepositoryComplexity.InputStatus.PENDING,
        "loc": None,
        "module_count": None,
        "contributor_count": None,
        "loc_score": 0.0,
        "module_score": 0.0,
        "contributor_score": 0.0,
        "weighted_score": 0.0,
        "multiplier": 1.0,
        "calculation_version": RepositoryComplexity.CALCULATION_VERSION,
        "source_analysis_id": None,
        "source_commit_sha": None,
        "missing_inputs": list(INPUT_FIELDS),
        "calculated_at": None,
    }


def _restricted_payload() -> JsonObject:
    return {
        "input_status": "restricted",
        "loc": None,
        "module_count": None,
        "contributor_count": None,
        "loc_score": 0.0,
        "module_score": 0.0,
        "contributor_score": 0.0,
        "weighted_score": 0.0,
        "multiplier": 1.0,
        "calculation_version": RepositoryComplexity.CALCULATION_VERSION,
        "source_analysis_id": None,
        "source_commit_sha": None,
        "missing_inputs": [],
        "calculated_at": None,
    }


def _audit_values(complexity: RepositoryComplexity | None) -> JsonObject | None:
    if complexity is None:
        return None
    return {
        "input_status": complexity.input_status,
        "loc": complexity.loc,
        "module_count": complexity.module_count,
        "contributor_count": complexity.contributor_count,
        "weighted_score": complexity.weighted_score,
        "multiplier": complexity.multiplier,
        "missing_inputs": complexity.missing_inputs,
        "calculation_version": complexity.calculation_version,
        "source_analysis_id": (
            str(complexity.source_analysis_id) if complexity.source_analysis_id else None
        ),
    }


def _load_analysis_artifacts(analysis) -> JsonObject:
    if analysis is None:
        return {}

    artifacts: JsonObject = {
        "constitution": analysis.constitution or {},
        "entropy": analysis.entropy or {},
        "opportunities": analysis.opportunities or [],
    }
    for name, key_field in (
        ("snapshot", "snapshot_key"),
        ("knowledge_graph", "knowledge_graph_key"),
        ("health", "health_key"),
        ("dead_code", "dead_code_key"),
    ):
        key = getattr(analysis, key_field)
        artifacts[name] = storage.get_json(key) if key else {}
    return artifacts


def _extract_loc(artifacts: JsonObject) -> int | None:
    health = _dict(artifacts.get("health"))
    direct = _first_int(
        health,
        (
            ("kpis", "loc"),
            ("kpis", "nloc"),
            ("kpis", "lines_of_code"),
            ("summary", "loc"),
            ("summary", "nloc"),
            ("summary", "lines_of_code"),
        ),
    )
    if direct is not None:
        return direct

    metrics = _list(health.get("metrics"))
    metric_loc = sum(
        value
        for value in (_first_int(metric, (("nloc",), ("loc",), ("lines_of_code",))) for metric in metrics)
        if value is not None
    )
    if metric_loc > 0:
        return metric_loc

    for artifact_name in ("knowledge_graph", "snapshot"):
        value = _first_int(
            _dict(artifacts.get(artifact_name)),
            (
                ("summary", "loc"),
                ("summary", "nloc"),
                ("summary", "lines_of_code"),
                ("repository_metrics", "loc"),
                ("repository_metrics", "nloc"),
                ("repository_metrics", "lines_of_code"),
            ),
        )
        if value is not None:
            return value
    return None


def _extract_module_count(artifacts: JsonObject) -> int | None:
    for artifact_name in ("health", "knowledge_graph", "snapshot"):
        artifact = _dict(artifacts.get(artifact_name))
        value = _first_int(
            artifact,
            (
                ("kpis", "module_count"),
                ("kpis", "total_modules"),
                ("summary", "module_count"),
                ("summary", "total_modules"),
                ("repository_metrics", "module_count"),
                ("repository_metrics", "total_modules"),
            ),
        )
        if value is not None:
            return value
        inventory_count = _inventory_count(artifact, ("modules", "module_inventory"))
        if inventory_count is not None:
            return inventory_count
    return None


def _extract_contributor_count(artifacts: JsonObject) -> int | None:
    for artifact_name in ("health", "knowledge_graph", "snapshot"):
        artifact = _dict(artifacts.get(artifact_name))
        value = _first_int(
            artifact,
            (
                ("kpis", "contributor_count"),
                ("kpis", "total_contributors"),
                ("summary", "contributor_count"),
                ("summary", "total_contributors"),
                ("repository_metrics", "contributor_count"),
                ("repository_metrics", "total_contributors"),
            ),
        )
        if value is not None:
            return value
        inventory_count = _contributor_inventory_count(artifact)
        if inventory_count is not None:
            return inventory_count
    return None


def _inventory_count(artifact: JsonObject, keys: tuple[str, ...]) -> int | None:
    for key in keys:
        items = _list(artifact.get(key))
        if items:
            return len(items)
        nested_items = _list(_dict(artifact.get("repository_metrics")).get(key))
        if nested_items:
            return len(nested_items)
    return None


def _contributor_inventory_count(artifact: JsonObject) -> int | None:
    contributors: set[str] = set()
    for value in _iter_contributor_inventory(artifact):
        identity = _contributor_identity(value)
        if identity:
            contributors.add(identity)
    return len(contributors) if contributors else None


def _iter_contributor_inventory(artifact: JsonObject) -> list[Any]:
    values: list[Any] = []
    for container in (artifact, _dict(artifact.get("repository_metrics"))):
        for key in ("contributors", "contributor_inventory"):
            values.extend(_list(container.get(key)))
        for key in ("contributors_json", "contributor_inventory_json"):
            values.extend(_json_list(container.get(key)))
    return values


def _contributor_identity(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if not isinstance(value, dict):
        return None
    for key in ("email", "login", "name"):
        identity = value.get(key)
        if isinstance(identity, str) and identity.strip():
            return identity.strip()
    return None


def _json_list(value: Any) -> list[Any]:
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return _list(decoded)


def _input_status(missing_inputs: list[str]) -> str:
    if not missing_inputs:
        return RepositoryComplexity.InputStatus.COMPLETE
    if len(missing_inputs) == len(INPUT_FIELDS):
        return RepositoryComplexity.InputStatus.PENDING
    return RepositoryComplexity.InputStatus.PARTIAL


def _band_score(value: int | None, bands: tuple[int, int, int]) -> float:
    if value is None:
        return 0.0
    if value <= bands[0]:
        return SCORE_VALUES[0]
    if value <= bands[1]:
        return SCORE_VALUES[1]
    if value <= bands[2]:
        return SCORE_VALUES[2]
    return SCORE_VALUES[3]


def _positive_int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        integer = int(value)
        return integer if integer > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        integer = int(value.strip())
        return integer if integer > 0 else None
    return None


def _first_int(data: JsonObject, paths: tuple[tuple[str, ...], ...]) -> int | None:
    for path in paths:
        value: Any = data
        for segment in path:
            if not isinstance(value, dict) or segment not in value:
                value = None
                break
            value = value[segment]
        positive = _positive_int_or_none(value)
        if positive is not None:
            return positive
    return None


def _dict(value: Any) -> JsonObject:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
