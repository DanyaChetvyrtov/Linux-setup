# Automatic tiling within XFCE

BSPWM manages the windows while XFCE continues to provide the panels, dock, application launchers, wallpaper, and four-finger workspace gestures. Opening an app splits the layout; closing an app gives that space back. The binary tree is the same family of layout as [Hyprland's dwindle layout](https://wiki.hypr.land/Configuring/Layouts/Dwindle-Layout/). This is an X11 setup using BSPWM and Picom. An actual Hyprland session would use Wayland and a different desktop configuration.

Tiled windows have 12px gaps between them and around the usable screen, with 2px green borders. XFWM title bars give way to thin borders; apps with their own title bars retain them. Picom rounds application corners to 8px. Dialogs, authentication prompts, audio controls, and desktop settings float. The top panel's reserved area stays clear, and the dock stays hidden until its bottom-edge area is hovered. Each of the four workspaces has its own layout.

The bottom panel appears above tiled and floating application windows when revealed. `scripts/start-panel-stacking.py` keeps XFCE's unmanaged dock windows in that position as windows open, gain focus, or switch workspaces. It changes only stacking; the panel retains its size, hiding behavior, and reserved space. Fullscreen windows and application menus remain above the panel. `config/bspwmrc` starts one listener per X screen at login and on reload; it exits when BSPWM is replaced. Reapply the tiling setup to activate this fix in an existing session.

## Apply and restore

```sh
python3 scripts/configure-tiling.py          # preview
python3 scripts/configure-tiling.py --apply
python3 scripts/configure-tiling.py --restore
```

Apply activates tiling in the current XFCE/X11 session and sets XFCE's window-manager startup command for subsequent logins. Existing applications stay open and return to their workspaces. The earlier half-screen gap helper is disabled before migrating. Keep this repository at its current path.

Backups live under ignored `state/tiling/backups/`. Restore returns the original XFWM startup command, compositor configuration, and the saved positions and workspaces of surviving windows. Later applies reload the tiling settings and hotkeys while retaining the original rollback. **Super+Ctrl+Escape** runs the same restore command. If BSPWM or its hotkey daemon exits unexpectedly, the supervisor starts XFWM so the desktop remains usable.

`config/bspwmrc` controls gaps, borders, splitting, focus, floating rules, and pointer behavior. `config/tiling-sxhkdrc` controls window shortcuts; apply again after editing either file. XFCE's existing application shortcuts, including terminal, browser, file manager, wallpaper, and screenshots, remain in XFCE. The **Shortcuts** viewer shows the active tiling bindings and accepts custom descriptions. Its window-shortcut editor opens the tiling configuration.

## Controls

| Shortcut | Action |
| --- | --- |
| Super + arrows | Focus the adjacent window |
| Super + Shift + arrows | Swap adjacent tiles |
| Super + Ctrl + arrows | Grow a tile at the selected edge |
| Super + Ctrl + Shift + arrows | Shrink a tile at the selected edge |
| Super + V | Toggle floating |
| Super + left mouse drag | Move a floating window or rearrange tiles |
| Super + right mouse drag | Resize |
| Alt + F11 | Toggle fullscreen |
| Super + M | Toggle the layout showing the focused window |
| Super + Q or Alt + F4 | Close the focused window |
| Alt + Tab / Alt + Shift + Tab | Cycle windows |
| Super + 1–4 | Switch workspace |
| Super + Shift + 1–4 | Move a window to a workspace and follow it |
| Ctrl + Alt + 1–4 | Switch workspace using the previous shortcuts |
| Ctrl + Super + 1–4 | Move a window without following it |
| Super + Ctrl + Escape | Restore the original XFCE window manager |

## Dependencies and checks

This workstation uses the official Kali `bspwm` and `sxhkd` packages extracted into `state/tiling/packages/`, with links under `state/bin/`. The supervisor supplies that directory on its processes' PATH. The packages' runtime libraries are already installed. No system packages were changed.

To reproduce the local installation, preview and then download with:

```sh
python3 scripts/install-tiling-locally.py
python3 scripts/install-tiling-locally.py --apply
```

Alternatively install the optional system package profile with `bash scripts/install-packages.sh --apply tiling`. The local installer uses APT's package download verification and records package versions and SHA-256 hashes. It requires the packages' dependencies to be available; it does not install those libraries itself.

Verification uses an optional local Xvfb binary to run an isolated display:

```sh
python3 scripts/install-tiling-locally.py --apply --test-display
python3 scripts/verify-tiling.py
python3 -m unittest discover -s tests
```

Restore XFWM before replacing active local binaries. The isolated check verifies automatic splits and reflow, exact inner and outer gaps, workspace and focus preservation during handover, focus and swap hotkeys, floating dialogs, fullscreen, workspace moves, the gesture listener's EWMH switch protocol, panel reservations, and dock stacking after opening windows, switching workspaces, and revealing the panel. Results are saved under `state/tiling/verification.json`. Logs from the active supervisor are in `state/tiling/session.log`; panel stacking logs are in `state/tiling/panel-stacking.log`.

Native commands and settings follow the [BSPWM manual](https://github.com/baskerville/bspwm/blob/master/doc/bspwm.1.asciidoc).
