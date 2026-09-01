# ADR-0148: A listed catalog row must be a self-contained, verifiable artifact; audio-only NEA packs with off-catalog assets and stale shared-zip hashes are de-listed, not left to fail silently

- Status: accepted
- Date: 2026-09-01
- Related: ADR-0138 §37/§43 (reinstall trigger on `source.sha256`, since
  amended by ADR-0141), ADR-0141 (one live slot per `pack_id`), ADR-0143
  (`pack_id` = origin × game, `pack:split` sibling expansion), ADR-0144
  (audio packs may supply `.ogg` tracks via a bundled ROM patch), ADR-0146
  (auto-load every accepted pack whenever possible); PRD Part A §1
  principles 1–3 and §4 slice D4; CLAUDE.md "Policy — auto-load all
  registered packs".
- Amends ADR-0144 (Decision): a bundled `.ips`/`.bps` counts toward the
  audio exception only when it is also *wired* — referenced by a `<patch>`
  line (`hires.txt`) or a `patches[]` entry (`pack.json`) — so the
  extract-audio flow actually has a patched ROM to work from. ADR-0144 as
  written (and `.github/ai/validate-classify.md`, which implements it)
  requires only that the patch be present in the archive.

## Context
The LiQuiDzGit/HDnes submission (#128) is a single GitHub archive zip
(`https://github.com/LiQuiDzGit/HDnes/archive/refs/heads/main.zip`) that
holds many game folders (the live archive fetched 2026-09-01, sha256
`2146b7f3…0b84f4`, has 15 game folders plus `HTML/`). Per ADR-0143 the
validate workflow expanded the submission into nine sibling issues — #128 (1942), #129 (Bio Miracle Bokutte Upa), #130
(Dr. Mario), #131 (Duck Hunt), #132 (Ice Climber), #133 (Ice Climber (VS)),
#134 (Super Mario Bros. 2), #135 (Super Mario Bros.), #136 (Urban Champion)
— each carrying `pack:valid` + `pack:split`, its own `pack_id`
(`liquidzgit/hdnes:<game>`) and the same pinned `source_sha256`
`2281b9fa…751687e` in its mep-meta, validated 2026-08-29 21:32–21:38Z. All
nine were live rows in `docs/community-packs.json` after the F6.5 catalog
regeneration.

Eight of the nine are "NEA" audio packs: their `hires.txt` declares only
`<bgm>`/`<sfx>` tracks (labels `assets:audio` + `patch:ips` on #128, #129,
#135 or `patch:bps` on #130, #131, #133, #134, #136; no `assets:textures`),
the referenced `.ogg` files are distributed separately by the author and
were never inside the archive (the lint runs on #128–#130 and #133–#136
report `<bgm> file does not exist … track/effect never registered`; #131
(Duck Hunt) linted clean, "0 errors / 0 warnings", its tracks being absent
rather than dangling), and — as the closing comment on #128 records —
"`hires.txt` has no `<patch>` line so the .ips is never applied". They had been classified `accepted`
under the ADR-0144 audio exception (a bundled `.ips` redeems missing `.ogg`
targets). Only #132 (Ice Climber) carries `assets:textures`.

In the client, a catalog row is downloaded and its bytes verified against
the row's `sha256` before install
(`UI/Services/CommunityPackCatalogFetcher.cs`, `DownloadAndVerifyAsync` /
`ComputeSha256`; `UI/Services/CommunityPackInstallCoordinator.cs` only
writes the resulting `source.sha256` stamp; ADR-0138 §43). GitHub branch
archives are regenerated on every push, so the shared `main.zip` no longer
hashed to the pinned value: at the time (2026-08-29 → 2026-08-31) the
download verification failed and none of the nine packs ever applied — the
failure was invisible to the player. (Since commit `3bc4482d`, 2026-09-01,
the fetcher treats a whole-repo `archive/refs/heads/<branch>.zip` as
mutable and installs it optimistically on a hash mismatch under ADR-0146;
that removes the staleness failure mode but not the self-containment one —
these eight packs would still contribute "no audio and no graphics".) Commit `916ca35e` (2026-08-30) had
just added nested-game-folder support and the ability to merge an audio-only
pack with a texture set, which is what would have made these packs usable
had they verified.

On 2026-08-31 the maintainer removed the eight audio-only siblings from the
catalog and closed their issues: commit `7bc8f13a` ("chore: remove 1942
community pack from documentation and data list", #128) and commit
`fd244f2a` ("chore: remove legacy community packs from documentation",
#129–#131, #133–#136; 161 JSON lines + 7 Markdown rows). The closing
comment on #129–#131 and #133–#136 (identical text) reads: "Removing this
pack from the catalog and closing the issue: it is an audio-only NEA pack
(no textures), and the catalog's pinned sha256 for the shared
LiQuiDzGit/HDnes repo zip is stale, so the download verification fails and
the pack never applies. Audio-only NEA packs were removed from the catalog
as a group. If the pack author ships a self-contained, texture-bearing
artifact, it can be resubmitted." The comment on #128 reads: "the artifact
is not playable standalone. The NEA audio tracks are distributed separately
(not in the pack archive), `hires.txt` has no `<patch>` line so the .ips is
never applied, and the track-7 filename comma ("Boss 1, Mid Boss A.ogg")
broke the previous parser. With no .ogg files and no patch wiring, the pack
contributes no audio and no graphics. It will be reconsidered if the pack
author ships a self-contained artifact." The eight issues kept their
`pack:valid` + `pack:split` labels; on the "MesenCE Community Packs" board
their Status was moved to "Inválido" (verified 2026-09-01 via
`gh project item-list`), which is what keeps
`scripts/generate_community_pack_catalog.py` — it selects rows by board
Status, never by issue state — from re-adding them on the next regeneration.
#132 (Ice Climber) stays open, Status "Aceito parcial (HD Mesen)", and is
the only row of the family listed today (still pointing at the same
whole-repo zip and the same pinned `sha256`).

Until now this product decision existed only in those issue comments and
commit messages (PRD §4, audit 2026-09-01, slice D4).

## Decision
1. **A listed catalog row must resolve to a self-contained artifact the
   client can verify and apply.** "Self-contained" means the archive at the
   row's URL, hashed to the row's `sha256`, contains everything the
   manifest references — textures, or audio tracks that are either bundled
   or produced at install time from a bundled **and wired** ROM patch.
   This ADR sets the bar tighter than ADR-0144, which it amends: ADR-0144
   accepts a `.ips`/`.bps` merely present in the archive; from now on the
   patch must also be referenced by a `<patch>` line / `patches[]` entry so
   it is actually applied (the eight LiQuiDz siblings met ADR-0144 and fail
   this rule). A pack
   whose only payload is an audio manifest pointing at off-catalog `.ogg`
   files is **not listable**, even when `mep_lint` passes and the classify
   verdict is `accepted`: lint validity is necessary, not sufficient, for a
   row.
2. **A stale pinned `sha256` of a shared artifact is grounds for
   de-listing, not silent failure.** When the bytes served at a row's URL no
   longer match the pinned hash, the row is removed from
   `docs/community-packs.json`/`.md` (board Status → "Inválido" so the
   generator does not restore it) and the issue receives a comment stating
   the reason. It is re-listed when the pack is re-validated against an
   artifact that satisfies rule 1 — for the LiQuiDz family the comments set
   the bar as "a self-contained, texture-bearing artifact" (or, for #128, "a
   self-contained artifact"); a fully bundled or patch-wired audio pack
   (ADR-0144 as amended by rule 1) also satisfies rule 1 and is listable. Re-validation happens
   through the existing `/revalidate` comment or a fresh submission, both of
   which recompute and re-pin the hash.
3. **Composition with ADR-0146 / CLAUDE.md auto-load policy.** "Accepted"
   in "auto-load every accepted pack whenever possible" means *present as a
   live row in `docs/community-packs.json`*. A closed issue is not a row,
   the `pack:valid` label alone does not make a pack loadable, and de-listing
   under rules 1–2 is one of the "whenever possible" exclusions — it is how
   the catalog acts as the trust boundary that ADR-0146 assigns to it
   ("a bad pack is removed from the catalog, not gated behind a per-user
   prompt"). Removal never uninstalls or interrupts a player who already has
   the pack (ADR-0141: pack removed from the catalog → keep install and
   per-ROM choice, no toast).
4. **Composition with ADR-0143.** A multi-game zip is still expanded into N
   sibling packs and N sibling issues with distinct `pack_id`s and distinct
   slots (ADR-0141). Each sibling must satisfy rule 1 **on its own**: one
   texture-bearing sibling (Ice Climber, #132) does not carry the audio-only
   siblings that share its archive, and de-listing eight siblings leaves the
   ninth listed.
5. **History, not invalidity.** The de-listed issues stay closed with their
   `pack:valid` + `pack:split` labels — the classify verdict they received
   was correct under the rules then in force (ADR-0144 before this
   amendment), and the record of
   the expansion stays intact for the author's resubmission. They are not
   re-labeled `pack:invalid`; the board Status ("Inválido") is the
   catalog-side switch, the labels are the verdict history.

## Consequences
- Implemented today (verified 2026-09-01): the eight rows are gone from
  `docs/community-packs.json` (11 rows remain, one LiQuiDz row: #132);
  the eight board items sit in "Inválido" so
  `scripts/generate_community_pack_catalog.py` (which filters by
  `ACCEPTED_STATUSES` only) does not restore them; the issues are closed with
  `pack:valid` + `pack:split`. The daily
  `.github/workflows/community-pack-drift-check.yml` already recomputes each
  accepted item's hash with `curl`+`sha256sum` and, on a change, comments
  "the pack's content changed since the last validation — revalidating
  automatically" and re-runs validation — which re-pins the hash rather than
  de-listing.
- Implemented 2026-09-01 (same day): `scripts/mep_lint.py`
  `scan_bundled_patches` now tags every `bundled patch:` line as
  `(present, wired — applied on load)` or `(present, NOT wired — …; ADR-0148)`
  from the `<patch>` lines / `patches[]` entries it linted, and the classify
  step (`.github/ai/validate-classify.md`) applies the ADR-0144 audio
  exception only to a wired patch. Follow-up, not implemented: the classify
  step does not yet check that the pack is listable under
  rule 1. An audio-only pack whose tracks live
  off-catalog and whose patch is unwired should receive a comment
  explaining that it is lint-valid but not listable (and what would make it
  so), instead of landing as an accepted row that never applies.
- Follow-up, not implemented: the catalog generator has no closed-issue or
  "de-listed" awareness beyond board Status; a row-level self-containment
  check (rule 1) does not exist in `generate_community_pack_catalog.py`,
  `mei_catalog_entry.py` or `pack_id_rules.py`.
- Follow-up, not implemented: whole-repo branch archives
  (`…/archive/refs/heads/<branch>.zip`) are inherently re-hashed on every
  push; the remaining Ice Climber row (#132) pins the same
  `2281b9fa…751687e` and is exposed to the same staleness. A stable
  per-release or per-commit URL (the "URL granular pendente" noted in the
  2026-08-31 catalog hash audit) is the durable fix; until then a drift-check
  hit on such a row should trigger rule 2 handling, not only re-validation.
  Since `3bc4482d` the client tolerates the mismatch for such URLs, so #132
  now installs; rule 2 remains the catalog-side rule for immutable URLs and
  for the catalog's own integrity.
- Client behavior: for immutable URLs a `sha256` mismatch still aborts the
  install (`CommunityPackCatalogFetcher.DownloadAndVerifyAsync` returns null,
  logging "sha256 MISMATCH"; `MepRecipeInstaller.cpp` "sha256 mismatch for
  …"); for mutable branch archives the fetcher installs optimistically
  (ADR-0146, `3bc4482d`). Surfacing the abort to the player instead of
  logging it is out of scope here (Advanced GUI, PRD Part B).

## Alternatives
- Keep the rows listed and let the client fail verification — rejected:
  the failure is silent (no toast, no log the player sees), so the product
  promise of ADR-0146 is broken invisibly while the catalog claims the pack
  exists; this is exactly the 2026-08-29 → 2026-08-31 state.
- Re-label the eight issues `pack:invalid` / re-run classify to an
  `invalid` verdict — rejected: the packs are lint-valid and the classify
  verdict was right under ADR-0144; `pack:invalid` would misdescribe them
  and erase the ADR-0143 split history the author needs to resubmit. Board
  Status "Inválido" already removes them from the generator's input.
- Bundle the author's `.ogg` tracks ourselves (mirror them or commit them)
  so the packs become self-contained — rejected: the official channel
  carries only clean data and derivative content is referenced, never hosted
  or committed (PRD Part A §1 principles 1–3).
- Re-pin the stale `sha256` to the current `main.zip` and keep the eight
  rows — rejected: it restores rows that still contribute "no audio and no
  graphics" (#128 comment) and would go stale again on the author's next
  push; only #132, which has textures, was worth keeping on that basis.
