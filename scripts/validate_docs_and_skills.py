from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
SKILLS_DIR = ROOT / ".agents" / "skills"

REQUIRED_DOCS = [
    "00-product-vision.md",
    "01-product-domain.md",
    "02-user-roles-and-permissions.md",
    "03-system-model.md",
    "04-feature-map.md",
    "05-user-flows.md",
    "06-github-app-api-spec.md",
    "07-data-storage-rules.md",
    "08-ui-ux-guidelines.md",
    "09-autonomy-and-automation-rules.md",
    "10-integrations.md",
    "11-security-and-compliance.md",
    "12-testing-strategy.md",
    "13-deployment-and-environments.md",
    "14-roadmap.md",
    "15-epics-and-tasks.md",
    "16-constitution-and-memory-schema.md",
    "17-entropy-signal-catalog.md",
    "18-technical-architecture.md",
    "19-shared-json-contracts.md",
    "20-team-working-agreement.md",
]

REQUIRED_SKILLS = [
    "analysis-engine-implementation",
    "backend-implementation",
    "code-review",
    "documentation-update",
    "entropy-modeler",
    "frontend-implementation",
    "gardening-session-planner",
    "github-app-implementation",
    "plan-next-step",
    "product-planning",
    "repo-constitution-builder",
    "safe-pr-author",
    "testing",
]

UNRESOLVED_MARKER = re.compile(r"^\s*(?:<!--\s*)?(TODO|TBD|FIXME|XXX)\b")
CONFLICT_MARKER = re.compile(r"^(<<<<<<<|=======|>>>>>>>)")


def fail(message: str) -> None:
    raise SystemExit(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = read(path)
    if not text.startswith("---\n"):
        fail(f"{path.relative_to(ROOT)} is missing frontmatter.")

    try:
        _, body = text.split("---\n", 1)
        frontmatter_text, _ = body.split("---\n", 1)
    except ValueError:
        fail(f"{path.relative_to(ROOT)} has malformed frontmatter.")

    values: dict[str, str] = {}
    for line in frontmatter_text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            fail(f"{path.relative_to(ROOT)} has invalid frontmatter line: {line}")
        values[key.strip()] = value.strip().strip('"')
    return values


def validate_required_files() -> None:
    for doc_name in REQUIRED_DOCS:
        if not (DOCS_DIR / doc_name).is_file():
            fail(f"Missing required doc: docs/{doc_name}")

    for skill_name in REQUIRED_SKILLS:
        skill_dir = SKILLS_DIR / skill_name
        if not (skill_dir / "SKILL.md").is_file():
            fail(f"Missing required skill: .agents/skills/{skill_name}/SKILL.md")
        if not (skill_dir / "agents" / "openai.yaml").is_file():
            fail(f"Missing skill agent metadata: .agents/skills/{skill_name}/agents/openai.yaml")


def validate_doc_headers() -> None:
    for doc_name in REQUIRED_DOCS:
        path = DOCS_DIR / doc_name
        text = read(path)
        if not text.startswith("# "):
            fail(f"{path.relative_to(ROOT)} must start with a level-1 heading.")
        if not any(line.startswith("> Status:") for line in text.splitlines()[:6]):
            fail(f"{path.relative_to(ROOT)} must declare a Status in its header.")
        if not any(line.startswith("> Purpose:") for line in text.splitlines()[:8]):
            fail(f"{path.relative_to(ROOT)} must declare a Purpose in its header.")


def validate_skill_metadata() -> None:
    agents_text = read(ROOT / "AGENTS.md")
    for skill_name in REQUIRED_SKILLS:
        skill_dir = SKILLS_DIR / skill_name
        skill_path = skill_dir / "SKILL.md"
        metadata_path = skill_dir / "agents" / "openai.yaml"

        frontmatter = parse_frontmatter(skill_path)
        if frontmatter.get("name") != skill_name:
            fail(f"{skill_path.relative_to(ROOT)} frontmatter name must be {skill_name}.")
        if not frontmatter.get("description"):
            fail(f"{skill_path.relative_to(ROOT)} must have a non-empty description.")

        metadata = read(metadata_path)
        for key in ["display_name", "short_description", "default_prompt"]:
            if f"{key}:" not in metadata:
                fail(f"{metadata_path.relative_to(ROOT)} is missing {key}.")
        if f"${skill_name}" not in metadata:
            fail(f"{metadata_path.relative_to(ROOT)} default prompt must reference ${skill_name}.")
        if f".agents/skills/{skill_name}/SKILL.md" not in agents_text:
            fail(f"AGENTS.md does not reference .agents/skills/{skill_name}/SKILL.md")


def iter_active_guidance_files() -> list[Path]:
    paths = [
        ROOT / "AGENTS.md",
        ROOT / "GARDENER.md",
        ROOT / "README.md",
    ]
    paths.extend(path for path in DOCS_DIR.rglob("*.md") if "archive" not in path.parts)
    paths.extend(SKILLS_DIR.rglob("*.md"))
    return sorted(paths)


def validate_no_unresolved_markers() -> None:
    errors: list[str] = []
    for path in iter_active_guidance_files():
        for line_number, line in enumerate(read(path).splitlines(), start=1):
            if UNRESOLVED_MARKER.search(line) or CONFLICT_MARKER.search(line):
                errors.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")

    if errors:
        fail("Unresolved guidance markers found:\n" + "\n".join(errors))


def main() -> None:
    validate_required_files()
    validate_doc_headers()
    validate_skill_metadata()
    validate_no_unresolved_markers()
    print(f"Validated {len(REQUIRED_DOCS)} docs and {len(REQUIRED_SKILLS)} skills.")


if __name__ == "__main__":
    main()
