#!/usr/bin/env python3
"""Supervise Picom in the XFCE session and restore XFWM compositing on exit."""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from Xlib import display

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/compositor"
SCRIPT = Path(__file__).resolve()
stopping = False


def compositing(enabled):
    subprocess.run(["xfconf-query", "-c", "xfwm4", "-p", "/general/use_compositing",
                    "-s", str(enabled).lower()], check=True)


def owner():
    connection = display.Display()
    try:
        window = connection.get_selection_owner(connection.intern_atom("_NET_WM_CM_S0"))
        return window.id if window else 0
    finally:
        connection.close()


def owned_pid():
    try:
        pid = int((STATE / "supervisor.pid").read_text())
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
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Compositor supervisor did not stop.")


def start():
    stop()
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "ready").unlink(missing_ok=True)
    with (STATE / "picom.log").open("a") as log:
        process = subprocess.Popen([sys.executable, str(SCRIPT), "--session"],
                                   stdout=log, stderr=log, start_new_session=True)
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError("Picom failed; XFWM compositing was restored. See state/compositor/picom.log.")
        if (STATE / "ready").exists() and owner():
            print("Picom running, PID", (STATE / "ready").read_text().strip())
            return
        time.sleep(0.1)
    stop()
    raise RuntimeError("Picom startup timed out; XFWM compositing restored.")


def session():
    global stopping
    if os.environ.get("XDG_SESSION_TYPE", "x11") != "x11":
        raise RuntimeError("Picom requires an X11 session.")
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "session.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if subprocess.run(["pgrep", "-x", "picom"], capture_output=True).returncode == 0:
            raise RuntimeError("Another Picom process is already running.")
        (STATE / "supervisor.pid").write_text(str(os.getpid()))
        process = None

        def terminate(signum, frame):
            global stopping
            stopping = True

        signal.signal(signal.SIGTERM, terminate)
        signal.signal(signal.SIGINT, terminate)
        try:
            compositing(False)
            for _ in range(30):
                if not owner():
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Existing compositor did not release the X11 session.")
            process = subprocess.Popen(["picom", "--config", str(REPO / "config/picom.conf"),
                                        "--log-level", os.environ.get("KALI_PICOM_LOG_LEVEL", "WARN")])
            time.sleep(0.5)
            if process.poll() is not None or not owner():
                raise RuntimeError("Picom could not take over compositing.")
            (STATE / "ready").write_text(str(process.pid))
            while not stopping and process.poll() is None:
                time.sleep(0.2)
        finally:
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            (STATE / "ready").unlink(missing_ok=True)
            compositing(True)
            (STATE / "supervisor.pid").unlink(missing_ok=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--session"]:
        session()
    elif sys.argv[1:] == ["--stop"]:
        stop()
    elif not sys.argv[1:]:
        start()
    else:
        raise SystemExit("Usage: start-compositor.py [--session|--stop]")
