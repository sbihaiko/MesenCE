# PRD — Community Pack → MEP Conversion Tool

**Status:** draft ·
**Author:** sbihaiko (drafted by Claude Code from a manual spike, 2026-08-27) ·
**Date:** 2026-08-27 ·
**Scope:** MesenCE fork ·
**PRD (parent):** [PRD-ecossistema-enhancement-comunitario.md](PRD-ecossistema-enhancement-comunitario.md) §4.2.2 (MEP format), §Phase 3 (MEP host — done) ·
**Spec:** [MEP-v1.md](../specs/MEP-v1.md) — this tool is a *producer* of MEP-v1 containers, it defines no new format ·
**Out of scope:** does not touch the C++/C# core or `Core/Shared/EnhancementPacks/`; this is a tooling-only initiative (Python script + optional CI wiring), same boundary as `scripts/mep_lint.py`.

---

## 1. Context and motivation

The "MesenCE Community Packs" triage pipeline (`.github/workflows/community-pack-validate.yml`,
`docs/specs/MEP-v1.md`) accepts third-party HD packs and classifies them as
`partial_hd` or `mep_full`. A manual spike on 2026-08-27 materialized all 12
currently-accepted packs into MesenCE's classic loose-`HdPacks/<rom>/`
layout, to test them in the real emulator (see git history around
`scripts/mep_lint.py`'s `discover_sections`/`find_fallback_subfolder*`
reuse). Two things fell out of that spike that motivate this PRD:

1. **None of the 12 accepted packs are in MEP format.** Every one of them
   is the pre-MEP legacy shape — a bare `hires.txt` at the pack's root, no
   `pack.json`, picked up only via `mep_lint.py`'s loose/legacy fallback
   (ADR-0049). MEP v1 (Phase 3, done) has had a working host in the core
   since 2026-08-24, but nothing in the pipeline ever *produces* a MEP
   container from what gets accepted — packs are validated, labeled, and
   left exactly as submitted.
2. **The containers these packs arrive in are wildly inconsistent**, and
   the spike had to special-case several shapes by hand:
   - clean nested path (`Contra80s-v1.1/Contra (U) [!]/hires.txt`, #33)
   - a whole-GitHub-repo archive with a wrapper folder
     (`Megaman-Super-main/`, #34; `HDNes-Graphics-Pac-master/`, #46;
     `ZII-mesen-main/`, #47)
   - bare root, no wrapper at all (#36, #38, #39, #41, #44, #45)
   - a named subfolder that isn't the wrapper convention
     (`Yie Ar Kung-Fu (Japan)/`, #43)
   - a **zip nested inside the downloaded zip**, alongside unrelated bonus
     folders (`ZeldaRemastered.zip` inside the Google Drive download, #35
     — already handled by `mep_lint.py` issue #19's fallback)
   - a **Google Drive large-file interstitial** that needs a confirm-token
     dance before the real bytes are reachable at all (#35)
   - **upstream drift breaking automatic discovery after acceptance**:
     issue #34's source repo gained `Customization/` variant subfolders
     with their own `hires.txt` files sometime after the pack was
     validated, so `find_fallback_subfolder` now sees 5 candidates and
     fails closed (ambiguous) where it once saw 1 — the spike had to fall
     back to "shallowest `hires.txt` wins" by hand.

Every one of those cases was resolved by *reusing* `mep_lint.py`'s own
`Source`, `discover_sections`, `find_fallback_subfolder`,
`find_fallback_subfolder_by_name`, and `find_top_level_nested_zip` —
proven, already-tested code, not new discovery logic. That reuse is the
foundation this PRD builds on.

## 2. Goals

1. **Convert any accepted community pack from its as-submitted container
   into a canonical MEP v1 container** — the §2.1 folder-form convention
   (`<Game>/textures/hires.txt`, `<Game>/audio/...`, `<Game>/synth/preset.cfg`)
   as the default target, since it needs no `pack.json` and every one of
   the 12 packs surveyed only ever has a single `textures` (or, after the
   community-pack-validate.yml `assets`-tagging fix already shipped,
   possibly `audio`) section — a bare-manifest pack.json only pays for
   itself once a pack combines sections or wants declared `patches[]`.
2. **Resolve the pack root the same way the CI already validated it** —
   call the exact same `mep_lint` discovery functions (not reimplement
   them), so a converted pack can never disagree with the verdict already
   posted on its issue.
3. **Auto-populate what the classify step already knows.** Since
   `community-pack-validate.yml`'s classify step now emits `assets`
   (`textures`/`audio`/`ips`/`bps`, shipped 2026-08-27), a `pack.json`
   variant of the output (Phase 2 below) can pre-fill `sections` and a
   `patches[]` skeleton from that same structured output instead of
   re-deriving it.
4. **Surface, never silently paper over, the edge cases the spike hit by
   hand**: an ambiguous root (multiple `hires.txt` candidates, #34's
   drift), a patch file with no license/rights statement, or a section
   whose referenced files are 100% missing (#37/#40/#42's actual invalid
   packs) must all produce a clear, actionable message — not a
   best-effort guess baked silently into the output.

### Non-goals (explicit)

- **Not hosting or committing converted third-party pack content in this
  repository**, ever — same legal boundary the parent PRD already draws
  (§2 non-goals: "Not hosting, bundling, or distributing derivative
  content... in any project repository"). Converted output is a local
  artifact (CLI output dir, or a CI *artifact* download) — never a commit,
  never a PR, never checked into `docs/community-packs.md` or any tracked
  path.
- **Not fabricating missing assets.** If a section's referenced OGG/PNG
  files are missing from the source (as in #37/#40/#42), the converter
  reports that section as unconvertible — it does not invent placeholder
  content to force a "complete-looking" MEP container.
- **Not adjudicating ROM-patch licensing.** When a bundled `.ips`/`.bps`
  patch has no accompanying rights statement, the tool emits a
  `patches[]` entry with a `"license": "TODO — needs manual review"`
  marker (or omits the patch and warns) — it never invents a license.
- **Not a new discovery algorithm.** Every "which folder is the real pack
  root" decision must delegate to `scripts/mep_lint.py`'s existing
  functions; this PRD adds no parallel implementation of that logic.
- **Not automatic/unattended for every case.** The Google Drive
  confirm-token dance and genuinely ambiguous roots (§4, Edge cases) are
  explicitly allowed to require a human-supplied hint or a manual
  download, per Non-goal above on not guessing.

## 3. Phases

### Phase 1 — `scripts/mep_convert.py`: folder-form converter (CLI)

- **F1.1** `import mep_lint` (same pattern the spike script used) to get
  `Source`, `discover_sections`, `find_fallback_subfolder`,
  `find_fallback_subfolder_by_name`, `find_top_level_nested_zip` for free.
  No copy-pasted discovery logic.
- **F1.2** CLI: `python3 scripts/mep_convert.py <pack.zip|dir> <rom_name> <out_dir>`.
  Resolves the pack root exactly as `mep_lint.py main()` would, then
  writes the §2.1 folder-form layout under `<out_dir>/<rom_name>/`:
  `textures/hires.txt` + referenced assets when a textures-shaped section
  was found, `audio/hires.txt` (or the resolved audio layout) when an
  audio-only section was found — mirroring whichever section
  `discover_sections` actually reported, never both unless both are real.
- **F1.3** On an ambiguous or unresolved root (mirrors #34's drift), exit
  non-zero with the candidate list printed — do not guess. `--root
  <prefix>` lets a human pin the choice explicitly (covers the "shallowest
  hires.txt" case the spike improvised, but as an explicit opt-in, not a
  silent default).
- **F1.4** On a bundled `.ips`/`.bps` file with no accompanying
  license/rights text in the issue body, print a warning and exclude the
  patch from the output by default; `--include-unlicensed-patches` opts in
  for local testing only (never for anything that leaves the machine).
- **Success criterion:** running F1.2 against all 12 currently-accepted
  packs' pack URLs (docs/community-packs.md + the 3 not yet in the catalog
  from CLAUDE.md's documented drift) reproduces the spike's 12 materialized
  folders, with `textures/hires.txt` (or `audio/...`) replacing the bare
  root `hires.txt` the spike used — same content, correct MEP-v1 §2.1 shape.

### Phase 2 — `pack.json` variant + `assets`-aware generation

- **F2.1** `--manifest` flag: emit a `pack.json` (§3 of MEP-v1) instead of
  bare folder-form, with `sections` populated from either a fresh
  `mep_lint`-style content scan or, when available, the `assets` array
  already computed by the classify step for that issue (avoids a second,
  possibly-diverging content analysis).
- **F2.2** ROM identification (§4): compute the No-Intro hash the same way
  `scripts/fetch_pack.py`/the validate workflow already record ROM
  SHA1/MD5 on the board, and fill `pack.json`'s `targets`.
- **Success criterion:** `mep_lint.py`'s own `lint_pack_json` reports 0
  errors against the generated manifest for every one of the 12 packs.

### Phase 3 — Optional CI wiring (opt-in, not automatic)

- **F3.1** A `/convert-to-mep` issue comment on an *accepted*
  (`pack:partial-hd`/`pack:mep-full`) issue triggers Phase 1+2 in CI and
  uploads the result as a workflow **artifact** (never a commit/PR) — the
  submitter or a maintainer downloads it locally.
- Explicitly **not** wired into the default validate-on-submit flow: this
  stays opt-in so no converted content is ever produced (or implied
  archived) without a human asking for it, consistent with the Non-goals
  above.

## 4. Edge cases this PRD must not silently drop (evidence from the spike)

| Case | Pack | Handling |
|---|---|---|
| Nested zip-in-zip | #35 (Zelda, Google Drive) | Delegate to `mep_lint.find_top_level_nested_zip` (already exists) |
| Google Drive virus-scan interstitial | #35 | Out of automatic scope (Non-goals) — document the manual confirm-token steps used in the spike as a one-time README note, don't automate scraping Google's confirmation flow |
| Whole-repo archive wrapper folder | #34, #46, #47 | `find_fallback_subfolder`/`_by_name` already strips this when unambiguous |
| Upstream drift after acceptance (multiple `hires.txt` now) | #34 | F1.3: fail closed with the candidate list, require `--root` |
| ROM patch bundled with no license | #37, #40, #42 (rejected, but same shape could recur in an *accepted* pack that also carries a patch) | F1.4: exclude by default, explicit opt-in only |
| Section with 0% functional content | #37, #40, #42 | Not applicable to *accepted* packs by construction (the classify-step fix from 2026-08-27 already requires real usable content per section) — still worth a defensive check in F1.2 so a future rule regression can't produce a hollow MEP container |

## 5. Open questions

- Does Phase 3's artifact-based distribution satisfy the actual testing
  need, or is a purely local Phase 1 CLI enough indefinitely? (Lean toward
  shipping Phase 1 first and revisiting.)
- Should `--include-unlicensed-patches` exist at all, or should unlicensed
  patches always be a hard exclusion with no override? (Currently framed
  as local-testing-only; revisit once Phase 1 is in use.)
