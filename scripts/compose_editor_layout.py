"""Host-free grid arithmetic and wording for the composition editor (F9.18).

The editor's window is tkinter (`scripts/compose_editor.py`); everything in
here is plain data in, plain numbers and strings out — where a cell of the
composed band row is drawn, which cell a click at (x, y) lands on, how much a
node's art is magnified, and what the row and the export preview say. So the
parts of the view that decide what the artist sees can be unit tested with no
display, the way `record_viewer_layout.py` is tested apart from
`record_viewer.py` (ADR-0169) and `compose_viewmodel.py` apart from the window
(ADR-0165 §Decision 2).

Drawing and hit-testing are two directions of the same grid, which is exactly
where they drifted apart once: the row painted its cells column-major while
clicks were resolved row-major, so every cell after the first was drawn off
the canvas — invisible — and a click on it hit a different cell. They are one
pair of inverse functions here (`cell_origin`/`index_at`), and
`test_compose_editor_gui.py` asserts the round trip.

**Variable cell geometry (ADR-0171).** The sprite layer's unit is no longer a
single 8x8 node but a *pose* — a silhouette of roughly 2x2 to 6x9 cells, i.e.
16x16 to 48x72 px — so one hard-coded cell box can no longer serve every row.
The grid is therefore parameterised by a `metrics` dict, computed once per row
by `row_metrics` from the art the row is about to draw, and threaded through
every geometry function. Two rules keep that affordable:

- `metrics=None` reproduces the fixed `ROW_N`/`CELL_W`/`CELL_H` grid *exactly*,
  numerically, so the background and object layers — whose unit is still a
  self-contained metatile — and every existing caller are untouched.
- the grid stays a closed form. `cell_origin` and `index_at` remain exact
  inverses under any metrics (that is the property whose loss once made every
  cell after the seed unclickable), and `cell_center` is published here rather
  than re-derived by each caller so a synthetic click and a real one agree.

A row's cells are all the same size even when its poses are not: the shared
scale and the largest art fix one box for the whole row. That is deliberate —
sizing each cell to its own pose would make the *grid* tell the artist about
silhouette size, when what must tell them is the art itself, drawn at one
scale so a big pose really looks bigger than a small one.

The editor owns the widgets; this module owns the arithmetic and the wording.
"""

# The composed band row: a fixed-width grid of art boxes with a caption under
# each, wrapping to a new line every ROW_N cells. These stay the default cell
# and the row canvas's width budget; `row_metrics` derives everything else
# from them so a pose-sized row still lines up with the panels around it.
ROW_N = 8
CELL_W = 66
CELL_H = 84

# Inset of the art box inside its cell, and of the art inside that box.
CELL_INSET = 8
ART_INSET = 8

# Gap above the art box, and the caption strip under it. Both are read out of
# the fixed cell rather than invented, so `row_metrics(None)` lands back on
# CELL_W/CELL_H to the pixel: 2 + (50 + ART_INSET) + 24 == CELL_H.
CELL_TOP_PAD = 2
CAPTION_H = CELL_H - CELL_TOP_PAD - (CELL_W - CELL_INSET)

# The art budget of a default cell — the box `row_cell_scale` has always fitted
# a node into, and the budget a row of poses is fitted into as well.
ROW_ART_BUDGET = CELL_W - CELL_INSET - ART_INSET

# Height the row canvas takes while it has no cells to show — one line of text.
EMPTY_ROW_H = 30

# Selection preview: a square canvas, so the art is scaled to its shorter side.
PREVIEW_BOX = 132
PREVIEW_ART = 124
PREVIEW_MAX_SCALE = 16

# Export preview: the composed sheet is wider than it is tall, so its scale
# follows the width, capped so a one-cell sheet is not blown up to a poster.
EXPORT_ART_W = 480
EXPORT_MAX_SCALE = 8


def fit_scale_box(avail_w, avail_h, w, h, cap=None):
    """Largest integer magnification of a `w` x `h` art that still fits in an
    `avail_w` x `avail_h` box — both axes, so a tall pose is not scaled off the
    bottom by a width that happens to allow more. Integer so the
    nearest-neighbour zoom keeps pixels square, and never below 1: a box too
    small for one native pixel clips rather than resampling (the same rule
    `record_viewer_layout.fit_zoom` applies to a captured frame)."""
    if w <= 0 or h <= 0 or avail_w <= 0 or avail_h <= 0:
        return 1
    scale = min(avail_w // w, avail_h // h)
    if cap is not None:
        scale = min(scale, cap)
    return max(1, scale)


def fit_scale(available, unit, cap=None):
    """Largest integer magnification of a square `unit`-px node that fits in
    `available` px. The one-axis spelling of `fit_scale_box`, kept because an
    8x8 node and a 16x16 metatile are square and most callers pass one."""
    return fit_scale_box(available, available, unit, unit, cap)


def row_metrics(sizes=None):
    """The cell geometry a row of art needs, as
    `{"cell_w", "cell_h", "per_line", "scale"}`.

    `sizes` is `[(w, h)]` of each cell's art in 1x pixels — a pose's bounding
    box, a node's 8x8, a metatile's 16x16. `None` or `[]` asks for the fixed
    default grid, which is returned verbatim (`ROW_N`, `CELL_W`, `CELL_H`), so
    a caller that has no variable art keeps today's numbers exactly.

    The scale is **one shared magnification for the whole row**, computed from
    the largest art so the relative sizes read true: two poses drawn at
    different scales would tell the artist nothing about which silhouette is
    bigger, which is the judgement ADR-0171 §1 puts in front of them. It is the
    largest art fitted into the same art-box budget `row_cell_scale` has always
    used, integer, never below 1 — a pose taller than the budget draws at 1x in
    a taller cell rather than being resampled away.

    `cell_w`/`cell_h` then follow that largest art plus the existing insets and
    caption strip, and `per_line` divides today's row canvas width by the new
    cell, so the row keeps its width and simply fits fewer, bigger cells."""
    if not sizes:
        return {"cell_w": CELL_W, "cell_h": CELL_H, "per_line": ROW_N,
                "scale": row_cell_scale(8)}
    art_w = max(max(1, int(w)) for w, _h in sizes)
    art_h = max(max(1, int(h)) for _w, h in sizes)
    scale = fit_scale_box(ROW_ART_BUDGET, ROW_ART_BUDGET, art_w, art_h)
    cell_w = art_w * scale + ART_INSET + CELL_INSET
    cell_h = CELL_TOP_PAD + art_h * scale + ART_INSET + CAPTION_H
    return {"cell_w": cell_w, "cell_h": cell_h,
            "per_line": max(1, (ROW_N * CELL_W) // cell_w), "scale": scale}


_DEFAULT_METRICS = {"cell_w": CELL_W, "cell_h": CELL_H, "per_line": ROW_N,
                    "scale": 0}


def _grid(metrics):
    """(cell_w, cell_h, per_line) of `metrics`, or of the fixed default grid.
    One accessor, so no geometry function can read a different grid than its
    inverse does."""
    m = metrics or _DEFAULT_METRICS
    return (m["cell_w"], m["cell_h"], m["per_line"])


def cell_origin(index, metrics=None):
    """Top-left of cell `index` in the row grid — row-major, `per_line` per
    line (ROW_N under the default metrics)."""
    cell_w, cell_h, per_line = _grid(metrics)
    row, col = divmod(index, per_line)
    return (col * cell_w, row * cell_h)


def index_at(x, y, metrics=None):
    """Which cell a click at (x, y) lands on — the inverse of `cell_origin`,
    and it must be given the same `metrics` the row was drawn with.
    May be past the end of the row; the caller bounds-checks against its own
    cell count (a click in the empty part of the canvas is not a cell)."""
    cell_w, cell_h, per_line = _grid(metrics)
    return (int(y) // cell_h) * per_line + (int(x) // cell_w)


def cell_center(index, metrics=None):
    """The middle of cell `index` — where a synthetic click aims. Published
    here rather than recomputed by each caller so a test's click and the
    editor's hit-testing can never disagree about the grid."""
    cell_w, cell_h, _per_line = _grid(metrics)
    x0, y0 = cell_origin(index, metrics)
    return (x0 + cell_w // 2, y0 + cell_h // 2)


def grid_size(count, metrics=None):
    """(width, height) the row canvas needs for `count` cells. The width is
    the row's fixed budget — bigger cells mean fewer per line, not a wider
    canvas — unless a single cell is wider than the whole budget."""
    cell_w, cell_h, per_line = _grid(metrics)
    rows = max(1, (count + per_line - 1) // per_line)
    return (max(ROW_N * CELL_W, cell_w), rows * cell_h)


def art_box(index, metrics=None):
    """The (x0, y0, x1, y1) art box of cell `index`, in row-canvas
    coordinates: the cell less its inset horizontally, and less the caption
    strip vertically (square under the default metrics, as tall as the row's
    tallest art under a pose-sized one)."""
    cell_w, cell_h, _per_line = _grid(metrics)
    x0, y0 = cell_origin(index, metrics)
    box_w = cell_w - CELL_INSET
    box_h = cell_h - CELL_TOP_PAD - CAPTION_H
    bx = x0 + (cell_w - box_w) // 2
    return (bx, y0 + CELL_TOP_PAD, bx + box_w, y0 + CELL_TOP_PAD + box_h)


def caption_point(index, metrics=None):
    """Where cell `index`'s "#node" caption is centred — in the caption strip
    under the art box, not over it."""
    cell_w, cell_h, _per_line = _grid(metrics)
    x0, y0 = cell_origin(index, metrics)
    return (x0 + cell_w // 2, y0 + cell_h - 12)


def row_cell_scale(unit, unit_h=None):
    """Magnification of one cell's art inside a row cell's art box. `unit` on
    its own is a square node or metatile; pass `unit_h` for a pose, whose
    bounding box is rarely square. A whole row of poses shares one scale —
    ask `row_metrics` for it rather than calling this per cell."""
    return fit_scale_box(ROW_ART_BUDGET, ROW_ART_BUDGET, unit,
                         unit if unit_h is None else unit_h)


def preview_scale(unit, unit_h=None):
    """Magnification of the selected art in the selection preview — a node, or
    a pose given its `unit_h`, fitted into the square preview box."""
    return fit_scale_box(PREVIEW_ART, PREVIEW_ART, unit,
                         unit if unit_h is None else unit_h, PREVIEW_MAX_SCALE)


def export_scale(sheet_width):
    """Magnification of the composed sheet in the export preview."""
    return fit_scale(EXPORT_ART_W, max(1, sheet_width), EXPORT_MAX_SCALE)


# Row placeholders. Worded as an instruction, so an empty row says what to do
# next instead of just looking broken.
ROW_WRONG_LAYER = ("the row composes the sprite floor band — seed one on this "
                   "tab")
ROW_NEEDS_SEED = ("seed a band member (left) — it becomes the first locked "
                  "cell")


def export_caption(name, cells, columns, unit, width, height, scale):
    """The export preview's one-line caption: the file `Export` writes, its
    cell count and grid, its real pixel size, and the magnification it is
    being shown at (so "big on screen" is never mistaken for "big on disk")."""
    return (f"{name}.png — {cells} cell(s), {columns} column(s) of {unit}px, "
            f"{width}×{height} px (shown at {scale}×)")
