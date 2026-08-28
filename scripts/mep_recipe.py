#!/usr/bin/env python3
"""mep_recipe — validate / dry-run / apply a MEP Recipe v1 document (F6.1);
assemble-sources builds the sources block deterministically (F6.2b).

stdlib only. Reuses mep_lint discovery (Source, discover_sections,
find_fallback_subfolder, find_fallback_subfolder_by_name,
find_top_level_nested_zip, safe_rel, parse_line) — never a parallel
implementation (ADR-0138).

Usage:
  python3 scripts/mep_recipe.py validate <recipe.json>
  python3 scripts/mep_recipe.py dry-run <recipe.json> --primary PATH
      [--dep ID=PATH ...] --out DIR [--rom-name NAME]
  python3 scripts/mep_recipe.py apply <recipe.json> --primary PATH
      [--dep ID=PATH ...] --out DIR [--rom-name NAME]
  python3 scripts/mep_recipe.py assemble-sources --issue-body PATH
      --pack-url URL --pack-sha256 HEX [--classify PATH] [--out PATH]

assemble-sources parses the issue body's "External assets" Issue Form
section (ADR-0138 §12 grammar: one `<url> [<sha256>] [<size>]` dependency
per non-empty, non-`#` line) and merges the CI-computed primary sha256
with classify's `ops`/`deps`/`pack` fragment (classify itself never
computes hashes, ADR-0138 §4). It prints `recipe_status: <status>` where
status is exactly one of `absent` (no external assets declared, or
classify emitted no recipe fragment at all), `present` (recipe assembled
and, when --out is given, written there), or `refused` (an
`external_assets` line is malformed or lacks a sha256 — ADR-0138 §7/§13).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

import mep_lint

RECIPE_VERSION = 1
SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
SOURCE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
KNOWN_OPS = ("copy", "glob", "rename", "rewrite-paths")
REWRITE_TAGS = ("bgm", "sfx", "img", "background", "patch")
PATCH_SUFFIXES = (".ips", ".bps")
FENCE = re.compile(r"```mep-recipe[^\n]*\n(.*?)```", re.DOTALL)
EXTERNAL_ASSETS_LABEL = "external assets"
NO_RESPONSE = "_no response_"


class RecipeError(Exception):
    """User-facing validation or apply failure."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_recipe(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("{"):
        data = json.loads(text)
    else:
        match = FENCE.search(text)
        if not match:
            raise RecipeError(f"{path}: not JSON and no ```mep-recipe block")
        data = json.loads(match.group(1))
    if not isinstance(data, dict):
        raise RecipeError(f"{path}: recipe root must be an object")
    return data


def _safe(path: str, where: str) -> str:
    rel = mep_lint.safe_rel(path)
    if rel is None or rel == "":
        raise RecipeError(f"{where}: escaping or empty path: {path!r}")
    return rel


def _split_from(value, where: str):
    if not isinstance(value, str) or ":" not in value:
        raise RecipeError(f"{where}: 'from' must be '<source-id>:<path>'")
    source_id, _, rest = value.partition(":")
    if not SOURCE_ID.match(source_id) or not rest:
        raise RecipeError(f"{where}: invalid 'from': {value!r}")
    return source_id, rest


def _known_source_ids(recipe: dict) -> set:
    ids = {"primary"}
    for dep in (recipe.get("sources") or {}).get("deps") or []:
        if isinstance(dep, dict) and isinstance(dep.get("id"), str):
            ids.add(dep["id"])
    return ids


def validate_recipe(recipe: dict) -> list:
    """Returns a list of error strings; empty means the recipe is valid."""
    errors = []

    def fail(msg):
        errors.append(msg)

    if recipe.get("recipe") != RECIPE_VERSION:
        fail(f"'recipe' must be the integer {RECIPE_VERSION}, got {recipe.get('recipe')!r}")

    sources = recipe.get("sources")
    if not isinstance(sources, dict):
        fail("'sources' must be an object")
        sources = {}
    primary = sources.get("primary")
    if not isinstance(primary, dict):
        fail("'sources.primary' must be an object")
        primary = {}
    url = primary.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        fail("'sources.primary.url' must be an HTTPS URL")
    if not isinstance(primary.get("sha256"), str) or not SHA256_HEX.match(primary.get("sha256") or ""):
        fail("'sources.primary.sha256' must be 64 hex digits")

    dep_ids = []
    deps = sources.get("deps")
    if deps is None:
        deps = []
    if not isinstance(deps, list):
        fail("'sources.deps' must be an array")
        deps = []
    for i, dep in enumerate(deps):
        where = f"sources.deps[{i}]"
        if not isinstance(dep, dict):
            fail(f"{where} must be an object")
            continue
        dep_id = dep.get("id")
        if not isinstance(dep_id, str) or not SOURCE_ID.match(dep_id):
            fail(f"{where}.id is missing or invalid")
        elif dep_id == "primary":
            fail(f"{where}.id MUST NOT be 'primary'")
        elif dep_id in dep_ids:
            fail(f"{where}.id is duplicated: {dep_id}")
        else:
            dep_ids.append(dep_id)
        if not isinstance(dep.get("sha256"), str) or not SHA256_HEX.match(dep.get("sha256") or ""):
            fail(f"{where}.sha256 must be 64 hex digits")
        if "size" in dep and not (isinstance(dep["size"], int) and dep["size"] >= 0):
            fail(f"{where}.size must be an integer >= 0")
        if "hints" in dep:
            if not isinstance(dep["hints"], list) or not all(isinstance(h, str) for h in dep["hints"]):
                fail(f"{where}.hints must be an array of strings")
        if "user_supplied" in dep and not isinstance(dep["user_supplied"], bool):
            fail(f"{where}.user_supplied must be a boolean")

    known_ids = {"primary", *dep_ids}
    ops = recipe.get("ops")
    if not isinstance(ops, list) or not ops:
        fail("'ops' must be a non-empty array")
        ops = []
    for i, op in enumerate(ops):
        where = f"ops[{i}]"
        if not isinstance(op, dict):
            fail(f"{where} must be an object")
            continue
        kind = op.get("op")
        if kind not in KNOWN_OPS:
            fail(f"{where}: unknown op {kind!r}")
            continue
        try:
            if kind in ("copy", "glob"):
                source_id, rest = _split_from(op.get("from"), where)
                if source_id not in known_ids:
                    fail(f"{where}: unknown source-id {source_id!r}")
                if kind == "copy":
                    _safe(rest, f"{where}.from path")
                else:
                    # glob pattern: every non-meta segment must be safe
                    stripped = rest.replace("**", "x").replace("*", "x").replace("?", "x")
                    _safe(stripped or "x", f"{where}.from pattern")
                _safe(op.get("to") if isinstance(op.get("to"), str) else "", f"{where}.to")
            elif kind == "rename":
                _safe(op.get("from") if isinstance(op.get("from"), str) else "", f"{where}.from")
                _safe(op.get("to") if isinstance(op.get("to"), str) else "", f"{where}.to")
            elif kind == "rewrite-paths":
                _safe(op.get("file") if isinstance(op.get("file"), str) else "", f"{where}.file")
                tags = op.get("tags")
                if not isinstance(tags, list) or not tags:
                    fail(f"{where}.tags must be a non-empty array")
                elif any(t not in REWRITE_TAGS for t in tags):
                    fail(f"{where}.tags entries MUST be one of {REWRITE_TAGS}")
                prefix = op.get("prefix")
                if not isinstance(prefix, str) or not prefix:
                    fail(f"{where}.prefix is required")
                else:
                    _safe(prefix.rstrip("/") or prefix, f"{where}.prefix")
        except RecipeError as exc:
            fail(str(exc))

    pack = recipe.get("pack")
    if not isinstance(pack, dict):
        fail("'pack' must be an object")
        pack = {}
    for key in ("name", "version"):
        if not isinstance(pack.get(key), str) or not pack[key]:
            fail(f"'pack.{key}' is required")
    if isinstance(pack.get("version"), str) and not SEMVER.match(pack["version"]):
        fail(f"'pack.version' is not semver: {pack['version']}")
    if "mep" in pack and (not isinstance(pack["mep"], str) or not SEMVER.match(pack["mep"])):
        fail(f"'pack.mep' is not semver: {pack.get('mep')}")
    targets = pack.get("targets")
    if not isinstance(targets, list) or not targets:
        fail("'pack.targets' must be a non-empty array")
    else:
        for i, target in enumerate(targets):
            if not isinstance(target, dict) or not isinstance(target.get("sha1"), str):
                fail(f"pack.targets[{i}] needs sha1")
            elif not re.fullmatch(r"[0-9A-Fa-f]{40}", target["sha1"]):
                fail(f"pack.targets[{i}].sha1 must be 40 hex digits")
    if "patches" in pack:
        patches = pack["patches"]
        if not isinstance(patches, list):
            fail("'pack.patches' must be an array")
        else:
            for i, patch in enumerate(patches):
                if not isinstance(patch, dict):
                    fail(f"pack.patches[{i}] must be an object")
                    continue
                try:
                    _safe(patch.get("file") if isinstance(patch.get("file"), str) else "", f"pack.patches[{i}].file")
                except RecipeError as exc:
                    fail(str(exc))
    if "sections" in pack:
        sections = pack["sections"]
        if not isinstance(sections, dict) or not sections:
            fail("'pack.sections' must be a non-empty object")
        else:
            for name, sec in sections.items():
                if not isinstance(sec, dict) or "path" not in sec:
                    fail(f"pack.sections.{name} needs 'path'")
                    continue
                path = sec["path"]
                if path != "" and mep_lint.safe_rel(path) is None:
                    fail(f"pack.sections.{name}.path is unsafe: {path!r}")

    policy = recipe.get("policy")
    if policy is None:
        policy = {}
    if not isinstance(policy, dict):
        fail("'policy' must be an object")
    elif "apply_patch_only_if_complete" in policy and not isinstance(
        policy["apply_patch_only_if_complete"], bool
    ):
        fail("'policy.apply_patch_only_if_complete' must be a boolean")
    return errors


def open_primary(path: Path, rom_name: str | None):
    """Opens a primary artifact and returns (Source, root_prefix).

    Reuses mep_lint discovery; prefix is '' at the container root or
    '<subfolder>/' when the ADR-0120/0121 fallback (or nested zip) wins.
    """
    src = mep_lint.Source(path)
    rep = mep_lint.Report()
    sections = mep_lint.discover_sections(src, rep, rom_name)
    if not sections:
        nested = mep_lint.find_top_level_nested_zip(src.names)
        if nested:
            try:
                src = mep_lint.Source.from_zip_bytes(src.read(nested), label=f"{path}!{nested}")
            except zipfile.BadZipFile as exc:
                raise RecipeError(f"nested zip {nested!r} is not a zip: {exc}") from exc
            mep_lint.discover_sections(src, rep, rom_name)
    prefix = ""
    root_hits = (
        src.exists("pack.json")
        or src.exists("hires.txt")
        or any(src.exists(p) for p in mep_lint.PROBES.values())
        or src.exists(mep_lint.AUDIO_ALT_PROBE)
    )
    if not root_hits:
        fallback = mep_lint.find_fallback_subfolder(src.names)
        if not fallback and rom_name:
            fallback = mep_lint.find_fallback_subfolder_by_name(src.names, rom_name)
        if fallback:
            prefix = fallback[0] + "/"
    return src, prefix


def _rel_names(src: mep_lint.Source, prefix: str) -> list:
    names = []
    for raw in src.names:
        rel = mep_lint.safe_rel(raw)
        if rel is None or rel.endswith("/"):
            continue
        if prefix:
            if not rel.startswith(prefix):
                continue
            rel = rel[len(prefix):]
        if rel:
            names.append(rel)
    return names


def _glob_to_re(pattern: str):
    regex = ["^"]
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            regex.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            regex.append(".*")
            i += 2
        elif pattern[i] == "*":
            regex.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            regex.append("[^/]")
            i += 1
        else:
            regex.append(re.escape(pattern[i]))
            i += 1
    regex.append("$")
    return re.compile("".join(regex))


def _out_path(out: Path, rel: str) -> Path:
    dest = (out / rel).resolve()
    root = out.resolve()
    if dest != root and root not in dest.parents:
        raise RecipeError(f"output path escapes the pack directory: {rel}")
    return dest


def _write_file(out: Path, rel: str, data: bytes):
    dest = _out_path(out, rel)
    if dest.exists():
        raise RecipeError(f"refusing to overwrite existing output path: {rel}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def _is_patch_dest(rel: str) -> bool:
    lower = rel.lower()
    return lower.startswith("patches/") or lower.endswith(PATCH_SUFFIXES)


def _rewrite_hires(text: str, tags: list, prefix: str) -> str:
    if not prefix.endswith("/"):
        prefix = prefix + "/"
    out_lines = []
    for raw in text.splitlines(keepends=True):
        newline = ""
        line = raw
        if line.endswith("\n"):
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            line = line[: -len(newline)]
        stripped = line.strip()
        parsed = mep_lint.parse_line(stripped) if stripped and not stripped.startswith("#") else None
        if not parsed:
            out_lines.append(raw)
            continue
        _conds, tag, params = parsed
        if tag not in tags:
            out_lines.append(raw)
            continue
        params = params.replace("\\", "/")
        if tag == "img":
            new_params = params if params == prefix or params.startswith(prefix) else prefix + params
            rebuilt = stripped[: stripped.find(">") + 1] + new_params
        else:
            tokens = params.split(",")
            idx = 2 if tag in ("bgm", "sfx") else 0
            if len(tokens) <= idx:
                out_lines.append(raw)
                continue
            token = tokens[idx].strip().replace("\\", "/")
            if token != prefix and not token.startswith(prefix):
                tokens[idx] = prefix + token
            rebuilt = stripped[: stripped.find(">") + 1] + ",".join(tokens)
        out_lines.append(rebuilt + newline)
    return "".join(out_lines)


def _derive_sections(out: Path) -> dict:
    src = mep_lint.Source(out)
    sections = {}
    if src.exists("hires.txt"):
        sections["textures"] = {"path": ""}
    for name, probe in mep_lint.PROBES.items():
        if src.exists(probe) or (name == "audio" and src.exists(mep_lint.AUDIO_ALT_PROBE)):
            path = mep_lint.SECTION_PATHS[name]
            if name != "synth" and not path.endswith("/"):
                path = path + "/"
            sections.setdefault(name, {"path": "" if name == "textures" and src.exists("hires.txt") else path})
    if "textures" in sections and src.exists("hires.txt") and not src.exists("textures/hires.txt"):
        sections["textures"] = {"path": ""}
    return sections


def _write_pack_json(recipe: dict, out: Path, include_patches: bool):
    pack = dict(recipe["pack"])
    body = {
        "mep": pack.get("mep") or "1.1.0",
        "name": pack["name"],
        "version": pack["version"],
        "license": pack.get("license") or "NOASSERTION",
        "targets": pack["targets"],
    }
    if pack.get("author"):
        body["author"] = pack["author"]
    if include_patches and pack.get("patches"):
        body["patches"] = pack["patches"]
    sections = pack.get("sections")
    if not isinstance(sections, dict) or not sections:
        sections = _derive_sections(out)
    body["sections"] = sections
    (out / "pack.json").write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


def _verify_primary(recipe: dict, primary: Path) -> None:
    if not primary.exists():
        raise RecipeError(f"primary does not exist: {primary}")
    expected = recipe["sources"]["primary"]["sha256"].lower()
    actual = sha256_file(primary)
    if actual != expected:
        raise RecipeError(f"primary sha256 mismatch: expected {expected}, got {actual}")


def _resolve_deps(recipe: dict, deps: dict) -> tuple:
    """Hash-verifies every dep path CI supplied; anything absent from
    `deps` (every declared dep, when the caller passes none — CI's
    recipe-gate, ADR §16) is collected into `missing` instead of raising.
    """
    dep_meta = {d["id"]: d for d in recipe["sources"].get("deps") or [] if isinstance(d, dict)}
    missing = []
    opened = {}
    for dep_id, meta in dep_meta.items():
        path = deps.get(dep_id)
        if path is None:
            missing.append(dep_id)
            continue
        path = Path(path)
        if not path.exists():
            raise RecipeError(f"dep {dep_id!r} does not exist: {path}")
        actual = sha256_file(path)
        if actual != meta["sha256"].lower():
            raise RecipeError(
                f"dep {dep_id!r} sha256 mismatch: expected {meta['sha256'].lower()}, got {actual}"
            )
        opened[dep_id] = (mep_lint.Source(path), "")
    return dep_meta, missing, opened


def _check_missing_policy(recipe: dict, dep_meta: dict, missing: list) -> None:
    if not missing:
        return
    policy = recipe.get("policy") or {}
    if not policy.get("apply_patch_only_if_complete", True):
        raise RecipeError(f"missing dep(s): {', '.join(missing)}")
    for dep_id in missing:
        if not dep_meta[dep_id].get("user_supplied", True):
            raise RecipeError(f"missing required dep {dep_id!r}")


class _RunState:
    """Mutable state threaded through run_recipe's per-op handlers: open
    sources, the missing-dep set, the output dir, and which dest paths
    (`skipped_exact`, from `copy`) / dest-dir prefixes (`skipped_prefixes`,
    from `glob`, trailing "/") were left unwritten because their op's
    source_id is a missing dep. A later `rename` referencing one of those
    un-written paths — the ADR-0138 §1 reference recipe chains exactly
    this: glob a missing `audio` dep, then rename inside it — is skipped
    too instead of raising, mirroring the copy/glob missing-dep skip.
    """

    def __init__(self, out: Path, opened: dict, include_patches: bool, missing: list):
        self.out = out
        self.opened = opened
        self.include_patches = include_patches
        self.missing = missing
        self.skipped_exact = set()
        self.skipped_prefixes = []


def _record_skipped_dest(op: dict, where: str, kind: str, state: "_RunState") -> None:
    if kind == "copy":
        state.skipped_exact.add(_safe(op["to"], f"{where}.to"))
    else:
        dest_dir = _safe(op["to"].rstrip("/") or op["to"], f"{where}.to")
        state.skipped_prefixes.append(dest_dir + "/")


def _run_copy_op(op: dict, where: str, state: "_RunState", source_id: str, rest: str) -> None:
    src, prefix = state.opened[source_id]
    rel = _safe(rest, f"{where}.from path")
    full = prefix + rel
    if not src.exists(full):
        raise RecipeError(f"{where}: source file not found: {full}")
    dest = _safe(op["to"], f"{where}.to")
    if not state.include_patches and _is_patch_dest(dest):
        return
    _write_file(state.out, dest, src.read(full))


def _run_glob_op(op: dict, where: str, state: "_RunState", source_id: str, rest: str) -> None:
    src, prefix = state.opened[source_id]
    pattern = rest.replace("\\", "/")
    matcher = _glob_to_re(pattern)
    matches = [n for n in _rel_names(src, prefix) if matcher.match(n)]
    if not matches:
        raise RecipeError(f"{where}: glob matched no files: {pattern}")
    dest_dir = _safe(op["to"].rstrip("/") or op["to"], f"{where}.to")
    seen = {}
    for match in matches:
        base = match.rsplit("/", 1)[-1]
        if base in seen:
            raise RecipeError(
                f"{where}: glob basename collision {base!r} ({seen[base]} vs {match})"
            )
        seen[base] = match
        dest = f"{dest_dir}/{base}"
        if not state.include_patches and _is_patch_dest(dest):
            continue
        _write_file(state.out, dest, src.read(prefix + match))


def _run_copy_or_glob_op(op: dict, where: str, state: "_RunState") -> None:
    kind = op["op"]
    source_id, rest = _split_from(op["from"], where)
    if source_id in state.missing:
        _record_skipped_dest(op, where, kind, state)
        return
    if kind == "copy":
        _run_copy_op(op, where, state, source_id, rest)
    else:
        _run_glob_op(op, where, state, source_id, rest)


def _run_rename_op(op: dict, where: str, state: "_RunState") -> None:
    src_rel = _safe(op["from"], f"{where}.from")
    dest_rel = _safe(op["to"], f"{where}.to")
    if not state.include_patches and (_is_patch_dest(src_rel) or _is_patch_dest(dest_rel)):
        return
    src_path = _out_path(state.out, src_rel)
    if not src_path.exists():
        skipped = src_rel in state.skipped_exact or any(
            src_rel.startswith(p) for p in state.skipped_prefixes
        )
        if skipped:
            return
        raise RecipeError(f"{where}: rename source does not exist: {src_rel}")
    dest_path = _out_path(state.out, dest_rel)
    if dest_path.exists():
        raise RecipeError(f"{where}: rename dest already exists: {dest_rel}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.rename(dest_path)


def _run_rewrite_paths_op(op: dict, where: str, state: "_RunState") -> None:
    rel = _safe(op["file"], f"{where}.file")
    path = _out_path(state.out, rel)
    if not path.exists():
        raise RecipeError(f"{where}: rewrite-paths file does not exist: {rel}")
    prefix = op["prefix"].replace("\\", "/")
    text = path.read_text(encoding="utf-8", errors="replace")
    path.write_text(_rewrite_hires(text, list(op["tags"]), prefix), encoding="utf-8")


def _run_op(i: int, op: dict, state: "_RunState") -> None:
    kind = op["op"]
    where = f"ops[{i}]"
    if kind in ("copy", "glob"):
        _run_copy_or_glob_op(op, where, state)
    elif kind == "rename":
        _run_rename_op(op, where, state)
    elif kind == "rewrite-paths":
        _run_rewrite_paths_op(op, where, state)


def run_recipe(recipe: dict, primary: Path, deps: dict, out: Path, rom_name: str | None) -> None:
    errors = validate_recipe(recipe)
    if errors:
        raise RecipeError("\n".join(errors))
    _verify_primary(recipe, primary)

    dep_meta, missing, opened = _resolve_deps(recipe, deps)
    _check_missing_policy(recipe, dep_meta, missing)

    primary_src, primary_prefix = open_primary(primary, rom_name)
    opened["primary"] = (primary_src, primary_prefix)

    if out.exists() and any(out.iterdir()):
        raise RecipeError(f"--out is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)

    state = _RunState(out, opened, include_patches=not missing, missing=missing)
    for i, op in enumerate(recipe["ops"]):
        _run_op(i, op, state)

    _write_pack_json(recipe, out, include_patches=state.include_patches)


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
    recipe): 'absent' (no external assets declared, or classify emitted no
    recipe fragment at all) / 'present' / 'refused' (a dep line is
    malformed or lacks a sha256); recipe is None unless status=='present'.
    """
    if not SHA256_HEX.match(pack_sha256 or ""):
        raise RecipeError(f"--pack-sha256 must be 64 hex digits, got {pack_sha256!r}")
    lines = _asset_lines(extract_issue_field_section(issue_body, EXTERNAL_ASSETS_LABEL))
    if not lines or not _classify_has_recipe_fragment(classify):
        return "absent", None
    try:
        assets = [_parse_asset_line(line) for line in lines]
        deps = merge_recipe_deps(classify.get("deps") or [], assets)
    except RecipeError:
        return "refused", None
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


def _parse_kv_args(argv):
    command = argv[1] if len(argv) > 1 else ""
    recipe = None
    primary = None
    out = None
    rom_name = None
    deps = {}
    rest = argv[2:]
    i = 0
    positional = []
    while i < len(rest):
        arg = rest[i]
        if arg == "--primary" and i + 1 < len(rest):
            primary = Path(rest[i + 1])
            i += 2
        elif arg == "--out" and i + 1 < len(rest):
            out = Path(rest[i + 1])
            i += 2
        elif arg == "--rom-name" and i + 1 < len(rest):
            rom_name = rest[i + 1]
            i += 2
        elif arg == "--dep" and i + 1 < len(rest):
            spec = rest[i + 1]
            if "=" not in spec:
                raise RecipeError("--dep expects ID=PATH")
            dep_id, _, path = spec.partition("=")
            deps[dep_id] = Path(path)
            i += 2
        elif arg.startswith("--"):
            raise RecipeError(f"unknown flag: {arg}")
        else:
            positional.append(arg)
            i += 1
    if positional:
        recipe = Path(positional[0])
    return command, recipe, primary, deps, out, rom_name


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 3:
        print(__doc__)
        return 2
    if argv[1] == "assemble-sources":
        return cmd_assemble_sources(argv[2:])
    try:
        command, recipe_path, primary, deps, out, rom_name = _parse_kv_args(argv)
    except RecipeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if command not in ("validate", "dry-run", "apply") or recipe_path is None:
        print(__doc__)
        return 2
    try:
        recipe = load_recipe(recipe_path)
        if command == "validate":
            errors = validate_recipe(recipe)
            if errors:
                for item in errors:
                    print(f"error: {item}", file=sys.stderr)
                return 1
            print(f"validate: {recipe_path} is a valid MEP Recipe v1 document")
            return 0
        if primary is None or out is None:
            raise RecipeError(f"{command} requires --primary and --out")
        run_recipe(recipe, primary, deps, out, rom_name)
        if command == "dry-run":
            rc = mep_lint.main(["mep_lint.py", str(out), *( [rom_name] if rom_name else [] ), "--quiet"])
            if rc != 0:
                raise RecipeError(f"dry-run produced a pack mep_lint.py rejected (exit {rc})")
            print(f"dry-run: wrote lint-clean pack to {out}")
        else:
            print(f"apply: wrote pack to {out}")
        return 0
    except RecipeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if command in ("dry-run", "apply") and out is not None and out.exists():
            # Leave the partial tree for diagnosis; callers using a tempdir
            # still clean up on process exit.
            pass
        return 1
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
