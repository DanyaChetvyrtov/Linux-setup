"""Check spacing and recognition across odd screen sizes and terminal hints."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

from Xlib import Xutil
from Xlib.protocol.rq import DictWrapper

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from window_gaps import Rect, matches, size_hints, tiles


class WindowGapTests(unittest.TestCase):
    def test_adjacent_halves_have_exact_gap_and_keep_outer_edges(self):
        for area in (Rect(0, 29, 1920, 1051), Rect(-1921, 40, 1921, 1039)):
            for gap in (0, 11, 12, 25):
                with self.subTest(area=area, gap=gap):
                    layout = tiles(area, gap)
                    left, right = layout["left"], layout["right"]
                    self.assertEqual(right.x - (left.x + left.width), gap)
                    self.assertEqual(left.x, area.x)
                    self.assertEqual(right.x + right.width, area.x + area.width)
                    up, down = layout["up"], layout["down"]
                    self.assertEqual(down.y - (up.y + up.height), gap)
                    self.assertEqual(up.y, area.y)
                    self.assertEqual(down.y + down.height, area.y + area.height)

    def test_quarters_have_the_same_horizontal_and_vertical_gap(self):
        layout = tiles(Rect(0, 29, 1920, 1051), 12)
        a, b, c = layout["up-left"], layout["up-right"], layout["down-left"]
        self.assertEqual(b.x - a.x - a.width, 12)
        self.assertEqual(c.y - a.y - a.height, 12)

    def test_floating_maximized_and_already_gapped_windows_are_not_native_tiles(self):
        area = Rect(0, 29, 1920, 1051)
        native = tiles(area).values()
        for rect in (area, Rect(60, 60, 900, 1000), tiles(area, 12)["left"]):
            self.assertFalse(any(matches(rect, tile) for tile in native))

    def test_terminal_size_rounding_is_bounded_by_cell_size(self):
        native = Rect(0, 29, 960, 1051)
        self.assertTrue(matches(Rect(0, 29, 955, 1040), native, (9, 18)))
        self.assertFalse(matches(Rect(0, 29, 945, 1040), native, (9, 18)))
        self.assertFalse(matches(Rect(10, 29, 955, 1040), native, (9, 18)))

    def test_xlib_hint_wrapper_and_validity_flags(self):
        hints = DictWrapper({"flags": Xutil.PMinSize, "min_width": 470, "min_height": 522,
                             "width_inc": 0, "height_inc": 0})
        window = SimpleNamespace(get_wm_normal_hints=lambda: hints)
        self.assertEqual(size_hints(window), {"min_width": 470, "min_height": 522,
                                             "width_inc": 1, "height_inc": 1})


if __name__ == "__main__":
    unittest.main()
