"""Verify that the viewer displays the commands SXHKD actually binds."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from tiling_shortcuts import bindings, description


class TilingShortcutTests(unittest.TestCase):
    def test_workspace_ranges_and_direction_pairs(self):
        commands = {b.shortcut: b.command for b in bindings()}
        self.assertEqual(commands["<Super>Left"], "bspc node -f west")
        self.assertEqual(commands["<Super><Shift>Right"], "bspc node -s east")
        self.assertEqual(commands["<Super><Shift>4"], "bspc node -d '^4' --follow")
        self.assertEqual(commands["<Alt>Tab"], "bspc node -f next.local.!hidden.window")
        self.assertEqual(commands["<Alt><Shift>Tab"], "bspc node -f prev.local.!hidden.window")

    def test_hotkeys_are_unique_and_every_command_has_a_description(self):
        current = bindings()
        self.assertEqual(len(current), len({b.shortcut for b in current}))
        for binding in current:
            with self.subTest(shortcut=binding.shortcut):
                self.assertTrue(description(binding.command))


if __name__ == "__main__":
    unittest.main()
