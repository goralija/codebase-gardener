#!/usr/bin/env bash
# Full Lane B analysis of a connected GitHub repo.
# Clones to a temp dir, runs index -> snapshot -> constitution -> entropy,
# writes JSON artifacts to analysis-output/<repo>/, then ALWAYS deletes the clone.
#
# Usage:  scripts/analyze_repo.sh <owner/repo>
#   e.g.  scripts/analyze_repo.sh HananB27/bloomhub-be
set -euo pipefail

REPO="${1:?usage: analyze_repo.sh <owner/repo>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="${REPO##*/}"
OUT="$ROOT/analysis-output/$NAME"
mkdir -p "$OUT"

# Temp clone dir; guaranteed cleanup on any exit (success, error, Ctrl-C).
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

# 1. Mint installation token (kept in a var, never printed).
TOKEN="$(cd "$ROOT/backend" && uv run python manage.py shell -c \
  "from apps.github_app.client import GitHubAppClient; from apps.github_app.models import GitHubInstallation; print(GitHubAppClient().create_installation_token(GitHubInstallation.objects.active().first().github_installation_id))" \
  2>/dev/null | tail -1)"

# 2. Shallow clone (token inline, scrubbed right after).
git clone --depth 1 "https://x-access-token:${TOKEN}@github.com/${REPO}.git" "$TMP/repo" >/dev/null 2>&1
unset TOKEN
echo "cloned $REPO -> temp"

# 3. Full Lane B chain; write every artifact to $OUT.
( cd "$ROOT/analysis_engine" && OUT="$OUT" REPO_DIR="$TMP/repo" uv run python -c "
import json, os
from pathlib import Path
from gardener_analysis import (index_repository, RepowiseIndexOptions, build_analysis_snapshot,
  build_repository_constitution, build_entropy_report, discover_source_truth)
out=Path(os.environ['OUT']); repo=Path(os.environ['REPO_DIR'])
idx   = index_repository(repo, RepowiseIndexOptions(repowise_project=Path('../RepoWise').resolve()))
disc  = discover_source_truth(repo)
snap  = build_analysis_snapshot(idx, 'repo_'+repo.name, 'const_'+repo.name)
const = build_repository_constitution(repo, 'repo_'+repo.name, snap['commit_sha'], discovery=disc)
rep   = build_entropy_report(snap, const)
(out/'analysis_snapshot.json').write_text(json.dumps(snap, indent=2))
(out/'repository_constitution.json').write_text(json.dumps(const, indent=2))
(out/'entropy_report.json').write_text(json.dumps(rep, indent=2))
(out/'knowledge_graph.json').write_text(json.dumps(idx.knowledge_graph or {}, indent=2))
(out/'health.json').write_text(json.dumps(idx.health, indent=2))
(out/'dead_code.json').write_text(json.dumps(idx.dead_code, indent=2))
print('commit          :', snap['commit_sha'][:12])
print('signal counts   :', {k:len(v) for k,v in snap['signals'].items()})
print('entropy         :', rep['score']['overall'], rep['score']['classification'])
print('explanation     :', rep['score']['explanation'])
" < /dev/null )

# 4. Clone deleted by trap on exit; analysis JSON persists.
echo "analysis saved -> $OUT  (clone deleted)"
ls -1 "$OUT"
