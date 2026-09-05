#!/usr/bin/env python3
"""sheet_repaint — external repaint of ADR-0153 artist sheets (PRD F9.6).

Takes the sheets the bootstrap wrote under `auto/textures/sheets/`
(ADR-0153: a metatile vocabulary, stitched maps, object sheets, each with a
sidecar JSON) and produces an upscaled repaint of them under
`auto/repaint/`, labelled `generated` in `pack.json` so the community-pack
pipeline can refuse it a catalog row (ADR-0154 §3).

    scripts/sheet_repaint.py <pack-or-sheets-dir> [--out DIR] [--scale N]
        [--target sheets|screens|both]
        [--backend passthrough|null|classical|esrgan|diffusion]
        [--sheets NAME[,NAME...]] [--seam-width W] [--no-variants] [--verbose]

Two targets (ADR-0154 §2, as re-scoped):

  * `--target screens` — the **primary** one. Repaints the captured scenes
    `textures/backgrounds/screenNNN.png` that ADR-0050 emits, discovered by
    reading the recorder's `hires.txt` `<background>` lines (which are
    condition-prefixed, e.g.
    `[screen001_A&screen001_B&screen001_C]<background>backgrounds/screen001.png,1,0,0,20`).
    A 256x240 scene is what a control image guides well, and it is the only
    surface on which a *positional* element can exist at all — a tile entry is
    position-independent, so painting a metatile paints it everywhere. The
    repaint re-emits a self-contained `hires.txt` with the same prefixes and
    the `<condition>` lines they reference, `<scale>` multiplied.
  * `--target sheets` — the ADR-0153 artist sheets, with the palette-variant
    and seam machinery below. Secondary.

Everything that does not depend on the model lives here and runs today:

  * the control image (the sheet nearest-upscaled to the target size) and the
    per-cell crop list, read from the sidecar's `cells[]` (contact sheets) or
    `placements[]` (maps) — ADR-0153 §4;
  * palette-variant recolouring from a *single* generation, so every variant
    of one shape keeps the same silhouette (ADR-0154 §5);
  * the seam pass, which symmetrises the border band of cells that are
    adjacent in game (adjacency read off `placements[]`, never guessed) so a
    stripe painted across a map stays continuous — ADR-0154 §6;
  * alpha taken from the source, nearest-neighbour, always (ADR-0154 §7).

The model itself sits behind `RepaintBackend`:

  * `passthrough` (alias `null`) — nearest-neighbour upscale: not a
    placeholder, but the deterministic control arm of PRD Phase 9 validation
    test 8, and what most of the tests assert against;
  * `classical` — an in-repo Scale2x/Scale3x pixel-art scaler (the hq2x/xBRZ
    family). Zero dependencies, always available, byte-reproducible, and it
    cannot invent a colour: every output pixel is a copy of an input pixel.
    This is the non-generative arm of the blind A/B;
  * `esrgan` — a **locally installed** Real-ESRGAN runner. Nothing is
    downloaded, ever: with no runner and no weights on the machine it fails
    with a message naming what to install and points at `classical`;
  * `diffusion` — ADR-0154 §2's decision: a **locally running** ComfyUI (HTTP,
    loopback only) or a local `diffusers` command, fed the control image as
    the ControlNet hint. It refuses a non-loopback endpoint outright, so
    ROM-derived art cannot leave the machine, and it never fetches weights.

No backend in this file talks to anything but `127.0.0.1`/`::1` or a local
process; adding one is wiring a new class into BACKENDS, not a rewrite.

Building the result needs the recorder's tile keys, which live outside the
repaint folder (ADR-0154 §4):

    python3 scripts/mep_build.py build <Game>/auto/repaint \\
        --source <Game>/auto/textures/hires.txt

Standard library only, like mep_build.py and sheet_report.py: struct + zlib
for PNG, no Pillow, no numpy. The PNG *decoder* is mep_build's, imported
rather than copied, so the tree keeps exactly one of them.

Exit codes: 0 = wrote a repaint, 1 = nothing to do or a fatal error,
2 = usage error.
"""

import argparse
import datetime
import json
import os
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mep_build  # noqa: E402  — the tree's single PNG decoder (_png_pixels)

SHEET_VERSION = 1
# ADR-0153 §3 sheet kinds. `map` is the only one carrying placements[].
CONTACT_KINDS = ("metatiles", "misc", "hud", "font", "object", "sprite")
MAP_KIND = "map"
DEFAULT_SCALE = 4
DEFAULT_SEAM_WIDTH = 1


class RepaintError(Exception):
    """Fatal, with a message a human can act on."""


# --- images -----------------------------------------------------------------


class Image:
    """8-bit RGBA, row-major, one flat bytearray. Deliberately not a pixel
    object model: a stitched map is thousands of pixels wide and every
    operation here is a band copy or a per-pixel arithmetic pass."""

    __slots__ = ("width", "height", "px")

    def __init__(self, width: int, height: int, px: bytearray = None):
        self.width = width
        self.height = height
        self.px = px if px is not None else bytearray(width * height * 4)

    def clone(self) -> "Image":
        return Image(self.width, self.height, bytearray(self.px))

    def offset(self, x: int, y: int) -> int:
        return (y * self.width + x) * 4

    def get(self, x: int, y: int):
        o = self.offset(x, y)
        return tuple(self.px[o:o + 4])

    def set(self, x: int, y: int, rgba):
        o = self.offset(x, y)
        self.px[o:o + 4] = bytes(rgba)

    def crop(self, x: int, y: int, w: int, h: int) -> "Image":
        out = Image(w, h)
        for row in range(h):
            src = self.offset(x, y + row)
            dst = out.offset(0, row)
            out.px[dst:dst + w * 4] = self.px[src:src + w * 4]
        return out

    def paste(self, other: "Image", x: int, y: int):
        for row in range(other.height):
            src = other.offset(0, row)
            dst = self.offset(x, y + row)
            self.px[dst:dst + other.width * 4] = other.px[src:src + other.width * 4]

    def upscale(self, n: int) -> "Image":
        """Nearest neighbour. The only resampler in this file: a soft edge on
        an 8x8 NES tile is wrong by construction (ADR-0154 §7)."""
        if n == 1:
            return self.clone()
        out = Image(self.width * n, self.height * n)
        for y in range(self.height):
            row = bytearray()
            src = self.offset(0, y)
            for x in range(self.width):
                row += self.px[src + x * 4:src + x * 4 + 4] * n
            for k in range(n):
                dst = out.offset(0, y * n + k)
                out.px[dst:dst + len(row)] = row
        return out


def read_png(path: Path) -> Image:
    """Decode an 8-bit non-interlaced RGB/RGBA PNG into an Image, through
    mep_build's decoder (the tree has one, and this is it). RGB is widened to
    RGBA with a fully opaque alpha."""
    bitmap = mep_build._png_pixels(path)
    if bitmap is None:
        raise RepaintError(f"{path}: not an 8-bit, non-interlaced RGB/RGBA PNG this tool can read")
    img = Image(bitmap.width, bitmap.height)
    if bitmap.channels == 4:
        img.px = bytearray(bitmap.raw)
        return img
    for i in range(bitmap.width * bitmap.height):
        img.px[i * 4:i * 4 + 3] = bitmap.raw[i * 3:i * 3 + 3]
        img.px[i * 4 + 3] = 0xFF
    return img


def write_png(path: Path, img: Image):
    """8-bit RGBA, filter 0, one IDAT — the same shape the C++ side and the
    test fixtures write, so a round-trip stays byte-comparable."""
    raw = bytearray()
    stride = img.width * 4
    for y in range(img.height):
        raw.append(0)
        raw += img.px[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", img.width, img.height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b""))


# --- sheets -----------------------------------------------------------------


class Region:
    """One crop the backend is told about: a rect in *target* (upscaled)
    pixels plus the vocabulary index it renders, when there is one."""

    __slots__ = ("x", "y", "w", "h", "vocab", "index")

    def __init__(self, x, y, w, h, vocab, index):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.vocab = vocab
        self.index = index

    def __repr__(self):
        return f"Region({self.x},{self.y},{self.w}x{self.h},vocab={self.vocab})"


class Sheet:
    """A sidecar plus the PNG it names, plus its `*.orig.png` twin."""

    def __init__(self, json_path: Path, doc: dict):
        self.json_path = json_path
        self.doc = doc
        self.kind = str(doc.get("kind") or "")
        self.unit = int(doc.get("gridUnit") or 8)
        self.gutter = int(doc.get("gutter") or 0)
        self.cells = [c for c in (doc.get("cells") or []) if isinstance(c, dict)]
        self.placements = [p for p in (doc.get("placements") or []) if isinstance(p, dict)]
        self.png_path = json_path.parent / str(doc.get("sheet") or f"{json_path.stem}.png")
        ref = str(doc.get("reference") or "").strip()
        self.orig_path = (json_path.parent / ref) if ref else None

    @property
    def stem(self) -> str:
        return self.png_path.stem


def find_sheets_dir(target: Path) -> Path:
    """`target` may be the sheets folder itself, a pack folder, or a game
    folder with an `auto/` sibling (ADR-0147). First hit wins, most specific
    first, so pointing at a game folder does the obvious thing."""
    candidates = [
        target,
        target / "sheets",
        target / "textures" / "sheets",
        target / "auto" / "textures" / "sheets",
    ]
    for cand in candidates:
        if cand.is_dir() and any(p.suffix == ".json" for p in cand.iterdir()):
            return cand
    raise RepaintError(f"no sheets/ folder with sidecar JSON under {target}")


def load_sheets(sheets_dir: Path, wanted=None):
    """Every version-1 sidecar in the folder. An unusable sidecar is skipped
    with a warning, never fatal — the same posture as mep_build's loader."""
    sheets = []
    for jp in sorted(sheets_dir.glob("*.json")):
        try:
            doc = json.loads(jp.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            print(f"warning: {jp.name}: not readable as JSON, skipped ({err})", file=sys.stderr)
            continue
        if not isinstance(doc, dict) or doc.get("version") != SHEET_VERSION:
            print(f"warning: {jp.name}: not an ADR-0153 v1 sidecar, skipped", file=sys.stderr)
            continue
        sheet = Sheet(jp, doc)
        if sheet.kind not in CONTACT_KINDS and sheet.kind != MAP_KIND:
            print(f"warning: {jp.name}: unknown sheet kind {sheet.kind!r}, skipped", file=sys.stderr)
            continue
        if not sheet.png_path.is_file():
            print(f"warning: {jp.name}: names '{sheet.png_path.name}', which does not exist — skipped",
                  file=sys.stderr)
            continue
        if wanted and sheet.stem not in wanted:
            continue
        sheets.append(sheet)
    return sheets


def crop_list(sheet: Sheet, scale: int):
    """The per-cell crop list, in target pixels. Contact sheets slice through
    `cells[]` (x/y are the cell's top-left, gutters excluded); a map slices
    through `placements[]` (map-pixel origin -> vocabulary index)."""
    unit = sheet.unit * scale
    regions = []
    if sheet.kind == MAP_KIND:
        for i, p in enumerate(sheet.placements):
            try:
                x, y, cell = int(p["x"]), int(p["y"]), int(p["cell"])
            except (KeyError, TypeError, ValueError):
                continue
            regions.append(Region(x * scale, y * scale, unit, unit, cell, i))
        return regions
    for i, c in enumerate(sheet.cells):
        try:
            x, y = int(c.get("x", 0)), int(c.get("y", 0))
        except (TypeError, ValueError):
            continue
        vocab = c.get("metatile")
        regions.append(Region(x * scale, y * scale, unit, unit,
                              vocab if isinstance(vocab, int) else None, i))
    return regions


def shape_key(cell: dict):
    """A cell's tile-shape tuple, palette ignored — the grouping key for
    palette variants (ADR-0154 §5). None when the cell carries no art."""
    tiles = cell.get("tiles")
    if not isinstance(tiles, list):
        return None
    key = tuple((t.get("tile") if isinstance(t, dict) else None) for t in tiles)
    return key if any(k for k in key) else None


def palette_key(cell: dict):
    tiles = cell.get("tiles")
    if not isinstance(tiles, list):
        return None
    return tuple((t.get("palette") if isinstance(t, dict) else None) for t in tiles)


# --- backends ---------------------------------------------------------------


class RepaintRequest:
    """What a backend is given. `source` is the sheet at 1x; `control` is the
    same image nearest-upscaled to the target size — the structure constraint
    a real backend feeds to its control/ControlNet input. `regions` is the
    crop list in target pixels, so a backend may work per cell if it wants."""

    __slots__ = ("source", "control", "scale", "kind", "regions", "sheet")

    def __init__(self, source: Image, control: Image, scale: int, kind: str, regions, sheet: Sheet):
        self.source = source
        self.control = control
        self.scale = scale
        self.kind = kind
        self.regions = regions
        self.sheet = sheet


class RepaintBackend:
    """The one seam a model plugs into (ADR-0154 §1).

    A backend returns a single image at exactly `request.control` size. It may
    ignore alpha, shift the palette and produce discontinuous cell borders:
    the caller re-applies the source alpha (§7), recolours palette variants
    from one generation (§5) and runs the seam pass (§6) *after* this returns,
    so a backend is corrected rather than trusted.

    A backend MUST NOT be reproducibility-critical and MUST NOT be called for
    every palette variant of a shape — `repaint_sheet` decides what to ask
    for. Implementations that talk to a network service must be opt-in by
    name and must say so in their docstring; the only ones here that open a
    socket at all (`diffusion`) refuse anything but a loopback address.

    `ensure_available` runs **before** the first sheet is read, so a backend
    that cannot run says so instead of writing half an output tree. It raises
    `RepaintError` with a message naming what is missing and what to install,
    and it MUST NOT download anything (ADR-0154 §2: the weight download is
    performed by the user, never by this repo).
    """

    name = "abstract"

    def __init__(self, options=None):
        self.options = options

    def ensure_available(self):
        """Available by default; the local-model backends override."""

    def repaint(self, request: RepaintRequest) -> Image:
        raise NotImplementedError


class PassthroughBackend(RepaintBackend):
    """Nearest-neighbour upscale: the deterministic control arm of PRD Phase 9
    validation test 8, and what makes the rest of this pipeline runnable and
    testable with no model at all."""

    name = "passthrough"

    def repaint(self, request: RepaintRequest) -> Image:
        return request.control.clone()


# --- the classical (non-generative) baseline --------------------------------


def _keep_opaque(candidate, current):
    """Scale2x/Scale3x substitute a neighbouring pixel for the centre one. A
    *transparent* neighbour must never win over an opaque centre: its RGB is
    the ghost colour left under the mask, `apply_alpha` would then hand it the
    centre's alpha back, and the cell would grow a speck of a colour that is
    nowhere in the art. With this guard every opaque output pixel is a copy of
    an opaque source pixel."""
    return current if candidate[3] == 0 and current[3] != 0 else candidate


def _scale2x(img: Image) -> Image:
    """Scale2x/AdvMAME2x, the hq2x/xBRZ family's simplest member.

    Every output pixel is a *copy* of an input pixel, so the pass can neither
    invent a colour nor soften an edge — which is exactly what ADR-0154 §7
    wants of a pixel-art scaler and what makes this arm of PRD test 8 fail for
    reasons about the art rather than about the algorithm."""
    w, h = img.width, img.height
    out = Image(w * 2, h * 2)
    for y in range(h):
        for x in range(w):
            e = img.get(x, y)
            b = img.get(x, y - 1) if y > 0 else e
            d = img.get(x - 1, y) if x > 0 else e
            f = img.get(x + 1, y) if x < w - 1 else e
            g = img.get(x, y + 1) if y < h - 1 else e   # "H" in the paper
            if b != g and d != f:
                e0 = d if d == b else e
                e1 = f if b == f else e
                e2 = d if d == g else e
                e3 = f if g == f else e
            else:
                e0 = e1 = e2 = e3 = e
            out.set(x * 2, y * 2, _keep_opaque(e0, e))
            out.set(x * 2 + 1, y * 2, _keep_opaque(e1, e))
            out.set(x * 2, y * 2 + 1, _keep_opaque(e2, e))
            out.set(x * 2 + 1, y * 2 + 1, _keep_opaque(e3, e))
    return out


def _scale3x(img: Image) -> Image:
    """Scale3x, same family and the same copy-only guarantee. Present so a
    scale of 3 or 6 is not silently degraded to nearest neighbour."""
    w, h = img.width, img.height
    out = Image(w * 3, h * 3)
    for y in range(h):
        for x in range(w):
            e = img.get(x, y)
            x0, x2 = max(x - 1, 0), min(x + 1, w - 1)
            y0, y2 = max(y - 1, 0), min(y + 1, h - 1)
            a, b, c = img.get(x0, y0), img.get(x, y0), img.get(x2, y0)
            d, f = img.get(x0, y), img.get(x2, y)
            g, hh, i = img.get(x0, y2), img.get(x, y2), img.get(x2, y2)
            if b != hh and d != f:
                e0 = d if d == b else e
                e1 = b if ((d == b and e != c) or (b == f and e != a)) else e
                e2 = f if b == f else e
                e3 = d if ((d == hh and e != a) or (d == b and e != g)) else e
                e4 = e
                e5 = f if ((b == f and e != i) or (hh == f and e != c)) else e
                e6 = d if d == hh else e
                e7 = hh if ((hh == f and e != i) or (d == hh and e != g)) else e
                e8 = f if hh == f else e
            else:
                e0 = e1 = e2 = e3 = e4 = e5 = e6 = e7 = e8 = e
            for k, px in enumerate((e0, e1, e2, e3, e4, e5, e6, e7, e8)):
                out.set(x * 3 + k % 3, y * 3 + k // 3, _keep_opaque(px, e))
    return out


def classical_scale(img: Image, factor: int) -> Image:
    """Factor 1 -> a copy; otherwise the factor is decomposed into 2s and 3s
    and the residual (a factor of 5, 7, …, which no member of this family
    covers) falls back to nearest neighbour. `apply_alpha` re-imposes the
    source alpha afterwards, so a pass that moved a silhouette by one pixel is
    corrected rather than trusted."""
    if factor <= 1:
        return img.clone()
    out, rest = img, factor
    while rest % 3 == 0:
        out, rest = _scale3x(out), rest // 3
    while rest % 2 == 0:
        out, rest = _scale2x(out), rest // 2
    return out if rest == 1 else out.upscale(rest)


class ClassicalBackend(RepaintBackend):
    """ADR-0154 §2's baseline arm: a pure-Python pixel-art scaler with no
    dependency, no weights and no network. Deterministic, so two runs of the
    blind A/B compare the same B.

    It is O(pixels) in Python, which on a 1024x960 captured screen at scale 2
    is a few seconds — slow, never a correctness problem, and the reason
    `--target screens --scale 1` is the usual invocation on already-upscaled
    recordings."""

    name = "classical"

    def repaint(self, request: RepaintRequest) -> Image:
        return classical_scale(request.source, request.scale)


# --- local Real-ESRGAN (never downloaded, never bundled) --------------------


ESRGAN_MISSING = (
    "the 'esrgan' backend needs a Real-ESRGAN install that is already on this "
    "machine, and this script never downloads one (ADR-0154 §2: the weight "
    "download is performed by the user, never by this repo).\n"
    "  what to install: the upstream `realesrgan-ncnn-vulkan` release "
    "(BSD-3-Clause) or any runner with the same CLI, plus its `.param`/`.bin` "
    "weights;\n"
    "  then point this script at them: --esrgan-binary <path or name on PATH> "
    "[--esrgan-model <weights file or model dir>], or set "
    "SHEET_REPAINT_ESRGAN_BIN / SHEET_REPAINT_ESRGAN_MODEL;\n"
    "  or use --backend classical, the in-repo scaler that always runs and "
    "needs nothing.")


class EsrganBackend(RepaintBackend):
    """A locally installed Real-ESRGAN runner, invoked as
    `<bin> -i <control.png> -o <out.png> -s <scale> [-m <model>]` — the CLI of
    the upstream `realesrgan-ncnn-vulkan` release.

    Nothing here fetches anything. With no runner and no weights on the
    machine, `ensure_available` fails with ESRGAN_MISSING, which names what to
    install and points at `classical`."""

    name = "esrgan"

    def _binary(self):
        opt = getattr(self.options, "esrgan_binary", None) or os.environ.get(
            "SHEET_REPAINT_ESRGAN_BIN") or "realesrgan-ncnn-vulkan"
        found = shutil.which(opt)
        if found:
            return found
        candidate = Path(opt).expanduser()
        return str(candidate) if candidate.is_file() and os.access(candidate, os.X_OK) else None

    def _model(self):
        opt = getattr(self.options, "esrgan_model", None) or os.environ.get(
            "SHEET_REPAINT_ESRGAN_MODEL")
        return Path(opt).expanduser() if opt else None

    def ensure_available(self):
        if self._binary() is None:
            raise RepaintError(ESRGAN_MISSING)
        model = self._model()
        if model is not None and not model.exists():
            raise RepaintError(
                f"--esrgan-model {model} does not exist. {ESRGAN_MISSING}")

    def repaint(self, request: RepaintRequest) -> Image:
        binary = self._binary()
        if binary is None:  # ensure_available ran, but a PATH can change under us
            raise RepaintError(ESRGAN_MISSING)
        with tempfile.TemporaryDirectory(prefix="sheet-repaint-esrgan-") as tmp:
            src, dst = Path(tmp) / "control.png", Path(tmp) / "out.png"
            write_png(src, request.control)
            cmd = [binary, "-i", str(src), "-o", str(dst), "-s", str(request.scale)]
            model = self._model()
            if model is not None:
                cmd += ["-m", str(model)]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=getattr(self.options, "backend_timeout", 600))
            except FileNotFoundError:
                raise RepaintError(ESRGAN_MISSING)
            except subprocess.TimeoutExpired:
                raise RepaintError(f"'{binary}' did not finish within the backend timeout")
            if proc.returncode != 0:
                raise RepaintError(
                    f"'{binary}' exited {proc.returncode}: "
                    f"{(proc.stderr or proc.stdout or '').strip()[:400]}")
            if not dst.is_file():
                raise RepaintError(f"'{binary}' wrote no image to {dst.name}")
            return read_png(dst)


# --- local diffusion + ControlNet (ADR-0154 §2, Option A) -------------------


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
DEFAULT_COMFY_ENDPOINT = "http://127.0.0.1:8188"
DIFFUSION_PLACEHOLDERS = ("CONTROL_IMAGE", "PROMPT", "NEGATIVE_PROMPT",
                          "SEED", "DENOISE", "WIDTH", "HEIGHT", "SCALE")

DIFFUSION_MISSING_ENDPOINT = (
    "the 'diffusion' backend needs a diffusion runtime that is already running "
    "on this machine; nothing is installed or downloaded by this script "
    "(ADR-0154 §2).\n"
    "  ComfyUI path: start it locally (`python main.py --listen 127.0.0.1`), "
    "put a Stable Diffusion checkpoint and a ControlNet (tile or canny) model "
    "you obtained yourself under its `models/` tree, export an API-format "
    "workflow, and pass --diffusion-workflow <that.json> "
    "[--diffusion-endpoint {endpoint}];\n"
    "  diffusers path: pass --diffusion-runner '<your local command>'. It is "
    "called as `<command> <control.png> <output.png> <scale>` and must write "
    "a PNG of exactly the control image's size;\n"
    "  or use --backend classical / --backend passthrough, which need nothing.")


class DiffusionBackend(RepaintBackend):
    """Drives a **locally running** ComfyUI or `diffusers` process with the
    control image as the ControlNet hint (ADR-0154 §2, Option A).

    Two drive modes, both local:

      * `--diffusion-runner CMD` — CMD is executed as
        `CMD <control.png> <output.png> <scale>`. This is the `diffusers`
        path: a short script the artist writes around the weights they already
        have. This backend never imports `diffusers` itself, so a missing
        install is the runner's error, not an import failure here.
      * otherwise ComfyUI's HTTP API on `--diffusion-endpoint` (default
        {endpoint}). The endpoint host MUST be a loopback address — a remote
        one is refused before any byte is read, because uploading ROM-derived
        art is Option B, which ADR-0154 §2 rejects. The workflow is the
        user's own API-format JSON with placeholders substituted:
        `__CONTROL_IMAGE__` (the uploaded control image's name),
        `__PROMPT__`, `__NEGATIVE_PROMPT__`, `__SEED__`, `__DENOISE__`,
        `__WIDTH__`, `__HEIGHT__`, `__SCALE__`. A quoted placeholder
        (`"__SEED__"`) is replaced by a bare number, so numeric widget slots
        stay numbers.

    **Never executed in CI or in this repo's tests.** Only its unavailable
    paths are covered; the generation path needs weights and a GPU that are
    deliberately not here. Read the test suite as evidence that it fails
    honestly, never as evidence that it produces an image."""

    name = "diffusion"

    def __init__(self, options=None):
        super().__init__(options)
        self.client_id = uuid.uuid4().hex

    # -- configuration ------------------------------------------------------

    @property
    def runner(self):
        return getattr(self.options, "diffusion_runner", None) or os.environ.get(
            "SHEET_REPAINT_DIFFUSION_RUNNER")

    @property
    def endpoint(self):
        raw = (getattr(self.options, "diffusion_endpoint", None)
               or os.environ.get("SHEET_REPAINT_COMFY_URL") or DEFAULT_COMFY_ENDPOINT)
        return raw.rstrip("/")

    @property
    def workflow_path(self):
        raw = getattr(self.options, "diffusion_workflow", None) or os.environ.get(
            "SHEET_REPAINT_DIFFUSION_WORKFLOW")
        return Path(raw).expanduser() if raw else None

    def _timeout(self):
        return int(getattr(self.options, "backend_timeout", 600) or 600)

    # -- availability -------------------------------------------------------

    def ensure_available(self):
        runner = self.runner
        if runner:
            argv = shlex.split(runner)
            if not argv or shutil.which(argv[0]) is None:
                raise RepaintError(
                    f"--diffusion-runner {runner!r}: {argv[0] if argv else '(empty)'} is not an "
                    f"executable on PATH.\n{self._missing_message()}")
            return
        host = urllib.parse.urlsplit(self.endpoint).hostname
        if host not in LOOPBACK_HOSTS:
            raise RepaintError(
                f"--diffusion-endpoint {self.endpoint} is not a loopback address "
                f"(host {host!r}). This backend only drives a diffusion runtime running on "
                "this machine: sending ROM-derived art to a remote host is ADR-0154 §2's "
                "rejected Option B, and there is no flag here that enables it.")
        workflow = self.workflow_path
        if workflow is None:
            raise RepaintError(
                "--diffusion-workflow is required for the ComfyUI path: there is no sane "
                "default graph, and guessing one would silently produce the wrong image.\n"
                + self._missing_message())
        if not workflow.is_file():
            raise RepaintError(
                f"--diffusion-workflow {workflow} does not exist.\n{self._missing_message()}")
        try:
            self._get("/system_stats", timeout=min(10, self._timeout()))
        except RepaintError as err:
            raise RepaintError(
                f"no diffusion runtime answered at {self.endpoint} ({err}).\n"
                + self._missing_message())

    def _missing_message(self):
        return DIFFUSION_MISSING_ENDPOINT.format(endpoint=self.endpoint)

    # -- transport (loopback only) -----------------------------------------

    def _url(self, path: str) -> str:
        url = f"{self.endpoint}{path}"
        host = urllib.parse.urlsplit(url).hostname
        if host not in LOOPBACK_HOSTS:  # belt and braces: never leaves the machine
            raise RepaintError(f"refusing to contact non-loopback host {host!r}")
        return url

    def _get(self, path: str, timeout=None) -> bytes:
        try:
            with urllib.request.urlopen(self._url(path), timeout=timeout or self._timeout()) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            raise RepaintError(f"GET {path} -> HTTP {err.code}")
        except (urllib.error.URLError, OSError) as err:
            raise RepaintError(f"GET {path} -> {err}")

    def _post_json(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self._url(path), data=body,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout()) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as err:
            detail = (err.read() or b"")[:400].decode("utf-8", "replace")
            raise RepaintError(f"POST {path} -> HTTP {err.code}: {detail}")
        except (urllib.error.URLError, OSError) as err:
            raise RepaintError(f"POST {path} -> {err}")
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as err:
            raise RepaintError(f"POST {path} -> answer is not JSON ({err})")
        if not isinstance(doc, dict):
            raise RepaintError(f"POST {path} -> answer is not a JSON object")
        return doc

    def _upload_control(self, png_bytes: bytes, name: str) -> str:
        """multipart/form-data to ComfyUI's /upload/image, hand-rolled: the
        stdlib has no multipart writer and this file takes no dependency."""
        boundary = "----sheet-repaint-" + uuid.uuid4().hex
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
            f"filename=\"{name}\"\r\nContent-Type: image/png\r\n\r\n".encode("utf-8"),
            png_bytes,
            f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\n"
            f"true\r\n--{boundary}--\r\n".encode("utf-8"),
        ]
        request = urllib.request.Request(
            self._url("/upload/image"), data=b"".join(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout()) as resp:
                doc = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            raise RepaintError(f"uploading the control image -> HTTP {err.code}")
        except (urllib.error.URLError, OSError, ValueError, UnicodeDecodeError) as err:
            raise RepaintError(f"uploading the control image -> {err}")
        uploaded = doc.get("name") if isinstance(doc, dict) else None
        if not uploaded:
            raise RepaintError(f"the runtime accepted the control image but named none: {doc}")
        subfolder = doc.get("subfolder") or ""
        return f"{subfolder}/{uploaded}" if subfolder else uploaded

    # -- workflow -----------------------------------------------------------

    def _graph(self, control_name: str, request: RepaintRequest) -> dict:
        text = self.workflow_path.read_text(encoding="utf-8")
        seed = getattr(self.options, "diffusion_seed", 0) or 0
        values = {
            "CONTROL_IMAGE": control_name,
            "PROMPT": getattr(self.options, "diffusion_prompt", "") or "",
            "NEGATIVE_PROMPT": getattr(self.options, "diffusion_negative_prompt", "") or "",
            "SEED": seed,
            "DENOISE": getattr(self.options, "diffusion_denoise", 0.55),
            "WIDTH": request.control.width,
            "HEIGHT": request.control.height,
            "SCALE": request.scale,
        }
        for key in DIFFUSION_PLACEHOLDERS:
            value = values[key]
            # `"__SEED__"` -> a bare number, so a numeric widget stays numeric;
            # a bare `__PROMPT__` inside a string is JSON-escaped in place.
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                text = text.replace(f'"__{key}__"', json.dumps(value))
            text = text.replace(f"__{key}__", json.dumps(str(value))[1:-1])
        try:
            graph = json.loads(text)
        except ValueError as err:
            raise RepaintError(
                f"--diffusion-workflow {self.workflow_path} is not valid JSON after "
                f"placeholder substitution ({err})")
        if not isinstance(graph, dict) or not graph:
            raise RepaintError(
                f"--diffusion-workflow {self.workflow_path} is not a ComfyUI API-format "
                "workflow (expected a non-empty object of node id -> node)")
        return graph

    def _wait_for(self, prompt_id: str) -> dict:
        deadline = time.monotonic() + self._timeout()
        while time.monotonic() < deadline:
            raw = self._get(f"/history/{urllib.parse.quote(prompt_id)}")
            try:
                history = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as err:
                raise RepaintError(f"the runtime's history is not JSON ({err})")
            entry = history.get(prompt_id) if isinstance(history, dict) else None
            if isinstance(entry, dict) and entry.get("outputs"):
                status = (entry.get("status") or {})
                if status.get("status_str") == "error":
                    raise RepaintError(f"the runtime reported an error for prompt {prompt_id}")
                return entry
            time.sleep(0.5)
        raise RepaintError(
            f"prompt {prompt_id} did not finish within {self._timeout()}s "
            "(raise --backend-timeout, or check the runtime's own log)")

    @staticmethod
    def _first_image(entry: dict) -> dict:
        for node in (entry.get("outputs") or {}).values():
            for image in (node or {}).get("images") or []:
                if isinstance(image, dict) and image.get("filename"):
                    return image
        raise RepaintError(
            "the workflow finished but produced no image — its output node is probably a "
            "PreviewImage; use SaveImage so the result is retrievable over the API")

    # -- generation ---------------------------------------------------------

    def repaint(self, request: RepaintRequest) -> Image:
        with tempfile.TemporaryDirectory(prefix="sheet-repaint-diffusion-") as tmp:
            control = Path(tmp) / "control.png"
            write_png(control, request.control)
            runner = self.runner
            image = (self._repaint_with_runner(runner, control, Path(tmp) / "out.png", request)
                     if runner else self._repaint_with_comfy(control, request))
        if image.width != request.control.width or image.height != request.control.height:
            raise RepaintError(
                f"the diffusion backend returned {image.width}x{image.height}, expected "
                f"{request.control.width}x{request.control.height} — the workflow is resizing "
                "the control image; fix the graph rather than letting the crop list drift")
        return image

    def _repaint_with_runner(self, runner: str, control: Path, out: Path,
                             request: RepaintRequest) -> Image:
        cmd = shlex.split(runner) + [str(control), str(out), str(request.scale)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout())
        except FileNotFoundError:
            raise RepaintError(f"--diffusion-runner {runner!r}: command not found")
        except subprocess.TimeoutExpired:
            raise RepaintError(f"--diffusion-runner {runner!r} did not finish within "
                               f"{self._timeout()}s")
        if proc.returncode != 0:
            raise RepaintError(f"--diffusion-runner {runner!r} exited {proc.returncode}: "
                               f"{(proc.stderr or proc.stdout or '').strip()[:400]}")
        if not out.is_file():
            raise RepaintError(f"--diffusion-runner {runner!r} wrote no image to {out}")
        return read_png(out)

    def _repaint_with_comfy(self, control: Path, request: RepaintRequest) -> Image:
        name = self._upload_control(control.read_bytes(), f"sheet-repaint-{self.client_id}.png")
        graph = self._graph(name, request)
        answer = self._post_json("/prompt", {"prompt": graph, "client_id": self.client_id})
        prompt_id = answer.get("prompt_id")
        if not prompt_id:
            raise RepaintError(f"the runtime queued nothing: {answer}")
        entry = self._wait_for(str(prompt_id))
        image = self._first_image(entry)
        query = urllib.parse.urlencode({
            "filename": image.get("filename"),
            "subfolder": image.get("subfolder") or "",
            "type": image.get("type") or "output",
        })
        raw = self._get(f"/view?{query}")
        with tempfile.TemporaryDirectory(prefix="sheet-repaint-view-") as tmp:
            path = Path(tmp) / "out.png"
            path.write_bytes(raw)
            return read_png(path)


BACKENDS = {
    "passthrough": PassthroughBackend,
    "null": PassthroughBackend,  # documented alias
    "classical": ClassicalBackend,
    "esrgan": EsrganBackend,
    "diffusion": DiffusionBackend,
}


# --- the pipeline -----------------------------------------------------------


def apply_alpha(generated: Image, control: Image, verbose=False, label=""):
    """ADR-0154 §7: alpha always comes from the source, and the RGB of a fully
    transparent pixel is zeroed so no halo can leak into a sliced crop."""
    if generated.width != control.width or generated.height != control.height:
        raise RepaintError(
            f"backend returned {generated.width}x{generated.height}, "
            f"expected {control.width}x{control.height}")
    px, src = generated.px, control.px
    for o in range(3, len(px), 4):
        a = src[o]
        px[o] = a
        if a == 0:
            px[o - 3:o] = b"\x00\x00\x00"
    if verbose:
        print(f"info: {label}: alpha taken from the source (any backend alpha is discarded)")
    return generated


def _palette_of(img: Image, region: Region):
    """The distinct opaque colours of a cell, most-frequent first. On NES art
    this is the cell's palette in use order; it is read off the pixels rather
    than off `tiles[].palette` because only the pixels say which of the four
    indexes actually got drawn."""
    counts = {}
    for y in range(region.y, region.y + region.h):
        for x in range(region.x, region.x + region.w):
            r, g, b, a = img.get(x, y)
            if a == 0:
                continue
            counts[(r, g, b)] = counts.get((r, g, b), 0) + 1
    return [c for c, _n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def recolour(generated: Image, canonical: Region, source: Image,
             canon_src: Region, variant_src: Region, verbose=False):
    """ADR-0154 §5: produce a palette variant of an already generated cell.

    Every generated pixel is matched to the nearest colour of the canonical
    cell's palette; the residual is kept and re-applied on top of the variant's
    colour at the same index, so shading and dithering survive while the
    silhouette (which comes from one generation and one alpha mask) does not
    move. Missing indexes degrade to identity, loudly, rather than inventing a
    mapping."""
    canon_pal = _palette_of(source, canon_src)
    var_pal = _palette_of(source, variant_src)
    if not canon_pal:
        return generated.crop(canonical.x, canonical.y, canonical.w, canonical.h)
    if len(var_pal) < len(canon_pal) and verbose:
        print(f"info: palette variant uses {len(var_pal)} colours against the canonical "
              f"{len(canon_pal)} — the missing indexes are left unchanged")
    out = generated.crop(canonical.x, canonical.y, canonical.w, canonical.h)
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = out.get(x, y)
            if a == 0:
                continue
            best, best_d = 0, None
            for i, (cr, cg, cb) in enumerate(canon_pal):
                d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
                if best_d is None or d < best_d:
                    best, best_d = i, d
            if best >= len(var_pal):
                continue
            cr, cg, cb = canon_pal[best]
            vr, vg, vb = var_pal[best]
            out.set(x, y, (_clamp(vr + r - cr), _clamp(vg + g - cg), _clamp(vb + b - cb), a))
    return out


def _clamp(v: int) -> int:
    return 0 if v < 0 else (255 if v > 255 else v)


def adjacency_pairs(sheets, scale: int):
    """Ordered `(vocab_a, side, vocab_b)` pairs read off the maps' placements
    (ADR-0154 §6) — adjacency is data, never a guess. `side` is "E" when b sits
    east of a and "S" when it sits south."""
    pairs = set()
    for sheet in sheets:
        if sheet.kind != MAP_KIND:
            continue
        unit = sheet.unit
        by_pos = {}
        for p in sheet.placements:
            try:
                by_pos[(int(p["x"]), int(p["y"]))] = int(p["cell"])
            except (KeyError, TypeError, ValueError):
                continue
        for (x, y), cell in by_pos.items():
            east = by_pos.get((x + unit, y))
            if east is not None:
                pairs.add((cell, "E", east))
            south = by_pos.get((x, y + unit))
            if south is not None:
                pairs.add((cell, "S", south))
    return sorted(pairs)


def seam_pass(img: Image, rect_pairs, width: int):
    """Symmetrise the border band of every adjacent rect pair.

    `rect_pairs` is [(rect_a, side, rect_b)] in target pixels. For offset j
    from the border, f = 0.5*(W-j)/W and both sides move toward each other by
    f, computed from the pre-blend values — so at j = 0 the two touching lines
    become their plain average and a stripe crosses the border continuously.

    Only the W-pixel band inside each cell is written: never the interior,
    never the gutter. A pixel pair where either side is fully transparent is
    skipped, so the pass can neither grow nor erode a silhouette."""
    if width <= 0:
        return img
    for rect_a, side, rect_b in rect_pairs:
        for j in range(width):
            f = 0.5 * (width - j) / width
            if side == "E":
                if j >= rect_a.w or j >= rect_b.w:
                    break
                ax = rect_a.x + rect_a.w - 1 - j
                bx = rect_b.x + j
                span = min(rect_a.h, rect_b.h)
                coords = [((ax, rect_a.y + k), (bx, rect_b.y + k)) for k in range(span)]
            else:
                if j >= rect_a.h or j >= rect_b.h:
                    break
                ay = rect_a.y + rect_a.h - 1 - j
                by = rect_b.y + j
                span = min(rect_a.w, rect_b.w)
                coords = [((rect_a.x + k, ay), (rect_b.x + k, by)) for k in range(span)]
            for (axp, ayp), (bxp, byp) in coords:
                if not (0 <= axp < img.width and 0 <= ayp < img.height):
                    continue
                if not (0 <= bxp < img.width and 0 <= byp < img.height):
                    continue
                a = img.get(axp, ayp)
                b = img.get(bxp, byp)
                if a[3] == 0 or b[3] == 0:
                    continue
                blended_a = tuple(_clamp(int(round((1 - f) * a[i] + f * b[i]))) for i in range(3)) + (a[3],)
                blended_b = tuple(_clamp(int(round((1 - f) * b[i] + f * a[i]))) for i in range(3)) + (b[3],)
                img.set(axp, ayp, blended_a)
                img.set(bxp, byp, blended_b)
    return img


def _rects_by_vocab(sheet: Sheet, regions):
    by_vocab = {}
    for region in regions:
        if region.vocab is not None:
            by_vocab.setdefault(region.vocab, region)
    return by_vocab


def seam_rect_pairs(sheet: Sheet, regions, pairs):
    """Turn the vocabulary pair table into rect pairs for one sheet: on a map,
    geometric neighbours; on a contact sheet, the cells that render the paired
    vocabulary entries (they are not physically adjacent there — separated by
    ADR-0153's gutter — but they must still tile in game)."""
    if sheet.kind == MAP_KIND:
        unit = sheet.unit
        scale = regions[0].w // unit if regions and unit else 1
        by_pos = {(r.x, r.y): r for r in regions}
        out = []
        for r in regions:
            east = by_pos.get((r.x + unit * scale, r.y))
            if east is not None:
                out.append((r, "E", east))
            south = by_pos.get((r.x, r.y + unit * scale))
            if south is not None:
                out.append((r, "S", south))
        return out
    by_vocab = _rects_by_vocab(sheet, regions)
    out = []
    for a, side, b in pairs:
        ra, rb = by_vocab.get(a), by_vocab.get(b)
        if ra is not None and rb is not None and ra is not rb:
            out.append((ra, side, rb))
    return out


def repaint_sheet(sheet: Sheet, backend: RepaintBackend, scale: int, pairs,
                  seam_width: int, variants: bool, verbose: bool) -> Image:
    """One sheet, end to end: control image -> backend -> alpha -> palette
    variants -> seam pass."""
    source = read_png(sheet.png_path)
    control = source.upscale(scale)
    regions = crop_list(sheet, scale)
    request = RepaintRequest(source, control, scale, sheet.kind, regions, sheet)
    generated = backend.repaint(request)
    if not isinstance(generated, Image):
        raise RepaintError(f"backend '{backend.name}' did not return an Image")
    generated = apply_alpha(generated, control, verbose=verbose, label=sheet.png_path.name)

    if variants and sheet.kind in CONTACT_KINDS:
        _apply_variants(sheet, generated, control, regions, verbose)

    seam_pass(generated, seam_rect_pairs(sheet, regions, pairs), seam_width * scale)
    return generated


def _apply_variants(sheet: Sheet, generated: Image, control: Image, regions, verbose: bool):
    """Group the sheet's cells by tile-shape tuple; keep the highest-`count`
    member as the canonical generation and rebuild every other member from it
    by recolour (ADR-0154 §5)."""
    groups = {}
    for region in regions:
        if region.index >= len(sheet.cells):
            continue
        cell = sheet.cells[region.index]
        key = shape_key(cell)
        if key is None:
            continue
        groups.setdefault(key, []).append((region, cell))
    for key, members in groups.items():
        if len(members) < 2:
            continue
        palettes = {palette_key(c) for _r, c in members}
        if len(palettes) < 2:
            continue
        members.sort(key=lambda rc: -int(rc[1].get("count") or 0))
        canon_region, _canon_cell = members[0]
        for region, _cell in members[1:]:
            patch = recolour(generated, canon_region, control, canon_region, region, verbose=verbose)
            generated.paste(patch, region.x, region.y)
        if verbose:
            print(f"info: {sheet.png_path.name}: {len(members) - 1} palette variant(s) recoloured "
                  f"from one generation")


# --- screens: the primary target (ADR-0154 §2, ADR-0050) --------------------


BACKGROUND_LINE = re.compile(r"^(?P<cond>\[[^\]]*\])?<background>(?P<body>.*)$")
CONDITION_LINE = re.compile(r"^<condition>(?P<name>[^,]+),(?P<rest>.*)$")
# Header tags copied verbatim into the repaint's own manifest. `scale` is the
# exception: it is multiplied, because the repaint really is N times bigger.
HIRES_HEADER_TAGS = ("ver", "system", "supportedRom", "overscan", "options")


class Screen:
    """One `<background>` entry: the captured 256x240 scene, its condition
    prefix (`[screen001_A&screen001_B&screen001_C]`, the `tileAtPosition`
    anchors ADR-0050 emits) and the rest of the entry's fields, all preserved
    verbatim so the repaint's manifest is the recorder's manifest at another
    resolution."""

    __slots__ = ("cond", "rel", "rest", "png_path", "orig_path")

    def __init__(self, cond: str, rel: str, rest, textures_dir: Path):
        self.cond = cond or ""
        self.rel = rel
        self.rest = rest
        self.png_path = textures_dir / rel
        # F5.4d's twin convention, the same one the sheets use: screen001.png
        # is the paintable copy, screen001.orig.png the untouched capture.
        self.orig_path = self.png_path.parent / f"{self.png_path.stem}.orig.png"

    @property
    def name(self) -> str:
        return self.png_path.name

    def condition_names(self):
        """The condition names the prefix references, `!` negation stripped."""
        if not self.cond:
            return []
        inner = self.cond.strip("[]")
        return [part.strip().lstrip("!") for part in inner.split("&") if part.strip()]

    def line(self) -> str:
        return f"{self.cond}<background>{','.join([self.rel] + list(self.rest))}"


class HiresManifest:
    """The recorder's `textures/hires.txt`, parsed down to what a screen
    repaint needs: the header tags, the `<condition>` lines by name (in file
    order) and the `<background>` entries."""

    def __init__(self, path: Path):
        self.path = path
        self.textures_dir = path.parent
        self.scale = 1
        self.header = []
        self.conditions = {}
        self.screens = []


def find_hires_txt(target: Path) -> Path:
    """`target` may be the textures folder, a pack folder, or a game folder
    with an `auto/` sibling (ADR-0147) — the same candidate order as
    `find_sheets_dir`, so one positional argument serves both targets."""
    for cand in (target / "hires.txt",
                 target / "textures" / "hires.txt",
                 target / "auto" / "textures" / "hires.txt"):
        if cand.is_file():
            return cand
    raise RepaintError(
        f"no textures/hires.txt under {target} — --target screens repaints the "
        "<background> entries of a recording, and that is where they are declared")


def parse_hires(path: Path) -> HiresManifest:
    doc = HiresManifest(path)
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("<scale>"):
            try:
                doc.scale = max(1, int(line[len("<scale>"):].strip()))
            except ValueError:
                pass
            continue
        if any(line.startswith(f"<{tag}>") for tag in HIRES_HEADER_TAGS):
            doc.header.append(line)
            continue
        cond = CONDITION_LINE.match(line)
        if cond:
            doc.conditions.setdefault(cond.group("name").strip(), line)
            continue
        match = BACKGROUND_LINE.match(line)
        if not match:
            continue
        fields = match.group("body").split(",")
        if not fields or not fields[0].strip():
            print(f"warning: {path.name}: a <background> entry names no file, skipped",
                  file=sys.stderr)
            continue
        doc.screens.append(Screen(match.group("cond"), fields[0].strip(),
                                  [f.strip() for f in fields[1:]], doc.textures_dir))
    return doc


def render_screen_hires(doc: HiresManifest, kept, factor: int) -> str:
    """The repaint's own `hires.txt`: the recorder's header with `<scale>`
    multiplied, then **only** the `<condition>` lines the kept entries
    reference, then those entries verbatim.

    Self-contained on purpose: the repaint folder carries backgrounds and
    nothing else, so copying the recorder's `<img>`/`<tile>` lines would leave
    a manifest pointing at files that are not there — which is a lint error
    and a load-time drop, not a cosmetic problem."""
    lines = [f"<scale>{doc.scale * factor}"]
    lines[:0] = [line for line in doc.header if line.startswith("<ver>")]
    lines += [line for line in doc.header if not line.startswith("<ver>")]
    wanted = []
    for screen in kept:
        for name in screen.condition_names():
            if name in doc.conditions and name not in wanted:
                wanted.append(name)
    lines += [doc.conditions[name] for name in wanted]
    lines += [screen.line() for screen in kept]
    return "\n".join(lines) + "\n"


def repaint_screen(screen: Screen, backend: RepaintBackend, scale: int, verbose: bool) -> Image:
    """A whole scene, end to end. No palette variants and no seam pass: a
    captured screen is one continuous image, it has no cell vocabulary and no
    border to symmetrise. Alpha still comes from the source (ADR-0154 §7),
    which on an opaque background is a no-op and on a masked one is not."""
    source = read_png(screen.png_path)
    control = source.upscale(scale)
    region = Region(0, 0, control.width, control.height, None, 0)
    request = RepaintRequest(source, control, scale, "screen", [region], None)
    generated = backend.repaint(request)
    if not isinstance(generated, Image):
        raise RepaintError(f"backend '{backend.name}' did not return an Image")
    return apply_alpha(generated, control, verbose=verbose, label=screen.name)


def write_screen_output(out_root: Path, screen: Screen, image: Image):
    out_dir = out_root / "textures" / Path(screen.rel).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    write_png(out_dir / screen.name, image)
    if screen.orig_path is not None and screen.orig_path.is_file():
        shutil.copyfile(screen.orig_path, out_dir / screen.orig_path.name)


def run_screens(target: Path, out_arg, scale: int, backend: RepaintBackend,
                wanted, verbose: bool) -> int:
    """`--target screens`. Returns the number of scenes repainted."""
    hires = find_hires_txt(target)
    doc = parse_hires(hires)
    if not doc.screens:
        raise RepaintError(
            f"{hires} declares no <background> entry — this recording has no captured "
            "screen to repaint (ADR-0050 emits them only for stable, non-scrolling scenes)")
    kept = []
    for screen in doc.screens:
        if wanted and screen.png_path.stem not in wanted:
            continue
        if not screen.png_path.is_file():
            print(f"warning: <background> {screen.rel} does not exist, skipped", file=sys.stderr)
            continue
        kept.append(screen)
    if not kept:
        raise RepaintError(
            f"none of the {len(doc.screens)} <background> entries in {hires.name} resolved to a "
            "file this tool can read")

    out_root = Path(out_arg) if out_arg else default_out_dir(hires.parent)
    out_root.mkdir(parents=True, exist_ok=True)
    for screen in kept:
        image = repaint_screen(screen, backend, scale, verbose)
        write_screen_output(out_root, screen, image)
        print(f"repainted {screen.rel} -> {out_root.name}/textures/{screen.rel} "
              f"({image.width}x{image.height}, backend {backend.name})")
    (out_root / "textures").mkdir(parents=True, exist_ok=True)
    (out_root / "textures" / "hires.txt").write_text(
        render_screen_hires(doc, kept, scale), encoding="utf-8")
    try:
        source_rel = str(hires.parent.relative_to(out_root.parent.parent))
    except ValueError:
        source_rel = str(hires.parent)
    stamp_pack_json(out_root, backend.name, scale * doc.scale, source_rel,
                    f"{out_root.parent.parent.name} — machine repaint",
                    inherited=inherit_manifest(hires.parent))
    print(f"labelled generated in {out_root / 'pack.json'} (ADR-0154 §3)")
    return len(kept)


# --- output -----------------------------------------------------------------


def inherit_manifest(sheets_dir: Path) -> dict:
    """The nearest existing `pack.json` around the source sheets, searched
    most-specific first. Only `mep`, `targets`, `license` and `author` are
    read from it: the repaint identifies the same ROM as the pack it was
    derived from, and without `targets` a stub manifest cannot lint clean
    (`'targets' must be a non-empty array`)."""
    seen = []
    for parent in [sheets_dir, *sheets_dir.parents]:
        for cand in (parent / "pack.json", parent / "mep" / "pack.json"):
            if cand in seen or not cand.is_file():
                continue
            seen.append(cand)
            try:
                doc = json.loads(cand.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(doc, dict) and isinstance(doc.get("targets"), list) and doc["targets"]:
                return doc
    return {}


def stamp_pack_json(out_root: Path, backend_name: str, scale: int, source_rel: str,
                    name: str, inherited: dict = None, sections=("textures",)) -> dict:
    """Write or update `<out_root>/pack.json` with the ADR-0154 §3 `generated`
    object. An existing manifest keeps every other field: the label is
    additive, and MEP-v1 §3.2 makes unknown fields ignorable, so stamping one
    never invalidates a pack.

    `targets` is inherited (never invented) so that the stub lints clean and
    `mep_build build` can run on the repaint. With nothing to inherit the
    field is left out and the caller is told exactly which lint error to
    expect and how to fix it."""
    path = out_root / "pack.json"
    doc = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                doc = loaded
        except (OSError, ValueError) as err:
            print(f"warning: {path}: unreadable, rewritten from scratch ({err})", file=sys.stderr)
    inherited = inherited or {}
    doc.setdefault("mep", inherited.get("mep") if isinstance(inherited.get("mep"), str) else "1.5.0")
    doc.setdefault("name", name)
    doc.setdefault("version", "0.1.0")
    for key in ("license", "author"):
        if key not in doc and isinstance(inherited.get(key), str):
            doc[key] = inherited[key]
    if "targets" not in doc and inherited.get("targets"):
        doc["targets"] = inherited["targets"]
    doc.setdefault("sections", {s: {"path": f"{s}/"} for s in sections})
    doc["generated"] = {
        "by": "sheet_repaint",
        "backend": backend_name,
        "date": datetime.date.today().isoformat(),
        "scale": scale,
        "source": source_rel,
    }
    path.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    if not doc.get("targets"):
        print(f"warning: {path}: no neighbouring pack.json to inherit 'targets' from — "
              "mep_build will report \"'targets' must be a non-empty array\" until you supply one "
              "(mep_build pack --rom <ROM>)", file=sys.stderr)
    return doc


def default_out_dir(sheets_dir: Path) -> Path:
    """ADR-0154 §4: `<Game>/auto/repaint`. A *sub*folder of `auto/`, because
    `bootstrap_auto_packs.sh` does `rm -rf auto/textures` on every re-record,
    and because overwriting the recorder's sheets would destroy the reference
    the artist and PRD test 8 compare against."""
    for parent in sheets_dir.parents:
        if parent.name == "auto":
            return parent / "repaint"
    # Not under auto/ (an authored pack, or a bare sheets folder): keep the
    # same shape one level up from textures/.
    base = sheets_dir.parent.parent if sheets_dir.parent.name == "textures" else sheets_dir.parent
    return base / "auto" / "repaint"


def write_output(out_root: Path, sheet: Sheet, image: Image):
    """The repaint, the sidecar verbatim, and a copy of the 1x `*.orig.png`
    twin — the twin is what makes `mep_build` count these cells as *painted*
    (ADR-0153 §4), so it is not optional decoration."""
    out_sheets = out_root / "textures" / "sheets"
    out_sheets.mkdir(parents=True, exist_ok=True)
    write_png(out_sheets / sheet.png_path.name, image)
    shutil.copyfile(sheet.json_path, out_sheets / sheet.json_path.name)
    if sheet.orig_path is not None and sheet.orig_path.is_file():
        shutil.copyfile(sheet.orig_path, out_sheets / sheet.orig_path.name)
    else:
        print(f"warning: {sheet.png_path.name}: no readable *.orig.png twin — mep_build will fall "
              "back to the static kind rank for its cells (ADR-0153 §4)", file=sys.stderr)


# --- cli --------------------------------------------------------------------


def build_parser():
    p = argparse.ArgumentParser(
        description="Repaint ADR-0153 artist sheets into auto/repaint (PRD F9.6, ADR-0154).")
    p.add_argument("target", metavar="PACK",
                   help="a sheets/ folder, a pack folder, or a game folder with auto/")
    p.add_argument("--out", help="output root (default: <Game>/auto/repaint)")
    p.add_argument("--scale", type=int, default=DEFAULT_SCALE, help="integer upscale factor")
    p.add_argument("--target", dest="what", default="sheets",
                   choices=("sheets", "screens", "both"),
                   help="what to repaint: the ADR-0153 artist sheets, the captured "
                        "<background> screens (ADR-0154 §2's primary target), or both")
    p.add_argument("--backend", default="passthrough", choices=sorted(BACKENDS),
                   help="generation backend (default: passthrough, a nearest-neighbour upscale)")
    p.add_argument("--sheets", help="comma-separated sheet/screen names to repaint (default: all)")
    p.add_argument("--backend-timeout", type=int, default=600,
                   help="seconds a local backend process/queue may take per image")
    esrgan = p.add_argument_group("esrgan backend (a Real-ESRGAN install you already have)")
    esrgan.add_argument("--esrgan-binary", help="runner executable (env SHEET_REPAINT_ESRGAN_BIN)")
    esrgan.add_argument("--esrgan-model", help="weights file or model dir "
                                               "(env SHEET_REPAINT_ESRGAN_MODEL)")
    diffusion = p.add_argument_group("diffusion backend (a local ComfyUI/diffusers, ADR-0154 §2)")
    diffusion.add_argument("--diffusion-endpoint", default=None,
                           help=f"local ComfyUI HTTP endpoint, loopback only "
                                f"(default {DEFAULT_COMFY_ENDPOINT}, env SHEET_REPAINT_COMFY_URL)")
    diffusion.add_argument("--diffusion-workflow",
                           help="ComfyUI API-format workflow JSON with __CONTROL_IMAGE__/"
                                "__PROMPT__/__SEED__/… placeholders")
    diffusion.add_argument("--diffusion-runner",
                           help="local command run as `<cmd> <control.png> <out.png> <scale>` "
                                "— the diffusers path; overrides the ComfyUI endpoint")
    diffusion.add_argument("--diffusion-prompt", default="", help="positive prompt")
    diffusion.add_argument("--diffusion-negative-prompt", default="", help="negative prompt")
    diffusion.add_argument("--diffusion-seed", type=int, default=0)
    diffusion.add_argument("--diffusion-denoise", type=float, default=0.55,
                           help="ControlNet denoise strength (default 0.55)")
    p.add_argument("--seam-width", type=int, default=DEFAULT_SEAM_WIDTH,
                   help="seam band in 1x pixels; 0 disables the seam pass")
    p.add_argument("--no-variants", action="store_true",
                   help="generate every palette variant independently instead of recolouring one")
    p.add_argument("--verbose", action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.scale < 1:
        print("error: --scale must be >= 1", file=sys.stderr)
        return 2
    if args.seam_width < 0:
        print("error: --seam-width must be >= 0", file=sys.stderr)
        return 2

    target = Path(args.target)
    wanted = {s.strip() for s in args.sheets.split(",")} if args.sheets else None

    try:
        # The availability probe runs before anything is read or written, so a
        # backend that cannot run leaves no half-written output tree behind
        # (ADR-0154 §1). It never downloads; it names what to install.
        backend = BACKENDS[args.backend](args)
        backend.ensure_available()

        if args.what in ("screens", "both"):
            try:
                count = run_screens(target, args.out, args.scale, backend, wanted, args.verbose)
                print(f"{count} captured screen(s) repainted; the repaint's own hires.txt keeps "
                      "the condition-prefixed <background> entries")
            except RepaintError as err:
                if args.what == "screens":
                    raise
                print(f"warning: --target both: no screens repainted ({err})", file=sys.stderr)
        if args.what == "screens":
            return 0

        sheets_dir = find_sheets_dir(target)
        sheets = load_sheets(sheets_dir, wanted)
        if not sheets:
            print(f"error: no usable ADR-0153 sheet under {sheets_dir}", file=sys.stderr)
            return 1

        pairs = adjacency_pairs(sheets, args.scale)
        out_root = Path(args.out) if args.out else default_out_dir(sheets_dir)
        out_root.mkdir(parents=True, exist_ok=True)

        for sheet in sheets:
            image = repaint_sheet(sheet, backend, args.scale, pairs, args.seam_width,
                                  not args.no_variants, args.verbose)
            write_output(out_root, sheet, image)
            print(f"repainted {sheet.png_path.name} -> {out_root.name}/textures/sheets/"
                  f"{sheet.png_path.name} ({image.width}x{image.height}, backend {backend.name})")

        try:
            source_rel = str(sheets_dir.relative_to(out_root.parent.parent))
        except ValueError:
            source_rel = str(sheets_dir)
        stamp_pack_json(out_root, backend.name, args.scale, source_rel,
                        f"{out_root.parent.parent.name} — machine repaint",
                        inherited=inherit_manifest(sheets_dir))
        print(f"labelled generated in {out_root / 'pack.json'} (ADR-0154 §3)")
        print(f"build it with: python3 scripts/mep_build.py build {out_root} "
              f"--source {sheets_dir.parent / 'hires.txt'}")
    except RepaintError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
