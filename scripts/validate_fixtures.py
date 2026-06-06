from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "fixtures" / "schemas"
CONTRACT_DIR = ROOT / "fixtures" / "contracts"

FIXTURE_SCHEMAS = {
    "repository_constitution.json": "repository_constitution.schema.json",
    "gardener_profile.json": "gardener_profile.schema.json",
    "analysis_snapshot.json": "analysis_snapshot.schema.json",
    "entropy_report.json": "entropy_report.schema.json",
    "maintenance_opportunity.json": "maintenance_opportunity.schema.json",
    "gardening_session_result.json": "gardening_session_result.schema.json",
    "maintenance_pr_plan.json": "maintenance_pr_plan.schema.json",
    "repository_automation_settings.json": "repository_automation_settings.schema.json",
    "first_report_fixture.json": "first_report_fixture.schema.json",
}


def load_json(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_schema_registry() -> Registry:
    resources = []
    for schema_path in SCHEMA_DIR.glob("*.schema.json"):
        schema = load_json(schema_path)
        if isinstance(schema, dict) and "$id" in schema:
            resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


SCHEMA_REGISTRY = load_schema_registry()


def validate_fixture(fixture_name: str, schema_name: str) -> None:
    schema = load_json(SCHEMA_DIR / schema_name)
    fixture = load_json(CONTRACT_DIR / fixture_name)
    validator = Draft202012Validator(schema, registry=SCHEMA_REGISTRY)
    errors = sorted(validator.iter_errors(fixture), key=lambda error: error.json_path)
    if errors:
        details = "\n".join(f"{error.json_path}: {error.message}" for error in errors)
        raise SystemExit(f"{fixture_name} does not match {schema_name}:\n{details}")


def main() -> None:
    for fixture_name, schema_name in FIXTURE_SCHEMAS.items():
        validate_fixture(fixture_name, schema_name)
    print(f"Validated {len(FIXTURE_SCHEMAS)} contract fixtures.")


if __name__ == "__main__":
    main()
