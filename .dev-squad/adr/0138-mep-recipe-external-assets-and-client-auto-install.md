# ADR-0138: MEP Recipe v1 — declarative re-packaging of split-distribution packs, issue-held metadata and client auto-install from the web catalog

- Status: accepted (design agreed with the user on 2026-08-27; F6.0 and F6.1 shipped; F6.2–F6.5 remaining — see Consequences; the user runs the implementation outside the autonomous dev-squad task)
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
  downloaded primary (no `--dep` supplied — missing `user_supplied` deps
  follow MEP-recipe-v1 §6's skip semantics, see Clarification §22) and runs
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
   `docs/specs/MEP-v1.md`; golden recipe fixture under `docs/specs/`. **Shipped as F6.1.**
2. `scripts/mep_recipe.py` (`validate` / `dry-run` / `apply`, stdlib only) +
   unit tests in the Python test set (**shipped as F6.1**); wire `validate` +
   `dry-run` into `community-pack-validate.yml` as a gate **after classify,
   before apply-verdict** (F6.2; the recipe is classify's own output, so it
   cannot be checked before classify runs — see Clarifications §1).
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
  JSON catalog would go stale after every accepted pack. **Shipped as
  F6.0** (also `timeout-minutes: 15` on the classify step, catalog
  backfill of #64/#73).

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

## Clarifications (after run 9967a42e92f1, 2026-08-28)

The first F6.2 run failed at Decompose because the points below were open.
Settled here; the nine auto-minted review ADRs (retired ids 0139–0147 reused
again) are folded and deleted.

1. **Pipeline seam.** `lint` → `classify` → **recipe gate** (`mep_recipe.py
   validate` then `dry-run` against the downloaded primary, deps stubbed) →
   `apply-verdict` → upsert `<!-- mep-meta -->`. Consequences item 2 above is
   corrected accordingly; "after lint, before classify" was unsatisfiable.
2. **Verdict precedence (two sources, one rule).** The deterministic gate is
   *inert* when classify emitted no recipe — the existing binary verdict path
   is untouched. When a recipe is present the gate may only **downgrade**
   `accepted` → `invalid` (schema failure or lint-unclean dry-run); it never
   upgrades an `invalid` classify verdict. `assets:external` is an additive
   content-index label like `assets:textures`/`assets:audio`, never a third
   verdict state; the verdict stays binary with Status "Aceito parcial (HD
   Mesen)". This rule is also stated in the workflow header comment and
   asserted by the `scripts/checks/` verifier.
3. **Dependency hashes come from the submitter.** MEP-recipe-v1 keeps
   `sources.deps[].sha256` as MUST (spec unchanged; the client contract of §4
   depends on it) and CI never downloads external deps. Therefore each
   `external_assets` line is `<url> [<sha256>] [<size>]`. A dep line **without**
   a sha256 means "no recipe for this submission": classify does not emit one,
   the verdict path is the pre-ADR one (`invalid` when files are missing, MEP-v1
   §5), and the verdict comment tells the submitter how to compute the hash
   (`sha256sum <file>`) and re-run `/revalidate`. Option (b) — hash-less deps
   pinned at first install — is rejected: it moves trust from the issue to the
   first downloader.
4. **The LLM never writes hashes.** Classify's structured output carries only
   the non-derivable parts: `ops`, `deps[]` (`id`, `hints`, `license`,
   `user_supplied`), `pack` metadata. A deterministic step assembles the
   hash-bearing `sources` block — `primary.url` from the form's pack link,
   `primary.sha256` from `steps.hash`, dep `sha256`/`size` from the parsed
   `external_assets` lines — and writes the final recipe before the gate runs.
   Prompt/schema growth stays bounded under the F6.0 15-minute cap.
5. **`<!-- mep-meta -->` is bot-owned.** The comment is rewritten wholesale on
   every pass (find the marked comment → PATCH its body; never merged with
   existing content); a missing or malformed block means "no prior metadata",
   not an error. Concurrency: `community-pack-submitted.yml` already groups
   all events of one issue under `community-pack-submitted-<number>` — GitHub
   serialises runs in a group (one running, one pending), so two `/revalidate`
   comments cannot interleave their read-modify-write; only *cancellation* is
   restricted to `issues` events (F6.0). No change needed; recorded so the
   race is not re-litigated.
6. **`assets:external` is derived, not judged.** The label comes from the
   assembled recipe having a non-empty `sources.deps` (a deterministic step
   output), not from the LLM's `assets` enum. `apply-verdict` applies it the
   same way it applies `assets:textures`/`assets:audio` today (an `external`
   branch in its label loop, fed by the assembly step's output). Creating the
   label (`ensure_community_pack_labels.sh`) and applying it are two
   deliverables, each with its own check — the second is the one the PRD's
   acceptance line ("`/revalidate` on #71 → `pack:valid` + `assets:external`")
   actually exercises.
7. **Where "no recipe" is decided.** §3 said "classify does not emit one";
   read together with §4 that means: classify may omit `ops/deps/pack` for a
   non-split pack, *and* the deterministic assembly step refuses to assemble
   `sources` when any `external_assets` line lacks a sha256. Either outcome is
   "no usable recipe" and leaves the gate inert (§2). The hash veto never lives
   in the prompt.
8. **One workflow, one text verifier.** Checks on
   `community-pack-validate.yml` text (assembly step present, gate after
   classify and before apply-verdict, downgrade-only shell logic, `external`
   label branch, wholesale upsert) extend the `CHECKS` tuple of the existing
   `scripts/checks/verify_community_pack_validate_workflow.py`. New standalone
   verifiers are only for new artefacts (the Issue Form fields, the labels
   script).
9. **One named handoff.** The assembly step writes the recipe to a single
   runner-local artefact, `mep_recipe.json` at the workspace root, and exposes
   one boolean step output `recipe_present`. Every downstream reader (gate,
   `external` label branch, mep-meta `recipe_hash`, later F6.3 MEI emission)
   reads that path/output — never re-derives "is there a recipe?". Recorded
   in `.github/AGENTS.md` Local Contracts; the workflow verifier asserts it.
10. **`apply-verdict` stays the sole verdict writer.** The gate step emits
    only `recipe_ok` (boolean) and never touches labels or Status.
    `apply-verdict` computes the effective verdict in one expression —
    `accepted` becomes `invalid` when `recipe_present && !recipe_ok` — so
    downgrade-only follows from the expression's shape, not from step order,
    and the verifier asserts that single line.
11. **Provenance is explicit.** `sources.primary.sha256` is CI-computed;
    every `sources.deps[].sha256`/`size` is submitter-declared and carried
    with `user_supplied: true`. The mep-meta comment states that
    `recipe_hash` covers the recipe document, not dep contents; dep digests
    are verified by the client at install time (§4).
12. **`external_assets` field contract (normative for both slices).** The
    Issue Form field is a `textarea` (id `external_assets`, optional). One
    dependency per non-empty line; blank lines and lines whose first
    non-space character is `#` are ignored; fields are whitespace-separated
    `<url> [<sha256>] [<size>]` (`sha256` = 64 lowercase hex, `size` =
    decimal bytes). Any dependency line lacking `sha256` disables recipe
    assembly for the whole submission (§3). `external_assets_license` is a
    single-line `input` (optional, free text). The F6.2a Issue-Form verifier
    and the F6.2b parser both cite this paragraph; neither invents a shape.
13. **Handoff location and status (amends §9).** The assembly step writes
    the recipe to `$RUNNER_TEMP/mep_recipe.json` — runner-local, never
    inside the checkout, so it can never be mistaken for (or committed as) a
    repo artefact — and exposes one step output `recipe_status` with exactly
    three values: `absent` (no external assets declared), `present` (recipe
    assembled and written), `refused` (assets declared but a dep lacks a
    sha256, §3/§12 — assembly declined). Downstream readers branch on the
    enum: the gate runs only on `present`; `assets:external` is applied only
    on `present`; `apply-verdict`'s downgrade expression (§10) reads
    `recipe_status == 'present' && !recipe_ok`; `refused` takes the pre-ADR
    verdict path and the verdict comment explains the missing hash. Wherever
    §9/§10 above say `recipe_present`, read `recipe_status == 'present'`.
14. **No inverted regression guards.** A verifier must assert the desired
    steady state, never pin a known failure message. The pre-existing defect
    that prompted one (`verify_community_pack_issue_template.py` required an
    `snes` option the Console dropdown must not have — CLAUDE.md, no
    `console:snes`) is fixed at the root in the same commit as this
    paragraph; the verifier now passes on `main` and F6.2a extends it for
    §12 rather than wrapping it.
15. **Array-shaped verifiers (after the F6.2a run 4f0d742630e5).** The
    six review ADRs minted by that run (retired ids 0139–0144 reused again)
    all concern `verify_community_pack_labels_script.sh` and are folded here:
    the verifier keeps an explicit expected name set *outside* the labels
    script (the independent expectation is the check's whole value — never
    derive it from the target) and derives its count from that set instead
    of a literal. Recorded as the standing pattern in `scripts/AGENTS.md`.
16. **`recipe_ok` is not dep integrity (restates §11 for the workflow).**
    CI never fetches or hashes external deps: the gate's `validate` +
    `dry-run` cover the recipe document and the CI-hashed primary only.
    `sources.deps[].sha256`/`size` are submitter-attested and are verified
    exclusively by the client at install time (§4, MEI trust model
    ADR-0006). The `<!-- mep-meta -->` block states this in one line
    ("dep digests: submitter-declared, verified on install") and the
    verdict comment says the same; MEP-recipe-v1 already carries
    `user_supplied: true` (§11) — no spec change. Fetch-and-verify in CI is
    rejected for v1: it re-introduces the size/host problem the split
    distribution exists to avoid. Corollary: `recipe_ok` is also silent
    about dep-dependent ops — the gate's dry-run runs with no `--dep`, so
    ops reading from a dep are skipped per MEP-recipe-v1 §6 (§22).
17. **Issue body is fetched, never taken from the event.** The assembly
    step reads the `external_assets` field with `gh issue view
    "$ISSUE_NUMBER" --repo "$REPO" --json body -q .body` — the same call the
    existing title/console step already makes (`inputs.issue_number` is the
    reusable workflow's only identity input). `github.event.issue.*` is
    never referenced by any new step, so the `issues`, `/revalidate` and
    scheduled drift-check callers resolve the same `recipe_status` for the
    same issue; the verifier asserts the absence of `github.event.issue` in
    the new steps. No "sticky" mep-meta logic is needed once the input is
    the issue itself.
18. **Two stores, one rule.** The Project "Pack Hash" field remains the
    authoritative, bot-only store for the primary sha256 (unchanged). The
    `<!-- mep-meta -->` comment is the only store for dep digests,
    `recipe_hash` and verdict provenance, and is rewritten wholesale by CI
    (§5). F6.3's catalog generator reads the primary hash from the field and
    the dep/recipe data from mep-meta; if the mep-meta `source_sha256`
    disagrees with the field, the generator emits no recipe for that pack
    and logs the mismatch (the field wins; a human-edited comment can never
    upgrade a pack). Both writers are bot-owned; human edits to the comment
    are overwritten on the next validation.

19. **Assembly failure never strands the item (after run 3cca17a3180c).**
    `assemble-recipe` carries `continue-on-error: true`; `apply-verdict`
    keeps its plain `steps.classify.outcome == 'success'` condition. An
    empty `recipe_status` is not `present`, so the downgrade expression is
    inert and the pre-ADR verdict path runs. `apply-verdict` writes its
    `verdict`/`labels` outputs *before* the Project writes, so a partial
    failure there never feeds empty values into mep-meta.
20. **Classify schema shape and the second handoff.** The classify schema
    keeps `required: [verdict, assets, comment]` at the top level; the recipe
    fragment is ONE optional nested `recipe` object whose subschema requires
    `ops`, `deps`, `pack` (§4/§7's "may omit" is satisfied at the fragment
    level). The assembly step consumes `jq -r '.recipe // {}'` of the
    structured output, never the whole object. `absent` means "classify
    emitted no recipe *content*" (empty containers included). `apply-verdict`
    exposes `verdict` (effective, post-downgrade) and `labels` (applied) as
    step outputs — the second named intra-workflow handoff besides §13's
    `recipe_status`; mep-meta and later F6.3 consume them, never re-derive.
21. **Lines are the spine.** `sources.deps` is built one-per-`external_assets`
    line (synthesized `extN` ids when classify has no matching `hints` URL,
    trailing-slash-normalised matching); classify's `deps[]` only decorates
    with id/hints/license. `user_supplied` is forced `true` on every such dep
    (§11 wins over §4). Precedence: lines are parsed before the fragment is
    consulted, so a hash-less/malformed line is `refused` even when classify
    emitted no content; `absent` is reserved for "no lines, or well-formed
    lines but no classify content". mep-meta records `deps`/`recipe_hash`
    whenever `present`, plus `recipe_ok` so a reader can tell a passing
    recipe's digests from a gate-rejected one's. `refused` stays
    non-downgrading but appends a submitter-facing note (how to compute
    `sha256sum`, `/revalidate`) to the verdict comment (§3).
22. **"Deps stubbed by name" means MEP-recipe-v1 §6, not a CLI mode.** There
    is no `--stub-dep`; the gate supplies no `--dep`, and the spec's
    `apply_patch_only_if_complete` semantics apply: skip ops whose `from` is
    the missing dep, skip `rename`/`rewrite-paths` whose source would only
    have been produced by such a skipped op (transitive closure — spec §6
    amended and `run_recipe` fixed in the same commit), skip patch dests,
    omit `pack.patches`. Placeholder sources per dep id are rejected (they
    re-open §16).
23. **File-size guardrail vs "one file" mandates.** §8's "one verifier" is
    read as one verifier *entry point*: `verify_community_pack_validate_workflow.py`
    may import its `CHECKS` from topic modules under `scripts/checks/`.
    Likewise the CI-side assembly (issue parsing, merge, `assemble-sources`
    CLI) may move out of `scripts/mep_recipe.py` into a sibling stdlib module
    sharing `RecipeError`/`SHA256_HEX`. Both splits are a mechanical slice
    (**F6.2c**) to run before F6.3 adds more checks.
24. **Split convention for `scripts/` (after the F6.2c run 05a8927950be).**
    When a script is split, shared symbols move to a dependency-free leaf
    module (`mep_recipe_common.py`; `checks/community_pack_validate/_shared.py`)
    that both halves import — never a back-import from the sibling broken by
    lazy in-function imports (which double-executes the CLI under a second
    module name and forks exception identities). The original file stays a
    back-compat facade re-exporting the moved names; new code imports from
    the new module. Topic-module packages under `scripts/checks/` are
    direct-script-invocation only (PEP 420 namespace package, relative
    imports; `python -m` is not a supported entry).
25. **The recipe document lives in mep-meta (pre-F6.3).** `$RUNNER_TEMP`
    dies with the job, so the `<!-- mep-meta -->` JSON block carries the
    full assembled `recipe` object (alongside `deps`, `recipe_hash`,
    `recipe_ok`) whenever `recipe_status == 'present'`. The catalog
    generator copies `recipe`/`recipe_hash` verbatim and never re-assembles.
26. **Catalog shape (reconciles §3's sketch with the PRD's F6.3 row).**
    `docs/community-packs.json` is an MEI document, `mei: "1.1.0"`, with the
    index fields of MEI §2.1 (`name` "MesenCE community packs", `maintainer`
    `sbihaiko`, `updated` = generation date). One `packs[]` entry per board
    item in an accepted Status, built from the Project fields (Pack URL →
    `url`, Pack Hash → `sha256` — §18 precedence — ROM SHA1 → `rom.sha1`,
    Game → `game`), the issue (`issue` number, `game`/`system` from the Form
    fields, `license` from `external_assets_license` or `"unknown"`) and the
    mep-meta block (`deps[]`, `recipe`, `recipe_hash`, `recipe_ok`, `verdict`,
    `validated_at`, `labels`). MEI **v1.1** amendments: (a) new optional
    `kind` ∈ {`mep`, `hd-legacy`}; for `hd-legacy` entries `version` and
    `mep` are omitted; `license` is SHOULD for any `kind` (§34); (b) `rom.sha1` MAY be
    absent (clients only auto-match entries that carry it); (c) an entry MAY
    carry `deps[]`/`recipe` referencing third-party artifacts by URL + hash,
    each dep SHOULD carry `license` and the client shows it — or "not
    declared" — before install (PRD row, §34); `deps[]` is copied from
    mep-meta's embedded `recipe.sources.deps` (the licence-bearing shape),
    never from mep-meta's top-level display-only `deps` summary; (d) `catalog_version` is not used — `mei` is the
    version. Golden `docs/specs/golden/mei/manifest.json` bumps to 1.1.0 and
    gains one `hd-legacy` entry with `deps`/`recipe`; MEI-v1.md §2.2 gains
    the v1.1 rows. Unknown-field tolerance (MEI §2.2) keeps 1.0 readers safe.
27. **Generation and validation seams.** `generate_community_pack_catalog.py`
    writes the JSON next to the Markdown in the same run (the existing
    `community-pack-catalog.yml` commits both files); the Markdown table
    gains an "External assets" marker column (`yes` when the entry has
    `deps`). `validate-specs.py` gains `validate_mei_catalog()` that validates
    the golden AND, when present, the committed `docs/community-packs.json`
    against the same v1.1 rules — offline, no `gh`. mep-meta parsing is a
    pure function over the comment body (`<!-- mep-meta -->` + fenced JSON)
    with its own tests; a malformed block skips the entry's recipe data and
    logs, never aborts the whole catalog.

28. **MEI entry rules have one owner (F6.3b).** `validate-specs.py` (not
    importable — hyphenated name) and `generate_community_pack_catalog.py`
    currently mirror the v1.1 entry constraints by hand; two of F6.3's four
    revision cycles were drift repairs on that mirror. F6.3b extracts the
    constraint set (`MEI_SYSTEMS`, hash regexes, kind-conditional required
    fields, `mei_entry_conforms`) into a stdlib-only leaf
    `scripts/mei_rules.py` imported by both; the generator runs every
    assembled entry through it before writing.
29. **`kind` derivation.** `kind` is derived from the mep-meta `verdict`
    (versioned in the issue timeline) with the Project Status literal as the
    fallback only; the Status→kind mapping is one constant shared by the
    generator and `community-pack-validate.yml`'s label/verdict step, guarded
    by a parity check in the `verify_mep_fallback_constant_parity.sh` style.
    An unmapped Status yields no entry (§32), never a `kind`-less one.
    *Amended 2026-08-28 (F6.3b):* mep-meta v1 carries an optional `kind`
    written by `apply-verdict`; its allowed values are exactly
    `mei_rules.MEI_KINDS`. `mei_rules.resolve_kind` uses a valid mep-meta
    `kind` first, ignores unrecognised values, falls back to
    `STATUS_TO_KIND[status]`, and returns `None` when neither yields one — a
    pre-change comment without `kind` therefore still resolves via Status.
    mep-meta-over-Status is intentional (the comment is versioned; the board
    literal is live-editable).
30. **Provenance fields are spec'd, not namespaced.** `issue`, `verdict`,
    `validated_at`, `labels`, `recipe_hash`, `recipe_ok` are listed in MEI
    §2.2 as optional (MAY, v1.1) non-normative provenance fields with their
    types (done 2026-08-28). Namespacing under a `provenance` object was
    rejected: nothing gains from the reshape and it would break the first
    consumer for free.
31. **Versioning precedent.** MEI v1.1 downgrades `rom.sha1` to optional for
    every `kind`, deliberately and not gated on the declared `mei` minor —
    recorded in MEI §2.3 (done 2026-08-28). Absent `kind` means `mep` with the
    full 1.0 field set; only explicit `hd-legacy` relaxes `version`/`mep`.
32. **Generator is the gatekeeper.** An accepted board item that cannot
    produce a spec-valid MEI entry is omitted from `packs[]` with a warning
    naming the issue; the Markdown row still lists it. Recorded in MEI §2.3
    (done 2026-08-28); `validate_mei_catalog()` stays strict.
33. **Fence length guard (F6.3b, workflow side).** `json.dumps` does not
    escape backticks, so a submitter-supplied ``` inside `hints`/`license`
    truncates the fixed three-backtick mep-meta block (data loss, not
    forgery — the prefix fails to parse and `parse_mep_meta` returns
    `None`). One format rule for both the mep-meta writer and the
    ```mep-recipe reader in `mep_recipe.py`: emit the shortest backtick run
    longer than any run in the payload; readers accept a fence of 3+
    backticks and match the closing run by length.
    *Shipped 2026-08-28 (F6.3b + fast-follow):* `mep_recipe_common.choose_fence`
    / `find_fenced_block` are the rule; the workflow writer, `mep_recipe.py`'s
    reader and `mep_meta_parser.py` all use them (the parser's fixed regex was
    the asymmetric leftover the auditor caught).
36. **Convergence slices are not parallelisable across the files they
    unify.** F6.3b's two real defects (fence rule asymmetric in
    `mep_meta_parser.py`; a second `mei_entry_conforms` in
    `mei_catalog_entry.py`) came from per-task file allowlists that split a
    single-source-of-truth rule across tasks. A slice whose purpose is to
    collapse duplicates puts the leaf and every call site in one task's file
    list, even if that task is larger. Critic report volume is not issue
    count (8 reports → 3 concerns): dedup before scheduling work.
34. **`license` is optional everywhere (user decision, 2026-08-28).**
    MEP-v1 §3.1 `license` is SHOULD (was MUST): absent reads as
    `NOASSERTION`, hosts never refuse a pack for it and surface "not
    declared". `mep_lint.py` warns instead of erroring; `validate-specs.py`
    only type-checks it when present; `MepPack.cpp` reads it with the
    `"unspecified"` default `MepPackManager` already uses for sibling
    folders. MEI §2.2 entry `license` and §2.3 dep `license` are SHOULD too;
    clients show "not declared" in place of a value. MEP-recipe-v1 already had
    it as SHOULD (default `NOASSERTION`), so recipe assembly is unchanged.
35. **File-size gate vs declared-file scope.** For every task whose
    deliverable exceeds ~2× the per-file cap (generator scripts, Core
    modules, anything) the 200-line-per-file threshold wins: a task that will need a module split
    pre-declares the extracted files in its file list so the scope critic
    cannot reject the split (F6.3 lost a cycle folding a correct split back).
    Decompose owns this: it pre-declares the extracted modules, or a glob
    such as `Core/Shared/EnhancementPacks/MepRecipe*.{h,cpp}`, in the task's
    file list (F6.4a lost two cycles to the same ping-pong on Core code).
    Two small checkers covering one script from different angles are fine;
    no convention slice is spent on it.

37. **F6.4 is split at the network boundary (2026-08-28).** `Core/` has no
    HTTP client and gains none (no libcurl dependency); the UI already uses
    `HttpClient` (`UpdatePromptViewModel`). So §4 is delivered as two
    slices. **F6.4a — Core installer, offline:**
    `Core/Shared/EnhancementPacks/MepRecipeInstaller.{h,cpp}` is a fixed
    interpreter of the four ops working only on local files: input = a
    recipe document (the MEI entry's `recipe`, JSON via `Utilities/JsonReader`),
    the primary zip path and a map dep-id → local path (possibly incomplete);
    it verifies every sha256 against the recipe (mismatch aborts with an
    error string), applies `policy.apply_patch_only_if_complete` (missing
    dep → patch and its dependent rename/rewrite-paths withheld, textures
    still applied, `withheld` reported), writes `pack.json` and
    `.mep-install.json` (`recipe_hash`, `source.sha256`, dep hashes,
    `installed_at`) into the ADR-0040 central per-ROM folder, and skips
    with `[MEP] recipe unsupported` on an unknown op or `recipe` version.
    `EnhancementPackConfig` gains `bool AutoInstallCommunityPacks = true`
    (stored; consulted by F6.4b). Verification is headless in
    `scripts/core_unit_tests.cpp`: the golden `mep-recipe` fixture installed
    by the C++ installer equals `mep_recipe.py apply` byte-for-byte (a
    Python-side helper dumps both trees), hash mismatch aborts, missing dep
    withholds the patch. **F6.4b — UI fetch and prompt (C#):** catalog fetch
    with ETag/If-None-Match cached under the MEP `.cache`, No-Intro sha1
    match, download of `source.url` within the CI host allow-list (shared
    constant, parity-checked against `community-pack-validate.yml`),
    downloads-cache lookup by sha256, prompt listing `hints` + licence for
    `user_supplied` deps, then an interop call into the F6.4a installer;
    reinstall when `source.sha256` changed; UI notice when the patch is
    withheld. Auto-install default per §4 applies in F6.4b.

38. **`AutoInstallCommunityPacks` default and consent (F6.4a audit).** The
    setting ships `true` in F6.4a as storage only — nothing reads it yet. §4's
    default stands, but F6.4b MUST ship, in the same slice, the settings
    toggle and a first-run consent prompt before the first automatic
    download; until F6.4b lands no code path installs anything.
39. **Two interpreters, one normative reference.** `scripts/mep_recipe.py`
    is the normative MEP-recipe-v1 interpreter; `MepRecipeInstaller`/
    `MepRecipeOps` (C++) re-derive it, including `mep_lint.py`'s root
    discovery. Any recipe-spec change lands on both sides in the same
    commit. Enforcement is the golden-parity test in
    `scripts/core_unit_tests.cpp` (Bloco E) over the real-bytes fixture set
    `docs/specs/golden/mep-recipe/fixture/` generated deterministically by
    `scripts/gen_mep_recipe_fixture.py` (committed zips are tiny, fixed
    timestamps, `ZIP_STORED`; `test_gen_mep_recipe_fixture.py` proves
    regeneration is byte-identical). Growing that set to the discovery edge
    cases (wrapped subfolder, nested top-level zip, ADR-0120/0121 fallback)
    is a follow-up (**F6.4c**, after F6.4b). `SHA256::GetHash(path)` returns
    `""` on an unopenable file so verification can never pass on a missing
    artifact (fixed 2026-08-28; `sha1` keeps its opportunistic contract).
40. **Critic false positives on Core code.** F6.4a's T4 stagnated for six
    cycles on "high-entropy token literal" findings that were a variable
    named `token`, SHA-256 known-answer vectors and chained ternaries — the
    work was complete (79/79 tests) and was recovered from the orphaned
    branch via `git fsck --unreachable`. When a critic finding names no file
    and the actor has already answered it, the run operator merges the task
    branch by hand instead of burning cycles.

41. **Allow-list packaging (F6.4b audit, PRIORITY 1).**
    `scripts/pack_host_allowlist.json` stays the single source. `UI/UI.csproj`
    embeds it as an `EmbeddedResource` (`LogicalName`
    `Mesen.pack_host_allowlist.json`, `Include="../scripts/pack_host_allowlist.json"`)
    and the service loads it via `CommunityPackHostAllowlist.LoadFromStream`
    from the assembly manifest — never from a repo-relative path, which does
    not exist in a published app. A check under `scripts/checks/` asserts the
    csproj references exactly that path. `MatchHost` mirrors
    `fetch_pack.py:match_host` (HTTPS-only, exact netloc, `path_contains_any`).
42. **Wire shape authority.** `docs/specs/MEI-v1.md` is normative; §3's
    sketch (`source.{url,sha256}`, `rom.sha1` array) is superseded by the
    real MEI shape: `url`/`size`/`sha256` at the entry top level, `rom.sha1` a
    scalar, `mei`/`name`/`packs` envelope. Wherever this ADR says "catalog
    `source.sha256`" read "the entry's `sha256`"; `.mep-install.json` keeps
    the key name `source.sha256` for the recorded value.
43. **Reinstall policy vs user-owned state (PRIORITY 3).** Automatic
    reinstall happens only when (a) the target folder holds a
    `.mep-install.json` written by the installer, (b) its `source.sha256`
    differs from the catalog entry's `sha256`, and (c) the container is not
    in `DisabledPacks`. A folder without the stamp is user-owned and is never
    overwritten (UI notice offering a manual install instead); a disabled
    pack is skipped silently.
44. **UI.Tests compiles UI/Logic under the same AOT contract.**
    `UI.Tests.csproj` sets `JsonSerializerIsReflectionEnabledByDefault=false`
    and `IsAotCompatible=true` like `UI.csproj`, so a UI/Logic file that
    relies on reflection-based JSON fails `dotnet test` (done 2026-08-28).
45. **`recipe` travels opaque.** `CommunityPackCatalogEntry.Recipe` is a
    `JsonElement?`; the service serialises it back to text (`GetRawText()`)
    and hands it to `InstallMepRecipe` unchanged — the UI never interprets a
    recipe (done 2026-08-28).
46. **Downloads cache = `<EnhancementPackFolder>/.cache/downloads/`**
    (ADR-0040 scratch space, safe to delete). Downloaded primaries and
    user-supplied deps are looked up there by sha256; the `user_supplied`
    prompt names this folder as the drop location.
47. **Interop encoding for `InstallMepRecipe`.** The dep-id → path map
    crosses the boundary as UTF-8 text, one `id<TAB>path` row per line
    (`EmuApiWrapperMep.cpp`, shipped in F6.4b/T5, same row grammar as
    `GetMepPackList`); the recipe crosses as raw JSON text; the result comes
    back through the existing char* out-buffer convention. Recorded here so
    the choice is not re-litigated; JSON-object encoding was the runner-up.
48. **Interop registries are exempt from the 200-line cap.** `UI/Interop/EmuApi.cs`
    and `InteropDLL/EmuApiWrapper.cpp` are flat one-declaration-per-line
    registries; new export families go in sibling files
    (`EmuApiWrapperMep.cpp` precedent) rather than splitting the registries.
49. **UI-only settings.** A field in `EnhancementPackConfig` (C#) that no
    native code reads (`CommunityPackAutoInstallConsentGiven`) is not
    mirrored into `InteropEnhancementPackConfig`; `AutoInstallCommunityPacks`
    stays mirrored because `SettingTypes.h` declares it. The rule: mirror iff
    a native consumer exists.

50. **Client download trust contract (F6.4b-2 audit).** Every HTTP GET the
    client issues for community packs — the catalog included — goes through
    one primitive, `UI/Services/CommunityPackDownloader.GetAsync`: redirects
    are never followed automatically, each hop is re-checked against the
    embedded allow-list (`MatchHost`, https only, 5-hop cap, mirroring
    `fetch_pack.py`'s `open_validated`), and the body is capped in bytes
    before it is buffered (300MB for artifacts = the CI validator's ceiling,
    16MB for the catalog). The catalog URL stays a compile-time constant
    bound to this fork, but it is no longer exempt from `MatchHost`. DNS /
    private-range checks remain CI-only by design: the allow-listed hosts are
    public CDNs and a client cannot pin DNS the way the runner does. The
    declared `sha256` doubles as the `.cache/downloads/` file name, so it is
    validated as 64 hex chars before touching the filesystem.
51. **§38 gate ownership and per-session idempotency.**
    `CommunityPackInstallService` (the ROM-load hook) owns the consent gate:
    it evaluates `CommunityPackConsentState` — showing the first-run dialog
    via `EnhancementPacksWindow.EnsureCommunityPackAutoInstallConsent` — and
    a per-process `HashSet` of attempted ROM sha1s *before* any network
    call; `CommunityPackInstallCoordinator`'s own `NeedsConsent` outcome is
    documented defense in depth, not the primary gate. The
    `.mep-install.json` stamp (§43) remains the cross-session gate. Power
    cycles are not new loads (an installed pack is applied through one).
52. **Container name is host-free.** The sanitization of the catalog's
    submitter-influenced `name`/`game` into a folder name and `DisabledPacks`
    key lives in `UI/Logic/CommunityPackContainerName.cs` (pinned by
    UI.Tests); `CommunityPackInstallCoordinator.ResolveOutFolder` is the
    stateful partner that roots it under `EnhancementPackFolder` and asserts
    it stayed there (ADR-0127 header rule).
53. **Three-layer rule for `UI/`.** `UI/Logic` = host-free decisions (BCL
    only, dual-compiled into UI.Tests); `UI/Services` = host/network
    orchestration (`HttpClient`, `EmuApi`, file I/O allowed); `UI/Windows`/
    `UI/ViewModels` = presentation. `scripts/verify-ui-logic-firewall.sh`
    enforces it in both directions: `UI/Logic/*.cs` never references
    `Mesen.Services`/`HttpClient`, and `HttpClient` under `UI/` is confined
    to `UI/Services/*.cs` plus the pre-existing `UpdatePromptViewModel`.
54. **Consent dialog placement — decided, stop re-raising.** The first-run
    Yes/No dialog is a public static helper on `EnhancementPacksWindow`
    (the window that owns the related settings and message-box usage),
    called from the Services layer via the UI dispatcher; the decision
    itself stays in `UI/Logic/CommunityPackConsentState`. Moving the
    presenter into `UI/Services/` would put Avalonia into the Services layer
    for no gain; revisit only if more prompts accumulate (per-pack consent).
55. **Closed without action (F6.4b-2 audit).** (a) `Link=` on the embedded
    allow-list: not needed — `LogicalName` is the only handle the code uses
    and the checker pins the `Include`/`LogicalName` pair; (b) a
    build-level (link-symbol) proof that `Core/` has no HTTP: the comment-
    stripping grep in `verify_core_no_http_client.sh` is proportionate to a
    tree that has no HTTP today; (c) moving the reinstall `Directory.Delete`
    into a Core "replace mode" of `MepRecipeInstaller::Install` (temp folder
    + atomic swap): deferred — the client-side delete is bounded by §52's
    sanitization and the rooted-path assertion; reopen if the installer
    grows a second mutating caller.

**F6.4b-2 shipped (2026-08-28, run `119e1031a25f`).** T1 (fetcher) stagnated
on two *real* critic findings (null dep id, sha256-as-path) — recovered per §40
and fixed by hand; T5 (`CommunityPackInstallService` + `MainWindow` hook) was
skipped for depending on T1 and written by hand; the auditor's PRIORITY
findings became §50–§53 and were implemented in the same commit. Remaining:
F6.4c, F6.5.

**F6.4b second half (2026-08-28).** Run `2ef26ba839d1` landed the UI/Logic
decision classes, DTOs and the interop export (T1–T5; T1 recovered per §40 and
fixed for the empty-body 200). The remaining run — **F6.4b-2** — ships, in one
task file list: `UI/Services/CommunityPackCatalogFetcher.cs`,
`UI/Services/CommunityPackInstallCoordinator.cs`,
`UI/Services/CommunityPackInstallService.cs`, the `UI.csproj` embedded
allow-list + its check (§41), `CommunityPackAutoInstallConsentGiven` in
`EnhancementPackConfig.cs`, the Settings checkbox and consent dialog in
`EnhancementPacksWindow`, and the ROM-load hook that triggers the service.

**Slicing (after three failed F6.2 runs, 2026-08-28).** F6.2 is executed as
two dev-squad runs: **F6.2a** — Issue Form fields, `assets:external` label
creation, authoring-doc section, Issue-Form/labels verifiers, and the
`.github/AGENTS.md` Local Contracts entry for §9; **F6.2b** — the
`community-pack-validate.yml` steps (classify schema narrowing, assembly
step + `mep_recipe.py` sources-assembly helper, gate, `apply-verdict`
expression and `external` branch, mep-meta upsert) plus the extended
workflow verifier.

**F6.3b — catalog hardening (2026-08-28, after F6.3).** §28 (`scripts/mei_rules.py`
leaf + generator self-check), §29 (`kind` from mep-meta `verdict`, one shared
Status mapping + parity check), §33 (fence length guard in
`community-pack-validate.yml`'s mep-meta writer and `mep_recipe.py`'s
```mep-recipe reader), and the §35 split of
`generate_community_pack_catalog.py` into MEI entry assembly (`scripts/mei_catalog_entry.py`), Markdown
rendering (`scripts/community_pack_markdown.py`) and the fetch/orchestration
that stays behind — file list pre-declared. Runs before F6.4.
