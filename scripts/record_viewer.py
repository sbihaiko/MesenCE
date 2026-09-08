"""The live recording viewer (ADR-0169 / F9.14) — watches a headless recording
as it runs and draws the two things ADR-0169 section 2 says the recorder
publishes: the composed frame and the sprite layer read as data.

`scripts/headless_record <rom> <seconds> <prefix> ... live=<ms>` publishes, every
<ms> of wall clock, into `<prefix>-live/` as an atomic file swap (lossy-latest,
ADR-0169 section 1):

    frame.ppm     the composed frame the emulator rendered (P6, its own scale)
    sprites.json  the sprite layer as data: raw OAM, palette RAM, PPU control
    chr.bin       the $0000-$1FFF pattern tables, mapper-resolved
    palette.json  the 64 RGB colors this run renders with (written once)
    status.json   progress / done

Run it against that folder:

    python3 scripts/record_viewer.py <prefix>-live/

This tool polls that directory, draws what it finds, and writes nothing
(ADR-0169 section 3). The sprite pane is a *reconstruction*: OAM entries are
expanded through the NES 8x8/8x16 rules of NesPpu::LoadSprite, so it ignores
the hardware it cannot see — the 8-sprite-per-scanline limit and the left
8-column mask — and is labelled as such. It may disagree with the composed
frame above it; that disagreement is the point (it shows what the OAM *said*,
before the PPU's limits applied).

Read-only, stdlib plus tkinter, an external tool in `scripts/` never linked
into the emulator (ADR-0165). The pure reconstruction helpers live above the
GUI class so the parsing/render can be exercised without a display.
"""

import argparse
import json
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk

# The NES sprite plane, in its own native pixels (the recorder's frame.ppm may
# be scaled, e.g. 2x -> 512x480; geometry_scale() recovers the factor).
NATIVE_W = 256
NATIVE_H = 240

# An OAM y >= 0xF0 puts the sprite's rows entirely below the last visible
# scanline (it wrapped off the bottom), so the PPU never shows it — skip it
# the same way the hardware does.
HIDDEN_SPRITE_Y = 0xF0

# Backdrop for the sprite pane, so transparent pixels read as "no sprite here"
# rather than as black art (same trick as compose_editor's image_photo).
BACKDROP = (0x16, 0x16, 0x1E)

SPRITE_RECONSTRUCTION_CAVEAT = (
    "rebuilt from OAM — ignores the PPU's 8-sprites-per-scanline limit and the "
    "left 8-column mask, and draws behind-background sprites as-is, so a sprite "
    "here may be absent from the frame above")


def geometry_scale(width, height):
    """Integer uniform scale of a captured frame back to the native NES plane,
    or None when the geometry is not a clean multiple (unexpected for a capture
    the emulator itself scaled)."""
    if width and height and width % NATIVE_W == 0 and height % NATIVE_H == 0:
        sx, sy = width // NATIVE_W, height // NATIVE_H
        if sx == sy:
            return sx
    return None


def parse_ppm_geometry(path):
    """(width, height) from a P6 PPM header. Reads only the header bytes; the
    pixels stay on disk for tk.PhotoImage."""
    with open(path, "rb") as f:
        magic = f.readline().strip()
        dims = f.readline().split()
        if magic != b"P6" or len(dims) != 2:
            raise ValueError(f"{path.name} is not a P6 PPM (bad header)")
        return int(dims[0]), int(dims[1])


def parse_sprites_json(text):
    """Validate and normalise one sprites.json into a plain dict. Raises
    ValueError with a reader-facing message when the file is not what ADR-0169
    section 2 publishes (atomic rename means a torn file is impossible, but a
    foreign file is)."""
    data = json.loads(text)
    palette = data["palette"]
    oam = data["oam"]
    if len(palette) != 0x20 or len(oam) != 64:
        raise ValueError("sprites.json is not an ADR-0169 sprite record")
    if any(len(entry) != 4 for entry in oam):
        raise ValueError("sprites.json OAM entry is not [y, tile, attr, x]")
    # Raw OAM layout: each entry is [y, tile, attr, x].
    return {
        "frame": int(data["frame"]),
        "captureFrame": int(data["captureFrame"]),
        "patternAddr": int(data["patternAddr"]) & 0x1000,
        "largeSprites": bool(data["largeSprites"]),
        "spritesEnabled": bool(data["spritesEnabled"]),
        "leftColumnClip": bool(data["leftColumnClip"]),
        "palette": list(palette),
        "oam": oam,
    }


def load_colors(path):
    """The run's 64 RGB colors (palette.json), as (r, g, b) tuples indexed by
    NES color number 0x00-0x3F."""
    data = json.loads(path.read_text())
    colors = data["colors"]
    if len(colors) != 64:
        raise ValueError(f"{path.name} does not carry the 64-color table")
    out = []
    for c in colors:
        out.append((int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)))
    return out


def _tile_base(tile, large, pattern_addr):
    """Absolute chr.bin address of a sprite's first 8x8 tile row (ADR-0169 /
    NesPpu::LoadSprite)."""
    if large:
        # Bit 0 of the tile selects the pattern table; the remaining bits index
        # a pair of 8x8 tiles that make the 8x16 sprite.
        return ((tile & 1) << 12) | ((tile & ~1) << 4)
    return pattern_addr | (tile << 4)


def build_native_plane(sprites, chr_bytes):
    """Sprite layer at native 256x240, as a bytearray whose cells hold the
    palette-RAM slot each pixel's color comes from (0 = no sprite pixel). OAM
    order decides overlap: a lower OAM index has priority (drawn on top), so
    ascending order and first-write-wins reproduce it.

    Returns (plane, touched) where touched[i] says OAM sprite i put down at
    least one pixel — a sprite whose whole tile is transparent never shows, so
    it should not be outlined either."""
    plane = bytearray(NATIVE_W * NATIVE_H)
    touched = [False] * len(sprites["oam"])
    large = sprites["largeSprites"]
    size = 16 if large else 8
    size_mask = size - 1
    pattern_addr = sprites["patternAddr"]
    oam = sprites["oam"]

    for i, (y0, tile, attr, x) in enumerate(oam):
        if y0 >= HIDDEN_SPRITE_Y:
            continue  # wrapped below the visible area - the PPU never shows it
        h_mirror = bool(attr & 0x40)
        v_mirror = bool(attr & 0x80)
        palette_base = ((attr & 3) << 2) | 0x10

        top = max(0, y0)
        bottom = min(NATIVE_H, y0 + size)
        for row_y in range(top, bottom):
            sy = row_y - y0
            tile_row = (sy ^ size_mask) if v_mirror else sy  # LoadSprite flip
            if large:
                base = _tile_base(tile, True, pattern_addr)
                if tile_row >= 8:
                    base += 0x10  # second 8x8 half of the 8x16 sprite
                    tile_row -= 8
            else:
                base = _tile_base(tile, False, pattern_addr)
            low = chr_bytes[base + tile_row]
            high = chr_bytes[base + tile_row + 8]

            # Shifter outputs MSB-first: display column dx reads original bit
            # (7 - dx); a horizontal mirror reverses the byte first, so dx reads
            # original bit dx.
            for dx in range(8):
                bit = dx if h_mirror else 7 - dx
                color = ((high >> bit) & 1) << 1 | ((low >> bit) & 1)
                if not color:
                    continue  # transparent
                cx = x + dx
                if cx >= NATIVE_W:
                    continue
                cell = row_y * NATIVE_W + cx
                if plane[cell] == 0:
                    plane[cell] = palette_base + color  # 0x11..0x1F, never 0
                    touched[i] = True
    return plane, touched


def make_native_ppm(plane, palette_ram, colors):
    """The sprite pane as a P6 PPM (native 256x240), each sprite pixel colored
    from its palette-RAM slot -> the run's color table; transparent cells fall
    back to BACKDROP. The GUI zooms this to the composite's geometry."""
    out = bytearray(b"P6\n%d %d\n255\n" % (NATIVE_W, NATIVE_H))
    for slot in plane:
        if slot:
            r, g, b = colors[palette_ram[slot] & 0x3F]
        else:
            r, g, b = BACKDROP
        out += bytes((r, g, b))
    return bytes(out)


def sprite_boxes(sprites, touched):
    """(x, y, w, h) of the OAM sprites that put at least one pixel down, for
    bounding boxes on the composite pane. Empty (transparent) tiles and sprites
    wrapped off the bottom of the screen never show, so they get no box."""
    large = sprites["largeSprites"]
    size = 16 if large else 8
    for i, (y0, _tile, _attr, x) in enumerate(sprites["oam"]):
        if touched[i]:
            yield (x, y0, size, size)


class RecordViewerApp:
    POLL_MS = 100

    def __init__(self, root: tk.Tk, live_dir: Path):
        self.root = root
        self.live_dir = live_dir
        root.title("MesenCE — live recording viewer (ADR-0169)")
        self._imgs = []          # keep PhotoImages alive (Tk drops them on GC)
        self._seen = {}          # {path: (mtime_ns, size)} of the last draw
        self._status_text = None
        self._last_mark = None    # (sprites, fx, fy) of the last draw
        self._error = None       # reader-facing problem, shown in the status bar

        # ---- top bar: the live directory -----------------------------------
        top = ttk.Frame(root, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Live:").pack(side="left")
        ttk.Label(top, text=str(live_dir), foreground="#555").pack(side="left")
        ttk.Button(top, text="Poll now", command=self._poll).pack(side="right")
        self.status = tk.StringVar(value="starting…")
        ttk.Label(root, textvariable=self.status, foreground="#555",
                  wraplength=1400).pack(fill="x", padx=6)

        # ---- the two panes: composite | sprite layer -----------------------
        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        self.mark_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="mark sprite bounds on the composite",
                        variable=self.mark_var, command=self._redraw_marks).pack(anchor="w")
        self.composite_canvas = tk.Canvas(left, background="#000",
                                          highlightthickness=0)
        self.composite_canvas.pack()
        self.composite_caption = tk.StringVar()
        ttk.Label(left, textvariable=self.composite_caption, foreground="#888",
                  wraplength=520).pack(anchor="w", pady=(2, 0))

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.sprite_canvas = tk.Canvas(right, background="#000",
                                       highlightthickness=0)
        self.sprite_canvas.pack()
        self.sprite_caption = tk.StringVar(value=SPRITE_RECONSTRUCTION_CAVEAT)
        ttk.Label(right, textvariable=self.sprite_caption, foreground="#888",
                  wraplength=520).pack(anchor="w", pady=(2, 0))

        self.root.after(self.POLL_MS, self._poll)

    # ---- polling -----------------------------------------------------------

    def _file_stamp(self, name):
        path = self.live_dir / name
        try:
            st = path.stat()
            return path, st.st_mtime_ns, st.st_size
        except OSError:
            return path, None, None

    def _read_once(self):
        """Read frame.ppm + sprites.json (+ chr.bin) at one poll; atomic renames
        keep each file whole, and reading them in the recorder's own publish
        order (frame, then sprites, then chr) keeps the trio on the same tick to
        within one publish interval. Returns a dict, or raises."""
        frame_path, fm_ns, fm_size = self._file_stamp("frame.ppm")
        if fm_ns is None:
            return None
        w, h = parse_ppm_geometry(frame_path)
        out = {"ppm": frame_path, "width": w, "height": h, "scale": geometry_scale(w, h)}
        sp_path, sp_ns, sp_size = self._file_stamp("sprites.json")
        if sp_ns is None:
            out["sprites"] = None
            return out
        out["sprites"] = parse_sprites_json((self.live_dir / "sprites.json").read_text())
        chr_path, chr_ns, chr_size = self._file_stamp("chr.bin")
        pal_path, pal_ns, pal_size = self._file_stamp("palette.json")
        if chr_ns is not None and pal_ns is not None:
            out["chr"] = chr_path.read_bytes()
            out["colors"] = load_colors(pal_path)
        return out

    def _poll(self):
        try:
            self._poll_once()
        except Exception as e:  # keep the poll loop alive on a bad file
            self.status.set(f"cannot read live data: {e}")
        self.root.after(self.POLL_MS, self._poll)

    def _poll_once(self):
        stamp = {name: self._file_stamp(name)[1:] for name in
                 ("frame.ppm", "sprites.json", "chr.bin", "palette.json")}
        changed = any(stamp[n] != self._seen.get(n) for n in stamp)
        self._seen = stamp

        status_path, st_ns, st_size = self._file_stamp("status.json")
        status = {}
        if st_ns is not None:
            try:
                status = json.loads((self.live_dir / "status.json").read_text())
            except (ValueError, OSError):
                status = {}

        if st_ns is None or status.get("frame") is None:
            self.status.set(f"no run in progress — waiting for {self.live_dir}")
            return
        if not changed and self._status_text is not None:
            self.status.set(self._status_text)
            return

        state = self._read_once()
        self._status_text = None
        if state is None:
            self.status.set(f"no frames published yet — waiting for {self.live_dir}")
            return

        frame = status.get("frame", "?")
        target = status.get("targetFrames", "?")
        done = bool(status.get("done"))
        wall = status.get("elapsedWallSec", 0)
        state_text = (
            f"frame {frame}/{target} · wall {wall}s" + (" · done — recording stopped"
            if done else "") + f" · capture {state['sprites']['captureFrame'] if state['sprites'] else '—'}")

        if state["sprites"] is not None:
            sp = state["sprites"]
            if not sp["spritesEnabled"]:
                state_text += " · sprites disabled on this frame (OAM may be stale)"
            self.sprite_caption.set(
                SPRITE_RECONSTRUCTION_CAVEAT +
                ((" · 8×16" if sp["largeSprites"] else " · 8×8")) +
                (f" · pattern ${sp['patternAddr']:04X}") +
                (" · left 8 columns clipped on screen" if sp["leftColumnClip"] else ""))
        else:
            self.sprite_caption.set("no sprite layer published (this is not a NES run, or sprites were off)")

        self.status.set(state_text)
        self._status_text = state_text
        self._draw(state)

    def _draw(self, state):
        scale = state["scale"] or 1
        w, h = state["width"], state["height"]
        self.composite_canvas.config(width=w, height=h)

        # The composite is the recorder's own file - Tk decodes the PPM in C.
        try:
            composite = tk.PhotoImage(file=str(state["ppm"]))
        except tk.TclError as e:
            self.status.set(f"cannot decode frame.ppm: {e}")
            return
        self._imgs.append(composite)
        self.composite_canvas.delete("all")
        self.composite_canvas.create_image(0, 0, image=composite, anchor="nw")
        self.composite_caption.set(
            f"composite — as the emulator rendered it ({w}×{h}, {scale}× native)")

        # The sprite pane is rebuilt from data; a temporary native PPM then gets
        # zoomed to the composite geometry (nearest, integer - Tk does it in C).
        sprites, chr_bytes, colors = state.get("sprites"), state.get("chr"), state.get("colors")
        if sprites is None or chr_bytes is None or colors is None:
            self.sprite_canvas.config(width=256, height=240)
            self.sprite_canvas.delete("all")
            return
        plane, touched = build_native_plane(sprites, chr_bytes)
        ppm = make_native_ppm(plane, sprites["palette"], colors)
        with tempfile.NamedTemporaryFile(suffix=".ppm", delete=False) as f:
            f.write(ppm)
            path = f.name
        try:
            pane = tk.PhotoImage(file=path)
            if scale > 1:
                pane = pane.zoom(scale, scale)
        finally:
            Path(path).unlink(missing_ok=True)
        self._imgs.append(pane)
        self.sprite_canvas.config(width=w, height=h)
        self.sprite_canvas.delete("all")
        self.sprite_canvas.create_image(0, 0, image=pane, anchor="nw")

        if self.mark_var.get():
            fx, fy = w / NATIVE_W, h / NATIVE_H
            self._last_mark = (sprites, touched, fx, fy)
            self._draw_marks(sprites, touched, fx, fy)
        else:
            self._last_mark = None
            self.composite_canvas.delete("spritemark")

    def _draw_marks(self, sprites, touched, fx, fy):
        self.composite_canvas.delete("spritemark")
        for x, y, bw, bh in sprite_boxes(sprites, touched):
            self.composite_canvas.create_rectangle(
                x * fx, y * fy, (x + bw) * fx, (y + bh) * fy,
                outline="#40c0ff", width=1, tags="spritemark")

    def _redraw_marks(self):
        # Repaint just the overlay after a checkbox flip, from the last draw.
        if self._last_mark is not None and self.mark_var.get():
            sprites, touched, fx, fy = self._last_mark
            self._draw_marks(sprites, touched, fx, fy)
        else:
            self.composite_canvas.delete("spritemark")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="MesenCE live recording viewer (ADR-0169) — watch a "
                    "headless recording's composed frame and reconstructed "
                    "sprite layer as it runs (read-only)")
    ap.add_argument("live_dir", help="the <prefix>-live/ folder a recording with "
                                     "live=<ms> publishes into")
    args = ap.parse_args(argv)
    root = tk.Tk()
    RecordViewerApp(root, Path(args.live_dir))
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
