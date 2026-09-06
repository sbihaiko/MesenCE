#!/usr/bin/env python3
"""upstream_tiers — mechanical fork/upstream ownership tiers (ADR-0163).

Computes, from the live merge-base of `HEAD` and an upstream ref, the four
ownership sets this fork uses to keep upstream merges cheap:

  A = files the fork *added* since the merge-base
      (git diff --diff-filter=A <merge-base>..HEAD)
  B = files the fork *modified* since the merge-base (--diff-filter=M)
  D = files the fork *deleted* since the merge-base (--diff-filter=D) — the
      delete/modify watchlist, not a tier of tracked files
  C = everything else under HEAD: inherited files the fork has never touched

...plus the second axis, upstream "heat": how many times each file appears in
`git log <upstream> --since=<since> --name-only`. A future upstream edit
lands clean in C (the fork never touches C), as a modify/modify conflict in B,
or as a delete/modify conflict in D whose standing resolution is "keep the
fork's deletion" (ADR-0163).

Nothing here is stored or hand-maintained: the tiers are a function of the
current merge-base and are recomputed on every run. Tier semantics and the
change policy that goes with them live in ADR-0163.

Usage:
  python3 scripts/upstream_tiers.py                     # summary + hazard watchlists
  python3 scripts/upstream_tiers.py --full              # summary + full per-tier listings
  python3 scripts/upstream_tiers.py --predicted         # + predicted B/D conflicts for the
                                                        #   upstream commits not yet merged
                                                        #   (meaningful only after a `git fetch upstream`)
  python3 scripts/upstream_tiers.py --json              # machine-readable snapshot on stdout
  python3 scripts/upstream_tiers.py --upstream upstream/master --since 1.year

Exit 0 on success; 1 when the upstream ref cannot be resolved or HEAD and the
upstream ref share no history.
"""
import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(root, *args):
    """Run a git command in the repo; exit with git's stderr on failure."""
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed ({proc.returncode}):\n"
                         f"{proc.stderr.strip()}")
    return proc.stdout


def git_ok(root, *args):
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True)
    return proc.returncode == 0


def nul_names(stdout):
    """Split `-z` git output (NUL-terminated records) into a list of names."""
    return [s for s in stdout.split("\0") if s]


def snapshot(root=ROOT, upstream="upstream/master", since="1.year"):
    """Compute the ownership snapshot. `upstream` is a ref (e.g. upstream/master).

    Returns a dict with the four tier sets, upstream heat per file, the
    merge-base, and — only when the upstream ref is not already an ancestor of
    HEAD (i.e. after a fetch that moved it forward) — the predicted conflict
    sets for the commits upstream is about to bring.
    """
    if not git_ok(root, "rev-parse", "--verify", "--quiet", upstream):
        raise SystemExit(
            f"cannot resolve upstream ref '{upstream}'. Fetch it first, e.g.:\n"
            f"  git fetch {upstream.split('/')[0]}")
    mb = git(root, "merge-base", "HEAD", upstream).strip()
    if not mb:
        raise SystemExit(
            f"HEAD and {upstream} share no history; there is no merge-base.")

    # git's own --diff-filter codes do not line up with our tier letters:
    # "modified" is M (B would mean "broken pair"). Map explicitly so a tier
    # rename here can never silently change what gets selected again.
    FILTER_CODE = {"A": "A", "B": "M", "D": "D"}
    tiers = {}
    for letter in "ABD":
        tiers[letter] = set(nul_names(git(
            root, "diff", f"--diff-filter={FILTER_CODE[letter]}",
            "--name-only", "-z", f"{mb}..HEAD")))
    head_files = set(nul_names(git(root, "ls-tree", "-r", "--name-only", "-z", "HEAD")))
    tiers["C"] = head_files - tiers["A"] - tiers["B"]

    heat = Counter(nul_names(git(
        root, "log", "--since", since, "--name-only", "-z", "--format=", upstream)))

    out = {
        "upstream": upstream,
        "upstream_sha": git(root, "rev-parse", upstream).strip(),
        "merge_base": mb,
        "ahead": git(root, "rev-list", "--count", f"{mb}..HEAD").strip(),
        "behind": git(root, "rev-list", "--count", f"HEAD..{upstream}").strip(),
        "tiers": {k: sorted(v) for k, v in tiers.items()},
        "heat": dict(heat),
        "watch": {
            "A_hot": [],
            "B_hot": sorted(f for f in tiers["B"] if f in heat),
            "C_hot": sorted(f for f in tiers["C"] if f in heat),
            "D_hot": sorted(f for f in tiers["D"] if f in heat),
        },
    }

    upstream_ancestor = git_ok(root, "merge-base", "--is-ancestor", upstream, "HEAD")
    out["upstream_merged"] = bool(upstream_ancestor)
    out["predicted"] = None
    if not upstream_ancestor:
        changed = set(nul_names(git(root, "diff", "--name-only", "-z", f"{mb}..{upstream}")))
        out["predicted"] = {
            "delete_modify": sorted(changed & tiers["D"]),  # keep the fork's deletion
            "modify_modify": sorted(changed & tiers["B"]),  # needs a human decision
            "total_changed": len(changed),
        }
    return out


def _fmt(name, items, limit=None):
    shown = items if limit is None else items[:limit]
    lines = [f"{name} ({len(items)})" + ("" if limit is None else
             ("" if len(items) <= limit else f", showing first {limit}"))]
    lines += [f"  {f}" for f in shown]
    return "\n".join(lines)


def render_human(snap, full, predicted):
    def count(t): return len(snap["tiers"][t])
    def hot(t): return len(snap["watch"][f"{t}_hot"])
    print(f"upstream ref : {snap['upstream']} @ {snap['upstream_sha'][:12]}")
    print(f"merge-base   : {snap['merge_base'][:12]}")
    print(f"ahead (ours) : {snap['ahead']} commits | behind (upstream) : {snap['behind']} commits")
    print(f"upstream fully merged: {snap['upstream_merged']}")
    print()
    print(f"Tier A (added by us)      : {count('A')} files | touched upstream/yr: {hot('A')}")
    print(f"Tier B (modified by us)   : {count('B')} files | touched upstream/yr: {hot('B')}")
    print(f"Tier C (inherited intact) : {count('C')} files | touched upstream/yr: {hot('C')}")
    print(f"Tier D (deleted by us)    : {count('D')} files | touched upstream/yr: {hot('D')}  <- delete/modify watchlist")
    if full:
        for t in "ABCD":
            print("\n" + _fmt(f"Tier {t}", snap["tiers"][t]))
    print()
    print(_fmt("B files upstream also touches (modify/modify risk if it edits again)",
               snap["watch"]["B_hot"], 40 if not full else None))
    print()
    print(_fmt("D files upstream also touches (delete/modify: keep the fork's deletion)",
               snap["watch"]["D_hot"], 40 if not full else None))

    if predicted and snap["predicted"] is None:
        print("\nNothing predicted: upstream is already merged (nothing to bring).")
    if snap["predicted"] is not None:
        p = snap["predicted"]
        print(f"\nPredicted for the {p['total_changed']} files upstream is about to change:")
        print(_fmt("  delete/modify (auto-resolve: keep deletion)", p["delete_modify"]))
        print(_fmt("  modify/modify (needs a decision)", p["modify_modify"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--upstream", default="upstream/master",
                    help="upstream ref to diff against (default: upstream/master)")
    ap.add_argument("--since", default="1.year",
                    help="heat window, passed to git log --since (default: 1.year)")
    ap.add_argument("--predicted", action="store_true",
                    help="print predicted B/D conflicts for not-yet-merged upstream commits")
    ap.add_argument("--full", action="store_true",
                    help="print the full per-tier listings, not just the watchlists")
    ap.add_argument("--json", action="store_true",
                    help="emit the machine-readable snapshot as JSON on stdout")
    args = ap.parse_args(argv)

    snap = snapshot(ROOT, args.upstream, args.since)
    if args.json:
        json.dump(snap, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        render_human(snap, args.full, args.predicted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
