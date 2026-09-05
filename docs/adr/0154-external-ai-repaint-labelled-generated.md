# ADR-0154: The optional AI repaint is an external, backend-pluggable script whose output lands in `auto/`, is labelled `generated` in `pack.json`, and is never eligible for the community catalog

- Status: accepted
- Date: 2026-09-05 (accepted 2026-09-05, after the user settled §2)
- Related: PRD Part A §4 "Phase 9" (slice F9.6 and validation test 8),
  ADR-0153, ADR-0049, ADR-0147, ADR-0050, ADR-0005, ADR-0140, ADR-0152,
  ADR-0148, ADR-0138 §41, MEP-v1 §3.1/§3.2, CLAUDE.md "Community HD/MEP Pack
  triage"
- Supersedes / amends: nothing. ADR-0153's non-goal ("AI generation inside the
  emulator — F9.6 stays an external script under its own ADR") is this ADR.

**This ADR is `accepted`.** It was written `proposed` because §2 was a genuine
either/or; the user picked **Option A** (local diffusion + ControlNet) on
2026-09-05, and §2 below is now written as that decision rather than as a
menu. The honesty caveats that were attached to each option are kept verbatim
where they still bear on the choice — in particular the licensing statements
were **not** verified against the licence texts in this task, and §2 says so.

## Context

ADR-0153 gave the bootstrap an artist surface: `textures/sheets/` holds a
metatile vocabulary, stitched maps and object sheets, each with a sidecar JSON
that `scripts/mep_build.py` slices back into `hires.txt` entries. The artist
paints a sheet in any image editor and the change reaches the emulator without
anyone opening `hires.txt`.

The obvious next question is whether a machine can do the first pass of that
painting — take `metatiles.png` and `map-NNN.png` and hand back a higher
resolution repaint that keeps the silhouettes. The PRD lists it as F9.6 and
guards it with validation test 8 (blind A/B against the artist pack, three
reviewers, five screens), explicitly "go/no-go by the user".

Three constraints shape the answer before any model is named.

1. **The input is copyrighted art.** A sheet is a rearrangement of a
   commercial game's CHR data. That is fine as a local, per-user artifact — it
   is what the whole `auto/` layer already is — and it is exactly what must
   not be pushed to a third party or published. This constrains the backend
   choice at least as hard as any model licence does, and it is the reason a
   hosted API is not the default.
2. **The catalog has provenance rules.** The community catalog exists to list
   *artists'* packs (`docs/community-packs.md` renders an "Author" column read
   off the pack itself, never off the submitter's login; ADR-0148 requires a
   self-contained, verifiable artifact). A machine repaint of Nintendo's art,
   submitted as somebody's pack, would poison that. The PRD row for F9.6 says
   it plainly: "labelled as generated in `pack.json`, never eligible for the
   community catalog as an artist pack."
3. **AI generation must stay outside the emulator.** ADR-0153's non-goals and
   the PRD's Phase 9 non-goals both say so. Nothing here links into `Core/`,
   loads weights at runtime, or adds a setting.

There is also a build-order trap worth naming up front:
`scripts/bootstrap_auto_packs.sh` does `rm -rf "$folder/auto/textures"` before
reinstalling a fresh recording. Anything written into `auto/textures/` is
therefore deleted by the next bootstrap run. §4 places the output accordingly.

**Non-goals.** Training a model, shipping weights, bundling a model in the
installer, calling any model from the emulator, generating audio, generating
*new* art (an unseen sprite, an invented tile) — this is a repaint of existing
cells, with the original as the structure constraint. Also not a goal: making
the repaint reproducible across machines. A generative backend is not
bit-reproducible and this ADR does not pretend otherwise; only the
non-generative backends (`passthrough`, `classical`) are deterministic.

## Decision

### 1. One external script, one pluggable backend seam

`scripts/sheet_repaint.py`, argparse, standard library only (the same
constraint `mep_build.py` and `sheet_report.py` live under — `struct` + `zlib`
for PNG, no Pillow, no numpy). Everything that does not depend on the model is
in the script and is testable today:

- read a sheet and its ADR-0153 §4 sidecar; build the control image (the sheet
  nearest-upscaled to the target size) and the per-cell crop list from
  `cells[]` (contact sheets) or `placements[]` (maps);
- palette-variant recolouring from a single generation (§5);
- the seam pass along cell borders (§6);
- alpha preservation (§7);
- write to `auto/repaint/` and stamp the `generated` label (§3, §4).

The model sits behind one interface:

```python
class RepaintBackend:
    name: str
    def repaint(self, request: RepaintRequest) -> Image: ...
```

`RepaintRequest` carries the 1x source image, the nearest-upscaled control
image at the target size, the scale factor, the sheet's `kind`, and the crop
list (each region's rect and its vocabulary index). The backend returns one
RGB or RGBA image at the control image's exact size; anything else is a hard
error. Alpha, recolour, seams and I/O are applied by the script *after* the
backend returns, so a backend that drops alpha or shifts the palette is
corrected rather than trusted.

Backends are registered by name in a dict and selected with `--backend`:
`passthrough` (nearest-neighbour upscale) and its alias `null`, `classical`
(the in-repo Scale2x/Scale3x pixel-art scaler), `esrgan` (a local Real-ESRGAN
install, if the user has one) and `diffusion` (§2). `passthrough` is not a
placeholder — it is the deterministic control arm of PRD validation test 8 and
the thing the tests assert against.

A backend that cannot run MUST say so before anything is written: `esrgan` and
`diffusion` both expose an availability probe that runs before the first
sheet, fails with `RepaintError` naming exactly what is missing and what to
install, and **never downloads anything**. `diffusion` additionally refuses a
non-loopback endpoint outright, so the "nothing leaves the machine" property
of §2 is enforced by the code and not only by the prose.

### 2. The backend: Option A — local diffusion + ControlNet

**Decided (2026-09-05): Option A.** `scripts/sheet_repaint.py` grows a
`diffusion` backend that drives a **locally running** ComfyUI or `diffusers`
process, giving it the §1 control image as the ControlNet hint. Option C (a
non-generative scaler) is built and kept as the baseline the blind A/B is run
against. Option B (a hosted API) stays rejected.

#### What Option A is, and what it costs

- **How it fits.** The control image of §1 is the ControlNet hint (tile or
  canny). This is the only option that is literally "structure-guided upscale
  with a control image", which is what the PRD row asks for — and the only one
  that *repaints* rather than smooths.
- **Where it runs.** Locally, and only locally. No repo content, no
  ROM-derived art and no prompt leaves the machine; the driver refuses any
  endpoint that is not a loopback address, so "local" is enforced rather than
  documented.
- **Weights are the user's problem, deliberately.** A multi-gigabyte one-time
  download performed **by the user**, never by this repo, this script or CI.
  The backend detects that the endpoint or the weights are absent and exits
  with a message naming what to install; it has no fallback that quietly
  downloads anything, and a machine without a suitable GPU simply cannot run
  it.
- **Licensing of the output — unchanged and still unverified.** SD 1.5 is
  published under CreativeML OpenRAIL-M and SDXL 1.0 under CreativeML Open
  RAIL++-M. Both are use-restricted licences whose text (as commonly
  summarised) states that the licensor claims no rights in the outputs,
  leaving the user with whatever rights they have — which, for a repaint of a
  commercial game's art, is dominated by the copyright in the *source*, not by
  the model licence. ControlNet's published weights are OpenRAIL; the
  `diffusers` and ComfyUI code is Apache-2.0. Real-ESRGAN's reference
  implementation and weights are BSD-3-Clause. **Not verified in this task or
  in the one that accepted this ADR:** nobody read the licence texts of SD
  1.5, SDXL 1.0, the ControlNet weights or Real-ESRGAN end to end. Every
  sentence in this paragraph comes from secondary summaries and must be
  re-checked against the actual `LICENSE.md` files by anyone who *distributes*
  a repaint. What makes accepting Option A defensible despite that gap is the
  premise below, not the summaries.

#### Why the licensing gap does not block the decision

Nothing here is published by this project. MesenCE hosts nothing and commits
no assets; `docs/community-packs.json` catalogs *links* to artifacts their
authors host (ADR-0148). A repaint lives in `auto/repaint/` on the artist's
own machine, and whether it is ever published is the artist's decision. The
licence questions above bear on *distribution*; a locally generated, locally
kept artifact has minimal exposure to them. That is what collapses the
argument for shipping Option C as the default: C was the safe answer, never
the good one — it smooths, it does not repaint.

#### Option C stays, as the baseline

Not as a consolation prize: PRD validation test 8 is a **blind A/B**, and an
A/B needs a B. Without a non-generative arm the panel is comparing the
diffusion output against nothing and "it looks better than the raw pixels" is
not a result. So the script ships two non-generative backends:

- `passthrough` (alias `null`) — nearest-neighbour upscale, deterministic,
  the control arm the tests assert against;
- `classical` — an in-repo, pure-Python pixel-art scaler of the hq2x/xBRZ
  family (Scale2x/Scale3x, decomposed for the requested factor). Chosen over
  wiring Real-ESRGAN as the default baseline because it has **zero**
  dependencies, always runs, is byte-reproducible, and cannot introduce a
  colour that was not already in the cell — so it can never fail the alpha or
  palette halves of test 8 for reasons unrelated to the comparison.

`esrgan` exists as a named backend for the artist who *does* have Real-ESRGAN
installed locally, and does nothing else: with no local weights and no local
runner it fails with a message naming what to install and pointing at
`classical`. It never downloads.

#### Option B stays rejected

A hosted API (Stability's "Control: Structure" plus an upscale endpoint, or
any equivalent) uploads every sheet to a third party. "We do not publish" does
not rehabilitate it: that is an export of ROM-derived art whether or not the
result is ever published, and it makes the tool unusable anywhere sending
repo/ROM content out is not allowed. If it is ever wanted, it is an explicit
`--backend stability` that refuses to run without both an API key from the
environment and an explicit `--allow-upload` flag, and it is documented as
exporting ROM-derived art. Its cost was never the deciding factor, but for the
record: secondary sources put the control endpoints at ~5 credits and a
conservative upscale at ~40 credits, with 1 credit ≈ US$0.01 — **not
verified**, the vendor's pricing page returned nothing usable when it was
checked, and the output-rights terms were not read either.

#### The catalog boundary does not move

"Local only" is true today and is one submission away from being false —
ADR-0146 makes every accepted pack auto-install on every client. The
`generated` label (§3) is what keeps that visible to whoever installs it. It
is disclosure, not a gate; §3 says why, and was rewritten after this ADR's
first draft got the reason wrong.

#### First target: the captured screen, not the metatile sheet

Re-scoped by the Punch-Out!! scrutiny (PRD Phase 9): the first target of the
generative backend is **the captured screen**
(`backgrounds/screenNNN.png`, already emitted with three `tileAtPosition`
anchors and condition-prefixed `<background>` lines), not `metatiles.png`. A
16x16 metatile is too small to give a diffusion model context and too visible
to let it improvise; a 256x240 scene is exactly what a control image guides
well, and it is the only surface on which a positional element — the mockup's
logo across the ring canvas — can exist at all. `sheet_repaint.py` therefore
takes `--target sheets|screens|both`; `screens` reads the recorder's
`hires.txt`, repaints every `<background>` target it resolves, and re-emits a
self-contained `hires.txt` carrying the same condition-prefixed lines with
`<scale>` multiplied by the repaint factor. The sheet path (§5's palette
variants, §6's seams) is unchanged and stays the secondary target.

### 3. The label: a `generated` object at the root of `pack.json`

MEP-v1 §3.2 says unknown fields MUST be ignored, so this is additive and every
existing pack stays valid:

```json
{
  "mep": "1.5.0",
  "name": "Zelda — machine repaint",
  "version": "0.1.0",
  "generated": {
    "by": "sheet_repaint",
    "backend": "passthrough",
    "date": "2026-09-05",
    "scale": 4,
    "source": "auto/textures/sheets"
  }
}
```

The rest of the stub is the minimum that lints clean: `sections` describes the
tree the tool actually wrote, and `targets` is **inherited** from the nearest
existing manifest around the source sheets (`<Game>/mep/pack.json`,
`<Game>/pack.json`, …), never invented — `mep_lint` treats a missing
`targets` as an error, so a repaint with nothing to inherit says so and names
the fix (`mep_build pack --rom <ROM>`) instead of writing a manifest that
breaks the next build.

Presence of a `generated` object is the label. `by` and `backend` are
required; the rest is informational. The field name is deliberately not
`ai` — Option C is not AI and is labelled all the same, because what the
catalog cares about is "no human drew this", not which algorithm did not.

**How the catalog pipeline sees it — disclosure, not a gate.** The first draft
of this ADR made a root `generated` object a `mep_lint` **error**, so the
verdict came out `invalid`. That was wrong, and the reason it was wrong is
worth writing down: it assumed this project publishes packs. It does not.
MesenCE hosts nothing and commits no assets — `docs/community-packs.json`
catalogs *links* to artifacts the author hosts (ADR-0148), and a submission is
an act by the author. Whether a generated pack gets published is the artist's
decision, not ours, and rejecting it at the lint takes that decision away from
them.

So `generated` carries no verdict. It is surfaced the way authorship already
is: `scripts/mei_catalog_entry.py` copies it into the row's `deps`-style
metadata and `scripts/generate_community_pack_catalog.py` renders it as a
column, so a reader deciding whether to try a pack can see that no human drew
it. The value is disclosure to the next person — every accepted pack
auto-installs on every client under ADR-0146 — not protection for us. A
generated pack listed silently beside hand-painted ones misleads the person
installing it; that is the only harm this label exists to prevent.

**The trap, stated plainly.** A submitter can delete the field. This label is
an honesty mechanism, not a detector: it stops an accident (someone promoting
their `auto/repaint/` folder and submitting it without thinking) and it does
not stop a deliberate misrepresentation. Building an actual detector for
machine-repainted pixel art is out of scope and this ADR does not claim one.

Accepting this ADR bumped MEP-v1 to **v1.6** (new optional root field
`generated`, §3.1) and added the catalog column. No `mep_lint` rule is added —
a generated pack lints exactly like any other, because under MEP-v1 §3.2 an
unknown field is ignored — and no verdict, label or de-listing follows from
the field. It is a column, like `author`.

### 4. The output goes to `auto/repaint/`, never on top of the recorder's sheets

```
<Game>/
  auto/
    textures/sheets/       # ADR-0153 recorder output — untouched, and wiped
                           # by the next bootstrap_auto_packs.sh run
    repaint/
      pack.json            # carries the §3 `generated` object
      textures/sheets/
        metatiles.png      # repainted, at N x
        metatiles.orig.png # copy of the recorder's 1x twin
        metatiles.json     # sidecar, copied verbatim
  mep/                     # the artist's pack — this tool never writes here
```

`auto/` because ADR-0049 makes provenance a matter of location ("a file under
`auto/` is machine-made; a file outside it is human-made"), and ADR-0147 keeps
`auto/` and `mep/` as siblings. A **sub**folder of `auto/`, not `auto/textures`
itself, for two reasons: the bootstrap deletes `auto/textures` wholesale, and
overwriting the recorder's sheets would destroy the reference the artist and
PRD test 8 compare against.

The `*.orig.png` twin is copied next to the repaint on purpose. `mep_build.py`
decides whether a cell *claims* a tile key by diffing it against that 1x twin
(ADR-0153 §4): a repainted cell differs, so it counts as painted and claims
its keys. Without the twin the sheet would fall back to static rank, which is
the wrong rule for this content.

The repaint folder has no `hires.txt` of its own, so building it needs the
recorder's keys:

```
python3 scripts/mep_build.py build <Game>/auto/repaint \
    --source <Game>/auto/textures/hires.txt
```

This is a documented two-step, not a hidden one. The tool never writes into
`mep/`; promoting a repaint into an artist pack is a human copy, and the human
carries the `generated` label with it or drops it knowingly.

### 5. Palette variants are recoloured from one generation

The same 8×8 shape appears in several cells under different NES palettes; the
sidecar records both (`tiles[].tile`, `tiles[].palette`). Generating each
variant independently gives each one a different silhouette, which breaks
every seam it participates in.

So: cells are grouped by their **tile-shape tuple** (the `tiles[].tile` values,
palette ignored). The member with the highest `count` is the canonical variant
and is the only one generated. Every other member is produced by recolouring
the canonical *generated* pixels:

1. From the 1x originals, read the canonical cell's palette colours and the
   variant cell's palette colours, in NES colour-index order (0..3).
2. For each generated pixel, find the nearest canonical palette colour in RGB
   and keep the residual `pixel - palette[i]`.
3. Emit `variant_palette[i] + residual`, clamped to 0..255.

Shading and dithering survive as residuals; the silhouette is identical
because it comes from one generation and one alpha mask. Transparent pixels
are skipped.

The trap this hides: a variant's **own** captured pixels are discarded — its
output is the canonical cell's geometry under the variant's colours. On real
data that is a no-op, because the group is keyed on the tile-shape tuple and
two cells with the same shapes *are* the same drawing. It stops being a no-op
the moment the vocabulary keys two visually different cells to one shape
tuple, and then the smaller-`count` variant silently inherits the bigger one's
art. `--no-variants` is the escape hatch, and the ADR-0153 sidecar's `count`
is what makes the choice of victim predictable rather than arbitrary. When a group's members do not agree on how many distinct colours
they use, the recolour degrades to identity for the missing indexes and says
so on stderr rather than inventing a mapping. `--no-variants` generates every
cell independently, for comparing the two.

### 6. The seam pass symmetrises the border band of adjacent cells

A per-cell or per-sheet generation is discontinuous where two cells meet in
game: PRD validation test 4 (paint a continuous diagonal stripe across a map,
play it back, no doubled or missing column) is the acceptance test and a naive
repaint fails it.

Adjacency is not guessed. It is read from the data ADR-0153 already emits: a
map's `placements[]` gives map-pixel origins and vocabulary indexes, so two
placements sharing a border give an ordered pair `(vocab_a, side, vocab_b)`.
Objects contribute the same pairs through `cells[].metatile`. The resulting
pair table is applied both on the map itself (geometric neighbours) and back
on the contact sheets (where the cells are not physically adjacent, separated
by ADR-0153's 1-cell gutter, but must still tile in game).

For each pair and each offset `j` in `0..W-1` from the border (`--seam-width`,
default 1, measured in **1x** pixels and multiplied by the scale):

```
f          = 0.5 * (W - j) / W
a[edge-j]  = (1-f) * a[edge-j] + f * b[j]
b[j]       = (1-f) * b[j]     + f * a[edge-j]      (pre-blend values)
```

At `j = 0` this is the plain average of the two touching columns, so the two
sides agree exactly at the border and a stripe crosses it. Both writes use the
pre-blend values, so the operation is symmetric and order-independent.

Constraints: the pass **only** writes inside a cell's `W`-pixel border band —
never the interior, never the gutter (which is transparent and which
`mep_build` does not slice) — and it skips a pixel pair where either side is
fully transparent, so it can never grow or erode a silhouette. A cell with
several different neighbours on the same side gets the mean of all of them,
which is a real loss of contrast on a tile that borders many different things;
that is the documented cost of not having a per-adjacency copy of the cell,
and the alternative (duplicating a metatile per neighbour) would break the
vocabulary the whole of ADR-0153 is built on.

### 7. Alpha comes from the source, always

Backends are assumed to lose alpha (most image models return RGB). The script
therefore takes the alpha channel from the nearest-upscaled source, applies it
to whatever the backend returned, and zeroes the RGB of fully transparent
pixels so no halo can leak into a crop. Nearest-neighbour, never resampled:
a soft alpha edge on an 8×8 NES tile is wrong by construction, and PRD test 8
fails the whole slice on "any visible alpha loss on sprites".

A backend that *does* return RGBA does not get to override this. Its alpha is
discarded, and the script says so once per sheet at `--verbose`. This is a
deliberate loss of expressiveness in exchange for a guarantee.

## Consequences

- Phase 9 gains an optional slice that costs the emulator nothing: no Core
  file, no setting, no runtime dependency, no weight in the installer. The
  Python scaffold plus its tests is the entire footprint until a backend is
  chosen.
- `passthrough` makes the whole pipeline runnable and testable today, which
  means the palette, seam and alpha logic gets reviewed and regression-tested
  independently of the model question. The cost is that a green test suite
  says nothing about whether the *generated* art is any good; only PRD
  validation test 8 does, and it is human.
- Accepting this ADR was a request for three pieces of work, in order: the MEP
  v1.6 `generated` field plus its catalog column (§3), the chosen backends
  (§2) and the `--target screens` path, and the blind A/B run (PRD test 8).
  The first two shipped with the acceptance; the third is human and has not
  been run. **The `diffusion` backend has never been executed** — it is
  written, its unavailable path is tested, and its generation path has no
  coverage at all because running it needs weights and a GPU this project
  does not provide. Nobody should read a green test suite as evidence that it
  produces an image.
- The two-step build (`mep_build build <Game>/auto/repaint --source
  <Game>/auto/textures/hires.txt`) is a papercut. It exists because `auto/`
  carries no `hires.txt` of its own outside `auto/textures`, and hiding it
  would mean teaching `mep_build` about a repaint layout, which is worse.
- A `generated` pack that reaches the catalog anyway (label stripped) is not
  detected. This is a known, accepted hole; the mitigation is social, not
  technical, and ADR-0148's de-listing rules remain the remedy.
- A generative backend is not reproducible. `content_id` (ADR-0139/0141) over
  a repainted folder changes on every run, so a repaint must never be the
  input to an automated update loop. It is an artist's starting point that a
  human then edits, which is exactly how `auto/` is already treated.
- Option A's RAIL use restrictions travel with any redistribution of the
  output. This ADR's position is that the question does not arise, because the
  output lives in `auto/` and is never distributed by this project — but
  anyone who *does* publish a repaint inherits both the RAIL terms and, far
  more importantly, the copyright in the original art. The `generated` label
  is the only thing this project puts between the two.
