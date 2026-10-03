# Inspected baseline — 2026-09-30

Kali 2026.1 rolling, kernel 6.18.12+kali-amd64; 2,432 installed packages and clean dpkg audit. XFCE 4.20/X11; Zsh 5.9 and customized Kitty 0.46.1. Intel N5030, four cores, 3.7 GiB RAM, 3.8 GiB swap, roughly 204 GiB free.

Git 2.53.0 with identity unset; repository initially had no commits. Java 25.0.3-ea runtime without JDK. Node 22.22.2/npm 9.2.0; Python 3.13.12/pip 26.0.1 without ensurepip or pipx. C/C++ tools, Go 1.26.2 and a user Rust stable toolchain present. Docker absent. Nmap/TShark/socat absent; tcpdump/netcat/dig/VPN clients present.

SSH disabled and inactive; user SSH directory empty with mode 0700. NetworkManager active and tunnel interface present. Observed TCP listeners localhost-only. nftables/AppArmor services inactive; rules and enforcement not established.

Current APT metadata proposes Python 3.14 plus Kitty/Hyprland upgrades and removal of node-re2, onboard, onboard-data when installing the entire profile set. The no-removal guard blocks this transaction until the transition is separately reviewed. Administrator access requires an interactive password.
