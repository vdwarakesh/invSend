import base64
import requests

API_URL = "http://127.0.0.1:8080/send"

def send_message(number: str, text: str, file: str | None = None) -> dict:
    """
    number: phone number with country code, digits only, e.g. "919876543210"
    text: message body (or caption, if a file is attached)
    file: optional path to a local file to send
    """
    payload = {"number": number, "text": text}

    if file:
        with open(file, "rb") as f:
            payload["file_b64"] = base64.b64encode(f.read()).decode()
        import os
        payload["file_name"] = os.path.basename(file)

    resp = requests.post(API_URL, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()