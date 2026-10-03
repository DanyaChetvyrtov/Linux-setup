#!/usr/bin/env bash
set -u
cat /etc/os-release
uname -srmo
printf '\nInstalled packages\n'
dpkg-query -W -f='${db:Status-Abbrev}\t${binary:Package}\t${Version}\n'
printf '\nTool versions\n'
for tool in git node npm python3 javac docker nmap pipx; do
  if command -v "$tool" >/dev/null; then "$tool" --version 2>&1; else printf '%s: absent\n' "$tool"; fi
done
java -version 2>&1
printf '\nService status\n'
systemctl is-active ssh docker NetworkManager nftables apparmor || true
printf '\nListeners\n'
ss -lntu
