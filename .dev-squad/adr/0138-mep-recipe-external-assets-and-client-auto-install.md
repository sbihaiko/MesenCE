# ADR-0138: MEP Recipe v1 — declarative re-packaging of split-distribution packs, issue-held metadata and client auto-install from the web catalog

- Status: proposed (design agreed with the user on 2026-08-27; nothing implemented yet — accepting this ADR is a request for the work listed in Consequences)
- Date: 2026-08-27
- Related: ADR-0040 (central per-ROM pack storage and discovery precedence), ADR-0044 (per-hash `patches[]`, hash gate on patches), ADR-0049 (sibling-folder convention), ADR-0120/ADR-0121 (zip fallback discovery, legacy `hires.txt`), ADR-0039 (No-Intro hash from the ROM file)
- Spec impact: `docs/specs/MEP-v1.md` §6 (security wording), new `docs/specs/MEP-recipe-v1.md`

## Context

Five of the twelve community packs triaged on 2026-08-27 (#65 1942, #66
Dr. Mario, #68 SMB2, #69 Yie Ar Kung-Fu, #71 SMB — all from the
LiQuiDzGit/HDnes family) are `pack:invalid`, and the verdict is correct: the
GitHub release zip contains only `hires.txt` plus an IPS/BPS patch, while
every `.ogg` referenced by `<bgm>`/`<sfx>` is distributed separately through
Google Drive/MEGA (hosts outside the CI allow-list, licence stated as
"various online file"). MEP-v1 §5 counts a section as present only when its
referenced files resolve inside the archive, so the lint is right to reject.

Installing such a zip as-is in Mesen is worse than not installing it: the
`<patch>` is applied (the HDnes patches rewrite game code so the HD audio
registers are written), then `HdPackLoader::ProcessSoundTrack`
(`Core/NES/HdPacks/HdPackLoader.cpp:826-840`) fails `CheckFile` on every
missing OGG, no track is registered and the game plays **silent**.

The user's constraints for a fix:

1. Every DE/PARA (source layout → MEP layout) metadata lives **in the issue**,
   in a programmatic form, and is *executed* by the client at runtime.
2. **No LLM in the client.** Whatever is stored must be interpreted
   deterministically.
3. The client auto-installs any pack listed in `docs/community-packs.md`,
   consulted over the web.
4. Custom, machine-readable fields on the issue, including the **sha256 of the
   source zip**, so changes upstream are detected and force revalidation.

Two facts shape where metadata can live. GitHub Issues have no custom fields;
Project fields exist (the CI already writes the content hash to "Pack Hash",
`PVTF_lAHOB1MsbM4BhjpNzhge9Is`, and `community-pack-drift-check.yml` +
`/revalidate` already re-run validation when that hash changes), but the
Projects GraphQL API requires an authenticated token an anonymous emulator
does not have. Reading issue bodies via REST works unauthenticated but is
rate-limited (60 req/h per IP) and would make the client parse Markdown from
N issues. And MEP-v1 §6 says "Hosts MUST NOT execute pack content; everything
is declarative data" — an arbitrary attached script would violate it.

## Decision

### 1. MEP Recipe v1 — a closed, declarative vocabulary

A recipe is a JSON document in a fenced ```mep-recipe block. It is
**data, not code**: the client interprets it with a fixed set of operations;
there is no scripting, no conditionals, no network access beyond the listed
sources. Shape (normative text goes to `docs/specs/MEP-recipe-v1.md`):

```json
{
  "recipe": 1,
  "sources": {
    "primary": { "url": "https://github.com/<owner>/<repo>/releases/download/<tag>/<file>.zip", "sha256": "<hex>" },
    "deps": [
      { "id": "audio", "sha256": "<hex>", "size": 123456789,
        "hints": ["https://drive.google.com/..."], "license": "various online file",
        "user_supplied": true }
    ]
  },
  "ops": [
    { "op": "copy",   "from": "primary:hires.txt",        "to": "hires.txt" },
    { "op": "copy",   "from": "primary:SMB.ips",          "to": "patches/SMB.ips" },
    { "op": "glob",   "from": "audio:**/*.ogg",           "to": "audio/" },
    { "op": "rename", "from": "audio/Track 01.ogg",       "to": "audio/track01.ogg" },
    { "op": "rewrite-paths", "file": "hires.txt", "tags": ["bgm", "sfx"], "prefix": "audio/" }
  ],
  "pack": { "name": "...", "version": "...", "targets": [{ "sha1": "<no-intro sha1>" }],
            "patches": [{ "sha1": "<no-intro sha1>", "file": "patches/SMB.ips" }] },
  "policy": { "apply_patch_only_if_complete": true }
}
```

- `ops` allowed in v1: `copy`, `glob`, `rename`, `rewrite-paths`. Anything
  else is a validation error. `from` is `<source-id>:<path>`; all paths are
  normalised and MUST stay inside the output directory (zip-slip rule of §6
  applies to recipe outputs as well).
- `pack` is the `pack.json` the client writes (MEP-v1 §3); `targets[]` and
  `patches[]` follow ADR-0044.
- `policy.apply_patch_only_if_complete: true` (default) means: if any dep is
  missing or fails its hash, the pack is installed **without** the patch and
  without the sections that depend on the missing dep, and the UI says so —
  never the silent-game outcome above.
- Sources are verified by sha256 **before** any op runs; a mismatch aborts the
  install (protects against a swapped link or compromised release).

### 2. Where the metadata lives — issue is the source of truth

- **Issue Form** (`.github/ISSUE_TEMPLATE/community-pack.yml`) gains
  structured fields: `external_assets` (one URL per line, for assets not in
  the primary zip), `external_assets_license`. Existing fields stay.
- **Classify step** (the only place an LLM runs, in CI) emits the
  ```mep-recipe block from the lint report + manifest + form fields. It
  treats file names, manifest and issue text as data, never as instruction
  (unchanged rule).
- **CI validates and dry-runs the recipe** with a new stdlib-only
  `scripts/mep_recipe.py` (`validate`, `dry-run`, `apply`): the schema check
  rejects unknown ops/escaping paths; the dry-run applies the ops to the
  downloaded primary (deps stubbed by their declared names) and runs
  `mep_lint.py` on the result. A recipe that does not produce a lint-clean
  pack fails the submission.
- **Bot comment with machine-readable block.** The CI upserts one comment
  marked `<!-- mep-meta -->` containing a JSON block with the computed data:
  `source_sha256`, per-dep `sha256`/`size` when obtainable, `verdict`,
  `labels`, `validated_at`, `recipe_hash`. It is rewritten in place on every
  revalidation, so the history stays on the issue and does not depend on
  Project fields.
- The Project "Pack Hash" field keeps its role as the **CI-side revalidation
  trigger** (drift check / `/revalidate`); the JSON only mirrors it.
- New labels: `assets:external` (pack needs user-supplied deps) alongside the
  existing taxonomy; `scripts/ensure_community_pack_labels.sh` creates it.
- Verdict semantics: a split-distribution pack whose recipe dry-runs clean is
  `accepted` (Status "Aceito parcial (HD Mesen)", label `pack:valid` +
  `assets:external`). A pack with missing files and **no** viable recipe stays
  `invalid` (MEP-v1 §5).

### 3. What the client reads — `docs/community-packs.json`

`scripts/generate_community_pack_catalog.py` emits, next to the Markdown, a
`docs/community-packs.json` built from the board's accepted items and each
issue's `<!-- mep-meta -->` block and recipe (CI has the token; the client
does not). One entry per pack:

```json
{ "issue": 71, "game": "Super Mario Bros.", "console": "nes",
  "rom": { "sha1": ["<no-intro sha1>"] },
  "source": { "url": "...", "sha256": "..." },
  "deps": [ { "id": "audio", "sha256": "...", "hints": ["..."], "license": "...", "user_supplied": true } ],
  "recipe": { ... },
  "verdict": "accepted", "validated_at": "2026-08-27T21:25:00Z", "catalog_version": 1 }
```

Served from `raw.githubusercontent.com/sbihaiko/MesenCE/main/docs/community-packs.json`:
one unauthenticated, cacheable request. The Markdown stays the human view.

### 4. Client — `MepRecipeInstaller` (C++, Core)

- Fetches the catalog (ETag/If-None-Match, cached under the MEP `.cache`
  directory), matches the loaded ROM by No-Intro sha1 (MEP-v1 §4,
  ADR-0039), and for each matching accepted entry:
  1. downloads `source.url` (same host allow-list as CI), verifies sha256;
  2. for each dep: if a file with the declared sha256 is already in the
     per-ROM pack folder or the user's downloads cache, uses it; otherwise
     shows a UI prompt with the `hints` and licence text asking the user to
     supply the file (the client never scrapes Drive/MEGA); the pack is
     installed with `policy.apply_patch_only_if_complete` applied;
  3. runs the `ops`, writes `pack.json`, and stores
     `.mep-install.json` (`catalog_version`, `source.sha256`, dep hashes,
     `recipe_hash`, `installed_at`) in the pack folder.
- Output location is the central per-ROM folder of ADR-0040 (the same place
  HdPacks use), so discovery precedence and the sibling-folder convention
  (ADR-0049) are unchanged.
- Auto-install is a setting in EnhancementPackConfig (`AutoInstallCommunityPacks`,
  default **on** for accepted packs whose deps are all downloadable, i.e. no
  `user_supplied` dep; packs needing user files prompt instead of installing
  silently). A pack whose catalog `source.sha256` differs from the installed
  `.mep-install.json` is reinstalled.
- **No LLM, no scripting**: the installer is a fixed interpreter of the four
  ops. Unknown op or `recipe` version → skip with a `[MEP] recipe unsupported`
  log and UI notice.

### 5. Spec amendment (MEP-v1 §6)

Replace "Hosts MUST NOT execute pack content; everything is declarative data"
with: "Hosts MUST NOT execute pack content as code. Patches (`patches[]`,
ADR-0044) and recipes (MEP-recipe-v1) are declarative data interpreted by a
fixed host vocabulary; hosts MUST reject any recipe operation outside that
vocabulary and any path that escapes the pack directory." This also settles
the pre-existing §6 vs `patches[]` tension noted in the 2026-08-27 ADR review.

## Consequences

Work implied by accepting this ADR, in order:

1. `docs/specs/MEP-recipe-v1.md` (normative recipe schema) + §6 amendment in
   `docs/specs/MEP-v1.md`; golden recipe fixture under `docs/specs/`.
2. `scripts/mep_recipe.py` (`validate` / `dry-run` / `apply`, stdlib only) +
   unit tests in the Python test set; wire `dry-run` into
   `community-pack-validate.yml` after lint, before classify.
3. Issue Form fields `external_assets` / `external_assets_license`; label
   `assets:external` in `ensure_community_pack_labels.sh`; classify prompt
   emits the recipe; new "Upsert mep-meta comment" step.
4. `generate_community_pack_catalog.py` emits `docs/community-packs.json`
   (and the Markdown gains an "external assets" marker per row).
5. Core: `MepRecipeInstaller` + `.mep-install.json`, `AutoInstallCommunityPacks`
   setting, UI prompt for user-supplied deps; headless test via the existing
   `gen_mep_test_pack.py` harness with a synthetic split pack.
6. Re-run `/revalidate` on #65, #66, #68, #69, #71 once 1–3 ship; they should
   flip to `pack:valid` + `assets:external`.

Other consequences:

- The five HDnes packs become installable with one user action (supplying the
  audio archive), and never in the silent-game state.
- The client gains a network dependency (catalog + primary zips) that is
  opt-out via the setting; CI's host allow-list is reused verbatim so the
  attack surface does not widen.
- Any change to the recipe vocabulary is a new `recipe` version and a new
  ADR; old clients skip newer recipes rather than misinterpret them.
- Prerequisite/independent fix: `community-pack-submitted.yml` currently
  cancels its own run when the verdict comment fires `issue_comment`
  (`cancel-in-progress: true`), losing the catalog-dispatch step; set
  `cancel-in-progress: ${{ github.event_name == 'issues' }}`. Without it the
  JSON catalog would go stale after every accepted pack.

## Alternatives

- **Attach a shell/Python script to the issue and run it in the client** —
  rejected: violates MEP-v1 §6, unauditable, and would require shipping an
  interpreter; the closed op vocabulary covers every observed HDnes layout.
- **Have CI re-zip the complete pack and host it in the repo/releases** —
  rejected: the audio has no redistribution licence ("various online file");
  MesenCE must not become the distributor. The recipe keeps the user as the
  one fetching the licensed material.
- **Client reads Project fields or issue bodies directly** — rejected:
  Projects API needs a token; issue REST is rate-limited and Markdown-parsed.
  The generated JSON is one cacheable file.
- **Accept split packs without a recipe and let the loader warn** — rejected:
  that is the current silent-game behaviour; the patch must not be applied
  without the assets it presupposes.
- **Store the recipe only in the catalog JSON (not in the issue)** —
  rejected: the user requires the issue to be the auditable source of truth;
  the JSON is derived and regenerable.
