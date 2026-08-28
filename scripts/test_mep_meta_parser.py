#!/usr/bin/env python3
"""Framework-free checks for scripts/mep_meta_parser.py (F6.3, ADR-0138 §27).

AC-1: a well-formed `<!-- mep-meta -->` block parses to the expected dict;
a missing marker, a truncated fence, invalid JSON, and a non-object JSON
payload all return `None` without raising.

Usage: python3 scripts/test_mep_meta_parser.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import mep_meta_parser  # noqa: E402

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


# Mirrors the exact body shape written by community-pack-validate.yml's
# "Upsert mep-meta comment" step (lines ~825-831): the marker, a fenced
# ```json block built with json.dumps(indent=2, sort_keys=True), a blank
# line, then a trailing provenance sentence after the fence.
WELLFORMED_META = {
    "deps": [{"id": "audio", "sha256": "a" * 64, "size": 64}],
    "labels": ["pack:valid", "assets:audio"],
    "recipe_hash": "b" * 64,
    "recipe_ok": True,
    "source_sha256": "c" * 64,
    "validated_at": "2026-08-28T00:00:00Z",
    "verdict": "accepted",
}


def _wellformed_body() -> str:
    return "\n".join([
        "<!-- mep-meta -->",
        "```json",
        json.dumps(WELLFORMED_META, indent=2, sort_keys=True),
        "```",
        "",
        "dep digests: submitter-declared, verified on install",
    ])


def check_wellformed_block_parses():
    parsed = mep_meta_parser.parse_mep_meta(_wellformed_body())
    if parsed != WELLFORMED_META:
        fail(f"well-formed block did not round-trip: {parsed!r}")
        return
    ok("well-formed mep-meta block parses to the expected dict")


def check_bare_fence_without_json_tag_parses():
    body = "\n".join([
        "some preamble text",
        "<!-- mep-meta -->",
        "```",
        json.dumps({"verdict": "accepted"}),
        "```",
    ])
    parsed = mep_meta_parser.parse_mep_meta(body)
    if parsed != {"verdict": "accepted"}:
        fail(f"bare ``` fence (no json tag) was not accepted: {parsed!r}")
        return
    ok("fenced block without an explicit json tag still parses")


def check_missing_marker_returns_none():
    body = "\n".join([
        "```json",
        json.dumps(WELLFORMED_META),
        "```",
    ])
    parsed = mep_meta_parser.parse_mep_meta(body)
    if parsed is not None:
        fail(f"missing marker did not return None: {parsed!r}")
        return
    ok("missing marker returns None")


def check_trivial_inputs_return_none():
    for label, value in [
        ("plain comment with no marker", "just a plain comment, no metadata here"),
        ("empty string", ""),
        ("non-string input", None),
    ]:
        parsed = mep_meta_parser.parse_mep_meta(value)  # type: ignore[arg-type]
        if parsed is not None:
            fail(f"{label} did not return None: {parsed!r}")
            return
    ok("trivial inputs (no marker, empty string, non-string) all return None")


def check_truncated_fence_returns_none():
    body = "\n".join([
        "<!-- mep-meta -->",
        "```json",
        json.dumps(WELLFORMED_META),
        # no closing fence: the comment was cut off mid-write
    ])
    parsed = mep_meta_parser.parse_mep_meta(body)
    if parsed is not None:
        fail(f"truncated fence did not return None: {parsed!r}")
        return
    ok("truncated fence (no closing ```) returns None")


def check_missing_fence_after_marker_returns_none():
    body = "\n".join([
        "<!-- mep-meta -->",
        "no fenced block follows the marker at all",
    ])
    parsed = mep_meta_parser.parse_mep_meta(body)
    if parsed is not None:
        fail(f"marker with no fence at all did not return None: {parsed!r}")
        return
    ok("marker with no fenced block at all returns None")


def check_invalid_json_returns_none():
    body = "\n".join([
        "<!-- mep-meta -->",
        "```json",
        '{"verdict": "accepted", oops this is not json}',
        "```",
    ])
    parsed = mep_meta_parser.parse_mep_meta(body)
    if parsed is not None:
        fail(f"invalid JSON did not return None: {parsed!r}")
        return
    ok("invalid JSON inside the fence returns None")


def check_non_object_payload_returns_none():
    body = "\n".join([
        "<!-- mep-meta -->",
        "```json",
        json.dumps(["not", "an", "object"]),
        "```",
    ])
    parsed = mep_meta_parser.parse_mep_meta(body)
    if parsed is not None:
        fail(f"non-object JSON payload did not return None: {parsed!r}")
        return
    ok("a valid but non-object JSON payload (a list) returns None")


def check_second_fenced_block_is_not_swallowed():
    body = "\n".join([
        "<!-- mep-meta -->",
        "```json",
        json.dumps({"verdict": "accepted"}),
        "```",
        "",
        "quoting a submitter comment below:",
        "```json",
        json.dumps({"verdict": "should-not-be-used"}),
        "```",
    ])
    parsed = mep_meta_parser.parse_mep_meta(body)
    if parsed != {"verdict": "accepted"}:
        fail(f"parser picked up the wrong fenced block: {parsed!r}")
        return
    ok("only the first fenced block after the marker is used")


def main():
    check_wellformed_block_parses()
    check_bare_fence_without_json_tag_parses()
    check_missing_marker_returns_none()
    check_trivial_inputs_return_none()
    check_truncated_fence_returns_none()
    check_missing_fence_after_marker_returns_none()
    check_invalid_json_returns_none()
    check_non_object_payload_returns_none()
    check_second_fenced_block_is_not_swallowed()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nAll mep_meta_parser checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
