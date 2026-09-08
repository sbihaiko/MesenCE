"""ViewModel for the composition editor (ADR-0165, F9.18) — MVVM split so the
seed/lock/swap/export state machine is testable headless, with zero tkinter.

`compose_engine.Pack` is the Model (already host-free, per ADR-0165 §Decision
2). `ComposeViewModel` holds the editor's session state — which layer is being
composed, the seed, the locked set, the active sprite Y band — and exposes
every gesture the view offers as a plain method returning plain data, so
`test_compose_viewmodel.py` exercises a full composition without a window.
`scripts/compose_editor.py`'s `EditorApp` is the View: it renders this class's
state and forwards tkinter events into these methods, nothing more.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compose_engine as E  # noqa: E402


class ComposeViewModel:
    def __init__(self):
        self.pack = None
        self.seed = None
        self.kept = []          # locked node ids, in lock order (seed excluded)
        self.mode = "object"    # the layer being composed: "object" or "sprite"
        self.band = None        # current Y band (sprite mode only)
        self.bg_members = []    # (node, Sheet, cell), most-seen first
        self.sp_members = []
        self.status = "no pack open"

    # ---- pack lifecycle -------------------------------------------------

    def load(self, folder) -> str:
        """Opens `folder`; raises `compose_engine.ComposeError` on failure,
        same as the Model — the view decides how to show that."""
        pack = E.Pack(Path(folder))
        self.pack = pack
        self.bg_members = pack.background_cells()
        self.sp_members = pack.sprite_cells()
        self.seed, self.kept = None, []
        self.mode = "object"
        bands = self.bands()
        self.band = bands[-1] if bands else None  # default: the most common ground
        bg = pack.adjacency.bg_vocab_size
        sp = pack.adjacency.sp_vocab_size if pack.adjacency.sprites_present else 0
        kinds = ", ".join(pack.layer_kinds())
        self.status = f"{pack.sheets_dir} — {bg} background nodes, {sp} sprite nodes; layers: {kinds}"
        return self.status

    def bands(self) -> list:
        return self.pack.adjacency.floors() if self.pack and self.pack.adjacency.sprites_present else []

    def set_band(self, band):
        """Switching floor bands starts that band's composition fresh."""
        self.band = band
        self.seed, self.kept = None, []
        self.mode = "sprite"

    # ---- locking state ----------------------------------------------------

    def locked_list(self) -> list:
        ids = ([self.seed] if self.seed is not None else []) + self.kept
        seen = []
        for n in ids:
            if n is not None and n not in seen:
                seen.append(n)
        return seen

    def seed_object(self, node):
        self.mode = "object"
        self.seed = node
        self.kept = []
        self.status = f"seed {node} (object)"

    def seed_sprite(self, node) -> bool:
        """Re-seeding the sprite row swaps only the first cell — the rest
        of a band the artist already built is kept, not wiped."""
        self.mode = "sprite"
        if self.seed is not None or self.kept:
            if node == self.seed:
                self.status = f"#{node} is already the seed"
                return False
            if node in self.kept:
                self.status = f"#{node} is already locked in the band row"
                return False
            self.seed = node
            self.status = f"seed swapped to #{node}; the rest of the row is kept"
        else:
            self.seed = node
            self.status = f"seed {node} (sprite)"
        return True

    def lock(self, node, kind: str) -> bool:
        """`kind` is "object" or "sprite" — which layer the suggestion came
        from; determines the active mode."""
        self.mode = kind
        if node == self.seed or node in self.kept:
            return False
        self.kept.append(node)
        self.status = f"locked {len(self.kept)} cells after seed {self.seed}"
        return True

    def unlock(self, node) -> bool:
        """Remove one lock. Unlocking the seed clears the whole composition —
        there is nothing left to recompute from."""
        if node == self.seed:
            self.seed, self.kept = None, []
            self.status = "all locks removed — composition cleared"
            return True
        if node in self.kept:
            self.kept.remove(node)
            self.status = f"unlocked #{node}"
            return True
        return False

    def swap_cell(self, index: int):
        """Advance the locked cell at `index` to the next sprite the engine
        recommends for the rest of the row, cycling past the current occupant
        so repeated calls tour the alternatives instead of bouncing back.
        Because the lock set changed, callers should re-fetch `row_spec()`/
        `sprite_rank()` afterwards — the rest of the row re-ranks (the
        butterfly). Returns the new node id, or None when nothing else fits."""
        order = self.locked_list()
        if self.band is None or not (0 <= index < len(order)):
            return None
        old = order[index]
        rest = order[:index] + order[index + 1:]
        pool = self.pack.sprite_rank(self.band, locked=rest) if rest else \
            [(n, 0) for n in self.pack.adjacency.band_members(self.band)]
        cands = [n for n, _co in pool if n not in rest]
        if not cands:
            self.status = f"#{old}: no alternative recommended for the rest of the row"
            return None
        k = cands.index(old) if old in cands else -1
        repl = cands[(k + 1) % len(cands)]
        if repl == old:
            self.status = f"#{old}: only sprite that still fits the rest of the row"
            return None
        if index == 0:
            self.seed = repl
        else:
            self.kept[index - 1] = repl
        self.status = f"swapped #{old} -> #{repl}; the row re-ranked (butterfly)"
        return repl

    # ---- ranking / recompute (mode-gated, so a stale layer's ids never leak
    # into the other layer's suggestions) -----------------------------------

    def background_rank(self) -> list:
        if not self.pack or self.mode != "object":
            return []
        base = self.locked_list()
        return self.pack.background_rank(base) if base else []

    def sprite_rank(self) -> list:
        if not self.pack or self.mode != "sprite" or self.band is None:
            return []
        base = self.locked_list()
        return self.pack.sprite_rank(self.band, locked=base) if base else []

    def band_members(self) -> list:
        if not self.pack or not self.pack.adjacency.sprites_present or self.band is None:
            return []
        return self.pack.adjacency.band_members(self.band)

    def row_spec(self) -> list:
        """The clickable row's cells: the locked row (seed first), plus
        one '+' ghost carrying the engine's next pick when a candidate still
        fits the composed set."""
        cells = [{"node": n} for n in self.locked_list()]
        if self.mode == "sprite" and self.band is not None:
            cand = self.pack.sprite_rank(self.band, locked=self.locked_list())
            if cand:
                cells.append({"node": None, "add": cand[0][0]})
        return cells

    def shape_name(self, node) -> str:
        tiles = self.pack.adjacency.sp.get(node).tiles if self.pack else None
        return tiles[0].get("tile", "")[:6] if tiles else ""

    # ---- art / export (thin passthroughs to the Model) ---------------------

    def node_art(self, node, sprite=None):
        if sprite is None:
            sprite = self.mode == "sprite"
        return self.pack.node_art(node, sprite=sprite)

    def can_export(self) -> bool:
        return bool(self.locked_list())

    def preview_sheet(self, to_dir=None):
        """The composed sheet as `export` would write it, plus the name it would
        take in `to_dir`. Returns `(canvas, columns, unit, name)`, or None when
        nothing is composed yet - the View draws these very pixels, so what the
        artist approves is the file."""
        order = self.locked_list()
        if not self.pack or not order:
            return None
        canvas, _cells, columns, unit = self.pack.compose_sheet(self.mode, order)
        where = Path(to_dir) if to_dir else self.pack.sheets_dir
        name = self.pack.next_free_name(where) if where.is_dir() else "usr???"
        return canvas, columns, unit, name

    def export(self, to_dir) -> str:
        order = self.locked_list()
        if not order:
            raise E.ComposeError("nothing to export")
        if self.mode == "sprite":
            return self.pack.export("sprite", order, seed=self.seed, locked=self.kept,
                                    band=self.band, to_dir=Path(to_dir))
        return self.pack.export("object", order, seed=self.seed, locked=self.kept, to_dir=Path(to_dir))
