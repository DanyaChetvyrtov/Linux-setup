#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mode=${1:---preview}
[[ "$mode" == --preview || "$mode" == --apply ]] || { echo 'Usage: install-packages.sh [--preview|--apply] [base languages containers security desktop ...]' >&2; exit 2; }
if (( $# )); then shift; fi
profiles=("$@")
if (( ${#profiles[@]} == 0 )); then profiles=(base languages containers security); fi
packages=()
for profile in "${profiles[@]}"; do
  case "$profile" in base|languages|containers|security|desktop|tiling) ;; *) echo "Unknown profile: $profile" >&2; exit 2;; esac
  while IFS= read -r package; do
    [[ -z "$package" || "$package" == \#* ]] || packages+=("$package")
  done < "$repo/packages/$profile.txt"
done
if [[ "$mode" == --preview ]]; then
  apt-get --simulate --no-remove install --no-install-recommends "${packages[@]}"
else
  # Intentionally interactive: inspect upgrades and authenticate in your terminal.
  sudo apt-get --no-remove install --no-install-recommends "${packages[@]}"
  mkdir -p "$repo/state"
  dpkg-query -W -f='${binary:Package}\t${Version}\n' > "$repo/state/packages.tsv"
fi
