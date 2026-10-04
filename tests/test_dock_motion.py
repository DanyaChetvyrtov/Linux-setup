"""Guard against losing motion when restoring and reapplying dock settings."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("configure_dock", ROOT / "scripts/configure-dock.py")
dock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dock)


class DockMotionTests(unittest.TestCase):
    def test_restore_then_reapply_preserves_other_rules(self):
        config = (ROOT / "config/picom.conf").read_text()
        enabled = dock.with_motion(config)
        restored = dock.without_motion(enabled)
        self.assertEqual(dock.without_motion(config), restored)
        self.assertIn("_KALI_WORKSPACE_DIRECTION", restored)
        self.assertNotIn('triggers = ["position"]', restored)
        self.assertEqual(dock.with_motion(restored), enabled)
        self.assertEqual(dock.with_motion(enabled), enabled)
        self.assertEqual(enabled.count("# BEGIN kali-setup dock motion"), 1)

    def test_incomplete_or_unrecognized_configuration_is_rejected(self):
        for config in ("backend = \"glx\";", "rules = (\n  # BEGIN kali-setup dock motion\n);"):
            with self.subTest(config=config), self.assertRaises(ValueError):
                dock.with_motion(config)


if __name__ == "__main__":
    unittest.main()
