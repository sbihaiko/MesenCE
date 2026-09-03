# ADR-0144: Audio packs may supply their .ogg tracks via a bundled ROM patch and install-time extraction

- Status: accepted
- Date: 2026-08-29
- Amended by ADR-0148 (2026-09-01): a bundled `.ips`/`.bps` counts only when it is
  also wired (`<patch>` line / `patches[]` entry), not merely present in the archive.

## Context
The LiQuiDz 'NEA audio' packs (1942, Dr_Mario, SMB2, Yie Ar) bundle only a .ips/.bps ROM patch plus a hires.txt whose audio section references .ogg tracks that are not in the zip. The .ogg are generated at install time by the extract-audio flow (ADR-0135) from the patched ROM. The strict MEP-v1 §5 file-resolution rule (a section only counts when its referenced files resolve in the archive) made the classify judge these invalid, even though the packs are functional in Mesen via that flow. User decision: amend the rule so this legitimate pattern is recognized.

## Decision
A pack's audio section counts as usable when its hires.txt references .ogg tracks (bare filenames or under any path) AND the zip bundles a .ips/.bps ROM patch that is present in the archive — the tracks are supplied at install time by the extract-audio flow (ADR-0135), mirroring the ADR-0138 §2/§7 external-assets exception. There is no path constraint on the .ogg references: the loader resolves each ref against the pack folder as written (`FolderUtilities::CombinePath(_hdPackFolder, <ref>)`, HdPackLoader.cpp `ProcessBgmTag`), so the install-time extraction must produce the tracks at exactly the referenced paths, and the patch being present in the archive is the whole redeeming condition. The classify prompt (validate-classify.md) is amended accordingly: a missing .ogg target is NOT by itself a reason to invalidate a patch-bundling audio pack.

## Consequences

Implementation state (verified 2026-09-01):
- Classify rule: `.github/ai/validate-classify.md:33` (AUDIO EXCEPTION) — a missing `.ogg` target does not invalidate a patch-bundling audio pack; `assets` gains `ips`/`bps` from the bundled-patch magic (:34); the `patches[]` field is passed through to the assembled `pack.json` (:38).
- Lint signal: `scripts/mep_lint.py:1112-1136` reports every bundled `.ips`/`.bps` as `bundled patch: <name> (present, wired — …)` or `(present, NOT wired — …)`, kept even in `--quiet` output (:1239-1241) because it is the classifier's authority; tests in `scripts/test_mep_audio_patch_resolution.py` (`6d16c55f`).
- Loader side unchanged: `HdPackLoader.cpp` `ProcessBgmTag` resolves each `.ogg` ref as written against the pack folder, so the extraction must produce exactly the referenced paths.
- Amended by ADR-0148 (2026-09-01): presence alone no longer redeems — the patch must be wired (`<patch>` line / `patches[]` entry). Under that tightening the eight LiQuiDz NEA siblings accepted under this ADR were de-listed from `docs/community-packs.json` (ADR-0148 rules 1–2); `mep_lint`, the classify prompt and this ADR's header all carry the amendment.
Not implemented: the install-time extraction itself — the extract-audio tool (ADR-0135, `NesConsole::ExtractAudioHdPack`, `Core/NES/NesConsole.h:77`) is a separate headless process and is not invoked by `UI/Services/CommunityPackInstallCoordinator.cs` or the legacy install path, so an accepted patch-bundling audio pack is classified as usable but its `.ogg` tracks are not generated automatically on install yet.

## Alternatives

- Keep MEP-v1 §5 strictly (every referenced file must resolve in the archive): rejected — it marked functional Mesen NEA packs invalid (Context).
- Require the `.ogg` under a conventional audio directory: rejected — the loader resolves refs as written, so a path constraint would add nothing the patch-presence condition does not already carry.
- Ship the generated `.ogg` in the catalog artifact: rejected — the tracks are derived from the copyrighted ROM; only the binary patch is redistributable.
- Redeem missing textures/synth sections by a bundled patch too: rejected — the patch supplies audio only (`validate-classify.md:33`).
- Count a patch that is merely present (this ADR's original text): superseded by ADR-0148 — an unwired patch is never applied and redeems nothing (#128).
