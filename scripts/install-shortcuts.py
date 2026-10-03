#!/usr/bin/env python3
"""Preview or install the Shortcuts application-menu launcher."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parent.parent
TARGET = Path.home() / ".local/share/applications/kali-setup-shortcuts.desktop"


def exec_argument(value):
    # Exec quoting is separate from the desktop file's string escaping.
    for character in ("\\", '"', "`", "$"):
        value = value.replace(character, "\\" + character)
    return '"' + value.replace("\\", "\\\\").replace("%", "%%") + '"'


def launcher():
    script = REPO / "scripts/shortcut-viewer.py"
    if "\n" in str(script) or "\r" in str(script):
        raise ValueError("The repository path cannot contain line breaks")
    return "\n".join([
        "[Desktop Entry]", "Type=Application", "Version=1.0", "Name=Shortcuts",
        "Comment=View keyboard shortcuts and edit their descriptions",
        "Exec=/usr/bin/python3 " + exec_argument(str(script)),
        "Icon=preferences-desktop-keyboard", "Terminal=false", "StartupNotify=true",
        "Categories=Settings;", "Keywords=keyboard;hotkeys;shortcuts;wallpaper;", "",
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Install the launcher")
    mode.add_argument("--restore", type=Path, metavar="RECORD", help="Restore a saved launcher backup")
    args = parser.parse_args()
    if TARGET.is_symlink():
        raise SystemExit("Refusing to replace a symlink: " + str(TARGET))
    if args.restore:
        record = json.loads(args.restore.read_text())
        if record["target"] != str(TARGET):
            raise SystemExit("The backup belongs to a different user or launcher")
        current = TARGET.read_text() if TARGET.exists() else None
        if current != record["installed"]:
            raise SystemExit("The launcher changed since installation; review it before restoring")
        if record["existed"]:
            shutil.copy2(args.restore.parent / "launcher.desktop", TARGET)
        else:
            TARGET.unlink()
        print("Restored:", TARGET)
        return

    content = launcher()
    with tempfile.TemporaryDirectory(prefix="kali-shortcuts-") as directory:
        preview = Path(directory) / TARGET.name
        preview.write_text(content)
        subprocess.run(["desktop-file-validate", str(preview)], check=True)
    print("Application-menu launcher:", TARGET)
    if not args.apply:
        print(content, end="")
        print("Preview only; use --apply to install.")
        return
    if TARGET.exists() and TARGET.read_text() == content:
        print("Already installed.")
        return
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup = REPO / "state/shortcuts" / stamp
    backup.mkdir(parents=True)
    existed = TARGET.exists()
    if existed:
        shutil.copy2(TARGET, backup / "launcher.desktop")
    record = {"target": str(TARGET), "existed": existed, "installed": content}
    (backup / "restore.json").write_text(json.dumps(record, indent=2) + "\n")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(content)
    print("Installed. Restore record:", backup / "restore.json")


if __name__ == "__main__":
    main()
