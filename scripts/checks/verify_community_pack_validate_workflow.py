#!/usr/bin/env python3
"""Structural checker for community-pack-validate.yml (AC-2, AC-6 validate-side).

Parses .github/workflows/community-pack-validate.yml with PyYAML and does
targeted substring/regex checks against the raw text for facts that don't
have a stable YAML shape (values embedded inside `if:`/`run:` strings, the
classification prompt, top-of-file comments).

The AC-6 cross-check below is a LITERAL `uses:`/string match against this
workflow's own text only — it never opens, reads, or parses
community-pack-catalog.yml (that file's own structural checker, from a
different task, covers its side of AC-6).

Usage: python3 scripts/checks/verify_community_pack_validate_workflow.py
"""
import re
import sys
from pathlib import Path

import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / ".github" / "workflows" / "community-pack-validate.yml"
)

REQUIRED_IDS = {
    "PVT_kwHOB1MsbM4BhjpN": "Project node id",
    "PVTSSF_lAHOB1MsbM4BhjpNzhge86c": "Status field id",
    "5173b5cd": "Status option: Novo envio",
    "51951f52": "Status option: Em validação",
    "227e4623": "Status option: Inválido",
    "39e4f3a1": "Status option: Aceito parcial HD Mesen",
    "cd763737": "Status option: Aceito MEP completo",
    "PVTF_lAHOB1MsbM4BhjpNzhge9Is": "Pack Hash field id",
}

HOST_ALLOWLIST = (
    "github.com",
    "raw.githubusercontent.com",
    "gist.githubusercontent.com",
    "gist.github.com",
)

ACEITO_MARKERS = ("STATUS_ACEITO_PARCIAL", "STATUS_ACEITO_COMPLETO", "aceito")

FAILURES = []


def fail(msg):
    FAILURES.append(msg)


def load():
    if not WORKFLOW_PATH.is_file():
        fail(f"missing file: {WORKFLOW_PATH}")
        return "", {}
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        fail(f"YAML did not parse: {exc}")
        data = {}
    return text, data


def check_workflow_call_inputs(data):
    # PyYAML resolves the bare `on:` key to the boolean True (YAML 1.1).
    on_block = data.get("on", data.get(True, {})) or {}
    wc = on_block.get("workflow_call")
    if not wc:
        fail("workflow_call trigger not declared under on:")
        return
    inputs = wc.get("inputs", {})
    for name in ("issue_number", "pack_url", "mode"):
        if name not in inputs:
            fail(f"workflow_call.inputs missing '{name}'")


def check_ids(text):
    for id_value, label in REQUIRED_IDS.items():
        if id_value not in text:
            fail(f"missing required id ({label}): {id_value}")


def check_project_number_only(text):
    if "PROJECT_NUMBER: 3" not in text:
        fail("PROJECT_NUMBER is not pinned to 3")
    for m in re.finditer(r"gh project item-(?:add|list)\s+(\d+)\b", text):
        fail(f"gh project call hardcodes a non-variable project number: {m.group(0)}")
    for m in re.finditer(r'gh project item-(?:add|list)\s+"\$([A-Z_]+)"', text):
        if m.group(1) != "PROJECT_NUMBER":
            fail(f"gh project call uses an unexpected project-number variable: {m.group(0)}")


def check_host_allowlist(text):
    for host in HOST_ALLOWLIST:
        if host not in text:
            fail(f"host allow-list missing host: {host}")
    if "/releases/" not in text:
        fail("host allow-list missing github.com /releases/ path restriction")


def check_size_cap(text):
    if "314572800" not in text:
        fail("300MB cap constant (314572800 bytes) not found")
    if "max-filesize" not in text:
        fail("curl --max-filesize (during-download cap) not found")
    if "content-length" not in text.lower():
        fail("pre-download Content-Length check not found")


def check_hash_write(text):
    if "sha256sum" not in text:
        fail("sha256 computation (sha256sum) not found")
    if "PACK_HASH_FIELD_ID" not in text:
        fail("Pack Hash field id constant not referenced")
    if "independent of the verdict" not in text:
        fail("no comment documenting the unconditional (always) Pack Hash write")


def check_mep_lint_call(text):
    if "python3 scripts/mep_lint.py" not in text:
        fail("exact 'python3 scripts/mep_lint.py' invocation not found")


def check_claude_action(text):
    if "anthropics/claude-code-action" not in text:
        fail("anthropics/claude-code-action not used")
    if "disallowed_tools" not in text or "Bash" not in text:
        fail("Claude Code Action step does not explicitly disallow Bash")
    lowered = text.lower()
    has_data_word = "dado" in lowered or "data" in lowered
    has_not_instruction = "nunca uma instrução" in lowered or "never" in lowered
    if not (has_data_word and has_not_instruction):
        fail("prompt lacks an explicit data-not-instruction clause")


def check_secret_name_comment(text):
    header = "\n".join(text.splitlines()[:15])
    for secret in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        if secret not in header:
            fail(f"top-of-file comment does not name required secret: {secret}")


def check_catalog_dispatch_gated_on_aceito(text):
    if "community-pack-catalog.yml" not in text:
        fail("no literal reference to community-pack-catalog.yml (dispatch/uses)")
        return
    blocks = [b for b in text.split("\n      - name:") if "community-pack-catalog.yml" in b]
    if not any(any(m in b for m in ACEITO_MARKERS) for b in blocks):
        fail("community-pack-catalog.yml call is not gated on an Aceito* status")


CHECKS = (
    check_ids,
    check_project_number_only,
    check_host_allowlist,
    check_size_cap,
    check_hash_write,
    check_mep_lint_call,
    check_claude_action,
    check_secret_name_comment,
    check_catalog_dispatch_gated_on_aceito,
)


def main():
    text, data = load()
    if text:
        check_workflow_call_inputs(data)
        for check in CHECKS:
            check(text)
    if FAILURES:
        print(f"FAIL ({len(FAILURES)} issue(s)):")
        for msg in FAILURES:
            print(f"  - {msg}")
        return 1
    print("PASS: community-pack-validate.yml structural checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
