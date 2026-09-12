"""Regression suite for the composition editor's view layer (ADR-0165, F9.18).

Two halves, in the shape `test_record_viewer_layout.py` (ADR-0169) uses for
the live viewer:

- **The grid, host-free.** `compose_editor_layout.py` holds the composed band
  row's arithmetic, so where a cell is drawn and which cell a click hits are
  one pair of inverse functions that can be asserted with no display. This is
  the half that must keep passing on any machine, and it is the half that
  caught nothing before the module existed: the row painted column-major
  (`col, row = divmod(i, ROW_N)`) while clicks resolved row-major, so every
  cell after the first was drawn below the canvas - invisible - and a click on
  a visible cell hit a different one. Every invariant here is asserted twice:
  once under the fixed default cell, and once under a pose-sized
  `row_metrics` (ADR-0171), because variable cell geometry is precisely what
  could reopen that drift.
- **The wiring, against the real window.** When Tk can open a display, the
  real `EditorApp` is opened on the synthetic pack `test_compose_engine.py`
  builds and driven through the artist's gestures via the widgets themselves
  (select a row, press the button, click the row canvas), then the widget
  state is asserted - including that everything drawn really lands inside the
  canvas, and that the two preview panels are not squeezed off the window on
  a small one. With no display this half prints `skip` and the suite still
  passes, so a headless CI run is not a false red.

Run:  python3 scripts/test_compose_editor_gui.py
"""

import sys
import tempfile
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compose_editor_layout as L  # noqa: E402
from test_compose_engine import make_pack  # noqa: E402

_FAILURES = []
_SKIPS = []
_CHECKS = []


def check(cond, name, detail=""):
    _CHECKS.append(name)
    if cond:
        print(f"ok   {name}")
    else:
        print(f"FAIL {name}: {detail}")
        _FAILURES.append(name)


# A pose-sized row (ADR-0171 §1): a tall 4x7-cell silhouette next to a small
# 2x2 one, so the metrics under test are the ones a real sprite row produces —
# the shared scale comes off the big pose and the small one is drawn in the
# same box, which is what makes "bigger pose looks bigger" readable.
POSE_SIZES = [(32, 56), (16, 16), (24, 40)]


def cell_center(index):
    return L.cell_center(index)


# ---- the grid, host-free ---------------------------------------------------


def test_drawing_and_hit_testing_are_inverse():
    misses = [i for i in range(3 * L.ROW_N) if L.index_at(*cell_center(i)) != i]
    check(not misses, "a click in a cell's centre resolves to that cell",
          f"cells that resolved elsewhere: {misses}")
    corners = [i for i in range(2 * L.ROW_N)
               if L.index_at(*L.cell_origin(i)) != i]
    check(not corners, "a click on a cell's own top-left corner is that cell",
          f"cells that resolved elsewhere: {corners}")


def test_a_pose_sized_grid_is_still_a_pair_of_inverses():
    """The same round trip under variable cell geometry. This is the property
    a pose-sized row is most likely to lose (the column-major/row-major drift
    only showed itself past the first cell), so it is asserted against the
    metrics the sprite layer will really compute, not against the default."""
    m = L.row_metrics(POSE_SIZES)
    n = 3 * m["per_line"]
    misses = [i for i in range(n) if L.index_at(*L.cell_center(i, m), m) != i]
    check(not misses, "a click in a pose cell's centre resolves to that cell",
          f"metrics={m} cells that resolved elsewhere: {misses}")
    corners = [i for i in range(n) if L.index_at(*L.cell_origin(i, m), m) != i]
    check(not corners,
          "a click on a pose cell's own top-left corner is that cell",
          f"metrics={m} cells that resolved elsewhere: {corners}")


def test_the_row_runs_across_before_it_wraps():
    first = [L.cell_origin(i) for i in range(L.ROW_N)]
    check(all(y == 0 for _x, y in first), "the first ROW_N cells share one line",
          str(first))
    check([x for x, _y in first] == sorted(x for x, _y in first) and
          first[1][0] == L.CELL_W,
          "cells advance across the canvas, one CELL_W at a time", str(first))
    check(L.cell_origin(L.ROW_N) == (0, L.CELL_H),
          "cell ROW_N wraps to the start of the second line",
          str(L.cell_origin(L.ROW_N)))


def test_a_pose_row_wraps_at_its_own_line_length():
    m = L.row_metrics(POSE_SIZES)
    per = m["per_line"]
    first = [L.cell_origin(i, m) for i in range(per)]
    check(all(y == 0 for _x, y in first),
          "the first per_line pose cells share one line", str(first))
    check(per >= 1 and first[-1][0] + m["cell_w"] <= L.ROW_N * L.CELL_W,
          "a full line of pose cells still fits the row's width budget",
          f"metrics={m} last cell ends at {first[-1][0] + m['cell_w']}")
    check(L.cell_origin(per, m) == (0, m["cell_h"]),
          "the cell after a full line wraps to the start of the second line",
          str(L.cell_origin(per, m)))


def test_every_cell_is_drawn_inside_the_canvas_the_row_asks_for():
    for count in (1, 2, L.ROW_N, L.ROW_N + 1, 3 * L.ROW_N):
        width, height = L.grid_size(count)
        outside = [i for i in range(count)
                   if not (L.art_box(i)[2] <= width and L.art_box(i)[3] <= height
                           and L.caption_point(i)[1] <= height)]
        check(not outside,
              f"{count} cell(s) all fall inside the {width}x{height} canvas",
              f"cells drawn outside: {outside}")


def test_art_boxes_never_overlap():
    boxes = [L.art_box(i) for i in range(2 * L.ROW_N)]
    clashes = []
    for i, (ax0, ay0, ax1, ay1) in enumerate(boxes):
        for j, (bx0, by0, bx1, by1) in enumerate(boxes[i + 1:], start=i + 1):
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                clashes.append((i, j))
    check(not clashes, "no two cells' art boxes overlap", str(clashes))


def test_a_pose_row_also_draws_inside_its_canvas_and_never_overlaps():
    m = L.row_metrics(POSE_SIZES)
    per = m["per_line"]
    for count in (1, 2, per, per + 1, 3 * per):
        width, height = L.grid_size(count, m)
        outside = [i for i in range(count)
                   if not (L.art_box(i, m)[2] <= width
                           and L.art_box(i, m)[3] <= height
                           and L.caption_point(i, m)[1] <= height)]
        check(not outside,
              f"{count} pose cell(s) all fall inside the {width}x{height} canvas",
              f"metrics={m} cells drawn outside: {outside}")
    boxes = [L.art_box(i, m) for i in range(2 * per)]
    clashes = []
    for i, (ax0, ay0, ax1, ay1) in enumerate(boxes):
        for j, (bx0, by0, bx1, by1) in enumerate(boxes[i + 1:], start=i + 1):
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                clashes.append((i, j))
    check(not clashes, "no two pose cells' art boxes overlap", str(clashes))


def test_the_row_cell_is_cut_to_the_art_the_row_holds():
    """`row_metrics` is what makes a pose legible, so the three properties the
    artist actually reads are asserted: the default is bit-for-bit today's
    grid, a taller pose buys a taller cell, and the whole row shares one
    scale (relative silhouette size is information, not a drawing accident)."""
    default = L.row_metrics(None)
    check(default["cell_w"] == L.CELL_W and default["cell_h"] == L.CELL_H
          and default["per_line"] == L.ROW_N and L.row_metrics([]) == default,
          "no sizes means exactly the fixed ROW_N/CELL_W/CELL_H grid",
          str(default))
    nodes = L.row_metrics([(8, 8)] * 4)
    # An explicit row of nodes is *not* required to be the default dict to the
    # pixel — the default cell rounds its art budget up (an 8px node at 6x is
    # 48 of the 50 available), so a measured row is a little tighter. What must
    # hold is that it reads the same: same magnification, same line length, and
    # never a cell bigger than the fixed one.
    check(nodes["scale"] == L.row_cell_scale(8)
          and nodes["per_line"] == L.ROW_N
          and nodes["cell_w"] <= L.CELL_W and nodes["cell_h"] <= L.CELL_H,
          "a measured row of plain 8x8 nodes reads as the default cell does",
          str(nodes))
    short, tall = L.row_metrics([(16, 16)]), L.row_metrics([(16, 72)])
    check(tall["cell_h"] > short["cell_h"] and tall["scale"] <= short["scale"],
          "a taller pose makes a taller cell, never a taller-scaled one",
          f"{short} vs {tall}")
    mixed = L.row_metrics(POSE_SIZES)
    biggest = L.row_metrics([max(POSE_SIZES, key=lambda s: s[0] * s[1])])
    check(mixed["scale"] == biggest["scale"] >= 1,
          "the whole row shares the scale the largest pose can take",
          f"{mixed} vs {biggest}")
    check(all(mixed["scale"] * v <= L.ROW_ART_BUDGET
              for v in (max(w for w, _h in POSE_SIZES),
                        max(h for _w, h in POSE_SIZES)))
          or mixed["scale"] == 1,
          "the shared scale fits the art budget on both axes, or bottoms at 1",
          str(mixed))
    check(L.row_metrics([(400, 400)])["scale"] == 1,
          "art far larger than the budget draws at 1x rather than vanishing",
          str(L.row_metrics([(400, 400)])))


def test_scales_are_integers_that_fit_and_never_vanish():
    check(L.row_cell_scale(8) == (L.CELL_W - L.CELL_INSET - L.ART_INSET) // 8,
          "a row cell magnifies an 8px sprite as far as its box allows",
          str(L.row_cell_scale(8)))
    check(L.row_cell_scale(16) * 16 <= L.CELL_W - L.CELL_INSET - L.ART_INSET,
          "a 16px metatile still fits its row cell", str(L.row_cell_scale(16)))
    check(L.preview_scale(8) * 8 <= L.PREVIEW_ART
          and L.preview_scale(8) <= L.PREVIEW_MAX_SCALE
          and L.preview_scale(1) == L.PREVIEW_MAX_SCALE,
          "the preview fills its box without overflowing it, and stays capped",
          f"8px -> {L.preview_scale(8)}, 1px -> {L.preview_scale(1)}")
    check(L.export_scale(1) == L.EXPORT_MAX_SCALE and L.export_scale(4000) == 1,
          "the export preview is capped, and a huge sheet still draws at 1x",
          f"{L.export_scale(1)} / {L.export_scale(4000)}")
    check(L.fit_scale(0, 8) == 1 and L.fit_scale(100, 0) == 1,
          "an unlaid-out box or a zero-width node scales to 1, never to 0")
    # A pose is rarely square, and the axis that binds must be the tight one:
    # scaling 16x48 art by the width alone would run it off the box's bottom.
    check(L.fit_scale_box(100, 100, 16, 48) == 2
          and L.fit_scale_box(100, 100, 48, 16) == 2,
          "a non-square art is fitted by whichever axis binds first",
          f"{L.fit_scale_box(100, 100, 16, 48)} / "
          f"{L.fit_scale_box(100, 100, 48, 16)}")
    check(L.fit_scale_box(100, 100, 8, 8, 3) == 3
          and L.fit_scale_box(2, 100, 8, 8) == 1
          and L.fit_scale_box(100, 0, 8, 8) == 1,
          "fit_scale_box honours the cap and never returns 0",
          str([L.fit_scale_box(100, 100, 8, 8, 3), L.fit_scale_box(2, 100, 8, 8),
               L.fit_scale_box(100, 0, 8, 8)]))
    check(L.row_cell_scale(8) == L.row_cell_scale(8, 8)
          and L.preview_scale(8) == L.preview_scale(8, 8)
          and L.row_cell_scale(8, 48) < L.row_cell_scale(8)
          and L.preview_scale(8, 48) < L.preview_scale(8),
          "the old square signatures still hold, and a tall art scales smaller",
          f"row {L.row_cell_scale(8)}/{L.row_cell_scale(8, 48)}, "
          f"preview {L.preview_scale(8)}/{L.preview_scale(8, 48)}")


def test_the_captions_say_what_lands_on_disk():
    caption = L.export_caption("usr003", 4, 4, 16, 69, 18, 6)
    for part in ("usr003.png", "4 cell(s)", "4 column(s) of 16px", "69×18 px",
                 "shown at 6×"):
        check(part in caption, f"the export caption states {part!r}", caption)
    # A pack whose sheets are 4x gets a 4x sheet (issue #169), so the caption
    # has to name the size the file really takes - quoting the 1x geometry
    # would send the artist looking for a PNG that is not there.
    scaled = L.export_caption("usr003", 4, 4, 16, 69, 18, 6, 4)
    for part in ("276×72 px", "at 4×"):
        check(part in scaled, f"the caption of a 4x pack states {part!r}", scaled)
    check("69×18 px" not in scaled, "the 1x geometry is not quoted as the file size", scaled)


def test_secondary_text_is_readable_on_either_theme():
    """The status line, the selection caption and the frame titles were fixed
    #555/#444: readable on the light aqua theme they were checked against,
    invisible on a dark one. Issue #171."""
    light = L.muted_foreground(0xEE, 0xEE, 0xEE, 255)
    dark = L.muted_foreground(0x2B, 0x2B, 0x33, 255)
    check(light == L.MUTED_ON_LIGHT, "a light surface keeps the dark grey", light)
    check(dark == L.MUTED_ON_DARK, "a dark surface gets a light grey", dark)
    check(L.muted_foreground(0xEE * 257, 0xEE * 257, 0xEE * 257) == light,
          "16-bit channels (winfo_rgb) read the same as 8-bit")
    # Contrast against the surface it sits on, both ways round.
    for bg, fg in ((0xEE, light), (0x2B, dark)):
        surface = L.relative_luminance(bg, bg, bg, 255)
        ink = L.relative_luminance(int(fg[1:3], 16), int(fg[3:5], 16), int(fg[5:7], 16), 255)
        ratio = (max(surface, ink) + 0.05) / (min(surface, ink) + 0.05)
        check(ratio >= 3.0, f"secondary text on 0x{bg:02x} clears 3:1", f"{ratio:.2f}:1")
    check("seed" in L.ROW_NEEDS_SEED and "tab" in L.ROW_WRONG_LAYER,
          "both row placeholders tell the artist what to do next")


# ---- the wiring, against the real window ----------------------------------


class _Dialogs:
    """Stands in for `tkinter.messagebox` so a wiring run never blocks on a
    modal dialog, and so the suite can assert which one the editor raised."""

    def __init__(self):
        self.calls = []

    def _record(self, kind):
        def call(title, message, **_kw):
            self.calls.append((kind, title, message))
        return call

    def __getattr__(self, name):
        return self._record(name)


def _click(app, handler, index):
    class Event:
        x, y = cell_center(index)
    handler(Event())


def _select(listbox, index):
    listbox.selection_clear(0, "end")
    listbox.selection_set(index)
    listbox.event_generate("<<ListboxSelect>>")


def _open_editor(root, folder):
    import compose_editor as ce
    dialogs = _Dialogs()
    ce.messagebox = dialogs
    app = ce.EditorApp(root, folder)
    root.update()
    return app, dialogs


def test_real_window_composes_a_band_through_its_own_widgets(root):
    with tempfile.TemporaryDirectory() as td:
        pack = make_pack(Path(td) / "pack")
        app, dialogs = _open_editor(root, pack)
        check(app.bg_seed.size() == len(app.vm.bg_members),
              "the background list holds one row per background cell",
              f"{app.bg_seed.size()} rows vs {len(app.vm.bg_members)} cells")

        app.sprite_tab.master.select(app.sprite_tab)
        _select(app.sp_seed, 0)
        app._seed_sprite()
        root.update()
        check(app.vm.mode == "sprite" and app.vm.seed is not None,
              "'Seed selected' on the sprite tab seeds the ViewModel from the list",
              f"mode={app.vm.mode} seed={app.vm.seed}")
        check(app.preview_lbl.get().startswith(f"#{app.vm.seed}"),
              "selecting a row previews that node's art", app.preview_lbl.get())

        # The '+' ghost is the last cell of the row; clicking it locks the
        # engine's next pick, the gesture the row's own caption promises.
        ghost = len(app.vm.row_spec()) - 1
        promised = app.vm.row_spec()[ghost]["add"]
        _click(app, app._row_left, ghost)
        root.update()
        check(promised in app.vm.locked_list(),
              "clicking '+' locks the candidate that cell was showing",
              f"{promised} not in {app.vm.locked_list()}")

        locked_before = list(app.vm.locked_list())
        _click(app, app._row_left, 1)
        root.update()
        check(app.vm.locked_list() != locked_before and
              len(app.vm.locked_list()) == len(locked_before),
              "clicking a locked cell swaps it instead of adding one",
              f"{locked_before} -> {app.vm.locked_list()}")

        _click(app, app._row_right, 1)
        root.update()
        check(len(app.vm.locked_list()) == len(locked_before) - 1,
              "right-clicking a locked cell removes it",
              str(app.vm.locked_list()))

        app.out_var.set(str(pack / "textures" / "sheets"))
        app._refresh_kept()
        app.export()
        root.update()
        written = sorted(p.name for p in (pack / "textures" / "sheets").glob("usr*"))
        check(written, "Export writes the composed sheet the preview showed",
              str(written))
        check(any(kind == "showinfo" for kind, _t, _m in dialogs.calls),
              "Export confirms with the paint-it-then-rebuild dialog",
              str(dialogs.calls))
        check(app.export_lbl.get().endswith("×)") and "cell(s)" in app.export_lbl.get(),
              "the export caption reads as the layout module writes it",
              app.export_lbl.get())


def test_real_row_canvas_draws_every_cell_where_a_click_can_reach_it(root):
    with tempfile.TemporaryDirectory() as td:
        app, _dialogs = _open_editor(root, make_pack(Path(td) / "pack"))
        app.sprite_tab.master.select(app.sprite_tab)
        _select(app.sp_seed, 0)
        app._seed_sprite()
        for _ in range(3):
            ghost = len(app.vm.row_spec()) - 1
            if app.vm.row_spec()[ghost]["node"] is not None:
                break
            _click(app, app._row_left, ghost)
        root.update()
        spec = app.vm.row_spec()
        check(len(spec) >= 3, "the fixture composed a multi-cell row", str(spec))
        canvas = app.row_canvas
        height = int(canvas.cget("height"))
        bbox = canvas.bbox("all")
        check(bbox is not None and bbox[3] <= height + 1,
              "nothing the row draws falls below the canvas it asked for",
              f"bbox={bbox} height={height}")
        # Every cell of the row is really painted, at the place its own click
        # lands: one hit per cell, and each hit finds items of that cell.
        empty = [i for i in range(len(spec))
                 if not canvas.find_overlapping(*L.art_box(i))]
        check(not empty, "every cell of the row has something drawn in it",
              f"cells with an empty art box: {empty}")


def test_both_preview_panels_survive_a_small_window(root):
    with tempfile.TemporaryDirectory() as td:
        app, _dialogs = _open_editor(root, make_pack(Path(td) / "pack"))
        root.geometry("900x560")
        root.update()
        app.sprite_tab.master.select(app.sprite_tab)
        _select(app.sp_seed, 0)
        app._seed_sprite()
        root.update()
        check(app.preview.winfo_width() >= L.PREVIEW_BOX,
              "the selection preview keeps its full width on a small window",
              f"{app.preview.winfo_width()} px of {L.PREVIEW_BOX}")
        bottom = (app.canvas.winfo_rooty() + app.canvas.winfo_height()
                  - root.winfo_rooty())
        check(bottom <= root.winfo_height(),
              "the export preview is not clipped off the bottom edge",
              f"reaches {bottom} px of a {root.winfo_height()} px window")


def test_a_pack_opens_on_art_and_each_list_keeps_its_own_selection(root):
    """Issue #171: a pack used to open on a column of ids with an empty
    Selection panel, and - because Tk Listboxes export their selection by
    default - picking a row in any other list cleared the first one and blanked
    the art the artist was looking at."""
    with tempfile.TemporaryDirectory() as td:
        app, _dialogs = _open_editor(root, make_pack(Path(td) / "pack"))
        check(app.bg_seed.curselection() == (0,),
              "opening a pack selects the first background cell",
              str(app.bg_seed.curselection()))
        opened = app.preview_lbl.get()
        check(opened.startswith("#") and "—" not in opened,
              "so the Selection panel shows art, not a dash", opened)

        app.sprite_tab.master.select(app.sprite_tab)
        root.update()          # the list has to be viewable to receive the event
        _select(app.sp_seed, 0)
        root.update()
        check(app.bg_seed.curselection() == (0,),
              "picking a sprite row leaves the background selection alone",
              str(app.bg_seed.curselection()))
        shown = app.preview_lbl.get()
        check(shown.startswith("#") and "sprite" in shown,
              "and the preview follows the list that was just touched", shown)


def main():
    host_free = [
        test_drawing_and_hit_testing_are_inverse,
        test_a_pose_sized_grid_is_still_a_pair_of_inverses,
        test_the_row_runs_across_before_it_wraps,
        test_a_pose_row_wraps_at_its_own_line_length,
        test_every_cell_is_drawn_inside_the_canvas_the_row_asks_for,
        test_art_boxes_never_overlap,
        test_a_pose_row_also_draws_inside_its_canvas_and_never_overlaps,
        test_the_row_cell_is_cut_to_the_art_the_row_holds,
        test_scales_are_integers_that_fit_and_never_vanish,
        test_the_captions_say_what_lands_on_disk,
        test_secondary_text_is_readable_on_either_theme,
    ]
    windowed = [
        test_real_window_composes_a_band_through_its_own_widgets,
        test_real_row_canvas_draws_every_cell_where_a_click_can_reach_it,
        test_both_preview_panels_survive_a_small_window,
        test_a_pack_opens_on_art_and_each_list_keeps_its_own_selection,
    ]
    for t in host_free:
        t()
    for t in windowed:
        try:
            root = tk.Tk()
        except tk.TclError as e:
            _SKIPS.append(t.__name__)
            print(f"skip {t.__name__}: no display ({e})")
            continue
        try:
            root.geometry("1180x760+40+40")
            t(root)
        finally:
            root.destroy()
    total = len(_CHECKS)
    print(f"\n{total - len(_FAILURES)}/{total} checks passed"
          f"{f' ({len(_SKIPS)} case(s) skipped: no display)' if _SKIPS else ''}")
    return 1 if _FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
