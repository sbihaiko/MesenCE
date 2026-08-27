# MEP migration reference (per-pack)

MEP packs are meant to be produced automatically, per pack, by a client-side
MEP exporter (not built yet — see `docs/specs/MEP-v1.md` for the target
format). This file records, one pack at a time, the exact before/after
transformation applied to turn a classic Mesen HD pack into an MEP-compliant
pack. It's a *reference*, not a one-size-fits-all rule: each entry below
documents what a specific real pack needed. Until the automatic exporter
exists, an artist can read the closest entry and apply the same steps by
hand to their own pack.

## The transformation rule (what the exporter will apply)

For a pack whose only content is textures, the rule observed so far is
always the same one structural change: the texture files (`hires.txt` and
the images it references) move from the pack root into a `textures/`
subfolder — nothing inside `hires.txt` itself needs to change, since its
paths are relative to the file's own location. See MEP-v1.md §2.1 rule 6
and §5.1 for the normative version of this rule.

---

## Pack: Contra80s (TasticHacks)

Source: <https://github.com/TasticHacks/Contra80s/releases/latest/download/Contra80s.zip>
(also tracked as `sbihaiko/MesenCE` community-pack submission, issue #4).

**Before (as published, classic Mesen HD pack layout):**
```
Contra80s-v1.1/                          <- GitHub Releases wrapper folder
  art/...                                <- promo material, not part of the pack
  changelog.txt
  Contra (U) [!]/
    hires.txt
    Ash1.png
    BillRizer.png
    ... (all other PNGs referenced by hires.txt)
```

**After (MEP layout):**
```
Contra (U) [!]/
  textures/
    hires.txt
    Ash1.png
    BillRizer.png
    ... (same files, same relative structure, just moved one level down)
```

What changed: only the location of `hires.txt` and its PNGs (moved into
`textures/`). No `pack.json` was added — the pack still qualifies under the
folder convention (MEP-v1.md §2.1), identified by the folder/file name
instead of a declared hash. The release-zip wrapper folder
(`Contra80s-v1.1/`) and the promo material inside it are dropped; they were
never part of the pack itself.

**Verification:** `python3 scripts/mep_lint.py <converted-folder>` no
longer reports "no section found" after this change — the structural
mismatch that caused the automated triage to reject the original zip
(`pack:invalid-structure`) is resolved by this move alone. Two unrelated
`error` lines remain in this specific pack's `hires.txt`
(an invalid `tileNearby` condition alias, and one `<background>` entry
pointing at a PNG that isn't present in the release) — those are pre-existing
content issues in the pack itself, unrelated to MEP compliance, and are not
addressed by this migration.

**Optional `pack.json`:** the folder move above is enough on its own — the
converted pack qualifies under the folder convention (MEP-v1.md §2.1) with
no `pack.json` at all. A maintainer who would rather use the canonical,
non-fallback form (e.g. to add `license`/`author` metadata, or list more
than one ROM revision under `targets`) can add this at the pack root
instead; `<sha1>` is the No-Intro hash of the target ROM's PRG+CHR payload
(MEP-v1.md §4) and must be filled in by whoever holds the ROM — it is not
published here:

```json
{
  "mep": "1.0.0",
  "name": "Contra80s",
  "version": "1.1.0",
  "author": "TasticHacks",
  "license": "<SPDX id — fill in with the license the pack author intends>",
  "targets": [
    { "system": "nes", "sha1": "<No-Intro SHA1 of your 'Contra (U) [!]' dump>", "name": "Contra (U) [!]" }
  ],
  "sections": {
    "textures": { "path": "textures/" }
  }
}
```

---

## Submitting a converted pack

1. Run `python3 scripts/mep_lint.py <folder-or-zip>` locally — it should
   finish with no `error` lines.
2. Submit through the "Community HD/MEP Pack Submission" form
   (`.github/ISSUE_TEMPLATE/community-pack.yml`) on
   [`sbihaiko/MesenCE`](https://github.com/sbihaiko/MesenCE/issues/new/choose).
   The automated triage comments the verdict on the issue.

For what each verdict ("Full MEP" / "Partial (HD Mesen)" / "Invalid")
means, see `docs/hd-pack-authoring.md`.
