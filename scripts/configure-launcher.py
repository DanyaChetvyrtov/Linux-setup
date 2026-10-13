#!/usr/bin/env python3
"""Center the existing Super-key applications menu in the XFCE session."""
import argparse
import datetime
import json
from pathlib import Path
import shlex
import shutil
import subprocess

from Xlib import display, error

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/launcher"
KEY = "/commands/custom/<Primary>Escape"
COMMAND = "xfce4-popup-whiskermenu --center"
MENU_RULE = "Wrapper-2.0:wrapper-2.0:Whisker Menu"


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=10).stdout.strip()


def current_command():
    return run("xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", KEY)


def set_command(value):
    run("xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", KEY, "-s", value)


def reset_menu_border():
    connection = display.Display()
    try:
        for window in connection.screen().root.query_tree().children:
            try:
                if window.get_wm_class() == ("wrapper-2.0", "Wrapper-2.0") and window.get_wm_name() == "Whisker Menu":
                    # A reused popup may retain the border added before its tiling exclusion.
                    window.configure(border_width=0)
            except error.BadWindow:
                continue
        connection.sync()
    finally:
        connection.close()


def apply():
    original = current_command()
    args = shlex.split(original)
    if not args or Path(args[0]).name != "xfce4-popup-whiskermenu":
        raise RuntimeError("The Super/Ctrl+Escape launcher binding changed; expected Whisker Menu.")
    if "--center" not in run("xfce4-popup-whiskermenu", "--help"):
        raise RuntimeError("This Whisker Menu version does not support centered popups.")
    # Apply only the popup rule to the live session; keep its layout settings intact.
    if (REPO / "state/tiling/ready").exists():
        local_bspc = REPO / "state/bin/bspc"
        bspc = str(local_bspc) if local_bspc.exists() else shutil.which("bspc")
        if not bspc:
            raise RuntimeError("The active tiling session's bspc command is unavailable.")
        subprocess.run([bspc, "rule", "-r", MENU_RULE], check=False, timeout=10)
        run(bspc, "rule", "-a", MENU_RULE, "state=floating", "focus=on", "border=off", "layer=above")
        reset_menu_border()
    if original == COMMAND:
        print("Super and Ctrl+Escape already open the applications menu at the screen center.")
        return
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup = STATE / "backups" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    record = {"property": KEY, "original": original, "applied": COMMAND}
    (backup / "restore.json").write_text(json.dumps(record, indent=2) + "\n")
    try:
        set_command(COMMAND)
        if current_command() != COMMAND:
            raise RuntimeError("The launcher shortcut did not retain the centered command.")
    except Exception:
        set_command(original)
        raise
    (STATE / "last-apply.json").write_text(json.dumps(record, indent=2) + "\n")
    print("Super and Ctrl+Escape now open the applications menu at the screen center.")
    print("Saved the previous shortcut command in", backup)


def restore():
    record = json.loads((STATE / "last-apply.json").read_text())
    if current_command() != record["applied"]:
        raise RuntimeError("The launcher shortcut changed after setup; refusing to overwrite it.")
    set_command(record["original"])
    print("Restored the previous application-menu shortcut position.")


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
        print("Preview: Super and Ctrl+Escape open Whisker Menu at the screen center.")
        print("BSPWM floats the menu above tiled windows and gives it keyboard focus.")
        print("Apply: python3 scripts/configure-launcher.py --apply")


if __name__ == "__main__":
    main()
