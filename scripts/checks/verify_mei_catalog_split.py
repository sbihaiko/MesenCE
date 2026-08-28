#!/usr/bin/env python3
"""AC-4 (F6.3b, ADR-0138 §28/§35) — the community pack catalog generator is
split into `mei_catalog_entry.py` (MEI entry assembly), `community_pack_
markdown.py` (Markdown rendering), and a fetch/orchestration facade
(`generate_community_pack_catalog.py`), each at or under the 200-line
guardrail; the assembly module self-checks entries through `mei_rules`
before they are kept, and the facade still exposes the five names
`verify_mei_catalog_generator.py` imports.

Offline, no-`gh`, no-network structural checker (mirrors verify_mei_
catalog_generator.py's own pattern): imports the real modules and inspects
their real source text/attributes -- never invokes `main()`.

Checks:
  1. mei_rules.py / mei_catalog_entry.py / community_pack_markdown.py /
     generate_community_pack_catalog.py each have <= 200 lines.
  2. mei_catalog_entry.py imports mei_rules and calls
     mei_rules.mei_entry_conforms and mei_rules.resolve_kind somewhere in
     its own source (never a locally re-implemented copy of either).
  3. community_pack_markdown.py defines build_markdown/render_table/
     build_row.
  4. The facade still exposes (as real attributes) build_pack_entry,
     mei_entry_conforms, normalized_rom_sha1, STATUS_MEP_COMPLETO, and
     STATUS_HD_PARCIAL -- the five names verify_mei_catalog_generator.py
     imports via `gen.<name>` -- and mei_entry_conforms there really is
     mei_rules.mei_entry_conforms (not a second, independent copy).
  5. Behavioral (real modules, no mocks): mei_catalog_entry.build_catalog
     drops a non-conforming entry (kind "mep" missing version/mep) rather
     than writing it into the catalog document, self-checking via
     mei_rules -- never trusting the caller to have filtered already.

Usage: python3 scripts/checks/verify_mei_catalog_split.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = ROOT / "scripts"

LINE_LIMIT = 200
SPLIT_FILES = [
    SCRIPTS_DIR / "mei_rules.py",
    SCRIPTS_DIR / "mei_catalog_entry.py",
    SCRIPTS_DIR / "community_pack_markdown.py",
    SCRIPTS_DIR / "generate_community_pack_catalog.py",
]
FACADE_NAMES = ["build_pack_entry", "mei_entry_conforms", "normalized_rom_sha1",
                "STATUS_MEP_COMPLETO", "STATUS_HD_PARCIAL"]

sys.path.insert(0, str(SCRIPTS_DIR))
import mei_rules  # noqa: E402
import mei_catalog_entry  # noqa: E402
import community_pack_markdown  # noqa: E402
import generate_community_pack_catalog as gen  # noqa: E402


def check_line_limits(failures):
    for path in SPLIT_FILES:
        if not path.exists():
            failures.append(f"missing file: {path}")
            continue
        n = len(path.read_text(encoding="utf-8").splitlines())
        if n > LINE_LIMIT:
            failures.append(f"{path.name} has {n} lines, exceeds the {LINE_LIMIT}-line guardrail")


def check_entry_module_uses_mei_rules(failures):
    text = (SCRIPTS_DIR / "mei_catalog_entry.py").read_text(encoding="utf-8")
    if "import mei_rules" not in text:
        failures.append("mei_catalog_entry.py does not import mei_rules")
    if "mei_rules.mei_entry_conforms" not in text:
        failures.append("mei_catalog_entry.py never calls mei_rules.mei_entry_conforms "
                         "(§28 self-check)")
    if "mei_rules.resolve_kind" not in text:
        failures.append("mei_catalog_entry.py never calls mei_rules.resolve_kind (§29)")


def check_markdown_module_shape(failures):
    for name in ("build_markdown", "render_table", "build_row"):
        if not hasattr(community_pack_markdown, name):
            failures.append(f"community_pack_markdown.py does not define {name}")


def check_facade_reexports(failures):
    for name in FACADE_NAMES:
        if not hasattr(gen, name):
            failures.append(f"generate_community_pack_catalog.py no longer exposes {name} "
                             f"(verify_mei_catalog_generator.py needs gen.{name})")
    if hasattr(gen, "mei_entry_conforms") and gen.mei_entry_conforms is not mei_rules.mei_entry_conforms:
        failures.append("gen.mei_entry_conforms is not mei_rules.mei_entry_conforms "
                         "(a second, independent copy exists)")


def check_build_catalog_self_checks(failures):
    conforming = {"name": "A", "game": "A", "system": "nes", "rom": {},
                  "url": "https://example.org/a.zip", "sha256": "a" * 64, "kind": "hd-legacy"}
    non_conforming = {"name": "B", "game": "B", "system": "nes", "rom": {},
                       "url": "https://example.org/b.zip", "sha256": "b" * 64, "kind": "mep"}
    catalog = mei_catalog_entry.build_catalog([conforming, non_conforming], "2026-01-01")
    packs = catalog.get("packs", [])
    if non_conforming in packs:
        failures.append("build_catalog kept a non-conforming 'mep' entry missing version/mep "
                         "(self-check via mei_rules did not run)")
    if conforming not in packs:
        failures.append("build_catalog dropped a conforming entry it should have kept")


def main():
    failures = []
    check_line_limits(failures)
    check_entry_module_uses_mei_rules(failures)
    check_markdown_module_shape(failures)
    check_facade_reexports(failures)
    check_build_catalog_self_checks(failures)
    if failures:
        print("FAIL: AC-4 (MEI catalog generator split)")
        for item in failures:
            print(f" - {item}")
        return 1
    print("PASS: AC-4 (mei_rules/mei_catalog_entry/community_pack_markdown/"
          "generate_community_pack_catalog are each <= 200 lines, the assembly "
          "module self-checks via mei_rules, and the facade re-exports stay intact)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
