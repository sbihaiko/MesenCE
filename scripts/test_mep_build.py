#!/usr/bin/env python3
"""Acceptance test for scripts/mep_build.py (PRD F5.4c, ADR-0049 §2).

Builds a synthetic author folder (a 16-column sheet + a key-source
hires.txt + two OGGs) and asserts the whole build/pack/rename cycle:

  * `build` re-points every tile key at the sheet cell that owns it (16px
    crops at scale 2, img index = sheet index), regenerates audio/hires.txt
    with the OGG ids taken from their file names, and lints clean;
  * `pack` writes a correct pack.json (sections from the tree, targets from
    the ROM) and produces a byte-deterministic zip that lints clean;
  * `rename-audio-id` renames an enumerated id across fingerprints.json +
    the midi/bgm/sfx files + the audio/hires.txt references;
  * the failure modes exit 2 with a clear message: no key source, sheet
    cells < tile keys, a non-16-column sheet.

Framework-free, mirroring test_mep_recipe.py's ok()/fail()/main() style.
Wired into `make doc-checks`. Usage: python3 scripts/test_mep_build.py
"""

import hashlib
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MEP_BUILD = REPO / "scripts" / "mep_build.py"
GEN_ROM = REPO / "scripts" / "gen_synthetic_nrom.py"
PY = sys.executable

FAILED = 0


def ok(msg):
    print(f"PASS: {msg}")


def fail(msg):
    global FAILED
    FAILED = 1
    print(f"FAIL: {msg}")


def png(width, height, rgba=(0xC8, 0x28, 0x28, 0xFF)) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgba) * width for _ in range(height))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def run(*argv, expect=0, cwd=None):
    p = subprocess.run([PY, str(MEP_BUILD), *argv], capture_output=True, text=True, cwd=cwd)
    out = (p.stdout + p.stderr).strip()
    if p.returncode != expect:
        fail(f"mep_build {' '.join(argv)} -> exit {p.returncode}, expected {expect}: {out}")
        return None
    return out


def make_author_folder(root: Path, keys: int = 16, name: str = "author"):
    """A buildable author folder: a 16-column sheet at scale 2 (16px cells),
    a key-source hires.txt, and one bgm + one sfx OGG."""
    folder = root / name
    (folder / "textures" / "sheets").mkdir(parents=True)
    (folder / "audio" / "bgm").mkdir(parents=True)
    (folder / "audio" / "sfx").mkdir(parents=True)
    (folder / "textures" / "sheets" / "objects.png").write_bytes(png(256, 16))  # 16 cells, scale 2
    lines = ["<ver>107", "<scale>2", "<system>nes",
             "<supportedRom>2A4E126D0286BEA0BF503C80A12352C57539F76B", "<img>old.png"]
    for k in range(keys):
        lines.append(f"<tile>0,{k:02X}{'00' * 15},0F001A2C,0,0,1,N")
    (folder / "textures" / "hires.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (folder / "audio" / "bgm" / "01.ogg").write_bytes(b"")
    (folder / "audio" / "sfx" / "03.ogg").write_bytes(b"")
    return folder


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        folder = make_author_folder(root)

        # --- build ---
        out = run("build", str(folder))
        if out is None:
            return 1
        hires = folder / "textures" / "hires.txt"
        text = hires.read_text(encoding="utf-8")
        tiles = [l for l in text.splitlines() if "<tile>" in l]
        if len(tiles) != 16:
            fail(f"build emitted {len(tiles)} tiles, expected 16")
        else:
            ok(f"build emitted 16 tiles")
        if "<img>sheets/objects.png" not in text:
            fail("build did not point <img> at the sheet under textures/sheets/")
        else:
            ok("build points <img> at the author sheet")
        # Cell k -> crop (k%16)*16, 0 at scale 2; key k -> tileData first byte k.
        for k, t in enumerate(tiles):
            body = t.split(">", 1)[1]
            f = body.split(",")
            want_x = str((k % 16) * 16)
            want_data = f"{k:02X}{'00' * 15}"
            if f[0] != "0" or f[3] != want_x or f[4] != "0" or f[1].upper() != want_data:
                fail(f"tile {k} not re-pointed: {body}")
                break
        else:
            ok("tile crops re-pointed to sheet cells (scale 2, img 0)")
        audio = (folder / "audio" / "hires.txt").read_text(encoding="utf-8")
        if "<bgm>0,1,bgm/01.ogg" not in audio or "<sfx>0,3,sfx/03.ogg" not in audio:
            fail(f"audio manifest missing expected ids:\n{audio}")
        else:
            ok("audio manifest references the new OGGs with their file-name ids")
        # run(expect=0) above already asserted the lint gate (a non-zero lint
        # exit fails the build); "0 error(s)" in the text would false-match a
        # naive substring search, so rely on the exit code alone.
        ok("build lints clean (lint gate = exit 0)")

        # --- pack determinism + correctness ---
        rom = root / "syn.nes"
        subprocess.run([PY, str(GEN_ROM), str(rom)], check=True, capture_output=True)
        z1, z2 = root / "a.zip", root / "b.zip"
        run("pack", str(folder), "--rom", str(rom), "--name", "F5.4c Test", "--version", "1.0.0", "--out", str(z1))
        run("pack", str(folder), "--rom", str(rom), "--name", "F5.4c Test", "--version", "1.0.0", "--out", str(z2))
        d1, d2 = hashlib.sha256(z1.read_bytes()).hexdigest(), hashlib.sha256(z2.read_bytes()).hexdigest()
        if d1 != d2:
            fail(f"pack not deterministic: {d1} != {d2}")
        else:
            ok(f"pack is byte-deterministic ({d1[:12]}…)")
        with zipfile.ZipFile(z1) as zf:
            names = zf.namelist()
            if names[0] != "pack.json":
                fail(f"pack.json is not the first zip entry: {names[:3]}")
            else:
                ok("pack.json is the first zip entry")
            meta = zf.read("pack.json").decode("utf-8")
            pj = json_loads(meta)
        if pj.get("sections") != {"textures": {"path": "textures/"}, "audio": {"path": "audio/"}}:
            fail(f"pack.json sections wrong: {pj.get('sections')}")
        else:
            ok("pack.json sections derived from the tree")
        if not pj["targets"][0]["sha1"]:
            fail("pack --rom did not fill targets[0].sha1")
        else:
            ok(f"pack --rom computed No-Intro sha1 {pj['targets'][0]['sha1'][:8]}...")

        # --- rename-audio-id (F5.4g Bloco D item 12 id lifecycle) ---
        audio_dir = folder / "audio"
        (audio_dir / "midi").mkdir(exist_ok=True)
        (audio_dir / "midi" / "track01.mid").write_bytes(b"M")
        (audio_dir / "bgm" / "track01.ogg").write_bytes(b"O")
        fp = audio_dir / "fingerprints.json"
        fp.write_text('{\n  "version": 1,\n  "tracks": [\n'
                      '    { "id": "track01", "kind": "bgm", "frames": 10, "midi": "midi/track01.mid", "events": [[0,0,0]] }\n'
                      '  ]\n}\n', encoding="utf-8")
        (audio_dir / "hires.txt").write_text("<ver>107\n<bgm>0,1,bgm/track01.ogg\n", encoding="utf-8")
        run("rename-audio-id", str(folder), "track01", "track02")
        if not (audio_dir / "midi" / "track02.mid").exists() or (audio_dir / "midi" / "track01.mid").exists():
            fail("rename-audio-id did not move midi/track01.mid -> track02.mid")
        else:
            ok("rename-audio-id moved the midi file")
        if not (audio_dir / "bgm" / "track02.ogg").exists() or (audio_dir / "bgm" / "track01.ogg").exists():
            fail("rename-audio-id did not move bgm/track01.ogg -> track02.ogg")
        else:
            ok("rename-audio-id moved the bgm OGG")
        fp_text = fp.read_text(encoding="utf-8")
        if '"id": "track01"' in fp_text or '"midi": "midi/track01.mid"' in fp_text:
            fail("rename-audio-id did not rewrite fingerprints.json id/midi")
        else:
            ok("rename-audio-id rewrote fingerprints.json id + midi path")
        hires_text = (audio_dir / "hires.txt").read_text(encoding="utf-8")
        if "bgm/track01.ogg" in hires_text or "bgm/track02.ogg" not in hires_text:
            fail("rename-audio-id did not rewrite the audio/hires.txt reference")
        else:
            ok("rename-audio-id rewrote the audio/hires.txt reference")

        # --- flat-pack migration: dangling seed refs dropped, ids reclaimed ---
        mig = root / "migrate"
        (mig / "textures" / "sheets").mkdir(parents=True)
        (mig / "audio" / "bgm").mkdir(parents=True)
        (mig / "audio" / "sfx").mkdir(parents=True)
        (mig / "textures" / "sheets" / "a.png").write_bytes(png(256, 16))
        # Key source carries bgm/sfx whose files do NOT exist under audio/:
        # the migration path must drop them and hand the freed ids to the
        # real OGGs, not keep dangling refs or collide.
        (mig / "textures" / "hires.txt").write_text(
            "<ver>107\n<scale>2\n<system>nes\n"
            + "\n".join(f"<tile>0,{k:02X}{'00' * 15},0F001A2C,0,0,1,N" for k in range(16))
            + "\n<bgm>0,0,track01.ogg\n<sfx>0,3,jump.ogg\n", encoding="utf-8")
        (mig / "audio" / "bgm" / "01.ogg").write_bytes(b"")
        (mig / "audio" / "sfx" / "03.ogg").write_bytes(b"")
        run("build", str(mig))
        mig_audio = (mig / "audio" / "hires.txt").read_text(encoding="utf-8")
        if "track01.ogg" in mig_audio or "jump.ogg" in mig_audio:
            fail(f"migration kept dangling seed refs:\n{mig_audio}")
        elif "<bgm>0,1,bgm/01.ogg" not in mig_audio or "<sfx>0,3,sfx/03.ogg" not in mig_audio:
            fail(f"migration did not reclaim the freed ids:\n{mig_audio}")
        elif mig_audio.count("<sfx>") != 1 or mig_audio.count("<bgm>") != 1:
            fail(f"migration produced duplicate track ids:\n{mig_audio}")
        else:
            ok("flat-pack migration drops dangling refs, reclaims ids, no duplicates")

        # --- non-NES packs skip the audio manifest (frozen, ADR-0041) ---
        sms = root / "sms"
        (sms / "textures" / "sheets").mkdir(parents=True)
        (sms / "audio" / "bgm").mkdir(parents=True)
        (sms / "textures" / "sheets" / "a.png").write_bytes(png(256, 16))
        (sms / "textures" / "hires.txt").write_text(
            "<ver>200\n<system>sms\n<scale>2\n"
            + "\n".join(f"<tile>0,{k:02X}{'00' * 15},0F001A2C,0,0,1,N" for k in range(16))
            + "\n", encoding="utf-8")
        (sms / "audio" / "bgm" / "01.ogg").write_bytes(b"")
        out = run("build", str(sms))
        if (sms / "audio" / "hires.txt").exists():
            fail("non-NES build wrote an audio manifest (GB/SMS OGG frozen)")
        else:
            ok("non-NES build skips the audio manifest")

        # --- empty argv is a usage error, not a crash ---
        p = subprocess.run([PY, str(MEP_BUILD)], capture_output=True, text=True)
        if p.returncode != 2 or "usage" not in (p.stdout + p.stderr):
            fail(f"mep_build with no args -> exit {p.returncode}, expected 2 + usage")
        else:
            ok("mep_build with no args prints usage and exits 2")

        # --- failure modes (exit 2) ---
        no_source = root / "no-source"
        (no_source / "textures" / "sheets").mkdir(parents=True)
        (no_source / "textures" / "sheets" / "a.png").write_bytes(png(256, 16))
        out = run("build", str(no_source), expect=2)
        if out is not None and "no tile-key source" in out:
            ok("missing key source fails with guidance")
        else:
            fail(f"missing key source: {out}")

        small = make_author_folder(root, keys=20, name="small")  # 16 cells, 20 keys
        run("build", str(small), expect=2)

        wide = make_author_folder(root, name="wide")
        (wide / "textures" / "sheets" / "objects.png").unlink()
        (wide / "textures" / "sheets" / "objects.png").write_bytes(png(512, 16))  # 32 columns
        run("build", str(wide), expect=2)

    return 1 if FAILED else 0


def json_loads(s):
    import json
    return json.loads(s)


if __name__ == "__main__":
    sys.exit(main())
