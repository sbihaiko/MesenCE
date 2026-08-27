# ADR-0121: Legacy loose hires.txt as fallback discovery signal in MEP zip wrapper folders

- Status: accepted
- Date: 2026-08-27

## Context
Bug https://github.com/sbihaiko/MesenCE/issues/48: scripts/mep_lint.py rejects classic Mesen 0.9.5/Mesen2-native HD packs (hires.txt at the pack's own root, no textures/ subfolder — the pre-MEP, pre-ADR-0049 convention MesenCE's HdPacks loader still supports at the container root) with "no section found", specifically when that loose hires.txt sits one level down inside an unrelated wrapper folder — e.g. a raw GitHub /archive/refs/heads/<branch>.zip download whose top-level folder is named after the repo (HDNes-Graphics-Pac-master/, ZII-mesen-main/), not the ROM/game.

Verified with two real test fixtures, both filed as community-pack submissions and run locally through scripts/mep_lint.py:
- https://github.com/sbihaiko/MesenCE/issues/46 (PepCodes/HDNes-Graphics-Pac, Pac-Man): HDNes-Graphics-Pac-master/hires.txt, HDNes-Graphics-Pac-master/Chr_00_0.png, etc.
- https://github.com/sbihaiko/MesenCE/issues/47 (ModernRetroDesign/ZII-mesen, Zelda II): ZII-mesen-main/hires.txt plus Characters/, Dialog/, Font/, HUD/, IPS patches.

Both fail today with exit code 1: "no section found (textures/hires.txt, audio/hires.txt, synth/preset.cfg, auto/...)".

Confirmed by reading current source in-session (not inferred):
- discover_sections() in scripts/mep_lint.py only treats src.exists("hires.txt") at the absolute container root as the legacy loose-pack signal (~line 343); it never re-checks a bare hires.txt as a *discovery* signal once inside a candidate prefix — only as a secondary check after a prefix is already known some other way (~line 371).
- find_fallback_subfolder (Python, structural/no-ROM-name) only matches FALLBACK_SUFFIXES = pack.json plus the convention PROBES (textures/hires.txt, audio/hires.txt, audio/fingerprints.json, synth/preset.cfg, and their auto/ variants) — never a bare hires.txt/preset.cfg/fingerprints.json without the textures//audio//synth/ wrapper.
- find_fallback_subfolder_by_name (Python, ROM-name-anchored, the ADR-0120 §3 named follow-up already implemented) DOES accept bare FALLBACK_PROBE_BASENAMES directly under a subfolder segment matching the declared ROM name — but only when that segment's name matches the ROM name. In both fixtures the wrapper folder is named after the repository, not the game, so this fallback does not match either.
- Core::MepPack::FindFallbackSubfolder (C++, MepPack.cpp:197) mirrors only the ROM-name-anchored variant; MepPackManager.cpp's ResolveFallbackPrefix always requires romName — there is no structural/no-ROM-name fallback at runtime at all. MesenCE's real installer would reject these exact two zips today even with the correct declared ROM name, since the wrapper-folder name mismatch defeats the name anchor regardless of language.
- UI/Logic/MepZipValidator.cs's FindStructuralFallbackPrefix mirrors the Python structural (no-name) variant — same convention-probe-only gap.

ADR-0120 §3 explicitly lists "add optional ROM-name parameter to MepZipValidator.Validate and mep_lint.py" as a deferred follow-up but does not mention legacy root-level hires.txt as a valid fallback indicator; its existing fallback logic across all three implementations (C++, C#, Python) is scoped only to the textures/audio/synth convention-probe shape.

## Decision
Decide whether the structural (Python/C#) and/or name-anchored (all three: C++, C#, Python) fallback subfolder discovery should also accept a bare legacy-probe-basename match (hires.txt / preset.cfg / fingerprints.json with no textures//audio//synth/ wrapper required) as a valid discovery signal — and if so, under what ambiguity and resource-cap rules, consistent with ADR-0120 §2's existing fail-closed-on-ambiguity, depth-4/entry-cap-2000 discipline enforced in lockstep by verify_mep_fallback_constant_parity.sh.

Alternative: reject as out of scope, on the grounds that accepting a bare legacy basename without the textures/audio/synth wrapper shape would meaningfully weaken the "this really looks like a pack" signal that ADR-0120 §3 deliberately keeps tied to the convention shape, and instead close issue #48 by documenting that legacy-format community-pack submissions must be re-zipped/renamed so the wrapper folder (or a subfolder) matches the ROM name for the existing name-anchored fallback to apply.

If accepted, scope the follow-up implementation consistently across scripts/mep_lint.py, Core/Shared/EnhancementPacks/MepPack.cpp, and UI/Logic/MepZipValidator.cs, keeping any new depth/entry-cap constants in lockstep via verify_mep_fallback_constant_parity.sh, and re-validate issues #46 and #47 against the new logic to confirm they move from "Inválido" to "Aceito parcial (HD Mesen)".

## Consequences


## Alternatives

