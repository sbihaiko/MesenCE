"""The composition editor (ADR-0165 / F9.18) — a tkinter layered canvas over
the host-free `compose_engine`.

`scripts/compose_editor.py [pack folder]` opens a pack recorded since F9.17
and lets an artist build a scene by the two queries ADR-0164 §5 defines:
seed -> rank -> lock -> recompute over the background adjacency (an object
layer) or inside a sprite Y band (floor-sharing shapes), then export the
kept cells as a composed `usrNNN` sheet. The engine never imports tkinter;
this view is a thin controller over it.

This is the interactive half and is judged by the human Phase 9 panel — the
automated half is `test_compose_engine.py`, which covers the engine's two
acceptance tests headless.
"""

import argparse
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compose_engine as E  # noqa: E402


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
        self.pack = None
        self.kept = []        # locked node ids, in lock order (seed excluded)
        self.seed = None
        self.mode = "object"  # the layer being composed: object or sprite
        self._imgs = []       # keep PhotoImage references alive
        self.bg_members = []  # (node, sheet, cell) for the background tab
        self.sp_members = []  # (node, sheet, cell) for the sprite tab

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

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=6, pady=4)
        self.sprite_tab = ttk.Frame(nb)
        self.bg_tab = ttk.Frame(nb)
        nb.add(self.bg_tab, text="Background (object layer)")
        nb.add(self.sprite_tab, text="Sprites (Y bands)")
        self._build_bg_tab()
        self._build_sprite_tab()

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
            pack = E.Pack(folder)
        except E.ComposeError as e:
            messagebox.showerror("Cannot compose", str(e))
            self.status.set(str(e))
            return
        self.pack = pack
        self.out_var.set(str(pack.sheets_dir))
        bg = pack.adjacency.bg_vocab_size
        sp = pack.adjacency.sp_vocab_size if pack.adjacency.sprites_present else 0
        kinds = ", ".join(pack.layer_kinds())
        self.status.set(f"{pack.sheets_dir} — {bg} background nodes, {sp} sprite nodes; layers: {kinds}")
        self.bg_members = pack.background_cells()
        self.sp_members = pack.sprite_cells()
        self._fill_bg_seed_list()
        self._fill_band_selector()
        self.kept, self.seed = [], None
        self._refresh_kept()

    # ---- background / object layer ------------------------------------------

    def _build_bg_tab(self):
        f = self.bg_tab
        left = ttk.LabelFrame(f, text="Background cells (most seen first)", padding=4)
        left.pack(side="left", fill="y", padx=4, pady=4)
        self.bg_seed = tk.Listbox(left, width=46, height=22)
        self.bg_seed.pack()
        ttk.Button(left, text="Seed selected", command=lambda: self.seed_from(self.bg_seed)).pack(pady=2)
        mid = ttk.LabelFrame(f, text="Ranked neighbours — lock to compose", padding=4)
        mid.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self.bg_sugg = tk.Listbox(mid, width=46, height=22)
        self.bg_sugg.pack(fill="both", expand=True)
        ttk.Button(mid, text="Lock suggestion", command=lambda: self.lock_from(self.bg_sugg)).pack(pady=2)
        ttk.Button(mid, text="Recompute (seed + locks)", command=self.refresh_bg).pack(pady=2)

    def _fill_bg_seed_list(self):
        self.bg_seed.delete(0, "end")
        for node, _sheet, cell in self.bg_members:
            self.bg_seed.insert("end", f"#{node}  count {cell.get('count')}  x{cell.get('x')}y{cell.get('y')}")
        self.refresh_bg()

    def refresh_bg(self):
        if not self.pack:
            return
        self.bg_sugg.delete(0, "end")
        base = self.locked_list()
        if not base:
            return
        for node, score in self.pack.background_rank(base):
            self.bg_sugg.insert("end", f"#{node}  score {score:.3f}")

    # ---- sprites / Y band ---------------------------------------------------

    def _build_sprite_tab(self):
        f = self.sprite_tab
        sel = ttk.LabelFrame(f, text="Floor band (bottom edge, 8 px)", padding=4)
        sel.pack(side="left", fill="y", padx=4, pady=4)
        self.band_var = tk.StringVar()
        self.band_box = ttk.Combobox(sel, textvariable=self.band_var, state="readonly", width=12)
        self.band_box.pack()
        self.sp_seed = tk.Listbox(sel, width=30, height=20)
        self.sp_seed.pack(pady=4)
        ttk.Button(sel, text="Seed selected", command=lambda: self.seed_from(self.sp_seed)).pack(pady=2)
        mid = ttk.LabelFrame(f, text="Ranked band members — lock to compose", padding=4)
        mid.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self.sp_sugg = tk.Listbox(mid, width=34, height=22)
        self.sp_sugg.pack(fill="both", expand=True)
        ttk.Button(mid, text="Lock suggestion", command=lambda: self.lock_from(self.sp_sugg)).pack(pady=2)
        ttk.Button(mid, text="Recompute", command=self.refresh_sprites).pack(pady=2)
        self.band_box.bind("<<ComboboxSelected>>", lambda _e: self._on_band())

    def _fill_band_selector(self):
        adj = self.pack.adjacency if self.pack else None
        bands = adj.floors() if adj and adj.sprites_present else []
        self.band_box["values"] = [f"{b} px" for b in bands]
        if bands:
            self.band_var.set(f"{bands[-1]} px")  # default: the most common ground
        self._on_band()

    def _current_band(self):
        try:
            return int(self.band_var.get().split()[0])
        except (ValueError, AttributeError):
            return None

    def _on_band(self):
        if not self.pack or not self.pack.adjacency.sprites_present:
            return
        band = self._current_band()
        self.sp_seed.delete(0, "end")
        for node in self.pack.adjacency.band_members(band) if band is not None else []:
            self.sp_seed.insert("end", f"#{node}")
        self.kept, self.seed = [], None
        self.mode = "sprite"
        self.refresh_sprites()

    def refresh_sprites(self):
        if not self.pack or not self.pack.adjacency.sprites_present:
            return
        band = self._current_band()
        if band is None:
            return
        self.sp_sugg.delete(0, "end")
        locked = self.locked_list()
        base = locked if locked else ([self.seed] if self.seed is not None else [])
        if not base:
            return
        for node, co in self.pack.sprite_rank(band, locked=base):
            name = self._shape_name(node)
            self.sp_sugg.insert("end", f"#{node}  coFrames {co}{'  ' + name if name else ''}")

    def _shape_name(self, node):
        tiles = self.pack.adjacency.sp.get(node).tiles if self.pack else None
        return tiles[0].get("tile", "")[:6] if tiles else ""

    # ---- shared -------------------------------------------------------------

    def locked_list(self):
        ids = ([self.seed] if self.seed is not None else []) + self.kept
        seen = []
        for n in ids:
            if n is not None and n not in seen:
                seen.append(n)
        return seen

    def seed_from(self, listbox):
        sel = listbox.curselection()
        if not sel:
            return
        text = listbox.get(sel[0])
        node = int(text.split()[0][1:])
        self.seed = node
        self.kept = []
        self.mode = "sprite" if listbox is self.sp_seed else "object"
        self.status.set(f"seed {node} ({self.mode})")
        self._refresh_suggestions()

    def lock_from(self, listbox):
        sel = listbox.curselection()
        if not sel:
            return
        text = listbox.get(sel[0])
        node = int(text.split()[0][1:])
        self.mode = "sprite" if listbox is self.sp_sugg else "object"
        if node == self.seed:
            return
        if node not in self.kept:
            self.kept.append(node)
            self.status.set(f"locked {len(self.kept)} cells after seed {self.seed}")
        self._refresh_suggestions()

    def _refresh_suggestions(self):
        if not self.pack:
            return
        self.refresh_bg()
        self.refresh_sprites()
        self._refresh_kept()

    def _refresh_kept(self):
        """Preview the kept cells (seed first) as one strip, from whichever
        layer is being composed."""
        self._imgs.clear()
        self.canvas.delete("all")
        if not self.pack or (self.seed is None and not self.kept):
            return
        order = self.locked_list()
        arts = []
        for node in order:
            try:
                arts.append(self.pack.node_art(node, sprite=(self.mode == "sprite")))
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
        if not self.pack:
            return
        order = self.locked_list()
        if not order:
            messagebox.showwarning("Nothing to export", "Seed a cell first.")
            return
        try:
            if self.mode == "sprite":
                band = self._current_band()
                name = self.pack.export("sprite", order, seed=self.seed, locked=self.kept,
                                        band=band, to_dir=Path(self.out_var.get()))
            else:
                name = self.pack.export("object", order, seed=self.seed, locked=self.kept,
                                        to_dir=Path(self.out_var.get()))
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
