#!/usr/bin/env python3
"""mep_meta_parser — dependency-free leaf module that reads the bot-owned
`<!-- mep-meta -->` comment body (ADR-0138 §25–27, F6.3) and returns its
embedded JSON metadata as a plain dict.

The comment body is written by `.github/workflows/community-pack-
validate.yml`'s "Upsert mep-meta comment" step in this exact shape
(see that step, lines ~825-831):

    <!-- mep-meta -->
    ```json
    { ... }
    ```

    dep digests: submitter-declared, verified on install

`parse_mep_meta` is intentionally pure (no I/O, no `gh` calls) so it can be
unit-tested in isolation and reused by `generate_community_pack_catalog.py`
without either module importing the other's CLI. Per ADR-0138 §27, any
malformed input (missing marker, truncated fence, invalid JSON, or a
JSON value that isn't an object) is treated as "no recipe data for this
entry" rather than a fatal error: the function returns `None` and never
raises, so a caller can skip that one catalog entry's recipe fields and
log a warning instead of aborting the whole run. Issue/comment text is
external, attacker-influenced input (a submitter could, in principle,
post a comment that mimics the marker, or one shaped to blow the JSON
decoder's recursion limit via deep nesting), so this function must stay
defensive against garbage by construction, not by the caller remembering
to wrap a try/except around it.

stdlib only.
"""
from __future__ import annotations

import json
import re

MARKER = "<!-- mep-meta -->"

# Matches a fenced ```json ... ``` block: allows either bare ``` or
# ```json as the opening fence (the workflow always emits ```json, but the
# parser accepts the looser form too since it costs nothing and matches
# how Markdown fences are commonly written by hand). Non-greedy body so a
# second fenced block later in the comment (e.g. inside a re-quoted
# submitter message) is never swallowed into the first block's contents.
JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


def parse_mep_meta(comment_body: str) -> dict | None:
    """Parse the `<!-- mep-meta -->` JSON block out of a comment body.

    Returns the decoded dict on success, or `None` when the marker is
    missing, the fenced block is truncated/absent, the fenced content
    isn't valid JSON, or the decoded JSON value isn't a JSON object
    (dict) — matching the shape the workflow always emits and letting a
    caller distinguish "no usable recipe data" from a real dict without
    ever catching an exception itself.
    """
    if not isinstance(comment_body, str):
        return None
    marker_pos = comment_body.find(MARKER)
    if marker_pos == -1:
        return None
    after_marker = comment_body[marker_pos + len(MARKER):]
    fence_match = JSON_FENCE_RE.search(after_marker)
    if fence_match is None:
        return None
    raw_json = fence_match.group(1)
    try:
        payload = json.loads(raw_json)
    except (ValueError, RecursionError):
        # ValueError covers JSONDecodeError; RecursionError (a deeply
        # nested payload) is a separate, non-ValueError case — see the
        # module docstring's threat-model note.
        return None
    if not isinstance(payload, dict):
        return None
    return payload
