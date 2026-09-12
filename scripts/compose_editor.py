"""The composition editor (ADR-0165 / F9.18) — a tkinter layered canvas over
the host-free `compose_engine`, wired through an MVVM split.

`scripts/compose_editor.py [pack folder]` opens a pack recorded since F9.17
and lets an artist build a scene by the two queries ADR-0164 §5 defines:
seed -> rank -> lock -> recompute over the background adjacency (an object
layer) or inside a sprite Y band (floor-sharing shapes), then export the
kept cells as a composed `usrNNN` sheet. `compose_engine.Pack` is the Model,
`compose_viewmodel.ComposeViewModel` is the ViewModel (seed/lock/swap/export
state, no tkinter), and `EditorApp` below is the View: it renders the
ViewModel's state and forwards tkinter events into its methods, nothing more.

This is the interactive half and is judged by the human Phase 9 panel — the
automated half is `test_compose_engine.py` (the engine's two ADR-0164
acceptance tests) and `test_compose_viewmodel.py` (a full seed/lock/swap/
export composition run headless through the ViewModel, so the state machine
this file draws is verified before a human ever opens the window).
"""

import argparse
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compose_editor_layout as L  # noqa: E402
import compose_engine as E  # noqa: E402
from compose_viewmodel import ComposeViewModel  # noqa: E402


def _backdrop_rgb(rgba, backdrop=(0x22, 0x22, 0x2A)):
    a = rgba[3] / 255.0
    return tuple(int(round(rgba[i] * a + backdrop[i] * (1.0 - a))) for i in range(3))


def image_photo(img, scale, backdrop=(0x22, 0x22, 0x2A)):
    """One nearest-scaled RGB PhotoImage of a composed image, alpha blended over
    a dark backdrop so transparency reads as background, not as black art.

    Used for both the export preview and the band row's cells - tkinter has no
    RGBA source of its own, so every pixel the editor shows goes through here."""
    width, height = img.width * scale, img.height * scale
    data = bytearray(b"P6\n%d %d\n255\n" % (width, height))
    for y in range(height):
        row = bytearray()
        for x in range(width):
            row += bytes(_backdrop_rgb(img.get(x // scale, y // scale), backdrop))
        data += row
    with tempfile.NamedTemporaryFile(suffix=".ppm", delete=False) as f:
        f.write(data)
        path = f.name
    photo = tk.PhotoImage(file=path)
    Path(path).unlink(missing_ok=True)
    return photo, width, height


def _pose_shape(pose):
    """A pose in one glance: the cells its tiles actually span, how many tiles
    carry it, and the frame count it was seen in (ADR-0171 §1). `extent` and
    not `size`, because `size` is what the sidecar claims and the extent is
    what the tiles the editor can draw support."""
    cols, rows = pose.extent()
    return f"{cols}x{rows}  {len(pose.tiles)}t  {pose.frames}f"


class EditorApp:
    def __init__(self, root: tk.Tk, folder: Path):
        self.root = root
        root.title("MesenCE — composition editor (F9.18)")
        self.vm = ComposeViewModel()
        self._imgs = []       # keep PhotoImage references alive
        self._cell_imgs = []
        # The grid the band row was last painted with (ADR-0171: a row of
        # poses has cells as big as its biggest silhouette, so the geometry is
        # computed per repaint instead of being a constant). Drawing and
        # hit-testing must read this same dict or they drift apart, which is
        # exactly the bug that cost the first GUI pass; None means the fixed
        # pre-ADR-0171 grid, which `compose_editor_layout` reproduces verbatim.
        self._row_metrics = None
        # Secondary text, resolved against the theme this window really runs
        # under: the fixed #555/#444 this file used to pass were unreadable in
        # dark mode, and so were the frame titles ttk styles from the theme.
        self.muted = self._muted_foreground()
        ttk.Style(root).configure("TLabelframe.Label", foreground=self.muted)

        top = ttk.Frame(root, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Pack:").pack(side="left")
        self.folder_var = tk.StringVar(value=str(folder))
        ttk.Entry(top, textvariable=self.folder_var, width=48).pack(side="left", padx=4)
        ttk.Button(top, text="Open…", command=self.open_pack).pack(side="left")
        ttk.Label(top, text="Output:").pack(side="left", padx=(12, 2))
        self.out_var = tk.StringVar()
        # Expands: the value is an absolute sheets path, and a fixed-width box
        # clipped it to "…Mega Man 3 (", hiding where Export writes.
        ttk.Entry(top, textvariable=self.out_var, width=24).pack(
            side="left", padx=4, fill="x", expand=True)
        ttk.Button(top, text="Export", command=self.export).pack(side="left")

        self.status = tk.StringVar(value="no pack open")
        ttk.Label(root, textvariable=self.status, foreground=self.muted).pack(fill="x", padx=6)

        # The export preview: the pixels `Export` writes, drawn from the very
        # image the engine composes (ADR-0165 - the artist approves the file,
        # not a second drawing of it), with the name and size it will take.
        # Packed before the body, from the bottom: the packer serves earlier
        # widgets their requested size first, and when it served the tab body
        # first this preview was the strip that got clipped away - the one
        # thing the artist is meant to approve before pressing Export.
        pane = self._labelframe(root, "Export preview — the sheet Export writes", padding=4)
        pane.pack(side="bottom", fill="x", padx=6, pady=(0, 6))
        self.export_lbl = tk.StringVar(value="nothing composed yet — seed a cell")
        ttk.Label(pane, textvariable=self.export_lbl, foreground=self.muted).pack(anchor="w")
        self.canvas = tk.Canvas(pane, height=120, background="#2b2b33", highlightthickness=0)
        self.canvas.pack(fill="x")

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=6, pady=(2, 2))
        # Selection preview — the actual pixels of the highlighted cell, so a
        # composer sees the art instead of decoding "#47". Packed before the
        # notebook for the same reason the export preview is packed before the
        # body: the packer serves earlier widgets first, and the tabs (which
        # expand) squeezed this panel off the right edge on a narrow window.
        side = ttk.Frame(body)
        side.pack(side="right", fill="y", padx=(8, 0))
        ttk.Label(side, text="Selection", foreground=self.muted).pack(anchor="w")
        self.preview = tk.Canvas(side, width=L.PREVIEW_BOX, height=L.PREVIEW_BOX,
                                 background="#1e1e24", highlightthickness=0)
        self.preview.pack()
        self.preview_tk = None   # keep the PhotoImage alive
        self.preview_lbl = tk.StringVar(value="—")
        ttk.Label(side, textvariable=self.preview_lbl, foreground=self.muted,
                  wraplength=L.PREVIEW_ART).pack(anchor="w", pady=(4, 0))

        nb = ttk.Notebook(body)
        nb.pack(side="left", fill="both", expand=True)
        self.sprite_tab = ttk.Frame(nb)
        self.bg_tab = ttk.Frame(nb)
        nb.add(self.bg_tab, text="Background (object layer)")
        nb.add(self.sprite_tab, text="Sprites (Y bands)")
        self._build_bg_tab()
        self._build_sprite_tab()
        self._bind_selection_preview()

        if folder.is_dir():
            self.load_pack(folder)

    def _labelframe(self, parent, text: str, **kw):
        """A `ttk.LabelFrame` whose title is a label this file colours itself.
        The aqua theme ignores `TLabelframe.Label`'s `foreground`, so styling
        alone left every frame title in the theme's own grey — unreadable on a
        dark background, which is how the F9.18 panel rehearsal found them. A
        `labelwidget` is honoured by every theme."""
        frame = ttk.LabelFrame(parent, **kw)
        frame.configure(labelwidget=ttk.Label(frame, text=text, foreground=self.muted))
        return frame

    def _muted_foreground(self) -> str:
        """Secondary text colour for this window, measured off the theme's own
        frame background through `winfo_rgb` — the same call
        `render_compose_editor.py` resolves colours with, so what the render
        shows is what the artist reads. Falls back to the light-theme grey when
        Tk cannot answer."""
        try:
            bg = ttk.Style(self.root).lookup("TFrame", "background") or self.root.cget("background")
            r, g, b = self.root.winfo_rgb(bg)
        except Exception:
            return L.MUTED_ON_LIGHT
        return L.muted_foreground(r, g, b)

    # ---- pack ---------------------------------------------------------------

    def open_pack(self):
        folder = filedialog.askdirectory(title="Choose a pack folder (textures/sheets inside)")
        if folder:
            self.folder_var.set(folder)
            self.load_pack(Path(folder))

    def load_pack(self, folder: Path):
        try:
            self.status.set(self.vm.load(folder))
        except E.ComposeError as e:
            messagebox.showerror("Cannot compose", str(e))
            self.status.set(str(e))
            return
        self.out_var.set(str(self.vm.pack.sheets_dir))
        self._fill_bg_seed_list()
        self._fill_band_selector()
        self.refresh_all()
        # Open on art, not on a column of ids: the seed list reads "#0 count
        # 2626 x1y1", and until something is highlighted the Selection panel is
        # an empty box, so a pack opens looking like a spreadsheet. Selecting
        # the first row draws its pixels straight away.
        if self.bg_seed.size():
            self.bg_seed.selection_clear(0, "end")
            self.bg_seed.selection_set(0)
            self.bg_seed.activate(0)
            self._show_selected(self.bg_seed)

    # ---- background / object layer ------------------------------------------

    def _build_bg_tab(self):
        f = self.bg_tab
        left = self._labelframe(f, "Background cells (most seen first)", padding=4)
        left.pack(side="left", fill="y", padx=4, pady=4)
        # The lists fill the window (`expand`), so the requested height is a
        # floor, not the size: a tall request squeezed the tab's own buttons
        # off the bottom edge on a shorter window.
        self.bg_seed = tk.Listbox(left, width=46, height=12, exportselection=False)
        self.bg_seed.pack(fill="both", expand=True)
        ttk.Button(left, text="Seed selected", command=self._seed_bg).pack(pady=2)
        mid = self._labelframe(f, "Ranked neighbours — lock to compose", padding=4)
        mid.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self.bg_sugg = tk.Listbox(mid, width=46, height=12, exportselection=False)
        self.bg_sugg.pack(fill="both", expand=True)
        ttk.Button(mid, text="Lock suggestion", command=self._lock_bg).pack(pady=2)
        ttk.Button(mid, text="Recompute (seed + locks)", command=self.refresh_all).pack(pady=2)

    def _fill_bg_seed_list(self):
        self.bg_seed.delete(0, "end")
        for node, _sheet, cell in self.vm.bg_members:
            self.bg_seed.insert("end", f"#{node}  count {cell.get('count')}  x{cell.get('x')}y{cell.get('y')}")

    def _seed_bg(self):
        node = self._selected_node(self.bg_seed)
        if node is None:
            return
        self.vm.seed_object(node)
        self.refresh_all()

    def _lock_bg(self):
        node = self._selected_node(self.bg_sugg)
        if node is None:
            return
        self.vm.lock(node, "object")
        self.refresh_all()

    def _refresh_bg_sugg(self):
        self.bg_sugg.delete(0, "end")
        for node, score in self.vm.background_rank():
            self.bg_sugg.insert("end", f"#{node}  score {score:.3f}")

    # ---- sprites / Y band ---------------------------------------------------

    def _build_sprite_tab(self):
        f = self.sprite_tab
        sel = self._labelframe(f, "Floor band (bottom edge, 8 px) — seed palette", padding=4)
        sel.pack(side="left", fill="y", padx=4, pady=4)
        self.band_var = tk.StringVar()
        self.band_box = ttk.Combobox(sel, textvariable=self.band_var, state="readonly", width=12)
        self.band_box.pack()
        self.sp_seed = tk.Listbox(sel, width=24, height=10, exportselection=False)
        self.sp_seed.pack(fill="both", expand=True, pady=4)
        ttk.Button(sel, text="Seed selected", command=self._seed_sprite).pack(pady=2)

        # The composed band row (ADR-0165 GUI): one cell per sprite of the composed band,
        # clickable — click a + cell to lock the engine's next pick, click a
        # locked cell to swap it for the next recommendation (the butterfly: the
        # lock set changed, so the whole row re-ranks), right-click to remove a
        # lock. Removing the last lock clears the composition.
        mid = self._labelframe(
            f, "Composed band — click + to lock · click a locked cell to swap · right-click to remove",
            padding=4)
        mid.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self.row_canvas = tk.Canvas(mid, height=L.EMPTY_ROW_H, background="#1e1e24",
                                    highlightthickness=0)
        self.row_canvas.pack(fill="x")
        self.row_canvas.bind("<Button-1>", self._row_left)
        self.row_canvas.bind("<Button-3>", self._row_right)
        sugg = self._labelframe(mid, "Ranked band members (coFrames) — or lock a pick here", padding=2)
        sugg.pack(fill="both", expand=True, pady=(4, 0))
        self.sp_sugg = tk.Listbox(sugg, width=42, height=8, exportselection=False)
        self.sp_sugg.pack(fill="both", expand=True)
        btns = ttk.Frame(sugg)
        btns.pack(fill="x", pady=(2, 0))
        ttk.Button(btns, text="Lock selected suggestion", command=self._lock_sprite).pack(side="left", padx=(0, 4))
        ttk.Button(btns, text="Recompute", command=self.refresh_all).pack(side="left")
        self.band_box.bind("<<ComboboxSelected>>", lambda _e: self._on_band())

    def _fill_band_selector(self):
        bands = self.vm.bands()
        self.band_box["values"] = [f"{b} px" for b in bands]
        if bands:
            self.band_var.set(f"{self.vm.band} px")
        self._fill_sp_seed_list()

    def _current_band(self):
        try:
            return int(self.band_var.get().split()[0])
        except (ValueError, AttributeError):
            return None

    def _on_band(self):
        band = self._current_band()
        if band is None:
            return
        self.vm.set_band(band)
        self._fill_sp_seed_list()
        self.refresh_all()

    def _fill_sp_seed_list(self):
        """The band's seed palette: poses on a pack recorded since ADR-0170,
        bare nodes on one recorded before it (`band_poses` is empty there, and
        that emptiness is the only gate — the View never asks which rung of
        ADR-0171 §1's ladder answered).

        Every line still starts with `#<anchor>`, because that prefix is the
        contract `_selected_node` parses and ADR-0171 §5 keeps `seed`/`locked`
        naming nodes. What follows is what an artist picks on: how big the
        silhouette is, how many tiles carry it, and how many frames it was
        seen in."""
        self.sp_seed.delete(0, "end")
        for anchor, pose in self.vm.band_poses():
            # ADR-0179 §5: the list is already in cycle-then-phase order; the
            # caption says which loop and phase, still behind the `#<anchor>`
            # prefix `_selected_node` parses.
            label = self.vm.pose_run_label(pose)
            self.sp_seed.insert("end", f"#{anchor}  {_pose_shape(pose)}" + (f"  {label}" if label else ""))
        if self.sp_seed.size():
            return
        for node in self.vm.band_members():
            self.sp_seed.insert("end", f"#{node}")

    def _seed_sprite(self):
        node = self._selected_node(self.sp_seed)
        if node is None:
            return
        self.vm.seed_sprite(node)
        self.refresh_all()

    def _lock_sprite(self):
        node = self._selected_node(self.sp_sugg)
        if node is None:
            return
        self.vm.lock(node, "sprite")
        self.refresh_all()

    def _refresh_sp_sugg(self):
        """The ranked candidates. On a pose pack the score is ADR-0171 §4's
        damped sum (a float, not a raw coFrames count), so it is labelled as a
        score and the line carries the silhouette's shape instead of the
        anchor tile's name — the artist is choosing a figure, not a fragment."""
        self.sp_sugg.delete(0, "end")
        if self.vm.mode != "sprite":
            return
        for node, score in self.vm.sprite_rank():
            pose = self.vm.pose_for(node)
            if pose is not None:
                self.sp_sugg.insert("end", f"#{node}  score {score:.2f}  {_pose_shape(pose)}")
                continue
            name = self.vm.shape_name(node)
            self.sp_sugg.insert("end", f"#{node}  coFrames {score}{'  ' + name if name else ''}")

    # ---- sprite band row (the clickable composition row) --------------------

    def _row_art(self, cell):
        """What one row cell shows: `(art, caption)`.

        ADR-0171 §1 — the unit of the sprite layer is the pose, so a locked
        cell draws the whole silhouette its anchor stands for, not the anchor's
        lone 8x8 fragment. `pose_for` answers None on a pack recorded before
        ADR-0170 and on an anchor in no pose, which is the ladder's third rung:
        the bare node, a degenerate pose of one.

        The caption keeps the `#<anchor>` prefix `_selected_node` parses and
        appends the shape, so "#12  3x4" says both who the cell locks and how
        much of the screen it covers. `art` is None when the pixels cannot be
        resolved; the caller draws the error box rather than a blank."""
        node = cell["node"]
        if node is None:
            cand = cell.get("add")
            return (None, "" if cand is None else f"#{cand}")
        pose = self.vm.pose_for(node)
        try:
            if pose is not None:
                cols, rows = pose.extent()
                return (self.vm.pack.pose_art(pose), f"#{node}  {cols}x{rows}")
            return (self.vm.node_art(node, sprite=True), f"#{node}")
        except E.ComposeError:
            return (None, f"#{node}")

    def row_metrics(self):
        """The grid the band row is currently painted with — the dict
        `compose_editor_layout` builds from this repaint's art sizes, or None
        for the fixed pre-ADR-0171 grid. Published for a driver that has to
        aim a synthetic click at a cell (`render_compose_editor.py`), which
        must use the very metrics the row was drawn with or it clicks a
        different cell than the one it means to."""
        return self._row_metrics

    def _refresh_row(self):
        self.row_canvas.delete("all")
        self._cell_imgs.clear()
        c = self.row_canvas
        self._row_metrics = None
        if not self.vm.pack or self.vm.mode != "sprite":
            c.config(height=L.EMPTY_ROW_H)
            c.create_text(8, 15, anchor="w", fill="#556", text=L.ROW_WRONG_LAYER)
            return
        spec = self.vm.row_spec()
        if not spec:
            c.config(height=L.EMPTY_ROW_H)
            c.create_text(8, 15, anchor="w", fill="#556", text=L.ROW_NEEDS_SEED)
            return
        drawn = [self._row_art(cell) for cell in spec]
        # One grid for the whole repaint, sized to the biggest silhouette in
        # it, and stored before anything is drawn: `_row_index_at` reads the
        # same dict back, so drawing and hit-testing cannot answer from two
        # different grids. A pack without poses passes None and keeps today's
        # fixed cells to the pixel (`row_metrics(None)` is the old constants).
        # The ghost `+` cell asks for nothing (8x8) - it holds no art, so it
        # must not be what inflates the row.
        if self.vm.uses_poses():
            sizes = [(a.width, a.height) if a else (8, 8) for a, _cap in drawn]
            self._row_metrics = L.row_metrics(sizes)
        metrics = self._row_metrics
        width, height = L.grid_size(len(spec), metrics)
        c.config(width=width, height=height)
        for i, (cell, (art, caption)) in enumerate(zip(spec, drawn)):
            # Every coordinate comes from `compose_editor_layout`, whose
            # `cell_origin` is the inverse of the `index_at` a click goes
            # through - so what is drawn here is what a click there hits.
            self._draw_row_cell(cell, i, art, caption, metrics,
                                is_seed=(i == 0 and cell["node"] is not None))

    def _draw_row_cell(self, cell, index, art, caption, metrics, is_seed):
        bx, by, bx1, by1 = L.art_box(index, metrics)
        cap_x, cap_y = L.caption_point(index, metrics)
        c = self.row_canvas
        if cell["node"] is None:
            c.create_rectangle(bx, by, bx1, by1, outline="#5a6b85", dash=(3, 2))
            c.create_text((bx + bx1) // 2, (by + by1) // 2, text="+", fill="#93a7c4",
                          font=("", 16, "bold"))
            if caption:
                c.create_text(cap_x, cap_y, text=caption, fill="#5f6f8a", font=("", 8))
            return
        node = cell["node"]
        if art is None:
            c.create_rectangle(bx, by, bx1, by1, outline="#c06058", width=2)
            c.create_text((bx + bx1) // 2, (by + by1) // 2, text="?", fill="#c06058",
                          font=("", 14, "bold"))
            c.create_text(cap_x, cap_y, text=f"#{node}", fill="#d7a3a3", font=("", 8))
            return
        # One magnification for the whole row (`metrics["scale"]`), so two
        # silhouettes drawn side by side really are to scale - the comparison
        # ADR-0171 §1 asks the artist to make. Re-fitted against this cell's
        # own box as a floor, so a cell can clip nothing even if the grid and
        # the art ever disagree.
        scale = L.row_cell_scale(art.width, art.height) if metrics is None else \
            min(metrics["scale"], L.fit_scale_box(bx1 - bx, by1 - by, art.width, art.height))
        img, w, h = image_photo(art, scale)
        self._cell_imgs.append(img)
        c.create_image(bx + (bx1 - bx - w) // 2, by + (by1 - by - h) // 2, image=img,
                       anchor="nw")
        outline = "#ffd27d" if is_seed else "#7fa7e0"
        fill = "#ffe2a8" if is_seed else "#cfd8e6"
        c.create_rectangle(bx, by, bx1, by1, outline=outline, width=2)
        c.create_text(cap_x, cap_y, text=caption, fill=fill, font=("", 8))

    def _row_index_at(self, event):
        """The cell a click landed on, resolved through the very metrics the
        last repaint drew with (see `_row_metrics`)."""
        return L.index_at(event.x, event.y, self._row_metrics)

    def _row_left(self, event):
        if not self.vm.pack:
            return
        spec = self.vm.row_spec()
        i = self._row_index_at(event)
        if not (0 <= i < len(spec)):
            return
        cell = spec[i]
        if cell["node"] is not None:
            self.vm.swap_cell(i)
            self.refresh_all()
            return
        node = cell.get("add")
        if node is None:
            return
        if self.vm.lock(node, "sprite"):
            self.refresh_all()

    def _row_right(self, event):
        if not self.vm.pack:
            return
        spec = self.vm.row_spec()
        i = self._row_index_at(event)
        if not (0 <= i < len(spec)):
            return
        node = spec[i]["node"]
        if node is None:
            return
        self.vm.unlock(node)
        self.refresh_all()

    # ---- shared -------------------------------------------------------------

    def _selected_node(self, listbox):
        sel = listbox.curselection()
        if not sel:
            return None
        return int(listbox.get(sel[0]).split()[0][1:])

    def _bind_selection_preview(self):
        for lb in (self.bg_seed, self.bg_sugg, self.sp_seed, self.sp_sugg):
            lb.bind("<<ListboxSelect>>", lambda _e, b=lb: self._show_selected(b))

    def _show_selected(self, listbox):
        """Show the actual pixels of the highlighted cell in the preview panel,
        so a composer sees the art instead of decoding "#47".

        A list that has just *lost* its selection says nothing about what the
        artist is looking at, so it leaves the panel alone: every Listbox here
        is `exportselection=False`, but Tk still delivers a <<ListboxSelect>>
        with an empty selection in other cases, and clearing the art on it
        blanked the panel the moment a second list was touched."""
        if not self.vm.pack:
            return
        node = self._selected_node(listbox)
        if node is None:
            return
        self.preview.delete("all")
        self.preview_lbl.set("—")
        self.preview_tk = None
        sprite = listbox in (self.sp_seed, self.sp_sugg)
        kind = "sprite" if sprite else "object"
        # A sprite list names an anchor, and ADR-0171 makes the pose behind it
        # the thing being judged - previewing the anchor's own 8x8 would show
        # a shoulder where the artist asked to see the character.
        pose = self.vm.pose_for(node) if sprite else None
        try:
            art = self.vm.pack.pose_art(pose) if pose is not None else \
                self.vm.node_art(node, sprite=sprite)
        except E.ComposeError as e:
            self.status.set(str(e))
            self.preview_lbl.set(f"#{node} ({kind}) — {e}")
            return
        if art is None:
            self.preview_lbl.set(f"#{node} ({kind}) — nothing to draw")
            return
        img, _w, _h = image_photo(art, L.preview_scale(art.width, art.height))
        self.preview_tk = img
        self.preview.create_image(L.PREVIEW_BOX // 2, L.PREVIEW_BOX // 2, image=img)
        self.preview_lbl.set(f"#{node} ({kind})" if pose is None else
                             f"#{node} (pose {_pose_shape(pose)})")

    def refresh_all(self):
        """Pull every view from the ViewModel's current state — the single
        redraw path every command (seed/lock/unlock/swap/band change) calls."""
        self.status.set(self.vm.status)
        self._refresh_bg_sugg()
        self._refresh_sp_sugg()
        self._refresh_row()
        self._refresh_kept()

    def _refresh_kept(self):
        """Draw the composed sheet exactly as `Export` will write it - same
        grid, same gutter - and name the file it would become."""
        self._imgs.clear()
        self.canvas.delete("all")
        if not self.vm.pack:
            self.export_lbl.set("no pack open")
            return
        try:
            composed = self.vm.preview_sheet(self.out_var.get())
        except E.ComposeError as e:
            self.export_lbl.set(str(e))
            self.canvas.config(height=24)
            return
        if composed is None:
            self.export_lbl.set("nothing composed yet — seed a cell")
            self.canvas.config(height=24)
            return
        sheet, columns, unit, name = composed
        #The caption describes the *file*, so it counts the cells the sheet
        #really carries: on the pose path one locked anchor writes a whole
        #silhouette (ADR-0171 §5), so the locked count would understate it by
        #an order of magnitude.
        cells = len(self.vm.placements() or self.vm.locked_list())
        scale = L.export_scale(sheet.width)
        img, _w, h = image_photo(sheet, scale)
        self._imgs.append(img)
        self.canvas.config(height=h + 4)
        self.canvas.create_image(2, 2, image=img, anchor="nw")
        self.export_lbl.set(L.export_caption(name, cells, columns, unit,
                                             sheet.width, sheet.height, scale,
                                             self.vm.pack.scale))

    def export(self):
        if not self.vm.pack:
            return
        if not self.vm.can_export():
            messagebox.showwarning("Nothing to export", "Seed a cell first.")
            return
        try:
            name = self.vm.export(Path(self.out_var.get()))
        except E.ComposeError as e:
            messagebox.showerror("Export failed", str(e))
            return
        out = Path(self.out_var.get())
        self.status.set(f"wrote {out / name}.png/.json/.orig.png — paint it, then run mep_build.py (ADR-0153 §4)")
        messagebox.showinfo("Composed sheet written",
                            f"{name} written to\n{out}\n\nThe sheet and its .orig.png twin start identical. "
                            "Paint usr*.png in an image editor, then rebuild with mep_build.py.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="MesenCE composition editor (ADR-0165, F9.18)")
    ap.add_argument("folder", nargs="?", default=None, help="pack folder with textures/sheets/")
    args = ap.parse_args(argv)
    root = tk.Tk()
    folder = Path(args.folder) if args.folder else Path.cwd()
    EditorApp(root, folder)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
