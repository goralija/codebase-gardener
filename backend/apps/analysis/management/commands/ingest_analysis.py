"""Ingest analysis artifacts produced by scripts/analyze_repo.sh into storage.

Local bridge for COD-45: reads the JSON files written to a directory and
persists them (large blobs -> object storage, small contracts inline) via
``store_analysis``. The async worker (E05-T01) will later call the same
service directly instead of going through files.

Usage:
    python manage.py ingest_analysis --repo <repository_id> --dir <artifact_dir>
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.analysis.storage_service import store_analysis
from apps.repositories.models import ManagedRepository


# artifact name -> filename written by scripts/analyze_repo.sh
_FILES = {
    "snapshot": "analysis_snapshot.json",
    "constitution": "repository_constitution.json",
    "entropy": "entropy_report.json",
    "opportunities": "opportunities.json",
    "knowledge_graph": "knowledge_graph.json",
    "health": "health.json",
    "dead_code": "dead_code.json",
}


class Command(BaseCommand):
    help = "Ingest analysis artifacts from a directory into per-tenant storage."

    def add_arguments(self, parser):
        parser.add_argument("--repo", required=True, help="ManagedRepository id")
        parser.add_argument("--dir", required=True, help="Artifact directory")

    def handle(self, *args, **options):
        directory = Path(options["dir"]).expanduser().resolve()
        if not directory.is_dir():
            raise CommandError(f"Artifact directory not found: {directory}")

        try:
            repository = ManagedRepository.objects.select_related("organization").get(
                id=options["repo"]
            )
        except ManagedRepository.DoesNotExist as exc:
            raise CommandError(f"Repository {options['repo']} not found.") from exc

        artifacts = {}
        for name, filename in _FILES.items():
            path = directory / filename
            if path.exists():
                artifacts[name] = json.loads(path.read_text(encoding="utf-8"))

        if "snapshot" not in artifacts:
            raise CommandError(
                f"No analysis_snapshot.json in {directory}; nothing to ingest."
            )
        commit_sha = str(artifacts["snapshot"].get("commit_sha", "")) or "unknown"

        analysis = store_analysis(
            organization=repository.organization,
            repository=repository,
            commit_sha=commit_sha,
            artifacts=artifacts,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Stored analysis {analysis.id} for {repository.full_name} "
                f"@ {commit_sha[:12]} ({len(artifacts)} artifacts)."
            )
        )
