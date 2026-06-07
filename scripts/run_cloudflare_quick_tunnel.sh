#!/usr/bin/env bash
set -euo pipefail

cloudflared_bin="${1:-cloudflared}"
tunnel_url="${2:-http://localhost:8000}"
host_header="${3:-localhost:8000}"
webhook_path="${4:-/api/v1/github-app/webhooks/}"

if ! command -v "$cloudflared_bin" >/dev/null 2>&1; then
  printf 'cloudflared is not installed; skipping public webhook tunnel.\n' >&2
  printf 'Install it from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/ to enable GitHub webhook URLs from make dev.\n' >&2
  exit 0
fi

printf 'Starting Cloudflare Quick Tunnel for GitHub webhooks -> %s\n' "$tunnel_url"
printf 'Waiting for Cloudflare to assign a public URL...\n'

printed_webhook_url=0
set +e
"$cloudflared_bin" tunnel \
  --url "$tunnel_url" \
  --http-host-header "$host_header" 2>&1 | while IFS= read -r line; do
    printf '%s\n' "$line"
    if [[ "$printed_webhook_url" -eq 0 && "$line" =~ https://[-[:alnum:]]+\.trycloudflare\.com ]]; then
      public_url="${BASH_REMATCH[0]}"
      printf '\nGitHub App webhook URL:\n%s%s\n\n' "$public_url" "$webhook_path"
      printed_webhook_url=1
    fi
  done
cloudflared_status="${PIPESTATUS[0]}"
set -e

if [[ "$cloudflared_status" -ne 0 ]]; then
  printf 'Cloudflare Quick Tunnel stopped with status %s; local dev services can continue running.\n' "$cloudflared_status" >&2
fi

exit 0
