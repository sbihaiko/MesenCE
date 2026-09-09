"""Render the live viewer's window to a PNG without a screen capture.

macOS gates `screencapture` behind the Screen Recording permission of the
process that calls it, which an agent's shell never has. This tool does not
need it: it runs the real RecordViewerApp against a live dir, lets it lay out
and poll, then walks the Tk widget tree and draws every mapped widget from
its actual on-screen rectangle, text and state - the two canvases from the
PhotoImages Tk itself holds, written out at 1:1. The result is the window's
true geometry with an approximation of the ttk theme, good enough to check
layout, overlap, wrapping and orientation at any window size.

    python3 scripts/render_record_viewer.py <live-dir> <out.png> <WxH> [action ...]

`action` names are RecordViewerApp methods invoked after the first poll, e.g.
`_cycle_layout` (Auto -> Side by side -> Stacked) or `_toggle_fit`. Needs
Pillow (only for the PNG); the viewer itself stays stdlib (ADR-0165).
"""
import sys
import time
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_viewer as rv  # noqa: E402

if len(sys.argv) < 4:
    sys.exit(__doc__)
live, out, geom = sys.argv[1], sys.argv[2], sys.argv[3]
actions = sys.argv[4:]

root = tk.Tk()
root.geometry(geom + "+60+60")
app = rv.RecordViewerApp(root, Path(live))
def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.01)
pump(0.4)
app._poll_now()
for a in actions:
    getattr(app, a)()
pump(0.5)

W, H = root.winfo_width(), root.winfo_height()
img = Image.new("RGB", (W, H), "#2b2b2b")
d = ImageDraw.Draw(img)
try:
    fnt = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 13)
    fntb = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 13)
    fnts = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 12)
except OSError:
    fnt = fntb = fnts = ImageFont.load_default()

rx, ry = root.winfo_rootx(), root.winfo_rooty()

def rect(w):
    return (w.winfo_rootx() - rx, w.winfo_rooty() - ry,
            w.winfo_rootx() - rx + w.winfo_width(), w.winfo_rooty() - ry + w.winfo_height())

def text_of(w):
    try:
        tv = w.cget("textvariable")
        if tv:
            return root.getvar(tv)
    except tk.TclError:
        pass
    try:
        return w.cget("text")
    except tk.TclError:
        return ""

def walk(w):
    if not w.winfo_ismapped():
        return
    r = rect(w)
    cls = w.winfo_class()
    if cls == "Canvas":
        d.rectangle(r, fill=w.cget("background"), outline="#444")
        for item in w.find_all():
            t = w.type(item)
            if t == "image":
                name = w.itemcget(item, "image")
                p = out + ".canvas.ppm"
                root.tk.call(name, "write", p, "-format", "ppm")
                fr = Image.open(p)
                cx, cy = w.coords(item)
                img.paste(fr, (int(r[0] + cx - fr.width / 2), int(r[1] + cy - fr.height / 2)))
            elif t == "rectangle":
                x0, y0, x1, y1 = w.coords(item)
                d.rectangle((r[0] + x0, r[1] + y0, r[0] + x1, r[1] + y1),
                            outline=w.itemcget(item, "outline"))
    elif cls in ("TLabel", "Label"):
        txt = text_of(w)
        fg = "#e6e6e6"
        try:
            st = w.cget("style")
            if st == "Meta.TLabel":
                fg = "#8a8a8a"
        except tk.TclError:
            pass
        if cls == "Label":
            d.rounded_rectangle(r, radius=3, fill=w.cget("background"))
            fg = w.cget("foreground")
        f = fnt
        try:
            fname = str(w.cget("font"))
            if "bold" in root.tk.call("font", "actual", fname) if fname else False:
                f = fntb
        except tk.TclError:
            pass
        anchor = "lm"
        try:
            if str(w.cget("anchor")) == "e":
                anchor = "rm"
        except tk.TclError:
            pass
        x = r[0] + 2 if anchor == "lm" else r[2] - 2
        wrap = 0
        try:
            wrap = int(str(w.cget("wraplength")) or 0)
        except tk.TclError:
            pass
        if wrap:
            words, line, y = txt.split(), "", r[1] + 2
            for wd in words:
                if d.textlength(line + " " + wd, font=fnts) > wrap:
                    d.text((r[0], y), line, fill=fg, font=fnts); y += 15; line = wd
                else:
                    line = (line + " " + wd).strip()
            d.text((r[0], y), line, fill=fg, font=fnts)
        else:
            d.text((x, (r[1] + r[3]) / 2), txt, fill=fg, font=f, anchor=anchor)
    elif cls in ("TButton",):
        d.rounded_rectangle(r, radius=5, fill="#5a5a5a", outline="#707070")
        d.text(((r[0] + r[2]) / 2, (r[1] + r[3]) / 2), text_of(w), fill="#f0f0f0", font=fnt, anchor="mm")
    elif cls == "TCheckbutton":
        on = False
        try:
            on = bool(root.getvar(w.cget("variable")))
        except tk.TclError:
            pass
        box = (r[0] + 2, (r[1] + r[3]) / 2 - 7, r[0] + 16, (r[1] + r[3]) / 2 + 7)
        d.rounded_rectangle(box, radius=3, fill="#3478f6" if on else "#555", outline="#777")
        if on:
            d.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), "✓", fill="white", font=fnts, anchor="mm")
        fg = "#e6e6e6" if str(w.instate(["!disabled"])) == "True" else "#777"
        d.text((r[0] + 22, (r[1] + r[3]) / 2), text_of(w), fill=fg, font=fnt, anchor="lm")
    elif cls == "TEntry":
        d.rounded_rectangle(r, radius=4, fill="#1e1e1e", outline="#666")
        d.text((r[0] + 6, (r[1] + r[3]) / 2), w.get(), fill="#e6e6e6", font=fnt, anchor="lm")
    elif cls == "TCombobox":
        d.rounded_rectangle(r, radius=4, fill="#5a5a5a", outline="#707070")
        d.text((r[0] + 6, (r[1] + r[3]) / 2), w.get(), fill="#f0f0f0", font=fnt, anchor="lm")
        d.text((r[2] - 8, (r[1] + r[3]) / 2), "⌄", fill="#f0f0f0", font=fnt, anchor="rm")
    elif cls == "TSpinbox":
        dis = "disabled" in w.state()
        d.rounded_rectangle(r, radius=4, fill="#1e1e1e" if not dis else "#333", outline="#666")
        d.text((r[0] + 6, (r[1] + r[3]) / 2), w.get(), fill="#e6e6e6" if not dis else "#777", font=fnt, anchor="lm")
    elif cls == "TSeparator":
        d.line((r[0], r[1], r[0], r[3]), fill="#555")
    for c in w.winfo_children():
        walk(c)

walk(root)
img.save(out)
Path(out + ".canvas.ppm").unlink(missing_ok=True)
print(f"saved {out} {W}x{H} orient={app._orientation} zoom={app.zoom_readout.get()}")
root.destroy()
