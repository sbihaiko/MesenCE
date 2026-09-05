#!/usr/bin/env python3
"""Known-missing errata: the single reader shared by both pack gates (ADR-0152).

An errata is a repo-side file naming the exact manifest targets a validated
pack does not ship. It is written by the project's validation, never by the
author or the submitter, and it downgrades those targets from the ADR-0151
error to an info line. Every target it does not name stays an error.

ADR-0152 anticipated two implementations agreeing on a format - one in
`mep_lint.py`, one in `smoke_pack_headless.sh`. That is the shape that produced
bug #155, so instead both gates call *this* module: Python imports it,
`smoke_pack_headless.sh` shells out to the `covers` subcommand. There is one
parser, so there is nothing for the gates to disagree about.

File: docs/community-packs/errata/<artifact-sha256>.json, keyed on the sha256
of the downloaded artifact - the same hash the pipeline records in "Pack Hash".
When the author republishes, the hash changes, no errata resolves, and the pack
is validated clean against their new material.

Usage:
  mep_errata.py validate <errata.json>...       schema-check (exit 1 on error)
  mep_errata.py covers <errata.json> <manifest> <tag> <target>
                                                exit 0 when declared, 1 when not
  mep_errata.py resolve <dir> <sha256>          print the errata path, if any
"""
import hashlib
import json
import os
import sys
from pathlib import Path

#Only targets that are *absent* can be declared known-missing. A corrupt PNG or
#a bad bitmap index is a different defect: the file is there and wrong, so
#"we checked, it is missing" would be a false statement.
KNOWN_TAGS = ("img", "background")
REQUIRED_ENTRY_FIELDS = ("manifest", "tag", "target", "reason", "reviewed_in")
DEFAULT_DIR = Path(__file__).resolve().parent.parent / "docs" / "community-packs" / "errata"


class ErrataError(Exception):
    pass


def _norm_manifest(manifest: str) -> str:
    #The two gates see the same manifest under different paths: mep_lint reads
    #it inside the archive (`hires.txt`), the smoke gate reads it in the
    #installed tree (`textures/hires.txt`). Identity is the basename, which is
    #unambiguous because MEP allows one hires.txt per section (MEP-v1 3.2).
    return os.path.basename(manifest.strip()).lower()


class Errata:
    """The parsed declarations for one artifact."""

    def __init__(self, path, artifact_sha256, entries):
        self.path = path
        self.artifact_sha256 = artifact_sha256
        self.entries = entries
        self._used = set()

    @property
    def keys(self):
        return {(_norm_manifest(e["manifest"]), e["tag"], e["target"]) for e in self.entries}

    def covers(self, manifest, tag, target):
        key = (_norm_manifest(manifest), tag, target)
        if key in self.keys:
            self._used.add(key)
            return True
        return False

    def entry_for(self, manifest, tag, target):
        key = (_norm_manifest(manifest), tag, target)
        for e in self.entries:
            if (_norm_manifest(e["manifest"]), e["tag"], e["target"]) == key:
                return e
        return None

    @property
    def unused(self):
        #An entry that matched nothing means the errata does not describe this
        #artifact: either it was written wrong, or the pack changed without its
        #hash changing (impossible) - so it is a hard error, not a nicety. It is
        #the only thing standing between "reviewed declaration" and "blanket
        #pardon nobody re-reads".
        return sorted(self.keys - self._used)


def load(path) -> Errata:
    path = Path(path)
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ErrataError(f"{path}: cannot be read as JSON ({exc})")
    if not isinstance(doc, dict):
        raise ErrataError(f"{path}: top level must be an object")

    sha = doc.get("artifact_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha):
        raise ErrataError(f"{path}: artifact_sha256 must be a 64-char lowercase hex digest")
    if path.stem != sha:
        raise ErrataError(f"{path}: file name must be <artifact_sha256>.json (expected {sha}.json)")

    entries = doc.get("known_missing")
    if not isinstance(entries, list) or not entries:
        raise ErrataError(f"{path}: known_missing must be a non-empty array")

    seen = set()
    for i, e in enumerate(entries):
        where = f"{path}: known_missing[{i}]"
        if not isinstance(e, dict):
            raise ErrataError(f"{where}: must be an object")
        for field in REQUIRED_ENTRY_FIELDS:
            value = e.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ErrataError(f"{where}: '{field}' is required and must be a non-empty string")
        if e["tag"] not in KNOWN_TAGS:
            raise ErrataError(f"{where}: tag must be one of {', '.join(KNOWN_TAGS)} (got {e['tag']!r})")
        for field in ("manifest", "target"):
            #A wildcard would let one reviewed line absolve defects nobody
            #looked at, which is exactly the "dumping ground" failure ADR-0152
            #names as its main risk.
            if any(ch in e[field] for ch in "*?["):
                raise ErrataError(f"{where}: '{field}' must be an exact name, no wildcards")
        if len(e["reason"].strip()) < 40:
            raise ErrataError(f"{where}: 'reason' must actually explain the finding (>= 40 chars)")
        key = (_norm_manifest(e["manifest"]), e["tag"], e["target"])
        if key in seen:
            raise ErrataError(f"{where}: duplicate declaration for {key}")
        seen.add(key)

    return Errata(path, sha, entries)


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve(sha256: str, directory=None):
    """The errata for an artifact hash, or None. Absence is the normal case."""
    directory = Path(directory) if directory else DEFAULT_DIR
    candidate = directory / f"{sha256}.json"
    return candidate if candidate.is_file() else None


def resolve_for_artifact(path, directory=None):
    return resolve(sha256_file(path), directory)


def mei_errata_field(pack_hash):
    """The MEI `errata` object for an artifact hash, or None (ADR-0152).

    Carries only what a reader needs to judge the row -- how many targets are
    declared, what they are, and where the declaration was reviewed. The full
    reasoning stays in the errata file, which the `reviewed_in` link reaches.
    """
    if not pack_hash:
        return None
    path = resolve(pack_hash.strip().lower())
    if not path:
        return None
    errata = load(path)
    return {
        "known_missing": [
            {"manifest": e["manifest"], "tag": e["tag"], "target": e["target"],
             "reviewed_in": e["reviewed_in"]}
            for e in errata.entries
        ],
        "declared_by": "MesenCE validation",
    }


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]

    if cmd == "validate":
        paths = argv[2:] or sorted(DEFAULT_DIR.glob("*.json"))
        if not paths:
            print("no errata files to validate")
            return 0
        bad = 0
        for p in paths:
            try:
                errata = load(p)
            except ErrataError as exc:
                print(f"FAIL {exc}")
                bad += 1
            else:
                print(f"PASS {Path(p).name}: {len(errata.entries)} declaration(s)")
        return 1 if bad else 0

    if cmd == "covers":
        if len(argv) != 6:
            print("usage: mep_errata.py covers <errata.json> <manifest> <tag> <target>")
            return 2
        try:
            errata = load(argv[2])
        except ErrataError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0 if errata.covers(argv[3], argv[4], argv[5]) else 1

    if cmd == "resolve":
        if len(argv) != 4:
            print("usage: mep_errata.py resolve <dir> <sha256>")
            return 2
        found = resolve(argv[3], argv[2])
        if found:
            print(found)
            return 0
        return 1

    print(f"error: unknown subcommand {cmd!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
