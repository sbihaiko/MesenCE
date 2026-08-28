# MEP Recipe v1 — declarative re-packaging of split-distribution packs

**Status:** v1 (stable) ·
**License of this spec:** CC0-1.0 (public domain) ·
**Versioning:** semver of this document; the on-disk `recipe` field is an
integer vocabulary version — a new operation or a change in op semantics
MUST bump `recipe` and is a new ADR (ADR-0138). Clients MUST skip an
unknown `recipe` integer rather than guess. ·
**Golden file:** [`golden/mep-recipe/recipe.json`](golden/mep-recipe/recipe.json) ·
**Validation:** `scripts/validate-specs.py` ·
**Reference interpreter:** `scripts/mep_recipe.py` (`validate` / `dry-run` /
`apply`)

The keywords MUST, MUST NOT, SHOULD, and MAY follow RFC 2119.

## 1. Scope

A recipe is **data, not code**: a JSON document that tells a host how to
assemble a MEP pack (MEP-v1) from a primary artifact plus optional
user-supplied dependencies. It exists so a zip that ships only `hires.txt`
and an IPS/BPS patch, with the referenced `.ogg` files distributed
separately (hosts outside the CI allow-list), can be installed without
applying the patch against missing audio (the silent-game outcome of
`HdPackLoader::ProcessSoundTrack`).

Hosts MUST interpret recipes with a fixed operation vocabulary. There is
no scripting, no conditionals, and no network access beyond fetching the
listed sources. MEP-v1 §6 forbids executing pack content as code; this
spec is the vocabulary that section names.

Non-goals: scraping Google Drive/MEGA confirm flows; fabricating missing
assets; adjudicating patch licences (the recipe records the declared
licence, nothing more).

## 2. Document shape

A recipe is a JSON object. It MAY appear as a standalone `.json` file or
inside a fenced `mep-recipe` code block (the issue is the auditable
source of truth; ADR-0138). Unknown fields MUST be ignored. An unknown
`op` value MUST be rejected — that is the one extension point that is
not ignored.

```json
{
  "recipe": 1,
  "sources": {
    "primary": {
      "url": "https://example.org/packs/synthetic-split-1.0.0.zip",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    "deps": [
      {
        "id": "audio",
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "size": 4096,
        "hints": ["https://example.org/audio/synthetic-split-ogg.zip"],
        "license": "CC0-1.0",
        "user_supplied": true
      }
    ]
  },
  "ops": [
    { "op": "copy", "from": "primary:hires.txt", "to": "hires.txt" },
    { "op": "copy", "from": "primary:tiles.png", "to": "tiles.png" },
    { "op": "copy", "from": "primary:game.ips", "to": "patches/game.ips" },
    { "op": "glob", "from": "audio:**/*.ogg", "to": "audio/" },
    { "op": "rename", "from": "audio/Track 01.ogg", "to": "audio/track01.ogg" },
    { "op": "rewrite-paths", "file": "hires.txt", "tags": ["bgm", "sfx"], "prefix": "audio/" }
  ],
  "pack": {
    "mep": "1.1.0",
    "name": "Synthetic Split Pack",
    "version": "1.0.0",
    "license": "CC0-1.0",
    "targets": [
      { "system": "nes", "sha1": "2A4E126D0286BEA0BF503C80A12352C57539F76B" }
    ],
    "patches": [
      { "sha1": "2A4E126D0286BEA0BF503C80A12352C57539F76B", "file": "patches/game.ips" }
    ],
    "sections": { "textures": { "path": "" } }
  },
  "policy": { "apply_patch_only_if_complete": true }
}
```

The golden file is this object (the `rename` op is omitted there because
the fixture's dep files already use the destination names).

## 3. Fields

### 3.1 Root

| Field | Requirement | Semantics |
|---|---|---|
| `recipe` | MUST | vocabulary version; v1 of this spec is the integer `1`. Hosts MUST reject any other value (including the string `"1"`) |
| `sources` | MUST | object with `primary` and optional `deps` |
| `ops` | MUST, ≥1 | operations, applied in list order |
| `pack` | MUST | fields written to the output `pack.json` (MEP-v1 §3) |
| `policy` | MAY | object; missing keys take the defaults in §6 |

### 3.2 `sources.primary`

| Field | Requirement | Semantics |
|---|---|---|
| `url` | MUST | HTTPS URL of the primary zip (the CI host allow-list applies to clients that fetch) |
| `sha256` | MUST | SHA-256 of the **artifact bytes**, 64 hex (case-insensitive on read; producers SHOULD write lowercase) |

### 3.3 `sources.deps[]`

Each dep is an extra artifact the ops may read. `id` is the source-id used
in `copy`/`glob` `from` values.

| Field | Requirement | Semantics |
|---|---|---|
| `id` | MUST | `[A-Za-z][A-Za-z0-9_-]*`, unique, MUST NOT be `primary` |
| `sha256` | MUST | SHA-256 of the artifact bytes, 64 hex |
| `size` | SHOULD | size in bytes, as a JSON integer ≥ 0 |
| `hints` | SHOULD | array of HTTPS (or other) URLs where a human can fetch the file; the host MUST NOT scrape confirm-interstitial hosts |
| `license` | SHOULD | SPDX id or a short declared-licence string copied from the submission; the host MUST show it before using the file |
| `user_supplied` | MAY | JSON boolean, default `true`. `true`: the host MUST NOT download the artifact itself; the user provides a file whose bytes hash to `sha256` |

### 3.4 `pack`

Written as the output `pack.json` after the ops run. Fields follow MEP-v1
§3 (`targets[]` / `patches[]` follow ADR-0044).

| Field | Requirement | Semantics |
|---|---|---|
| `name` | MUST | pack name |
| `version` | MUST | pack semver |
| `targets` | MUST, ≥1 | ROMs the pack applies to (MEP-v1 §4) |
| `mep` | SHOULD | targeted MEP spec version; default `"1.1.0"` |
| `license` | SHOULD | SPDX of the assembled pack; default `"NOASSERTION"` |
| `author` | MAY | passed through |
| `patches` | MAY | `[{ "sha1", "file" }]` relative to the output root |
| `sections` | MAY | if omitted, the interpreter MUST derive them from the output tree (root `hires.txt` → `textures.path` `""`; otherwise the folder-form probes of MEP-v1 §2.1) |

A derived or explicit `sections` object MUST still satisfy MEP-v1: at
least one of `textures` / `audio` / `synth`, and every `path` MUST be a
safe relative path (§5). Do not declare an `audio` section unless
`audio/hires.txt` or `audio/fingerprints.json` exists — OGG files reached
only via `<bgm>`/`<sfx>` tags in the textures `hires.txt` are not a MEP
`audio` section.

## 4. Operations

v1 allows exactly four `op` values. Anything else is a validation error.

`from` on `copy` and `glob` is `<source-id>:<path>` (`source-id` is
`primary` or a dep `id`; `<path>` uses `/`). `rename` and
`rewrite-paths` address the **output** tree, not a source.

### 4.1 `copy`

```json
{ "op": "copy", "from": "primary:hires.txt", "to": "hires.txt" }
```

Copies one file. `from` is resolved against the discovered pack root of
that source (§7), then read. `to` is output-relative. Parent directories
are created. Copying onto an existing output path MUST fail. v1 does not
copy directories.

### 4.2 `glob`

```json
{ "op": "glob", "from": "audio:**/*.ogg", "to": "audio/" }
```

`from` is `<source-id>:<pattern>`. The pattern is matched against every
safe relative path inside that source (after §7 root discovery for
`primary`; against the artifact root for a dep). `*` matches one path
segment, `**` matches zero or more segments, `?` matches one character
other than `/`. Each match is copied into `to` (treated as a directory)
using the match's **basename**. Two matches that share a basename MUST
fail. An existing dest path MUST fail. Zero matches MUST fail.

### 4.3 `rename`

```json
{ "op": "rename", "from": "audio/Track 01.ogg", "to": "audio/track01.ogg" }
```

Renames an output path produced by an earlier op. `from` MUST exist.
`to` MUST NOT already exist. Parent directories of `to` are created.

### 4.4 `rewrite-paths`

```json
{ "op": "rewrite-paths", "file": "hires.txt", "tags": ["bgm", "sfx"], "prefix": "audio/" }
```

Rewrites HDNes `hires.txt` tags in an output file. `file` MUST exist.
`tags` is a non-empty array whose entries MUST be a subset of
`bgm`, `sfx`, `img`, `background`, `patch`. `prefix` is a safe relative
directory prefix (SHOULD end with `/`; hosts MUST treat it as a
directory). For each matching tag, the file-path token —

- `bgm` / `sfx`: the third comma-separated field (album, track, **file**)
- `img`: the whole tag body
- `background` / `patch`: the first comma-separated field

— is rewritten: backslashes become `/`, and if the path does not already
equal `prefix` or start with `prefix`, `prefix` is prepended. Other
fields of the line MUST be left unchanged. Lines that are not those tags
MUST be left unchanged.

The prefix is relative to the rewritten file's directory (HDNes
resolution). A recipe that keeps `hires.txt` at the pack root and globs
OGG files into `audio/` therefore uses `"prefix": "audio/"`. A prefix
containing `..` is unsafe and MUST be rejected (§5).

## 5. Path safety

Every path a recipe writes or rewrites (`to`, `rename.from`/`to`,
`rewrite-paths.file`/`prefix`, and the path half of `copy`/`glob` `from`)
MUST be a **safe relative path** as in MEP-v1 §2 rule 3 and §6: `/`
separator, no leading `/`, no drive letter, no `.` or `..` segment after
normalization. The zip-slip rule applies to recipe outputs. An escaping
path is a validation error; hosts MUST NOT apply the recipe.

Source zip entries that themselves escape MUST be skipped and MUST NOT
become a pack root (same `safe_rel` guard `mep_lint.py` already applies).

## 6. Policy

| Field | Default | Semantics |
|---|---|---|
| `apply_patch_only_if_complete` | `true` | When any dep is missing or fails its hash: abort on a hash mismatch; on a **missing** `user_supplied` dep, skip ops whose `from` source-id is that dep, skip `rename`/`rewrite-paths` ops whose source path would only have been produced by an op skipped this way (transitively), skip ops whose `to` (or `rename` dest) sits under `patches/` or whose basename ends in `.ips`/`.bps`, and omit `pack.patches` from the written `pack.json`. Textures (and any other complete sections) are still written. The host MUST tell the user the patch was withheld. When `false`, a missing dep MUST abort the whole install |

A sha256 mismatch on a provided artifact (primary or dep) MUST always
abort, regardless of this flag.

## 7. Source discovery

`primary` is opened with the same discovery `scripts/mep_lint.py` uses —
`Source`, `discover_sections`, `find_fallback_subfolder`,
`find_fallback_subfolder_by_name`, `find_top_level_nested_zip` — never a
parallel implementation. `copy`/`glob` paths on `primary` are relative to
the discovered pack root (a nested zip or a wrapped subfolder), not
necessarily the artifact root.

A dep is opened as a `Source` at its artifact root. Deps are typically a
bag of `.ogg` files and have no pack layout; glob patterns run against
that root.

## 8. Hash verification and `pack.json`

Hosts MUST verify every provided artifact's sha256 **before** any op
runs. After the ops, they MUST write `pack.json` from `pack` (with
derived `sections` when omitted) and MUST NOT write any other generated
format this spec does not name. The F6.4 installer additionally writes
`.mep-install.json`; that file is not part of this vocabulary.

## 9. Golden file

[`golden/mep-recipe/recipe.json`](golden/mep-recipe/recipe.json) —
validated by `scripts/validate-specs.py` (integer `recipe` 1, HTTPS
primary URL, sha256 format, known ops, safe paths). The golden hashes
are format fixtures, not hashes of a committed zip.
