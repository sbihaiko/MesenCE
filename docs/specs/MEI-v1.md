# MEI v1.1 — MesenCE Enhancement Index

**Status:** v1.1 (stable) ·
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
  "mei": "1.1.0",
  "name": "Índice oficial MesenCE",
  "maintainer": "sbihaiko",
  "updated": "2026-08-24",
  "packs": [
    {
      "name": "After Burner — Studio FM tuning",
      "version": "1.2.0",
      "game": "After Burner (World)",
      "system": "sms",
      "rom": { "sha1": "2A4E126D0286BEA0BF503C80A12352C57539F76B", "crc32": "1C851C7E" },
      "mep": "1.0.0",
      "license": "CC0-1.0",
      "url": "https://example.org/packs/after-burner-studio-1.2.0.zip",
      "size": 18342,
      "sha256": "a3f1c2… (64 lowercase hex chars of the .zip artifact)"
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
separately (§2.3).

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
| `rom` | MUST | object; `sha1` (40 uppercase hex, No-Intro range from MEP §4) MAY (v1.1) be absent, optionally `crc32` |
| `mep` | MUST unless `kind: "hd-legacy"` | MEP spec version of the artifact |
| `license` | SHOULD | SPDX of the content, or `"unknown"` when the submitter declared none (any `kind`, v1.1); an absent field is read as `"unknown"` |
| `url` | MUST | URL of the `.zip` artifact — **HTTPS required** |
| `size` | SHOULD | size of the artifact in bytes |
| `sha256` | MUST | SHA-256 of the artifact, 64 hex (case-insensitive on read; producers SHOULD write lowercase) |
| `deps` | MAY (v1.1) | list of third-party artifacts the pack references; see §2.3 |
| `recipe` | MAY (v1.1) | MEP-recipe-v1 document assembled for `deps`; see §2.3 |
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
- `rom.sha1` MAY be absent regardless of `kind` (clients only auto-match an
  entry against a loaded ROM when it carries a `sha1`; an entry without one
  is still listable and installable, just not hash-matchable). This is a
  deliberate v1.1 downgrade of a v1.0 MUST for every `kind`, not gated on
  the declared `mei` minor: a v1.0 document stays valid under v1.1 rules, and
  the only opt-in relaxation is the explicit `kind: "hd-legacy"` (absent
  `kind` means `mep`).
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
and the v1.1 `kind`-aware relaxations of §2.3). The same rules are run over
the generated `docs/community-packs.json` catalog when it exists in the
repo (`validate_mei_catalog()`).
