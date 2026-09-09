"""Unit tests for the live viewer's host-free layout logic (ADR-0169).

No display: everything under test is arithmetic on sizes and formatting of
captions, which is exactly why it lives outside the tkinter class
(record_viewer_layout.py's docstring).

    python3 -m unittest scripts.test_record_viewer_layout -v
    python3 scripts/test_record_viewer_layout.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import record_viewer_layout as vl


def sprites(large=False, pattern=0x0000, clip=False, enabled=True):
    return {"largeSprites": large, "patternAddr": pattern,
            "leftColumnClip": clip, "spritesEnabled": enabled}


def background(pattern=0x1000, enabled=True, clip=False):
    return {"patternAddr": pattern, "enabled": enabled, "leftColumnClip": clip}


class RomIdentityTests(unittest.TestCase):
    """status.json's "rom" (ADR-0169: the slot is reused by every session, so
    the ROM is what tells one session from the next)."""

    def test_title_names_the_rom(self):
        self.assertEqual(vl.window_title("Castlevania.nes"),
                         vl.TITLE + " — Castlevania.nes")

    def test_title_without_a_rom_stays_plain(self):
        self.assertEqual(vl.window_title(""), vl.TITLE)
        self.assertEqual(vl.window_title(None), vl.TITLE)
        self.assertEqual(vl.window_title("   "), vl.TITLE)

    def test_rom_name_tolerates_a_missing_field(self):
        self.assertEqual(vl.rom_name({}), "")
        self.assertEqual(vl.rom_name(None), "")
        self.assertEqual(vl.rom_name({"rom": None}), "")
        self.assertEqual(vl.rom_name({"rom": " Zelda.nes "}), "Zelda.nes")

    def test_run_state_names_the_rom_when_the_run_publishes_one(self):
        self.assertEqual(
            vl.format_run_state({"frame": 120, "elapsedWallSec": 30.0, "rom": "Metroid.nes"}),
            "Metroid.nes · frame 120 live · wall 30.0s")

    def test_run_state_without_a_rom_is_unchanged(self):
        self.assertEqual(vl.format_run_state({"frame": 120, "elapsedWallSec": 30.0}),
                         "frame 120 live · wall 30.0s")


class OrientationTests(unittest.TestCase):
    def test_explicit_modes_ignore_the_window(self):
        self.assertEqual(vl.pick_orientation(vl.LAYOUT_SIDE, 400, 900), vl.ORIENT_HORIZONTAL)
        self.assertEqual(vl.pick_orientation(vl.LAYOUT_STACK, 1900, 400), vl.ORIENT_VERTICAL)

    def test_auto_splits_a_wide_window_and_stacks_a_tall_one(self):
        self.assertEqual(vl.pick_orientation(vl.LAYOUT_AUTO, 1400, 800), vl.ORIENT_HORIZONTAL)
        self.assertEqual(vl.pick_orientation(vl.LAYOUT_AUTO, 700, 900), vl.ORIENT_VERTICAL)

    def test_auto_picks_the_split_that_draws_the_frame_larger(self):
        # 1100x780 (the default window): side by side fits 2x, stacked only 1x.
        self.assertEqual(vl.pick_orientation(vl.LAYOUT_AUTO, 1100, 780), vl.ORIENT_HORIZONTAL)

    def test_auto_stacks_a_square_window(self):
        # Two frames side by side in a square window are each half as wide as
        # they are tall - stacking gives both more room.
        self.assertEqual(vl.pick_orientation(vl.LAYOUT_AUTO, 800, 800), vl.ORIENT_VERTICAL)

    def test_auto_stacks_when_half_the_window_cannot_hold_a_pane(self):
        # 700 wide: each side-by-side pane would be 350px, under MIN_PANE_W,
        # even though the frame arithmetic alone is a tie at 1x.
        self.assertEqual(vl.pick_orientation(vl.LAYOUT_AUTO, 700, 520), vl.ORIENT_VERTICAL)
        self.assertEqual(vl.pick_orientation(vl.LAYOUT_AUTO, 2 * vl.MIN_PANE_W, 520),
                         vl.ORIENT_HORIZONTAL)

    def test_auto_before_the_window_is_mapped(self):
        self.assertEqual(vl.pick_orientation(vl.LAYOUT_AUTO, 0, 0), vl.ORIENT_HORIZONTAL)

    def test_every_label_maps_back_to_a_mode(self):
        modes = [mode for mode, _label in vl.LAYOUT_LABELS]
        self.assertEqual(modes, [vl.LAYOUT_AUTO, vl.LAYOUT_SIDE, vl.LAYOUT_STACK])
        self.assertEqual(len(set(label for _m, label in vl.LAYOUT_LABELS)), 3)


class ZoomTests(unittest.TestCase):
    def test_fit_is_the_largest_integer_that_still_fits(self):
        self.assertEqual(vl.fit_zoom(256, 240, 800, 700), 2)
        self.assertEqual(vl.fit_zoom(256, 240, 1100, 760), 3)

    def test_fit_is_bounded_by_the_tighter_axis(self):
        # Wide but short: height decides.
        self.assertEqual(vl.fit_zoom(256, 240, 2000, 500), 2)

    def test_fit_never_goes_below_one_or_past_the_cap(self):
        self.assertEqual(vl.fit_zoom(256, 240, 100, 100), vl.MIN_ZOOM)
        self.assertEqual(vl.fit_zoom(256, 240, 100000, 100000), vl.MAX_ZOOM)

    def test_fit_on_an_unmapped_pane(self):
        self.assertEqual(vl.fit_zoom(256, 240, 0, 0), vl.MIN_ZOOM)
        self.assertEqual(vl.fit_zoom(0, 0, 800, 800), vl.MIN_ZOOM)

    def test_fit_accounts_for_a_recorder_scaled_frame(self):
        # A 2x recording (512x480) fits half as many times as a native one.
        self.assertEqual(vl.fit_zoom(512, 480, 1100, 1000), 2)

    def test_clamp_zoom(self):
        self.assertEqual(vl.clamp_zoom(0), vl.MIN_ZOOM)
        self.assertEqual(vl.clamp_zoom(99), vl.MAX_ZOOM)
        self.assertEqual(vl.clamp_zoom("3"), 3)
        self.assertEqual(vl.clamp_zoom(""), vl.MIN_ZOOM)      # a Spinbox can be empty
        self.assertEqual(vl.clamp_zoom(None), vl.MIN_ZOOM)

    def test_resolve_zoom_follows_the_fit_checkbox(self):
        self.assertEqual(vl.resolve_zoom(True, 7, 256, 240, 800, 700), 2)
        self.assertEqual(vl.resolve_zoom(False, 7, 256, 240, 800, 700), 7)

    def test_shared_available_is_the_smaller_pane(self):
        self.assertEqual(vl.shared_available([(800, 600), (700, 650)]), (700, 600))

    def test_shared_available_ignores_unmapped_panes(self):
        self.assertEqual(vl.shared_available([(800, 600), (0, 0)]), (800, 600))
        self.assertEqual(vl.shared_available([(0, 0), (0, 0)]), (0, 0))


class StatusTests(unittest.TestCase):
    def test_interactive_run_reads_live(self):
        text = vl.format_run_state({"frame": 26509, "elapsedWallSec": 441.0})
        self.assertEqual(text, "frame 26509 live · wall 441.0s")

    def test_scripted_run_names_its_target(self):
        text = vl.format_run_state({"frame": 100, "targetFrames": 600, "elapsedWallSec": 3.5})
        self.assertIn("of 600", text)

    def test_stopped_run(self):
        self.assertIn("stopped", vl.format_run_state({"frame": 12, "done": True, "elapsedWallSec": 1}))

    def test_badges(self):
        self.assertEqual(vl.run_badge({"frame": 1}), "REC")
        self.assertEqual(vl.run_badge({"frame": 1, "done": True}), "STOPPED")
        self.assertEqual(vl.run_badge({}), "IDLE")
        self.assertEqual(vl.run_badge(None), "IDLE")

    def test_notices_are_empty_for_an_unremarkable_run(self):
        self.assertEqual(vl.format_notices({"frame": 1}, sprites()), [])

    def test_notices_name_hd_pack_and_disabled_sprites(self):
        out = vl.format_notices({"hdPackActive": True}, sprites(enabled=False))
        self.assertEqual(len(out), 2)
        self.assertIn("HD pack ON", out[0])
        self.assertIn("sprites off", out[1])

    def test_waiting_text_names_the_watched_dir(self):
        self.assertIn("/tmp/run-live", vl.waiting_text("/tmp/run-live"))


class MetaTests(unittest.TestCase):
    def test_composite_meta_hides_a_1x_view(self):
        self.assertEqual(vl.format_composite_meta(512, 480, 2, 1), "512×480 · 2× native")

    def test_composite_meta_shows_the_view_zoom(self):
        self.assertEqual(vl.format_composite_meta(256, 240, 1, 3),
                         "256×240 · 1× native · view 3×")

    def test_composite_meta_survives_an_odd_geometry(self):
        # geometry_scale() returns None for a non-multiple capture.
        self.assertIn("1× native", vl.format_composite_meta(300, 240, None, 1))

    def test_reconstruction_meta_reports_the_ppu_bits(self):
        text = vl.format_reconstruction_meta(sprites(large=True, pattern=0x0000),
                                             background(pattern=0x1000))
        self.assertEqual(text, "8×16 · sprite $0000 · bg $1000")

    def test_reconstruction_meta_flags_clip_and_bg_off(self):
        text = vl.format_reconstruction_meta(sprites(clip=True),
                                             background(enabled=False, clip=True))
        self.assertEqual(
            text, "8×8 · sprite $0000 · bg $1000 · bg off this frame · bg left clip · sprite left clip")

    def test_reconstruction_meta_without_a_background_layer(self):
        self.assertEqual(vl.format_reconstruction_meta(sprites(), None),
                         "8×8 · sprite $0000")

    def test_reconstruction_meta_without_a_sprite_layer(self):
        self.assertEqual(vl.format_reconstruction_meta(None, None), "")


class NoteTests(unittest.TestCase):
    def test_full_note_when_both_layers_are_on_the_wire(self):
        self.assertEqual(vl.reconstruction_note(True, True, False), vl.RECONSTRUCTION_NOTE)

    def test_old_recording_gets_the_sprites_only_note(self):
        self.assertEqual(vl.reconstruction_note(True, False, False), vl.SPRITES_ONLY_NOTE)

    def test_hd_pack_note_replaces_the_usual_one(self):
        self.assertEqual(vl.reconstruction_note(True, True, True), vl.HD_PACK_NOTE)
        self.assertEqual(vl.reconstruction_note(True, False, True), vl.HD_PACK_NOTE)

    def test_no_sprite_layer_wins_over_everything(self):
        self.assertEqual(vl.reconstruction_note(False, False, True), vl.NO_SPRITE_LAYER_NOTE)

    def test_notes_are_layout_neutral(self):
        # The panes can sit side by side, so no note may say "above"/"below".
        for note in (vl.RECONSTRUCTION_NOTE, vl.SPRITES_ONLY_NOTE, vl.HD_PACK_NOTE):
            self.assertNotIn("above", note)
            self.assertNotIn("below", note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
