#!/usr/bin/env bash
# F5.4b header guardrail (docs/roadmap/AGENTS.md: "Status in the header is
# the source of truth for whether a phase is still work"): once the
# palette-variant capture fix (ADR-0050 step b) ships, the header Status
# line in plano-execucao-F5.md must carry F5.4b as a done clause with a
# done marker (not still listed among the pending items after F5.4a), and
# the old pending phrasing must be gone verbatim.
set -euo pipefail
cd "$(dirname "$0")/.."

plan="docs/roadmap/plano-execucao-F5.md"
oldPending="F5.4b variantes de paleta, F5.4c"

if [[ ! -f "$plan" ]]; then
	echo "ERROR: $plan not found." >&2
	exit 1
fi

header="$(grep -m1 '^\*\*Status:\*\*' "$plan")"
fail=0

if [[ -z "$header" ]]; then
	echo "ERROR: $plan has no '**Status:**' header line." >&2
	exit 1
fi

if ! grep -qE 'F5\.4b[^*]*✅' <<<"$header"; then
	echo "ERROR: header Status line has no 'F5.4b' clause paired with a done (✅) marker." >&2
	fail=1
fi

if grep -qF "$oldPending" <<<"$header"; then
	echo "ERROR: header Status line still contains the old pending phrasing '$oldPending' verbatim." >&2
	fail=1
fi

if [[ "$fail" -ne 0 ]]; then
	exit 1
fi

echo "OK: header Status line marks F5.4b done and no longer contains the old pending phrasing."
