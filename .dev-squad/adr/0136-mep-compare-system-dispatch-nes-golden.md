# ADR-0136: mep_compare.py system dispatch and an NES-shaped golden fixture

- Status: accepted (2026-08-27, work requested via docs/roadmap/PRD-mesence-enhancement-ecosystem.md; was: small, actionable; not implemented — `render_original` is still NES-only and the only golden texture pack is GB)
- Date: 2026-08-27
- Consolidates: ADR-0107, ADR-0117
- Related: ADR-0050 (uses `mep_compare.py` as its NES evidence tool), ADR-0132 (F5.4b evidence)

## Context

`scripts/mep_compare.py` compares the bootstrap's auto layer with an artist
pack. `render_original(chr_hex, pal_hex)` (`mep_compare.py:109-111`) does
`bytes.fromhex(chr_hex)` on a 32-hex NES CHR tile and slices an 8-hex NES
palette through `NES_PALETTE` (`for i in range(0, 8, 2)`), with no check of the
pack's `<system>` tag. GB/SMS `hires.txt` (see
`docs/specs/hires-gbsms-v1-draft.md` §"Tile identity key") use different tile
and palette encodings (`gb`: 2bpp tile + `TTPP` 4-hex register key; `gbc`:
18-hex CGB palette snapshot; `sms`: 4bpp tile + 36-hex CRAM snapshot), so
pointing the comparator at the repo's only checked-in golden MEP
texture pack — `docs/specs/golden/mep/textures/hires.txt`, which declares
`<system>gb` — raises a bare `ValueError` inside a list comprehension.

That already forced the F5.4b run to hand-roll a private `<system>nes` fixture
(`scripts/test_mep_compare_auto_palettes.py:60`) instead of reusing the
golden, and every future `mep_compare` test will duplicate the same fixture.
ADR-0117 framed the product line as "NES/GB/SMS/GBA"; note that GBA is not a
target of the HD-pack/MEP texture format at all — `docs/specs/MEP-v1.md`
hashes `gb`, `gbc`, `sms`, `gg`, `sg1000`, `coleco` and NES, and the
community-pack console taxonomy in `CLAUDE.md` is `console:nes`/`gb`/`gbc`/
`sms`. `docs/roadmap/AGENTS.md:17` does list GBA among product consoles on
`main`, but there is no GBA HD pack, so the comparator's scope is
nes/gb/gbc/sms.

## Decision

Do both halves; they are cheap and complementary:

1. **System dispatch in `render_original`.** Read `<system>` from the pack
   header (default `nes` when absent, matching Mesen's HD pack default) and
   dispatch: `nes` → current CHR/8-hex path; `gb`/`gbc`/`sms` → the tile and
   palette decoding of `hires-gbsms-v1-draft.md`. Any other value, or a palette
   string of the wrong width for the declared system, raises a single explicit
   `SystemExit`/`ValueError` naming the system and the expected widths
   (`"unsupported <system>gba; mep_compare supports nes, gb, gbc, sms"`),
   before any per-tile work. `palettes_per_shape` and the other stats stay
   system-agnostic.
2. **NES-shaped golden.** Add a minimal NES texture pack under
   `docs/specs/golden/mep/` (its own `textures/hires.txt` with `<system>nes`, a
   handful of tiles across at least two palettes for one shape, and the
   matching `pack.json` entry) so `test_mep_compare_auto_palettes.py` and
   future tests import it instead of building strings inline. `mep_lint.py`
   must pass on it like on the GB golden.

## Consequences

- `mep_compare.py` stops crashing on the project's own fixture and fails
  loudly on anything it cannot render.
- One shared NES fixture replaces per-test hand-rolled packs; the existing
  inline fixture in `test_mep_compare_auto_palettes.py` is migrated to it.
- GB/SMS comparisons become possible for the F2/F5 GB/SMS bootstrap, which
  today has no comparator at all.
- `docs/specs/golden/mep/path-cases.txt` and `scripts/AGENTS.md` (golden
  fixture bullets) need one line each for the new fixture.
- Accept once both halves land with `scripts/validate-specs.py` / `mep_lint.py`
  green on both goldens.

## Alternatives

- **Dispatch only, no NES golden** — still leaves every NES test hand-rolling
  fixtures; rejected as half a fix.
- **NES golden only, keep the comparator NES-only** — acceptable stopgap, but
  the bare `ValueError` on a GB pack remains a trap for the next GB/SMS task.
- **Convert the existing GB golden to NES** — rejected: the GB golden exercises
  the GB/SMS draft format paths in `mep_lint.py`; both systems need coverage.
- **Include GBA in the dispatch** — rejected: no GBA HD pack format exists.
