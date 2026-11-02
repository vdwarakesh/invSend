import base64
import os
import subprocess
import sys
import time

import requests

PORT = 60995
BASE_URL = f"http://127.0.0.1:{PORT}"

# Folder containing main.go / go.mod — same folder as this file by default.
GO_SRC_DIR = os.path.dirname(os.path.abspath(__file__))

_server_process = None  # keeps a reference so it isn't garbage collected


def _is_server_up() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/status", timeout=1)
        return r.ok
    except requests.exceptions.RequestException:
        return False


LOG_PATH = os.path.join(GO_SRC_DIR, "server.log")


def _start_server():
    """Launch the Go server as a background process.
    Output is NOT discarded -- it's written to server.log in this folder,
    so build/runtime errors are visible for debugging, while the terminal
    stays quiet on success."""
    global _server_process

    kwargs = {}
    if os.name == "nt":
        # Prevents a console window from popping up on Windows.
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    log_file = open(LOG_PATH, "w")

    _server_process = subprocess.Popen(
        ["go", "run", "."],
        cwd=GO_SRC_DIR,
        stdout=log_file,
        stderr=log_file,
        stdin=subprocess.DEVNULL,
        **kwargs,
    )
    return _server_process


def _dump_log(lines: int = 40):
    if not os.path.exists(LOG_PATH):
        print("(no server.log was produced)")
        return
    with open(LOG_PATH, "r", errors="replace") as f:
        content = f.readlines()
    print(f"--- last {min(lines, len(content))} line(s) of server.log ---")
    print("".join(content[-lines:]))
    print("--- end of log ---")


def _wait_for_server(timeout: float = 45.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if _server_process is not None and _server_process.poll() is not None:
            # The process already exited -- no point waiting further.
            return False
        if _is_server_up():
            return True
        time.sleep(0.5)
    return False


def _show_qr(code: str):
    try:
        import qrcode
    except ImportError:
        print("Install the 'qrcode' package to see the QR code: pip install qrcode")
        print("Raw QR data:", code)
        return

    qr = qrcode.QRCode(border=1)
    qr.add_data(code)
    qr.make()
    qr.print_ascii(invert=True)


def _handle_login():
    last_code = None
    while True:
        try:
            status = requests.get(f"{BASE_URL}/status", timeout=2).json()
        except requests.exceptions.RequestException:
            time.sleep(1)
            continue

        if status.get("logged_in"):
            return

        try:
            qr_resp = requests.get(f"{BASE_URL}/qr", timeout=2)
            if qr_resp.ok:
                code = qr_resp.json().get("code")
                if code and code != last_code:
                    last_code = code
                    print("\nScan this QR code on your WhatsApp linked devices\n")
                    _show_qr(code)
        except requests.exceptions.RequestException:
            pass

        time.sleep(2)


def ensure_ready():
    """Start the Go server if needed, and wait for WhatsApp login if needed.
    Call this once at the top of your script before send_message()."""
    if not _is_server_up():
        print("Starting WhatsApp server...")
        _start_server()
        if not _wait_for_server():
            print("Server failed to start.", file=sys.stderr)
            _dump_log()
            sys.exit(1)

    status = requests.get(f"{BASE_URL}/status", timeout=2).json()
    if not status.get("logged_in"):
        _handle_login()
        print("WhatsApp connected!")


def send_message(number: str, text: str, file: str | None = None) -> dict:
    """
    number: phone number with country code, digits only, e.g. "919876543210"
    text:   message body (or caption, if a file is attached)
    file:   optional path to a local file to send
    """
    payload = {"number": number, "text": text}

    if file:
        with open(file, "rb") as f:
            payload["file_b64"] = base64.b64encode(f.read()).decode()
        payload["file_name"] = os.path.basename(file)

    resp = requests.post(f"{BASE_URL}/send", json=payload, timeout=30)
    if not resp.ok:
        print("Server said:", resp.text, file=sys.stderr)
    resp.raise_for_status()
    return resp.json()