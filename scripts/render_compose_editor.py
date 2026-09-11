"""Render the composition editor's window to a PNG without a screen capture.

Same trick as `render_record_viewer.py` (ADR-0169's viewer): macOS gates
`screencapture` behind a Screen Recording permission an agent's shell never
has, so instead of grabbing pixels off the display this tool runs the real
`compose_editor.EditorApp` against a real pack, lets Tk lay it out, then walks
the widget tree and draws every mapped widget from its actual on-screen
rectangle, text and state - canvases from the PhotoImages Tk itself holds.
Every colour is resolved through `winfo_rgb`, so an aqua system colour name
(`systemWindowBackgroundColor` and friends of the theme the editor really
runs under) is drawn as the pixels the artist sees, and every string is
clipped to its widget the way Tk clips it. The result is the window's true
geometry with an approximation of the theme, good enough to judge layout,
overlap, truncation and contrast.

    python3 scripts/render_compose_editor.py <pack folder> <out.png> <WxH> [step ...]

A `step` drives the GUI the way a hand would, through the widgets rather than
the ViewModel, so the wiring itself is exercised:

    tab-bg | tab-sprites      switch notebook tabs
    pick-bg:<i>               select row <i> of the background cell list
    seed-bg                   press "Seed selected" on the background tab
    pick-bg-sugg:<i>          select row <i> of the ranked neighbour list
    lock-bg                   press "Lock suggestion"
    band:<i>                  choose floor band <i> in the combobox
    pick-sprite:<i>           select row <i> of the band member list
    seed-sprite               press "Seed selected" on the sprite tab
    pick-sprite-sugg:<i>      select row <i> of the ranked band member list
    lock-sprite               press "Lock selected suggestion"
    row-click:<i>             left-click the composed row's cell <i>
    row-remove:<i>            right-click the composed row's cell <i>
    sprite-band-demo[:<n>]    the whole ADR-0171 gesture in one step: open the
                              sprite tab, seed the band's first pose and lock
                              the top <n> (default 1) suggestions, so one
                              render shows a composed pose band

Needs Pillow (only to write the PNG); the editor itself stays stdlib
(ADR-0165).
"""
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compose_editor as ce  # noqa: E402
import compose_editor_layout as L  # noqa: E402


def load_fonts():
    try:
        base = "/System/Library/Fonts/SFNS.ttf"
        return (ImageFont.truetype(base, 13), ImageFont.truetype(base, 11))
    except OSError:
        default = ImageFont.load_default()
        return (default, default)


FNT, FNT_S = load_fonts()


def opt(widget, name, default=""):
    """A widget option as a string, or `default` when unset/unsupported."""
    try:
        value = str(widget.cget(name))
    except tk.TclError:
        return default
    return default if value in ("", "None") else value


def canvas_font(spec):
    """A Tk canvas font spec ("", 16, "bold") mapped onto our two sizes."""
    try:
        size = int(str(spec).split()[1])
    except (IndexError, ValueError):
        return FNT
    return FNT if size >= 12 else FNT_S


class Renderer:
    def __init__(self, root, out):
        self.root, self.out = root, out
        self.style = ttk.Style(root)
        self.w, self.h = root.winfo_width(), root.winfo_height()
        self.window_bg = self.rgb(root.cget("background"), (236, 236, 236))
        self.img = Image.new("RGB", (self.w, self.h), self.window_bg)
        self.d = ImageDraw.Draw(self.img)
        self.ox, self.oy = root.winfo_rootx(), root.winfo_rooty()

    # ---- colour / text helpers ---------------------------------------------

    def rgb(self, spec, default=(0, 0, 0)):
        """Any Tk colour (hex, name, or an aqua `system*` colour) as RGB."""
        try:
            r, g, b = self.root.winfo_rgb(str(spec))
        except tk.TclError:
            return default
        return (r >> 8, g >> 8, b >> 8)

    def themed(self, widget, option, fallback):
        """A ttk widget's colour: its own option when the editor set one,
        else what the live theme resolves for its style."""
        own = opt(widget, option)
        if own:
            return self.rgb(own, fallback)
        return self.rgb(self.style.lookup(widget.winfo_class(), option), fallback)

    def clipped(self, text, font, width):
        """`text` cut to `width` px with an ellipsis, as Tk clips a widget."""
        if width <= 0 or self.d.textlength(text, font=font) <= width:
            return text
        cut = text
        while cut and self.d.textlength(cut + "…", font=font) > width:
            cut = cut[:-1]
        return cut + "…"

    def line(self, xy, text, font, fill, width=0, anchor="lm"):
        self.d.text(xy, self.clipped(text, font, width) if width else text,
                    fill=fill, font=font, anchor=anchor)

    def rect(self, widget):
        x = widget.winfo_rootx() - self.ox
        y = widget.winfo_rooty() - self.oy
        return (x, y, x + widget.winfo_width(), y + widget.winfo_height())

    # ---- per-class painters ------------------------------------------------

    def paint_canvas(self, widget, r):
        """A canvas is drawn into its own image and pasted, so an item placed
        outside the widget is clipped away exactly as Tk clips it - the
        difference between "off-canvas, invisible to the artist" and "drawn on
        top of the neighbouring frame"."""
        sub = Image.new("RGB", (max(1, r[2] - r[0]), max(1, r[3] - r[1])),
                        self.rgb(opt(widget, "background", "white")))
        page, canvas_d, origin = self.img, self.d, (r[0], r[1])
        self.img, self.d = sub, ImageDraw.Draw(sub)
        r = (0, 0, sub.width, sub.height)
        self.d.rectangle((0, 0, sub.width - 1, sub.height - 1), outline=(170, 170, 170))
        for item in widget.find_all():
            kind = widget.type(item)
            coords = widget.coords(item)
            if kind == "image":
                ppm = self.out + ".item.ppm"
                self.root.tk.call(widget.itemcget(item, "image"), "write", ppm,
                                  "-format", "ppm")
                frame = Image.open(ppm)
                x, y = r[0] + coords[0], r[1] + coords[1]
                if str(widget.itemcget(item, "anchor")) != "nw":
                    x, y = x - frame.width / 2, y - frame.height / 2
                self.img.paste(frame, (int(x), int(y)))
            elif kind == "rectangle":
                x0, y0, x1, y1 = coords
                self.d.rectangle((r[0] + x0, r[1] + y0, r[0] + x1, r[1] + y1),
                                 outline=self.rgb(widget.itemcget(item, "outline")),
                                 width=int(float(widget.itemcget(item, "width") or 1)))
            elif kind == "text":
                anchor = {"w": "lm", "center": "mm"}.get(
                    str(widget.itemcget(item, "anchor")), "mm")
                self.line((r[0] + coords[0], r[1] + coords[1]),
                          widget.itemcget(item, "text"),
                          canvas_font(widget.itemcget(item, "font")),
                          self.rgb(widget.itemcget(item, "fill") or "black"),
                          anchor=anchor)
        self.img, self.d = page, canvas_d
        self.img.paste(sub, origin)

    def paint_listbox(self, widget, r):
        self.d.rectangle(r, fill=self.rgb(widget.cget("background"), (255, 255, 255)),
                         outline=(150, 150, 150))
        fg = self.rgb(widget.cget("foreground"), (0, 0, 0))
        sel_bg = self.rgb(widget.cget("selectbackground"), (60, 120, 216))
        sel_fg = self.rgb(widget.cget("selectforeground"), (255, 255, 255))
        selected = set(widget.curselection())
        step = tkfont.Font(root=self.root, font=widget.cget("font")).metrics("linespace")
        y = r[1] + 2
        for i in range(widget.size()):
            if y + step > r[3]:
                self.line((r[0] + 4, y + step / 2), "…", FNT_S, fg)
                break
            if i in selected:
                self.d.rectangle((r[0] + 1, y, r[2] - 1, y + step), fill=sel_bg)
            self.line((r[0] + 4, y + step / 2), widget.get(i), FNT_S,
                      sel_fg if i in selected else fg, width=r[2] - r[0] - 8)
            y += step

    def paint_labelframe(self, widget, r):
        self.d.rectangle((r[0], r[1] + 7, r[2], r[3]), outline=(160, 160, 160))
        label = opt(widget, "text")
        if label:
            width = self.d.textlength(label, font=FNT_S)
            self.d.rectangle((r[0] + 6, r[1] + 1, r[0] + 12 + width, r[1] + 14),
                             fill=self.window_bg)
            self.line((r[0] + 9, r[1] + 7), label, FNT_S, (40, 40, 40),
                      width=r[2] - r[0] - 12)

    def paint_notebook(self, widget, r):
        x = r[0] + 6
        current = widget.select()
        for tab in widget.tabs():
            label = widget.tab(tab, "text")
            width = self.d.textlength(label, font=FNT) + 20
            active = tab == current
            self.d.rounded_rectangle((x, r[1] + 2, x + width, r[1] + 24), radius=4,
                                     fill=(120, 150, 200) if active else (222, 222, 222),
                                     outline=(150, 150, 150))
            self.line((x + width / 2, r[1] + 13), label, FNT,
                      (255, 255, 255) if active else (70, 70, 70), anchor="mm")
            x += width + 4

    def paint_label(self, widget, r):
        text = opt(widget, "textvariable")
        text = self.root.getvar(text) if text else opt(widget, "text")
        fg = self.themed(widget, "foreground", (0, 0, 0))
        wrap = int(float(opt(widget, "wraplength", 0) or 0))
        if not wrap:
            self.line((r[0] + 2, (r[1] + r[3]) / 2), text, FNT, fg,
                      width=r[2] - r[0] - 4)
            return
        line, y = "", r[1] + 2
        for word in text.split():
            if self.d.textlength(line + " " + word, font=FNT_S) > wrap:
                self.line((r[0] + 2, y), line, FNT_S, fg, anchor="la")
                y, line = y + 14, word
            else:
                line = (line + " " + word).strip()
        self.line((r[0] + 2, y), line, FNT_S, fg, anchor="la")

    def walk(self, widget):
        if not widget.winfo_ismapped():
            return
        r = self.rect(widget)
        cls = widget.winfo_class()
        if cls == "Canvas":
            self.paint_canvas(widget, r)
        elif cls == "Listbox":
            self.paint_listbox(widget, r)
        elif cls == "TLabelframe":
            self.paint_labelframe(widget, r)
        elif cls == "TNotebook":
            self.paint_notebook(widget, r)
        elif cls in ("TLabel", "Label"):
            self.paint_label(widget, r)
        elif cls == "TButton":
            self.d.rounded_rectangle(r, radius=5, fill=(250, 250, 250),
                                     outline=(160, 160, 160))
            self.line(((r[0] + r[2]) / 2, (r[1] + r[3]) / 2), opt(widget, "text"), FNT,
                      (20, 20, 20), width=r[2] - r[0] - 8, anchor="mm")
        elif cls in ("TEntry", "TCombobox"):
            combo = cls == "TCombobox"
            self.d.rounded_rectangle(r, radius=4,
                                     fill=(240, 240, 240) if combo else (255, 255, 255),
                                     outline=(150, 150, 150))
            self.line((r[0] + 6, (r[1] + r[3]) / 2), widget.get(), FNT_S, (20, 20, 20),
                      width=r[2] - r[0] - (26 if combo else 12))
            if combo:
                self.line((r[2] - 8, (r[1] + r[3]) / 2), "v", FNT_S, (20, 20, 20),
                          anchor="rm")
        for child in widget.winfo_children():
            self.walk(child)


class Click:
    """The two fields `EditorApp`'s canvas handlers read off a Tk event."""

    def __init__(self, x, y):
        self.x, self.y = x, y


def select(listbox, index):
    listbox.selection_clear(0, "end")
    listbox.selection_set(index)
    listbox.event_generate("<<ListboxSelect>>")


def run_step(app, step):
    name, _, arg = step.partition(":")
    index = int(arg) if arg else 0
    if name == "tab-bg":
        app.bg_tab.master.select(app.bg_tab)
    elif name == "tab-sprites":
        app.sprite_tab.master.select(app.sprite_tab)
    elif name == "pick-bg":
        select(app.bg_seed, index)
    elif name == "pick-bg-sugg":
        select(app.bg_sugg, index)
    elif name == "seed-bg":
        app._seed_bg()
    elif name == "lock-bg":
        app._lock_bg()
    elif name == "band":
        app.band_box.current(index)
        app.band_box.event_generate("<<ComboboxSelected>>")
    elif name == "pick-sprite":
        select(app.sp_seed, index)
    elif name == "pick-sprite-sugg":
        select(app.sp_sugg, index)
    elif name == "seed-sprite":
        app._seed_sprite()
    elif name == "lock-sprite":
        app._lock_sprite()
    elif name in ("row-click", "row-remove"):
        # The row's grid is per-repaint since ADR-0171 (a band of poses has
        # cells as big as its biggest silhouette), so the click is aimed
        # through the metrics the app actually drew with. Computing it from
        # the fixed CELL_W/CELL_H would hit a different cell than the one the
        # step names - the same drawing/hit-testing drift the layout module
        # exists to prevent.
        click = Click(*L.cell_center(index, app.row_metrics()))
        (app._row_left if name == "row-click" else app._row_right)(click)
    elif name == "sprite-band-demo":
        app.sprite_tab.master.select(app.sprite_tab)
        select(app.sp_seed, 0)
        app._seed_sprite()
        for _ in range(index or 1):
            if not app.sp_sugg.size():
                break
            select(app.sp_sugg, 0)
            app._lock_sprite()
    else:
        raise SystemExit(f"unknown step: {step}")


def main(argv):
    if len(argv) < 4:
        raise SystemExit(__doc__)
    pack, out, geom, steps = argv[1], argv[2], argv[3], argv[4:]
    root = tk.Tk()
    root.geometry(geom + "+40+40")
    app = ce.EditorApp(root, Path(pack))

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            root.update()
            time.sleep(0.01)

    pump(0.5)
    for step in steps:
        run_step(app, step)
        pump(0.2)
    pump(0.4)

    renderer = Renderer(root, out)
    renderer.walk(root)
    renderer.img.save(out)
    Path(out + ".item.ppm").unlink(missing_ok=True)
    print(f"saved {out} {renderer.w}x{renderer.h}")
    print(f"status: {app.status.get()}")
    print(f"export: {app.export_lbl.get()}")
    root.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
