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


## Alternatives

