#!/usr/bin/env python3
"""Verify physical-key English/Russian input and Super+Space in a temporary GTK window."""
import ctypes
import json
from pathlib import Path
import time

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
from gi.repository import Gdk, Gtk
from Xlib import display, X, XK
from Xlib.ext import xtest

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/keyboard"


class XkbState(ctypes.Structure):
    # XkbStateRec from the installed X11/extensions/XKBstr.h.
    _fields_ = [("group", ctypes.c_ubyte), ("locked_group", ctypes.c_ubyte),
                ("base_group", ctypes.c_ushort), ("latched_group", ctypes.c_ushort),
                ("mods", ctypes.c_ubyte), ("base_mods", ctypes.c_ubyte),
                ("latched_mods", ctypes.c_ubyte), ("locked_mods", ctypes.c_ubyte),
                ("compat_state", ctypes.c_ubyte), ("grab_mods", ctypes.c_ubyte),
                ("compat_grab_mods", ctypes.c_ubyte), ("lookup_mods", ctypes.c_ubyte),
                ("compat_lookup_mods", ctypes.c_ubyte), ("ptr_buttons", ctypes.c_ushort)]


def main():
    assert Gtk.init_check()[0], "The input check must connect to the desktop"
    native = ctypes.CDLL("libX11.so.6")
    native.XOpenDisplay.argtypes = [ctypes.c_char_p]
    native.XOpenDisplay.restype = ctypes.c_void_p
    native.XCloseDisplay.argtypes = [ctypes.c_void_p]
    native.XkbGetState.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(XkbState)]
    native.XkbGetState.restype = ctypes.c_int
    native.XkbLockGroup.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
    native.XkbLockGroup.restype = ctypes.c_int
    native.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    xdisplay = native.XOpenDisplay(None)
    assert xdisplay, "XKB must connect to the desktop"
    connection = display.Display()
    original_focus = connection.get_input_focus().focus

    def state():
        result = XkbState()
        assert native.XkbGetState(xdisplay, 0x0100, ctypes.byref(result)) == 0
        return result

    def lock_group(group):
        assert native.XkbLockGroup(xdisplay, 0x0100, group)
        native.XSync(xdisplay, 0)

    def pump(duration=0.15):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            while Gtk.events_pending():
                Gtk.main_iteration()
            time.sleep(0.01)

    initial = state()
    assert initial.base_mods == 0, "Release any held modifier keys before the input check"
    window = Gtk.Window(title="Keyboard input check")
    window.set_type_hint(Gdk.WindowTypeHint.DIALOG)
    window.set_default_size(480, 160)
    window.set_position(Gtk.WindowPosition.CENTER)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=20)
    box.pack_start(Gtk.Label(label="Checking English and Russian keyboard input…"), False, False, 0)
    entry = Gtk.Entry()
    box.pack_start(entry, False, False, 0)
    status = Gtk.Label(label="Super + Space switches language.")
    box.pack_start(status, False, False, 0)
    window.add(box)

    def has_focus():
        focused = connection.get_input_focus().focus
        while hasattr(focused, "id") and focused.id != connection.screen().root.id:
            if focused.id == window.get_window().get_xid():
                return True
            focused = focused.query_tree().parent
        return False

    def press(code):
        assert has_focus() and entry.has_focus(), "Input must reach only the temporary check window"
        xtest.fake_input(connection, X.KeyPress, code)
        xtest.fake_input(connection, X.KeyRelease, code)
        connection.sync()
        pump(0.04)

    def type_physical(text):
        entry.set_text("")
        for letter in text:
            press(connection.keysym_to_keycode(XK.string_to_keysym(letter)))
        pump()
        return entry.get_text()

    def switch():
        assert has_focus(), "Layout-switch verification requires the check window's focus"
        super_code = connection.keysym_to_keycode(XK.string_to_keysym("Super_L"))
        space_code = connection.keysym_to_keycode(XK.string_to_keysym("space"))
        xtest.fake_input(connection, X.KeyPress, super_code)
        try:
            xtest.fake_input(connection, X.KeyPress, space_code)
            xtest.fake_input(connection, X.KeyRelease, space_code)
        finally:
            xtest.fake_input(connection, X.KeyRelease, super_code)
            connection.sync()
        pump()

    try:
        window.show_all()
        entry.grab_focus()
        window.present()
        deadline = time.monotonic() + 5
        while not has_focus() and time.monotonic() < deadline:
            pump(0.05)
        assert has_focus() and entry.has_focus(), "The check window must receive keyboard focus"
        lock_group(0)
        english = type_physical("hello")
        assert english.casefold() == "hello", english
        switch()
        assert state().group == 1, "Super+Space must select Russian"
        # Raw keycodes for the Latin-key positions g h b d t n should spell привет.
        russian = type_physical("ghbdtn")
        assert russian.casefold() == "привет", russian
        status.set_text(f"English: {english} · Russian: {russian}")
        pump()
        STATE.mkdir(parents=True, exist_ok=True)
        width, height = window.get_size()
        image = Gdk.pixbuf_get_from_window(window.get_window(), 0, 0, width, height)
        if image:
            image.savev(str(STATE / "verification.png"), "png", [], [])
        switch()
        assert state().group == 0, "Super+Space must return to English"
        results = {"english_input": english, "russian_input": russian,
                   "physical_keycodes_verified": True, "super_space_switches_both_directions": True}
        (STATE / "verification.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        lock_group(initial.locked_group)
        window.destroy()
        pump()
        if hasattr(original_focus, "id"):
            connection.set_input_focus(original_focus, X.RevertToPointerRoot, X.CurrentTime)
            connection.sync()
        connection.close()
        native.XCloseDisplay(xdisplay)


if __name__ == "__main__":
    main()
