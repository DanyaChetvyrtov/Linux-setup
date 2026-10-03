#!/usr/bin/env bash
set -u
failed=0
for tool in git rg fdfind fzf direnv shellcheck nvim python3 pipx java javac docker nmap socat tshark; do
  if command -v "$tool" >/dev/null; then printf 'OK %s\n' "$tool"; else printf 'MISSING %s\n' "$tool"; failed=1; fi
done
if command -v docker >/dev/null; then docker compose version || { docker-compose version || failed=1; }; fi
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
python3 -m venv "$work/venv" && "$work/venv/bin/python" -m pip --version || failed=1
if command -v javac >/dev/null; then
  printf 'class Check { public static void main(String[] a) { System.out.println("Java OK"); } }\n' > "$work/Check.java"
  javac "$work/Check.java" && java -cp "$work" Check || failed=1
fi
exit "$failed"
