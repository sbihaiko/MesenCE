# ADR-0132: Per-shape palette-variant cap in the NES bootstrap HD Pack builder (F5.4b)

- Status: accepted (records the behaviour shipped by dev-squad run `a4420a72f7ae`, commits `76843ae0`, `bfba05e4`, `bcf333e4`; two follow-ups still open, see Consequences)
- Date: 2026-08-27
- Consolidates: ADR-0100, ADR-0101, ADR-0102, ADR-0103, ADR-0104, ADR-0105, ADR-0106, ADR-0108, ADR-0109, ADR-0110, ADR-0114, ADR-0115, ADR-0116, ADR-0119 (ADR-0112 and ADR-0113 are retired as process lessons, see Alternatives)
- Related: ADR-0050 (`<background>` screens — must NOT be amended with palette content), ADR-0043 (static ROM tile export as `DefaultTile` wildcard entries)

## Context

F5.4b was scheduled in `docs/roadmap/plano-execucao-F5.md` as a "palette
variant capture fix", and both the plan and `scripts/check-f5-4b-doc.sh`
(header comment, line 4) call it "ADR-0050 step (b)". That step never existed:
`.dev-squad/adr/0050-auto-screen-backgrounds.md` is entirely about
`<background>` screen capture and contains no palette-variant item and no
per-shape cap (ADR-0114). ADR-0050 must therefore not be amended for palette
matters — the "ADR-0050 step (b)" wording in the plan file and in
`scripts/check-f5-4b-doc.sh` should be repointed to this ADR.

The spec's premise was also false (ADR-0106, ADR-0108, ADR-0110, ADR-0112):
the "`DefaultTile` wildcard funnel" in `HdPackBuilder::ProcessTile` was dead
code. `HdTileKey::GetKey(true)` sentinels `PaletteColors` to `0xFFFFFFFF`
(`Core/NES/HdPacks/HdData.h`), a value no PPU palette word can produce, while
`_tileUsageCount` is only ever written with `GetKey(false)` keys
(`Core/NES/HdPacks/HdPackBuilder.cpp:101-102`, `AddTile`). So the wildcard
fallback could never match, and capture was already palette-specific and
**unbounded**: every distinct `(shape, PaletteColors)` sighting already got its
own `HdPackTileInfo`.

What was genuinely unbounded is per-shape growth. Measured on a 20 s
`roms/Zelda.nes` `hdpack` recording before the cap (recorded in the
`HdPackBuilder.h` field comment and in `scripts/validate_palette_variants.py`):
182 shapes, median 14 variants/shape, p95 15, p99 27, and a single all-zero
blank-tile shape reaching 71 — a mostly/fully flat tile renders identically
under any background palette, so unrelated screen state alone racks up
"distinct" palettes with no artistic value. The measured mean (~12.1
palettes/shape, ADR-0110) already exceeds the ~7.6 palettes/shape that ADR-0050
*measured* on Zelda Remastered — that figure was a measurement in 0050's
Context, never a target (ADR-0102 misread it). This is the substantive reason
F5.4b is closed: nothing needed fixing on the capture side; the only delivered
change is a bound.

The rationale so far lived only in a multi-KB single-line `**Status:**` header
(line 3 of `plano-execucao-F5.md`) and in the header comment of
`Core/NES/HdPacks/HdPackBuilder.h` — a behaviour-narrowing decision with no ADR
(ADR-0114). This ADR is that record.

## Decision

The following is what ships today in `Core/NES/HdPacks/HdPackBuilder.{h,cpp}`:

1. **Cap value.** `static constexpr uint32_t MaxPaletteVariantsPerTile = 32;`
   (`HdPackBuilder.h:44`), chosen above the measured p99 of 27 so real
   per-shape diversity survives intact and only the degenerate near-blank tail
   is bounded. It is a builder-local constant, not an `HdPackBuilderOptions`
   field (ADR-0116: YAGNI, no evidence the cap bites real content).
2. **Selection rule: order-first.** `CaptureOrCapPaletteVariant`
   (`HdPackBuilder.cpp:121-150`) keeps the first N distinct `PaletteColors`
   seen for a shape (`_paletteVariantsByShape[tile.GetKey(true)]`). On
   saturation it does not create a new entry; it bumps usage and
   `TransparencyRequired` on `variants.back()` (the most recently captured
   variant) and returns. No usage ranking, no palette-proximity selection
   (ADR-0104, ADR-0116). Which 32 palettes survive depends purely on encounter
   order during the recording session.
3. **Scope: per session, not per pack.** `_paletteVariantsByShape` is not
   seeded from an existing on-disk `hires.txt`: the constructor
   (`HdPackBuilder.cpp:35-50`) loads `_hdData.Tiles` and calls `AddTile`,
   which fills `_tilesByKey`/`_tileUsageCount` only. A re-record session can
   therefore add up to `MaxPaletteVariantsPerTile` more variants per shape on
   top of what is on disk. The header comment states this honestly
   (`HdPackBuilder.h:40-42`); `_screensSeen` (`HdPackBuilder.cpp:445-458`,
   ADR-0050's per-session cap of 300 screens) has the same gap (ADR-0109,
   ADR-0115).
4. **`DefaultTile` wildcard kept beside variants (pre-existing behaviour, not a
   change).** `AddRomTiles`/`AddPrgScanTiles` write the palette-agnostic
   wildcard into `_tilesByKey` under `GetKey(true)` (`HdPackBuilder.cpp:208,
   :280`, ADR-0043) and palette-specific entries (`DefaultTile = false`) are
   appended beside it. Draw-time resolution in `Core/NES/HdPacks/HdNesPack.cpp`
   (`:501`, `:509`) tries the exact key then the wildcard, so palettes never
   seen (or seen past the cap) still render through the wildcard ramp. Builder
   invariant: 0..N palette-specific entries + at most one wildcard per shape
   (ADR-0101, ADR-0105 — both non-decisions per ADR-0113, since the code
   already did this before and after the change).
5. **Evidence reports distributions, not ratios.**
   `scripts/validate_palette_variants.py` proves the cap on a real recording by
   reporting max variants per shape, shapes above 1 variant and shapes at the
   cap (requiring at least one shape to reach the cap so the check cannot pass
   vacuously). `palettes_per_shape` in `scripts/mep_compare.py:216,220`
   (`len(keys)/len(shapes)`) stays as a secondary figure only: a ratio rises
   with any key-count growth, including `PaletteColors` bits the renderer never
   uses, so it cannot separate coverage from key inflation (ADR-0103,
   ADR-0119). Rule for future coverage claims: report max, histogram and
   count-at-cap, not a mean.

## Consequences

- F5.4b is recorded as "bound per-shape palette-variant growth", not "fix a
  wildcard collapse". The plan header and `HdPackBuilder.h` already say so;
  `scripts/check-f5-4b-doc.sh:4` and `.dev-squad/runs/a4420a72f7ae/spec.md`
  still cite "ADR-0050 step b" and should be repointed here (doc-only).
- Runtime effect: palette combinations beyond the 32nd for a shape fall
  through `HdNesPack`'s exact-key lookup to the wildcard entry (if the shape
  came from ROM/PRG export) or to un-enhanced NES rendering otherwise.
  Practical severity is low because 32 sits above the measured p99.
- **Open follow-up (a), not yet implemented — saturation log.**
  `CaptureOrCapPaletteVariant` saturates silently (`HdPackBuilder.cpp:130-140`:
  no log, no pack-side marker). Emit one core log line the first time a shape
  saturates, so headless runs and `mep_compare` evidence can distinguish "the
  game has N palettes" from "the builder stopped at N". Without it, F5.4c/F5.4d
  coverage reporting cannot detect that the cap is biting (ADR-0102, ADR-0116).
- **Open follow-up (b), not yet implemented — seed or document.** Either seed
  `_paletteVariantsByShape` in the constructor from `_hdData.Tiles` (group
  non-`DefaultTile` entries by `GetKey(true)`) so the cap becomes a pack-level
  invariant, or make `scripts/AGENTS.md:88-89` ("never letting any single
  shape exceed") and the `validate_palette_variants.py` docstring/check text
  (`:19`, `:128`) say explicitly that the bound is per-session. Rule going
  forward: every new tracking map in `HdPackBuilder` is either ctor-seeded from
  `_hdData` or documented as session-scoped wherever its bound is asserted
  (ADR-0109, ADR-0115).
- Revisit the cap value or selection rule only if F5.4c/F5.4d coverage
  reporting (with the saturation log in place) shows real content being
  dropped.

## Alternatives

- **Tunable `HdPackBuilderOptions` field** with the constant as default
  (ADR-0100) — rejected for now: YAGNI per ADR-0116; 32 > p99 27 and no
  session has shown the cap biting. Reopen only with saturation evidence.
- **Usage-ranked top-N per shape** instead of first-N-seen (ADR-0104,
  ADR-0106) — deferred; kept as the follow-up option if order-first truncation
  is shown to lose common palettes.
- **Low-entropy/near-blank shape filter** instead of a flat numeric cap
  (ADR-0108) — not implemented; the header comment identifies flat tiles as
  the source of the long tail, so an explicit skip of such shapes remains a
  candidate instrument.
- **Cap of 8–16 derived from ADR-0050's ~7.6 figure** (ADR-0102) — superseded
  by measured data (median 14 would already be truncated).
- **Amend ADR-0050** (ADR-0101, ADR-0108, ADR-0110) — rejected: 0050 has no
  palette content; this ADR is the record instead.
- **ADR-0112 and ADR-0113** were process lessons, not architecture decisions,
  and are retired as ADRs: (1) a "fix defect X" spec must carry a reproduction
  of X (a failing check, a log line, a measured number) before Spec/Decompose;
  (2) critic issues that do not cite a verified line of code are unranked
  until confirmed. They belong in dev-squad guardrails
  (`/dev-squad:squad-guardrails`), not here.
