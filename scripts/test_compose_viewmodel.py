"""Headless suite for the composition editor's ViewModel (ADR-0165, F9.18).

`compose_editor.py`'s `EditorApp` (tkinter) cannot be driven headless — its
window is judged by the human Phase 9 panel. What *can* and must run here,
with no window, is the state machine the view draws: seed -> lock -> swap ->
unlock -> export, on both layers, exactly the gestures the human panel
exercises by hand. This suite runs a full functional composition through
`ComposeViewModel` alone, against the same synthetic fixture
`test_compose_engine.py` uses, so a regression in the gradeado's logic (the
click/swap/remove gesture set) is caught before a human ever opens the tool.

Run:  python3 scripts/test_compose_viewmodel.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compose_engine as E  # noqa: E402
from compose_viewmodel import ComposeViewModel  # noqa: E402
from test_compose_engine import make_pack, _OBJ000, mep_build_load  # noqa: E402

_FAILURES = []


def check(cond, name, detail=""):
    if cond:
        print(f"ok   {name}")
    else:
        print(f"FAIL {name}: {detail}")
        _FAILURES.append(name)


def test_load_reports_pack_summary_and_resets_state():
    with tempfile.TemporaryDirectory() as td:
        vm = ComposeViewModel()
        status = vm.load(make_pack(Path(td)))
        check("background nodes" in status, "load() returns a pack summary", status)
        check(vm.seed is None and vm.kept == [], "load() starts with an empty composition")
        check(vm.mode == "object", "load() defaults to the object layer")
        check(vm.band == max(vm.bands()), "load() defaults the band to the most common ground",
              f"{vm.band} vs {vm.bands()}")


def test_background_seed_lock_recompute_matches_engine_acceptance():
    """The full object-layer gesture set (F9.18 human panel item 1, step 3),
    driven only through the ViewModel — no tkinter, no window."""
    with tempfile.TemporaryDirectory() as td:
        vm = ComposeViewModel()
        vm.load(make_pack(Path(td)))
        check(vm.background_rank() == [], "no suggestions before a seed is set")
        seed = _OBJ000[0]
        vm.seed_object(seed)
        check(vm.locked_list() == [seed], "seeding sets the sole locked node", str(vm.locked_list()))
        ranked = vm.background_rank()
        check(bool(ranked), "seeding produces ranked neighbours")
        first = ranked[0][0]
        check(first in _OBJ000[1:], "top suggestion is inside the seed's obj000 group", f"got {first}")
        check(vm.lock(first, "object"), "locking the top suggestion succeeds")
        check(vm.locked_list() == [seed, first], "lock order is seed-first", str(vm.locked_list()))
        check(not vm.lock(first, "object"), "re-locking the same node is a no-op", "")
        ranked2 = vm.background_rank()
        rest = [m for m in _OBJ000 if m not in vm.locked_list()]
        decoys = [c for c, _ in ranked2 if c not in _OBJ000]
        rest_pos = [i for i, (c, _) in enumerate(ranked2) if c in rest]
        decoy_pos = [i for i, (c, _) in enumerate(ranked2) if c in decoys]
        check(rest and decoy_pos and max(rest_pos) < min(decoy_pos),
              "recompute still ranks the rest of the group before any decoy",
              f"rest {rest_pos} decoys {decoy_pos}")


def test_export_object_composition_is_legal_mep_build_input():
    """One full, functional object-layer composition, start to finish."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        vm = ComposeViewModel()
        vm.load(make_pack(root))
        seed = _OBJ000[0]
        vm.seed_object(seed)
        for node, _score in vm.background_rank()[:2]:
            vm.lock(node, "object")
        check(len(vm.locked_list()) == 3, "three cells locked (seed + two)", str(vm.locked_list()))
        out = root / "mep" / "textures" / "sheets"
        out.mkdir(parents=True)
        name = vm.export(out)
        doc_path = out / f"{name}.json"
        check(doc_path.is_file(), "export() writes a sidecar", str(doc_path))
        docs, _ = mep_build_load(out)
        check(len(docs) == 1 and docs[0].kind == "object", "mep_build loads the exported sheet as object",
              str([d.kind for d in docs]))


def test_sprite_band_gradeado_seed_lock_swap_unlock_reset():
    """The exact user-described gesture set: seed -> lock via + -> swap a
    locked cell (cycling, never a no-op bounce) -> unlock -> empty resets."""
    with tempfile.TemporaryDirectory() as td:
        vm = ComposeViewModel()
        vm.load(make_pack(Path(td)))
        band = 176
        vm.set_band(band)
        check(vm.mode == "sprite" and vm.band == band, "set_band switches to the sprite layer")
        check(vm.row_spec() == [], "an empty band shows no row yet")

        vm.seed_sprite(0)  # Ryu's own shape, per the fixture
        spec = vm.row_spec()
        check(spec and spec[0]["node"] == 0, "seeding puts the seed first in the row", str(spec))
        check(spec[-1]["node"] is None, "a '+' ghost follows the seed", str(spec))
        ghost = spec[-1]["add"]
        check(ghost in (1, 2), "the ghost proposes a ground enemy first", str(ghost))

        # Click the '+' -> a second lock.
        check(vm.lock(ghost, "sprite"), "clicking + locks the proposed node")
        row = vm.locked_list()
        check(row == [0, ghost], "locked order is seed then the newly locked cell", str(row))

        # Re-click the locked non-seed cell -> swap, cycling to a *different*
        # sprite (never bouncing back to the same occupant).
        before = vm.locked_list()[1]
        after = vm.swap_cell(1)
        check(after is not None and after != before, "swap_cell replaces the cell with a different sprite",
              f"{before} -> {after}")
        check(vm.locked_list()[1] == after, "the swapped node lands in the same slot", str(vm.locked_list()))
        check(vm.locked_list()[0] == 0, "the seed cell is untouched by swapping a different cell", "")

        # Swap the seed cell (index 0) too. In this fixture the seed (node 0)
        # is the only hub `pairs[]` gives any of the other shapes a nonzero
        # coFrames with, so there is genuinely no alternative for that slot —
        # swap_cell must recognise that and no-op safely rather than force a
        # bogus replacement.
        seed_before = vm.seed
        seed_after = vm.swap_cell(0)
        check(seed_after is None and vm.seed == seed_before,
              "swap_cell leaves the seed alone when no alternative fits its slot",
              f"{seed_before} -> {seed_after}")

        # Unlock the non-seed cell -> back to a lone seed.
        remaining = vm.kept[0]
        check(vm.unlock(remaining), "unlocking a non-seed cell succeeds")
        check(vm.locked_list() == [vm.seed], "one lock left: the seed", str(vm.locked_list()))

        # Unlock the seed -> the whole composition clears (per the user's
        # "se nenhum lock restar a imagem inteira eh removida").
        check(vm.unlock(vm.seed), "unlocking the seed succeeds")
        check(vm.seed is None and vm.kept == [], "removing the last lock clears the composition",
              f"seed={vm.seed} kept={vm.kept}")
        check(vm.row_spec() == [], "the gradeado is empty once the composition is cleared")


def test_swap_cell_out_of_range_or_no_alternative_is_a_safe_no_op():
    with tempfile.TemporaryDirectory() as td:
        vm = ComposeViewModel()
        vm.load(make_pack(Path(td)))
        vm.set_band(176)
        check(vm.swap_cell(0) is None, "swap on an empty row is a no-op, not a crash")
        vm.seed_sprite(0)
        check(vm.swap_cell(5) is None, "swap with an out-of-range index is a no-op")


def test_export_sprite_band_composition_is_legal_mep_build_input():
    """One full, functional sprite-band composition, start to finish — the
    same gesture set as the acceptance runbook's item 1, headless."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        vm = ComposeViewModel()
        vm.load(make_pack(root))
        vm.set_band(176)
        vm.seed_sprite(0)
        ghost = vm.row_spec()[-1]["add"]
        vm.lock(ghost, "sprite")
        check(len(vm.locked_list()) == 2, "band composition has two locked cells", str(vm.locked_list()))
        out = root / "mep" / "textures" / "sheets"
        out.mkdir(parents=True)
        name = vm.export(out)
        docs, _ = mep_build_load(out)
        check(len(docs) == 1 and docs[0].kind == "sprite", "mep_build loads the exported sheet as sprite",
              str([d.kind for d in docs]))
        import json
        doc = json.loads((out / f"{name}.json").read_text(encoding="utf-8"))
        check(doc["band"]["bottom"] == 176, "exported band matches the composed floor", str(doc.get("band")))
        check(doc["seed"] == 0 and doc["locked"] == vm.kept, "seed/locked carried from the ViewModel",
              str((doc["seed"], doc["locked"])))


def test_switching_layers_never_leaks_node_ids_into_the_other_suggestion_list():
    """A regression guard for the HUD-adjacent bug class found on real MM3
    packs: seeding one layer must not populate the other layer's ranked list
    with ids from a different node space."""
    with tempfile.TemporaryDirectory() as td:
        vm = ComposeViewModel()
        vm.load(make_pack(Path(td)))
        vm.set_band(176)
        vm.seed_sprite(0)
        check(vm.background_rank() == [], "seeding the sprite layer leaves background_rank empty",
              str(vm.background_rank()))
        vm.seed_object(_OBJ000[0])
        check(vm.sprite_rank() == [], "seeding the background layer leaves sprite_rank empty",
              str(vm.sprite_rank()))


def main():
    tests = [
        test_load_reports_pack_summary_and_resets_state,
        test_background_seed_lock_recompute_matches_engine_acceptance,
        test_export_object_composition_is_legal_mep_build_input,
        test_sprite_band_gradeado_seed_lock_swap_unlock_reset,
        test_swap_cell_out_of_range_or_no_alternative_is_a_safe_no_op,
        test_export_sprite_band_composition_is_legal_mep_build_input,
        test_switching_layers_never_leaks_node_ids_into_the_other_suggestion_list,
    ]
    for t in tests:
        t()
    print(f"\n{len(tests) - len(_FAILURES)}/{len(tests)} cases passed")
    return 1 if _FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
