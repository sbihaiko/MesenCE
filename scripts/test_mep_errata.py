#!/usr/bin/env python3
"""ADR-0152 known-missing errata: schema rules and the two-gate parity contract.

The contract this protects is the one bug #155 broke: the submission gate and
the runtime gate must reach the same verdict on the same target. Here that is
checked structurally - both gates resolve declarations through
scripts/mep_errata.py, so the assertion is that neither one grew its own parser.
"""
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import mep_errata  # noqa: E402

FAILURES = []
SHA = "a" * 64


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL {msg}")


def ok(msg):
    print(f"PASS {msg}")


def write_errata(tmp, **overrides):
    entry = {
        "manifest": "hires.txt",
        "tag": "background",
        "target": "missing.png",
        "reason": "x" * 45,
        "reviewed_in": "https://github.com/sbihaiko/MesenCE/issues/1",
    }
    entry.update(overrides.pop("entry", {}))
    doc = {"artifact_sha256": SHA, "known_missing": [entry]}
    doc.update(overrides)
    path = Path(tmp) / f"{doc['artifact_sha256']}.json"
    path.write_text(json.dumps(doc))
    return path


def expect_rejected(tmp, label, **overrides):
    path = write_errata(tmp, **overrides)
    try:
        mep_errata.load(path)
    except mep_errata.ErrataError:
        ok(f"rejected: {label}")
    else:
        fail(f"accepted an errata it should reject: {label}")


def make_pack(tmp):
    """A minimal NES pack whose hires.txt references one absent PNG."""
    pack = Path(tmp) / "pack.zip"
    hires = (
        "<ver>106\n"
        "<scale>1\n"
        "<supportedRom>DAB79C84934F9AA5DB4E7DAD390E5D0C12443FA2\n"
        "<background>missing.png,1\n"
    )
    with zipfile.ZipFile(pack, "w") as z:
        z.writestr("hires.txt", hires)
    return pack


def lint(pack, errata=None):
    cmd = [sys.executable, str(REPO / "scripts" / "mep_lint.py"), str(pack)]
    if errata:
        cmd += ["--errata", str(errata)]
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        # --- schema ---
        good = write_errata(tmp)
        try:
            errata = mep_errata.load(good)
            ok(f"accepted a well-formed errata ({len(errata.entries)} declaration)")
        except mep_errata.ErrataError as exc:
            fail(f"rejected a well-formed errata: {exc}")

        expect_rejected(tmp, "a wildcard target", entry={"target": "select*.png"})
        expect_rejected(tmp, "a tag outside img/background", entry={"tag": "bgm"})
        expect_rejected(tmp, "a reason too short to be a justification", entry={"reason": "dead line"})
        expect_rejected(tmp, "a missing reviewed_in", entry={"reviewed_in": "  "})
        expect_rejected(tmp, "an empty known_missing list", known_missing=[])
        expect_rejected(tmp, "a non-hex artifact_sha256", artifact_sha256="z" * 64)

        # File name must equal the hash: an errata that does not name its
        # artifact could be applied to a pack nobody reviewed it against.
        stray = Path(tmp) / "not-the-hash.json"
        stray.write_text(json.dumps({"artifact_sha256": SHA, "known_missing": [
            {"manifest": "hires.txt", "tag": "background", "target": "m.png",
             "reason": "y" * 45, "reviewed_in": "https://example.invalid/pr/1"}]}))
        try:
            mep_errata.load(stray)
        except mep_errata.ErrataError:
            ok("rejected: file name that does not match artifact_sha256")
        else:
            fail("accepted an errata whose file name is not its artifact hash")

        # --- manifest identity across the two gates ---
        # mep_lint sees "hires.txt" inside the archive; the smoke gate sees
        # "<pack>/textures/hires.txt" on disk. Both must resolve the same entry,
        # or a target pardoned by one gate fails the other (bug #155).
        errata = mep_errata.load(write_errata(tmp))
        in_archive = errata.covers("hires.txt", "background", "missing.png")
        on_disk = errata.covers("/x/The Legend of Zelda/mep/textures/hires.txt", "background", "missing.png")
        if in_archive and on_disk:
            ok("same declaration resolves from the archive path and the installed path")
        else:
            fail(f"manifest identity diverges between gates (archive={in_archive}, installed={on_disk})")

        if errata.covers("hires.txt", "background", "other.png"):
            fail("an undeclared target was treated as declared")
        else:
            ok("an undeclared target stays undeclared")

        # --- lint integration ---
        pack = make_pack(tmp)
        before = lint(pack)
        if before.returncode == 1 and "<background> missing.png does not exist" in before.stdout:
            ok("without an errata the unresolvable target is an error (ADR-0151 intact)")
        else:
            fail(f"expected an ADR-0151 error without errata; rc={before.returncode}")

        real = write_errata(tmp)
        after = lint(pack, real)
        if after.returncode == 0 and "declared known-missing" in after.stdout:
            ok("with an errata the declared target passes and says who declared it")
        else:
            fail(f"errata did not clear the declared target; rc={after.returncode}")

        if "not by the author" in after.stdout:
            ok("the finding attributes the declaration to the validation, not the author")
        else:
            fail("the downgraded finding does not state who declared it")

        # A second, undeclared missing target must still fail the pack.
        pack2 = Path(tmp) / "pack2.zip"
        with zipfile.ZipFile(pack2, "w") as z:
            z.writestr("hires.txt", "<ver>106\n<scale>1\n<background>missing.png,1\n<background>other.png,1\n")
        both = lint(pack2, real)
        if both.returncode == 1 and "other.png does not exist" in both.stdout:
            ok("an undeclared target still fails a pack that carries an errata")
        else:
            fail(f"errata pardoned a target it does not name; rc={both.returncode}")

        # A declaration matching nothing means the errata does not describe the
        # artifact - it fails rather than sitting there as a blanket pardon.
        stale = write_errata(tmp, entry={"target": "never-referenced.png"})
        res = lint(pack, stale)
        if res.returncode == 1 and "does not describe this artifact" in res.stdout:
            ok("a declaration that matches nothing fails the pack")
        else:
            fail(f"an unused declaration was tolerated; rc={res.returncode}")

    # --- structural parity: one parser, two gates ---
    lint_src = (REPO / "scripts" / "mep_lint.py").read_text()
    smoke_src = (REPO / "scripts" / "smoke_pack_headless.sh").read_text()
    if "import mep_errata" in lint_src:
        ok("mep_lint.py resolves declarations through mep_errata")
    else:
        fail("mep_lint.py does not import mep_errata")
    if re.search(r"mep_errata\.py\"? covers", smoke_src):
        ok("smoke_pack_headless.sh resolves declarations through mep_errata")
    else:
        fail("smoke_pack_headless.sh does not call mep_errata covers")
    if "known_missing" in smoke_src:
        fail("smoke_pack_headless.sh parses the errata format itself — that is the #155 shape")
    else:
        ok("neither gate re-implements the errata format")

    # --- the shipped errata files are valid ---
    shipped = sorted((REPO / "docs" / "community-packs" / "errata").glob("*.json"))
    for path in shipped:
        try:
            mep_errata.load(path)
            ok(f"shipped errata is valid: {path.name}")
        except mep_errata.ErrataError as exc:
            fail(f"shipped errata is invalid: {exc}")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s)")
        return 1
    print("All mep_errata checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
