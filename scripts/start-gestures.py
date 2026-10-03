#!/usr/bin/env python3
"""Start the single native gesture listener in the logged-in X11 session."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/input"
BINARY = REPO / "state/bin/workspace-gestures"


def stop_listener():
    pidfile = STATE / "gestures.pid"
    if not pidfile.exists():
        return
    pid = int(pidfile.read_text())
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[0].decode()
        if command != str(BINARY):
            return
        os.kill(pid, 15)
        for _ in range(30):
            if not Path(f"/proc/{pid}").exists():
                break
            time.sleep(0.1)
    except (ProcessLookupError, FileNotFoundError):
        pass
    pidfile.unlink(missing_ok=True)


def start():
    if os.environ.get("XDG_SESSION_TYPE", "x11") != "x11":
        raise RuntimeError("This gesture listener requires an X11 session.")
    settings = json.loads((REPO / "config/input.json").read_text())
    args = [str(BINARY), "--device", settings["device"], "--fingers", str(settings["fingers"]),
            "--threshold", str(settings["threshold"]), "--lockfile", str(STATE / "gestures.lock")]
    if settings["wrap"]:
        args.append("--wrap")
    if settings["swipe_left"] == "previous":
        args.append("--inverse")
    if (REPO / "state/compositor/enabled").exists():
        args.append("--animate")
    STATE.mkdir(parents=True, exist_ok=True)
    stop_listener()
    with (STATE / "gestures.log").open("a") as log:
        process = subprocess.Popen(args, stdout=log, stderr=log, start_new_session=True)
    (STATE / "gestures.pid").write_text(str(process.pid))
    time.sleep(0.5)
    if process.poll() is not None:
        raise RuntimeError("Gesture listener exited; inspect state/input/gestures.log.")
    print("Gesture listener running, PID", process.pid)


if __name__ == "__main__":
    if sys.argv[1:] == ["--stop"]:
        stop_listener()
    elif not sys.argv[1:]:
        start()
    else:
        raise SystemExit("Usage: start-gestures.py [--stop]")
