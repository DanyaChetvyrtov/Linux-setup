# Split desktop panels

The layout keeps the existing green GTK/icon/window theme and top-panel widgets. A 28px menu bar places the Kali system menu and active application's name on the left, with workspaces, CPU/VPN indicators, network/Bluetooth tray, audio, notifications, battery and the date/time on the right. A centered 64px bottom panel contains the applications menu, existing desktop/file controls and Docklike Taskbar. Clicking the panel's applications-menu button opens it above the bottom panel. Super opens the menu at the screen center.

The existing Super-key mapping sends Ctrl+Escape. `python3 scripts/configure-launcher.py --apply` sets that shortcut to Whisker's native centered popup and reloads BSPWM's menu-specific rule. The menu floats above the tiled windows and receives keyboard focus immediately, so you can type into search as soon as it opens. Opening it does not move or resize application windows. Its position is set each time it opens. The Shortcuts app describes the centered menu under the Ctrl+Escape binding. Shortcut backups live under `state/launcher/backups/`; `python3 scripts/configure-launcher.py --restore` returns the previous shortcut positioning.

`python3 scripts/verify-launcher.py` checks the live Super-key popup twice, verifies its centered position and keyboard focus, and types a search query. It closes the popup afterward and saves its results and a search screenshot under `state/launcher/`. The isolated tiling check also verifies the menu's floating and focus rules.

The launcher uses a charcoal surface, a spacious search field, a sidebar with green selection highlights, and a grid of 48px application icons. `config/launcher.css` scopes its GTK styling to Whisker Menu; `config/launcher.json` sets the native menu dimensions and view options. The default size is 860 × 620. Click a category to browse it, or start typing immediately after pressing Super to search.

`python3 scripts/style-launcher.py` validates the appearance without applying it. Use `--apply` to install it in the current XFCE session; the panels briefly restart to load the CSS. Favorites and panel layout are verified after application. Backups live under `state/launcher/style-backups/`; `--restore` returns the appearance and changed menu settings to their state before the first upgrade, preserving other GTK CSS. The launcher verifier saves both `home-verification.png` and `search-verification.png` for visual inspection.

The XFCE Screensaver password panel follows the same charcoal colors and green accents, with an 18px rounded card, larger password field, framed avatar and a clear green Unlock button. `config/lockscreen.css` targets the native panel's `#login_window.keycap` selector. `python3 scripts/style-lockscreen.py` validates the stylesheet; `--apply` installs it for the next unlock dialog. No screensaver restart is required. Backups live under `state/lockscreen/backups/`; `--restore` returns the previous appearance while preserving the launcher, panels and later GTK CSS additions.

`python3 scripts/verify-lockscreen.py --mode candidate` previews the repository stylesheet, and the default mode verifies the installed style. The script loads the UI resource from the installed XFCE Screensaver into an isolated Xvfb display and saves normal and status-message previews under `state/lockscreen/`. It checks the native masked password field, input focus, Unlock button and status area. This is a visual check of native widgets; it does not invoke authentication or lock the active session.

Desktop icons are hidden so the wallpaper stays clear. Open applications with Super or the dock, and open your files through the file manager. `python3 scripts/configure-desktop-icons.py --apply` saves the previous XFCE icon setting under `state/desktop-icons/backups/` and disables desktop icons immediately and at future logins. `python3 scripts/configure-desktop-icons.py --restore` brings back the previous icon display. Desktop files and applications remain available.

Click Kali for session and power controls. Click the active application's name for the open-window list. The label updates once per second and shows Desktop when no application is active. It uses the installed Generic Monitor plugin and `scripts/panel-active-app.py`; no additional menu-bar package is needed. The clock includes the weekday and date and opens a calendar when clicked. `top-menu-bar` in `config/panels.json` sets the system-menu title and clock format.

The bottom panel uses XFCE's **Always** automatic hiding (`autohide-behavior: 2`). It stays hidden when application focus changes, even when the focused window is above the dock area. Hover over the bottom edge beneath the centered dock to reveal it; moving away hides it again. Docklike Taskbar combines each pinned app and its running windows into one icon, with a green running indicator. Click an open app to focus it; Shift-click starts another instance. Right-click an app to pin or unpin it. Docklike's Super shortcuts stay disabled so Super continues to open the applications menu. [Docklike Taskbar documentation](https://docs.xfce.org/panel-plugins/xfce4-docklike-plugin/start).

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

## Dock magnification and motion

Hovering an icon enlarges it from 40px to 52px and lifts it slightly, with 180 ms easing in both directions. Button positions and click areas stay fixed. The panel reserves enough height and spacing for the enlarged icons. GTK's [animated icon transforms](https://docs.gtk.org/gtk3/css-properties.html) apply to Docklike app icons and the existing dock controls, including the applications menu.

The dock stays hidden until the pointer enters its bottom-edge sensor, independently of application focus. Moving to that edge reveals it after a short delay; moving away allows 450 ms before hiding. Picom eases position changes over 220 ms, including the reveal that XFCE normally performs immediately. The rule matches the main panel window taller than 40px, excluding the top bar and the small edge sensor. It uses Picom 13's [position animation trigger](https://github.com/yshui/picom/blob/v13/man/picom.1.adoc); this trigger is experimental, and its rendered hide/show positions were verified on this workstation. No blur or additional background process is required. Maximized windows allow edge reveal; true fullscreen windows still cover the panel.

```sh
python3 scripts/configure-dock.py          # Preview
python3 scripts/configure-dock.py --apply  # Apply size, styling, and compositor motion
python3 scripts/configure-dock.py --restore
```

The supervised Picom compositor must already be running. Apply saves existing GTK styles, the changed bottom-panel properties, and a compositor rollback file under ignored `state/dock/backups/`. Restore puts back those styles and properties and reloads the saved compositor configuration; it preserves app pins and unrelated panel properties. On the initial apply, the compositor rollback removes only the new dock-motion block. Subsequent applies back up the current compositor file. Restoration leaves the repository's panel CSS and JSON defaults available for reapplying the upgrade.

Hover timing and magnification live in `config/panels.css`; motion timing lives in `config/dock-motion.conf`. Applying regenerates the marked dock block in `config/picom.conf`, so the upgrade can be reapplied after restoring. Existing Docklike pins, wallpaper cycling, and hotkeys are retained. Local rendered-frame measurements are saved in `state/dock/verification.json`.

## Panel appearance

`config/panels.css` provides panel-only GTK overrides: a neutral translucent menu bar, compact white controls, subtle hover highlights and an unboxed clock. The top bar uses a 10% opaque tint and the dock a 16% opaque tint, with a single background layer so the wallpaper shows through. External plugin windows have transparent backgrounds, preventing the GTK theme from adding opaque blocks behind their controls. Text and icons stay fully opaque. The dock retains its rounded corners and green running indicators. It uses existing icons and fonts. The style script leaves panel positions, sizes, widget order and hiding behavior intact, and keeps any existing user GTK CSS.

```sh
python3 scripts/style-panels.py          # validate and preview
python3 scripts/style-panels.py --apply
python3 scripts/style-panels.py --restore
```

Application creates `~/.config/gtk-3.0/kali-setup-panels.css` and adds a managed import to `gtk.css`. Before writing, it backs up both files and the live panel profile under ignored `state/panels/style-backups/`. Applying briefly restarts the panels. Restore returns the CSS and native panel settings to their state immediately before the last style application, including the split layout. Run `configure-panels.py --restore` separately only when you want to undo the split layout itself.

GTK CSS is checked with the actual installed GTK parser before application. The script also verifies layout properties after restarting. To change colors or radii, edit the repository stylesheet and apply again. [XFCE panel theming reference](https://docs.xfce.org/xfce/xfce4-panel/theming).

## Tiled window spacing

The active setup uses [automatic tiling with BSPWM](tiling.md), which includes matching inner and outer gaps, floating windows, and keyboard controls. The former XFWM half-screen gap helper has been disabled. The commands below remain available for the earlier manual-snapping setup; restore BSPWM before applying them.

```sh
python3 scripts/configure-window-gaps.py            # preview
python3 scripts/configure-window-gaps.py --apply
python3 scripts/configure-window-gaps.py --restore
```

Change `inner_gap` in `config/window-gaps.json` and apply again to adjust the spacing. A small Python Xlib listener runs in the XFCE/X11 user session and starts at login. It observes native XFWM tile geometry and requests a smaller rectangle after snapping finishes. It accounts for window decorations and CSD shadows. Floating windows, dialogs, maximized windows and fullscreen windows are excluded. Applications with resize increments may leave a slightly wider gap; windows whose minimum size prevents shrinking retain their native tile size.

XFWM 4.20 has no native gap setting ([tiling implementation](https://github.com/xfce-mirror/xfwm4/blob/xfwm4-4.20.0/src/client.c#L3093)). The helper recognizes windows occupying the native half/quarter rectangles, including windows already tiled when it starts. A manually positioned window matching one of those rectangles receives the same treatment. It responds to events and waits for pointer release before adjusting a dragged window.

Apply backs up the helper's autostart entry and active settings under ignored `state/window-gaps/backups/`. Restore stops the listener, returns unchanged gapped tiles to their original rectangles, and restores the configuration from before the last apply. Windows moved or resized afterward keep their new positions. `--stop` only stops the listener, keeping the current positions and login autostart entry.
