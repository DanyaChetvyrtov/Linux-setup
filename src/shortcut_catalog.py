"""Descriptions and annotation storage rules for the XFCE shortcut viewer."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shlex


@dataclass(frozen=True)
class Binding:
    provider: str
    shortcut: str
    command: str
    property: str


def extract_bindings(provider, properties, base):
    bindings = []
    for path, command in properties.items():
        if not path.startswith(base + "/") or not isinstance(command, str):
            continue
        shortcut = path[len(base) + 1:]
        if not shortcut or shortcut == "override" or "/" in shortcut or not command.strip():
            continue
        bindings.append(Binding(provider, shortcut, command, path))
    return bindings


def annotation_path(binding):
    identity = (binding.provider + "\0" + binding.shortcut).encode()
    return "/descriptions/" + hashlib.sha256(identity).hexdigest()


def read_annotation(binding, encoded):
    if not encoded:
        return None
    try:
        saved = json.loads(encoded)
    except (ValueError, TypeError):
        return None
    if not isinstance(saved, dict) or saved.get("command") != binding.command:
        return None
    description = saved.get("description")
    return description if isinstance(description, str) and description.strip() else None


WINDOW_DESCRIPTIONS = {
    "above_key": "Keep the window above other windows",
    "add_workspace_key": "Add a workspace",
    "cancel_key": "Cancel a window move or resize",
    "close_window_key": "Close the window",
    "cycle_windows_key": "Switch to the next window",
    "cycle_reverse_windows_key": "Switch to the previous window",
    "del_workspace_key": "Remove the last workspace",
    "down_key": "Move downward during a window move or resize",
    "down_workspace_key": "Switch to the workspace below",
    "fullscreen_key": "Toggle fullscreen",
    "hide_window_key": "Minimize the window",
    "left_key": "Move left during a window move or resize",
    "left_workspace_key": "Switch to the workspace on the left",
    "lower_window_key": "Send the window behind other windows",
    "maximize_window_key": "Toggle maximized window",
    "move_window_down_workspace_key": "Move the window to the workspace below",
    "move_window_left_workspace_key": "Move the window to the workspace on the left",
    "move_window_right_workspace_key": "Move the window to the workspace on the right",
    "move_window_up_workspace_key": "Move the window to the workspace above",
    "move_window_key": "Start moving the window",
    "move_window_next_workspace_key": "Move the window to the next workspace",
    "move_window_prev_workspace_key": "Move the window to the previous workspace",
    "move_window_to_monitor_down_key": "Move the window to the monitor below",
    "move_window_to_monitor_left_key": "Move the window to the monitor on the left",
    "move_window_to_monitor_right_key": "Move the window to the monitor on the right",
    "move_window_to_monitor_up_key": "Move the window to the monitor above",
    "popup_menu_key": "Open the window menu",
    "raise_window_key": "Bring the window in front of other windows",
    "resize_window_key": "Start resizing the window",
    "right_key": "Move right during a window move or resize",
    "right_workspace_key": "Switch to the workspace on the right",
    "show_desktop_key": "Show or hide the desktop",
    "stick_window_key": "Show the window on all workspaces",
    "switch_window_key": "Switch windows",
    "tile_down_key": "Tile the window to the bottom half",
    "tile_down_left_key": "Tile the window to the bottom-left corner",
    "tile_down_right_key": "Tile the window to the bottom-right corner",
    "tile_left_key": "Tile the window to the left half",
    "tile_right_key": "Tile the window to the right half",
    "tile_up_key": "Tile the window to the top half",
    "tile_up_left_key": "Tile the window to the top-left corner",
    "tile_up_right_key": "Tile the window to the top-right corner",
    "up_key": "Move upward during a window move or resize",
    "up_workspace_key": "Switch to the workspace above",
}


def default_description(binding, catalog):
    configured = catalog.get(binding.provider, {}).get(binding.command)
    if isinstance(configured, str):
        return configured
    command = binding.command
    if binding.provider == "xfwm4":
        match = re.fullmatch(r"(move_window_)?workspace_(\d+)_key", command)
        if match:
            return ("Move the window to workspace " if match[1] else "Switch to workspace ") + match[2]
        return WINDOW_DESCRIPTIONS.get(command, "")
    try:
        args = shlex.split(command)
    except ValueError:
        return ""
    if not args:
        return ""
    executable = Path(args[0]).name
    if executable == "exo-open" and "--launch" in args:
        index = args.index("--launch") + 1
        return {"FileManager": "Open the file manager", "WebBrowser": "Open the web browser",
                "TerminalEmulator": "Open a terminal", "MailReader": "Open the mail application"}.get(
                    args[index] if index < len(args) else "", "")
    if executable == "xfdesktop" and "--next" in args:
        return "Change to the next wallpaper"
    if executable == "xfce4-popup-whiskermenu":
        return "Open the applications menu" + (" at the pointer" if "--pointer" in args else "")
    if executable == "xfce4-screenshooter":
        region = next((label for flag, label in [("--region", "a selected area"),
                      ("--window", "the active window"), ("--fullscreen", "the whole screen")]
                      if flag in args), None)
        if region:
            return "Capture " + region + (" to the clipboard" if "--clipboard" in args else "")
        return "Open the screenshot tool"
    if executable == "pkexec" and len(args) > 1 and Path(args[1]).name == "x-terminal-emulator":
        return "Open an administrator terminal"
    return {"xfce4-session-logout": "Show logout and power options", "xfrun4": "Run a command",
            "xflock4": "Lock the screen", "xfce4-taskmanager": "Open the task manager",
            "xfce4-appfinder": "Find an application", "mate-calc": "Open the calculator",
            "xfce4-display-settings": "Configure displays", "xfce4-find-cursor": "Highlight the mouse pointer",
            "xkill": "Select an unresponsive window to force close"}.get(executable, "")
