#!/usr/bin/env bash
# AC-8 (ADR-0138 §41, PRIORITY 1): UI/Services/CommunityPackCatalogFetcher.cs
# must load the community-pack host allow-list strictly from the assembly
# manifest (Assembly.GetExecutingAssembly().GetManifestResourceStream(...)
# + CommunityPackHostAllowlist.LoadFromStream) and never touch the
# filesystem for it - a published app has no scripts/ tree to read a
# repo-relative path from. This script fails loudly, naming the offending
# token, when the fetcher references either forbidden pattern:
#   - CommunityPackHostAllowlist.LoadFromFile (the filesystem-path overload)
#   - the literal repo-relative path "scripts/pack_host_allowlist.json"
# Exits 0 when clean, non-zero (with a diagnostic on stderr) when either
# forbidden token is present. No mocks: reads the real source file from disk.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET_FILE="$REPO_ROOT/UI/Services/CommunityPackCatalogFetcher.cs"

fail() {
	echo "FAIL: $1" >&2
	exit 1
}

[ -f "$TARGET_FILE" ] || fail "file not found: $TARGET_FILE"

if grep -n "LoadFromFile" "$TARGET_FILE" >/dev/null 2>&1; then
	fail "$TARGET_FILE references LoadFromFile (filesystem allow-list load) - must use GetManifestResourceStream + LoadFromStream only"
fi

if grep -n "scripts/pack_host_allowlist.json" "$TARGET_FILE" >/dev/null 2>&1; then
	fail "$TARGET_FILE references the repo-relative allow-list path literal 'scripts/pack_host_allowlist.json' - a published app has no scripts/ tree; use the embedded resource logical name 'Mesen.pack_host_allowlist.json' instead"
fi

echo "PASS: $TARGET_FILE never references LoadFromFile or the repo-relative allow-list path"
