"""
Launcher for Glass Assistant.

Run it however you like:

    python run.py
    .\.venv\Scripts\python.exe run.py
    (double-click run.bat)

IMPORTANT: this launcher protects you from a common trap. If you start it
with the WRONG Python (e.g. an old system Python 3.10.0 that crashes the
LLM libraries), it automatically RE-LAUNCHES itself using the project's
own virtual-environment Python in `.venv`. That way the app always runs on
the correct interpreter where the packages are installed.
"""

import subprocess
import sys
from pathlib import Path

# Windows terminals default to cp1252; force UTF-8 so any non-ASCII output
# (e.g. an em-dash in a log line) can never crash the app with an encode error.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_SENTINEL = "--glass-reexec"   # marks that we've already switched interpreters


def _ensure_venv_python():
    """Relaunch using .venv's Python if we're running on a different one."""
    if _SENTINEL in sys.argv:
        return  # already re-launched once; don't loop forever

    here = Path(__file__).resolve().parent
    venv_python = here / ".venv" / "Scripts" / "python.exe"
    current = Path(sys.executable).resolve()

    # If the venv exists and we are NOT already running its Python, switch.
    # We use subprocess (not os.execv) because it correctly quotes paths
    # that contain spaces, e.g. "...\main copy\screening\...".
    if venv_python.exists() and current != venv_python.resolve():
        print(f"[run.py] Switching to venv Python: {venv_python}")
        result = subprocess.run(
            [str(venv_python), str(here / "run.py"), _SENTINEL, *sys.argv[1:]]
        )
        sys.exit(result.returncode)


_ensure_venv_python()

# Remove the internal sentinel so it doesn't confuse anything downstream.
if _SENTINEL in sys.argv:
    sys.argv.remove(_SENTINEL)

# Helpful sanity print so you can SEE which Python is actually running.
print(f"[run.py] Running on Python {sys.version.split()[0]}")

from glass_assistant.main import main

if __name__ == "__main__":
    main()
