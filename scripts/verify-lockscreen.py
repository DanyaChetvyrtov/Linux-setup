#!/usr/bin/env python3
"""Render the installed XFCE lock-screen widgets on an isolated display for review."""
import argparse
import datetime
import json
import os
from pathlib import Path
import pwd
import select
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/lockscreen"
RESOURCE = "/org/xfce/screensaver/xfce4-screensaver-dialog.ui"
DIALOG = "/usr/libexec/xfce4-screensaver-dialog"


def preferences(channel):
    path = Path.home() / f".config/xfce4/xfconf/xfce-perchannel-xml/{channel}.xml"
    return ET.parse(path).getroot() if path.exists() else None


def render(mode):
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gdk, GdkPixbuf, Gtk
    assert Gtk.init_check()[0], "The preview must connect to its virtual display"
    settings = Gtk.Settings.get_default()
    native = preferences("xsettings")
    for name, prop, default in (("ThemeName", "gtk-theme-name", "Kali-Green-Dark"),
                                ("IconThemeName", "gtk-icon-theme-name", "Flat-Remix-Green-Dark")):
        item = native.find(f"./property[@name='Net']/property[@name='{name}']") if native is not None else None
        settings.set_property(prop, item.get("value") if item is not None else default)
    if mode == "candidate":
        provider = Gtk.CssProvider()
        errors = []
        provider.connect("parsing-error", lambda _provider, _section, error: errors.append(str(error)))
        provider.load_from_path(str(REPO / "config/lockscreen.css"))
        assert not errors, errors
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
    xml = subprocess.run(["gresource", "extract", DIALOG, RESOURCE],
                         check=True, capture_output=True, text=True, timeout=10).stdout
    builder = Gtk.Builder.new_from_string(xml, -1)
    overlay = builder.get_object("lock-overlay")
    panel = builder.get_object("lock-panel")
    card = builder.get_object("login_window")
    entry = builder.get_object("auth-prompt-entry")
    unlock = builder.get_object("auth-unlock-button")
    panel.set_halign(Gtk.Align.FILL)
    panel.set_valign(Gtk.Align.START)
    overlay.add_overlay(panel)
    card.set_halign(Gtk.Align.CENTER)
    card.set_valign(Gtk.Align.CENTER)
    overlay.add_overlay(card)
    account = pwd.getpwuid(os.getuid())
    realname = account.pw_gecos.split(",")[0] or account.pw_name
    from gi.repository import GLib
    builder.get_object("auth-realname-label").set_markup(
        '<span size="x-large">' + GLib.markup_escape_text(realname) + '</span>')
    builder.get_object("auth-hostname-label").set_text(os.uname().nodename)
    builder.get_object("auth-date-time-label").set_text(datetime.datetime.now().strftime("%A %d %B, %H:%M"))
    face = Path.home() / ".face"
    if face.exists():
        builder.get_object("auth-face-image").set_from_pixbuf(
            GdkPixbuf.Pixbuf.new_from_file_at_scale(str(face), 80, 80, True))
    desktop = preferences("xfce4-desktop")
    images = [item for item in desktop.findall(".//property[@name='last-image']") if item.get("value")] if desktop is not None else []
    wallpaper = Path(images[0].get("value")) if images else Path("/usr/share/desktop-base/kali-theme/login/background")
    if not wallpaper.is_file():
        wallpaper = Path("/usr/share/desktop-base/kali-theme/login/background")
    builder.get_object("lock-image").set_from_pixbuf(
        GdkPixbuf.Pixbuf.new_from_file_at_scale(str(wallpaper), 1280, 720, False))
    window = Gtk.Window()
    window.set_decorated(False)
    window.set_default_size(1280, 720)
    window.add(overlay)
    window.show_all()
    # Populate the same UI state as the initial native password prompt.
    builder.get_object("auth-logout-button").hide()
    builder.get_object("keyboard-toggle").show()
    builder.get_object("greeter_infobar").hide()
    entry.show()
    entry.grab_focus()
    window.set_focus(entry)
    assert not entry.get_visibility(), "Password text must be masked"
    assert entry.get_input_purpose() == Gtk.InputPurpose.PASSWORD
    assert window.get_focus() == entry, "The password field must retain keyboard focus"
    assert unlock.get_visible() and unlock.get_sensitive()

    def flush():
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            while Gtk.events_pending():
                Gtk.main_iteration()
            time.sleep(0.01)

    def capture(filename):
        flush()
        image = Gdk.pixbuf_get_from_window(window.get_window(), 0, 0, 1280, 720)
        assert image, "The native lock-screen preview must render"
        image.savev(str(STATE / filename), "png", [], [])

    capture(f"preview-{mode}.png")
    card_rect = card.get_allocation()
    field_rect = entry.get_allocation()
    button_rect = unlock.get_allocation()
    if mode != "before":
        background = card.get_style_context().get_background_color(Gtk.StateFlags.NORMAL)
        assert [round(value * 255) for value in (background.red, background.green, background.blue)] == [23, 28, 36]
        assert field_rect.height >= 44 and button_rect.height >= 44, "Input controls must have generous height"
    # Review the native status area as well as the empty password prompt.
    status = builder.get_object("auth-status-label")
    status.set_text("Incorrect password. Please try again.")
    status.show()
    builder.get_object("infobar-content_area").show()
    builder.get_object("greeter_infobar").show()
    capture(f"preview-{mode}-status.png")
    assert status.get_visible() and status.get_allocation().height > 0
    results = {"preview_mode": mode, "native_ui_resource": RESOURCE,
               "isolated_display": True, "password_masked": True,
               "password_field_focus": True, "unlock_button_available": True,
               "status_message_visible": True,
               "card_size": [card_rect.width, card_rect.height],
               "password_field_height": field_rect.height,
               "unlock_button_height": button_rect.height}
    (STATE / f"verification-{mode}.json").write_text(json.dumps(results, indent=2) + "\n")
    window.destroy()
    print(json.dumps(results, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("before", "candidate", "installed"), default="installed")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True)
    if args.worker:
        render(args.mode)
        return
    xvfb = shutil.which("Xvfb") or str(REPO / "state/tiling/packages/xvfb/usr/bin/Xvfb")
    if not Path(xvfb).is_file():
        raise RuntimeError("The existing isolated-display Xvfb binary is unavailable.")
    env = os.environ.copy()
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/tmp/kali-lockscreen-preview-no-session-bus"
    env["NO_AT_BRIDGE"] = "1"
    env.pop("GTK_MODULES", None)
    env.pop("GTK_THEME", None)
    env.pop("XAUTHORITY", None)
    read_fd, write_fd = os.pipe()
    with tempfile.TemporaryDirectory(prefix="kali-lockscreen-preview-") as directory:
        with (Path(directory) / "xvfb.log").open("w+") as log:
            process = subprocess.Popen([xvfb, "-displayfd", str(write_fd), "-screen", "0", "1280x720x24",
                                        "-nolisten", "tcp"], pass_fds=(write_fd,), stdout=log, stderr=log)
            os.close(write_fd)
            try:
                if not select.select([read_fd], [], [], 5)[0]:
                    raise RuntimeError("The isolated preview display could not start.")
                number = os.read(read_fd, 100).decode().strip()
                if not number:
                    log.seek(0)
                    raise RuntimeError("The isolated display failed: " + log.read(1800))
                env["DISPLAY"] = ":" + number
                subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", "--mode", args.mode],
                               env=env, check=True, timeout=20)
            finally:
                os.close(read_fd)
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
