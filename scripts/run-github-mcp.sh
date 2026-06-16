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

# Cursor mangles spaces in --header args; use Authorization:Bearer<token> (no space after colon).
export GITHUB_AUTH_HEADER="Bearer ${GITHUB_TOKEN}"

exec npx -y mcp-remote@latest "https://api.githubcopilot.com/mcp/" \
  --header "Authorization:${GITHUB_AUTH_HEADER}"
