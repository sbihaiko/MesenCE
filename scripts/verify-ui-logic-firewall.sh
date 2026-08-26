#!/usr/bin/env bash
# Fase 0/1 guardrail (docs/roadmap/plano-testes-unitarios.md): UI.Tests must
# stay a cheap, cross-platform `dotnet test` project, and UI/Logic/*.cs must
# stay host-free (BCL + System.IO.Compression only) so it dual-compiles
# unmodified into UI.Tests without pulling in Avalonia or the native
# MesenCore bridge (EmuApi). See UI/AGENTS.md and UI.Tests/AGENTS.md.
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0

csproj="UI.Tests/UI.Tests.csproj"
if [[ ! -f "$csproj" ]]; then
	echo "ERROR: $csproj not found." >&2
	exit 1
fi

if grep -qE '<RuntimeIdentifier' "$csproj"; then
	echo "ERROR: $csproj declares <RuntimeIdentifier> - this turns the test project into a full app build (SDL2/native dependency, Windows-only publish flags), breaking the cheap cross-platform 'dotnet test' contract." >&2
	fail=1
fi

if grep -qE '<ProjectReference' "$csproj"; then
	echo "ERROR: $csproj declares <ProjectReference> - it must dual-compile UI/Logic/*.cs via <Compile Include>, not reference UI.csproj (which drags in Avalonia/EmuApi)." >&2
	fail=1
fi

logicDir="UI/Logic"
if [[ ! -d "$logicDir" ]]; then
	echo "ERROR: $logicDir not found." >&2
	exit 1
fi

while IFS= read -r -d '' file; do
	# Strip '//' line-comment content first: these files document what they
	# mirror (e.g. "counterpart to EmuApi.GetMepPackList()") in prose, which
	# is not an actual dependency - only code outside comments must stay
	# Avalonia/EmuApi-free.
	if sed -E 's|//.*$||' "$file" | grep -qE 'Avalonia|EmuApi'; then
		echo "ERROR: $file references Avalonia or EmuApi in code - UI/Logic/*.cs must stay BCL-only (plus System.IO.Compression) so it dual-compiles into UI.Tests." >&2
		fail=1
	fi
done < <(find "$logicDir" -name '*.cs' -print0)

if [[ "$fail" -ne 0 ]]; then
	exit 1
fi

echo "OK: UI/Logic firewall holds ($csproj has no RuntimeIdentifier/ProjectReference, UI/Logic/*.cs is free of Avalonia/EmuApi)."
