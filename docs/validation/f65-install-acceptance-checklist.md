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
- One `.ogg` file of your own to play the "user-supplied audio" role in
  Part B (any small Vorbis file; content is irrelevant, its sha256 is not).
- Paths used below (macOS):
  - Mesen home: `~/Library/Application Support/Mesen2`
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
      `"sha256": "<sha256 of your .ogg>"`.
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
- [ ] **B5. (outcome 1 — the prompt)** With your `.ogg` **absent** from
      `.cache/downloads/`, an on-screen message appears, worded exactly:
      `Missing file '<hints>' (licence: <license>) - drop it into <home>/EnhancementPacks/.cache/downloads and power cycle`
      (an undeclared licence must render as the literal `not declared`, never
      blank). The log shows `pendingDeps=1` on the
      `[CommunityPackInstall] calling EmuApi.InstallMepRecipe` line.
- [ ] **B6. (outcome 2 — hash validation)** Copy your `.ogg` into
      `.cache/downloads/` **under a deliberately wrong name** (the resolver
      matches by content sha256, never by file name) and power-cycle. The
      prompt must be gone and `pendingDeps=0`.
- [ ] **B7.** Negative control: replace the file with a different `.ogg`
      (different bytes, same name) and power-cycle. The prompt must come
      back — a name-only match would be a bug worth filing on the bug board.
- [ ] **B8.** Remove the seeded `community-packs.json` / `.etag` afterwards so
      the client returns to the published catalog.

## Post-condition gate — `scripts/smoke_pack_headless.sh`

This is the objective part of the run: it boots the real core (no GUI) over
the folder the installer just produced and fails on any missing
`<img>`/`<tile>`/`<background>`/`<bgm>`/`<sfx>` target. Run it on the **sibling
folder** (the one that holds `mep/`), not on `mep/` itself:

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

| Item | Result | Log line / path observed |
|---|---|---|
| A2 fetch + download+verify | | |
| A3 `update verdict=NotInstalled` | | |
| A4 `mep/` folder | | |
| A5 `.mep-install.json` | | |
| A7 `<patch>` applied (or hash-mismatch override) | | |
| B5 pending-dependency prompt | | |
| B6 dep resolved by sha256 | | |
| B7 wrong-bytes negative control | | |
| smoke gate | | |

Tester / date / build (git sha): ______________________
