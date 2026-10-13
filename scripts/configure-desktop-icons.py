#!/usr/bin/env python3
"""Hide XFCE desktop icons while retaining the wallpaper, panels, and applications."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/desktop-icons"
PROPERTY = "/desktop-icons/style"


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=10).stdout.strip()


def current_style():
    return int(run("xfconf-query", "-c", "xfce4-desktop", "-p", PROPERTY))


def set_style(value):
    run("xfconf-query", "-c", "xfce4-desktop", "-p", PROPERTY, "-s", str(value))


def apply():
    original = current_style()
    if original == 0:
        print("Desktop icons are already hidden.")
        return
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup = STATE / "backups" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    record = {"property": PROPERTY, "original": original, "applied": 0}
    (backup / "restore.json").write_text(json.dumps(record, indent=2) + "\n")
    try:
        set_style(0)
        if current_style() != 0:
            raise RuntimeError("XFCE did not retain the desktop icon setting.")
    except Exception:
        set_style(original)
        raise
    (STATE / "last-apply.json").write_text(json.dumps(record, indent=2) + "\n")
    print("Desktop icons hidden now and at future logins.")
    print("Applications remain available through the Super-key menu and dock.")
    print("Saved the previous icon setting in", backup)


def restore():
    record = json.loads((STATE / "last-apply.json").read_text())
    if current_style() != record["applied"]:
        raise RuntimeError("Desktop icon settings changed after setup; refusing to overwrite them.")
    set_style(record["original"])
    print("Restored the previous desktop icon setting.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if args.apply:
        apply()
    elif args.restore:
        restore()
    else:
        print("Preview: hide all desktop icons and keep the wallpaper visible.")
        print("Apply: python3 scripts/configure-desktop-icons.py --apply")


if __name__ == "__main__":
    main()
