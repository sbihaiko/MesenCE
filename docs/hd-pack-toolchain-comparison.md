# HD Pack toolchains: MesenCE (upstream) and MesenAI (this fork), side by side

Written 2026-09-16, from measurement rather than memory: the upstream tree was
read, the format's loader and builder were read here, and the MesenAI numbers
were taken from packs recorded on this machine.

## Naming, and why the comparison is lopsided

| Name | What it is | Where it is |
| --- | --- | --- |
| **Mesen** (0.9.x) | The original, .NET/WinForms | `SourMesen/Mesen` — **archived** 2024-12 |
| **Mesen2** | The C++ rewrite | `SourMesen/Mesen2` — **archived**; its README points at `nesdev-org/MesenCE` |
| **MesenCE** | The community continuation; `mesen.ca` distributes it (2.2.1) | `nesdev-org/MesenCE` — **upstream of this repo** |
| **MesenAI** | This fork | `sbihaiko/MesenAI` (renamed from `sbihaiko/MesenCE` on 2026-09-16) |

`git remote -v` in this tree is the ground truth: `origin` is the fork,
`upstream` is `nesdev-org/MesenCE` with push disabled.

**The repository was renamed on 2026-09-16**; the old `sbihaiko/MesenCE` URLs
redirect. Project files, release tags (`mesence-v0.1.0`), the catalog's
`"MesenCE validation"` strings and older `docs/` prose still read `MesenCE`
and are updated as they are touched. In this document "MesenCE" always means
the upstream, and "MesenAI" this fork.

The consequence for everything below: **MesenAI did not reimplement the HD
Pack subsystem.** `Core/NES/HdPacks/` is inherited from upstream MesenCE, and
the HD Pack Builder window still ships here
(`UI/Windows/HdPackBuilderWindow.axaml`). So the honest comparison is the
**inherited base versus the layer built on top of it** — every row in the left
column is also in the right column unless the row says otherwise. A row is
marked *inherited* when MesenAI did nothing to it.

Two facts about the base that colour the rest:

- Upstream is in **maintenance**: the last functional change to
  `HdPackBuilder.cpp` was 2024-07-15, the format has been frozen at version 109
  since 2023-12-29, and the most recent commit touching it is `clang-format`.
- Upstream **documentation stopped in 2020** (`mesen.ca/docs/hdpacks.html` is
  stamped version 0.9.9, format v105). `<addition>`, `<fallback>`,
  `sppalette*` and `positionCheck*` exist in the loader and are documented
  nowhere. There is no `docs/` directory in the upstream repository at all.

## Capability table

| | MesenCE (upstream) | MesenAI (this fork) | Better |
| --- | --- | --- | --- |
| **Recording** | HD Pack Builder window: press Start, play the game to the end, press Stop | Same window, plus `headless_record`: no window, deterministic, ~3× real time | **MesenAI** |
| **Route as data** | — | `input=` frame-counted scripts, `state=` save states, `movie=` TAS, `cheat=` RAM pokes, `cdl=` code/data log | **MesenAI** |
| **Coverage measurement** | — | `artist_cover.py` (per image, per state, and which tiles only that state shows), `gameplay_probe.py` (gameplay vs menus), live % in the builder window | **MesenAI** |
| **"What did I miss" steering** | Play more and look | Contra measured 53.8 % → 58.9 % → 64.6 % across recordings | **MesenAI** |
| **Tile identity** | `(tileData, palette)`; CHR ROM by bank index, CHR RAM by the 16 bytes | *Inherited*, plus explicit per-console decisions for GB/GBC/SMS/GG (ADR-0036, ADR-0037) | Upstream defines it; the fork extends it |
| **Picking a tile's key by hand** | Right-click → *Copy tile (HD pack format)* in Tile/Tilemap/Sprite viewers; Shift+right-click copies a whole nametable | *Inherited* — nothing added | **MesenCE** (the only tool of its kind) |
| **Vocabulary (which tiles are one thing)** | Recorded in `.NES` file order, deliberately. Sour: *"I tried to make the recorder smarter… it didn't work very well and was generally worse"* | Metatile vocabulary by mutual predictability, sprite figures (`sprNNN`), poses from the OAM stream, cycles/sequences/variants, fusion labels | **MesenAI** |
| **Ambiguity of a reused tile** | 13 condition types, all hand-written by the author | `spriteNearby` (spanning tree, ADR-0189) and `tileNearby` (directed co-occurrence, ADR-0190) emitted automatically, each with a mandatory bare twin | **MesenAI** |
| **Conditions deliberately refused** | All 13 available to a human author | `frameRange`, `tileAtPosition`, `memoryCheckConstant` are not emitted (ADR-0189 §4) | **MesenCE** (a hand author can do what our tool will not) |
| **Sprite composition** | Nothing in the emulator; the community's answer is an external editor (`mkwong98/HDNes-Graphics-Pack-Editor`, CHR ROM only, wxWidgets) | `compose_editor.py`: MVVM tkinter over a host-free engine, poses as the unit, export as legal build input | **MesenAI** |
| **Extra tiles drawn on match** | `<addition>` — composes sprites without spending the 8-per-scanline limit; 1987 uses in one community pack | Emitted from the composition editor's overflow layer (F12.5, ADR-0196): anchored on the pose's root cell, target key proved unmatched against the ROM's CHR, linted | **Even** — upstream's format, authored by tool here |
| **Writing `hires.txt`** | By hand, or by the author's own generator (the most prolific author ships a 9.9 MB, 34-sheet Excel workbook) | `mep_build.py build` regenerates it from sheets; the guide forbids hand-editing | **MesenAI** |
| **File-level duplicate bitmaps (CHR ROM)** | `automaticFallbackTiles` exists in the format and the builder never set it | Set on every CHR ROM recording (ADR-0195) | **MesenAI** |
| **Validation** | None. No linter, no spec that matches the code | `mep_lint.py`, versioned MEP-v1, canonical `content_id`, sha256 errata, pack CI | **MesenAI** |
| **Interop with community packs** | The packs are written for the format upstream defines | Textures and BPS match optimistically; **IPS does not relax**, and a pack that patches CHR RAM → CHR ROM keys in a disjoint namespace (ADR-0145) | **MesenCE** (it defined the namespace; the fork inherited the incompatibility) |
| **Painting, end to end** | Edit the recorded PNGs in place and reload | Kit → paint PNG → `build` → `lint`; the acceptance test can pass while the figure is half-unpainted (#255, #256) | **MesenCE** |
| **Staying inside the emulator** | One window. Start, play, stop, edit, see it | A repo checkout, a headless binary with six flags, four generators, a copy step, and a "see it on screen" step that is not in the guide's table | **MesenCE** |
| **Vocabulary scale** | An author's shipped Metroid pack, re-measured 2026-09-17: 67 images, 150 199 tile rules, **8 401 keys** (distinct `tileData`+`palette`), 260 146 lines | A 60-second recording: 2211 keys. The tools run at his scale — `mep_build` 2.70 s and `mep_lint` 0.59 s on a 300 000-line project — but the recording vocabulary is still ours to close ([log](validation/f12.1-scale-and-load-2026-09-17.md)) | **MesenCE** |

## Where the numbers came from

| Claim | Measurement |
| --- | --- |
| Palette variants barely inflate the mapping | Contra 1776 `<tile>` lines / 1694 bitmaps = 1.05. Mega Man 3: 8581 / 8192 = 1.05 |
| The vocabulary is shared, not repeated | Contra stage 3 boss: 517 poses, 9868 tile placements, **195 distinct nodes** — 50.6× reuse |
| CHR ROM duplicates bitmaps | Mega Man 3 (USA): 8192 indices, **6663 distinct bitmaps**, 1529 redundant (18.7 %) |
| The fallback option is worth setting | Same pack, 1529 redundant lines deleted: 625 920 vs 599 040 matched bg tiles over ~60 frames, the only difference being the `<options>` line |
| The artist's real competitor is a spreadsheet | The Metroid pack ships `SourceWorkForComplexHires_TXTCoding.xlsx`: 9.9 MB, 34 sheets, 113 855 declared rows, of which 97 399 carry a `hires.txt` directive |
| His bottleneck is not drawing | Every structure in that workbook is a device for emitting rule text at volume: comma columns, concatenation columns, coordinate steppers, frame counters spliced into condition names |

Full method and raw evidence: `docs/validation/metroid-artist-workflow-evidence.md`,
`docs/validation/c5-fable-artist-run-zelda-2026-09-14.md`,
`docs/validation/c5-fable-artist-run-mega-man-3-2026-09-14.md`,
`docs/validation/tilenearby-evidence-study.md`.

## Gaps this table names

The seven rows marked **MesenCE** are not a scoreboard to zero — the Core,
the format and the builder are upstream's, and the competitor the artist
evidence actually measured is a spreadsheet, not an emulator. They are the
places where a hand author is still better served than by the layer built
here, and each has a bounded slice in the PRD (Part A §4, **Phase 12 — Paint
loop and hand-authored conditions**, opened 2026-09-16). The mapping:

| Row | Slice | Decision it waits on |
| --- | --- | --- |
| Vocabulary scale | F12.1 — delivered 2026-09-17: the pack is measured and every count now carries its definition ([log](validation/f12.1-scale-and-load-2026-09-17.md)); what remains open on this row is the recording's vocabulary, not the tools' speed | — |
| Picking a tile's key by hand | F12.2 (*Copy as MEP sheet cell*) | — |
| Painting, end to end · Staying inside the emulator | F12.3 (reload without reopening the ROM), F12.4 (asset-name template) | — |
| Extra tiles drawn on match | F12.5 — delivered 2026-09-19: the overflow layer emits `<addition>`, proved pixel-exact on one pose each of Mega Man 3 (CHR ROM) and Contra (CHR RAM) ([log](validation/f12.5-addition-overflow-layer-2026-09-19.md)) | ADR-0196 (accepted 2026-09-16) |
| Conditions deliberately refused | F12.6a / F12.6b | ADR-0197 (accepted 2026-09-16; amends ADR-0189 §4's scope, keeps its refusals) |
| Interop with community packs | F12.7 (plain packs first; a patched-ROM pack imports against the patched ROM, ADR-0198 §3) | ADR-0198 (accepted 2026-09-16) |
| Tile identity | none — it is the inherited contract | — |

When a slice closes, the row above is re-measured and the cell cites the log
under `docs/validation/`; until then the **Better** column stands as written.
Two things the phase deliberately does not do: emit any key a recording did
not observe (ADR-0183 §3, with ADR-0196 §3's one confined exception), or
claim that recording coverage is solved — that criterion stays with
ADR-0182/0184/0185 and F9.25.

## "Mapping without playing", precisely

Worth stating carefully, because the short version oversells it. MesenAI does
not map without the game running. What it removed is **the human at the
controls and the emulator's window** — and, in three cases, the run itself.

**Driven, not hand-played.** `headless_record` runs the console with no window
and takes its input from data:

- `input=<script>` — a text route of frame-counted button states
  (`<n>f <buttons>`). Hand-written, or generated by `write_play_scripts.py`.
- `state=<file.mss>` — start from a save state, so a recording does not spend
  its budget on the title screen. The guide's `mint` step exists for this: one
  short run produces the state, every later run starts inside the level.
- `movie=<file.bk2>` — a published TAS drives the pad (ADR-0185);
  `fm2_to_bk2.py` converts FCEUX `.fm2`, which the Core cannot read directly.
- `cheat=AAAA:VV` — RAM writes only (ADR-0184), to reach a state no route
  reaches. A cheated run feeds the background surfaces and never the sprites.
- `cdl=<file.cdl>` — a Code/Data Logger map of what the run executed, which
  finds art the PPU fetched but never drew.

The result is deterministic in **emulated frames**, so the same route over the
same state produces the same pack, and coverage becomes something you measure
and steer on rather than something you eyeball. All of it is built on the
inherited builder — upstream records the same data; what is new is that a
program can drive it.

**Genuinely play-free.** Three paths reach art with no gameplay at all:

- The **static ROM export** (`romtiles`, ADR-0043): every CHR ROM tile becomes
  a palette-agnostic `defaultTile` entry without running anything. On GB/SMS
  and on CHR RAM it is a heuristic scan of the file and finds uncompressed
  tiles only — 12 of 26 on-screen tiles in the F1 test ROM are built at run
  time and stay invisible to it. The UI says so.
- The **CHR kit's ROM fill**: pattern pages are completed from the cartridge
  and marked `seen: false`. Metroid measured 82 % complete this way.
- **Donation across recordings** of the same ROM: one recording's CHR page
  donates cells to another's, refused unless the `supportedRom` SHA1 matches.

Everything else is a recording. The honest one-line version: **MesenAI replaced
"play the game from start to finish" with "write down a route, measure what it
covered, and write a better one" — the play still happened, but it stopped
being the thing that decides whether the map is complete.**

## What not to claim

- **Not "a different emulator".** MesenAI is a fork of MesenCE. The Core, the
  format and the builder are upstream's work, and a MesenCE HD pack loads here
  unchanged. Where this table says a row is inherited, the credit is upstream's.
- **Not "automatic mapping".** Every inference is marked, and anything that
  would change what a rebuilt pack *renders* is only emitted when the key it
  carries was actually observed (ADR-0183 §3). Names come from data or a human,
  never from a generator.
- **Not "beats upstream at its own job".** For one-off surgical work inside a
  running game — pick a tile, get its key, paint that one thing — the inherited
  gesture is faster than anything added here.
- **Not "the community author should switch".** He patches the ROM to convert
  CHR RAM into CHR ROM because that buys him a short stable tile id per graphic,
  which is what his spreadsheet manipulates. These tools assume the stock ROM.
  That bet is the opposite of his, and it is unresolved (issue #225).
