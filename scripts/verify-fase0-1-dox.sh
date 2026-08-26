#!/usr/bin/env bash
# Fase 0/1 DOX guardrail (docs/roadmap/plano-testes-unitarios.md): the three
# AGENTS.md files this slice introduces/updates must exist, and the root
# AGENTS.md Child DOX Index must reference UI.Tests/ so the new project
# isn't an undocumented island. See AGENTS.md (root) for the DOX contract.
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0

for doc in "UI/AGENTS.md" "UI.Tests/AGENTS.md" ".github/AGENTS.md"; do
	if [[ ! -f "$doc" ]]; then
		echo "ERROR: $doc not found - required Fase 0/1 DOX artifact." >&2
		fail=1
	fi
done

rootDoc="AGENTS.md"
if [[ ! -f "$rootDoc" ]]; then
	echo "ERROR: $rootDoc not found." >&2
	exit 1
fi

if ! grep -qE 'UI\.Tests/' "$rootDoc"; then
	echo "ERROR: $rootDoc Child DOX Index does not reference UI.Tests/." >&2
	fail=1
fi

if [[ "$fail" -ne 0 ]]; then
	exit 1
fi

echo "OK: Fase 0/1 DOX artifacts present (UI/AGENTS.md, UI.Tests/AGENTS.md, .github/AGENTS.md) and root AGENTS.md indexes UI.Tests/."
