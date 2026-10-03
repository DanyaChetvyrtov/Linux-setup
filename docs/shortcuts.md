# Shortcuts

Open **Shortcuts** from the application menu. It combines the active application and window/workspace bindings from XFCE in a table with **Hotkey**, **Description**, and **Command** columns. Search any column or filter by category. **Super** means the Windows key.

Double-click a row or select **Edit description…** to change its description. You can also edit the description directly in the table. Notes are saved automatically; **Reset to default** restores the supplied description. If a hotkey is reassigned to a different command, its old note is no longer shown.

Use **Edit hotkeys…** to open XFCE's application or window shortcut settings. The viewer refreshes when those bindings change. It reads the bindings rather than maintaining a second copy.

The wallpaper hotkey is **Super + Shift + W**, described as “Change to the next wallpaper.”

## Installation

```sh
python3 scripts/install-shortcuts.py          # Preview
python3 scripts/install-shortcuts.py --apply  # Add the application-menu launcher
python3 scripts/shortcut-viewer.py            # Open directly
python3 scripts/shortcut-viewer.py --list     # Export the current list as JSON
```

This uses the system Python, GTK 3, PyGObject, and Xfconf already present on this workstation. Keep the repository at its current location; the launcher points to the script here.

Personal descriptions live in the separate `kali-setup-shortcuts` Xfconf channel. This leaves XFCE's shortcut definitions intact. Repository defaults for additional commands belong in `config/shortcut-descriptions.json`, keyed by the exact command under `commands` or by the action name under `xfwm4`. Choose **Refresh shortcuts** after editing that file.

Installation saves a restore record under `state/shortcuts/`. To remove the launcher, or restore the launcher that was present before installation:

```sh
python3 scripts/install-shortcuts.py --restore state/shortcuts/TIMESTAMP/restore.json
```

Restoring the launcher keeps saved descriptions. The installer refuses to overwrite a launcher that changed after installation.

## Checks

```sh
python3 -m unittest discover -s tests
python3 -m py_compile src/shortcut_catalog.py scripts/shortcut-viewer.py scripts/install-shortcuts.py
```
