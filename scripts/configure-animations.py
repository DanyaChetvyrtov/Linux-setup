#!/usr/bin/env python3
"""Enable short Picom workspace slides with backed-up user-session settings."""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/compositor"
AUTOSTART = Path.home() / ".config/autostart/kali-workspace-animations.desktop"


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "scripts" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def restore(record):
    module("start-compositor").stop()
    if record["autostart-existed"]:
        shutil.copy2(record["autostart-backup"], AUTOSTART)
    else:
        AUTOSTART.unlink(missing_ok=True)
    if record["enabled"]:
        (STATE / "enabled").touch()
        module("start-compositor").start()
    else:
        (STATE / "enabled").unlink(missing_ok=True)
        module("start-compositor").compositing(record["xfwm-compositing"])
    module("start-gestures").start()


def apply():
    if not shutil.which("picom"):
        raise RuntimeError("Install the desktop package profile first: bash scripts/install-packages.sh --apply desktop")
    version = run("picom", "--version")
    match = re.search(r"v?(\d+)", version)
    if not match or int(match[1]) < 13:
        raise RuntimeError(f"Picom 13 or newer required; found {version}.")
    if not (REPO / "state/input/last-apply.json").exists():
        raise RuntimeError("Apply configure-input.py first to enable the workspace gesture listener.")
    if AUTOSTART.is_symlink():
        raise RuntimeError("Refusing to replace a symlink autostart entry.")
    # Rebuild the listener before changing any session configuration.
    module("configure-input").build()
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup = STATE / "backups" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    record = {"xfwm-compositing": run("xfconf-query", "-c", "xfwm4", "-p", "/general/use_compositing") == "true",
              "enabled": (STATE / "enabled").exists(), "autostart-existed": AUTOSTART.exists(),
              "autostart-backup": str(backup / AUTOSTART.name)}
    if AUTOSTART.exists():
        shutil.copy2(AUTOSTART, record["autostart-backup"])
    (backup / "restore.json").write_text(json.dumps(record, indent=2) + "\n")
    try:
        script = str(REPO / "scripts/start-compositor.py").replace("\\", "\\\\").replace('"', '\\"')
        AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART.write_text('[Desktop Entry]\nType=Application\nName=Workspace animations\n'
                             f'Exec=/usr/bin/python3 "{script}"\nOnlyShowIn=XFCE;\nTerminal=false\n')
        (STATE / "enabled").touch()
        module("start-compositor").start()
        module("start-gestures").start()
    except Exception:
        restore(record)
        raise
    (STATE / "last-apply.json").write_text(json.dumps(record, indent=2) + "\n")
    print("Workspace slides enabled: 180 ms, eased, four-finger gesture directions retained.")
    print("Restore: python3 scripts/configure-animations.py --restore")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if args.apply:
        apply()
    elif args.restore:
        restore(json.loads((STATE / "last-apply.json").read_text()))
        print("Restored the compositor configuration from before the last apply.")
    else:
        print("Preview: Picom 13+, GLX/vsync, 180 ms workspace slides after four-finger swipes.")
        print("Apply: install the desktop package profile, then run this script with --apply.")
        print("Keeps XFWM, backs up user settings, restores XFWM compositing if Picom exits.")


if __name__ == "__main__":
    main()
