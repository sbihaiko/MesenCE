#!/usr/bin/env python3
"""Framework-free checks for the ADR-0138 §33 "shortest safe fence" rule
(`scripts/mep_recipe_common.py`'s `choose_fence`/`find_fenced_block`) and
its use by `scripts/mep_recipe.py`'s `FENCE`/`load_recipe`.

Acceptance (F6.3b, AC-7/AC-9):
  * a payload embedding backtick runs of varying lengths round-trips
    byte-for-byte through the shared choose-fence writer helper and
    `mep_recipe.load_recipe`'s length-matched reader
  * the plain 3-backtick case (no embedded backticks) is unaffected
  * `load_recipe`'s pre-existing "not JSON and no fence" failure mode is
    unchanged

Usage: python3 scripts/test_mep_recipe_fence.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPTS))
import mep_recipe  # noqa: E402
import mep_recipe_common  # noqa: E402

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def _write_fenced_document(tmp: Path, payload: str) -> Path:
    """Wrap `payload` in a ```mep-recipe fence chosen by the shared rule,
    exactly as a well-behaved writer would, and write it to a file."""
    fence = mep_recipe_common.choose_fence(payload)
    document = f"{fence}mep-recipe\n{payload}\n{fence}\n"
    path = tmp / "recipe.mep-recipe.md"
    path.write_text(document, encoding="utf-8")
    return path


def check_plain_payload_uses_min_fence_and_roundtrips():
    recipe = {"recipe": 1, "ops": [], "note": "no backticks here at all"}
    payload = json.dumps(recipe, indent=2, sort_keys=True)
    fence = mep_recipe_common.choose_fence(payload)
    if fence != "```":
        fail(f"plain payload with no backticks should choose a 3-backtick fence, got {fence!r}")
        return
    with tempfile.TemporaryDirectory() as tmp_s:
        path = _write_fenced_document(Path(tmp_s), payload)
        data = mep_recipe.load_recipe(path)
    if data != recipe:
        fail(f"plain 3-backtick round trip mismatch: {data!r} != {recipe!r}")
        return
    if json.dumps(data, indent=2, sort_keys=True) != payload:
        fail("plain 3-backtick round trip is not byte-for-byte identical to the original payload")
        return
    ok("payload with no embedded backticks round-trips through a 3-backtick fence (no regression)")


def _embedded_backtick_recipe() -> dict:
    return {
        "recipe": 1,
        "ops": [],
        "hints": "single ` double `` triple ``` quadruple ```` quintuple ````` end",
        "license": "contains a fenced block already: ```json {}```",
    }


def check_embedded_backtick_runs_roundtrip_byte_for_byte():
    recipe = _embedded_backtick_recipe()
    payload = json.dumps(recipe, indent=2, sort_keys=True)
    longest_run = mep_recipe_common.max_backtick_run(payload)
    fence = mep_recipe_common.choose_fence(payload)
    if len(fence) <= longest_run or longest_run < 5:
        fail(f"fixture/fence mismatch: fence={len(fence)} backticks, longest run in payload={longest_run}")
        return
    with tempfile.TemporaryDirectory() as tmp_s:
        path = _write_fenced_document(Path(tmp_s), payload)
        data = mep_recipe.load_recipe(path)
    if data != recipe:
        fail(f"backtick-laden round trip mismatch: {data!r} != {recipe!r}")
        return
    if json.dumps(data, indent=2, sort_keys=True) != payload:
        fail("backtick-laden round trip is not byte-for-byte identical to the original payload")
        return
    ok(f"payload embedding backtick runs up to length {longest_run} round-trips byte-for-byte "
       f"through a {len(fence)}-backtick fence")


def check_choose_fence_is_strictly_longer_than_any_run():
    cases = [
        ("", "```"),
        ("no backticks", "```"),
        ("one ` run", "```"),
        ("two `` run", "```"),
        ("three ``` run", "````"),
        ("five ````` run", "``````"),
    ]
    for payload, expected in cases:
        got = mep_recipe_common.choose_fence(payload)
        if got != expected:
            fail(f"choose_fence({payload!r}) = {got!r}, expected {expected!r}")
            return
    ok("choose_fence always picks the shortest fence strictly longer than any run already present")


def check_find_fenced_block_matches_closer_by_exact_length_not_prefix():
    # The body embeds a 3-backtick run; the real fence is 4 backticks, so a
    # reader that only checked "starts with the same backticks" (a prefix
    # match) could stop at the embedded run instead of the real closer.
    body = "before ``` middle"
    text = f"````mep-recipe\n{body}\n````\nTRAILER"
    recovered = mep_recipe_common.find_fenced_block(text, "mep-recipe")
    if recovered != body + "\n":
        fail(f"find_fenced_block matched the wrong closer: {recovered!r} != {body + chr(10)!r}")
        return
    ok("find_fenced_block matches the closing fence by exact length, not a shorter embedded run")


def check_load_recipe_still_raises_with_no_fence():
    with tempfile.TemporaryDirectory() as tmp_s:
        path = Path(tmp_s) / "recipe.mep-recipe.md"
        path.write_text("not json and no fence block here", encoding="utf-8")
        try:
            mep_recipe.load_recipe(path)
        except mep_recipe.RecipeError as exc:
            if "not JSON and no" not in str(exc):
                fail(f"unexpected RecipeError message for a fence-less document: {exc}")
                return
            ok("load_recipe still raises RecipeError when neither JSON nor a fenced block is present")
            return
        fail("load_recipe did not raise for a document that is neither JSON nor fenced")


def main():
    check_plain_payload_uses_min_fence_and_roundtrips()
    check_embedded_backtick_runs_roundtrip_byte_for_byte()
    check_choose_fence_is_strictly_longer_than_any_run()
    check_find_fenced_block_matches_closer_by_exact_length_not_prefix()
    check_load_recipe_still_raises_with_no_fence()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nAll mep_recipe fence checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
