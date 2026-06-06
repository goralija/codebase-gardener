from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FixtureRepository:
    name: str
    path: Path
    description: str
    tags: tuple[str, ...]


FIXTURE_REPOSITORIES: tuple[FixtureRepository, ...] = (
    FixtureRepository(
        name="normal_repo",
        path=Path("normal_repo"),
        description="Small documented service with source, tests, and a clear constitution.",
        tags=("documented", "single_repo", "tests"),
    ),
    FixtureRepository(
        name="monorepo_repo",
        path=Path("monorepo_repo"),
        description="Workspace-style repo with API, web, and shared package boundaries.",
        tags=("documented", "monorepo", "logical_systems"),
    ),
    FixtureRepository(
        name="missing_docs_repo",
        path=Path("missing_docs_repo"),
        description="Parseable source tree with intentionally missing source-truth docs.",
        tags=("missing_docs", "single_repo"),
    ),
    FixtureRepository(
        name="conflicting_docs_repo",
        path=Path("conflicting_docs_repo"),
        description="Docs intentionally disagree so source-truth conflict handling can be tested.",
        tags=("conflicting_docs", "source_truth"),
    ),
    FixtureRepository(
        name="protected_modules_repo",
        path=Path("protected_modules_repo"),
        description="Repo constitution declares protected modules and never-touch paths.",
        tags=("protected_modules", "never_touch", "source_truth"),
    ),
)


def default_fixtures_root() -> Path:
    return Path(__file__).resolve().parents[3] / "fixtures" / "repos"


def list_fixture_repositories(fixtures_root: Path | None = None) -> list[FixtureRepository]:
    root = fixtures_root or default_fixtures_root()
    fixtures = [
        FixtureRepository(
            name=fixture.name,
            path=root / fixture.path,
            description=fixture.description,
            tags=fixture.tags,
        )
        for fixture in FIXTURE_REPOSITORIES
    ]
    return sorted(fixtures, key=lambda fixture: fixture.name)


def load_fixture_repository(
    name: str, fixtures_root: Path | None = None
) -> FixtureRepository:
    for fixture in list_fixture_repositories(fixtures_root):
        if fixture.name == name:
            return fixture

    known = ", ".join(sorted(fixture.name for fixture in FIXTURE_REPOSITORIES))
    raise ValueError(f"Unknown fixture repository {name!r}. Known fixtures: {known}.")
