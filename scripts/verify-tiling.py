#!/usr/bin/env python3
"""Check the BSPWM layout and hotkeys on an isolated virtual X11 display."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time

from Xlib import X, Xatom, Xutil, display, protocol

REPO = Path(__file__).resolve().parent.parent


def wait_for(predicate, label):
    end = time.monotonic() + 4
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(label)


def main():
    env = os.environ.copy()
    env["PATH"] = str(REPO / "state/bin") + os.pathsep + env.get("PATH", os.defpath)
    env["SXHKD_SHELL"] = "/bin/sh"
    processes = []
    connection = None
    results = {}
    with tempfile.TemporaryDirectory(prefix="kali-tiling-test-") as directory:
        temporary = Path(directory)
        env["KALI_TILING_CONFIGURED"] = str(temporary / "configured")
        read_fd, write_fd = os.pipe()
        with (temporary / "session.log").open("w+") as log:
            try:
                processes.append(subprocess.Popen(["Xvfb", "-displayfd", str(write_fd),
                    "-screen", "0", "1280x800x24", "-nolisten", "tcp"], env=env,
                    pass_fds=(write_fd,), stdout=log, stderr=log))
                os.close(write_fd)
                if not select.select([read_fd], [], [], 5)[0]:
                    raise RuntimeError("Virtual display startup timed out")
                # Xvfb can write the number and newline separately. Keep the
                # pipe open until both arrive so its final write cannot fail.
                with os.fdopen(read_fd) as display_number:
                    env["DISPLAY"] = ":" + display_number.readline().strip()
                connection = display.Display(env["DISPLAY"])
                root = connection.screen().root
                processes.append(subprocess.Popen(["bspwm", "-c", str(REPO / "config/bspwmrc")],
                                                  env=env, stdout=log, stderr=log))
                processes.append(subprocess.Popen(["sxhkd", "-m", "-1", "-c", str(REPO / "config/tiling-sxhkdrc")],
                                                  env=env, stdout=log, stderr=log))
                try:
                    wait_for(lambda: (temporary / "configured").exists(), "BSPWM config must load")
                except AssertionError:
                    print("Test display:", env["DISPLAY"], "Processes:", [p.poll() for p in processes], file=sys.stderr)
                    probe = subprocess.run(["sh", "-x", str(REPO / "config/bspwmrc")], env=env,
                                           capture_output=True, text=True, timeout=3)
                    print(probe.stdout, probe.stderr, file=sys.stderr)
                    raise
                panel_selection = connection.intern_atom(
                    f"_KALI_SETUP_PANEL_STACKING_S{connection.get_default_screen()}")
                panel_listener = connection.get_selection_owner(panel_selection)
                assert panel_listener, "Panel stacking listener must start with BSPWM"
                # Reloading must also work when pointer focus and popup rules already exist.
                subprocess.run(["sh", str(REPO / "config/bspwmrc")], env=env, check=True,
                               stdout=log, stderr=log)
                assert connection.get_selection_owner(panel_selection).id == panel_listener.id
                results["panel-listener-singleton-on-reload"] = True
                results["configuration-reload"] = True

                def bsp(*args):
                    return subprocess.run(["bspc", *args], env=env, check=True,
                                          capture_output=True, text=True).stdout.strip()

                def node(window):
                    return json.loads(bsp("query", "-T", "-n", hex(window.id)))

                def geometry(window):
                    g = window.get_geometry()
                    p = root.translate_coords(window, 0, 0)
                    return (p.x - g.border_width, p.y - g.border_width,
                            g.width + 2 * g.border_width, g.height + 2 * g.border_width)

                def focus(window):
                    bsp("node", hex(window.id), "-f")

                def above(upper, lower):
                    order = [w.id for w in root.query_tree().children]
                    return order.index(upper.id) > order.index(lower.id)

                def key(shortcut):
                    subprocess.run(["xdotool", "key", "--clearmodifiers", shortcut], env=env, check=True)
                    time.sleep(0.2)

                def resize_drag(window, dx, dy):
                    x, y, width, height = geometry(window)
                    x, y = x + width - 24, y + 24
                    subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y),
                        "keydown", "Super_L", "mousedown", "3", "sleep", "0.1",
                        "mousemove", "--sync", str(x + dx), str(y + dy), "sleep", "0.1",
                        "mouseup", "3", "keyup", "Super_L"], env=env, check=True)
                    time.sleep(0.1)

                def window(color, parent=None, instance="kali-tiling-test", class_name="KaliTilingTest",
                           name="Tiling verification", window_type=None, position=(80, 80)):
                    w = root.create_window(*position, 400, 300, 0, connection.screen().root_depth,
                                           X.InputOutput, X.CopyFromParent, background_pixel=color)
                    w.set_wm_name(name)
                    w.set_wm_class(instance, class_name)
                    w.set_wm_hints(flags=Xutil.InputHint | Xutil.StateHint, input=1, initial_state=Xutil.NormalState)
                    w.set_wm_normal_hints(flags=Xutil.PMinSize, min_width=100, min_height=100)
                    kind = window_type or ("DIALOG" if parent else "NORMAL")
                    w.change_property(connection.intern_atom("_NET_WM_WINDOW_TYPE"), Xatom.ATOM, 32,
                                      [connection.intern_atom("_NET_WM_WINDOW_TYPE_" + kind)])
                    if parent:
                        w.set_wm_transient_for(parent)
                    w.map()
                    connection.sync()
                    wait_for(lambda: w.id in {int(n, 16) for n in bsp("query", "-N", "-n", ".window").splitlines()}, "New window must be managed")
                    time.sleep(0.1)
                    return w

                # XFCE starts the dock before application windows. It must remain
                # unmanaged and above them even without a reserved bottom strut.
                bottom = root.create_window(400, 735, 480, 65, 0, connection.screen().root_depth,
                                            X.InputOutput, X.CopyFromParent, background_pixel=0x171c18)
                bottom.set_wm_class("xfce4-panel", "Xfce4-panel")
                bottom.change_property(connection.intern_atom("_NET_WM_WINDOW_TYPE"), Xatom.ATOM, 32,
                                       [connection.intern_atom("_NET_WM_WINDOW_TYPE_DOCK")])
                bottom.map()
                connection.sync()
                a = window(0x203028)
                assert geometry(a) == (12, 12, 1256, 776), geometry(a)
                wait_for(lambda: above(bottom, a), "The bottom panel must stay above a newly opened window")
                assert bottom.id not in {int(wid, 16) for wid in bsp("query", "-N", "-n", ".window").splitlines()}
                assert connection.get_input_focus().focus.id == a.id
                results["bottom-panel-above-new-windows"] = True
                results["one-window-outer-gap"] = 12
                b = window(0x253342)
                ra, rb = sorted((geometry(a), geometry(b)))
                assert rb[0] - ra[0] - ra[2] == 12, (ra, rb)
                results["two-windows-inner-gap"] = 12
                left = min((a, b), key=lambda w: geometry(w)[0])
                original = geometry(left)
                focus(left)
                key("super+ctrl+Right")
                wait_for(lambda: geometry(left)[2] > original[2], "Keyboard resizing must grow the selected tile")
                key("super+ctrl+shift+Right")
                wait_for(lambda: geometry(left) == original, "Keyboard resizing must shrink the selected tile")
                results["keyboard-tile-resize"] = True
                resize_drag(left, 60, 0)
                wait_for(lambda: geometry(left)[2] > original[2], "Super + right-drag must resize a tiled window")
                resized_left, resized_right = sorted((geometry(a), geometry(b)))
                assert resized_right[0] - resized_left[0] - resized_left[2] == 12
                assert node(left)["client"]["state"] == "tiled"
                resize_drag(left, -60, 0)
                results["mouse-tile-resize-preserves-gaps"] = True
                focus(b)
                before_launcher = (geometry(a), geometry(b))
                launcher = window(0x203028, instance="wrapper-2.0", class_name="Wrapper-2.0",
                                  name="Whisker Menu", window_type="MENU", position=(440, 250))
                assert node(launcher)["client"]["state"] == "floating"
                assert node(launcher)["client"]["layer"] == "above"
                assert node(launcher)["client"]["borderWidth"] == 0
                assert geometry(launcher) == (440, 250, 400, 300), geometry(launcher)
                assert connection.get_input_focus().focus.id == launcher.id
                assert (geometry(a), geometry(b)) == before_launcher
                wait_for(lambda: above(launcher, bottom), "The applications menu must stay above the dock")
                launcher.destroy()
                connection.sync()
                results["launcher-floats-centered-with-keyboard-focus"] = True
                saved = {"current": 0, "active": a.id, "windows": [
                    {"id": a.id, "desktop": 0}, {"id": b.id, "desktop": 1},
                    {"id": 0, "desktop": 2}]}
                subprocess.run([sys.executable, "-c",
                    'import json, runpy, sys; runpy.run_path(sys.argv[1])["migrate_windows"](json.loads(sys.argv[2]))',
                    str(REPO / "scripts/configure-tiling.py"), json.dumps(saved)], env=env, check=True)
                assert bsp("query", "-D", "-n", hex(a.id), "--names") == "1"
                assert bsp("query", "-D", "-n", hex(b.id), "--names") == "2"
                assert bsp("query", "-D", "-d", "focused", "--names") == "1"
                assert int(bsp("query", "-N", "-n", "focused"), 16) == a.id
                results["handover-preserves-workspaces-and-focus"] = True
                bsp("node", hex(b.id), "-d", "^1")
                focus(b)
                key("super+Left")
                assert int(bsp("query", "-N", "-n", "focused"), 16) == a.id
                results["focus-hotkey"] = True
                key("super+shift+Right")
                assert geometry(a)[0] > geometry(b)[0]
                results["swap-hotkey"] = True
                key("super+v")
                assert node(a)["client"]["state"] == "floating"
                assert geometry(b) == (12, 12, 1256, 776)
                original_floating = geometry(a)
                resize_drag(a, 60, -40)
                wait_for(lambda: geometry(a)[2] > original_floating[2]
                         and geometry(a)[3] > original_floating[3],
                         "Super + right-drag must resize both dimensions of a floating window")
                results["mouse-floating-resize"] = True
                focus(a)
                key("super+v")
                assert node(a)["client"]["state"] == "tiled"
                results["floating-toggle-and-reflow"] = True
                key("super+shift+2")
                assert bsp("query", "-D", "-d", "focused", "--names") == "2"
                assert geometry(a) == (12, 12, 1256, 776)
                results["move-window-and-follow"] = True
                key("super+1")
                assert bsp("query", "-D", "-d", "focused", "--names") == "1"
                results["workspace-hotkey"] = True
                focus(b)
                key("alt+F11")
                assert geometry(b) == (0, 0, 1280, 800)
                wait_for(lambda: above(b, bottom), "Fullscreen windows must cover the dock")
                key("alt+F11")
                wait_for(lambda: above(bottom, b), "The dock must return above a window leaving fullscreen")
                results["bottom-panel-fullscreen-layering"] = True
                results["fullscreen-toggle"] = True
                dialog = window(0x3b2b30, b)
                assert node(dialog)["client"]["state"] == "floating"
                wait_for(lambda: above(bottom, dialog), "The dock must stay above floating application windows")
                dialog.destroy()
                connection.sync()
                results["dialogs-float"] = True
                # Exercise the same EWMH protocol used by the gesture listener.
                root.send_event(protocol.event.ClientMessage(window=root,
                    client_type=connection.intern_atom("_NET_CURRENT_DESKTOP"), data=(32, [1, 0, 0, 0, 0])),
                    event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
                connection.flush()
                wait_for(lambda: bsp("query", "-D", "-d", "focused", "--names") == "2", "EWMH workspace switch")
                results["gesture-workspace-protocol"] = True
                bsp("node", hex(a.id), "-d", "^1", "--follow")
                c = window(0x352c42)
                before_a, before_c = geometry(a), geometry(c)
                b.destroy()
                connection.sync()
                wait_for(lambda: len(bsp("query", "-N", "-n", ".window").splitlines()) == 2, "Closing a window must remove its tile")
                after_a, after_c = geometry(a), geometry(c)
                assert (after_a[2] * after_a[3] > before_a[2] * before_a[3]
                        or after_c[2] * after_c[3] > before_c[2] * before_c[3])
                results["close-window-reflows"] = True
                # A dock reserves panel space without joining the tiling tree.
                dock = root.create_window(0, 0, 1280, 28, 0, connection.screen().root_depth,
                                          X.InputOutput, X.CopyFromParent, background_pixel=0x171c18)
                dock.set_wm_class("xfce4-panel", "Xfce4-panel")
                dock.change_property(connection.intern_atom("_NET_WM_WINDOW_TYPE"), Xatom.ATOM, 32,
                                     [connection.intern_atom("_NET_WM_WINDOW_TYPE_DOCK")])
                dock.change_property(connection.intern_atom("_NET_WM_STRUT_PARTIAL"), Xatom.CARDINAL, 32,
                                     [0, 0, 28, 0, 0, 0, 0, 0, 0, 1279, 0, 0])
                dock.map()
                connection.sync()
                wait_for(lambda: min(geometry(a)[1], geometry(c)[1]) == 40, "Panel reservation must be honored")
                results["panel-space-reserved"] = True
                focus(a)
                bsp("desktop", "-f", "^2")
                bsp("desktop", "-f", "^1")
                wait_for(lambda: above(bottom, a) and above(bottom, c), "The dock must stay above windows after workspace switching")
                before_reveal = (geometry(a), geometry(c))
                bottom.configure(y=850)
                bottom.configure(stack_mode=X.Below)
                bottom.configure(y=735)
                connection.sync()
                wait_for(lambda: above(bottom, a) and above(bottom, c), "Revealing the dock must restore its stacking")
                assert geometry(bottom) == (400, 735, 480, 65)
                assert (geometry(a), geometry(c)) == before_reveal
                assert connection.get_input_focus().focus.id == a.id
                results["bottom-panel-workspace-and-reveal-stacking"] = True
                results["four-workspaces"] = bsp("query", "-D", "--names").splitlines() == ["1", "2", "3", "4"]
                processes[1].terminate()
                processes[1].wait(timeout=3)
                wait_for(lambda: not connection.get_selection_owner(panel_selection),
                         "The panel listener must exit when BSPWM stops")
                results["panel-listener-stops-with-window-manager"] = True
                STATE = REPO / "state/tiling"
                STATE.mkdir(parents=True, exist_ok=True)
                (STATE / "verification.json").write_text(json.dumps(results, indent=2) + "\n")
                print(json.dumps(results, indent=2))
            finally:
                if connection:
                    connection.close()
                for process in reversed(processes):
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                log.seek(0)
                output = log.read()
                if output:
                    print(output, file=sys.stderr)
                if "Could not grab" in output or "Unknown" in output:
                    raise AssertionError("Tiling configuration produced startup errors")


if __name__ == "__main__":
    main()
