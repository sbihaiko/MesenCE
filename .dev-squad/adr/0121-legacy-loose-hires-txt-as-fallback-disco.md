# ADR-0121: Legacy loose hires.txt as fallback discovery signal in MEP zip wrapper folders

- Status: accepted (2026-08-27 — option A chosen by the user; already shipped in `805cb10d` across Python, C# and C++; MEP-v1 §2.1 rule 9 wording shipped with F6.1)
- Date: 2026-08-27
- Extends ADR-0120 §2/§3 (subfolder fallback for wrapped zips). Motivated by issues #46, #47, #48.

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
**Option A.** The structural (Python/C#) and name-anchored (C++, C#, Python) fallback subfolder discovery also accept a bare legacy-probe-basename match (`hires.txt` / `preset.cfg` / `fingerprints.json` with no `textures/`/`audio/`/`synth/` wrapper) as a valid discovery signal, under the same fail-closed-on-ambiguity and depth-4/entry-cap-2000 rules as ADR-0120 §2, enforced in lockstep by `verify_mep_fallback_constant_parity.sh`. Implemented in `805cb10d` across `scripts/mep_lint.py`, `Core/Shared/EnhancementPacks/MepPack.cpp` and `UI/Logic/MepZipValidator.cs`; the 2026-08-27 re-triage of the community packs (#62–#73, all legacy HD Mesen shape, several in GitHub `/archive/` wrappers) validated through it.

Legacy HD Mesen packs (bare root `hires.txt`, no `pack.json`) are therefore an accepted submission class. The spec still lacks the sentence: MEP-v1 §2.1 rule 9 must describe the bare-basename acceptance path — this doc item is part of roadmap slice F6.1 (`docs/roadmap/PRD-mesence-enhancement-ecosystem.md`), which touches §2.1/§6 anyway.

## Consequences
Option A — extend the structural fallback to bare legacy basenames:
- Issues #46 and #47 (raw GitHub `/archive/refs/heads/<branch>.zip` downloads wrapped in a repo-named folder) validate without the submitter re-zipping; the triage board moves them from "Inválido" to "Aceito parcial (HD Mesen)".
- The "this really looks like a pack" signal weakens: any zip with a `hires.txt` somewhere in its first four path segments becomes a candidate, so the fail-closed ambiguity rule (more than one candidate → reject) and the depth-4/entry-cap-2000 bounds from ADR-0120 §2 carry more weight and must be applied identically in all three languages.
- Three implementations change (Python, C#, and — for load-time parity — C++ `MepPack::FindFallbackSubfolder` / `ResolveFallbackPrefix`, which today has no structural, no-ROM-name variant at all), plus the parity script.
- MEP-v1 §2.1 rule 9 must be amended to describe the bare-basename acceptance path.

Option B — reject and require re-zip/rename:
- No code change; ADR-0120's convention-shape signal stays as tight as designed.
- Issue #48 is closed by documentation: legacy-format submissions must be re-zipped (or the wrapper folder renamed) so the existing name-anchored fallback applies. Submitters of #46/#47 have to act, and the same friction will recur for every raw GitHub archive download of a legacy pack.
- Runtime behaviour stays aligned with what the C++ loader already does (name-anchored only), so validators do not accept anything the engine would reject.

## Alternatives
- **A. Accept bare legacy probe basenames as a discovery signal** in the structural fallback (and optionally the name-anchored one), under the same fail-closed-on-ambiguity, depth-4/entry-cap-2000 rules as ADR-0120 §2, implemented in lockstep across Python, C# and C++.
- **B. Reject as out of scope**: keep the fallback tied to the textures/audio/synth convention shape (ADR-0120 §3) and document that legacy community-pack submissions must be re-zipped or renamed so that the wrapper folder (or a subfolder) matches the ROM name, letting the existing name-anchored fallback apply.
- Not considered viable: accepting the first plausible candidate without an ambiguity rule — already rejected by ADR-0120 for non-determinism.

