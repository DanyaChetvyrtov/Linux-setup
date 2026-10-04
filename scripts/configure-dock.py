#!/usr/bin/env python3
"""Apply hover magnification and smooth motion to the existing XFCE dock."""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/dock"
MOTION_PATTERN = r",\n  # BEGIN kali-setup dock motion\n.*?\n  # END kali-setup dock motion"


def without_motion(config):
    return re.sub(MOTION_PATTERN, "", config, flags=re.S)


def with_motion(config):
    clean = without_motion(config)
    if "# BEGIN kali-setup dock motion" in clean or "# END kali-setup dock motion" in clean:
        raise ValueError("The dock motion block is incomplete; inspect config/picom.conf.")
    if "rules = (" not in clean:
        raise ValueError("Expected the repository's Picom window rules.")
    end = clean.rfind("\n);")
    if end < clean.index("rules = ("):
        raise ValueError("Could not find the end of the Picom window rules.")
    rule = (REPO / "config/dock-motion.conf").read_text().rstrip("\n")
    block = ",\n  # BEGIN kali-setup dock motion\n" + rule + "\n  # END kali-setup dock motion"
    return clean[:end] + block + clean[end:]


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "scripts" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def restore(record):
    style = module("style-panels")
    style.restore_files(record["style"])
    # Restore only the properties this script changes, preserving later app pins.
    for path, value in record["properties"].items():
        if value is None:
            subprocess.run(["xfconf-query", "-c", "xfce4-panel", "-p", path, "-r"], check=True)
        else:
            style.set_property(path, "uint", value)
    shutil.copy2(record["picom-backup"], REPO / "config/picom.conf")
    style.run("xfce4-panel", "--restart")
    if record["picom-active"]:
        module("start-compositor").start()


def apply():
    style = module("style-panels")
    layout = json.loads((REPO / "state/panels/last-apply.json").read_text())
    spec = json.loads((REPO / "config/panels.json").read_text())
    css = style.render(layout["top"], layout["bottom"])
    style.validate(css)
    picom_current = (REPO / "config/picom.conf").read_text()
    picom_updated = with_motion(picom_current)
    found = style.run("xfconf-query", "-c", "xfce4-panel", "-p", "/panels")
    if [int(x) for x in found.splitlines() if x.isdigit()] != [layout["top"], layout["bottom"]]:
        raise RuntimeError("The panel layout changed since setup; inspect it before applying.")
    picom_active = module("start-compositor").owned_pid() is not None
    if not picom_active:
        raise RuntimeError("The supervised Picom compositor must be running for smooth dock motion.")
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup = STATE / "backups" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    style_backup = {"files": []}
    for path in (style.MAIN_CSS, style.PANEL_CSS):
        if path.is_symlink():
            raise RuntimeError("Refusing to replace a symlink: " + str(path))
        item = {"path": str(path), "existed": path.exists(), "backup": str(backup / path.name)}
        if path.exists():
            shutil.copy2(path, item["backup"])
        style_backup["files"].append(item)
    properties = {}
    for name in ("size", "popdown-speed"):
        path = f"/panels/panel-{layout['bottom']}/{name}"
        query = subprocess.run(["xfconf-query", "-c", "xfce4-panel", "-p", path], capture_output=True, text=True)
        properties[path] = int(query.stdout.strip()) if query.returncode == 0 else None
    # Picom reads the repository file directly. On the first apply, rollback
    # removes just our new dock rule; other compositor settings stay intact.
    previous = STATE / "last-apply.json"
    picom_backup = backup / "picom.conf"
    if previous.exists():
        shutil.copy2(REPO / "config/picom.conf", picom_backup)
    else:
        picom_backup.write_text(without_motion(picom_current))
    record = {"style": style_backup, "properties": properties, "picom-backup": str(picom_backup),
              "picom-active": picom_active}
    (backup / "restore.json").write_text(json.dumps(record, indent=2) + "\n")
    try:
        (REPO / "config/picom.conf").write_text(picom_updated)
        for name in ("size", "popdown-speed"):
            style.set_property(f"/panels/panel-{layout['bottom']}/{name}", "uint", spec["bottom"][name])
        style.apply(css, layout["top"], layout["bottom"])
        module("start-compositor").start()
    except Exception:
        restore(record)
        raise
    previous.write_text(json.dumps(record, indent=2) + "\n")
    print("Dock enabled: 30% hover magnification, 180 ms icon easing, 220 ms motion.")
    print("Backup:", backup)
    print("Restore: python3 scripts/configure-dock.py --restore")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if args.restore:
        restore(json.loads((STATE / "last-apply.json").read_text()))
        print("Restored dock size, motion, and panel appearance.")
    elif args.apply:
        apply()
    else:
        print("Preview: existing XFCE dock, 40px icons enlarging to 52px on hover.")
        print("64px panel, short eased icon and hide/show transitions; intelligent hiding retained.")
        print("Apply: python3 scripts/configure-dock.py --apply")


if __name__ == "__main__":
    main()
