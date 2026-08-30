#!/usr/bin/env python3
"""revalidate_pack_hashes.py — local simulation of the CI pack-hash + lint
step (community-pack-validate.yml) against the RAW artifact at each catalog
entry's URL.

The accepted pack hashes in docs/community-packs.json were recorded by the
pre-fix pipeline, which rewrote every zip with unwrap_single_root_zip before
hashing — so the stored sha256 is the hash of a REWRITTEN zip, not of the
artifact a fresh client downloads. This script re-runs the CI's two checks
(download raw artifact -> sha256; mep_lint -> verdict) for every accepted
entry and reports what a revalidation would write.

Findings it surfaces (all data/URL/classification problems, not client bugs):
  * stale sha256 (declared != raw artifact);
  * an artifact that is the whole repository rather than one pack
    (LiQuiDzGit/HDnes main.zip -> 9 catalog entries, none installable);
  * a multi-root artifact mep_lint refuses (fail-closed on ambiguity) that
    the client's hires.txt-anchored FindPackRoot still installs
    (AxlRocks/Megaman-Super main.zip).

Usage:
  python3 scripts/revalidate_pack_hashes.py [--catalog FILE] [--work DIR]
      [--write] [--quiet]

  --write   write the corrected catalog to <work>/community-packs.corrected.json
            (sha256 = raw artifact hash; Pac-Man URL -> master). Does NOT touch
            docs/ or the board: this is the simulation output, for a human to
            review and apply.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 314572800  # same cap as the CI workflow

# No URL rewrites needed: revalidation downloads exactly the stored URL
# (a branch 404 in the data would surface as a DOWNLOAD FAILED row below).
URL_FIXES = {}


def _cert_env():
    env = dict(os.environ)
    try:
        import certifi
        env["SSL_CERT_FILE"] = certifi.where()
    except ImportError:
        pass
    return env


def download(url: str, out: Path) -> bool:
    if out.exists() and out.stat().st_size > 0:
        return True
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "fetch_pack.py"), url, str(out),
         "--max-bytes", str(MAX_BYTES)],
        cwd=str(REPO_ROOT), env=_cert_env(), capture_output=True, text=True)
    return r.returncode == 0


def mep_lint_errors(zip_path: Path, rom_name: str = "") -> (int, str):
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "mep_lint.py"), str(zip_path)]
    if rom_name:
        cmd.append(rom_name)
    r = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    out = r.stdout + r.stderr
    m = re_search(r"(\d+) error\(s\)", out)
    errors = int(m.group(1)) if m else -1
    note = ""
    if "no section found" in out:
        note = "no section found (single-root discovery fails)"
    elif "multi-game" in out or "distinct pack root" in out:
        note = "multi-root container (fail-closed)"
    return errors, note


def re_search(pattern, text):
    import re
    return re.search(pattern, text)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", type=Path, default=REPO_ROOT / "docs" / "community-packs.json")
    ap.add_argument("--work", type=Path, default=REPO_ROOT / ".cache" / "revalidate")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    cat = json.load(open(args.catalog))
    packs = cat["packs"]
    args.work.mkdir(parents=True, exist_ok=True)

    # One download per unique URL (several catalog entries share an artifact).
    by_url = {}
    for p in packs:
        by_url.setdefault(p["url"], []).append(p)

    rows = []
    changed = []
    for url, entries in by_url.items():
        resolved = URL_FIXES.get(url, url)
        cache = args.work / (hashlib.sha256(resolved.encode()).hexdigest()[:16] + ".zip")
        if not download(resolved, cache):
            note = "DOWNLOAD FAILED (404/dead link)"
            rows.append((entries[0], None, note, -1, "dead"))
            continue
        actual = hashlib.sha256(cache.read_bytes()).hexdigest()
        for p in entries:
            declared = (p.get("sha256") or "").lower()
            mismatch = declared != actual
            errors, lnote = mep_lint_errors(cache, p.get("game") or "")
            note = lnote or ("" if errors == 0 else f"lint: {errors} error(s)")
            rows.append((p, actual, note, errors, "stale" if mismatch else "ok"))
            if mismatch or url != resolved:
                changed.append(p)

    print(f"{'game':40s} {'iss':5s} {'hash':12s} {'raw':12s}  lint  note")
    for p, actual, note, errors, status in sorted(rows, key=lambda r: (r[4], r[0]["game"])):
        raw = (actual or "")[:12]
        decl = (p.get("sha256") or "")[:12]
        print(f"{p['game'][:40]:40s} {str(p.get('issue','')):5s} {decl:12s} {raw:12s}  {str(errors):>4s}  {note}")

    stale = [r for r in rows if r[4] == "stale"]
    dead = [r for r in rows if r[4] == "dead"]
    print(f"\n{len(rows)} unique artifacts; stale-hash entries: {len(stale)}; dead: {len(dead)}")

    if args.write:
        # Apply: sha256 = raw artifact hash; URL = fixed branch.
        for p in packs:
            row = next((r for r in rows if r[0] is p), None)
            if row is None or row[1] is None:
                continue
            if (p.get("sha256") or "").lower() != row[1]:
                p["sha256"] = row[1]
            p["url"] = URL_FIXES.get(p["url"], p["url"])
        out = args.work / "community-packs.corrected.json"
        json.dump(cat, open(out, "w"), indent=1)
        print(f"wrote corrected catalog -> {out}")
    return 1 if (stale or dead) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
