#!/usr/bin/env python3
"""Apply repository-managed XFCE panel CSS, with backups and appearance rollback."""
import argparse
import datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/panels"
GTK = Path.home() / ".config/gtk-3.0"
MAIN_CSS = GTK / "gtk.css"
PANEL_CSS = GTK / "kali-setup-panels.css"
BEGIN = "/* BEGIN kali-setup panel style */"
END = "/* END kali-setup panel style */"


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def render(top, bottom):
    return ((REPO / "config/panels.css").read_text()
            .replace("@TOP_PANEL@", str(top)).replace("@BOTTOM_PANEL@", str(bottom)))


def validate(css):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    errors = []
    provider = Gtk.CssProvider()
    provider.connect("parsing-error", lambda _provider, _section, error: errors.append(str(error)))
    provider.load_from_data(css.encode())
    if errors:
        raise ValueError("GTK CSS validation failed: " + "; ".join(errors))


def managed_import(old):
    pattern = re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?"
    clean = re.sub(pattern, "", old, flags=re.S)
    suffix = f'{BEGIN}\n@import url("{PANEL_CSS.as_uri()}");\n{END}\n'
    return clean.rstrip("\n") + ("\n\n" if clean.strip() else "") + suffix


def set_property(path, kind, value):
    query = ["xfconf-query", "-c", "xfce4-panel", "-p", path]
    exists = subprocess.run(query, capture_output=True).returncode == 0
    run(*(query + ([] if exists else ["-n", "-t", kind]) + ["-s", str(value)]))


def restore_files(record):
    for item in record["files"]:
        target = Path(item["path"])
        if item["existed"]:
            shutil.copy2(item["backup"], target)
        elif target.exists():
            target.unlink()


def structure(panel_ids):
    result = {}
    for panel in panel_ids:
        for name in ["position", "position-locked", "size", "length", "length-adjust",
                     "autohide-behavior", "plugin-ids"]:
            path = f"/panels/panel-{panel}/{name}"
            result[path] = run("xfconf-query", "-c", "xfce4-panel", "-p", path)
    return result


def apply(css, top, bottom):
    current = run("xfconf-query", "-c", "xfce4-panel", "-p", "/panels")
    found = [int(x) for x in current.splitlines() if x.isdigit()]
    if found != [top, bottom]:
        raise ValueError("The saved top/bottom panel IDs do not match this session.")
    before = structure(found)
    # Refuse symlinks so the override never edits another repository or theme.
    for path in [MAIN_CSS, PANEL_CSS]:
        if path.is_symlink():
            raise ValueError(f"Refusing to replace a symlink: {path}")
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup_dir = STATE / "style-backups" / stamp
    backup_dir.mkdir(parents=True, exist_ok=False)
    native_backup = backup_dir / "panels.tar.bz2"
    run("xfce4-panel-profiles", "save", str(native_backup))
    record = {"native-backup": str(native_backup), "files": []}
    for path in [MAIN_CSS, PANEL_CSS]:
        item = {"path": str(path), "existed": path.exists(), "backup": str(backup_dir / path.name)}
        if path.exists():
            shutil.copy2(path, item["backup"])
        record["files"].append(item)
    old = MAIN_CSS.read_text() if MAIN_CSS.exists() else ""
    spec = json.loads((REPO / "config/panels.json").read_text())
    # Record the recovery information before making the first change.
    (backup_dir / "restore.json").write_text(json.dumps(record, indent=2) + "\n")
    try:
        GTK.mkdir(parents=True, exist_ok=True)
        PANEL_CSS.write_text(css)
        MAIN_CSS.write_text(managed_import(old))
        validate(MAIN_CSS.read_text())
        for panel in found:
            set_property(f"/panels/panel-{panel}/background-style", "uint", 0)
        plugins = run("xfconf-query", "-c", "xfce4-panel", "-p", f"/panels/panel-{top}/plugin-ids")
        for plugin in [int(x) for x in plugins.splitlines() if x.isdigit()]:
            kind = run("xfconf-query", "-c", "xfce4-panel", "-p", f"/plugins/plugin-{plugin}")
            if kind == "separator":
                set_property(f"/plugins/plugin-{plugin}/style", "uint", 0)
            elif kind == "clock":
                font = spec.get("top-menu-bar", {}).get("clock-font", "Cantarell Bold 10")
                set_property(f"/plugins/plugin-{plugin}/digital-time-font", "string", font)
        run("xfce4-panel", "--restart")
        time.sleep(2)
        if structure(found) != before:
            raise RuntimeError("Panel layout changed unexpectedly.")
    except Exception:
        restore_files(record)
        run("xfce4-panel-profiles", "load", str(native_backup))
        raise
    (STATE / "last-style.json").write_text(json.dumps(record, indent=2) + "\n")
    print("Applied panel style. Positions, sizes, plugin order and hiding behavior verified unchanged.")
    print("Appearance backup:", backup_dir)
    print("Restore: python3 scripts/style-panels.py --restore")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if args.restore:
        record = json.loads((STATE / "last-style.json").read_text())
        restore_files(record)
        run("xfce4-panel-profiles", "load", record["native-backup"])
        print("Restored panel appearance from", record["native-backup"])
        return
    layout = json.loads((STATE / "last-apply.json").read_text())
    css = render(layout["top"], layout["bottom"])
    validate(css)
    if args.apply:
        apply(css, layout["top"], layout["bottom"])
    else:
        print("GTK CSS validated: transparent menu bar and rounded green-accented dock.")
        print("Preview only. Use --apply in your XFCE session; positions and layout are retained.")


if __name__ == "__main__":
    main()
