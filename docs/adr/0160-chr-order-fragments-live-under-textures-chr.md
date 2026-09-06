# ADR-0160: The CHR-order fragments live under `textures/chr/` — `sheets/` is the front door

- Status: accepted (2026-09-05, by the user — record of a decision already reflected in the code: the move shipped in `a2139da6` and the legacy sweep of §3 in `2b12c5e2`. No PRD slice pending)
- Date: 2026-09-05
- Related: PRD Part A §4 "Phase 9" (slice F9.10, and the 2026-09-05 scrutiny
  against a target mockup, item 5), ADR-0153 §3/§5, ADR-0050, ADR-0049,
  ADR-0147, ADR-0005, MEP-v1 §2.1/§5.1
- Supersedes / amends: amends ADR-0153 (the bootstrap pack's top level is now
  three folders and a manifest; the CHR-order layer it inherited from ADR-0049
  moves one level down) and ADR-0049 (`Chr_XX_N.png` is no longer written at
  the pack root)

## Context

`HdPackBuilder::SaveHdPack` writes one 16×16-cell PNG per CHR bank/page, in CHR
order, and names it in `<img>`. It has always written them next to `hires.txt`.
On the 30-ROM library that is **12993 fragments** across the packs — 7.1 MB on
Punch-Out!! alone — and since ADR-0153 they sit beside the artist surfaces they
were supposed to be replaced by: `sheets/` (the metatile vocabulary, maps,
objects, sprites) and `backgrounds/` (ADR-0050's captured screens). Sorted by
name, `Chr_00_0.png` comes first; an artist opening the folder meets a wall of
8×8 fragments with no neighbourhood and has to know that the two folders below
are the ones to open.

They cannot be deleted. `hires.txt` renders from them: every `<tile>` line is
`<img>` index plus a pixel offset into that image, and the sheets under
`sheets/` are a *paint* surface that `scripts/mep_build.py` slices back into
`<tile>` lines — they are not themselves a rendering layer (ADR-0153 §6). Remove
the fragments and the pack renders nothing.

So the question is only *where they go*, and what happens to the packs already
on disk.

Non-goals: changing what the fragments contain, their geometry or their CHR
order; changing `hires.txt` semantics; a per-pack option (the layout is not a
user preference); touching a third-party HD Pack's layout — an external pack
keeps whatever shape its author shipped.

## Decision

### 1. They go to `<pack>/textures/chr/`, and `<img>` says so

The builder writes `chr/Chr_XX_N.png` (and, under `_writeReferences`, its
`chr/Chr_XX_N.orig.png` twin) and emits `<img>chr/Chr_XX_N.png`. The name is
`chr` because that is exactly what the layer is — the console's CHR, in CHR
order — and it sorts before `sheets/` alphabetically but reads as plumbing,
which `backgrounds/` and `sheets/` do not.

The top level of a bootstrap pack is then:

```
textures/
  hires.txt
  sheets/        <- ADR-0153: the artist surface
  backgrounds/   <- ADR-0050: the positional surface
  chr/           <- the CHR-order rendering layer
```

### 2. Nothing in the loader changes, because `<img>` was always a path

`HdPackLoader::LoadFile` resolves an `<img>`/`<background>`/`<patch>` target
against the pack root, for a folder pack (`FolderUtilities::CombinePath`) and a
zip pack (`ZipReader`) alike, and normalises backslashes before any tag is
parsed. `backgrounds/screenNNN.png` has been loading through that path since
ADR-0050. A subfolder in `<img>` is therefore not a new capability and needs no
version bump: the manifest is self-describing, so a pack in either shape loads
under the same code.

That is what makes the shape a **per-pack** property rather than a global one,
and it is why there is no fallback rule to write down: the loader never guesses
where a fragment is, it reads the path the manifest gives it.

### 3. Existing packs are not migrated; a pack being *re-recorded* is

Two shapes exist in the wild and both must keep working:

- **An old pack that is only ever read** keeps its top-level fragments and its
  root-relative `<img>` lines, and renders exactly as before. `auto/` is
  regenerable by construction (ADR-0153's consequences), so there is no reason
  to rewrite one in place, and no upgrade step for a user to run.
- **An old pack the builder re-records over** is a different case. The builder
  loads the existing `hires.txt` in its constructor and rewrites the whole pack
  at save time, so the new manifest names `chr/` while the old fragments stay
  behind at the top level — unreferenced by anything, and *exactly* the clutter
  this ADR removes. `PruneLegacyChrFiles` therefore deletes them, after
  `hires.txt` has been written (an interrupted save can never leave a manifest
  pointing at files that are gone) and restricted to names the builder itself
  writes (`Chr_<N>.png`, `Chr_<HH>_<N>.png` and the `.orig.png` twin of either)
  at the pack's top level only. `sheets/`, `backgrounds/`, `audio/`, and any
  file an artist added are never candidates. The count is logged.

The alternative — migrating every pack found on disk at load time — was
rejected: it makes the loader write to the user's files to fix a cosmetic
problem, on a path that also runs for read-only and zipped third-party packs.

### 4. The round trip does not learn about `chr/`

`scripts/mep_build.py` reads the key source's `<tile>` lines and **drops every
`<img>`**, re-emitting one per sheet it builds under `sheets/`. Where the
fragments live is therefore invisible to it, and that is the property to keep:
a built pack references `sheets/` alone, whatever shape its key source was in.
`scripts/test_mep_build.py` pins it by building the same fixture twice, once
with a root-relative and once with a `chr/`-relative `<img>` in the key source,
and requiring the two manifests to be byte-identical.

## Consequences

- The top level of a recorded pack goes from *N* fragments + `hires.txt` +
  two folders to **one file and three folders**, on every game. Measured on a
  300-frame Mega Man 3 bootstrap: 183 top-level entries → 4, and 1.89 MB of
  fragments moved out of the artist's first screen.
- `sheets/` and `backgrounds/` are what an artist meets, which is the whole
  point of Phase 9; `chr/` reads as plumbing on sight.
- A pack recorded before this ADR and a pack recorded after it are both valid
  and both load. Tooling that walks a pack must not assume either shape — it
  must read `<img>`. `UI/ViewModels/HdPackPreviewViewModel` scans the pack root
  *and* `chr/` for that reason.
- The builder now deletes files. The blast radius is bounded by name and by
  depth, but it is a deletion, and it is the one part of this change that could
  destroy an artist's work if the name test were ever loosened. Any future
  change to `PruneLegacyChrFiles` should be read as touching user data.
- `mep_lint` needed no change: it resolves `<img>` targets by path and reports
  a real `auto/` pack in the new shape with 0 errors and all 91 images found.

## Amendments (2026-09-06, code-review pass)

- §3 guard: `PruneLegacyChrFiles()` is skipped, with a log line, whenever the
  export dropped a tile on the upstream ">256 tiles of the same palette" path
  (`HdPackBuilder::_droppedTiles`). A truncated re-emit must never delete the
  artist's source `Chr_*.png`.
