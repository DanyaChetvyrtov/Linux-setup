#!/usr/bin/env python3
"""Preview, apply, or restore inner spacing between XFCE tiled windows."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
from window_gaps import GapListener

STATE = REPO / "state/window-gaps"
SCRIPT = Path(__file__).resolve()
AUTOSTART = Path.home() / ".config/autostart/kali-window-gaps.desktop"
ACTIVE = STATE / "active.json"


def settings(path):
    result = json.loads(path.read_text())
    gap = result["inner_gap"]
    if type(gap) is not int or not 0 <= gap <= 100:
        raise ValueError("inner_gap must be an integer from 0 to 100 pixels.")
    return result


def owned_pid():
    try:
        pid = int((STATE / "listener.pid").read_text())
        args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        return pid if str(SCRIPT).encode() in args and b"--session" in args else None
    except (FileNotFoundError, ValueError, ProcessLookupError):
        return None


def stop():
    pid = owned_pid()
    if pid:
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            if owned_pid() != pid:
                return
            time.sleep(0.1)
        raise RuntimeError("Window gap listener did not stop.")


def start():
    stop()
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "ready").unlink(missing_ok=True)
    with (STATE / "listener.log").open("a") as log:
        process = subprocess.Popen([sys.executable, str(SCRIPT), "--session"],
                                   stdout=log, stderr=log, start_new_session=True)
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError("Gap listener failed; inspect state/window-gaps/listener.log.")
        if (STATE / "ready").exists() and owned_pid() == process.pid:
            return
        time.sleep(0.1)
    stop()
    raise RuntimeError("Gap listener startup timed out.")


def session():
    if os.environ.get("XDG_SESSION_TYPE", "x11") != "x11":
        raise RuntimeError("The window gap helper requires XFCE on X11.")
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "listener.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        listener = GapListener(settings(ACTIVE)["inner_gap"])
        (STATE / "listener.pid").write_text(str(os.getpid()))

        def terminate(signum, frame):
            listener.stopping = True

        signal.signal(signal.SIGTERM, terminate)
        signal.signal(signal.SIGINT, terminate)
        try:
            listener.run(lambda: (STATE / "ready").write_text(str(os.getpid())))
        finally:
            listener.close()
            (STATE / "listener.pid").unlink(missing_ok=True)
            (STATE / "ready").unlink(missing_ok=True)


def restore(record):
    stop()
    listener = GapListener(0)
    try:
        listener.restore_windows()
    finally:
        listener.close()
    for item in record["files"]:
        path = Path(item["path"])
        if path.is_symlink():
            raise RuntimeError("Refusing to replace a symlink: " + str(path))
        if item["existed"]:
            shutil.copy2(item["backup"], path)
        else:
            path.unlink(missing_ok=True)
    if record["running"]:
        start()


def apply(config):
    if (REPO / "state/tiling/enabled").exists():
        raise RuntimeError("Restore automatic tiling before enabling the XFWM half-screen gap helper.")
    # Check X11 access before changing user-session files.
    listener = GapListener(config["inner_gap"])
    listener.close()
    for path in (AUTOSTART, ACTIVE):
        if path.is_symlink():
            raise RuntimeError("Refusing to replace a symlink: " + str(path))
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup = STATE / "backups" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    record = {"running": owned_pid() is not None, "files": []}
    for path in (AUTOSTART, ACTIVE):
        item = {"path": str(path), "existed": path.exists(), "backup": str(backup / path.name)}
        if path.exists():
            shutil.copy2(path, item["backup"])
        record["files"].append(item)
    (backup / "restore.json").write_text(json.dumps(record, indent=2) + "\n")
    try:
        stop()
        ACTIVE.write_text(json.dumps(config, indent=2) + "\n")
        AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
        script = str(SCRIPT).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
        AUTOSTART.write_text('[Desktop Entry]\nType=Application\nName=Window tiling gaps\n'
                             f'Exec=/usr/bin/python3 "{script}" --session\n'
                             'OnlyShowIn=XFCE;\nTerminal=false\n')
        start()
    except Exception:
        restore(record)
        raise
    (STATE / "last-apply.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"Applied {config['inner_gap']}px inner gaps; enabled XFCE login autostart.")
    print("Restore: python3 scripts/configure-window-gaps.py --restore")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--restore", action="store_true")
    modes.add_argument("--session", action="store_true", help=argparse.SUPPRESS)
    modes.add_argument("--stop", action="store_true", help="Stop the listener, keeping window positions")
    args = parser.parse_args()
    if args.session:
        session()
    elif args.stop:
        stop()
    elif args.restore:
        restore(json.loads((STATE / "last-apply.json").read_text()))
        print("Restored the previous gap helper and original positions of unchanged tiles.")
    else:
        config = settings(REPO / "config/window-gaps.json")
        if args.apply:
            apply(config)
        else:
            print(f"Preview: {config['inner_gap']}px between half-screen and quarter-screen tiles.")
            print("Uses existing XFWM hotkeys and edge snapping; keeps outer screen edges fixed.")
            print("Apply: python3 scripts/configure-window-gaps.py --apply")


if __name__ == "__main__":
    main()
