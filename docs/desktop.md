# Split desktop panels

The layout keeps the existing green GTK/icon/window theme and top-panel widgets. A 28px menu bar places the Kali system menu and active application's name on the left, with workspaces, CPU/VPN indicators, network/Bluetooth tray, audio, notifications, battery and the date/time on the right. A centered 54px bottom panel contains the applications menu, existing desktop/file controls and Docklike Taskbar. The applications menu opens above the bottom panel, including when invoked with Super through the existing keyboard shortcut.

Click Kali for session and power controls. Click the active application's name for the open-window list. The label updates once per second and shows Desktop when no application is active. It uses the installed Generic Monitor plugin and `scripts/panel-active-app.py`; no additional menu-bar package is needed. The clock includes the weekday and date and opens a calendar when clicked. `top-menu-bar` in `config/panels.json` sets the system-menu title and clock format.

The bottom panel intelligently hides when a window overlaps it. Move the pointer to the bottom edge to reveal it. Docklike Taskbar combines each pinned app and its running windows into one icon, with a green running indicator. Click an open app to focus it; Shift-click starts another instance. Right-click an app to pin or unpin it. Docklike's Super shortcuts stay disabled so Super continues to open the applications menu. [Docklike Taskbar documentation](https://docs.xfce.org/panel-plugins/xfce4-docklike-plugin/start).

Install `xfce4-docklike-plugin` first, or use `bash scripts/install-packages.sh --apply desktop`. The initial pins are Mousepad, Firefox ESR and QTerminal, matching the existing primary launchers. Root Terminal remains available in the applications menu. The first apply replaces the separate launchers, Window Buttons and their separator, saving the original layout for rollback. Later applies preserve pin changes made through the dock's menu.

From an XFCE terminal in this checkout:

```sh
python3 scripts/configure-panels.py          # preview
python3 scripts/configure-panels.py --apply
python3 scripts/configure-panels.py --restore
```

Apply the appearance with `python3 scripts/style-panels.py --apply` after applying the layout. To undo both, restore the style first, then restore the panel layout.

Every apply exports the live configuration with XFCE Panel Profiles before changing it. Backups and generated profiles are under ignored `state/panels/`; keep those files for rollback. `--restore` restores the state immediately before the most recent apply. Earlier backups can be loaded with `xfce4-panel-profiles load state/panels/before-TIMESTAMP.tar.bz2`.

Edit `config/panels.json` to reproduce different heights, hiding behavior, plugin placement or initial pins. The script adapts to the current desktop dimensions, preserves existing plugin settings, and refuses unfamiliar multi-panel layouts. Run without sudo: desktop configuration belongs to your user session. Applying briefly restarts the panels.

Right-click an empty panel area and choose Panel → Panel Preferences to adjust it interactively. Official documentation: [Panel Preferences](https://docs.xfce.org/xfce/xfce4-panel/preferences), [Panel Profiles](https://docs.xfce.org/apps/xfce4-panel-profiles/start).

## Panel appearance

`config/panels.css` provides panel-only GTK overrides: a neutral translucent menu bar, compact white controls, subtle hover highlights and an unboxed clock. The top bar uses a 10% opaque tint and the dock a 16% opaque tint, with a single background layer so the wallpaper shows through. External plugin windows have transparent backgrounds, preventing the GTK theme from adding opaque blocks behind their controls. Text and icons stay fully opaque. The dock retains its rounded corners and green running indicators. It uses existing icons and fonts. The style script leaves panel positions, sizes, widget order and hiding behavior intact, and keeps any existing user GTK CSS.

```sh
python3 scripts/style-panels.py          # validate and preview
python3 scripts/style-panels.py --apply
python3 scripts/style-panels.py --restore
```

Application creates `~/.config/gtk-3.0/kali-setup-panels.css` and adds a managed import to `gtk.css`. Before writing, it backs up both files and the live panel profile under ignored `state/panels/style-backups/`. Applying briefly restarts the panels. Restore returns the CSS and native panel settings to their state immediately before the last style application, including the split layout. Run `configure-panels.py --restore` separately only when you want to undo the split layout itself.

GTK CSS is checked with the actual installed GTK parser before application. The script also verifies layout properties after restarting. To change colors or radii, edit the repository stylesheet and apply again. [XFCE panel theming reference](https://docs.xfce.org/xfce/xfce4-panel/theming).
