#!/usr/bin/env python3
"""`Upstream-Delta:` trailer check (ADR-0163).

A commit that touches a Tier C file (an inherited file the fork has never
modified — where upstream's edits land clean) or a Tier B file that upstream
also touches widens the fork's merge surface. ADR-0163 therefore requires such
commits to carry, in the body, an `Upstream-Delta:` line explaining why the
fork diverges and the smaller-upstream-surface alternative that was considered.

This check scans a revision range and fails on every non-merge commit in it
that touches such a file without the trailer. Merge commits are skipped: they
bring upstream's own changes to Tier C files, and upstream-authored commits
never carry the fork's trailer. The tier sets come from the *current*
merge-base (`scripts/upstream_tiers.py`), so the check is only meaningful on
the range it is invoked with — pass the commits you are about to push.

Usage:
  python3 scripts/checks/verify_upstream_delta.py <rev-range> [--upstream upstream/master] [--since 1.year]
  python3 scripts/checks/verify_upstream_delta.py merge-base..HEAD

Exit 0 on PASS; 1 with one line per offending commit when a commit touches a
guarded file without the trailer. Commits that touch nothing guarded always
pass and need no trailer.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import upstream_tiers  # noqa: E402

TRAILER = re.compile(r"^[ \t]*Upstream-Delta:", re.MULTILINE)


def git(*args):
    proc = subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed ({proc.returncode}):\n"
                         f"{proc.stderr.strip()}")
    return proc.stdout


def guarded_files(snap):
    """Tier C plus Tier B files upstream also touches: the trailer's trigger set."""
    guarded = set(snap["tiers"]["C"])
    guarded |= set(snap["watch"]["B_hot"])
    return guarded


def commits_in_range(rev_range):
    return git("rev-list", rev_range).split()


def is_merge(commit):
    parents = git("show", "-s", "--format=%P", commit).split()
    return len(parents) > 1


def touched_files(commit):
    # plain -r against the commit's own parent(s) is enough; merges are
    # skipped anyway before this is consulted.
    out = git("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", commit)
    return set(upstream_tiers.nul_names(out))


def body(commit):
    return git("log", "-1", "--format=%B", commit)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rev_range", help="revision range to scan, e.g. merge-base..HEAD")
    ap.add_argument("--upstream", default="upstream/master")
    ap.add_argument("--since", default="1.year")
    args = ap.parse_args(argv)

    commits = commits_in_range(args.rev_range)
    if not commits:
        # An empty range (e.g. HEAD..HEAD, or merge-base..HEAD with nothing
        # new) has zero commits to check and zero violations by definition —
        # PASS, not an error. Return before computing the tiers so a caller
        # that only wants a no-op gate does not need the upstream ref at all.
        print("PASS verify_upstream_delta: no commits in range.")
        return 0

    snap = upstream_tiers.snapshot(ROOT, args.upstream, args.since)
    guarded = guarded_files(snap)

    failures = []
    checked = 0
    for commit in commits:
        if is_merge(commit):
            continue
        touched = touched_files(commit)
        offenders = sorted(touched & guarded)
        if not offenders:
            continue
        checked += 1
        if not TRAILER.search(body(commit)):
            subject = git("log", "-1", "--format=%s", commit)
            failures.append(
                f"{commit[:12]} {subject}: touches guarded files "
                f"({' ,'.join(offenders[:5])}{'…' if len(offenders) > 5 else ''}) "
                "without an Upstream-Delta: line")

    if failures:
        print(f"FAIL verify_upstream_delta ({checked} guarded commit(s) checked):")
        for f in failures:
            print(f"  {f}")
        print("Each must explain in the body why the fork diverges and the")
        print("smaller-upstream-surface alternative considered (ADR-0163).")
        return 1
    if checked == 0:
        print("PASS verify_upstream_delta: no guarded (Tier C / hot Tier B) commit in range.")
    else:
        print(f"PASS verify_upstream_delta: {checked} guarded commit(s) all carry Upstream-Delta:.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
