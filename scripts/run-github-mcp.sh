#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  line="$(grep -v '^#' .env | grep '^GITHUB_TOKEN=' | head -1 || true)"
  if [[ -n "$line" ]]; then
    GITHUB_TOKEN="${line#GITHUB_TOKEN=}"
    GITHUB_TOKEN="${GITHUB_TOKEN%\"}"
    GITHUB_TOKEN="${GITHUB_TOKEN#\"}"
    GITHUB_TOKEN="${GITHUB_TOKEN%\'}"
    GITHUB_TOKEN="${GITHUB_TOKEN#\'}"
    export GITHUB_TOKEN
  fi
fi

: "${GITHUB_TOKEN:?Set GITHUB_TOKEN in .env (repo root)}"
export GITHUB_PERSONAL_ACCESS_TOKEN="$GITHUB_TOKEN"

exec docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN ghcr.io/github/github-mcp-server
