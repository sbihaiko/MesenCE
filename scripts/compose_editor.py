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
import compose_engine as E  # noqa: E402
from compose_viewmodel import ComposeViewModel  # noqa: E402


def _backdrop_rgb(rgba, backdrop=(0x22, 0x22, 0x2A)):
    a = rgba[3] / 255.0
    return tuple(int(round(rgba[i] * a + backdrop[i] * (1.0 - a))) for i in range(3))


def strip_photo(arts, scale, gap=3):
    """One scaled RGB strip image of the kept cells (alpha blended over a dark
    backdrop so transparency reads as background, not as black art)."""
    unit = arts[0].width if arts else 8
    n = len(arts)
    pad = 4
    width = pad * 2 + n * unit * scale + (n - 1) * gap
    height = pad * 2 + unit * scale
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            row += bytes((0x22, 0x22, 0x2A))
        rows.append(row)
    for i, art in enumerate(arts):
        for sy in range(unit):
            for sx in range(unit):
                c = _backdrop_rgb(art.get(sx, sy))
                x0 = pad + i * (unit * scale + gap) + sx * scale
                y0 = pad + sy * scale
                for dy in range(scale):
                    off = (y0 + dy) * width * 3 + x0 * 3
                    for dx in range(scale):
                        rows[y0 + dy][off + dx * 3:off + dx * 3 + 3] = bytes(c)
    data = bytearray(b"P6\n%d %d\n255\n" % (width, height))
    for row in rows:
        data += row
    with tempfile.NamedTemporaryFile(suffix=".ppm", delete=False) as f:
        f.write(data)
        path = f.name
    img = tk.PhotoImage(file=path)
    Path(path).unlink(missing_ok=True)
    return img, width, height


class EditorApp:
    def __init__(self, root: tk.Tk, folder: Path):
        self.root = root
        root.title("MesenCE — composition editor (F9.18)")
        self.vm = ComposeViewModel()
        self._imgs = []       # keep PhotoImage references alive
        self._cell_imgs = []

        top = ttk.Frame(root, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Pack:").pack(side="left")
        self.folder_var = tk.StringVar(value=str(folder))
        ttk.Entry(top, textvariable=self.folder_var, width=48).pack(side="left", padx=4)
        ttk.Button(top, text="Open…", command=self.open_pack).pack(side="left")
        ttk.Label(top, text="Output:").pack(side="left", padx=(12, 2))
        self.out_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.out_var, width=24).pack(side="left", padx=4)
        ttk.Button(top, text="Export", command=self.export).pack(side="left")

        self.status = tk.StringVar(value="no pack open")
        ttk.Label(root, textvariable=self.status, foreground="#555").pack(fill="x", padx=6)

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=6, pady=(2, 2))
        nb = ttk.Notebook(body)
        nb.pack(side="left", fill="both", expand=True)
        self.sprite_tab = ttk.Frame(nb)
        self.bg_tab = ttk.Frame(nb)
        nb.add(self.bg_tab, text="Background (object layer)")
        nb.add(self.sprite_tab, text="Sprites (Y bands)")
        self._build_bg_tab()
        self._build_sprite_tab()
        self._bind_selection_preview()

        # Selection preview — the actual pixels of the highlighted cell, so a
        # composer sees the art instead of decoding "#47".
        side = ttk.Frame(body)
        side.pack(side="right", fill="y", padx=(8, 0))
        ttk.Label(side, text="Selection", foreground="#aaa").pack(anchor="w")
        self.preview = tk.Canvas(side, width=132, height=132, background="#1e1e24",
                                 highlightthickness=0)
        self.preview.pack()
        self.preview_tk = None   # keep the PhotoImage alive
        self.preview_lbl = tk.StringVar(value="—")
        ttk.Label(side, textvariable=self.preview_lbl, foreground="#aaa",
                  wraplength=124).pack(anchor="w", pady=(4, 0))

        self.canvas = tk.Canvas(root, height=120, background="#2b2b33", highlightthickness=0)
        self.canvas.pack(fill="x", padx=6, pady=(0, 6))
        if folder.is_dir():
            self.load_pack(folder)

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

    # ---- background / object layer ------------------------------------------

    def _build_bg_tab(self):
        f = self.bg_tab
        left = ttk.LabelFrame(f, text="Background cells (most seen first)", padding=4)
        left.pack(side="left", fill="y", padx=4, pady=4)
        self.bg_seed = tk.Listbox(left, width=46, height=22)
        self.bg_seed.pack()
        ttk.Button(left, text="Seed selected", command=self._seed_bg).pack(pady=2)
        mid = ttk.LabelFrame(f, text="Ranked neighbours — lock to compose", padding=4)
        mid.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self.bg_sugg = tk.Listbox(mid, width=46, height=22)
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
        sel = ttk.LabelFrame(f, text="Floor band (bottom edge, 8 px) — seed palette", padding=4)
        sel.pack(side="left", fill="y", padx=4, pady=4)
        self.band_var = tk.StringVar()
        self.band_box = ttk.Combobox(sel, textvariable=self.band_var, state="readonly", width=12)
        self.band_box.pack()
        self.sp_seed = tk.Listbox(sel, width=24, height=18)
        self.sp_seed.pack(pady=4)
        ttk.Button(sel, text="Seed selected", command=self._seed_sprite).pack(pady=2)

        # The gradeado (ADR-0165 GUI): one cell per sprite of the composed band,
        # clickable — click a + cell to lock the engine's next pick, click a
        # locked cell to swap it for the next recommendation (the butterfly: the
        # lock set changed, so the whole row re-ranks), right-click to remove a
        # lock. Removing the last lock clears the composition.
        mid = ttk.LabelFrame(
            f, text="Composed band — click + to lock · click a locked cell to swap · right-click to remove",
            padding=4)
        mid.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self._ROW_N = 8
        self._CELL_W = 66
        self._CELL_H = 84
        self.row_canvas = tk.Canvas(mid, height=30, background="#1e1e24", highlightthickness=0)
        self.row_canvas.pack(fill="x")
        self.row_canvas.bind("<Button-1>", self._row_left)
        self.row_canvas.bind("<Button-3>", self._row_right)
        sugg = ttk.LabelFrame(mid, text="Ranked band members (coFrames) — or lock a pick here", padding=2)
        sugg.pack(fill="both", expand=True, pady=(4, 0))
        self.sp_sugg = tk.Listbox(sugg, width=42, height=12)
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
        self.sp_seed.delete(0, "end")
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
        self.sp_sugg.delete(0, "end")
        if self.vm.mode != "sprite":
            return
        for node, co in self.vm.sprite_rank():
            name = self.vm.shape_name(node)
            self.sp_sugg.insert("end", f"#{node}  coFrames {co}{'  ' + name if name else ''}")

    # ---- sprite band gradeado (the clickable composition row) ---------------

    def _refresh_row(self):
        self.row_canvas.delete("all")
        self._cell_imgs.clear()
        c = self.row_canvas
        if not self.vm.pack or self.vm.mode != "sprite":
            c.config(height=30)
            c.create_text(8, 15, anchor="w", fill="#556",
                          text="the row composes the sprite floor band — seed one on this tab")
            return
        spec = self.vm.row_spec()
        if not spec:
            c.config(height=30)
            c.create_text(8, 15, anchor="w", fill="#556",
                          text="seed a band member (left) — it becomes the first locked cell")
            return
        rows = (len(spec) + self._ROW_N - 1) // self._ROW_N
        c.config(width=self._ROW_N * self._CELL_W, height=rows * self._CELL_H)
        for i, cell in enumerate(spec):
            col, row = divmod(i, self._ROW_N)
            self._draw_row_cell(cell, col * self._CELL_W, row * self._CELL_H,
                                is_seed=(i == 0 and cell["node"] is not None))

    def _draw_row_cell(self, cell, x0, y0, is_seed):
        box = self._CELL_W - 8
        bx, by = x0 + (self._CELL_W - box) // 2, y0 + 2
        c = self.row_canvas
        if cell["node"] is None:
            cand = cell.get("add")
            c.create_rectangle(bx, by, bx + box, by + box, outline="#5a6b85", dash=(3, 2))
            c.create_text(bx + box // 2, by + box // 2, text="+", fill="#93a7c4",
                          font=("", 16, "bold"))
            if cand is not None:
                c.create_text(x0 + self._CELL_W // 2, y0 + self._CELL_H - 12,
                              text=f"#{cand}", fill="#5f6f8a", font=("", 8))
            return
        node = cell["node"]
        try:
            art = self.vm.node_art(node, sprite=True)
        except E.ComposeError:
            c.create_rectangle(bx, by, bx + box, by + box, outline="#c06058", width=2)
            c.create_text(bx + box // 2, by + box // 2, text="?", fill="#c06058", font=("", 14, "bold"))
            c.create_text(x0 + self._CELL_W // 2, y0 + self._CELL_H - 12, text=f"#{node}",
                          fill="#d7a3a3", font=("", 8))
            return
        unit = art.width
        scale = max(1, (box - 8) // unit)
        img, w, h = strip_photo([art], scale, gap=0)
        self._cell_imgs.append(img)
        c.create_image(bx + (box - w) // 2, by + (box - h) // 2, image=img, anchor="nw")
        outline = "#ffd27d" if is_seed else "#7fa7e0"
        fill = "#ffe2a8" if is_seed else "#cfd8e6"
        c.create_rectangle(bx, by, bx + box, by + box, outline=outline, width=2)
        c.create_text(x0 + self._CELL_W // 2, y0 + self._CELL_H - 12, text=f"#{node}",
                      fill=fill, font=("", 8))

    def _row_index_at(self, event):
        return (event.y // self._CELL_H) * self._ROW_N + (event.x // self._CELL_W)

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
        so a composer sees the art instead of decoding "#47"."""
        self.preview.delete("all")
        self.preview_lbl.set("—")
        self.preview_tk = None
        if not self.vm.pack:
            return
        node = self._selected_node(listbox)
        if node is None:
            return
        sprite = listbox in (self.sp_seed, self.sp_sugg)
        kind = "sprite" if sprite else "object"
        try:
            art = self.vm.node_art(node, sprite=sprite)
        except E.ComposeError as e:
            self.status.set(str(e))
            self.preview_lbl.set(f"#{node} ({kind}) — {e}")
            return
        unit = art.width
        scale = max(1, min(16, 124 // unit))
        img, _w, _h = strip_photo([art], scale)
        self.preview_tk = img
        self.preview.create_image(66, 66, image=img)
        self.preview_lbl.set(f"#{node} ({kind})")

    def refresh_all(self):
        """Pull every view from the ViewModel's current state — the single
        redraw path every command (seed/lock/unlock/swap/band change) calls."""
        self.status.set(self.vm.status)
        self._refresh_bg_sugg()
        self._refresh_sp_sugg()
        self._refresh_row()
        self._refresh_kept()

    def _refresh_kept(self):
        """Preview the kept cells (seed first) as one strip, from whichever
        layer is being composed."""
        self._imgs.clear()
        self.canvas.delete("all")
        if not self.vm.pack:
            return
        order = self.vm.locked_list()
        if not order:
            return
        arts = []
        for node in order:
            try:
                arts.append(self.vm.node_art(node))
            except E.ComposeError as e:
                self.status.set(str(e))
                return
        if not arts:
            return
        scale = max(1, min(16, 96 // arts[0].width))
        img, w, h = strip_photo(arts, scale)
        self._imgs.append(img)
        self.canvas.config(width=w + 4, height=h + 4)
        self.canvas.create_image(2, 2, image=img, anchor="nw")

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
