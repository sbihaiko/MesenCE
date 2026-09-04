# F6.5 — guided manual acceptance of the community-pack install flow

Status: checklist only. **No run recorded here.** Every box below has to be
ticked by a human in front of a real display; this file is the script for
that run, not a report of one.

## What this accepts

F6.5 accepts the **installer**, i.e. the ADR-0138 split-distribution flow as
implemented by `UI/Services/CommunityPackInstallCoordinator.cs` and
`UI/Services/CommunityPackInstallService.cs`. Neither is dual-compiled into
`UI.Tests` (ADR-0123: only `UI/Logic/**` is), so no unit test covers the
orchestration — only the pure decisions it delegates to
(`CommunityPackDepResolver`, `CommunityCatalogUpdateDecision`,
`CommunityPackContainerName`, `LegacyHdPackInstall`).

Five observable outcomes are in scope:

1. the pending-dependency prompt for a `user_supplied` asset;
2. hash validation of the file the user drops into `.cache/downloads/`;
3. patch application (`<patch>` / `patches[]`);
4. the `.mep-install.json` stamp;
5. the installed `mep/` folder.

`scripts/smoke_pack_headless.sh` (F6.6) is the objective post-condition at
the end — it boots the real core on the installed folder. It is not a
substitute for the run: it never executes the installer.

## Pack under test

**Mega Man (USA)** — submission issue #138, `pack_id`
`axlrocks/megaman-super:mega-man-usa`, row in `docs/community-packs.json`,
artifact `https://github.com/AxlRocks/Megaman-Super/archive/refs/heads/main.zip`,
declared `sha256`
`666bdeae79a721cc6c9ff38e4613c144e0b971f271dd13a7b39780eb6fe557bc`,
`content_id` `ab971a624bd3…`.

Why this one (verified 2026-09-03 against the catalog row's own artifact —
the cached copy under `.cache/validate-local/138/pack_download.bin` hashes to
exactly the declared `sha256`):

```
$ python3 scripts/mep_lint.py <artifact>
info    pack  bundled patch: Megaman - Super.ips (present, wired — applied on load)
info    pack  bundled patch: Customization/Patch - Music NES, No Pause (Default)/Megaman - Super.ips (present, wired — applied on load)
… (5 bundled .ips, all reported wired)
```

- Its root `hires.txt` carries `<patch>Megaman - Super.ips,2F88381557339A14C20428455F6991C1EB902C99`,
  so the patch is **wired** in the ADR-0148 sense (ADR-0148 amends ADR-0144:
  merely bundling a `.ips`/`.bps` is not enough). The patch + extraction path
  is therefore the one exercised.
- It declares 17 `<bgm>` tracks and bundles **zero** `.ogg` files — the
  author distributes the audio separately. That is precisely the
  split-distribution shape F6.5 is about.

Runners-up, if the tester cannot supply a Mega Man (USA) dump:

| Pack | Wired? | Why it is second choice |
|---|---|---|
| #139 The Legend of Zelda (USA) | `ZeldaHD.ips` wired | Textures only — exercises patch + extraction but no audio dependency. Its No-Intro sha1 `BE2F5DC8…` is the one the repo's own `roms/Zelda.nes` has, so it is the easiest to run |
| #141 Zelda II (USA) | `Revamp.ips` wired, `Revamp+Music.ips` **not** wired | Mixed; the audio-bearing patch is the unwired one |
| #143 Castlevania, #148 Metroid | not verified here | `patch:ips` labelled but their artifacts were not re-linted for this checklist |

The other six catalog rows carry no patch at all.

## Known gap — the prompt cannot fire from the published catalog

Verified 2026-09-03 against `docs/community-packs.json`: **all 11 rows are
`kind: "hd-legacy"` and none carries `deps` or `recipe`.** The pending-dependency
prompt is raised by `CommunityPackInstallCoordinator.ResolveDeps`, which
returns immediately when `entry.Deps` is empty, so no live catalog row can
raise it today. Mega Man's 17 missing OGGs are missing *inside the pack
manifest*, not declared as recipe deps — the loader simply logs
`OGG file not found` for each.

Consequence for this checklist: **Part A** runs against the real catalog and
covers outcomes 3–5; **Part B** covers outcomes 1–2 with a seeded catalog,
using only supported code paths (no build flags, no code edits). Closing the
gap for real means publishing a MEP-recipe row with a `user_supplied` dep —
out of scope here, and the reason Part B exists.

## Prerequisites

- A Release `Mesen.app` built from the working tree:
  `scripts/build_app_macos.sh` → `bin/osx-arm64/Release/osx-arm64/publish/Mesen.app`.
- A user-supplied No-Intro **Mega Man (USA)** dump (never redistributed with
  this repo). Catalog `rom.sha1` = `6047E52929DFE8ED4708D325766CCB8D3D583C7D`.
- A **zip** of your own to play the "user-supplied audio" role in Part B,
  holding one small `.ogg` at the path the recipe's ops read. The dep artifact
  is always opened as an archive (`MepRecipeSource::LoadBytes`); handing over a
  bare `.ogg` fails the install with `not a valid zip archive`. Its content is
  irrelevant, its sha256 is not.
- Paths used below (macOS):
  - Mesen home: `~/Library/Application Support/MesenCE`
  - log: `<home>/mesen.log` (previous session rotated to `mesen.log.1`)
  - downloads cache: `<home>/EnhancementPacks/.cache/downloads/`
  - catalog cache: `<home>/EnhancementPacks/.cache/community-packs.json`
    (+ `community-packs.etag`)
- Tools > Enhancement Packs: `Enable MEP packs`, `Audio (OGG)`, `ROM patch`
  and `Auto-install community packs` all ticked (the last defaults to `true`,
  ADR-0146).

## Part A — install from the live catalog

Start from a clean slate for this ROM: delete `<rom folder>/<Rom Name>/mep/`,
the row's file in `.cache/downloads/`, and
`.cache/install-registry/` entries for the ROM sha1, if present.

- [ ] **A1.** Launch `Mesen.app`, load the Mega Man (USA) ROM.
- [ ] **A2.** Open `<home>/mesen.log` (or Debug > Log Window) and confirm the
      fetch chain, in order:
      - `[CommunityPackFetch] catalog HTTP status=200 …`
      - `[CommunityPackFetch] matching entry for romSha1=… via=sha1: axlrocks/megaman-super:mega-man-usa url=… sha256=666bdeae…`
      - `[CommunityPackDownload] downloading url=…` then
        `[CommunityPackDownload] downloaded+verified, wrote …/.cache/downloads/666bdeae…`
        — or, since this URL is a mutable branch archive, the ADR-0146 line
        `sha256 mismatch on mutable repo archive … installing optimistically`.
        Both are a pass; a bare `sha256 MISMATCH` line for an *immutable* URL
        is a fail.
- [ ] **A3.** Confirm the install decision:
      `[CommunityPackInstall] update verdict=NotInstalled installStampExists=False entryContentId=ab971a62… entrySha256=666bdeae…`
      then `[CommunityPackInstall] hd-legacy entry - installing as a loose HD pack`
      and `[CommunityPackInstall] hd-legacy installed (MEP-ized): <…>/mep`.
- [ ] **A4. (outcome 5 — the `mep/` folder)** On disk, beside the ROM:
      `<rom folder>/<Rom Name>/mep/` exists and contains `textures/hires.txt`
      plus the pack's PNGs and `Megaman - Super.ips`, and a generated
      `pack.json` whose `sections` is `{ "textures": { "path": "textures/" } }`
      (ADR-0147 MEP-ization).
- [ ] **A5. (outcome 4 — the stamp)** `<…>/mep/.mep-install.json` exists and
      reads, modulo whitespace:
      ```json
      { "pack_id": "axlrocks/megaman-super:mega-man-usa",
        "content_id": "ab971a624bd30c5599a7d90c201bd4f08ff5d0d54b2d4fbb0fbb8b4cb9062354",
        "source": { "sha256": "666bdeae…" },
        "installed_at": "…Z" }
      ```
- [ ] **A6.** The client power-cycles by itself
      (`[CommunityPack] power-cycling to apply newly installed pack`). If
      instead you see `Community pack installed - reload the game to apply`,
      reload manually.
- [ ] **A7. (outcome 3 — patch application)** After the power cycle the log
      shows
      `[HDPack] <patch> applied: '…Megaman - Super.ips' (ROM sha1 …; the running ROM's hash is now the patched one)`.
      If it instead shows
      `[HDPack] <patch> skipped: no entry for this ROM's sha1 … (enable 'apply patches on hash mismatch' to force it)`,
      your dump is a different revision from the one the `<patch>` line names
      (`2F883815…`): tick **Apply patches on hash mismatch** in Tools >
      Enhancement Packs, power-cycle, and accept the ADR-0145 override line
      `[HDPack] <patch> hash mismatch - applied '…' anyway (ApplyPatchOnHashMismatch)`
      instead. Record which of the two you got.
      Two skip lines are *not* acceptable here and mean a mis-set toggle:
      `'ROM patch' layer disabled` and
      `the pack's <bgm> patch would mute the game while 'Audio (OGG)' is off`.
- [ ] **A8.** The game renders the HD textures. 17
      `[HDPack - Line N] OGG file not found: BGM/MUS_*.ogg` lines are
      **expected** at this point — the author's OGGs are not in the artifact.

## Part B — the user-supplied dependency (seeded catalog)

Part B exercises outcomes 1–2, which Part A cannot reach (see the gap above).
It uses the fetcher's own ETag cache: `CommunityCatalogCacheDecision.Resolve`
returns `Reused` — i.e. the **on-disk** catalog body is authoritative —
whenever the conditional GET answers `304`, or whenever the GET fails at all.
Nothing here patches the client.

- [ ] **B1.** Build a one-row catalog JSON of your own: copy the Mega Man row,
      set `"kind": "mep-recipe"`, add a `recipe` document (see
      `docs/specs/MEP-recipe-v1.md`; `scripts/gen_mep_recipe_fixture.py`
      emits a valid one) whose `sources.deps[]` has a single entry with
      `"user_supplied": true`, a `hints` string, a `license`, and
      `"sha256": "<sha256 of your dep zip>"`.
- [ ] **B2.** Write it to `<home>/EnhancementPacks/.cache/community-packs.json`
      and write the **live** catalog's current ETag to
      `<home>/EnhancementPacks/.cache/community-packs.etag`:
      ```bash
      curl -sI https://raw.githubusercontent.com/sbihaiko/MesenCE/main/docs/community-packs.json \
        | awk 'tolower($1)=="etag:"{print $2}' | tr -d '\r"'
      ```
      The next launch sends `If-None-Match`, gets `304`, and your body wins.
      (Equivalent alternative: stay offline — any failed GET also resolves to
      `Reused`.)
- [ ] **B3.** Make sure the primary artifact is already in
      `<home>/EnhancementPacks/.cache/downloads/` under its `sha256` as file
      name — `DownloadAndVerifyAsync` reuses a cache file whose hash matches
      and skips the network entirely.
- [ ] **B4.** Launch, load the ROM. Confirm
      `[CommunityPackFetch] catalog HTTP status=304 cacheUsable=True resolvedBodyLen=…`
      — this proves your seeded body is the one in play.
- [ ] **B5. (outcome 1 — the prompt)** A pending dep does **not** abort the
      install: the recipe installer completes, withholding only the ops that
      read the dep (`InstallMepRecipe returned success=True resultText=1\n\naudio/`,
      `Status=Installed`), and the dep-backed folder is absent on disk.
      With your dep **absent** from
      `.cache/downloads/`, an on-screen message appears, worded exactly:
      `Missing file '<hints>' (licence: <license>) - drop it into <home>/EnhancementPacks/.cache/downloads and power cycle`
      (an undeclared licence must render as the literal `not declared`, never
      blank). The log shows `pendingDeps=1` on the
      `[CommunityPackInstall] calling EmuApi.InstallMepRecipe` line.
- [ ] **B6. (outcome 2 — hash validation)** Copy your `.ogg` into
      `.cache/downloads/` **under a deliberately wrong name** (the resolver
      matches by content sha256, never by file name) and **restart the app**,
      then load the ROM again. The prompt must be gone and `pendingDeps=0`,
      with the dep-backed folder now present on disk.
      Do not follow the prompt's own "power cycle" wording, and do not just
      reload the ROM: both are no-ops here (issue #156) — `OnGameLoaded`
      returns early on `isPowerCycle`, and `_attemptedRomSha1` latches the ROM
      for the rest of the process after a partial install.
- [ ] **B7.** Negative control: replace the file with a different but equally
      well-formed zip (different bytes, plausible name and inner layout), bump
      the seeded row's `content_id` so the verdict is `Updated` rather than
      `UpToDate`, and restart. The prompt must come back, `pendingDeps=1`, and
      the dep-backed folder must be gone again — the pack is rebuilt from the
      recipe, not patched in place. A name-only or shape-only match would be a
      bug worth filing on the bug board.
- [ ] **B8.** Remove the seeded `community-packs.json` / `.etag` afterwards so
      the client returns to the published catalog.

## Post-condition gate — `scripts/smoke_pack_headless.sh`

This is the objective part of the run: it boots the real core (no GUI) over
the folder the installer just produced and fails on any missing
`<img>`/`<tile>`/`<background>`/`<bgm>`/`<sfx>` target. Run it on the **pack
root** — `mep/`, the folder that holds `pack.json` and `textures/hires.txt`.
Pointing it at the sibling folder instead exits with
`FAIL: no hires.txt manifest`.

```bash
scripts/smoke_pack_headless.sh "<rom folder>/<Rom Name>" "<rom folder>/<Rom Name>.nes"
```

- Part A result (Mega Man, no OGGs supplied): the 17 `<bgm>` targets are
  missing, so the run **must** be gated with `--allow-missing-audio`,
  which reports them as `SKIP` and still validates the textures:

  ```bash
  scripts/smoke_pack_headless.sh "<rom folder>/Mega Man (USA)" "<rom folder>/Mega Man (USA).nes" --allow-missing-audio
  ```

  Expected tail: `PASS (17 user-supplied OGG(s) skipped — not supplied locally)`.

- The real acceptance line is the positive audio signal, which requires the
  OGGs to be present under the paths `hires.txt` names. With them in place,
  drop `--allow-missing-audio` and require, in the `--- loader diagnostics ---`
  block, a line of the form:

  ```
  [MEP] audio: 17 BGM / 0 SFX tracks after '<installed folder>'
  ```

  (format from `Core/NES/NesConsole.cpp`:
  `[MEP] <label>: <n> BGM / <m> SFX tracks after '<folder>'`), and the script
  to end in `PASS: boots with no missing img/tile/background/bgm/sfx targets`.
  A zero-BGM count, or any `OGG file not found` line without
  `--allow-missing-audio`, is a FAIL.

Note the smoke deliberately excludes `<patch>` from its gate scope: a
`patch skipped` line there is informational. Patch application is checked in
**A7**, in the GUI run, not here.

## Sign-off

Run of 2026-09-04, build `ea2bd0f21982aa35cc10595aefff5226ed2519bb`
(`make clean && scripts/build_app_macos.sh`, core-unit-tests 287/287).
Pack under test: catalog row `issue-139` (Zelda HD), not the Mega Man row the
steps above use as their example. ROM: a user-supplied No-Intro dump,
No-Intro sha1 `B6643CE5CD43F14915466407FFA1F89C1CDFE76F`.

| Item | Result | Log line / path observed |
|---|---|---|
| A2 fetch + download+verify | PASS | `catalog HTTP status=200 cacheUsable=False resolvedBodyLen=9648`; `matching entry … via=game: issue-139`; Drive 303→confirm→200, `final response status=200 bodyBytes=187345689`; `downloaded+verified` |
| A3 `update verdict=NotInstalled` | PASS | `verdict=NotInstalled installStampExists=False entryContentId=57af4f12… entrySha256=03b5eeab…`; `gates passed`; `hd-legacy installed (MEP-ized)` |
| A4 `mep/` folder | PASS | 423 files under `<rom folder>/<Rom Name>/mep/textures`, including `ZeldaHD.ips` |
| A5 `.mep-install.json` | PASS | stamp carries the three identity fields; `installed_at 2026-09-04T22:56:50Z` |
| A7 `<patch>` applied (or hash-mismatch override) | PASS (both halves) | gated: `<patch> skipped: no entry for this ROM's sha1 3CDFA4F2… / no-intro B6643CE5…`; after ticking the override: `<patch> hash mismatch - applied '…/mep/textures/ZeldaHD.ips' anyway (ApplyPatchOnHashMismatch)` |
| B5 pending-dependency prompt | PASS (log); OSD wording unverified | `depPaths=0 pendingDeps=1`; `InstallMepRecipe returned success=True resultText=1\n\naudio/`; `Status=Installed`; `mep/audio/` absent on disk |
| B6 dep resolved by sha256 | PASS | dep dropped as `definitely-not-an-ogg.bin`; `depPaths=1 pendingDeps=0`; `success=True`; `mep/audio/zelda-hd-audio.ogg` present |
| B7 wrong-bytes negative control | PASS | valid decoy zip, correct inner layout, wrong bytes → `depPaths=0 pendingDeps=1`, `resultText=1\n\naudio/`, `mep/audio/` gone again |
| smoke gate | **FAIL** — see issue #155 | `FAIL: missing target: Error while loading background: selectscreen.png`; the artifact ships `selectscreen1..6.png` and `selectscreentop.png` but no `selectscreen.png`, while `hires.txt:6124` declares it. `mep_lint.py` on the same folder reports 0 errors — the two gates disagree |

Also observed:

- Matching covered both paths: `via=game` in Part A (the dump's sha1 is not in
  the published row) and `via=sha1` in Part B (the seeded row lists it).
- HD rendering confirmed from a captured frame rather than by eye:
  `scripts/headless_record "<rom>" 4 <outdir> screenshot` produces a 512×480 PNG
  of the pack's title screen. It runs against an isolated mesen-home yet still
  loads the sibling `mep/`, so it does not disturb the installed state.
- Defects filed: **#155** (row `issue-139` declares a target it does not ship;
  `mep_lint` passes it, the smoke gate rejects it — ADR-0148) and **#156**
  (a pending dep is unrecoverable within a session; the prompt names an action
  the service skips).

### Re-run after the fixes (same day, working tree on top of `ea2bd0f2`)

Both defects were fixed and re-tested in the same session:

| Item | Result | Evidence |
|---|---|---|
| #156 — dep recovery within one session | PASS | first load: `depPaths=0 pendingDeps=1`, `mep/audio/` absent. Dep dropped into `.cache/downloads` under a deliberately wrong name (`totally-wrong-name.bin`, matched by sha256). Second **ROM load in the same process** (no restart): `depPaths=1 pendingDeps=0`, `InstallMepRecipe returned success=True resultText=1\n`, `mep/audio/zelda-hd-audio.ogg` (1.6M) on disk. Before the fix this second load logged `skipped: already attempted this session` |
| #155 — gate alignment | PASS (both gates now reject the same row) | `mep_lint.py` exit 1 with `error hires.txt:6124 <background> selectscreen.png does not exist …`; `smoke_pack_headless.sh` exit 1 with `FAIL: missing target: Error while loading background: selectscreen.png`. Same line, same file, same verdict (ADR-0151) |

Consequence to carry forward: catalog row `issue-139` no longer passes
validation. It is live and auto-installed today; the next `/revalidate` (manual
or via the daily drift check) will fail it, and ADR-0148's de-listing path
applies until the manifest or the artifact is corrected.

Note on the checklist's own steps: the "reload the ROM" step above was driven by
re-launching the binary with the ROM as `argv[1]` — `SingleInstance` forwards it
to the running process, which is the same non-power-cycle `GameLoaded` path a
manual File → Reload ROM takes.

Tester / date / build (git sha): Claude (Opus 5) with the maintainer, 2026-09-04,
`ea2bd0f21982aa35cc10595aefff5226ed2519bb` plus the uncommitted fixes for
#155/#156
