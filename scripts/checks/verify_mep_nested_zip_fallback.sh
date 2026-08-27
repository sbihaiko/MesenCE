#!/usr/bin/env bash
# Regression for GitHub issue #19: scripts/mep_lint.py did not extract a
# nested .zip when the downloaded pack itself contains a single .zip file
# among its top-level entries (repro: a Google Drive export whose top level
# is "BonusA/", "BonusB/", "RealPack.zip", "Readme.txt" — the real
# hires.txt-shaped pack lives one level deeper, inside RealPack.zip, past
# every existing discovery path (root conventions, structural fallback,
# ROM-name fallback)). scripts/mep_lint.py's find_top_level_nested_zip +
# discover_sections now try that last resort only after every earlier path
# already found nothing, and only when exactly one top-level entry is a
# .zip file (two: fails closed, same ADR-0120 philosophy as the structural/
# ROM-name fallbacks — never guesses which zip is the real pack). No mocks:
# runs the real mep_lint.py CLI against real generated zip files.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="${PYTHON:-python3}"
LINT="$REPO_ROOT/scripts/mep_lint.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

"$PY" - "$WORK" <<'EOF'
import io
import sys
import zipfile

work = sys.argv[1]

def inner_pack_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("textures/hires.txt", "<ver>106\n<scale>1\n")
    return buf.getvalue()

# accept: one top-level .zip entry among unrelated bonus folders/files.
with zipfile.ZipFile(f"{work}/accept.zip", "w") as z:
    z.writestr("BonusGraphics/readme.txt", "bonus")
    z.writestr("BonusSound/readme.txt", "bonus")
    z.writestr("RealPack.zip", inner_pack_bytes())
    z.writestr("Readme.txt", "top-level readme")

# ambiguous: two top-level .zip entries — must NOT guess, must fail closed.
with zipfile.ZipFile(f"{work}/ambiguous.zip", "w") as z:
    z.writestr("PackA.zip", inner_pack_bytes())
    z.writestr("PackB.zip", inner_pack_bytes())
EOF

ACCEPT_OUT="$("$PY" "$LINT" "$WORK/accept.zip" 2>&1)" || true
if ! grep -q "nested-zip fallback (issue #19)" <<<"$ACCEPT_OUT"; then
  fail "accept.zip: mep_lint.py did not report the nested-zip fallback info line. Output:
$ACCEPT_OUT"
fi
if ! grep -qE "^0 error\(s\)" <<<"$ACCEPT_OUT"; then
  fail "accept.zip: expected 0 errors once the nested RealPack.zip is unwrapped and linted. Output:
$ACCEPT_OUT"
fi

AMBIGUOUS_OUT="$("$PY" "$LINT" "$WORK/ambiguous.zip" 2>&1)" || true
if grep -q "nested-zip fallback (issue #19)" <<<"$AMBIGUOUS_OUT"; then
  fail "ambiguous.zip: mep_lint.py must not guess between two top-level .zip candidates. Output:
$AMBIGUOUS_OUT"
fi
if ! grep -q "no section found" <<<"$AMBIGUOUS_OUT"; then
  fail "ambiguous.zip: expected the pre-existing 'no section found' rejection. Output:
$AMBIGUOUS_OUT"
fi

echo "PASS: mep_lint.py unwraps a single top-level nested .zip as a last-resort fallback and reports 0 errors once discovered, while still failing closed on two ambiguous top-level .zip candidates"
