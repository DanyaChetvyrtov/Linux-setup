# Touchpad scrolling and workspace gestures

## English and Russian keyboard input

The keyboard supports English (US) and standard Russian. **Super + Space** switches between them. XFCE saves the layouts and switching option in its native `keyboard-layout` settings, so they apply to the active X11 session and future logins. Open Settings → Keyboard → Layout to adjust them interactively.

`config/keyboard.json` defines the layouts, variants and switching option. `python3 scripts/configure-keyboard.py` previews the setup; `--apply` installs it, preserving unrelated keyboard options. The original settings and complete XKB keymap are backed up under `state/keyboard/backups/`. `--restore` returns the keyboard to its state before the first application.

`python3 scripts/verify-keyboard.py` opens a temporary input window, types through physical keycodes, checks `hello` in English and `привет` in Russian, and verifies that Super+Space switches both ways. It restores the previous keyboard group and window focus, then closes the check window. Its results and screenshot are saved under `state/keyboard/`.

## Touchpad and gestures

The ELAN touchpad exposed natural scrolling disabled and advertises gesture support via XInput 2.4. Four-finger workspace changes were observed in the running listener's log. This configuration reverses the inspected scroll direction by enabling natural scrolling in XFCE's persistent per-device pointer settings.

Four-finger horizontal gestures use a small native X11 listener built from `src/workspace-gestures.c` with the installed GCC/libXi/libX11 development libraries. It runs as your user without raw `/dev/input` access or system package installation. The autostart entry starts it on subsequent XFCE logins.

- Swipe four fingers **left** to reveal the **next workspace**.
- Swipe four fingers **right** to reveal the **previous workspace**.
- One workspace change per completed gesture; short, diagonal, vertical and cancelled swipes are ignored.
- Other finger counts are replayed to applications. Keyboard and two-finger scrolling are retained.
- Gestures stop at the first/last workspace. Optional [Picom transitions](animations.md) add a short eased slide after release.

Edit `config/input.json` to change the scroll setting, movement threshold, wrap behavior or direction mapping. Set `swipe_left` to `previous` to make the swipe direction match the direction of workspace travel instead.

```sh
python3 scripts/configure-input.py          # build, run logic checks, preview
python3 scripts/configure-input.py --apply
python3 scripts/configure-input.py --restore
```

The scroll setting and any existing autostart entry are backed up under ignored `state/input/backups/`. Restore stops the listener and restores the settings from immediately before the most recent apply. The generated binary, process ID and gesture-only log are also under ignored `state/`. Keep this checkout at its current path.

Diagnosis:

```sh
state/bin/workspace-gestures --inspect
cat state/input/gestures.log
```

The listener asks X11 for swipe events only and uses the window manager's `_NET_CURRENT_DESKTOP` protocol to switch workspaces. Other gestures are released with `XIReplayDevice`. API documentation is provided by the installed `XInput2.h`, `XIAllowEvents(3)` and `XIGrabButton(3)` manuals; [XFCE pointer settings implementation](https://github.com/xfce-mirror/xfce4-settings/blob/master/xfsettingsd/pointers.c) describes persistent device settings.
