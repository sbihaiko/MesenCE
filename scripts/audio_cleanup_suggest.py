#!/usr/bin/env python3
"""audio_cleanup_suggest — read the extract-audio tool's enumeration.log and
suggest which trigger ids look like garbage (ADR-0135 point 6: "so a human can
prune garbage ids"; F5.4g Block D item 12).

The probe writes `<pack>/auto/audio/enumeration.log` with one CSV row per id:
`id,kind,audible,frames,last,hash,"first-notes",repeat`. This helper summarises
which ids are worth dropping (short/title/repeat/silent) so a human can decide,
then does the final cut with `rename-audio-id` or a manual edit of
fingerprints.json after listening. It is deliberately REPORT-ONLY: the
id<->trackNN mapping is not 1:1 (the F5.3 recorder segments by silence, not by
trigger id), so an automated delete would risk removing a real track.

Usage: python3 scripts/audio_cleanup_suggest.py <pack-folder>
Exit codes mirror mep_lint: 0 = nothing obviously garbage, 1 = suggestions made.
"""
import csv
import io
import json
import sys
from pathlib import Path

GARBAGE_KINDS = {"short", "title"}


def main(argv) -> int:
    if len(argv) != 2:
        print("usage: python3 scripts/audio_cleanup_suggest.py <pack-folder>", file=sys.stderr)
        return 2

    pack = Path(argv[1])
    log_path = pack / "auto" / "audio" / "enumeration.log"
    if not log_path.exists():
        print(f"no enumeration.log at {log_path} - run the extract-audio tool first "
              "(scripts/spike_sound_driver <rom> <workdir> <pack-folder> ...)", file=sys.stderr)
        return 2

    # Parse the CSV block after the "id,kind,..." header line.
    rows = []
    header = "id,kind,audible,frames,last,hash,first-notes,repeat"
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"cannot read {log_path}: {e}", file=sys.stderr)
        return 2
    in_table = False
    for line in text.splitlines():
        line = line.strip()
        if line == header:
            in_table = True
            continue
        if not in_table or not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 8:
            continue
        try:
            rows.append({
                "id": parts[0],
                "kind": parts[1],
                "audible": int(parts[2]),
                "frames": int(parts[3]),
                "hash": parts[5],
                "notes": parts[6].strip('"'),
                "repeat": parts[7] == "yes",
            })
        except ValueError:
            continue

    if not rows:
        print(f"no per-id rows found in {log_path}", file=sys.stderr)
        return 2

    # Garbage heuristics (mirror the probe's own classifications).
    garbage = []
    seen_hashes = set()
    for r in rows:
        reasons = []
        if r["kind"] in GARBAGE_KINDS:
            reasons.append(f"kind={r['kind']}")
        if r["kind"] not in GARBAGE_KINDS and r["audible"] == 0:
            reasons.append("silent")
        if r["repeat"]:
            reasons.append("repeat of an earlier id")
        if r["hash"] in seen_hashes:
            reasons.append("duplicate hash")
        seen_hashes.add(r["hash"])
        if reasons:
            r["reasons"] = "; ".join(reasons)
            garbage.append(r)

    # Cross-reference the recorder's segments so the human knows the scale.
    tracks = []
    for fp in (pack / "auto" / "audio" / "fingerprints.json",
               pack / "audio" / "fingerprints.json"):
        if fp.exists():
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                print(f"warning: cannot read {fp}: {e}", file=sys.stderr)
                data = None
            if isinstance(data, dict) and isinstance(data.get("tracks"), list):
                tracks = data["tracks"]
                break

    n_rows = len(rows)
    print(f"enumeration.log: {n_rows} ids x {len(tracks)} recorder segment(s) "
          f"({'not 1:1 - the recorder segments by silence' if tracks else 'no fingerprints yet'})")
    if not garbage:
        print("no obviously-garbage ids - nothing to prune")
        return 0

    print(f"{len(garbage)} id(s) worth reviewing (listen, then drop via "
          f"`scripts/mep_build.py rename-audio-id` or editing fingerprints.json):")
    for r in sorted(garbage, key=lambda r: (r["kind"], r["id"])):
        print(f"  id {r['id']:>3}  {r['kind']:<6} audible={r['audible']:>3}/{r['frames']:>3} "
              f"hash={r['hash']:<8} {r['notes'][:32]:<34} [{r['reasons']}]")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
