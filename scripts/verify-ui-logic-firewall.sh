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

# ADR-0123 (H5): derive the scanned file set from the csproj's
# <Compile Include="../..."> entries (globs expanded relative to UI.Tests/) so
# InteropEnums.cs and any future dual-compiled path are scanned automatically,
# not just the hardcoded UI/Logic folder.
declare -a scanFiles=()
while IFS= read -r include; do
	pattern="${include#../}"
	if [[ "$pattern" == *'**'* ]]; then
		# Recursive glob (e.g. UI/Logic/**/*.cs): the directory is everything
		# before '**', the file name everything after the last '/'.
		dir="${pattern%%\*\**}"
		dir="${dir%/}"
		name="${pattern##*/}"
		while IFS= read -r -d '' f; do
			scanFiles+=("$f")
		done < <(find "$dir" -name "$name" -type f -print0)
	else
		scanFiles+=("$pattern")
	fi
done < <(grep -oE '<Compile Include="\.\./[^"]+"' "$csproj" | sed -E 's/<Compile Include="([^"]+)"/\1/')

if [[ "${#scanFiles[@]}" -eq 0 ]]; then
	echo "ERROR: no <Compile Include=\"../...\"> dual-compiled entries found in $csproj." >&2
	exit 1
fi

for file in "${scanFiles[@]}"; do
	if [[ ! -f "$file" ]]; then
		echo "ERROR: dual-compiled file $file (from $csproj) not found on disk." >&2
		fail=1
	fi
done

for file in "${scanFiles[@]}"; do
	# Strip '//' line-comment content first: these files document what they
	# mirror (e.g. "counterpart to EmuApi.GetMepPackList()") in prose, which
	# is not an actual dependency - only code outside comments must stay
	# Avalonia/EmuApi-free.
	if sed -E 's|//.*$||' "$file" | grep -qE 'Avalonia|EmuApi'; then
		echo "ERROR: $file references Avalonia or EmuApi in code - UI/Logic/*.cs must stay BCL-only (plus System.IO.Compression) so it dual-compiles into UI.Tests." >&2
		fail=1
	fi
	# ADR-0138 §53: the three-layer rule also holds upward - Logic never
	# reaches into the host-aware Services layer or issues HTTP itself.
	if sed -E 's|//.*$||' "$file" | grep -qE 'Mesen\.Services|System\.Net\.Http|HttpClient'; then
		echo "ERROR: $file references Mesen.Services/HttpClient - UI/Logic/*.cs is the host-free decision layer; network orchestration belongs in UI/Services/*.cs." >&2
		fail=1
	fi
done

# ADR-0138 §53: HttpClient use in UI/ is confined to UI/Services/*.cs (plus the
# pre-existing update check) - never Windows code-behind or ViewModels.
while IFS= read -r -d '' file; do
	case "$file" in
		UI/Services/*|UI/ViewModels/UpdatePromptViewModel.cs) continue ;;
	esac
	if sed -E 's|//.*$||' "$file" | grep -qE 'HttpClient'; then
		echo "ERROR: $file uses HttpClient outside UI/Services/ - the network boundary is UI/Services/*.cs (ADR-0138 §37/§53)." >&2
		fail=1
	fi
done < <(find UI -name '*.cs' -not -path 'UI/bin/*' -not -path 'UI/obj/*' -print0)

if [[ "$fail" -ne 0 ]]; then
	exit 1
fi

echo "OK: UI/Logic firewall holds ($csproj has no RuntimeIdentifier/ProjectReference, the dual-compiled file set (from <Compile Include=\"../...\">, ${#scanFiles[@]} files) is free of Avalonia/EmuApi/HttpClient/Mesen.Services, HttpClient confined to UI/Services/)."
