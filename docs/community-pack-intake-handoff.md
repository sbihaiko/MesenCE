# Community pack intake handoff

**Audience:** another coding agent. Follow this file as the task. Do not
expand scope into emulator features, ROM dumps, or core work.

Researched 2026-08-30 against the user's NES folder
`/Users/bihaiko/VSCodeProjects/EMULADORES/2. Switch/G3 - Nitendinho/roms`
plus RHDN, Google, [NesDev HD Pack's Mesen](https://forums.nesdev.org/viewtopic.php?t=17110),
[NESMakers 8385](https://www.nesmakers.com/index.php?threads/hd-packs-for-mesen.8385/)
(no packs), and a second pass over:

- [Retro Gaming Banter list](https://retrogamingbanter.com/hd-texture-packs-for-8-bit-nes-games/) (best public index; St1ka video roundup)
- [r/emulation Megaman Super v2.0](https://www.reddit.com/r/emulation/comments/nn4ipy/megaman_super_v_20_released_mesen_hd_pack/)
- [r/emulation Metroid HD overhaul](https://www.reddit.com/r/emulation/comments/1abla4p/overhauled_nes_metroid_enhancement_pack_uses_new/)
- [Peakd / acstriker showcase](https://peakd.com/hive-140217/@acstriker/engesp-playing-nes-games-with-high-resolution-sprites-and-custom-music-ft-mesen)
- [Libretro "HD packs don't work"](https://forums.libretro.com/t/mesen-hd-packs-dont-work/44054) — support thread, **no pack catalog** (Mega Man / Zelda mentioned as test cases; RetroArch Mesen core ≠ standalone Mesen 2)

## Goal

Submit **new** community HD/MEP packs through the existing GitHub Issue Form
pipeline so validate + classify + catalog run. Prefer packs that match the
user's ROMs and that already live on an allow-listed host as a **ZIP**.

Do **not** re-submit anything already in `docs/community-packs.md`.

## Hard constraints

- Product branch is `main`. Never merge `upstream/master` (or GitHub Sync
  fork) into `main`.
- Remaining cores: NES, GB/GBC/GBS, SMS/GG/SG-1000, GBA. No SNES/PCE/WS/Coleco
  packs. SNES **gamepads** stay.
- All **docs, AGENTS.md, Issue/PR titles and bodies, workflow comments** are
  **en-US**. Chat with the human may follow their language.
- Bugs go to `scripts/report-bug.sh`. **Packs do not.** Never use
  `report-bug.sh` for this work. Board is
  [MesenCE Community Packs](https://github.com/users/sbihaiko/projects/3)
  (Project 3), not the bug tracker.
- Read the DOX chain before editing: root `AGENTS.md`, then
  `docs/AGENTS.md`, `.github/AGENTS.md`, `scripts/AGENTS.md` as you touch
  those trees. `scripts/pack_host_allowlist.json` is a trust boundary.
- GitHub Issue Form Status option names on Project 3 stay the Portuguese
  literals: `"Novo envio"` → `"Em validação"` → `"Inválido"` /
  `"Aceito parcial (HD Mesen)"` / `"Aceito (MEP completo)"`.
- `mep_lint.py` opens **ZIP only** (`zipfile`). A `.7z` artifact fails lint.
  Do not unpack and re-host the pack on a new URL (that is redistribution).
  Skip `.7z`-only releases, or find an official ZIP on the same thread.
- Forum topic URLs (`romhacking.net/forum/...`, `forums.nesdev.org/viewtopic.php`,
  `nesmakers.com`) are **not** download URLs and are **not** on the allow-list.
  The Issue Form **Pack link** must be the file itself.
- Do not add `romhacking.net`, `forums.nesdev.org`, `nesmakers.com`, or
  `liquidz*.net` to the allow-list unless the human explicitly asks. Allowed
  hosts today: GitHub releases/archive/raw/gist, Google Drive, MediaFire
  `/file/` + `*.mediafire.com` CDN.

## Pipeline (do this for each new pack)

1. Confirm the game is **not** already a row in `docs/community-packs.md`.
2. Open the source thread. Extract a **direct ZIP** (or Drive/MediaFire/GitHub
   Release) URL. If Cloudflare blocks the forum, try print view, YouTube
   descriptions, NesDev `view=print`, or GitHub mirrors listed below.
3. Confirm the host is in `scripts/pack_host_allowlist.json`. If it is not,
   **stop and ask** before editing the allow-list.
4. Create the issue with the form headings the workflows parse. **Put
   `community-pack` on create** (an opened webhook without that label never
   starts validate). Do not add the label in a second command after create.

```bash
# labels MUST be on this create call
gh issue create --repo sbihaiko/MesenCE \
  --title "[Pack] <Game (Region)>" \
  --label community-pack \
  --body "$(cat <<'EOF'
### Pack link

<https-direct-zip-or-drive-or-mediafire-file-url>

### Target game/ROM and region

<Game (USA)>   # human game name + region; not a filename lecture

### Console

NES
EOF
)"
```

The submit workflow takes the **first** `http(s)://` in the body as
`pack_url`. Put no other URL above Pack link.

5. Confirm `.github/workflows/community-pack-submitted.yml` (and the
   reusable validate + catalog workflows) are **enabled**. They have been
   `disabled_manually` before.
6. Watch the Actions run on that issue. Classify can fail structured output;
   comment **exactly** `/revalidate` (no extra text) to retry. Do not cancel
   an in-flight run with another `/revalidate` until it finishes (catalog
   dispatch is after the verdict comment).
7. On `"Aceito*"` Status, `community-pack-catalog.yml` should regenerate
   `docs/community-packs.md` + `docs/community-packs.json` on `main`. If the
   catalog job did not run, `gh workflow run community-pack-catalog.yml` and
   confirm the commit lands. Do **not** hand-edit those two files.
8. If lint fails because the zip is a wrapper with one nested zip (Zelda
   Remastered shape), that is already handled client-side; CI `mep_lint`
   still needs a discoverable `hires.txt` / `pack.json`. Read the lint
   comment; do not invent a new host.

## Priority queue (run these)

Work top to bottom. One issue per pack. Stop a row if you cannot find an
allow-listed ZIP.

| Priority | Game | Why | Where to get the Pack link |
|---|---|---|---|
| 1 | Bomberman (USA) | User has the ROM; not in catalog | [RHDN 30619](https://www.romhacking.net/forum/index.php?topic=30619.0) (imkrut). Forum page is not the pack URL. |
| 2 | Ninja Gaiden (USA) | User has the ROM; not in catalog | [RHDN 26164](https://www.romhacking.net/forum/index.php?topic=26164.0) (RichterSnipes, beta). Prefer NG1 ZIP for the user's ROM; NG2 is a second issue if a separate ZIP exists. |
| 3 | 1943 (USA) | User has the ROM; catalog only has 1942 | Official artifact is **7z**: `https://www.mediafire.com/file/aqfadtaaj2xbze7/1943_%28U%29.7z/file` ([NesDev](https://forums.nesdev.org/viewtopic.php?t=17110&start=60), mkwong98, [demo](https://youtu.be/9mRQ9aCG-7c)). **Skip unless you find a ZIP.** Do not convert/rehost. |
| 4 | Donkey Kong (JU) | Clean MediaFire ZIP; not in catalog | `https://www.mediafire.com/file/5xgz6dr0tyiqm6g/Donkey_Kong_%28JU%29_HD_Pack.zip/file` (mkwong98; also on the Banter list) |
| 5 | Popeye (World) (Rev A) | GitHub; not in catalog | [LiQuiDzGit/HDNES-POPEYE](https://github.com/LiQuiDzGit/HDNES-POPEYE) — use a **release or raw zip**, not the repo HTML homepage if that 404s as a file. |
| 6 | Megaman: Super (USA) | Alternate to catalog Mega Man | [RHDN 25426](https://www.romhacking.net/forum/index.php?topic=25426.0) / [GitHub AxlRocks/Megaman-Super](https://github.com/AxlRocks/Megaman-Super) / [r/emulation v2.0](https://www.reddit.com/r/emulation/comments/nn4ipy/megaman_super_v_20_released_mesen_hd_pack/). Only if a ZIP/release URL exists. |
| 7 | Castlevania Rondo of Blood style | Alternate to catalog kya pack; Mesen 2 | `https://www.mediafire.com/file/cezj6r6s06obdhi/Castlevania_%2528U%2529_%2528PRG_1%2529.7z/file` (mkwong98, 2026-08-24, [NesDev p.7](https://forums.nesdev.org/viewtopic.php?t=17110&start=90), [YouTube](https://youtu.be/Z7-1pDp7ZMg)). **7z — skip unless a ZIP appears.** |
| 8 | Metroid HD | **Submitted [#148](https://github.com/sbihaiko/MesenCE/issues/148).** Pack link is the allow-listed MediaFire 2.0 ZIP (JUD6MENT orchestral + Aclectico graphics, 280.8 MiB, local `mep_lint` 0 errors). Drive 2.0 default-music wrapper is 476 MiB — over the 300MB cap. MetConst 2.1.2 is the current canonical ([hack 381](https://www.metroidconstruction.com/hack.php?id=381)) but that host is not allow-listed; do not add it or re-submit unless the human asks. ROM SHA-1 `ecf39ec5a33e6a6f832f03e8ffc61c5d53f4f90b`. |
| 9 | TwinBee Remastered | [RHDN 30670](https://www.romhacking.net/forum/index.php?topic=30670) |
| 10 | Battle City | [RHDN 30639](https://www.romhacking.net/forum/index.php?topic=30639); YuriEgorov also on NesDev |
| 11 | Donkey Kong Jr. Remastered | [RHDN 30538](https://www.romhacking.net/forum/index.php?topic=30538.0) |
| 12 | Little Nemo (demo) | [RHDN 28358](https://www.romhacking.net/forum/index.php?topic=28358) |
| 13 | Shatterhand | [RHDN 26926](https://www.romhacking.net/forum/index.php?topic=26926.0) |
| 14 | Ice Climber Remastered | Only if distinct from catalog Ice_Climber [#132](https://github.com/sbihaiko/MesenCE/issues/132). [RHDN 30581](https://www.romhacking.net/forum/index.php?topic=30581.0) |
| 15 | Kung Fu | NesDev attachment `file.php?id=12070` is **not** allow-listed. Skip unless a Drive/MediaFire/GitHub ZIP exists. |
| 16 | Nuts & Milk | Same: NesDev `file.php?id=12071`. Skip unless rehosted by the author on an allowed host. |
| 17 | Road Fighter | NesDev attachment only. Skip unless allow-listed ZIP. |
| 18 | Paper Mario Bros (SMB1 reskin) | [RHDN 31920](https://www.romhacking.net/forum/index.php?topic=31920). Optional; catalog already has SMB1 Cubear. |
| 19 | SMB Arcade / lyonhrt / mkwong98 SMB | Optional duplicates of catalog SMB. NesDev rars are not allow-listed. Lyonhrt tree: [GitHub](https://github.com/lyonhrt/hdnes-projects/tree/master/Super%20Mario%20Bros) (not a release zip by itself). |
| 20 | Faxanadu Revisioned, Dig Dug Deluxe, Galaga, Galaxian, Mappy, Ms. Pac-Man, Circus Charlie, Bowser's Castle | Listed on LiQuiDz hub / NesDev index only. Take only if you find an allow-listed ZIP. LiQuiDz HTTP hosts are **not** on the allow-list. |

## Do not submit (already cataloged)

| Game | Issue |
|---|---|
| Contra (USA) | [#137](https://github.com/sbihaiko/MesenCE/issues/137) |
| Mega Man (USA) (the catalog slot, not Super) | [#138](https://github.com/sbihaiko/MesenCE/issues/138) |
| The Legend of Zelda (USA) | [#139](https://github.com/sbihaiko/MesenCE/issues/139) |
| Castlevania (USA) (kya / MediaFire already in) | [#143](https://github.com/sbihaiko/MesenCE/issues/143) |
| Donkey Kong (JU) | [#144](https://github.com/sbihaiko/MesenCE/issues/144) |
| Ninja Gaiden (USA) | [#145](https://github.com/sbihaiko/MesenCE/issues/145) |
| Paper Mario Bros (SMB1 reskin) | [#147](https://github.com/sbihaiko/MesenCE/issues/147) |
| Metroid (USA) (MediaFire 2.0 orchestral ZIP) | [#148](https://github.com/sbihaiko/MesenCE/issues/148) |
| Super Mario Bros | [#135](https://github.com/sbihaiko/MesenCE/issues/135) |
| Super Mario Bros. 2 | [#134](https://github.com/sbihaiko/MesenCE/issues/134) |
| Zelda II | [#141](https://github.com/sbihaiko/MesenCE/issues/141) |
| 1942 | [#128](https://github.com/sbihaiko/MesenCE/issues/128) |
| Duck Hunt, Ice Climber, Pac-Man, Dr. Mario, Bio Miracle, Urban Champion | [#131](https://github.com/sbihaiko/MesenCE/issues/131) [#132](https://github.com/sbihaiko/MesenCE/issues/132) [#140](https://github.com/sbihaiko/MesenCE/issues/140) [#130](https://github.com/sbihaiko/MesenCE/issues/130) [#129](https://github.com/sbihaiko/MesenCE/issues/129) [#136](https://github.com/sbihaiko/MesenCE/issues/136) |

Banter-list URLs for games **already in the catalog** (do not open a second issue; useful if `/revalidate` needs a current file):

- Duck Hunt Remastered (Drive): `https://drive.google.com/file/d/1j4b0kousFpvSnvywld1_gHT-fUayfoXT/view?usp=sharing`
- Pac-Man (Ed Peppe): [github.com/PepCodes/HDNes-Graphics-Pac](https://github.com/PepCodes/HDNes-Graphics-Pac)

Contra [RHDN 33075](https://www.romhacking.net/forum/index.php?topic=33075.0) is stage-1-only; do not replace #137 with it unless the human asks.

## User ROMs with no pack found anywhere

Do not invent issues for these:

- Excitebike
- Gauntlet
- Mike Tyson's Punch-Out!!
- Super Mario Bros. 3

## Done when

- Each attempted priority row is either a live issue with a validate run, or a
  one-line skip reason (no ZIP, host not allowed, duplicate, 7z-only).
- Accepted packs appear in `docs/community-packs.md` on `main` (catalog
  workflow commit, not a manual table edit).
- Allow-list edits, if any, are committed with a short en-US reason and the
  existing `kind` / `host_ends_with` conventions.
- Report skipped rows to the human in their chat language.

## Related files

- `.github/ISSUE_TEMPLATE/community-pack.yml`
- `.github/workflows/community-pack-submitted.yml`
- `.github/workflows/community-pack-validate.yml`
- `.github/workflows/community-pack-catalog.yml`
- `scripts/pack_host_allowlist.json`
- `scripts/generate_community_pack_catalog.py`
- `docs/hd-pack-authoring.md`
- `docs/community-packs.md` / `docs/community-packs.json`
