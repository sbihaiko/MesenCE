#!/usr/bin/env python3
"""ADR reference integrity — every `ADR-NNNN` cited in docs resolves to a file.

Scans `docs/**/*.md` (the ADR register itself included), `.github/**/*.md`,
`CLAUDE.md` and every `AGENTS.md` for `ADR-NNNN` references and fails when it has no
`docs/adr/NNNN-*.md` file. Motivation: commit b0b334b0 (2026-08-28)
deleted four accepted ADRs (0130/0131/0136/0137) as a side effect of an
unrelated fix and nothing noticed for four days (PRD slice D1).

Two classes of ids intentionally have no file and are tolerated in context:

- Permanently retired ids (ADR-0035: 0009-0010, 0015-0020, 0022-0032) are
  allowed only when the citing line itself says "former", "retired",
  "consolidat…", "superseded" or "deleted" (case-insensitive) — a bare
  citation of a retired id is a dangling reference like any other.
- Ids folded into a consolidating ADR on 2026-08-27 and then deleted
  (CLAUDE.md: "ADR-0122–0137 are the consolidation of the former
  ADR-0053–0119"; ADR-0049 line 6: drafts 0045/0046/0048) are allowed
  under the same context rule, and additionally anywhere inside an ADR
  that carries its own `- Consolidates:` header line — those ADRs discuss
  their sources by id throughout.

`roms/` is skipped (unversioned local content).

Usage: python3 scripts/checks/verify_adr_refs.py
Exit 0 on PASS, 1 on any dangling reference (each reported as file:line).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ADR_DIR = ROOT / "docs/adr"

RETIRED_IDS = (
    {f"{n:04d}" for n in range(9, 11)}
    | {f"{n:04d}" for n in range(15, 21)}
    | {f"{n:04d}" for n in range(22, 33)}
)
CONSOLIDATED_IDS = {f"{n:04d}" for n in range(53, 120)} | {"0045", "0046", "0048"}
RETIRED_CONTEXT = re.compile(r"former|retired|consolidat|superseded|deleted", re.IGNORECASE)
CONSOLIDATES_HEADER = re.compile(r"^- Consolidates:", re.MULTILINE)
ADR_REF = re.compile(r"ADR-(\d{4})")
SKIP_PARTS = {"roms"}


def known_ids():
    ids = set()
    for p in ADR_DIR.glob("*.md"):
        m = re.match(r"(\d{4})-", p.name)
        if m:
            ids.add(m.group(1))
    return ids


def candidate_files():
    seen = set()
    for pattern in ("docs/**/*.md", ".github/**/*.md",
                    "CLAUDE.md", "**/AGENTS.md"):
        for p in ROOT.glob(pattern):
            rel = p.relative_to(ROOT).as_posix()
            if any(rel == s or rel.startswith(s + "/") for s in SKIP_PARTS):
                continue
            if p.is_file() and rel not in seen:
                seen.add(rel)
                yield p, rel


def scan(failures):
    ids = known_ids()
    if not ids:
        failures.append(f"no ADR files found under {ADR_DIR}")
        return
    for path, rel in sorted(candidate_files(), key=lambda t: t[1]):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        consolidating_adr = rel.startswith("docs/adr/") and bool(
            CONSOLIDATES_HEADER.search(text))
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in ADR_REF.finditer(line):
                num = m.group(1)
                if num in ids:
                    continue
                if num in RETIRED_IDS or num in CONSOLIDATED_IDS:
                    if RETIRED_CONTEXT.search(line):
                        continue
                    if num in CONSOLIDATED_IDS and consolidating_adr:
                        continue
                    kind = "retired id (ADR-0035)" if num in RETIRED_IDS else \
                        "consolidated-and-deleted id (2026-08-27)"
                    failures.append(
                        f"{rel}:{lineno}: ADR-{num} is a {kind} cited without "
                        "former/retired/consolidated/superseded/deleted context")
                    continue
                failures.append(
                    f"{rel}:{lineno}: ADR-{num} has no docs/adr/{num}-*.md")


def main():
    failures = []
    scan(failures)
    if failures:
        print("FAIL verify_adr_refs:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("PASS verify_adr_refs: every cited ADR-NNNN resolves to docs/adr/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
