# Animated workspace gestures on XFCE

Picom 13 replaces XFWM's compositing while XFWM continues to manage windows. Four-finger swipes retain the current direction and filtering. After release, windows on the outgoing and incoming workspaces slide together over one monitor width with a 180 ms ease-out curve. Panels and sticky windows stay in place. Ordinary window actions outside the transition are not animated.

This is a short transition after a gesture, rather than Hyprland's interactive workspace movement that follows the fingers. Clicking the XFCE workspace pager still uses the normal immediate switch.

```sh
bash scripts/install-packages.sh --preview desktop
bash scripts/install-packages.sh --apply desktop
python3 scripts/configure-animations.py --apply
```

The inspected package transaction adds `picom`, `libconfig15` and `libev4t64` without removals or upgrades. Only user desktop configuration is changed after installation. The active configuration is `config/picom.conf`; change its four `duration = 0.18` offset timings and the two matching opacity timings together to tune the transition. Keep the duration below 300 ms because the listener clears its temporary direction property after 350 ms.

GLX, vsync and damage tracking are enabled. Background blur is disabled to suit this machine. Window rules use the gesture listener's temporary `_KALI_WORKSPACE_DIRECTION` client property. The listener clears it after each transition and on graceful shutdown. Existing scroll direction, workspace count and panel settings are retained.

The user autostart entry starts `scripts/start-compositor.py`. Its supervisor restores XFWM compositing if Picom exits or fails to start. The listener also continues to switch workspaces if Picom is unavailable. Keep this repository at its current path.

```sh
python3 scripts/configure-animations.py --restore
```

Restore puts back the previous autostart entry and XFWM compositor setting and restarts the gesture listener with the former animation mode. Backups and logs live under ignored `state/compositor/`.

Animation syntax and context variables follow the [official Picom v13 manual](https://github.com/yshui/picom/blob/v13/man/picom.1.adoc).

Verified on this machine: both slide directions showed intermediate rendered positions and returned to the starting workspace; temporary direction markers cleared afterward. Terminating the supervised Picom child restored XFWM compositing automatically, and Picom restarted successfully. The panel positions, sizes, hiding behavior and plugin lists, the scroll setting and the animated gesture listener were checked in the running session. Local results are saved in `state/compositor/transition-check.json` and `state/compositor/verification.json`.
