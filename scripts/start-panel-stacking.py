#!/usr/bin/env python3
"""Start one event-driven XFCE panel stacking listener for the BSPWM session."""
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
from panel_stacking import PanelStacking


def main():
    listener = PanelStacking()
    try:
        if sys.argv[1:] == ["--session"]:
            listener.run()
        elif not sys.argv[1:]:
            if not listener.is_bspwm():
                raise RuntimeError("Panel stacking requires the active BSPWM session.")
            if listener.running():
                return
            state = REPO / "state/tiling"
            state.mkdir(parents=True, exist_ok=True)
            with (state / "panel-stacking.log").open("a") as log:
                process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--session"],
                    stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            for _ in range(40):
                if listener.running():
                    return
                if process.poll() is not None:
                    raise RuntimeError("Panel stacking exited during startup; see state/tiling/panel-stacking.log.")
                time.sleep(0.1)
            process.terminate()
            process.wait(timeout=3)
            raise RuntimeError("Panel stacking startup timed out; see state/tiling/panel-stacking.log.")
        else:
            raise SystemExit("Usage: start-panel-stacking.py [--session]")
    finally:
        listener.close()


if __name__ == "__main__":
    main()
