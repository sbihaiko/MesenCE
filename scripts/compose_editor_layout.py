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

The editor owns the widgets; this module owns the arithmetic and the wording.
"""

# The composed band row: a fixed-width grid of art boxes with a caption under
# each, wrapping to a new line every ROW_N cells.
ROW_N = 8
CELL_W = 66
CELL_H = 84

# Inset of the art box inside its cell, and of the art inside that box.
CELL_INSET = 8
ART_INSET = 8

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


def cell_origin(index):
    """Top-left of cell `index` in the row grid — row-major, ROW_N per line."""
    row, col = divmod(index, ROW_N)
    return (col * CELL_W, row * CELL_H)


def index_at(x, y):
    """Which cell a click at (x, y) lands on — the inverse of `cell_origin`.
    May be past the end of the row; the caller bounds-checks against its own
    cell count (a click in the empty part of the canvas is not a cell)."""
    return (int(y) // CELL_H) * ROW_N + (int(x) // CELL_W)


def grid_size(count):
    """(width, height) the row canvas needs for `count` cells."""
    rows = max(1, (count + ROW_N - 1) // ROW_N)
    return (ROW_N * CELL_W, rows * CELL_H)


def art_box(index):
    """The (x0, y0, x1, y1) art box of cell `index`, and the caption baseline
    under it, all in row-canvas coordinates."""
    x0, y0 = cell_origin(index)
    box = CELL_W - CELL_INSET
    bx = x0 + (CELL_W - box) // 2
    return (bx, y0 + 2, bx + box, y0 + 2 + box)


def caption_point(index):
    """Where cell `index`'s "#node" caption is centred."""
    x0, y0 = cell_origin(index)
    return (x0 + CELL_W // 2, y0 + CELL_H - 12)


def fit_scale(available, unit, cap=None):
    """Largest integer magnification of a `unit`-px-wide node that still fits
    in `available` px. Integer so the nearest-neighbour zoom keeps pixels
    square, and never below 1 — a box too small for one native pixel clips
    rather than resampling (the same rule `record_viewer_layout.fit_zoom`
    applies to a captured frame)."""
    if unit <= 0 or available <= 0:
        return 1
    scale = available // unit
    if cap is not None:
        scale = min(scale, cap)
    return max(1, scale)


def row_cell_scale(unit):
    """Magnification of a node's art inside a row cell's art box."""
    return fit_scale(CELL_W - CELL_INSET - ART_INSET, unit)


def preview_scale(unit):
    """Magnification of a node's art in the selection preview."""
    return fit_scale(PREVIEW_ART, unit, PREVIEW_MAX_SCALE)


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
