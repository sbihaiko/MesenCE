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

## Clarifications (after run 2fd5d89d0471, 2026-08-28)

The first H4 run failed at Decompose: the proxy never approved because the
Decision above left four points open. They are settled here (the five
auto-minted review ADRs, which reused the retired ids 0139–0143, are folded
and deleted):

1. **Layout — sibling roots, never nested.** The NES golden lives at
   `docs/specs/golden/mep-nes/` (own `pack.json`, `textures/hires.txt` with
   `<system>nes`, one small PNG), next to the GB golden at
   `docs/specs/golden/mep/`. A MEP pack root must never contain another pack
   root: `mep_lint.py` ignores unknown subfolders today, but that is an
   implementation detail, not a MEP layout guarantee. The Decision's "under
   `docs/specs/golden/mep/`" is superseded by this paragraph. The GB golden is
   **not** moved (its path is a literal in `scripts/core_unit_tests.cpp` and
   `validate-specs.py`).
2. **No `path-cases.txt` line.** The Consequences bullet asking for "one line
   in `path-cases.txt`" was wrong: that file is the zip-slip path-safety
   corpus (ADR-0124), not a fixture index. Fixture registration is
   `scripts/AGENTS.md` (golden bullet) plus a `validate_mep(...)` call for
   `mep-nes/pack.json` in `validate-specs.py` `main()`.
3. **Golden lint green-ness is owned by `validate-specs.py`.** The GB golden
   was red under its own linter (declared `audio` section without
   `audio/hires.txt`) and nothing caught it. Fixed by hand before the rerun
   with a header-only `audio/hires.txt` (the C++ golden test requires all
   three sections declared, so dropping the section was not an option).
   H4 adds a `lint_golden_packs()` step to `validate-specs.py` that runs
   `scripts/mep_lint.py` as a subprocess over `docs/specs/golden/mep/` and
   `docs/specs/golden/mep-nes/` and fails on a non-zero exit — the tripwire
   that makes "mep_lint green on both goldens" a checked invariant.
4. **`render_original` API.** Keep the free function; add a keyword
   `system: str = "nes"` and make `Pack` expose the header's `<system>`
   (default `nes`) as `pack.system`, so the three call sites pass
   `system=artist.system`. The `(chr_hex, pal_hex)` tuple stays the dict
   key for coverage math. A bound `pack.render(key)` method was considered
   and rejected as churn for a 235-line script.

## Clarifications (after run a2f602e039ee, 2026-08-28) — shipped

Run `a2f602e039ee` shipped both halves (merged as `2c4aefb9`: dispatch,
`docs/specs/golden/mep-nes/`, `lint_golden_packs()`, migrated
`test_mep_compare_auto_palettes.py`, new `test_mep_compare_render_dispatch.py`).
Its review raised eight findings, folded here (auto-minted files reused the
retired ids 0139–0146 again — deleted); the real ones were fixed in the
follow-up commit:

5. **`<system>` is a legal NES header tag.** `mep_lint.py` `NES_TAGS` now
   includes `system`, whose value must be `nes` in a NES `hires.txt` (error
   otherwise); `HdPackLoader` ignores unknown tags, so the golden's header is
   harmless to Mesen. This keeps `pack.system` as the one declaration
   mechanism every fixture uses, instead of relying on the absent-header
   default. The NES golden now lints with 0 warnings.
6. **Tile-data width is per system too.** `Pack._parse` filtered `<tile>`
   lines on a hard-coded 32-hex width, so every SMS tile (32 bytes 4bpp =
   64 hex) was dropped and an SMS pack "compared" as empty. Fixed with a
   `_TILE_HEX_WIDTH` table; the parser reads the header (`<system>`) in a
   first pass because nothing in the format orders it before the first
   `<tile>`. Covered by `check_sms_tiles_parse` (late header, 64-hex tile).
7. **Two error messages, not one.** An unsupported system and a wrong-width
   palette for a supported system were both reported as "unsupported
   <system>X". Now: `unsupported <system>gba; mep_compare supports …` for
   formats that do not exist; `<system>gg is a valid pack format but not
   implemented in mep_compare yet; …` for `gg`/`sg1000`/`coleco` (legal per
   the draft and `mep_lint`, deliberately outside this v1); and
   `<system>nes expects a 8-hex palette key, got 2` for a malformed key.
8. **Deferred, on purpose.** The system membership is encoded in several
   places (`mep_lint.KNOWN_SYSTEMS`, `validate-specs.SYSTEMS`, the GB/SMS
   `<system>` check, the draft §3.1, `mep_compare.SYSTEMS`). A single shared
   table (system → tile width, palette width, comparator support) would turn
   each divergence into an explicit flag. Not done here: it crosses three
   scripts for a cosmetic gain today; revisit when a fifth consumer appears.
