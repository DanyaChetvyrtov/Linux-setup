"""Read the paired brace sequences used by the BSPWM hotkey configuration."""
from pathlib import Path
import re

from shortcut_catalog import Binding

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "config/tiling-sxhkdrc"


def expand(expression):
    group = re.search(r"\{([^{}]+)\}", expression)
    if not group:
        return [expression.replace("_", "") if expression.strip() == "_" else expression]
    choices = group[1].split(",")
    if len(choices) == 1 and re.fullmatch(r"\d-\d", choices[0]):
        first, last = map(int, choices[0].split("-"))
        choices = [str(n) for n in range(first, last + 1)]
    values = []
    for choice in choices:
        choice = "" if choice == "_" else choice
        values.extend(expand(expression[:group.start()] + choice + expression[group.end():]))
    return values


def gtk_key(key):
    parts = [part.strip() for part in key.split("+")]
    modifiers = {"super": "Super", "ctrl": "Primary", "alt": "Alt", "shift": "Shift"}
    return "".join("<" + modifiers[part] + ">" for part in parts[:-1]) + parts[-1]


def bindings(path=CONFIG):
    result = []
    keys = None
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            if keys is not None:
                raise ValueError("Hotkey missing its command")
            keys = expand(line.strip())
        else:
            if keys is None:
                raise ValueError("Command missing its hotkey")
            commands = expand(line.strip())
            if len(commands) == 1:
                commands *= len(keys)
            if len(keys) != len(commands):
                raise ValueError("Hotkey and command brace sequences have different lengths")
            for key, command in zip(keys, commands):
                shortcut = gtk_key(key)
                result.append(Binding("bspwm", shortcut, command, "/bspwm/" + shortcut))
            keys = None
    if keys is not None:
        raise ValueError("Hotkey missing its command")
    return result


def active():
    return (REPO / "state/tiling/ready").exists()


def description(command):
    if command.startswith("bspc node -f "):
        direction = command.split()[-1]
        if direction.startswith(("next", "prev")):
            return "Focus the " + ("next" if direction.startswith("next") else "previous") + " window"
        return "Focus the window to the " + direction
    if command.startswith("bspc node -s "):
        return "Swap with the window to the " + command.split()[-1]
    if command.startswith("bspc node -z "):
        return "Resize the focused tile"
    if command.startswith("bspc desktop -f "):
        target = command.split()[-1].strip("'")
        if target.startswith("^"):
            return "Switch to workspace " + target[1:]
        return "Switch to the " + ("next" if target.startswith("next") else "previous") + " workspace"
    if command.startswith("bspc node -d "):
        target = command.split()[3].strip("'")
        label = "Move window to workspace " + target[1:] if target.startswith("^") else "Move window to the adjacent workspace"
        return label + (" and follow" if "--follow" in command else "")
    return {"bspc node -t '~floating'": "Toggle floating window",
            "bspc node -t '~fullscreen'": "Toggle fullscreen",
            "bspc desktop -l next": "Toggle focused-window workspace layout",
            "bspc node -c": "Close the focused window", "bspc node -g sticky": "Toggle window on all workspaces"}.get(
                command, "Restore the original XFCE window manager" if command.endswith("configure-tiling.py --restore") else "")
