# ADR-0044: Permissive ROM targets — dump normalisation and per-hash patches

- Status: accepted (F5.1, 2026-08-25)
- Date: 2026-08-25
- Fase 5 (docs/roadmap/plano-execucao-F5.md), F5.1.

## Context
Zelda Remastered v1.3 requires one exact PRG0 sha1: it ships an IPS that
rewrites game code so the HD audio registers get written. None of the user's
three dumps matched — one of them *was* PRG0 with 11 trailing `00` bytes.
Loose HD packs already ignore `<supportedRom>` (name-based matching) but gate
`<patch>` on the hash, and MEP `targets[]` accept N hashes. Applying an IPS
made for one revision to another produces a corrupt ROM, so the hash gate on
patches is a real safety property, not friction.

## Decision
1. **Dump normalisation** in `MepPackManager::ComputeNoIntroSha1`: for iNES,
   hash exactly the PRG+CHR size declared by the header (drops trailing
   garbage); trainer handling unchanged. Log raw and normalised hash.
2. **`patches[]`** in `pack.json`: `[{ "sha1": "...", "file": "rel/path.ips" }]`.
   A ROM that matches any `target` loads textures/audio/synth; the patch is
   applied only when an entry matches the ROM's sha1, otherwise skipped with a
   `[MEP] patch skipped` log and a UI notice.
3. **Opt-in override** "apply patch even if the hash differs" in
   EnhancementPackConfig, off by default, with an on-screen warning.

## Consequences
- Same-bytes dumps with padding work out of the box.
- Other revisions get everything except the patch (tile bitmaps are
  revision-independent; address-based conditions and backgrounds may misfire —
  that is the author's call via `targets[]`).
- Automatic IPS relocation across revisions is explicitly out of scope.
