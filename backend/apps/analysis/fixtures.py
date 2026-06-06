import json
from functools import cache
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from jsonschema import Draft202012Validator
from referencing import Registry, Resource


def load_first_report_fixture() -> dict[str, Any]:
    fixture = _load_json(first_report_fixture_path())
    if not isinstance(fixture, dict):
        raise ImproperlyConfigured("First report fixture must be a JSON object.")

    validate_first_report_fixture_contract(fixture)
    return fixture


def first_report_fixture_path() -> Path:
    return settings.BASE_DIR.parent / "fixtures" / "contracts" / "first_report_fixture.json"


def validate_first_report_fixture_contract(fixture: dict[str, Any]) -> None:
    validate_against_schema(
        "first_report_fixture.schema.json",
        fixture,
        label="First report fixture",
    )


def validate_against_schema(
    schema_name: str,
    payload: dict[str, Any],
    *,
    label: str | None = None,
) -> None:
    """Validate ``payload`` against a fixture schema by file name.

    Raises ``ImproperlyConfigured`` with aggregated error details when the
    payload does not match the contract.
    """

    schema = _load_json(_schema_path(schema_name))
    validator = Draft202012Validator(schema, registry=_schema_registry())
    errors = sorted(validator.iter_errors(payload), key=lambda error: error.json_path)
    if errors:
        details = "; ".join(f"{error.json_path}: {error.message}" for error in errors)
        prefix = label or schema_name
        raise ImproperlyConfigured(f"{prefix} does not match contract: {details}")


@cache
def _schema_registry() -> Registry:
    resources = []
    for schema_path in _schema_dir().glob("*.schema.json"):
        schema = _load_json(schema_path)
        if isinstance(schema, dict) and "$id" in schema:
            resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def _schema_path(schema_name: str) -> Path:
    return _schema_dir() / schema_name


def _schema_dir() -> Path:
    return settings.BASE_DIR.parent / "fixtures" / "schemas"


def _load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as json_file:
            return json.load(json_file)
    except OSError as exc:
        raise ImproperlyConfigured(f"Could not read {path.name}.") from exc
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(f"{path.name} is not valid JSON.") from exc
