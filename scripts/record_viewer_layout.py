"""Host-free layout and label logic for the live recording viewer (ADR-0169).

The viewer's window is tkinter (scripts/record_viewer.py); everything in here
is plain data in, plain numbers and strings out — how big a frame is drawn,
which way the split runs, what the status strip and the pane headers say. So
the parts of the viewer that decide what the user sees can be unit tested
without a display, the way compose_viewmodel.py is tested apart from
compose_editor.py (ADR-0165).

The viewer owns the widgets; this module owns the arithmetic and the wording.
"""

# The NES plane in its own native pixels. A captured frame.ppm may already be
# scaled by the recorder (2x -> 512x480); the view zoom multiplies that.
NATIVE_W = 256
NATIVE_H = 240

# View zoom the user can ask for, on top of the recorder's own scale. 1x is a
# NES-native pixel; the cap keeps a stray keystroke from asking Tk to zoom a
# frame to a gigabyte of PhotoImage.
MIN_ZOOM = 1
MAX_ZOOM = 8

# How the two panes share the window.
LAYOUT_AUTO = "auto"
LAYOUT_SIDE = "side"
LAYOUT_STACK = "stack"
LAYOUT_LABELS = ((LAYOUT_AUTO, "Auto"), (LAYOUT_SIDE, "Side by side"),
                 (LAYOUT_STACK, "Stacked"))

# Auto compares the two splits by how large one native frame could be drawn in
# half the window each way, and takes the bigger; a tie goes to side by side,
# the order the notes and the docstring name the panes in. A side-by-side pane
# narrower than MIN_PANE_W cannot hold its own header and layer toggles on one
# line, so below that Auto stacks regardless of the frame arithmetic.
MIN_PANE_W = 380

ORIENT_HORIZONTAL = "horizontal"
ORIENT_VERTICAL = "vertical"

# Pane titles. Short, so the header row stays one line at any window size; the
# long explanation lives in the notes strip (see reconstruction_note).
COMPOSITE_TITLE = "Composite"
COMPOSITE_SUBTITLE = "as the emulator rendered it"
RECONSTRUCTION_TITLE = "Reconstruction"
RECONSTRUCTION_SUBTITLE = "rebuilt from the captured layers"

# Notes text for the reconstruction pane once the background layer is on the
# wire (2026-09-08 ADR-0169 "capture every layer"). Everything an end-of-frame
# capture can prove is applied - priority, the mask bits, palette - so the pane
# is a real multiplex of both layers; only the per-scanline limits a single
# capture cannot see are left out and named. Worded without "above"/"below" so
# it reads the same whether the panes are stacked or side by side.
RECONSTRUCTION_NOTE = (
    "Reconstruction: rebuilt from OAM + nametables — same priority as the PPU "
    "(front sprites, behind sprites only through a backdrop pixel, mask bits "
    "honoured), but it cannot see a frame's 8-sprites-per-scanline overflow or "
    "a mid-frame scroll split, so a sprite here may still differ from the "
    "composite.")

# Older recordings (and non-background captures) show sprites over the backdrop
# color alone; name that so it reads as "no background data", not as an error.
SPRITES_ONLY_NOTE = (
    "Reconstruction: rebuilt from OAM only (this recording predates the "
    "background capture) — sprites drawn over the backdrop color, no priority "
    "to multiplex.")

# status.json's hdPackActive (LiveRecordFormat.h's LiveSnapshot::HdPackActive):
# with HD pack texture substitution live, the composite is the pack's redrawn
# art while the CHR/nametable/OAM bytes the reconstruction rebuilds from still
# hold the original NES tiles. There is no data channel that carries a
# substituted tile back to a reconstruction, so the two panes are simply
# describing different graphics - say so instead of letting the pane read as a
# fidelity failure.
HD_PACK_NOTE = (
    "HD pack substitution is ON for this run — the composite shows the pack's "
    "redrawn art, the reconstruction shows the original NES tiles it replaced, "
    "so the two are not comparable. Turn off Settings > NES > Enable HD Packs "
    "(or run headless_record with hdpack-off) to compare the reconstruction "
    "itself.")

NO_SPRITE_LAYER_NOTE = (
    "No sprite layer published — this is not a NES run, or sprites were off.")


def pick_orientation(mode, width, height):
    """Which way the two panes sit, for a layout mode and a window size.

    `auto` follows the window: whichever split lets a native frame be drawn
    larger in its half wins, so a wide window splits left/right and a tall or
    square one stacks — unless side by side would leave each pane too narrow
    for its own controls (MIN_PANE_W), in which case it stacks."""
    if mode == LAYOUT_SIDE:
        return ORIENT_HORIZONTAL
    if mode == LAYOUT_STACK:
        return ORIENT_VERTICAL
    if width <= 0 or height <= 0:
        return ORIENT_HORIZONTAL
    if width / 2 < MIN_PANE_W <= width:
        return ORIENT_VERTICAL
    side = min(width / 2 / NATIVE_W, height / NATIVE_H)
    stack = min(width / NATIVE_W, height / 2 / NATIVE_H)
    return ORIENT_HORIZONTAL if side >= stack else ORIENT_VERTICAL


def clamp_zoom(zoom, max_zoom=MAX_ZOOM):
    """A user-typed zoom brought back into range (a Spinbox can hand us junk)."""
    try:
        zoom = int(zoom)
    except (TypeError, ValueError):
        return MIN_ZOOM
    return max(MIN_ZOOM, min(zoom, max_zoom))


def fit_zoom(frame_w, frame_h, avail_w, avail_h, max_zoom=MAX_ZOOM):
    """Largest integer zoom of a frame_w x frame_h image that still fits in
    avail_w x avail_h. Integer so the nearest-neighbour zoom keeps pixels
    square, capped, and never below 1 — a pane too small for one native pixel
    per screen pixel clips rather than resampling."""
    if frame_w <= 0 or frame_h <= 0 or avail_w <= 0 or avail_h <= 0:
        return MIN_ZOOM
    return max(MIN_ZOOM, min(avail_w // frame_w, avail_h // frame_h, max_zoom))


def resolve_zoom(fit, manual, frame_w, frame_h, avail_w, avail_h, max_zoom=MAX_ZOOM):
    """The view zoom to draw at: the fit-the-pane one, or the user's pick."""
    if fit:
        return fit_zoom(frame_w, frame_h, avail_w, avail_h, max_zoom)
    return clamp_zoom(manual, max_zoom)


def shared_available(sizes):
    """The (w, h) both panes can honour, given each pane's own free space, so
    one zoom draws both frames at the same size (they are meant to be compared
    pixel for pixel). Panes not laid out yet report 0 and are ignored."""
    real = [(w, h) for w, h in sizes if w > 0 and h > 0]
    if not real:
        return (0, 0)
    return (min(w for w, _ in real), min(h for _, h in real))


# The window title, so a taskbar/dock entry says which game is on screen.
TITLE = "MesenCE — live recording viewer"


def window_title(rom):
    """The title bar: the tool, plus the ROM the run is publishing (status.json's
    "rom", written by both producers). A run from before that field, or a
    session with no game open, keeps the plain title rather than showing an
    empty dash."""
    rom = (rom or "").strip()
    return f"{TITLE} — {rom}" if rom else TITLE


def rom_name(status):
    """status.json's "rom" (both producers write it): the game the published
    frames belong to. Empty for a recording made before the field existed, or
    for a session with no game open."""
    return ((status or {}).get("rom") or "").strip()


def run_badge(status):
    """Short state chip for the status strip: what the run is doing right now."""
    if not status or status.get("frame") is None:
        return "IDLE"
    if status.get("done"):
        return "STOPPED"
    return "REC"


def format_run_state(status):
    """'Castlevania.nes · frame 26509 live · wall 441.0s' — the run's progress in
    one line, named by the ROM it is recording. A scripted run has a target
    frame count; an interactive one runs until the human stops it, so it reads
    'live'."""
    frame = status.get("frame", "?")
    target = status.get("targetFrames", 0) or 0
    wall = status.get("elapsedWallSec", 0)
    if status.get("done"):
        tail = "stopped"
    elif target:
        tail = f"of {target}"
    else:
        tail = "live"
    line = f"frame {frame} {tail} · wall {wall}s"
    rom = rom_name(status)
    return f"{rom} · {line}" if rom else line


def format_notices(status, sprites):
    """The things that change how the panes should be read, as short chips.
    Empty when the run is unremarkable — a quiet strip means nothing is off."""
    out = []
    if status.get("hdPackActive"):
        out.append("HD pack ON")
    if sprites is not None and not sprites.get("spritesEnabled", True):
        out.append("sprites off this frame (OAM may be stale)")
    return out


def format_composite_meta(width, height, recorder_scale, view_zoom):
    """The composite pane's one-line header meta: what the file holds and how
    much the viewer is magnifying it."""
    parts = [f"{width}×{height}", f"{recorder_scale or 1}× native"]
    if view_zoom and view_zoom > 1:
        parts.append(f"view {view_zoom}×")
    return " · ".join(parts)


def format_reconstruction_meta(sprites, bg):
    """The reconstruction pane's one-line header meta: the PPU configuration
    this frame was rebuilt under, so a wrong-looking pane can be read against
    the bits that produced it."""
    if sprites is None:
        return ""
    parts = ["8×16" if sprites["largeSprites"] else "8×8",
             f"sprite ${sprites['patternAddr']:04X}"]
    if bg is not None:
        parts.append(f"bg ${bg['patternAddr']:04X}")
        if not bg["enabled"]:
            parts.append("bg off this frame")
        if bg["leftColumnClip"]:
            parts.append("bg left clip")
    if sprites["leftColumnClip"]:
        parts.append("sprite left clip")
    return " · ".join(parts)


def reconstruction_note(has_sprites, has_background, hd_pack_active):
    """The paragraph the notes strip shows for the current recording. The
    HD-pack note replaces the usual one rather than joining it: with
    substitution on, the per-scanline limits are not what makes the panes
    differ."""
    if not has_sprites:
        return NO_SPRITE_LAYER_NOTE
    if hd_pack_active:
        return HD_PACK_NOTE
    return RECONSTRUCTION_NOTE if has_background else SPRITES_ONLY_NOTE


def waiting_text(live_dir):
    """What to say while no run has published into the watched directory."""
    return ("Nothing published yet — start Live Recording from the emulator's "
            f"Tools menu, or attach a headless <prefix>-live/ dir. Watching {live_dir}")
