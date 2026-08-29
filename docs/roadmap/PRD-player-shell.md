# PRD — Player shell (minimal GUI)

**Status:** active (2026-08-28) — product text of §3–§6 accepted by the
user on 2026-08-28; P.0 done (ADR-0139/0140/0141 accepted 2026-08-28);
P.1 done (content_id in scripts/ + Core, mep-meta + `.mep-install.json`,
golden parity — 2026-08-29); P.2 done (catalog/mep-meta/MEI identity +
one slot per pack_id — 2026-08-29); P.3 done (per-ROM preference resolver
+ Advanced picker — 2026-08-29). P.4–P.6 are runnable slices; P.6 waits for
F6.4b ·
**Author:** sbihaiko ·
**Scope:** MesenCE fork (`main`); nothing goes upstream ·
**Parent roadmap:** [PRD-mesence-enhancement-ecosystem.md](PRD-mesence-enhancement-ecosystem.md)
(Phase 7). Pack/core work stays there (Phase 6 F6.4b/c/F6.5, Phase 5,
input tester). This document owns chrome, pack identity, duplicates, and
the player-facing choice between packs ·
**Specs:** [MEP-v1](../specs/MEP-v1.md) · [MEI-v1](../specs/MEI-v1.md) ·
[MEP-recipe-v1](../specs/MEP-recipe-v1.md) ·
**Decisions:** identity model (§3) and one-slot rule (§3.6) are accepted
product requirements, specified by ADR-0139 (`content_id`), ADR-0140
(`pack_id`, catalog uniqueness) and ADR-0141 (one slot, client update
trigger — amends ADR-0138 §37). Chrome (§6) is a product requirement; it
needs an ADR only if P.4 finds trade-offs beyond what §6 states ·
**Process:** one dev-squad run per **slice** (P.1, P.2, …). Settle the
slice's ADRs first. A slice is done when its acceptance checks pass and
this header plus the parent roadmap's Phase 7 entry are updated.

---

## 1. Vision

The fork's thesis is *faithful, then enhanced, on by default*. The current
GUI is still classic Mesen: File / Game / Options / Tools / Debug / Help,
plus debugger, HD Pack Builder, netplay, movies, Lua. That chrome is
correct for authors and for anyone who already lives in Mesen. It is the
wrong first screen for a player who should drop a ROM and already hear and
see the enhanced game.

Default chrome becomes a **player shell**: recent games, drop a ROM, the
game fills the window, packs apply themselves, a thin overlay for pause /
save / pack / settings. **Advanced GUI** restores the classic Mesen menus
and tools unchanged.

This is one Avalonia process and one window, not a second binary. Player
and Advanced are chrome modes over the same ViewModels.

The legal principles of the parent PRD §1 still apply: the official
channel carries URLs + hashes + licences, never third-party assets; hosts
never execute pack content as code; no LLM in the client.

Product consoles stay NES, GB/GBC/GBS, SMS/GG/SG-1000, GBA
(`docs/roadmap/AGENTS.md`). SNES gamepads stay as input.

## 2. Problem

Three pack-identity problems and one chrome problem.

**Identity**

1. **The zip the catalog hashes is not the pack.** Community submissions
   are GitHub `/archive/` trees, release zips, nested folders, whole
   repos. After ADR-0120/0121 discovery (and a MEP Recipe, when there is
   one) the host loads a *subset* of that zip. Two wrappers of the same
   tree look like two packs if identity is the source sha256. One primary
   zip plus two different recipes is two packs even when the source
   sha256 matches. Today's "Pack Hash" (mep-meta `source_sha256`, MEI
   `sha256`) is the download, not the pack.
2. **A content hash alone cannot version a pack.** Contra80s 1.0 and 1.2
   are the same product and two artifacts. If the unique id is the
   resolved-tree hash, they look like two competing packs for the same
   ROM and the player is asked to choose. Updates need a stable lineage
   id; integrity and duplicate-bytes detection need the content hash.
3. **Several real packs can target the same ROM.** That is not a
   duplicate. The player has to pick one, and the choice has to stick
   per ROM. Today the host applies the first lexicographic container
   (ADR-0040) and hides the rest behind Tools → Enhancement Packs (MEP)….

**Chrome**

4. **The GUI fights the product.** Enhanced Audio is already on by
   default (`AudioConfig.EnableEnhancedAudio = true`); bootstrap already
   writes `<Game>/auto/` beside the ROM; F6.4b will auto-install from the
   catalog. None of that reads as a player product while Debug and HD
   Pack Builder sit in the menu bar.

## 3. Pack identity — two ids, not one

A pack is a *product* that has *revisions*. Treating the content hash as
"the" unique id makes versions look like different packs. Treating the
source-zip sha256 as "the" unique id makes wrappers look like different
packs. Neither is sufficient alone.

### 3.1 Four names, four jobs

| Name | What it identifies | Changes when | Already exists? |
|---|---|---|---|
| **`pack_id`** | the product (lineage). "This is Contra80s by Tastic." Shared by every revision | never, unless it is a different product | no — new (§3.3) |
| **`content_id`** | one revision: the canonical resolved pack tree the host will load | any loaded file changes | no — new (§3.2) |
| **`version`** | human/semver label of that revision | the author bumps it (can lie; `content_id` is the truth) | yes — `pack.json` `version` (MEP-v1 §3.1, MUST); absent on `hd-legacy` |
| **`source_sha256`** | the downloaded bytes (the wrapper) | the zip wrapper changes, even if the inner tree does not | yes — board "Pack Hash", mep-meta `source_sha256`, MEI `sha256`, `.mep-install.json` `source.sha256` |

Also **not** a pack id:

- **ROM No-Intro sha1** — the game. Many packs share one; one pack may
  list several `targets[]`.
- **GitHub issue number** — the submission. A second issue can be the
  same `pack_id` (duplicate submit) or a different one (competing pack).
  Useful as catalog provenance (`issue`, already in MEI v1.1 §2.2), not
  as the product id.
- **Container file name** — the local discovery key (ADR-0040/0049). It
  is the fallback `pack_id` for a folder the user dropped (§3.3), never a
  catalog id.

### 3.2 `content_id` — identity of a revision

Computed **on the tree the host would actually load**, not on the zip
bytes: discovery first (MEP-v1 §2.1 rules 5–9, ADR-0120/0121), then the
recipe when one exists.

- **No recipe:** unzip → find the pack root → hash that tree. A GitHub
  archive whose pack lives in `HdPacks/Contra (U) [!]/` hashes only that
  subfolder. `__MACOSX/`, `.DS_Store`, README, screenshots outside the
  root do not enter the id.
- **With a recipe:** `content_id` is a function of (hash of the resolved
  *primary* tree, `recipe_hash`, the declared dep sha256s). CI can compute
  it without fetching `user_supplied` deps (it has the primary zip and the
  recipe's declared digests). Two recipes on the same primary zip are two
  revisions. The same recipe plus the same deps is the same revision even
  if CI never saw the dep bytes. The client computes the same function
  **at install time**, when `MepRecipeInstaller` still holds the primary
  bytes, and stores the result in `.mep-install.json` (§4); it does not
  re-derive it from the installed output tree.

Exact canonicalisation (path order, which files, newline folding, zip
entry metadata ignored, whether `pack.json` `version` is part of the
payload) is the P.0 ADR. The product constraint is: **same loaded files
⇒ same `content_id`; wrapper-only change ⇒ same `content_id`; any
loaded-file change ⇒ new `content_id`.** Recommendation for the ADR:
hash payload files, not the `version` string, so a label-only bump is not
a new revision.

`content_id` answers: *are these two artifacts the same bytes the
emulator will play?* It does **not** answer: *is this Contra80s 1.2 or a
different Contra pack?*

The algorithm has **two implementations, one normative reference**, like
the recipe interpreter (ADR-0138 §39): `scripts/` (CI, normative) and the
Core (client). A parity fixture keeps them equal.

### 3.3 `pack_id` — identity of the product

Stable across revisions. Source, first match wins:

1. An explicit `id` field in `pack.json` (slug, lowercase, unique in the
   official catalog). This is a MEP minor bump and part of the P.0 ADR.
   Best long-term id; authors already have `name`/`version`/`author`.
2. Else, for a `github.com` / `codeload.github.com` pack URL:
   `owner/repo` (the origin, not the tag or release filename).
   `/archive/v1.2.zip` and `/releases/download/v1.2/pack.zip` of the same
   repo are the same product.
3. Else, catalog fallback: `issue-{n}` of the accepted submission. This
   is the only option for gists, `raw.githubusercontent.com` and Google
   Drive links (`scripts/pack_host_allowlist.json`) when the pack has no
   `id` — so for those hosts **product-level deduplication does not
   exist**; only byte-level (`content_id`) does.
4. **Local drops** (a folder or zip the user put in `EnhancementPacks/`,
   `HdPacks/<Game>/` or beside the ROM) with no `id`: `pack_id` is
   `local:<container-name>` (the ADR-0040/0049 discovery key). Two local
   containers with the same `content_id` are one pack (§5). A local
   container whose `content_id` equals a catalog entry's is that catalog
   `pack_id`, not a second choice. The local `content_id` is computed
   **once** and cached under `EnhancementPacks/.cache/` keyed by the
   container's path + size + mtime (recomputed only when those change);
   it is never computed on the synchronous ROM-load path. Until the cache
   is warm the container is treated as `local:<container-name>`; the
   catalog merge happens on the next load. HD trees run to hundreds of
   MB — hashing them at every boot is not acceptable.

**Catalog uniqueness** (product requirement; enforcement is the P.0 ADR).
The catalog holds **one live row per `pack_id`** (§3.6) — never two
revisions of the same product.

**Origin binding (anti-hijack).** A `pack_id` is bound to the **origin**
of its first accepted submission: the `owner/repo` of the pack URL, or,
for hosts without one (gist, raw, Drive), the GitHub login that opened the
issue. A later submission that claims an existing `pack_id` (via `id` in
`pack.json` or via the same `owner/repo`) but comes from a **different
origin** is *not* a revision: it does not compete for the slot, is not
listed, and gets a comment + the `pack:needs-review` label for human
triage — a maintainer may re-bind the origin (author moved repos) or
treat it as a competing pack. Without this rule anyone could publish
`id: contra80s`, `version: 99.0.0` and have §3.6 push it to every
client. The catalog stores the bound origin in mep-meta
(`pack_origin`). Amends ADR-0140/0141 (recorded in both, 2026-08-28).

Actions when the incoming submission is from the **same** origin:

| Incoming vs existing | Meaning | Action |
|---|---|---|
| same `content_id` | byte-duplicate, even if `pack_id`/`version`/`source_sha256` differ | not a second pack; comment "duplicate of #N"; do not list twice |
| same `pack_id`, new `content_id` | new revision of that product | occupies the single slot if it wins §3.6's order; never a picker choice. Triage warns when `version` did not bump |
| different `pack_id`, different `content_id`, same ROM sha1 | competing packs | both listed; the player chooses (§5) |
| different `pack_id`, same `content_id` | same files under two names | byte-duplicate; the existing row wins |

`/revalidate` on the same issue rewrites that issue's **provenance**
(mep-meta: `source_sha256`, recomputed `content_id`, `version`,
`validated_at`) in place. Whether the revalidated revision **occupies the
slot** follows §3.6 — a revalidation that republishes a lower semver does
not displace a higher one already in the slot.

### 3.4 `version`

Keep `pack.json` `version` (semver, MUST for MEP). It is a **label**, not
an id. On its own it is not sufficient to know "newest" (authors forget to
bump, or bump without changing files) — but it is the best available
*ordering* signal, which is why §3.6 uses it first and `content_id`
(unordered) never.

- `hd-legacy` has no `version`; the catalog and picker show the
  validation date and a short `content_id` prefix instead.
- `version` bumps, `content_id` does not → the revision did not change
  (wrapper-only, or a label bump). The client does not re-download.
- `content_id` changes, `version` does not → still a new revision of that
  `pack_id`. Triage warns; §3.6 still applies.

Do not order competing *products* by `version`.

### 3.5 Why not one id

| Candidate as "the" unique id | Breaks |
|---|---|
| `source_sha256` (Pack Hash) | wrappers; pack is a subset; two recipes on one zip |
| `content_id` alone | every revision is a new pack; the player is asked to choose between 1.0 and 1.2 |
| `pack_id` alone | cannot tell duplicate bytes from an update; cannot verify an install |
| `version` alone | not unique; authors forget to bump; two products can both be "1.0" |
| ROM sha1 | many packs per game |
| issue number | second submit of the same product; local drops have no issue |

The pair **`pack_id` + `content_id`** is the split npm (`name` + integrity
hash), git (ref + commit) and Docker (`name:tag` + digest) already use. A
single-id scheme is not proposed.

### 3.6 Current revision — one catalog slot

**`content_id` is equality/integrity only.** The official catalog has
**one live slot per `pack_id`**; whatever occupies that slot *is* current.
The player never sees 1.0 vs 1.2 of the same pack.

When two candidates compete for the same slot, the first rule that
decides wins:

1. **semver** of `pack.json` `version`, when both have a comparable
   version — higher wins. The catalog knowingly accepts that an inflated
   `version` can win **from the same origin** (§3.3 origin binding);
   triage warns, it does not block. `mep_lint` already rejects any
   non-`x.y.z` `version` (error), so "comparable" only fails for
   `hd-legacy`, which has none.
2. Else **`validated_at`** — later wins.
3. Else **issue number** — higher wins (later submission).

History may live in mep-meta / git; it is not a second catalog row and
not a player choice.

**Client**

- Compare the installed `content_id` (from `.mep-install.json`) to the
  catalog slot of the chosen `pack_id`. Different → reinstall, power
  cycle, toast ("Updated …"). Wrapper-only change (`source_sha256`
  changed, `content_id` did not) → do not reinstall. **This amends
  ADR-0138 §37**, whose trigger is `source.sha256`; the P.0 ADR records
  the amendment.
- **No automatic downgrade.** If the installed revision's semver is
  *greater* than the slot's (yank, rollback, author republished an older
  label), keep the install; Advanced may offer "use catalog revision" with
  confirmation. `hd-legacy` (no semver): a `content_id` difference against
  the slot still updates — there is no version number to protect.
- **Pack removed from the catalog** (no slot for that `pack_id` any
  more): keep the install, keep the per-ROM choice, no toast. It stays
  visible in Advanced; the player is not interrupted by a catalog
  decision.
- Reinstall preserves the user's per-container state (`DisabledPacks`,
  per-section flags — both keyed by container name today), since the
  container name does not change on an update.
- Sibling folder still always wins. No catalog write, no update, no
  picker while it is present.

Old trees may remain under `EnhancementPacks/.cache/`; they are not
listed in the picker and are not applied.

## 4. Applying a pack to a ROM

Already shipped, and this GUI must not bypass it:

1. Load ROM → No-Intro sha1 (ADR-0039).
2. `MepPackManager::LoadForRom` scans **sibling folder →
   `HdPacks/<Game>/` → `EnhancementPacks/`** (ADR-0049/0040/0120/0121).
3. A container matches when any `targets[].sha1` equals the ROM, or when
   it is a convention pack named like the ROM (MEP-v1 §2.1 rule 5).
4. Per section, the first pack in lexicographic container order wins,
   unless the user disabled that container. The sibling folder beats
   everything, in every section.
5. `patches[]` apply in place before the console reads the ROM
   (ADR-0044). Missing patch for this sha1 → skip the patch with a log
   line and a UI notice, still load the other sections.
6. Per-section toggles and enable/disable apply on the **next load /
   power cycle**, not live. Pack switch in the player stays a power
   cycle. Do not invent live texture/patch swap in this phase.

F6.4b (parent roadmap, not this PRD) adds: fetch official MEI, match ROM
sha1, download within the host allow-list, sha256-verify the *source*, run
`MepRecipeInstaller`, write into `EnhancementPacks/`, then the scan above
applies it. The `AutoInstallCommunityPacks` toggle and first-run consent
stay in F6.4b (ADR-0138 §38).

This PRD adds, on top of that scan:

- At install time, record `pack_id` + `content_id` in `.mep-install.json`
  next to `recipe_hash`, `source.sha256`, `deps`, `installed_at` (all
  already written by `MepRecipeInstaller::WriteInstallStamp`).
- On the next load of that ROM sha1, follow §3.6: new `content_id` on the
  chosen `pack_id`'s catalog slot → update (unless it would be a semver
  downgrade).
- Sibling folder still always wins. No catalog auto-install, no picker,
  while a sibling pack is present (artist at work).

## 5. Choosing among packs for the same ROM

Not a duplicate. Two `pack_id`s with the same ROM sha1 and different
`content_id`s are competing products (Contra80s vs another Contra HD
pack).

**Player mode**

- 0 catalog/local matches → play with Enhanced Audio + bootstrap only.
  If F6.4b is on and the catalog later gains a match, offer install as a
  toast; never stall the first frame.
- 1 `pack_id` (any number of revisions on disk or in history) → apply
  the catalog slot (§3.6). No picker. Never ask 1.0 vs 1.2.
- 2+ `pack_id`s and no stored choice for this ROM sha1 → the game starts
  **un-enhanced** (Enhanced Audio + bootstrap only) and the picker opens
  over it, once. Picking applies on the power cycle the picker triggers;
  dismissing plays un-enhanced this session and asks again next launch.
  The picker shows name, `author` (from `pack.json`; `hd-legacy` shows
  the submission title), `version` (or validation date + short
  `content_id` for `hd-legacy`), layers (textures / audio / synth /
  patch), licence (or "not declared"), and catalog 👍 as **sort key**, not
  as auto-pick. The choice is remembered **per ROM sha1** — the No-Intro
  sha1 of the ROM as loaded, **before** any `patches[]` apply (§4 step 1
  precedes step 5) — a pack with three `targets[]` is chosen up to three
  times, once per ROM.
- Changing the choice later: overlay → current pack chip → picker.
  Applies on power cycle.
- Mixing section A from pack 1 with section B from pack 2 is **Advanced
  only** (today's Enhancement Packs window and per-section toggles).
  Player picks a whole pack.

**Advanced mode** keeps Tools → Enhancement Packs (MEP)… as it is: list
of matching containers, per-pack enable, per-section flags, lexicographic
default when nothing is chosen. When a per-ROM choice exists (P.3), it
overrides the lexicographic default in Advanced too, and the window shows
which container is the chosen one.

**Local + catalog.** A user-dropped container in `EnhancementPacks/`
whose `content_id` equals the pack already chosen for this ROM is the same
pack, not a second choice. A local container with a different
`content_id` and no `id` joins the picker as `local:<container-name>`
(§3.3 rule 4). The merge only works for packs whose `content_id` is a
tree hash: the *output* folder of a recipe install copied elsewhere
without its `.mep-install.json` cannot be re-associated with the catalog
row (§3.2 — the recipe composite is never derived from the output tree);
it shows up as a `local:` entry. Documented non-goal (§7).

**Where 👍 comes from.** The client has no GitHub access. P.2 adds an
additive MEI field (`votes`, integer, MAY, non-normative like `issue`)
written by the catalog generator from the submission issue's 👍 count.
Clients ignore it for install decisions; the picker uses it only to sort.

## 6. Player chrome and Advanced GUI

One process. `PreferencesConfig.UiMode`: `Player` | `Advanced`.

| | Player (default on a fresh install) | Advanced |
|---|---|---|
| Menu bar | hidden | classic File / Game / Options / Tools / Debug / Help |
| Home (no ROM) | the existing recent-games grid (`RecentGamesViewModel`), always shown; drop a ROM anywhere | same grid, as today (`GameSelectionScreenMode` keeps its current meaning: what happens when a recent game is clicked; `Disabled` still hides the grid) |
| Playing | game fills the window; the overlay shortcut opens a thin overlay: Resume, Save/Load slot, Pack (if 2+ `pack_id`s, or to inspect the current one), Settings (video / audio / input essentials), Advanced GUI, Quit | current menus and windows |
| Overlay shortcut | a new configurable `EmulatorShortcut` (default Esc on keyboard; `KeyCombination` already accepts controller buttons, so a gamepad binding is a config choice, no new code). Default rule in Player: while a ROM runs, Esc opens the overlay and never leaves fullscreen; "Exit fullscreen" is an overlay item. P.4 implements that precedence inside the shortcut config, not by hard-coding | n/a |
| Gamepad navigation | the overlay and the pack picker are fully operable with D-pad/A/B (Avalonia focus navigation; no pointer required). Acceptance of P.4/P.5 includes a keyboard-arrows pass as proxy | n/a |
| Pack feedback | OSD toast on apply/update ("Applied Contra 80s — textures"); pack name on the overlay chip | Enhancement Packs window |
| Debugger, HD Pack Builder, Lua, netplay, movies, cheats, Record Music | not in the overlay; reachable only after switching to Advanced | unchanged |
| Existing `AutoHideMenu` | ignored in Player (no menu bar); left in Advanced preferences | unchanged |

Switching modes is instant and persisted. **Default rule:** when the
settings file already exists at startup and has no `UiMode` key, the
value is `Advanced`, so a current Mesen user is not stripped of Debug on
upgrade. When no settings file exists (fresh unzip), `UiMode` is `Player`.
The key is always written on first save, so the rule only ever runs once.

Do not fork ViewModels. Player hides chrome and routes a small overlay at
windows that already exist (open-ROM dialog, save slots, a reduced
settings page, the pack picker). Advanced is the current `MainMenuView`.

## 7. Non-goals

- A second executable or a rewrite off Avalonia.
- Live swap of textures/patches without power cycle.
- Auto-picking the 👍 leader when two `pack_id`s match; 👍 only sorts
  the picker.
- A full pack browser (search, extra MEI URLs). The parent PRD defers
  that until the catalog outgrows a list.
- Replacing F6.4b. This PRD consumes it.
- Hosting or committing pack bytes.
- Changing discovery precedence (sibling still wins).
- Product-level deduplication for packs without `id` hosted outside
  GitHub (§3.3 rule 3).
- Re-associating a recipe *output* folder copied without its
  `.mep-install.json` with its catalog row (§5).
- SNES / PCE / WonderSwan / ColecoVision chrome.

## 8. Slices

Architecture slices need their ADR accepted first. P.3–P.5 run on local
packs and do not wait for F6.4b; catalog install/update in the overlay
(P.6) does.

| Slice | Deliverable | Depends | Acceptance |
|---|---|---|---|
| **P.0** | ADR-0139/0140/0141 (accepted 2026-08-28): (1) `content_id` canonicalisation, the recipe composite, and the two-implementation/parity rule; (2) `pack_id` sources incl. the MEP `id` field and the `local:` fallback; (3) catalog uniqueness (§3.3) + one-slot occupancy (§3.6) as CI/client policy, **amending ADR-0138 §37** (update trigger = `content_id`, no auto-downgrade) | — | **done 2026-08-28** — ADR-0139/0140/0141 accepted; ADR-0141 carries the ADR-0138 §37 amendment |
| **P.1** | `content_id` in `scripts/` (normative) **and** in the Core (`MepPackManager`/`MepRecipeInstaller`), both on the discovered pack root and the recipe composite; `mep_lint` / validate workflow writes it to mep-meta; `.mep-install.json` gains `pack_id`/`content_id`. Goldens: same tree in two wrappers → same id; two recipes on one primary → two ids | P.0 | **done 2026-08-29** — `scripts/mep_content_id.py` (normative) + `scripts/test_mep_content_id.py` (8 checks) + `Core/Shared/EnhancementPacks/MepContentId.{h,cpp}`; `mep_lint --content-id` + the validate workflow's `content-id` step write the tree hash (and the recipe composite for split packs) into mep-meta; `MepRecipeInstaller::WriteOutputs` computes the composite at install time and `WriteInstallStamp` records `pack_id`/`content_id` in `.mep-install.json`; parity fixture `docs/specs/golden/mep-content-id.json` run by `scripts/test_mep_content_id_golden.py` (Python) and core-unit-tests BlocoG (C++), both green |
| **P.2** | Catalog / mep-meta / MEI grow `pack_id`, `content_id`, `version`, `votes` (all additive; unknown-field ignore already required). One live row per `pack_id` (§3.6). Duplicate comment on same `content_id`. `/revalidate` rewrites provenance and occupies the slot only by §3.6 order. Origin binding (§3.3): mep-meta `pack_origin`; different origin → not listed, `pack:needs-review` (label added to `ensure_community_pack_labels.sh`) | P.1 | **done 2026-08-29** — `scripts/pack_id_rules.py` (leaf, stdlib-only): `resolve_pack_id` (MEP `id` → `owner/repo` → `issue-n`), `pack_origin` (§3.3), `slot_winner`/`select_catalog_rows` (§3.6: content-dedup global, per-pack_id origin filter then slot winner — semver → validated_at → issue, deterministic) + `scripts/test_pack_id_rules.py` (8 checks); `mei_catalog_entry.build_pack_entry` gains additive `pack_id`/`content_id`/`votes` (MAY, via `apply_mei_identity`); the validate workflow's mep-meta upsert writes `pack_id`/`pack_origin`/`content_id` and a new `identity-check` step (`scripts/mep_identity_check.py`, `--post`, `continue-on-error`) comments on duplicate `content_id` / foreign-origin claims; `pack:needs-review` label (13th) added to `ensure_community_pack_labels.sh`; the generator was split per ADR-0138 §35 into `mei_catalog_fetch` (all `gh` reads) + a 123-line orchestrator feeding `select_catalog_rows` (rows still 👍-sorted by `render_table`); AC-2/AC-4/AC-6 verifiers updated for the split and green; `make doc-checks` green |
| **P.3** | Per-ROM-sha1 preference (`pack_id` chosen, `local:` fallback for local drops) persisted in `EnhancementPackConfig`; the **resolution logic** (sha1 → `pack_id`, `local:` fallback, `content_id` merge, lexicographic default) lives in a host-free class under `UI/Logic/` (ADR-0123: `UI.Tests` dual-compiles only `UI/Logic/**`, never `UI/Config`). Picker window usable from **Advanced** (ships before Player chrome). The preference overrides lexicographic order; lexicographic stays the default when no preference exists | P.0 (for the `pack_id` rules) | **done 2026-08-29** — `UI/Logic/PackPreferenceResolver.cs` (host-free): `DerivePackId` (stamped pack_id, else `local:<container>`, ADR-0140 rule 4) + `Resolve` (content_id merge — a container duplicating another's content_id is not a new entry — and preference → winning container, lexicographic default when none/stale); `scripts/`-side `.mep-install.json` identity exposed as pack_id/content_id columns 9–10 of `GetMepPackList` (parser extended, 8-column rows still accepted); `EnhancementPackConfig.RomPackPreference` (romSha1 → pack_id, reset-then-push via the new `ClearPreferredMepPacks`/`SetPreferredMepPack` interop) drives the core's per-ROM preferred pack (`MepPackManager::FindPreferredPack`, consulted before the ADR-0040 order in `GetPackForSection`); Advanced's Enhancement Packs window gained a "Preferred pack for this ROM" combo (content-merged choices + "(default)" clear). UI.Tests: `PackPreferenceResolverTests` (11 checks incl. `local:`, merge, stale, disabled) + 194 total green; `make core`/`ui`/`doc-checks` green |
| **P.4** | `UiMode` + Player chrome: hide menu, overlay + its shortcut, recent games as home, Settings subset, Advanced switch. Existing settings file → Advanced; none → Player | — (chrome only) | UI.Tests for the default rule (file present / absent); manual pass: Player cannot reach Debug without switching; Esc collision resolved in shortcut config |
| **P.5** | Player pack UX: toast, overlay chip, picker from §5 wired to P.3; un-enhanced start while the picker is open | P.3, P.4 | two local packs: first launch picks, second launch silent; dismissing the picker plays un-enhanced and asks again next launch; sibling folder suppresses the picker |
| **P.6** | Player overlay talks to F6.4b install/update using §3.6 (`content_id` trigger, no auto-downgrade, removed-from-catalog keeps install); `votes` sorts the picker | P.5, F6.4b | catalog update of the chosen `pack_id` reinstalls and keeps `DisabledPacks`/section flags; wrapper-only does not reinstall; installed semver > slot does not downgrade; removed slot keeps the install; competing `pack_id`s still open the picker |

## 9. ADR map

| Topic | Status | Meaning |
|---|---|---|
| ADR-0139 — `content_id` algorithm (tree canonicalisation, recipe composite, excluded files, `version` string excluded, two implementations + parity) | **accepted** (2026-08-28) | P.1 cannot start without it |
| ADR-0140 — `pack_id` (MEP `id` field; `owner/repo`; `issue-n`; `local:<container>`) + catalog uniqueness + origin binding (amended 2026-08-28) | **accepted** (2026-08-28) | P.2/P.3 cannot start without it. §3.6 is accepted product text — the ADR specifies enforcement |
| ADR-0141 — one live slot per `pack_id`; amends ADR-0138 §37 (client update trigger `source.sha256` → `content_id`); no auto-downgrade; removed slot keeps install | **accepted** (2026-08-28) | P.6 conflicts with the accepted text until amended |
| Player chrome (`UiMode`, overlay contents, overlay shortcut, upgrade default Advanced) | **needed only if** P.4 finds trade-offs beyond §6 | P.4 |
| ADR-0039/0040/0044/0049/0120/0121 | accepted | precedence and ROM hash-matching do not change |
| ADR-0138 (except §37 as above) | accepted | F6.4b is the network installer this shell consumes |

## 10. Risks

| Risk | Mitigation |
|---|---|
| `content_id` treated as the pack id | §3.5–§3.6; picker and preference key off `pack_id`; `content_id` is equality/integrity only |
| Catalog yank / republished older semver | no auto-downgrade (§3.6); Advanced confirms |
| Authors omit `id` / `version` (`hd-legacy`) | fallbacks in §3.3/§3.4; keyed by origin repo or issue; picker shows date + hash prefix |
| Two issues, same product, different `pack_id` fallbacks (non-GitHub hosts) | `content_id` still collapses byte-duplicates; remaining cases open the picker (safe default); documented non-goal until `id` is common |
| Inflated `version` wins the slot | accepted trade-off (§3.6 rule 1) **within one origin**; triage warns; no auto-downgrade protects installs |
| Third party claims an existing `pack_id` (`id` or `owner/repo` spoof) with a high `version` | origin binding (§3.3): different origin never occupies the slot; `pack:needs-review` for a human |
| Hashing local HD trees stalls the ROM load | `content_id` of local containers cached by path+size+mtime, computed off the load path (§3.3 rule 4) |
| Overlay unusable from the couch | overlay shortcut bindable to a controller button; overlay/picker navigable by D-pad (§6) |
| Recipe identity without dep bytes | composite in §3.2; computed at install time from the primary bytes, stored, not re-derived |
| `scripts/` and Core hashers drift | parity fixture in P.1, same pattern as ADR-0138 §39 |
| Local-pack identity ambiguous | `local:<container>` rule (§3.3 rule 4); `content_id` merges local ↔ catalog |
| Player chrome accidentally ships a second UI stack | P.4 acceptance: no new debugger/settings rewrite; hide and overlay only |
| Esc collides with existing shortcuts | configurable `EmulatorShortcut`; P.4 resolves in shortcut config |
| Scope collision with F6.4b | P.6 waits; P.3–P.5 work on local packs |

## 11. Open questions

None for P.0 — the four questions this section held (tree-hash
canonicalisation; MEP `id` field now; duplicate-submit policy; silent
`local:` → catalog `pack_id` migration) were closed by ADR-0139/0140/0141
on 2026-08-28 (hash: ADR-0139; `id` as MEP v1.4 SHOULD, comment + close
the newer duplicate issue, silent migration: ADR-0140). New questions go
here only when a slice surfaces a trade-off §3–§6 do not settle.

## 12. References

- Parent roadmap: `docs/roadmap/PRD-mesence-enhancement-ecosystem.md`
- Discovery / precedence: ADR-0040, ADR-0049, ADR-0120, ADR-0121
- ROM hash: ADR-0039, MEP-v1 §4
- Catalog / recipe / auto-install: ADR-0138 (§37–§39), MEI-v1 §2.2,
  MEP-recipe-v1
- Host allow-list: `scripts/pack_host_allowlist.json`
- Install stamp: `Core/Shared/EnhancementPacks/MepRecipeInstaller.cpp`
  (`WriteInstallStamp`)
- Current pack UI: `UI/ViewModels/EnhancementPacksViewModel.cs`,
  `UI/Config/EnhancementPackConfig.cs`
- Current chrome: `UI/Views/MainMenuView.axaml`,
  `UI/Windows/MainWindow.axaml`, `UI/ViewModels/RecentGamesViewModel.cs`
