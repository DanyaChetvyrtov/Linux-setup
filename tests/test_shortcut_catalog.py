"""Check shortcut metadata handling without a desktop session."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from shortcut_catalog import Binding, annotation_path, default_description, extract_bindings, read_annotation


class ShortcutCatalogTests(unittest.TestCase):
    def setUp(self):
        self.wallpaper = Binding("commands", "<Shift><Super>w", "/usr/bin/xfdesktop --next",
                                 "/commands/custom/<Shift><Super>w")

    def test_only_active_binding_entries_are_extracted(self):
        properties = {
            self.wallpaper.property: self.wallpaper.command,
            "/commands/custom/override": True,
            self.wallpaper.property + "/startup-notify": True,
            "/commands/custom/<Super>e/startup-notify": "metadata",
            "/commands/custom/<Super>e": "  ",
            "/commands/default/<Super>w": "exo-open --launch WebBrowser",
        }
        self.assertEqual(extract_bindings("commands", properties, "/commands/custom"), [self.wallpaper])

    def test_reassigned_hotkey_does_not_keep_old_description(self):
        saved = json.dumps({"command": self.wallpaper.command, "description": "Next background"})
        self.assertEqual(read_annotation(self.wallpaper, saved), "Next background")
        reassigned = Binding("commands", self.wallpaper.shortcut, "another-command", self.wallpaper.property)
        self.assertIsNone(read_annotation(reassigned, saved))

    def test_corrupt_annotations_fall_back(self):
        for encoded in (None, "not JSON", "null", "[]", "true", '{"description": "Old note"}',
                        json.dumps({"command": self.wallpaper.command, "description": 12}),
                        json.dumps({"command": self.wallpaper.command, "description": " "})):
            with self.subTest(encoded=encoded):
                self.assertIsNone(read_annotation(self.wallpaper, encoded))

    def test_same_hotkey_in_different_providers_has_separate_notes(self):
        window = Binding("xfwm4", self.wallpaper.shortcut, "close_window_key", "/xfwm4/custom/key")
        self.assertNotEqual(annotation_path(self.wallpaper), annotation_path(window))

    def test_descriptions_of_existing_actions(self):
        commands = {
            '"/usr/bin/exo-open" --launch "TerminalEmulator"': "Open a terminal",
            "/usr/share/kali-themes/xfce4-screenshooter --region --clipboard":
                "Capture a selected area to the clipboard",
            "exo-open --launch": "",
            "unknown-app --argument": "",
            "bad 'quote": "",
        }
        for command, description in commands.items():
            binding = Binding("commands", "key", command, "/commands/custom/key")
            with self.subTest(command=command):
                self.assertEqual(default_description(binding, {}), description)
        binding = Binding("xfwm4", "key", "move_window_workspace_10_key", "/xfwm4/custom/key")
        self.assertEqual(default_description(binding, {}), "Move the window to workspace 10")

    def test_repo_description_overrides_inferred_description(self):
        catalog = {"commands": {self.wallpaper.command: "Choose another wallpaper"}}
        self.assertEqual(default_description(self.wallpaper, catalog), "Choose another wallpaper")


if __name__ == "__main__":
    unittest.main()
