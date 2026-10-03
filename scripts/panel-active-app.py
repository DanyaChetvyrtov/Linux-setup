#!/usr/bin/env python3
"""Show the active application's name in the XFCE menu bar."""
import html
import re
import subprocess


NAMES = {
    "xfdesktop": "Desktop",
    "xfce4-panel": "Desktop",
    "wrapper-2.0": "Desktop",
    "qterminal": "Terminal",
    "kitty": "kitty",
    "mousepad": "Mousepad",
    "thunar": "Files",
    "firefox-esr": "Firefox",
    "firefox": "Firefox",
    "telegramdesktop": "Telegram",
    "org.telegram.desktop": "Telegram",
    "gnome-system-monitor": "System Monitor",
    "spotify": "Spotify",
    "happ": "Happ",
}


def active_app():
    try:
        active = subprocess.run(
            ["xprop", "-root", "_NET_ACTIVE_WINDOW"], check=True,
            capture_output=True, text=True, timeout=1).stdout
        match = re.search(r"0x[0-9a-fA-F]+", active)
        if not match or int(match.group(), 16) == 0:
            return "Desktop"
        properties = subprocess.run(
            ["xprop", "-id", match.group(), "WM_CLASS"], check=True,
            capture_output=True, text=True, timeout=1).stdout
        classes = re.findall(r'"([^"\n]*)"', properties)
        if not classes:
            return "Desktop"
        name = classes[-1]
        return NAMES.get(name.lower(), name[:32])
    except (OSError, subprocess.SubprocessError):
        return "Desktop"


if __name__ == "__main__":
    name = html.escape(active_app())
    print(f"<txt><b>{name}</b></txt>"
          "<txtclick>xfdesktop --windowlist</txtclick>"
          "<tool>Switch between open windows</tool>")
