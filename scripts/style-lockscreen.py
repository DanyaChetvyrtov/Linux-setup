#!/usr/bin/env python3
"""Style the native XFCE lock-screen password panel, with CSS backup and rollback."""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/lockscreen"
GTK = Path.home() / ".config/gtk-3.0"
MAIN_CSS = GTK / "gtk.css"
LOCK_CSS = GTK / "kali-setup-lockscreen.css"
BEGIN = "/* BEGIN kali-setup lockscreen style */"
END = "/* END kali-setup lockscreen style */"
PATTERN = re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?"


def validate(css):
    spec = importlib.util.spec_from_file_location("panel_style", REPO / "scripts/style-panels.py")
    style = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(style)
    style.validate(css)


def managed_css(old, block=None):
    if old.count(BEGIN) != old.count(END) or old.count(BEGIN) > 1:
        raise ValueError("The lock screen's GTK import is incomplete or duplicated.")
    clean = re.sub(PATTERN, "", old, flags=re.S).rstrip("\n")
    if block is None:
        block = f'{BEGIN}\n@import url("{LOCK_CSS.as_uri()}");\n{END}\n'
    return clean + ("\n\n" if clean and block else "") + block + ("\n" if clean and not block else "")


def check_paths():
    for path in (MAIN_CSS, LOCK_CSS):
        if path.is_symlink():
            raise RuntimeError(f"Refusing to replace a symlink: {path}")


def restore_files(record, full_css=False):
    check_paths()
    for item in record["files"]:
        path = Path(item["path"])
        if path == MAIN_CSS and not full_css:
            # Retain the launcher, panels and any CSS added after this upgrade.
            current = path.read_text() if path.exists() else ""
            original = Path(item["backup"]).read_text() if item["existed"] else ""
            old_block = re.search(PATTERN, original, re.S)
            updated = managed_css(current, old_block.group() if old_block else "")
            if item["existed"] or updated.strip():
                path.write_text(updated)
            else:
                path.unlink(missing_ok=True)
        elif item["existed"]:
            shutil.copy2(item["backup"], path)
        else:
            path.unlink(missing_ok=True)


def apply(css):
    dialog = Path("/usr/libexec/xfce4-screensaver-dialog")
    resources = subprocess.run(["gresource", "list", str(dialog)],
                               check=True, capture_output=True, text=True, timeout=10).stdout
    if "/org/xfce/screensaver/xfce4-screensaver-dialog.ui" not in resources:
        raise RuntimeError("The expected native XFCE Screensaver dialog is unavailable.")
    check_paths()
    old = MAIN_CSS.read_text() if MAIN_CSS.exists() else ""
    updated = managed_css(old)
    if LOCK_CSS.exists() and LOCK_CSS.read_text() == css and updated == old:
        print("The modern lock-screen style is already installed.")
        return
    backup = STATE / "backups" / datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup.mkdir(parents=True, exist_ok=False)
    record = {"files": []}
    for path in (MAIN_CSS, LOCK_CSS):
        item = {"path": str(path), "existed": path.exists(), "backup": str(backup / path.name)}
        if item["existed"]:
            shutil.copy2(path, item["backup"])
        record["files"].append(item)
    (backup / "restore.json").write_text(json.dumps(record, indent=2) + "\n")
    try:
        GTK.mkdir(parents=True, exist_ok=True)
        LOCK_CSS.write_text(css)
        MAIN_CSS.write_text(updated)
        validate(updated)
        if LOCK_CSS.read_text() != css or MAIN_CSS.read_text() != updated:
            raise RuntimeError("The lock-screen stylesheet was not saved correctly.")
    except Exception:
        restore_files(record, full_css=True)
        raise
    baseline = STATE / "restore.json"
    if not baseline.exists():
        baseline.write_text(json.dumps(record, indent=2) + "\n")
    (STATE / "last-apply.json").write_text(json.dumps(record, indent=2) + "\n")
    print("Installed the modern lock-screen password panel for the next unlock dialog.")
    print("Appearance backup:", backup)
    print("Restore: python3 scripts/style-lockscreen.py --restore")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if args.restore:
        baseline = STATE / "restore.json"
        restore_files(json.loads(baseline.read_text()))
        baseline.unlink()
        print("Restored the lock-screen panel appearance from before the upgrade.")
        return
    css = (REPO / "config/lockscreen.css").read_text()
    validate(css)
    if args.apply:
        apply(css)
    else:
        print("GTK CSS validated: charcoal password panel, rounded edges and a green Unlock button.")
        print("Apply: python3 scripts/style-lockscreen.py --apply")


if __name__ == "__main__":
    main()
