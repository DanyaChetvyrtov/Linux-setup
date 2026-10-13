#!/usr/bin/env python3
"""Enable persistent English and Russian keyboard layouts in the XFCE session."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import time

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/keyboard"
CHANNEL = "keyboard-layout"


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=10).stdout.strip()


def runtime_settings():
    return {key.strip(): value.strip() for key, _, value in
            (line.partition(":") for line in run("setxkbmap", "-query").splitlines())}


def get_property(path):
    result = subprocess.run(["xfconf-query", "-c", CHANNEL, "-p", path],
                            capture_output=True, text=True, timeout=10)
    if result.returncode:
        if "does not exist" in result.stdout + result.stderr:
            return None
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def set_property(path, kind, value):
    args = ["xfconf-query", "-c", CHANNEL, "-p", path]
    if get_property(path) is None:
        args += ["-n", "-t", kind]
    run(*(args + ["-s", str(value).lower() if kind == "bool" else str(value)]))


def expected_properties(settings):
    layouts, variants = settings["layouts"], settings["variants"]
    if layouts != ["us", "ru"] or len(variants) != len(layouts):
        raise ValueError("Expected the English and Russian layouts with matching variant entries.")
    for layout in layouts:
        if not Path("/usr/share/X11/xkb/symbols", layout).is_file():
            raise RuntimeError(f"The installed keyboard data lacks the {layout} layout.")
    return {
        "/Default/XkbLayout": ("string", ",".join(layouts)),
        "/Default/XkbVariant": ("string", ",".join(variants)),
        "/Default/XkbOptions/Group": ("string", settings["switch_option"]),
        "/Default/XkbDisable": ("bool", False),
    }


def restore(record):
    for path, item in record["properties"].items():
        if item["original"] is None:
            if get_property(path) is not None:
                run("xfconf-query", "-c", CHANNEL, "-p", path, "-r")
        else:
            set_property(path, item["kind"], item["original"])
    original = record["runtime"]
    args = ["setxkbmap", "-rules", original.get("rules", "evdev"),
            "-model", original.get("model", "pc105"), "-layout", original["layout"],
            "-variant", original.get("variant", ""), "-option", ""]
    if original.get("options"):
        args += ["-option", original["options"]]
    run(*args)
    # Retain any pre-existing custom key mappings as well as the layout names.
    run("xkbcomp", "-w", "0", record["keymap-backup"], os.environ["DISPLAY"])


def apply(settings, properties):
    original = runtime_settings()
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup = STATE / "backups" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    keymap = backup / "keyboard.xkb"
    run("xkbcomp", "-w", "0", "-xkb", os.environ["DISPLAY"], str(keymap))
    record = {"runtime": original, "keymap-backup": str(keymap), "properties": {}}
    for path, (kind, value) in properties.items():
        record["properties"][path] = {"kind": kind, "original": get_property(path), "applied": value}
    (backup / "restore.json").write_text(json.dumps(record, indent=2) + "\n")
    try:
        # Configure the native layouts before enabling XFCE's layout override.
        for path, (kind, value) in properties.items():
            set_property(path, kind, value)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            current = runtime_settings()
            if current.get("layout") == ",".join(settings["layouts"]) and settings["switch_option"] in current.get("options", "").split(","):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("XFCE did not apply the English/Russian layouts to the active keyboard.")
        for path, (kind, value) in properties.items():
            expected = str(value).lower() if kind == "bool" else str(value)
            if get_property(path) != expected:
                raise RuntimeError(f"The keyboard setting was not retained: {path}")
        other_options = [option for option in original.get("options", "").split(",")
                         if option and not option.startswith("grp:")]
        if not set(other_options).issubset(current.get("options", "").split(",")):
            raise RuntimeError("An unrelated keyboard option changed unexpectedly.")
    except Exception:
        restore(record)
        raise
    baseline = STATE / "restore.json"
    if not baseline.exists():
        baseline.write_text(json.dumps(record, indent=2) + "\n")
    (STATE / "last-apply.json").write_text(json.dumps(record, indent=2) + "\n")
    print("English and standard Russian keyboard layouts enabled now and at future XFCE logins.")
    print("Switch languages with Super+Space.")
    print("Keyboard backup:", backup)
    print("Restore: python3 scripts/configure-keyboard.py --restore")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if args.restore:
        baseline = STATE / "restore.json"
        restore(json.loads(baseline.read_text()))
        baseline.unlink()
        print("Restored the original keyboard layouts and switching options.")
        return
    settings = json.loads((REPO / "config/keyboard.json").read_text())
    properties = expected_properties(settings)
    if args.apply:
        apply(settings, properties)
    else:
        print("Preview: English + standard Russian; Super+Space switches the active layout.")
        print("Apply: python3 scripts/configure-keyboard.py --apply")


if __name__ == "__main__":
    main()
