#!/usr/bin/env python3
"""mep_recipe_assemble — CI-side recipe-assembly for mep_recipe.py's
assemble-sources subcommand (F6.2b, split out per ADR-0138 Clarification
§23 / F6.2c: the file-size guardrail reads "one verifier"/"one script" as
one *entry point*, so this sibling stdlib module may hold the CI-only
assembly code as long as `mep_recipe.py` keeps validate/dry-run/apply and
its dispatch, and shares RecipeError/SHA256_HEX/RECIPE_VERSION with this
module instead of redefining them).

stdlib only. Imports RecipeError/SHA256_HEX/RECIPE_VERSION from the leaf
module `mep_recipe_common` (never from `mep_recipe`, so there is no import
cycle — ADR-0138 §24); never re-implements mep_lint discovery (this module
does no zip/pack I/O at all, only issue-body text parsing and dict merging).

`mep_recipe.py` re-exports `assemble_sources`/`cmd_assemble_sources` as a
back-compat facade and dispatches its `assemble-sources` CLI subcommand
here; new code imports from this module directly.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from mep_recipe_common import RECIPE_VERSION, RecipeError, SHA256_HEX

EXTERNAL_ASSETS_LABEL = "external assets"
NO_RESPONSE = "_no response_"


def extract_issue_field_section(body: str, label: str) -> str:
    """Text under a GitHub Issue Form '### <label>...' heading, up to the
    next '### ' heading or the end of the body. Empty string when the
    heading is absent (Issue Forms always emit one heading per field, so
    a missing heading means the caller is looking at the wrong body).
    """
    heading = re.compile(rf"^###\s*{re.escape(label)}\b.*$", re.IGNORECASE | re.MULTILINE)
    match = heading.search(body)
    if not match:
        return ""
    rest = body[match.end():]
    next_heading = re.search(r"^###\s", rest, re.MULTILINE)
    return rest[: next_heading.start()] if next_heading else rest


def _asset_lines(section: str) -> list:
    lines = []
    for raw in section.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.lower() == NO_RESPONSE:
            continue
        lines.append(line)
    return lines


def _parse_asset_line(line: str) -> dict:
    """Parses one `<url> [<sha256>] [<size>]` line (ADR-0138 §12).

    Raises RecipeError for a bad URL, a missing/malformed sha256 (reusing
    SHA256_HEX rather than a new regex), or a non-decimal size — every one
    of those means "no usable recipe" (§7) for the whole submission.
    """
    parts = line.split()
    if not (1 <= len(parts) <= 3):
        raise RecipeError(f"malformed external_assets line: {line!r}")
    url = parts[0]
    if not url.startswith("https://"):
        raise RecipeError(f"external_assets url must be HTTPS: {url!r}")
    if len(parts) < 2:
        raise RecipeError(f"external_assets line missing sha256: {line!r}")
    sha256 = parts[1]
    if not SHA256_HEX.match(sha256):
        raise RecipeError(f"external_assets sha256 is malformed: {sha256!r}")
    size = None
    if len(parts) == 3:
        if not parts[2].isdigit():
            raise RecipeError(f"external_assets size must be decimal bytes: {parts[2]!r}")
        size = int(parts[2])
    return {"url": url, "sha256": sha256.lower(), "size": size}


def _normalize_hint_url(url: str) -> str:
    """Trailing-slash-insensitive comparison key for hint/line URL matching
    (a bare cosmetic difference must not flip a real match into 'refused').
    """
    return url.rstrip("/")


def _classify_deps_by_url(classify_deps: list) -> dict:
    by_url = {}
    for dep in classify_deps:
        if not isinstance(dep, dict):
            raise RecipeError("classify dep entry must be an object")
        for url in dep.get("hints") or []:
            by_url.setdefault(_normalize_hint_url(url), dep)
    return by_url


def _synth_dep_id(seed: int, taken: set) -> str:
    """Deterministic dep id for a line that no classify dep hints at —
    ADR-0138 §12 makes the line itself the authoritative dependency, so it
    still needs an id even without classify metadata to borrow one from.
    """
    n = seed
    candidate = f"ext{n}"
    while candidate == "primary" or candidate in taken:
        n += 1
        candidate = f"ext{n}"
    return candidate


def merge_recipe_deps(classify_deps: list, assets: list) -> list:
    """Builds one MEP Recipe dep per parsed `external_assets` line — the
    lines are the authoritative dependency list (ADR-0138 §12: "one
    dependency per non-empty line"), so every line becomes a dep even when
    classify's `deps[]` has no matching entry (fewer classify deps than
    lines, or `deps: []` outright, must never silently drop a declared
    asset). Each line is matched to classify's non-derivable id/hints/
    license/user_supplied fragment by its hints URL when one exists
    (classify never sees a hash, ADR-0138 §4/§11); a line with no classify
    match gets a synthesized id and hints=[url] instead of being skipped.
    """
    by_url = _classify_deps_by_url(classify_deps)
    merged = []
    taken_ids = set()
    for i, asset in enumerate(assets):
        dep = by_url.get(_normalize_hint_url(asset["url"]))
        if dep is not None:
            merged_dep = dict(dep)
        else:
            merged_dep = {"id": _synth_dep_id(i + 1, taken_ids), "hints": [asset["url"]], "user_supplied": True}
        taken_ids.add(merged_dep.get("id"))
        # sha256/size are always the deterministic step's to set (ADR-0138
        # §4/§11: submitter-declared, never classify's) — drop whatever
        # classify's copied dep fragment carried before applying the parsed
        # line's values, so a classify-supplied size never survives a
        # size-less line by merely being left untouched.
        merged_dep.pop("size", None)
        # ADR-0138 §11/§16 (MEP-recipe-v1 §3.3): every dep built from an
        # external_assets line is submitter-supplied by definition — the
        # client MUST NOT fetch it itself — so classify never gets to say
        # otherwise (§4's `user_supplied` is decoration, §11 wins).
        merged_dep["user_supplied"] = True
        merged_dep["sha256"] = asset["sha256"]
        if asset.get("size") is not None:
            merged_dep["size"] = asset["size"]
        merged.append(merged_dep)
    return merged


def _build_present_recipe(classify: dict, pack_url: str, pack_sha256: str, deps: list) -> dict:
    recipe = {
        "recipe": RECIPE_VERSION,
        "sources": {
            "primary": {"url": pack_url, "sha256": pack_sha256.lower()},
            "deps": deps,
        },
        "ops": classify.get("ops") or [],
        "pack": classify.get("pack") or {},
    }
    if "policy" in classify:
        recipe["policy"] = classify["policy"]
    return recipe


def _classify_has_recipe_fragment(classify: dict | None) -> bool:
    """True only when classify emitted actual ops/deps/pack *content*.

    The same F6.2b work narrows the classify JSON schema to
    `required: ["ops", "deps", "pack"]`, so all three keys are always
    present — literal key-presence can never distinguish a genuine
    split-pack fragment from a non-split pack's empty defaults
    (`{"ops": [], "deps": [], "pack": {}}`). Checking for non-empty
    content instead keeps that case mapped to 'absent' (ADR-0138 §7)
    instead of a schema-clean-looking 'present' that validate_recipe
    would reject (ops/pack are required non-empty), which would wrongly
    downgrade an otherwise-accepted plain pack to invalid (§2/§10).
    """
    if not classify:
        return False
    return bool(classify.get("ops")) or bool(classify.get("deps")) or bool(classify.get("pack"))


def assemble_sources(issue_body: str, classify: dict | None, pack_url: str, pack_sha256: str):
    """Assembles `sources` from the issue body + CI hash + classify's
    ops/deps/pack fragment (ADR-0138 §4/§7/§12/§13). Returns (status,
    recipe): 'refused' (a declared dep line is malformed or lacks a sha256 —
    checked first, §13) / 'absent' (no lines, or well-formed lines but
    classify emitted no recipe content) / 'present'; recipe is None unless
    status=='present'.
    """
    if not SHA256_HEX.match(pack_sha256 or ""):
        raise RecipeError(f"--pack-sha256 must be 64 hex digits, got {pack_sha256!r}")
    lines = _asset_lines(extract_issue_field_section(issue_body, EXTERNAL_ASSETS_LABEL))
    if not lines:
        return "absent", None
    # ADR-0138 §13 precedence: the declared lines are parsed BEFORE the
    # classify fragment is consulted, so a hash-less/malformed line is
    # `refused` (submitter gets the sha256 guidance) even when classify saw
    # a complete-looking HD pack and emitted no recipe content.
    try:
        assets = [_parse_asset_line(line) for line in lines]
    except RecipeError:
        return "refused", None
    if not _classify_has_recipe_fragment(classify):
        return "absent", None
    deps = merge_recipe_deps(classify.get("deps") or [], assets)
    return "present", _build_present_recipe(classify, pack_url, pack_sha256, deps)


def _parse_assemble_args(rest: list) -> dict:
    args = {"issue_body": None, "classify": None, "pack_url": None, "pack_sha256": None, "out": None}
    flags = {
        "--issue-body": "issue_body",
        "--classify": "classify",
        "--pack-url": "pack_url",
        "--pack-sha256": "pack_sha256",
        "--out": "out",
    }
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg in flags and i + 1 < len(rest):
            args[flags[arg]] = rest[i + 1]
            i += 2
        else:
            raise RecipeError(f"assemble-sources: unknown or incomplete flag: {arg}")
    return args


def cmd_assemble_sources(rest: list) -> int:
    try:
        args = _parse_assemble_args(rest)
        for key in ("issue_body", "pack_url", "pack_sha256"):
            if not args[key]:
                raise RecipeError(f"assemble-sources requires --{key.replace('_', '-')}")
        body = Path(args["issue_body"]).read_text(encoding="utf-8")
        classify = json.loads(Path(args["classify"]).read_text(encoding="utf-8")) if args["classify"] else None
        status, recipe = assemble_sources(body, classify, args["pack_url"], args["pack_sha256"])
    except RecipeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: invalid classify JSON: {exc}", file=sys.stderr)
        return 2
    if status == "present":
        if not args["out"]:
            print("error: assemble-sources requires --out when a recipe is assembled", file=sys.stderr)
            return 2
        Path(args["out"]).write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")
    print(f"recipe_status: {status}")
    return 0
