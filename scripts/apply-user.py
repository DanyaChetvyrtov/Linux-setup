#!/usr/bin/env python3
"""Apply additive user configuration; back up every modified existing file."""
from pathlib import Path
import datetime, shutil, sys
repo = Path(__file__).resolve().parent.parent
home = Path.home()
apply = sys.argv[1:] == ['--apply']
if sys.argv[1:] not in ([], ['--apply']):
    raise SystemExit('Usage: apply-user.py [--apply]')
backup = home / '.local/state/kali-setup/backups' / datetime.datetime.now().strftime('%Y%m%dT%H%M%S%f')
def append(path, line):
    old = path.read_text() if path.exists() else ''
    if ('\n' + line + '\n') in ('\n' + old.rstrip('\n') + '\n'):
        print('Already configured:', path)
        return
    print('Append configuration:', path)
    if apply:
        if path.exists():
            target = backup / path.relative_to(home)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(old + ('\n' if old and not old.endswith('\n') else '') + line + '\n')
import shlex
append(home / '.zshrc', 'source ' + shlex.quote(str(repo / 'config/shell.zsh')))
append(home / '.tmux.conf', 'source-file "' + str(repo / 'config/tmux.conf').replace('"', '\"') + '"')
# Keep identity and any existing configuration intact.
value = str(repo / 'config/git.conf').replace('\\', '\\\\').replace('"', '\\"')
append(home / '.gitconfig', '[include]\n\tpath = "' + value + '"')
if apply:
    print('Backup location (if needed):', backup)
else:
    print('Preview only; use --apply to write.')
