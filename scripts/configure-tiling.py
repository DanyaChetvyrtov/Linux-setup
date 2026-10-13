#!/usr/bin/env python3
"""Install, supervise, or restore BSPWM window management within XFCE/X11."""
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
from window_gaps import GapListener, Rect
from Xlib import X, error, protocol

STATE = REPO / "state/tiling"
SCRIPT = Path(__file__).resolve()
SESSION_KEY = "/sessions/Failsafe/Client0_Command"


def environment():
    env = os.environ.copy()
    env["PATH"] = str(REPO / "state/bin") + os.pathsep + env.get("PATH", os.defpath)
    env["KALI_TILING_CONFIGURED"] = str(STATE / "configured")
    env["SXHKD_SHELL"] = "/bin/sh"
    return env


def run(*args, check=True):
    return subprocess.run(args, env=environment(), check=check, capture_output=True, text=True).stdout.strip()


def wm_info():
    connection = GapListener(0)
    try:
        check = connection.property(connection.root, "_NET_SUPPORTING_WM_CHECK")
        if not check:
            return "", None
        window = connection.connection.create_resource_object("window", check[0])
        prop = window.get_full_property(connection.atom("_NET_WM_NAME"), X.AnyPropertyType)
        name = bytes(prop.value).decode(errors="replace") if prop else ""
        pid = connection.property(window, "_NET_WM_PID")
        return name, pid[0] if pid else None
    except error.BadWindow:
        return "", None
    finally:
        connection.close()


def snapshot():
    reader = GapListener(0)
    result = {"current": (reader.property(reader.root, "_NET_CURRENT_DESKTOP") or [0])[0],
              "active": (reader.property(reader.root, "_NET_ACTIVE_WINDOW") or [0])[0], "windows": []}
    try:
        for wid in reader.clients():
            window = reader.connection.create_resource_object("window", wid)
            try:
                types = reader.property(window, "_NET_WM_WINDOW_TYPE")
                if types and reader.atom("_NET_WM_WINDOW_TYPE_NORMAL") not in types:
                    continue
                result["windows"].append({"id": wid, "rect": reader.geometry(window).values(),
                    "desktop": (reader.property(window, "_NET_WM_DESKTOP") or [result["current"]])[0],
                    "states": [reader.connection.get_atom_name(s) for s in reader.property(window, "_NET_WM_STATE")]})
            except error.BadWindow:
                pass
        return result
    finally:
        reader.close()


def message(reader, window, name, values):
    reader.root.send_event(protocol.event.ClientMessage(window=window,
        client_type=reader.atom(name), data=(32, values)),
        event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)


def restore_windows(saved):
    reader = GapListener(0)
    try:
        live = set(reader.clients())
        for item in saved["windows"]:
            if item["id"] not in live:
                continue
            window = reader.connection.create_resource_object("window", item["id"])
            try:
                for state in ("MAXIMIZED_HORZ", "MAXIMIZED_VERT", "FULLSCREEN"):
                    message(reader, window, "_NET_WM_STATE", [0, reader.atom("_NET_WM_STATE_" + state), 0, 2, 0])
                message(reader, window, "_NET_WM_DESKTOP", [item["desktop"], 2, 0, 0, 0])
            except error.BadWindow:
                pass
        reader.connection.flush()
        time.sleep(0.2)
        for item in saved["windows"]:
            if item["id"] not in live:
                continue
            window = reader.connection.create_resource_object("window", item["id"])
            try:
                reader.place(window, Rect(*item["rect"]))
                for state in item["states"]:
                    if state.rsplit("_", 1)[-1] in ("FOCUSED", "HIDDEN"):
                        continue
                    message(reader, window, "_NET_WM_STATE", [1, reader.atom(state), 0, 2, 0])
            except error.BadWindow:
                pass
        message(reader, reader.root, "_NET_CURRENT_DESKTOP", [saved["current"], X.CurrentTime, 0, 0, 0])
        if saved["active"] in live:
            active = reader.connection.create_resource_object("window", saved["active"])
            message(reader, active, "_NET_ACTIVE_WINDOW", [2, X.CurrentTime, 0, 0, 0])
        reader.connection.sync()
    finally:
        reader.close()


def release_xfwm():
    name, pid = wm_info()
    if not name:
        return
    if name != "Xfwm4" or not pid or Path(f"/proc/{pid}/comm").read_text().strip() != "xfwm4":
        raise RuntimeError(f"Expected XFWM, found {name!r}; refusing to stop another window manager.")
    # Tell the session manager not to respawn this specific XFWM client.
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def call(path, interface, method, parameters=None):
        return bus.call_sync("org.xfce.SessionManager", path, interface, method, parameters,
                             None, Gio.DBusCallFlags.NONE, 3000, None).unpack()

    clients = call("/org/xfce/SessionManager", "org.xfce.Session.Manager", "ListClients")[0]
    for path in clients:
        properties = call(path, "org.xfce.Session.Client", "GetSmProperties",
                          GLib.Variant("(as)", (["Program"],)))[0]
        if Path(properties.get("Program", "")).name == "xfwm4":
            call(path, "org.xfce.Session.Client", "SetSmProperties",
                 GLib.Variant("(a{sv})", ({"RestartStyleHint": GLib.Variant("y", 3)},)))
    os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if wm_info()[0] != "Xfwm4":
            return
        time.sleep(0.1)
    raise RuntimeError("XFWM did not release window management.")


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
        for _ in range(80):
            if owned_pid() != pid:
                return
            time.sleep(0.1)
        raise RuntimeError("Tiling supervisor did not stop.")


def spawn_xfwm():
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "xfwm.log").open("a") as log:
        process = subprocess.Popen(["xfwm4", "--replace"], stdout=log, stderr=log, start_new_session=True)
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError("XFWM failed to start; see state/tiling/xfwm.log.")
        if wm_info()[0] == "Xfwm4":
            time.sleep(0.3)
            return
        time.sleep(0.1)
    raise RuntimeError("XFWM startup timed out.")


def session():
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "session.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        if not (STATE / "enabled").exists():
            os.execvp("xfwm4", ["xfwm4"])
        (STATE / "supervisor.pid").write_text(str(os.getpid()))
        (STATE / "configured").unlink(missing_ok=True)
        stopping = False
        processes = []

        def terminate(signum, frame):
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, terminate)
        signal.signal(signal.SIGINT, terminate)
        try:
            if wm_info()[0]:
                release_xfwm()
            for name, args in (("bspwm", ["-c", str(REPO / "config/bspwmrc")]),
                               ("sxhkd", ["-m", "-1", "-c", str(REPO / "config/tiling-sxhkdrc")])):
                processes.append(subprocess.Popen([name, *args], env=environment()))
                if name == "sxhkd":
                    (STATE / "sxhkd.pid").write_text(str(processes[-1].pid))
            for _ in range(50):
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("Tiling or hotkey process exited during startup.")
                if (STATE / "configured").exists():
                    (STATE / "ready").write_text(str(os.getpid()))
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("BSPWM configuration timed out.")
            while not stopping and all(p.poll() is None for p in processes):
                time.sleep(0.2)
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            (STATE / "ready").unlink(missing_ok=True)
            (STATE / "supervisor.pid").unlink(missing_ok=True)
            (STATE / "sxhkd.pid").unlink(missing_ok=True)
            if not stopping:
                spawn_xfwm()


def start():
    (STATE / "ready").unlink(missing_ok=True)
    with (STATE / "session.log").open("a") as log:
        process = subprocess.Popen([sys.executable, str(SCRIPT), "--session"],
                                   stdout=log, stderr=log, start_new_session=True)
    for _ in range(80):
        if process.poll() is not None:
            raise RuntimeError("Tiling startup failed; original manager restored. See state/tiling/session.log.")
        if (STATE / "ready").exists() and owned_pid() == process.pid:
            return
        time.sleep(0.1)
    stop()
    raise RuntimeError("Tiling startup timed out.")


def session_command():
    import gi
    gi.require_version("Xfconf", "0")
    from gi.repository import Xfconf
    if not Xfconf.init():
        raise RuntimeError("Could not read XFCE settings.")
    channel = Xfconf.Channel.new("xfce4-session")
    return channel, channel.get_string_list(SESSION_KEY)


def set_session_command(values):
    # Xfconf's variadic C setter cannot marshal a Python list through GI.
    args = ["xfconf-query", "-c", "xfce4-session", "-p", SESSION_KEY, "-a"]
    for value in values:
        args.extend(["-t", "string", "--set=" + value])
    run(*args)


def restore():
    record = json.loads((STATE / "restore.json").read_text())
    (STATE / "enabled").unlink(missing_ok=True)
    stop()
    set_session_command(record["session-command"])
    shutil.copy2(record["picom-backup"], REPO / "config/picom.conf")
    if wm_info()[0] != "Xfwm4":
        spawn_xfwm()
    restore_windows(record["windows"])
    if record["picom-active"]:
        subprocess.run([sys.executable, str(REPO / "scripts/start-compositor.py")], check=True)
    print("Restored XFWM, its startup command, compositor settings, and surviving windows.")


def migrate_windows(saved):
    nodes = {int(node, 16) for node in run("bspc", "query", "-N", "-n", ".window").splitlines()}
    for item in saved["windows"]:
        node = f"0x{item['id']:08X}"
        if item["id"] in nodes and item["desktop"] != 0xffffffff:
            target = f"^{item['desktop'] + 1}"
            current = run("bspc", "query", "-D", "-n", node)
            destination = run("bspc", "query", "-D", "-d", target)
            # BSPWM reports failure when a node already belongs to its target desktop.
            if current != destination:
                run("bspc", "node", node, "-d", target)
    run("bspc", "desktop", "-f", f"^{saved['current'] + 1}")
    if saved["active"] in nodes:
        run("bspc", "node", f"0x{saved['active']:08X}", "-f")


def apply():
    if os.environ.get("XDG_SESSION_TYPE", "x11") != "x11":
        raise RuntimeError("This setup requires XFCE on X11.")
    for name in ("bspwm", "bspc", "sxhkd"):
        if not shutil.which(name, path=environment()["PATH"]):
            raise RuntimeError(f"Missing {name}; install the tiling package profile first.")
    if owned_pid():
        run("sh", str(REPO / "config/bspwmrc"))
        pid = int((STATE / "sxhkd.pid").read_text())
        args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        if str(REPO / "config/tiling-sxhkdrc").encode() not in args:
            raise RuntimeError("Hotkey daemon changed; refusing to reload another process.")
        os.kill(pid, signal.SIGUSR1)
        print("Reloaded the tiling settings. Original XFWM rollback retained.")
        return
    if wm_info()[0] != "Xfwm4":
        raise RuntimeError("Apply this setup from your original XFCE/XFWM session.")
    channel, original = session_command()
    if not original or Path(original[0]).name != "xfwm4":
        raise RuntimeError("Unexpected XFCE startup command; refusing to replace it.")
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup = STATE / "backups" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(REPO / "config/picom.conf", backup / "picom.conf")
    record = {"session-command": original, "picom-backup": str(backup / "picom.conf"),
              "picom-active": (REPO / "state/compositor/ready").exists(), "windows": snapshot()}
    (backup / "restore.json").write_text(json.dumps(record, indent=2) + "\n")
    (STATE / "restore.json").write_text(json.dumps(record, indent=2) + "\n")
    try:
        set_session_command([sys.executable, str(SCRIPT), "--session"])
        picom = (REPO / "config/picom.conf").read_text()
        picom = picom.replace("corner-radius = 0;", "corner-radius = 8;", 1)
        picom = picom.replace("    shadow = false;", "    shadow = false;\n    corner-radius = 0;", 1)
        (REPO / "config/picom.conf").write_text(picom)
        (STATE / "enabled").touch()
        start()
        migrate_windows(record["windows"])
        if record["picom-active"]:
            subprocess.run([sys.executable, str(REPO / "scripts/start-compositor.py")], check=True)
    except Exception:
        restore()
        raise
    print("Automatic tiling enabled now and at XFCE login; 12px gaps and 2px green borders.")
    print("Restore: Super+Ctrl+Escape, or python3 scripts/configure-tiling.py --restore")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--restore", action="store_true")
    modes.add_argument("--session", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.session:
        session()
    elif args.restore:
        restore()
    elif args.apply:
        apply()
    else:
        print("Preview: BSPWM automatic tiling within XFCE; 12px gaps, 2px green borders.")
        print("Existing application shortcuts, panels, dock, and workspace gestures stay available.")
        print("Apply: python3 scripts/configure-tiling.py --apply")


if __name__ == "__main__":
    main()
