"""
Running this file does everything needed to get invSend working:

1. Creates a local virtual environment (.venv) if it doesn't exist.
2. Installs the Python packages this project needs into it.
3. Re-launches itself using that venv's Python interpreter.
4. Makes sure the Go dependencies (whatsmeow, sqlite driver, etc.) are
   downloaded, by running `go mod init`/`go mod tidy` in this folder.
5. Starts the WhatsApp server (main.go) in the background if it isn't
   already running, and shows a QR code to scan if not yet logged in.
6. Hands off to your own code at the bottom of this file.

Deleting this entire folder removes everything: the venv, the Go module
cache references, and invsend.db (your WhatsApp session/secrets) - nothing
sensitive is stored outside this directory.
"""

import os
import sys
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(SCRIPT_DIR, ".venv")


def _venv_python() -> str:
    if os.name == "nt":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")


def _in_venv() -> bool:
    return os.path.abspath(sys.prefix) == os.path.abspath(VENV_DIR)


def _bootstrap_venv():
    """Create .venv and install Python deps, then restart inside it."""
    if _in_venv():
        return  # already running inside .venv, nothing to do

    if not os.path.exists(VENV_DIR):
        print("Creating virtual environment (.venv)...")
        subprocess.run([sys.executable, "-m", "venv", VENV_DIR], check=True)

    venv_python = _venv_python()

    print("Installing Python dependencies...")
    subprocess.run(
        [venv_python, "-m", "pip", "install", "-q", "--upgrade", "pip"],
        check=True,
    )
    subprocess.run(
        [venv_python, "-m", "pip", "install", "-q", "-r",
         os.path.join(SCRIPT_DIR, "requirements.txt")],
        check=True,
    )
    result = subprocess.run([venv_python] + sys.argv)
    sys.exit(result.returncode)

def _check_go_installed():
    try:
        subprocess.run(
            ["go", "version"], check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        print(
            "Go doesn't seem to be installed or isn't on PATH.\n"
            "Install it from https://go.dev/dl/ and run this script again.",
            file=sys.stderr,
        )
        sys.exit(1)


def _bootstrap_go():
    """Make sure go.mod exists and all Go dependencies are downloaded."""
    _check_go_installed()

    gomod_path = os.path.join(SCRIPT_DIR, "go.mod")
    if not os.path.exists(gomod_path):
        print("Initializing Go module...")
        subprocess.run(["go", "mod", "init", "invsend"], cwd=SCRIPT_DIR, check=True)

    print("Fetching Go dependencies (first run may take a minute)...")
    subprocess.run(["go", "mod", "tidy"], cwd=SCRIPT_DIR, check=True)


# --- Step 1 & 2: venv + pip deps (restarts the process if needed) ---
_bootstrap_venv()

# --- Step 3: Go deps ---
_bootstrap_go()

# --- Step 4: start server + handle login (safe to import now; we're in .venv) ---
from invsend import ensure_ready, send_message  # noqa: E402

try:
    ensure_ready()

    # ========== WhatsApp is Connected ==========

    from automate import message_sender_ss
    message_sender_ss(None, None, send_message)
except Exception as e:
    print(f"\nSomething went wrong: {e}")
finally:
    try:
        input("\nPress Enter to exit...")
    except EOFError:
        pass
    os._exit(0)