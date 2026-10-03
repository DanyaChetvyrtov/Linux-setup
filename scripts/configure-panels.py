#!/usr/bin/env python3
"""Split the existing XFCE panel with a native backup and rollback on failure."""
import argparse
import datetime
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import time

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state/panels"


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def load_profile(profile):
    # Some plugins save cached settings on exit. Let them finish before loading
    # the new profile, otherwise their old values overwrite the requested ones.
    run("xfce4-panel", "--quit")
    time.sleep(0.5)
    try:
        run("xfce4-panel-profiles", "load", str(profile))
    finally:
        with (STATE / "panel-start.log").open("ab") as log:
            subprocess.Popen(["xfce4-panel"], stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, start_new_session=True)


def variant(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return f"uint32 {value}"
    if isinstance(value, str):
        return repr(value)
    raise ValueError(f"Unsupported setting: {value!r}")


def array(values):
    return "[" + ", ".join(f"<{value}>" for value in values) + "]"


def ids(value):
    return [int(x) for x in re.findall(r"<\s*(?:int32\s+)?(\d+)\s*>", value)]


def configure_dock(members, props, original, types, spec):
    """Replace separate launchers/tasks once; retain user pin edits afterward."""
    if not Path("/usr/share/xfce4/panel/plugins/docklike.desktop").is_file():
        raise RuntimeError("Install xfce4-docklike-plugin before applying this layout.")
    dock_ids = [plugin for plugin in original if types[plugin] == "docklike"]
    if len(dock_ids) > 1:
        raise ValueError("Multiple Docklike instances found; leave layout unchanged.")
    retired = {plugin for plugin in original if types[plugin] in {"launcher", "tasklist"}}
    # The separator between launchers and running windows is no longer needed.
    for index, plugin in enumerate(original):
        if types[plugin] == "tasklist" and index and types[original[index - 1]] == "separator":
            retired.add(original[index - 1])
    if dock_ids and retired:
        raise ValueError("Mixed Docklike and legacy app widgets found; leave layout unchanged.")
    if dock_ids:
        return original, types, []
    if not any(types[plugin] == "tasklist" for plugin in original):
        raise ValueError("No Window Buttons plugin found to replace; leave layout unchanged.")

    import gi
    gi.require_version("GioUnix", "2.0")
    from gi.repository import GioUnix
    pins = spec["pinned-apps"]
    for app in pins:
        if GioUnix.DesktopAppInfo.new(app + ".desktop") is None:
            raise ValueError(f"Pinned application is not installed: {app}")
    used = [int(match.group(1)) for key in props
            if (match := re.fullmatch(r"/plugins/plugin-(\d+)", key))]
    dock_id = max(used, default=0) + 1
    # Insert the combined widget where the first launcher used to be.
    position = min(original.index(plugin) for plugin in retired)
    migrated = original[:position] + [dock_id] + original[position:]
    migrated = [plugin for plugin in migrated if plugin not in retired]
    for plugin in retired:
        prefix = f"/plugins/plugin-{plugin}"
        for key in list(props):
            if key == prefix or key.startswith(prefix + "/"):
                del props[key]
    props[f"/plugins/plugin-{dock_id}"] = repr("docklike")
    types[dock_id] = "docklike"
    members[f"docklike-{dock_id}.rc"] = (
        "[user]\n"
        f"pinned={';'.join(pins)};\n"
        "forceIconSize=true\n"
        f"iconSize={spec['bottom']['icon-size']}\n"
        "indicatorStyle=1\n"
        "inactiveIndicatorStyle=1\n"
        "indicatorColor=rgb(73,211,164)\n"
        "inactiveColor=rgb(73,211,164)\n"
        "keyComboActive=false\n"
        "keyAloneActive=false\n"
        "showWindowCount=true\n"
        "noWindowsListIfSingle=true\n"
    ).encode()
    return migrated, types, sorted(retired)


def configure_menu_bar(props, top, types, spec):
    """Keep status tools, adding a functional system menu and active-app label."""
    settings = spec["top-menu-bar"]
    command = shlex.join(["python3", str(REPO / "scripts/panel-active-app.py")])
    matches = [plugin for plugin in top if types[plugin] == "genmon"
               and props.get(f"/plugins/plugin-{plugin}/command") == repr(command)]
    if len(matches) > 1:
        raise ValueError("Multiple active-app labels found; leave layout unchanged.")
    if matches:
        active_app = matches[0]
    else:
        if not Path("/usr/share/xfce4/panel/plugins/genmon.desktop").is_file():
            raise RuntimeError("The menu bar needs the installed Generic Monitor plugin.")
        used = [int(match.group(1)) for key in props
                if (match := re.fullmatch(r"/plugins/plugin-(\d+)", key))]
        active_app = max(used, default=0) + 1
        top = top + [active_app]
        types[active_app] = "genmon"
        props[f"/plugins/plugin-{active_app}"] = repr("genmon")
    for name, value in {"command": command, "use-label": False,
                        "enable-single-row": True, "font": "Cantarell Bold 10"}.items():
        props[f"/plugins/plugin-{active_app}/{name}"] = variant(value)
    props[f"/plugins/plugin-{active_app}/update-period"] = "int32 1000"

    actions = [plugin for plugin in top if types[plugin] == "actions"]
    expanders = [plugin for plugin in top if types[plugin] == "separator"
                 and props.get(f"/plugins/plugin-{plugin}/expand") == "true"]
    if len(actions) != 1 or len(expanders) != 1:
        raise ValueError("Expected one session control and one expanding separator.")
    session = actions[0]
    for name, value in {"appearance": 1, "button-title": 3,
                        "custom-title": settings["system-title"],
                        "ask-confirmation": True}.items():
        props[f"/plugins/plugin-{session}/{name}"] = variant(value)
    entries = ["+lock-screen", "+switch-user", "+separator", "+suspend",
               "-hibernate", "-hybrid-sleep", "+separator", "+shutdown",
               "+restart", "+separator", "+logout"]
    props[f"/plugins/plugin-{session}/items"] = (
        "[" + ", ".join(f"<{entry!r}>" for entry in entries) + "]")

    spacers = [plugin for plugin in top if types[plugin] == "separator"
               and plugin not in expanders]
    for plugin in spacers:
        props[f"/plugins/plugin-{plugin}/style"] = variant(0)
        props[f"/plugins/plugin-{plugin}/expand"] = "false"
    for plugin in top:
        prefix = f"/plugins/plugin-{plugin}/"
        if types[plugin] == "clock":
            props[prefix + "digital-layout"] = variant(3)
            props[prefix + "digital-time-format"] = variant(settings["clock-format"])
            props[prefix + "digital-time-font"] = variant(settings["clock-font"])
        elif types[plugin] == "systray":
            props[prefix + "size-max"] = variant(16)
            props[prefix + "symbolic-icons"] = "true"
        elif types[plugin] == "cpugraph":
            for color in ["foreground-1", "foreground-2", "foreground-3"]:
                props[prefix + color] = "[<0.88>, <0.89>, <0.92>, <1.0>]"
    remaining = [plugin for plugin in top if plugin not in
                 [session, active_app, *expanders, *spacers]]
    groups = [[plugin for plugin in remaining if types[plugin] == "pager"],
              [plugin for plugin in remaining if types[plugin] in {"cpugraph", "genmon"}],
              [plugin for plugin in remaining if types[plugin] not in
               {"pager", "cpugraph", "genmon", "clock"}],
              [plugin for plugin in remaining if types[plugin] == "clock"]]
    arranged = spacers[:1] + [session, active_app, expanders[0]]
    for index, group in enumerate(groups):
        arranged.extend(group)
        if index < len(groups) - 1:
            arranged.extend(spacers[index + 1:index + 2])
    arranged.extend(spacers[len(groups):])
    assert sorted(arranged) == sorted(top), "Menu bar lost a panel widget"
    return arranged


def build_profile(source, target, spec, width, height):
    with tarfile.open(source) as archive:
        members = {m.name: archive.extractfile(m).read()
                   for m in archive.getmembers() if m.isfile()}
    props = dict(line.split(" ", 1) for line in members["config.txt"].decode().splitlines()
                 if line.strip())
    panels = ids(props["/panels"])
    if not panels or len(panels) > 2:
        raise ValueError("Expected one panel or the two panels created by this script.")
    if len(panels) == 2:
        if not (STATE / "last-apply.json").exists():
            raise ValueError("Existing two-panel layout has no setup record; leave it unchanged.")
        previous = json.loads((STATE / "last-apply.json").read_text())
        if panels != [previous["top"], previous["bottom"]]:
            raise ValueError("Panel IDs changed since the last setup; leave them unchanged.")
    top_id = panels[0]
    bottom_id = panels[1] if len(panels) == 2 else max(panels) + 1
    original = []
    for panel in panels:
        original.extend(ids(props[f"/panels/panel-{panel}/plugin-ids"]))
    types = {plugin: props[f"/plugins/plugin-{plugin}"].strip("'\"") for plugin in original}
    retired = []
    if "docklike" in spec["bottom-plugins"]:
        original, types, retired = configure_dock(members, props, original, types, spec)
    bottom = [p for p in original if types[p] in spec["bottom-plugins"]]
    if not any(types[p] in {"tasklist", "docklike"} for p in bottom):
        raise ValueError("No application taskbar found; leave layout unchanged.")
    # Retain launchers and their existing .desktop files. Give the running apps
    # one separator after the launchers without adding another panel plugin.
    task = next((p for p in original if types[p] == "tasklist"), None)
    if task is not None:
        task_index = original.index(task)
        if task_index and types[original[task_index - 1]] == "separator":
            separator = original[task_index - 1]
            bottom.insert(bottom.index(task), separator)
    top = [p for p in original if p not in bottom]
    assert sorted(top + bottom) == sorted(original)
    if "top-menu-bar" in spec:
        top = configure_menu_bar(props, top, types, spec)
    props["/panels"] = array([top_id, bottom_id])
    for panel, settings, plugins in [(top_id, spec["top"], top), (bottom_id, spec["bottom"], bottom)]:
        prefix = f"/panels/panel-{panel}/"
        for name, value in settings.items():
            props[prefix + name] = variant(value)
        props[prefix + "plugin-ids"] = array(plugins)
    props[f"/panels/panel-{bottom_id}/position"] = variant(f"p=10;x={width // 2};y={height}")
    for plugin in original:
        kind = types[plugin]
        if kind == "cpugraph":
            props[f"/plugins/plugin-{plugin}/size"] = f"int32 {spec['cpu-graph-width']}"
        if kind == "tasklist":
            props[f"/plugins/plugin-{plugin}/show-labels"] = "false"
            props[f"/plugins/plugin-{plugin}/show-handle"] = "false"
            props[f"/plugins/plugin-{plugin}/grouping"] = "uint32 1"
    members["config.txt"] = "\n".join(f"{key} {value}" for key, value in sorted(props.items())).encode()
    with tarfile.open(target, "w:bz2") as archive:
        for name, data in members.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return {"top": top_id, "bottom": bottom_id, "top-plugins": top,
            "bottom-plugins": bottom, "retired-plugins": retired}


def apply(spec):
    # Check session access before creating any files or changing settings.
    run("xfconf-query", "-c", "xfce4-panel", "-p", "/panels")
    output = run("xrandr", "--current")
    match = re.search(r"current (\d+) x (\d+)", output)
    if not match:
        raise RuntimeError("Could not determine the desktop size.")
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    STATE.mkdir(parents=True, exist_ok=True)
    backup = STATE / f"before-{stamp}.tar.bz2"
    target = STATE / f"split-{stamp}.tar.bz2"
    run("xfce4-panel-profiles", "save", str(backup))
    result = build_profile(backup, target, spec, *map(int, match.groups()))
    try:
        load_profile(target)
        # A restart is asynchronous; verify the actual stored layout afterward.
        time.sleep(2)
        actual = run("xfconf-query", "-c", "xfce4-panel", "-p", "/panels")
        found = [int(x) for x in actual.splitlines() if x.isdigit()]
        if found != [result["top"], result["bottom"]]:
            raise RuntimeError(f"Unexpected panel IDs: {actual}")
        for name in ["top", "bottom"]:
            value = run("xfconf-query", "-c", "xfce4-panel", "-p",
                        f"/panels/panel-{result[name]}/plugin-ids")
            plugins = [int(x) for x in value.splitlines() if x.isdigit()]
            if plugins != result[name + "-plugins"]:
                raise RuntimeError(f"Unexpected {name} plugin order: {value}")
    except Exception:
        print("Applying layout failed; restoring", backup)
        load_profile(backup)
        raise
    result.update({"backup": str(backup), "profile": str(target)})
    (STATE / "last-apply.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Applied top status bar and bottom application panel.")
    print("Backup:", backup)
    print("Restore: python3 scripts/configure-panels.py --restore")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    spec = json.loads((REPO / "config/panels.json").read_text())
    if args.restore:
        record = json.loads((STATE / "last-apply.json").read_text())
        load_profile(record["backup"])
        print("Restored:", record["backup"])
    elif args.apply:
        apply(spec)
    else:
        print(f"Preview: full-width {spec['top']['size']}px menu bar; centered {spec['bottom']['size']}px bottom app panel.")
        print("Docklike combines pinned apps and running windows; bottom intelligently hides.")
        print("Install xfce4-docklike-plugin first. Existing Docklike pins are retained.")
        print("Applying panel settings needs no administrator privileges. Use --apply in your XFCE session.")


if __name__ == "__main__":
    main()
