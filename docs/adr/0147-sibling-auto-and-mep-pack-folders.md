# ADR-0147: Sibling-pack folders `auto/` (recorder) and `mep/` (edited MEP pack), installed visible by default

- Status: accepted
- Date: 2026-09-01
- Related: ADR-0049 (sibling-folder convention), ADR-0040 (storage/discovery precedence), ADR-0138 §4 (client install output), ADR-0050 (auto backgrounds), ADR-0146 (auto-load accepted packs), MEP-v1 §2.1/§5.1.
- Supersedes / amends: the "output location" clause of ADR-0138 §4; the sibling-folder layout of ADR-0049 (the human layer moves from the pack root to `mep/`); the `auto/` resolution note of ADR-0050 (now recorded in MEP-v1 §2.1).

## Context

Today a community pack installed from the catalog is materialized in the
central per-ROM folder `EnhancementPacks/<container>/` (ADR-0040) — the same
place `HdPacks` uses — with the download staged in `EnhancementPacks/.cache/downloads/`
(ADR-0138 §4, §46). The bootstrap recorder writes its machine layer to the
ROM sibling folder `auto/` (ADR-0049). The *applied* pack is therefore not
visible beside the ROM: an artist or curious user who wants to see or edit
the pack that is actually playing must hunt through `EnhancementPacks/.cache`.

The user's direction is a simpler, legible model with exactly two child
folders under the game folder, so the applied pack is visible and editable
by default and customization is encouraged, with a **Restore** action to undo
local changes.

## Decision

For `<dir>/<Game>.<ext>`, the game folder `<dir>/<Game>/` holds two sibling
child folders:

```
<dir>/<Game>/
  auto/    # RECORDER (machine): the bootstrap writes textures + audio + synth here, already MEP-compatible
  mep/     # PACK (human/catalog): the pack, unzipped and MEP-ized, with pack.json + textures + audio + synth, editable
```

- **`auto/`** = the machine layer (ADR-0049). The bootstrap keeps writing
  `auto/<convention>`; it is the "recorder" that produces MEP-compatible
  content. Same role as today.
- **`mep/`** = the pack layer (human/catalog). A catalog pack is materialized
  here as a complete MEP pack (`pack.json` + `textures/` + `audio/` + `synth/`,
  plus its own `auto/` if the catalog pack carries one). It is the editable
  layer.
- **Precedence per entry: `mep/` > `auto/`.** What exists in `mep/` wins; what
  is missing in `mep/` is filled from `auto/`. This is the "human wins, auto
  added" resolution the loaders already perform (`MergeLowerLayer`), with the
  human layer now rooted at `mep/` instead of the pack root.
- **Install output.** A catalog pack is materialized to `<Game>/mep/`
  (non-writable ROM folder → fall back to the central `EnhancementPacks/<container>/`,
  per ADR-0049). Applies to both MEP-recipe packs (via `InstallMepRecipe`) and
  `hd-legacy` packs, which are **MEP-ized** on install (a `pack.json` is
  generated and the content lands in `mep/textures/`), so every installed pack
  is in the MEP format.
- **Restore.** An explicit action that deletes `mep/` and re-materializes it
  from the original catalog artifact (the zip in `.cache/downloads/`, or a
  re-download), undoing local edits. The install registry (ROM → active
  `pack_id` → `content_id` → `source.sha256` → `mep/` path) lives in the
  central cache (`EnhancementPacks/.cache/installs/<romsha1>.json`), *not*
  inside `mep/`, so a mangled `mep/` never destroys the ability to restore.
- **Local-edit detection.** Whether the `mep/` tree differs from the installed
  state is decided by recomputing the tree `content_id`
  (`MepContentId::ComputeTree`) and comparing it to the `content_id` recorded
  in the install stamp. On `Updated` (P.6), a locally-edited pack is **not**
  silently overwritten; the client offers "Restore & update" (drop the edit,
  take the new version) or "keep changes".
- **Identity (Phase 7) is preserved.** The catalog keeps one live slot per
  `pack_id`; a local edit is client state, not a catalog version. When 2+
  packs compete for the same ROM (P.5), `mep/` materializes the **active**
  pack; installing another replaces it (`ClearFolderForReinstall`).

## Consequences

- Installed packs are visible and editable beside the ROM; curious users can
  tweak `mep/` and the change applies (the human layer wins), and Restore
  reverts to the original.
- The bootstrap recorder (`auto/`) and the installed pack (`mep/`) no longer
  collide: each owns its own folder, and the previous ambiguity over two
  `auto/`-style layers is gone.
- `MepPackManager` must recognize `mep/` as the sibling's human layer while
  keeping the legacy root layout working (a sibling without `mep/` still loads
  as before — backward compatibility for existing authoring folders).
- The install path must resolve `mep/` under the sibling with a central
  fallback, and the hd-legacy install path must MEP-ize instead of writing to
  `HdPacks/<rom>/`. This makes the hd-legacy loader path (`HdPacks/`) unused for
  catalog installs, though it remains for hand-placed loose packs.
- ADP/ADR churn: ADR-0138 §4's "central per-ROM folder" output is superseded
  for catalog installs; ADR-0049's sibling layout is amended (human layer at
  `mep/`); MEP-v1 §2.1 records the host convention (amend, below).

## Alternatives

- Keep central-per-ROM install (status quo) — rejected: the applied pack is
  invisible to the artist/curious user, which is the whole problem.
- Materialize `mep/` as a *symlink* to the central pack — rejected: editing
  through a symlink edits the managed central copy (so P.6 update can still
  clobber the edit), it does not resolve the bootstrap `auto/` collision,
  and directory symlinks are unreliable/privileged on Windows.
- Materialize the pack at the sibling root (`<Game>/textures`, etc.) instead of
  `mep/` — rejected: it collides with the bootstrap's `auto/` (two owners of
  the same root) and with the Phase 7 one-pack-per-ROM identity model.
- Symlink-free convenience only ("Open pack folder") — rejected: it gives
  visibility but not the default-editable workflow and Restore the user asked
  for.

## Spec amendment (MEP-v1 §2.1)

Add a host-convention note: a MesenCE sibling pack may materialize its human
layer at `<Game>/mep/` (with `pack.json`) and its machine layer at
`<Game>/auto/`, as sibling folders; precedence is per entry, `mep/` over
`auto/`; the ADR-0050 exception (auto `<background>` screens are not merged
under a human `textures/` layer) is re-stated for this layout.
