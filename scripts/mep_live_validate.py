#!/usr/bin/env python3
"""Drives the real C++ HD/MEP pack loader against a downloaded pack, using
the synthetic copyright-free NROM from gen_synthetic_nrom.py instead of a
real game ROM (see that script's docstring for why this is valid: the
loader's structural validation never reads PRG/CHR bytes).

Reuses mep_lint.py's own pack-root discovery (Source, find_fallback_subfolder,
find_fallback_subfolder_by_name) so it tests exactly the layer mep_lint.py
graded, not a different guess at the pack's shape.

Usage:
  python3 scripts/mep_live_validate.py <pack-file> <rom-name> <capture-tool> <work-dir>

Prints one line to stdout: "errors=<N>" followed by each raw [HDPack]/[MEP]
diagnostic line found in the core log (for a human or an agent to compare
against mep_lint.py's own findings). Exit code 0 always (this is a report,
not a pass/fail gate by itself) unless the harness itself fails to run.
"""
import re
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mep_lint import Source, find_fallback_subfolder, find_fallback_subfolder_by_name  # noqa: E402
from gen_synthetic_nrom import build_rom  # noqa: E402

DIAG_PREFIXES = ("[HDPack", "[MEP")


def discover_root(src: Source, rom_name: str):
    if src.exists("pack.json"):
        return ""
    fb = find_fallback_subfolder(src.names)
    if not fb and rom_name:
        fb = find_fallback_subfolder_by_name(src.names, rom_name)
    return (fb[0] + "/") if fb else None


def extract_root(pack_path: Path, root: str, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pack_path) as z:
        for name in z.namelist():
            norm = name.replace("\\", "/")
            if not norm.startswith(root) or norm.endswith("/"):
                continue
            rel = norm[len(root):]
            if not rel or ".." in Path(rel).parts:
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))


def sanitize(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "test-rom"


def main(argv):
    if len(argv) != 5:
        print(__doc__)
        return 2
    pack_path = Path(argv[1])
    rom_name = argv[2]
    capture_tool = Path(argv[3])
    work_dir = Path(argv[4])
    work_dir.mkdir(parents=True, exist_ok=True)

    src = Source(pack_path)
    root = discover_root(src, rom_name)
    if root is None:
        print("errors=0")
        print("note: no pack root discovered by mep_lint's own logic; nothing to load live")
        return 0

    rom_base = sanitize(rom_name) if rom_name else "test-rom"
    # headless_record derives <home> as "<output-prefix-dir>/mesen-home" -
    # pre-seed the pack there directly, under the same output dir we pass in.
    out_dir = work_dir / "out"
    home = out_dir / "mesen-home"
    if src.exists(root + "pack.json"):
        target = home / "EnhancementPacks" / rom_base
        extra_flags = ["mep-forcepatch"]
    else:
        target = home / "HdPacks" / rom_base
        extra_flags = []
    extract_root(pack_path, root, target)

    rom_path = work_dir / f"{rom_base}.nes"
    rom_path.write_bytes(build_rom())

    out_prefix = out_dir / "x"
    cmd = [str(capture_tool), str(rom_path), "2", str(out_prefix), "log"] + extra_flags
    result = subprocess.run(cmd, cwd=str(Path(capture_tool).parent.parent), capture_output=True, text=True, timeout=60)
    log = result.stdout + result.stderr

    diag_lines = [line for line in log.splitlines() if line.strip().startswith(DIAG_PREFIXES)]
    loaded_with = re.search(r"Loaded with (\d+) errors?", log)
    error_count = int(loaded_with.group(1)) if loaded_with else 0
    print(f"errors={error_count}")
    for line in diag_lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
