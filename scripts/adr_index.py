#!/usr/bin/env python3
"""Print an index of the accepted ADRs, for injection at session start.

ADRs are not loaded into a Claude Code session automatically, and the whole
register (60+ files) is far too large to inject. This prints one line per
`accepted` ADR — id, date and title — so a session always knows which
decisions exist and can read the bodies it actually needs
(`docs/adr/NNNN-*.md`). Wired as a `SessionStart` hook in
`.claude/settings.json`; also runnable by hand.

`proposed` and `superseded` ADRs are deliberately omitted: only `accepted`
ones are binding (see CLAUDE.md, "Architecture Decision Records").

Usage: python3 scripts/adr_index.py [--all]
  --all   also list the proposed and superseded ones, grouped by status.
Exit 0 always (a missing register prints a note, never fails a session).
"""
import re
import sys
from pathlib import Path

ADR_DIR = Path(__file__).resolve().parent.parent / "docs/adr"
STATUS = re.compile(r"^- Status:\s*(\w+)", re.MULTILINE)
DATE = re.compile(r"^- Date:\s*(\S+)", re.MULTILINE)


def parse(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    title = text.split("\n", 1)[0].lstrip("# ").strip()
    status = STATUS.search(text)
    date = DATE.search(text)
    return {
        "id": path.name[:4],
        "title": title,
        "status": status.group(1).lower() if status else "unknown",
        "date": date.group(1) if date else "?",
    }


def main():
    show_all = "--all" in sys.argv[1:]
    if not ADR_DIR.is_dir():
        print(f"No ADR register at {ADR_DIR}.")
        return 0

    adrs = sorted((parse(p) for p in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")),
                  key=lambda a: a["id"])
    groups = ["accepted"] if not show_all else \
        ["accepted", "proposed", "superseded", "unknown"]

    for status in groups:
        rows = [a for a in adrs if a["status"] == status]
        if not rows:
            continue
        print(f"# {status.capitalize()} ADRs ({len(rows)}) — binding decisions; "
              f"read docs/adr/NNNN-*.md before changing the area one covers."
              if status == "accepted" else f"# {status.capitalize()} ADRs ({len(rows)})")
        for a in rows:
            print(f"- {a['id']} ({a['date']}) {a['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
