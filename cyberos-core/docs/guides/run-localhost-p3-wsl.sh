#!/usr/bin/env bash
# CyberOS WSL localhost-only P3 runner.
# Safety contract: no live Nmap invocation unless CYBEROS_P3_AUTHORIZED=YES.
# This script never targets anything except 127.0.0.1 and never retries.

set -Eeuo pipefail

readonly REPOSITORY_URL="https://github.com/malhiloo-byte/cyberHub.git"
readonly REPOSITORY_DIR="${CYBEROS_REPOSITORY_DIR:-$HOME/cyberHub}"
readonly CORE_DIR="$REPOSITORY_DIR/cyberos-core"
readonly CONFIG_PATH="${CYBEROS_CONFIG:-$HOME/.cyberos/cyberos.toml}"
readonly DATA_DIR="$HOME/.cyberos"
readonly P3_GUARD="$DATA_DIR/localhost-p3-single-use.lock"
readonly RUN_LABEL="$(date -u +%Y%m%dT%H%M%SZ)-$$"
readonly RUN_LOG="$DATA_DIR/localhost-p3-run-${RUN_LABEL}.log"

on_error() {
  local exit_code=$?
  printf '\nScript stopped with exit code %s. Ubuntu/WSL was not shut down. No retry was attempted.\n' "$exit_code" >&2
  printf 'Run log: %s\n' "$RUN_LOG" >&2
  exit "$exit_code"
}
trap on_error ERR

extract_id() {
  grep -oE '"id"[[:space:]]*:[[:space:]]*"[0-9a-f-]+"' \
    | head -n 1 \
    | sed -E 's/.*"([0-9a-f-]+)"/\1/'
}

require_id() {
  local value=$1
  local label=$2
  if [[ ! "$value" =~ ^[0-9a-f-]{36}$ ]]; then
    printf 'Could not extract %s from CyberOS JSON output. Stopping.\n' "$label" >&2
    exit 1
  fi
}

printf '%s\n' '=== CyberOS WSL localhost-only runner ==='
printf '%s\n' 'This script can perform one real Nmap TCP Connect scan only when explicitly enabled.'

sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nmap sqlite3

if [[ -d "$REPOSITORY_DIR/.git" ]]; then
  git -C "$REPOSITORY_DIR" fetch origin
  git -C "$REPOSITORY_DIR" checkout main
  git -C "$REPOSITORY_DIR" pull --ff-only origin main
else
  git clone "$REPOSITORY_URL" "$REPOSITORY_DIR"
fi

cd "$CORE_DIR"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

mkdir -p "$DATA_DIR/logs"
exec > >(tee -a "$RUN_LOG") 2>&1
if [[ ! -f "$CONFIG_PATH" ]]; then
  cp config/cyberos.example.toml "$CONFIG_PATH"
fi
export CYBEROS_CONFIG="$CONFIG_PATH"

printf '%s\n' '=== Quality gates ==='
bash scripts/check.sh
cyberos doctor --json --file "$CYBEROS_CONFIG"

readonly NMAP_PATH="/usr/bin/nmap"
readonly NMAP_SHA256="$(sha256sum "$NMAP_PATH" | awk '{print $1}')"
readonly NMAP_VERSION="$("$NMAP_PATH" --version | sed -n '1s/^Nmap version \([^ ]*\).*/\1/p')"

if [[ -z "$NMAP_VERSION" || ! "$NMAP_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
  printf '%s\n' 'Nmap identity preflight failed. Stopping before any scan.' >&2
  exit 1
fi

printf '%s\n' '=== Creating explicit localhost-only context ==='
workspace_json="$(cyberos workspace create "WSL Localhost Lab $RUN_LABEL" \
  --description "One explicit localhost-only CyberOS lab" \
  --json --file "$CYBEROS_CONFIG")"
WORKSPACE_ID="$(printf '%s' "$workspace_json" | extract_id)"
require_id "$WORKSPACE_ID" 'Workspace ID'

engagement_json="$(cyberos engagement create "$WORKSPACE_ID" "Localhost TCP Connect Lab $RUN_LABEL" \
  --kind learning \
  --authorization-reference "LOCALHOST-ONLY-$(date +%F)" \
  --json --file "$CYBEROS_CONFIG")"
ENGAGEMENT_ID="$(printf '%s' "$engagement_json" | extract_id)"
require_id "$ENGAGEMENT_ID" 'Engagement ID'

scope_json="$(cyberos scope create "$ENGAGEMENT_ID" "127.0.0.1 Only $RUN_LABEL" \
  --description "Explicit WSL loopback only; no LAN, CIDR, gateway, or external target" \
  --json --file "$CYBEROS_CONFIG")"
SCOPE_ID="$(printf '%s' "$scope_json" | extract_id)"
require_id "$SCOPE_ID" 'Scope ID'

target_json="$(cyberos target add "$SCOPE_ID" \
  --rule include --kind ipv4 --value 127.0.0.1 \
  --json --file "$CYBEROS_CONFIG")"
TARGET_ID="$(printf '%s' "$target_json" | extract_id)"
require_id "$TARGET_ID" 'Target ID'

cyberos scope authorize "$SCOPE_ID" \
  --authorization-reference "LOCALHOST-P3-ONE-RUN-$(date +%F)" \
  --json --file "$CYBEROS_CONFIG"

cyberos scope evaluate "$SCOPE_ID" \
  --kind ipv4 --value 127.0.0.1 \
  --json --file "$CYBEROS_CONFIG"

printf '\nScope ID:  %s\nTarget ID: %s\nNmap:      %s (%s)\n' \
  "$SCOPE_ID" "$TARGET_ID" "$NMAP_VERSION" "$NMAP_SHA256"

if [[ "${CYBEROS_P3_AUTHORIZED:-NO}" != "YES" ]]; then
  printf '%s\n' ''
  printf '%s\n' 'Preflight completed. No live scan was run.'
  printf '%s\n' 'To run the one approved localhost scan, re-run this script with:'
  printf '%s\n' 'CYBEROS_P3_AUTHORIZED=YES bash run-localhost-p3-wsl.sh'
  exit 0
fi

if [[ -e "$P3_GUARD" ]]; then
  printf '%s\n' 'Single-use P3 guard already exists. No scan will be executed.' >&2
  printf 'Guard path: %s\n' "$P3_GUARD" >&2
  exit 1
fi

date --iso-8601=seconds > "$P3_GUARD"
printf '%s\n' '=== Executing exactly one localhost-only Nmap scan ==='

set +e
cyberos recon nmap-localhost "$SCOPE_ID" "$TARGET_ID" \
  --nmap-sha256 "$NMAP_SHA256" \
  --nmap-version "$NMAP_VERSION" \
  --ports 22,80,443 \
  --nmap-path "$NMAP_PATH" \
  --json --file "$CYBEROS_CONFIG" \
  | tee "$DATA_DIR/localhost-p3-last-result.json"
P3_EXIT=${PIPESTATUS[0]}
set -e

printf '%s\n' '=== Read-only post-run verification ==='
cyberos task list --scope-id "$SCOPE_ID" --json --file "$CYBEROS_CONFIG"
sqlite3 "$DATA_DIR/cyberos.sqlite3" 'PRAGMA quick_check; PRAGMA foreign_key_check;'

printf 'Live invocation exit code: %s\n' "$P3_EXIT"
printf 'Task output receipt: %s\n' "$DATA_DIR/localhost-p3-last-result.json"
printf 'Single-use guard:    %s\n' "$P3_GUARD"
printf '%s\n' 'No retry was attempted. Do not remove the guard or re-run without a new explicit authorization.'
exit "$P3_EXIT"
