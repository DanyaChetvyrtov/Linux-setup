#!/usr/bin/env python3
"""Persist touchpad scroll direction and install a user-session gesture autostart."""
import argparse
import datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import importlib.util

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/input"
BINARY = REPO / "state/bin/workspace-gestures"
AUTOSTART = Path.home() / ".config/autostart/kali-workspace-gestures.desktop"


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def build():
    BINARY.parent.mkdir(parents=True, exist_ok=True)
    temporary = BINARY.with_suffix(".new")
    run("gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", str(REPO / "src/workspace-gestures.c"),
        "-lXi", "-lX11", "-lm", "-o", str(temporary))
    temporary.replace(BINARY)
    print(run(str(BINARY), "--self-test"))


def pointer_path(name):
    # Match XFCE's device normalization: spaces become underscores;
    # unsupported punctuation is removed.
    device = re.sub(r"[^A-Za-z0-9_-]", "", name.replace(" ", "_"))
    return f"/{device}/Properties/libinput_Natural_Scrolling_Enabled"


def set_scroll(path, value):
    args = ["xfconf-query", "-c", "pointers", "-p", path]
    exists = subprocess.run(args, capture_output=True).returncode == 0
    run(*(args + ([] if exists else ["-n", "-t", "int"]) + ["-s", str(int(value))]))


def listener():
    spec = importlib.util.spec_from_file_location("gesture_start", REPO / "scripts/start-gestures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def restore(record):
    listener().stop_listener()
    if record["autostart-existed"]:
        shutil.copy2(record["autostart-backup"], AUTOSTART)
    else:
        AUTOSTART.unlink(missing_ok=True)
    if record["scroll-persisted"] is not None:
        set_scroll(record["scroll-path"], record["scroll-persisted"])
    else:
        # Apply the former runtime value before clearing the new persistent key.
        set_scroll(record["scroll-path"], record["scroll-runtime"])
        run("xfconf-query", "-c", "pointers", "-p", record["scroll-path"], "-r")


def apply(settings):
    devices = json.loads(run(str(BINARY), "--inspect"))
    device = next(d for d in devices if d["name"] == settings["device"])
    if device["natural_scrolling"] not in [0, 1]:
        raise RuntimeError("Touchpad scroll property unavailable.")
    path = pointer_path(device["name"])
    previous = subprocess.run(["xfconf-query", "-c", "pointers", "-p", path], capture_output=True, text=True)
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup = STATE / "backups" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    record = {"scroll-path": path, "scroll-runtime": device["natural_scrolling"],
              "scroll-persisted": int(previous.stdout.strip()) if previous.returncode == 0 else None,
              "autostart-existed": AUTOSTART.exists(), "autostart-backup": str(backup / AUTOSTART.name)}
    if AUTOSTART.is_symlink():
        raise RuntimeError("Refusing to replace a symlink autostart entry.")
    if AUTOSTART.exists():
        shutil.copy2(AUTOSTART, record["autostart-backup"])
    (backup / "restore.json").write_text(json.dumps(record, indent=2) + "\n")
    try:
        set_scroll(path, settings["natural_scrolling"])
        time.sleep(0.3)
        after = next(d for d in json.loads(run(str(BINARY), "--inspect")) if d["name"] == device["name"])
        if after["natural_scrolling"] != int(settings["natural_scrolling"]):
            raise RuntimeError("XFCE did not apply the runtime scroll direction.")
        # Check the gesture registration before creating the autostart entry.
        listener().stop_listener()
        print(run(str(BINARY), "--probe", "--device", settings["device"],
                  "--fingers", str(settings["fingers"]), "--threshold", str(settings["threshold"])))
        AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
        script = str(REPO / "scripts/start-gestures.py").replace("\\", "\\\\").replace('"', '\\"')
        AUTOSTART.write_text('[Desktop Entry]\nType=Application\nName=Four-finger workspace gestures\n'
                             f'Exec=/usr/bin/python3 "{script}"\nOnlyShowIn=XFCE;\nTerminal=false\n')
        listener().start()
    except Exception:
        restore(record)
        raise
    (STATE / "last-apply.json").write_text(json.dumps(record, indent=2) + "\n")
    print("Touchpad scroll direction applied and verified; gesture autostart enabled.")
    print("Restore: python3 scripts/configure-input.py --restore")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if args.restore:
        restore(json.loads((STATE / "last-apply.json").read_text()))
        print("Restored the previous scroll setting and removed the gesture listener.")
        return
    settings = json.loads((REPO / "config/input.json").read_text())
    build()
    if args.apply:
        apply(settings)
    else:
        print("Preview: natural scrolling enabled; four-finger left -> next, right -> previous.")
        print("No system packages or raw input permissions required. Use --apply in your X11 session.")


if __name__ == "__main__":
    main()
