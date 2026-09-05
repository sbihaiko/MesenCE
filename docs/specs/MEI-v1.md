# MEI v1.4 — MesenCE Enhancement Index

**Status:** v1.4 (stable) — 1.1: `kind`, optional `rom.sha1`, `deps[]`, `recipe`; 1.2: additive `rom.sha1s[]` (§2.4); 1.3: additive `pack_id`, `content_id`, `votes` (§2.5); 1.4: additive `errata` (§2.6) ·
**License for this spec:** CC0-1.0 (public domain) ·
**Versioning:** semver — new optional field = minor; semantic change = major ·
**Golden file:** [`golden/mei/manifest.json`](golden/mei/manifest.json) ·
**Validation:** `scripts/validate-specs.py`

The keywords MUST, MUST NOT, SHOULD, and MAY follow RFC 2119.

## 1. Scope

MEI is the **discovery** manifest for MEP packs: a static `manifest.json`
(hostable on any HTTP server or GitHub repository) listing packs with name,
game, No-Intro hash, artifact URL, and checksum. Indexes are **federated**:
anyone MAY publish an MEI and point the emulator at it; a project's official
index is just another MEI, with no protocol privilege.

An index MUST list only content its maintainer is able to distribute
(presets, mappings, licensed original compositions); third-party derivative
content circulates outside the index, in its own hubs.

## 2. `manifest.json`

```json
{
  "mei": "1.4.0",
  "name": "Índice oficial MesenCE",
  "maintainer": "sbihaiko",
  "updated": "2026-08-24",
  "packs": [
    {
      "name": "After Burner — Studio FM tuning",
      "version": "1.2.0",
      "game": "After Burner (World)",
      "system": "sms",
      "rom": {
        "sha1": "2A4E126D0286BEA0BF503C80A12352C57539F76B",
        "crc32": "1C851C7E",
        "sha1s": ["7B1F0E2C3D4A5B6C7D8E9F0A1B2C3D4E5F6A7B8C"]
      },
      "mep": "1.0.0",
      "license": "CC0-1.0",
      "url": "https://example.org/packs/after-burner-studio-1.2.0.zip",
      "size": 18342,
      "sha256": "a3f1c2… (64 lowercase hex chars of the .zip artifact)",
      "pack_id": "after-burner-studio",
      "content_id": "1d4184aaaea725c3aa9a5101b76c8e433508b48cbad561f39003dabb1db84d3f",
      "votes": 3
    },
    {
      "kind": "hd-legacy",
      "name": "Zelda HD Pack — community submission",
      "game": "Legend of Zelda, The (USA)",
      "system": "nes",
      "rom": { "crc32": "6C648F63" },
      "license": "unknown",
      "url": "https://github.com/example/zelda-hd/releases/download/v1/zelda-hd.zip",
      "size": 20480,
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "deps": [
        {
          "id": "audio",
          "url": "https://example.org/audio/zelda-hd-ogg.zip",
          "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
          "size": 4096,
          "license": "CC0-1.0"
        }
      ]
    }
  ]
}
```

The second entry above is a `kind: "hd-legacy"` example: no `version`/`mep`
(the original submission predates MEP and has no pack manifest to mirror),
`license: "unknown"` (the submitter did not declare one), no `rom.sha1`
(only a legacy `crc32` is known), and a `deps[]` array pointing at a
third-party audio replacement the client must download and confirm
separately (§2.3). The first entry's `rom.sha1s` lists an additional No-Intro
hash (another revision of the same game) that the same pack also matches
(§2.4, v1.2). That first entry also carries the v1.3 identity fields:
`pack_id` (its declared MEP `id`), `content_id` (the ADR-0139 hash of the loaded tree — not the
`sha256` of the wrapper) and `votes` (community 👍 count) (§2.5).

### 2.1 Index fields

| Field | Requirement | Semantics |
|---|---|---|
| `mei` | MUST | MEI spec version (semver); an unknown major MUST be rejected |
| `name` | MUST | human-readable name of the index |
| `maintainer` | SHOULD | person/entity responsible |
| `updated` | SHOULD | ISO 8601 date of the last update |
| `packs` | MUST | list (possibly empty) of entries |

### 2.2 Fields of each pack

| Field | Requirement | Semantics |
|---|---|---|
| `kind` | MAY (v1.1) | `"mep"` (default when absent) or `"hd-legacy"`; see §2.3 |
| `name` | MUST | mirrors the artifact's `pack.json` (or the submission title for `hd-legacy`) |
| `version` | MUST unless `kind: "hd-legacy"` | mirrors the artifact's `pack.json` |
| `game`, `system` | MUST | target game and system (`system` values as in MEP §4) |
| `rom` | MUST | object; `sha1` (40 uppercase hex, No-Intro range from MEP §4) MAY (v1.1) be absent, optionally `crc32`; `sha1s` MAY (v1.2) list additional No-Intro SHA1s of other revisions/dumps of the same game that the same pack also matches — see §2.4 |
| `mep` | MUST unless `kind: "hd-legacy"` | MEP spec version of the artifact |
| `license` | SHOULD | SPDX of the content, or `"unknown"` when the submitter declared none (any `kind`, v1.1); an absent field is read as `"unknown"` |
| `url` | MUST | URL of the `.zip` artifact — **HTTPS required** |
| `size` | SHOULD | size of the artifact in bytes |
| `sha256` | MUST | SHA-256 of the artifact, 64 hex (case-insensitive on read; producers SHOULD write lowercase) |
| `deps` | MAY (v1.1) | list of third-party artifacts the pack references; see §2.3 |
| `recipe` | MAY (v1.1) | MEP-recipe-v1 document assembled for `deps`; see §2.3 |
| `pack_id` | MAY (v1.3) | product identity of the pack across revisions (ADR-0140/0143): lowercase slug, `owner/repo[:game-slug]` or `issue-N`; see §2.5 |
| `content_id` | MAY (v1.3) | ADR-0139 canonical hash of the pack's loaded tree, 64 **lowercase** hex; the client's update trigger (ADR-0141); see §2.5 |
| `votes` | MAY (v1.3) | non-negative integer, community 👍 count of the submission; non-normative like `issue` — a sort key, never an install decision; see §2.5 |
| `errata` | MAY (v1.4) | reviewed known-missing manifest targets of this exact artifact, declared by the index maintainer's validation and never by the pack's author; non-normative — never an install decision, and clients SHOULD display it; see §2.6 |
| `issue`, `verdict`, `validated_at`, `labels`, `recipe_hash`, `recipe_ok` | MAY (v1.1) | producer provenance: issue number (integer), triage verdict string, ISO-8601 validation date, list of label strings, SHA-256 hex of the `recipe` document, boolean recipe dry-run result. Non-normative — clients MUST ignore them for install decisions and MAY display them |

Unknown fields MUST be ignored.

### 2.3 `kind`, `rom.sha1`, `deps[]` and `recipe` (v1.1)

MEI v1.0 assumed every listed pack was a complete, self-contained MEP
artifact with a known No-Intro ROM hash. v1.1 adds a `kind` discriminator so
an index MAY also list packs submitted before MEP existed, or packs that
split part of their content into third-party artifacts:

- `kind: "mep"` (the default, used when the field is absent) — the entry
  behaves exactly as in v1.0: `version`, `mep` and `rom.sha1` are expected.
- `kind: "hd-legacy"` — a community submission accepted only as a plain
  HD/texture pack (MEP-v1 §5.2 "Aceito parcial (HD Mesen)"), with no MEP
  `pack.json` to mirror. For these entries `version` and `mep` MAY be
  omitted (`license` MAY be `"unknown"` for any `kind`, §2.2).
- `rom.sha1` MAY be absent regardless of `kind` (an entry without one is
  still listable and installable, just not hash-matchable). This is a
  deliberate v1.1 downgrade of a v1.0 MUST for every `kind`, not gated on
  the declared `mei` minor: a v1.0 document stays valid under v1.1 rules, and
  the only opt-in relaxation is the explicit `kind: "hd-legacy"` (absent
  `kind` means `mep`). Auto-matching an entry against a loaded ROM is a
  hash match first (`rom.sha1`, and `rom.sha1s[]` from v1.2 — §2.4). When no
  entry's hash matches, a client MAY additionally auto-match by title — the
  ROM display name and the entry's `game` identify the same title after
  stripping trailing region/dump tags (so "Legend of Zelda, The (USA)"
  matches "The Legend of Zelda (USA)") — and this title fallback applies to
  every entry regardless of whether it carries a `sha1` (ADR-0146; an entry
  with `rom: {}` still auto-installs by identity). Such an optimistic match
  is self-healing (ADR-0145 health signal) and IPS/patches stay hash-gated
  (ADR-0044): they apply only on an exact hash match.
- `deps` (when present) is a list of objects, each SHOULD carry `license`
  (SPDX id or a short declared-licence string, mirroring MEP-recipe-v1 §3.3)
  and SHOULD carry `url`/`sha256`/`size` identifying the third-party
  artifact. Clients MUST show each dep's `license` — or that none was
  declared — before downloading or installing it (mirrors MEI §3's trust
  obligations). Index producers copy `deps[]` from the recipe's
  `sources.deps` (the licence-bearing shape), never from a stripped summary.
- An index producer MUST omit an entry it cannot make conformant to this
  section (missing `url`/`sha256`, unresolvable `kind`) rather than emit an
  incomplete one; it SHOULD log the omission naming the source item. A
  committed index is therefore valid by construction and its validator stays
  strict.
- `recipe` (when present) is the MEP-recipe-v1 document that assembles
  `deps` and the primary artifact into an installable pack; clients that do
  not implement the recipe interpreter MUST ignore it and MAY still list
  the pack, but MUST NOT attempt to install `deps` without it.

Unknown fields MUST still be ignored (§2.2), so a v1.0 client sees a v1.1
entry with `kind`/`deps`/`recipe` stripped and, when `version`/`mep`/
`rom.sha1` happen to be present, otherwise behaves as before.

### 2.4 `rom.sha1s[]` (v1.2)

One pack often serves more than one No-Intro dump of the same game — a
later revision (Castlevania (USA) Rev A), a regional variant with identical
CHR data, or an alternate dump (Ninja Gaiden (USA) alt). `rom.sha1` still
names the primary target; v1.2 adds an **additive** list of exact-match
alternates:

- `rom.sha1s` (when present) is a JSON array of strings, each a 40-uppercase-
  hex No-Intro SHA1 (same shape as `rom.sha1`) of another ROM the same
  artifact also matches. Producers MUST NOT repeat `rom.sha1` inside
  `sha1s`, and SHOULD NOT emit an empty array (omit the field instead).
- Matching a loaded ROM against an entry is `rom.sha1` first, then any
  `rom.sha1s[]` element, compared case-insensitively. A hit on either is an
  **exact** hash match and carries the same trust as a `rom.sha1` hit —
  including for hash-gated content such as IPS patches (ADR-0044).
- `sha1s` is a plain exact-match list. It is **distinct from** the
  optimistic same-title fallback of §2.3 (ROM display name vs `game`) and
  from the optimistic texture/BPS matching of ADR-0145, both of which apply
  a pack to a ROM whose hash the entry does *not* list; `sha1s` never
  widens those mechanisms, it only adds hashes the producer has verified.
- `sha1s` MAY be present with `rom.sha1` absent (`rom.sha1` MAY be absent
  for every `kind`, §2.3); it then supplies the entry's only exact hashes.
  An entry with neither `sha1` nor a non-empty `sha1s` has no exact hash
  match and reaches a ROM only through the §2.3 title fallback (ADR-0146),
  i.e. never for hash-gated content (ADR-0044).
- Clients unaware of the field ignore it (§2.2) and keep matching on
  `rom.sha1` alone; a v1.1 document stays valid under v1.2 rules. The
  field is recognized by its shape, not by the declared `mei` minor: a
  v1.2-aware client SHOULD honor `sha1s` in a document that still declares
  `"mei": "1.1.x"` (the reference client and verifiers do not gate on the
  declared minor). Producers emitting `sha1s` SHOULD nevertheless declare
  `"mei": "1.2.0"`, per the header's versioning rule (new optional field = minor).

The reference producer (`scripts/generate_community_pack_catalog.py`, via
`scripts/rom_target.py`) fills `sha1s` from the No-Intro alternates known
for the resolved title; the reference client
(`UI/Logic/CommunityPackCatalogMatcher.cs`) and the headless verifier
(`scripts/verify_community_install_from_zero.py`) consume it as above.

### 2.5 `pack_id`, `content_id` and `votes` (v1.3)

`sha256` identifies a download wrapper, not a pack: two zips of one tree are
two `sha256`s, and one zip carrying several revisions (`/revalidate`) is one
`sha256` with different contents over time. v1.3 adds three **additive**
per-pack fields so a client can tell "a revision of the pack I have" from "a
competing pack" without re-hashing anything (PRD Part B §3.2–§3.6):

- `pack_id` (when present) is a non-empty lowercase string naming the
  **product** — every revision of one pack shares it. Its shape is one of
  the ADR-0140 catalog sources, first match wins: the pack's declared MEP
  `id` slug (`[a-z0-9][a-z0-9-]{2,63}`, MEP-v1 §3.1); else, for
  github.com/codeload/raw pack URLs, the origin `owner/repo` lowercased,
  suffixed `:game-slug` when the game is known (ADR-0143: one slot per
  game, e.g. `liquidzgit/hdnes:ice-climber`); else `issue-N` of the
  accepted submission. The client-only `local:<container>` fallback
  (ADR-0140 source 4) is never written to an index. An index MUST list at
  most one live entry per `pack_id` (the PRD Part B §3.6 slot ADR-0141
  implements; history stays out of the index) — a producer rule the
  reference generator enforces (`select_catalog_rows`); §5's per-entry
  shape checks do not cover it.
- `content_id` (when present) is the ADR-0139 canonical hash of the pack
  tree the host actually loads (excluding, per ADR-0139: wrapper metadata,
  any path with a `__MACOSX` or `screenshots` segment, `.DS_Store`, any
  basename starting with `README`, and the `pack.json` `version` key;
  recipe composite when a `recipe` is present): exactly **64 lowercase hex digits**, the hasher's
  `sha256().hexdigest()`. Same loaded files ⇒ same `content_id`;
  wrapper-only repack ⇒ same `content_id`; any loaded-file change ⇒ new
  `content_id`. Unlike `sha256` it is not case-insensitive on write —
  producers MUST emit lowercase (the reference client compares it
  case-insensitively, but other clients need not).
- `votes` (when present) is a JSON integer ≥ 0: the community 👍 count of
  the submission issue at generation time. It is non-normative, like
  `issue`: a client MAY use it to **order** competing packs (most-👍 first,
  PRD Part B §5 — the reference Player picker sorts by `votes` descending,
  then name) and MUST NOT use it to auto-pick, install or reject anything.
  A non-integer (string, float, boolean) is a malformed document.
- Producers emit each field only when known and never empty: no `pack_id`
  when no source resolves, no `content_id` when the validator did not
  record one, no `votes` when the count is unavailable. Since every
  accepted community submission has an issue number, the reference catalog
  carries all three on every row.
- Client rules. `pack_id` groups revisions: a per-ROM preference is stored
  as a `pack_id` (ADR-0140), and two entries with different `pack_id`s for
  one ROM are competing packs the player may be asked to choose between,
  whereas one `pack_id` is never offered as a 1.0-vs-1.2 choice
  (ADR-0141). `content_id` — not `sha256` — is the **update trigger**: a
  client that installed an entry reinstalls when the slot's `content_id`
  differs from the one it recorded, treats a `sha256`-only change as a
  wrapper-only repack (no reinstall), and does not downgrade when its
  installed semver is higher (ADR-0141). An installed local container whose
  `content_id` equals an entry's is the same pack and adopts that entry's
  `pack_id` (PRD Part B §5 merge). An entry lacking these fields is still
  listable and installable; a client then falls back to `sha256`/container
  identity as in v1.2.
- Clients unaware of the fields ignore them (§2.2); a v1.2 document stays
  valid under v1.3 rules. The fields are recognized by their shape, not by
  the declared `mei` minor: a v1.3-aware client SHOULD honor them in a
  document that still declares `"mei": "1.2.x"` (the reference client does
  not gate on the minor). Producers emitting them SHOULD nevertheless
  declare `"mei": "1.3.0"`, per the header's versioning rule (new optional
  field = minor).

The reference producer is `scripts/pack_id_rules.py`
(`resolve_pack_id`, `apply_mei_identity`, called from
`scripts/mei_catalog_entry.py`), reading `content_id` from the submission's
mep-meta as written by `scripts/mep_content_id.py` (golden
[`golden/mep-content-id.json`](golden/mep-content-id.json)); the shapes live
in `scripts/mei_rules.py` (`PACK_ID`, `CONTENT_ID_HEX`,
`mei_identity_field_errors`). Reference consumers:
`UI/Logic/CommunityPackCatalog.cs` (deserialization, each field nullable),
`UI/Logic/CommunityCatalogUpdateDecision.cs` (`content_id` trigger),
`UI/Logic/PackPreferenceResolver.cs` (`pack_id` preference and `content_id`
merge) and the Player picker in `UI/ViewModels/MainWindowViewModel.cs`
(`votes` ordering).

### 2.6 `errata` (v1.4)

An entry MAY carry an `errata` object recording manifest targets the listed
artifact does **not** ship, which the index maintainer's validation checked and
declared:

```json
"errata": {
  "known_missing": [
    {
      "manifest": "hires.txt",
      "tag": "background",
      "target": "selectscreen.png",
      "reviewed_in": "https://github.com/sbihaiko/MesenCE/issues/139"
    }
  ],
  "declared_by": "MesenCE validation"
}
```

- `known_missing` MUST be a non-empty list; each item MUST carry `manifest`,
  `tag` (`"img"` or `"background"`) and `target` as exact names — no wildcards
  and no line numbers — and SHOULD carry `reviewed_in`, the URL where the
  declaration was reviewed. `declared_by` names the source of the declaration.
- The object is **provenance, not an install instruction**: nothing in the
  artifact is added, removed or rewritten because of it, so an entry's
  `content_id` is the same with or without one. A client MUST NOT treat it as
  a reason to refuse an install, and SHOULD surface it to the user attributed
  to `declared_by` — a known gap presented as the author's claim would be a
  misattribution.
- It is scoped to the entry's `sha256`. When the author republishes, the
  artifact hash changes and any declaration written against the old one stops
  applying; producers MUST NOT carry an `errata` across a `sha256` change.
- Clients unaware of the field ignore it (§2.2); a v1.3 document stays valid
  under v1.4 rules.

The reference producer is `scripts/mep_errata.py` (`mei_errata_field`, called
from `scripts/mei_catalog_entry.py`), reading the reviewed declaration files
under `docs/community-packs/errata/<artifact-sha256>.json`; the same module is
the single reader for both validation gates (`scripts/mep_lint.py` and
`scripts/smoke_pack_headless.sh`), which downgrade exactly the declared targets
and keep every other unresolvable target an error (ADR-0151/ADR-0152). Reference
consumers: `UI/Logic/CommunityPackCatalog.cs` (deserialization) and the Player
pack picker in `UI/ViewModels/MainWindowViewModel.cs` (the known-missing line).

## 3. Trust model (normative — ADR-0006)

MEI clients (an emulator's pack browser, or any other):

1. MUST verify the declared `sha256` **before** extracting, activating, or
   persisting the artifact, and MUST reject the installation on mismatch.
2. MUST require HTTPS for both the manifest URL and artifact URLs; `http:`
   MUST be refused (no downgrade-with-warning).
3. MUST reject, after path normalization, any zip entry that escapes the
   pack's installation directory (zip-slip).
4. MUST require explicit user confirmation when adding/installing from a
   manifest that is not the host's default index.
5. SHOULD present `license` (or "not declared") and `maintainer` before
   installation.

These rules are the **spec's contract**, not an implementation detail:
third-party clients inherit the same obligations.

## 4. Ranking and telemetry

MEI does not define telemetry. Hosts MAY order by public hosting signals
(GitHub release downloads/stars, for example). Clients MUST NOT send user
data to the index's maintainer beyond the GET request itself.

## 5. Golden file

[`golden/mei/manifest.json`](golden/mei/manifest.json) — validated by
`scripts/validate-specs.py` (required fields, semver, HTTPS, hash formats,
the v1.1 `kind`-aware relaxations of §2.3, the v1.2 `rom.sha1s[]` shape
of §2.4, and the v1.3 §2.5 shapes — `pack_id` slug/`owner/repo[:game]`/
`issue-N`, `content_id` 64 lowercase hex, `votes` non-negative integer,
none of them empty or mistyped — via `scripts/mei_rules.py`
`mei_identity_field_errors`, unit-tested by `scripts/test_mei_rules.py`).
The same rules are run over
the generated `docs/community-packs.json` catalog when it exists in the
repo (`validate_mei_catalog()`).
