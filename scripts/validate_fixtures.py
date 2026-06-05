from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


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
    "first_report_fixture.json": "first_report_fixture.schema.json",
}


def load_json(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_fixture(fixture_name: str, schema_name: str) -> None:
    schema = load_json(SCHEMA_DIR / schema_name)
    fixture = load_json(CONTRACT_DIR / fixture_name)
    validator = Draft202012Validator(schema)
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

