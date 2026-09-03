---
name: adr
description: Write or amend an Architecture Decision Record in docs/adr/. Use when an architecture or trade-off decision is being made, revisited, or superseded — a choice between designs, a format/spec change, a storage/precedence rule, a CI or test-wiring contract. Also use when the user says "open an ADR", "record this decision", "/adr", or asks why a decision was made. Not for bugs (those go to the bug board via scripts/report-bug.sh) and not for plans (those are PRD slices).
---

# Architecture Decision Records

`docs/adr/` is this project's decision register: `NNNN-<kebab-title>.md`,
versioned like any other doc, owned by `docs/AGENTS.md`. Accepted ADRs are
**binding** — see CLAUDE.md, "Architecture Decision Records".

## Before writing

1. **Check for an existing ADR on the topic.** The session already carries
   the accepted-ADR index (id, date, title) from the `SessionStart` hook.
   Grep the register for the area (`grep -ril "<term>" docs/adr/`) and read
   the candidates. Amending or superseding an existing ADR is almost always
   better than minting a second one on the same topic.
2. **Decide which shape applies:**
   - *new decision* → new file;
   - *the same decision, refined* → edit that ADR in place and extend its
     Context/Decision; note the change and its date;
   - *the decision is reversed* → the old one becomes `superseded` with a
     `- Superseded by: ADR-NNNN` line, and the new one carries the rationale.
3. **Confirm the status with the user when it isn't obvious.** `accepted`
   means decided, and accepting one is a request for work. An open
   question or an either/or stays `proposed` until a human picks.

## Allocating the id

Ids are never reused (ADR-0035). Take the next one:

```bash
python3 - <<'EOF'
import pathlib, re
ids = sorted(int(p.name[:4]) for p in pathlib.Path("docs/adr").glob("[0-9][0-9][0-9][0-9]-*.md"))
print(f"next: {max(ids) + 1:04d}")
EOF
```

Never fill a gap: `0009–0010`, `0015–0020` and `0022–0032` are permanently
retired, and `0053–0119` were consolidated into `0122–0137` and deleted.
Their text lives in git history only.

## Template

```markdown
# ADR-NNNN: <one-line decision, stated as the decision — not "investigate X">

- Status: proposed | accepted | superseded
- Date: YYYY-MM-DD
- Related: <specs and ADRs this touches, e.g. MEP-v1 §5, PRD Part A §4, ADR-0040>
- Supersedes / amends: <optional — what this changes, with section numbers>
- Superseded by: <only on a superseded ADR: ADR-NNNN, or the reason when there is none>

## Context

What forced the decision: the constraint, the conflict, the thing that
broke. Include the non-goals — what this deliberately does not do.

## Decision

The decision itself, concretely enough to implement and to verify: file
formats with an example, precedence rules in order, the config key and its
default, the exact target/check name.

## Consequences

What this costs, what it forecloses, and the traps it leaves behind
(a rebuild requirement, an interop mirror, a migration).
```

## House rules

- **Prose is en-US**, like every instruction file — the chat stays pt-br.
- Quote GitHub Project Status option names verbatim (they are Portuguese
  literals tied to live board state; "translating" them desyncs the doc).
- Cite **target and section names, not line numbers** — `makefile:233`
  rots on the next edit; `make core-unit-tests` does not.
- One ADR per decision, written by hand. Don't mint an ADR per review
  finding: that shape (truncated titles, placeholder sections) is what the
  2026-08-27 consolidation existed to undo.
- The Status line says whether the decision is already reflected in the
  code/docs or is still a pending slice in
  `docs/roadmap/PRD-mesence-enhancement-ecosystem.md`.

## After writing

- `python3 scripts/checks/verify_adr_refs.py` — every cited `ADR-NNNN`
  must resolve. A citation of a retired or consolidated id needs
  "former"/"retired"/"consolidated"/"superseded"/"deleted" on the same line.
- If the ADR is `accepted` and needs implementing, say so and get a
  go-ahead — don't implement it in the same turn it is accepted.
- If it changes a spec, bump that spec's semver in `docs/specs/` and add
  the `Supersedes / amends` line naming the sections.
