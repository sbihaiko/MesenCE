#!/usr/bin/env bash
# ADR-0138 §41 (PRIORITY 1): scripts/pack_host_allowlist.json is the single
# source of truth for the community-pack host allow-list, shared by CI
# (scripts/fetch_pack.py) and the client. UI/UI.csproj must embed it as an
# EmbeddedResource with the exact Include path and LogicalName the client's
# CommunityPackCatalogFetcher expects on its assembly manifest
# (GetManifestResourceStream("Mesen.pack_host_allowlist.json")) — a published
# app has no scripts/ tree on disk, so the LogicalName is the only handle
# that survives packaging. Fails loudly, never vacuously, when the csproj
# is missing, the EmbeddedResource element is absent, or the Include/
# LogicalName pair doesn't match exactly. No mocks: reads the real csproj
# from disk.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CSPROJ="$REPO_ROOT/UI/UI.csproj"
ALLOWLIST_SOURCE="$REPO_ROOT/scripts/pack_host_allowlist.json"

EXPECTED_INCLUDE='Include="../scripts/pack_host_allowlist.json"'
EXPECTED_LOGICAL_NAME='LogicalName="Mesen.pack_host_allowlist.json"'

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -f "$CSPROJ" ] || fail "file not found: $CSPROJ"
[ -f "$ALLOWLIST_SOURCE" ] || fail "allow-list source not found: $ALLOWLIST_SOURCE"

MATCH_LINE="$(grep -n 'EmbeddedResource' "$CSPROJ" | grep -F 'pack_host_allowlist.json' || true)"
[ -n "$MATCH_LINE" ] \
  || fail "$CSPROJ has no EmbeddedResource element referencing pack_host_allowlist.json"

grep -qF "$EXPECTED_INCLUDE" "$CSPROJ" \
  || fail "$CSPROJ's allow-list EmbeddedResource does not have the exact Include $EXPECTED_INCLUDE"
grep -qF "$EXPECTED_LOGICAL_NAME" "$CSPROJ" \
  || fail "$CSPROJ's allow-list EmbeddedResource does not have the exact LogicalName $EXPECTED_LOGICAL_NAME"

# Both attributes must land on the SAME EmbeddedResource element, not two
# unrelated elements that each happen to contain one of the two strings.
SAME_LINE="$(grep -n 'EmbeddedResource' "$CSPROJ" | grep -F "$EXPECTED_INCLUDE" | grep -F "$EXPECTED_LOGICAL_NAME" || true)"
[ -n "$SAME_LINE" ] \
  || fail "$CSPROJ's Include and LogicalName for the allow-list are not on the same EmbeddedResource element"

echo "PASS: UI/UI.csproj embeds scripts/pack_host_allowlist.json as EmbeddedResource LogicalName=Mesen.pack_host_allowlist.json ($SAME_LINE)"
