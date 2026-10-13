#!/usr/bin/env python3
"""Apply the modern Whisker Menu appearance with settings and CSS rollback."""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/launcher"
GTK = Path.home() / ".config/gtk-3.0"
MAIN_CSS = GTK / "gtk.css"
LAUNCHER_CSS = GTK / "kali-setup-launcher.css"
BEGIN = "/* BEGIN kali-setup launcher style */"
END = "/* END kali-setup launcher style */"
PATTERN = re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?"


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=15).stdout.strip()


def validate(css):
    spec = importlib.util.spec_from_file_location("panel_style", REPO / "scripts/style-panels.py")
    style = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(style)
    style.validate(css)


def managed_css(old, block=None):
    if old.count(BEGIN) != old.count(END) or old.count(BEGIN) > 1:
        raise ValueError("The launcher's managed GTK import is incomplete or duplicated.")
    clean = re.sub(PATTERN, "", old, flags=re.S).rstrip("\n")
    if block is None:
        block = f'{BEGIN}\n@import url("{LAUNCHER_CSS.as_uri()}");\n{END}\n'
    return clean + ("\n\n" if clean and block else "") + block + ("\n" if clean and not block else "")


def plugin_base():
    properties = run("xfconf-query", "-c", "xfce4-panel", "-l").splitlines()
    found = [path for path in properties if re.fullmatch(r"/plugins/plugin-\d+", path)
             and run("xfconf-query", "-c", "xfce4-panel", "-p", path) == "whiskermenu"]
    if len(found) != 1:
        raise RuntimeError("Expected one Whisker Menu plugin in this session.")
    return found[0]


def get_property(path):
    query = subprocess.run(["xfconf-query", "-c", "xfce4-panel", "-p", path],
                           capture_output=True, text=True, timeout=10)
    if query.returncode:
        if "does not exist" in query.stderr + query.stdout:
            return None
        raise RuntimeError(query.stderr.strip())
    return query.stdout.strip()


def set_property(path, kind, value):
    args = ["xfconf-query", "-c", "xfce4-panel", "-p", path]
    if get_property(path) is None:
        args += ["-n", "-t", kind]
    run(*(args + ["-s", str(value).lower() if kind == "bool" else str(value)]))


def panel_structure():
    panels = [line for line in run("xfconf-query", "-c", "xfce4-panel", "-p", "/panels").splitlines()
              if line.isdigit()]
    names = ("position", "size", "length", "length-adjust", "autohide-behavior", "plugin-ids")
    return {f"/panels/panel-{panel}/{name}": get_property(f"/panels/panel-{panel}/{name}")
            for panel in panels for name in names}


def restore_record(record, full_css=False):
    if run("xfconf-query", "-c", "xfce4-panel", "-p", record["plugin"]) != "whiskermenu":
        raise RuntimeError("The saved launcher plugin no longer exists.")
    for item in record["files"]:
        path = Path(item["path"])
        if path.is_symlink():
            raise RuntimeError(f"Refusing to replace a symlink: {path}")
        if path == MAIN_CSS and not full_css:
            # Keep panel styling and any user CSS added after the launcher upgrade.
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
    for path, item in record["properties"].items():
        if item["original"] is None:
            if get_property(path) is not None:
                run("xfconf-query", "-c", "xfce4-panel", "-p", path, "-r")
        else:
            set_property(path, item["kind"], item["original"])
    run("xfce4-panel", "--restart")
    time.sleep(2)


def apply(css, settings):
    base = plugin_base()
    before = panel_structure()
    favorites = get_property(base + "/favorites")
    command = run("xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", "/commands/custom/<Primary>Escape")
    for path in (MAIN_CSS, LAUNCHER_CSS):
        if path.is_symlink():
            raise RuntimeError(f"Refusing to replace a symlink: {path}")
    old_css = MAIN_CSS.read_text() if MAIN_CSS.exists() else ""
    updated_css = managed_css(old_css)
    backup = STATE / "style-backups" / datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup.mkdir(parents=True, exist_ok=False)
    record = {"plugin": base, "files": [], "properties": {}}
    for path in (MAIN_CSS, LAUNCHER_CSS):
        item = {"path": str(path), "existed": path.exists(), "backup": str(backup / path.name)}
        if item["existed"]:
            shutil.copy2(path, item["backup"])
        record["files"].append(item)
    for name, value in settings.items():
        path = base + "/" + name
        record["properties"][path] = {"kind": "bool" if isinstance(value, bool) else "int",
                                      "original": get_property(path), "applied": value}
    (backup / "restore.json").write_text(json.dumps(record, indent=2) + "\n")
    try:
        GTK.mkdir(parents=True, exist_ok=True)
        LAUNCHER_CSS.write_text(css)
        MAIN_CSS.write_text(updated_css)
        validate(updated_css)
        for path, item in record["properties"].items():
            set_property(path, item["kind"], item["applied"])
        run("xfce4-panel", "--restart")
        time.sleep(2)
        for path, item in record["properties"].items():
            expected = str(item["applied"]).lower() if item["kind"] == "bool" else str(item["applied"])
            if get_property(path) != expected:
                raise RuntimeError(f"Launcher setting was not retained: {path}")
        if panel_structure() != before or get_property(base + "/favorites") != favorites:
            raise RuntimeError("Panel structure or launcher favorites changed unexpectedly.")
        if run("xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", "/commands/custom/<Primary>Escape") != command:
            raise RuntimeError("The launcher keyboard shortcut changed unexpectedly.")
    except Exception:
        restore_record(record, full_css=True)
        raise
    baseline = STATE / "style-restore.json"
    if not baseline.exists():
        baseline.write_text(json.dumps(record, indent=2) + "\n")
    (STATE / "last-style.json").write_text(json.dumps(record, indent=2) + "\n")
    print("Applied the modern launcher: charcoal surfaces, spacious search and 48px app tiles.")
    print("Verified launcher settings, favorites, panel layout and the Super-key command.")
    print("Appearance backup:", backup)
    print("Restore: python3 scripts/style-launcher.py --restore")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if args.restore:
        baseline = STATE / "style-restore.json"
        restore_record(json.loads(baseline.read_text()))
        baseline.unlink()
        print("Restored the launcher appearance from before the upgrade.")
        return
    css = (REPO / "config/launcher.css").read_text()
    settings = json.loads((REPO / "config/launcher.json").read_text())
    validate(css)
    if args.apply:
        apply(css, settings)
    else:
        print("GTK CSS validated: charcoal launcher, green accents and 48px application tiles.")
        print("Menu size:", settings["menu-width"], "×", settings["menu-height"])
        print("Apply: python3 scripts/style-launcher.py --apply")


if __name__ == "__main__":
    main()
