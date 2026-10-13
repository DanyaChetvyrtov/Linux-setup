#!/usr/bin/env python3
"""Verify Super-key launcher position, keyboard focus, and unchanged tiled windows."""
import json
from pathlib import Path
import subprocess
import time

from Xlib import display, error, X

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/launcher"
BSPC = str(REPO / "state/bin/bspc")


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=10).stdout.strip()


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise RuntimeError("Timed out waiting for the application menu")


def main():
    connection = display.Display()
    root = connection.screen().root
    original_pointer = root.query_pointer()

    def is_menu(window):
        return window.get_wm_class() == ("wrapper-2.0", "Wrapper-2.0") and window.get_wm_name() == "Whisker Menu"

    def menu():
        for window in root.query_tree().children:
            try:
                if is_menu(window) and window.get_attributes().map_state == X.IsViewable:
                    return window
            except error.BadWindow:
                continue
        return None

    def rectangle(window):
        geometry = window.get_geometry()
        position = root.translate_coords(window, 0, 0)
        return (position.x, position.y, geometry.width, geometry.height)

    def layout():
        result = {}
        for wid in run(BSPC, "query", "-N", "-n", ".window").splitlines():
            window = connection.create_resource_object("window", int(wid, 16))
            if not is_menu(window):
                result[wid] = rectangle(window)
        return result

    def menu_has_focus(window):
        focused = connection.get_input_focus().focus
        while hasattr(focused, "id") and focused.id != root.id:
            if focused.id == window.id:
                return True
            focused = focused.query_tree().parent
        return False

    def close_menu():
        window = menu()
        if window:
            # Focus the known popup before sending Escape, including after a failed assertion.
            run(BSPC, "node", hex(window.id), "-f")
            run("xdotool", "key", "--clearmodifiers", "Escape")
            time.sleep(0.2)
            # Whisker's first Escape clears an active search; the next closes the menu.
            if menu():
                assert menu_has_focus(window)
                run("xdotool", "key", "--clearmodifiers", "Escape")
            wait_for(lambda: menu() is None)

    def capture_menu(geometry, filename):
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, Gtk
        assert Gtk.init_check()[0], "GTK must connect to the display"
        capture = Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(), *geometry)
        assert capture, "Could not capture the launcher"
        STATE.mkdir(parents=True, exist_ok=True)
        capture.savev(str(STATE / filename), "png", [], [])

    try:
        command = run("xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", "/commands/custom/<Primary>Escape")
        assert command == "xfce4-popup-whiskermenu --center", command
        if menu():
            # The native command toggles an existing popup even when it lacks focus.
            run("xfce4-popup-whiskermenu", "--center")
            wait_for(lambda: menu() is None)
        monitor = json.loads(run(BSPC, "query", "-T", "-m", "focused"))["rectangle"]
        original_layout = layout()
        opened = []
        for attempt in range(2):
            run("xdotool", "key", "--clearmodifiers", "Super_L")
            window = wait_for(menu)
            wait_for(lambda: menu_has_focus(window))
            node = json.loads(run(BSPC, "query", "-T", "-n", hex(window.id)))
            assert node["client"]["state"] == "floating", node
            assert node["client"]["layer"] == "above", node
            assert node["client"]["borderWidth"] == 0, node
            geometry = rectangle(window)
            x, y, width, height = geometry
            center_x = monitor["x"] + monitor["width"] / 2
            center_y = monitor["y"] + monitor["height"] / 2
            assert abs(x + width / 2 - center_x) <= 1, geometry
            assert abs(y + height / 2 - center_y) <= 1, geometry
            assert layout() == original_layout, "The launcher must not rearrange tiled windows"
            opened.append(geometry)
            if attempt == 0:
                # Keep the pointer over the search field so a launcher tooltip
                # cannot obscure the appearance captures.
                root.warp_pointer(x + width // 2, y + 42)
                connection.sync()
                time.sleep(0.3)
                capture_menu(geometry, "home-verification.png")
                # Require actual X11 focus before sending text, so it cannot reach another app.
                assert menu_has_focus(window)
                run("xdotool", "type", "--clearmodifiers", "--delay", "35", "shortcuts")
                time.sleep(0.3)
                assert menu_has_focus(window)
                capture_menu(geometry, "search-verification.png")
            close_menu()
            assert layout() == original_layout
        assert opened[0] == opened[1], opened
        results = {"shortcut_command": command, "super_key_verified": True,
                   "menu_geometry": opened[0], "screen_center": [center_x, center_y],
                   "floating_above_tiles": True, "keyboard_focus_on_open": True,
                   "search_input_sent": "shortcuts", "application_layout_unchanged": True,
                   "reopening_keeps_position_and_focus": True}
        (STATE / "verification.json").write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps(results, indent=2))
    finally:
        close_menu()
        root.warp_pointer(original_pointer.root_x, original_pointer.root_y)
        connection.sync()
        connection.close()


if __name__ == "__main__":
    main()
