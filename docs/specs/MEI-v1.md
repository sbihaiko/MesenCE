# MEI v1 — MesenCE Enhancement Index

**Status:** v1 (stable) ·
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
  "mei": "1.0.0",
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
    }
  ]
}
```

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
| `name`, `version` | MUST | mirror the artifact's `pack.json` |
| `game`, `system` | MUST | target game and system (`system` values as in MEP §4) |
| `rom` | MUST | `sha1` (40 uppercase hex, No-Intro range from MEP §4) and optionally `crc32` |
| `mep` | MUST | MEP spec version of the artifact |
| `license` | MUST | SPDX of the content |
| `url` | MUST | URL of the `.zip` artifact — **HTTPS required** |
| `size` | SHOULD | size of the artifact in bytes |
| `sha256` | MUST | SHA-256 of the artifact, 64 hex (case-insensitive on read; producers SHOULD write lowercase) |

Unknown fields MUST be ignored.

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
5. SHOULD present `license` and `maintainer` before installation.

These rules are the **spec's contract**, not an implementation detail:
third-party clients inherit the same obligations.

## 4. Ranking and telemetry

MEI does not define telemetry. Hosts MAY order by public hosting signals
(GitHub release downloads/stars, for example). Clients MUST NOT send user
data to the index's maintainer beyond the GET request itself.

## 5. Golden file

[`golden/mei/manifest.json`](golden/mei/manifest.json) — validated by
`scripts/validate-specs.py` (required fields, semver, HTTPS, hash formats).
