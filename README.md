# Kali development and security setup

Reproducible, modular configuration for this workstation. Keep this checkout at its current path: user configuration sources its files directly.

Desktop layout: see [split panel setup and rollback](docs/desktop.md). The bottom application panel uses Docklike Taskbar with animated hover magnification and smooth hide/show motion; settings live in `config/panels.json`.

Window management: [automatic tiling within XFCE](docs/tiling.md) uses BSPWM for Hyprland-style splits, 12px gaps, thin green borders, floating windows, and keyboard controls. Settings live in `config/bspwmrc` and `config/tiling-sxhkdrc`.

Touchpad behavior: see [scroll direction and four-finger workspace gestures](docs/input.md). Configuration lives in `config/input.json` and runs in the user XFCE/X11 session.

Workspace transitions: see [Picom animations and rollback](docs/animations.md). The optional `desktop` package profile installs Picom and Docklike Taskbar; animation settings live in `config/picom.conf`.

Keyboard shortcuts: see [the searchable Shortcuts viewer](docs/shortcuts.md), which combines XFCE hotkeys with editable descriptions. Repository defaults live in `config/shortcut-descriptions.json`.

## Apply

Review package changes first. APT metadata is not refreshed automatically.

```sh
bash scripts/install-packages.sh --preview base
bash scripts/install-packages.sh --apply base
bash scripts/install-packages.sh --preview languages containers security
bash scripts/install-packages.sh --apply languages containers security
python3 scripts/apply-user.py
python3 scripts/apply-user.py --apply
```

The installer refuses package removals and prompts before installation. If a rolling transition requires removals, review it separately rather than bypassing the guard. No distribution upgrade or autoremove is performed. Successful installs record versions under ignored `state/`; those records do not guarantee historical package availability.

Open a new terminal after applying user settings. Existing Zsh/Kitty settings are preserved. Modified user files are backed up under `~/.local/state/kali-setup/backups/`. To roll back, restore those backups (or remove newly created include files). No credentials or identities belong in this repository.

## Personal identity

Set these locally with your own values:

```sh
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## Languages

Java development uses OpenJDK 21 via the Zsh fragment; system Java alternatives are not changed intentionally. Use project Maven/Gradle wrappers. Keep system Node.js initially and use project lockfiles and runtime requirements. Use `python3 -m venv .venv` per project and pipx for Python CLI applications. Never use sudo pip or bypass externally-managed protections. Existing user Rust and system Go installations are retained.

## Containers and security

Docker installation may start its service and alter networking. After installation, inspect `sudo systemctl status docker` and `sudo docker info`. Leave boot startup unchanged unless desired; start manually with `sudo systemctl start docker` if necessary. No Docker group membership is added. Use `sudo docker compose` (or `sudo docker-compose` if that is the packaged command). Bind lab ports explicitly to `127.0.0.1`, pin image versions/digests, and use small workloads on this 4 GB machine.

TShark installation may ask whether non-root users should capture packets: choose No for the initial setup. No packet-capture group access is added. SSH server, firewall, AppArmor, and existing VPN/tunnel settings are not modified by these scripts.

## Verify

```sh
bash scripts/verify.sh
bash scripts/inspect.sh
```

Verification creates a temporary virtual environment and compiles a tiny Java program; it does not download images or scan networks. Inspection prints no private keys or Git identity. Before changing protections, inspect `sudo nft list ruleset`, `sudo aa-status`, `systemctl status apparmor`, and the existing tunnel configuration. Decide firewall rules from actual VPN and Docker needs.
