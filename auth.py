"""Google OAuth token storage."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from dotenv import load_dotenv

from health_client import SCOPES, HealthApiError, HealthClient, refresh_access_token

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
TOKEN_FILE = DATA_DIR / "tokens.json"

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8080/auth/callback")
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

DATA_DIR.mkdir(exist_ok=True)


class AuthError(Exception):
    pass


def load_tokens() -> dict | None:
    if not TOKEN_FILE.exists():
        return None
    return json.loads(TOKEN_FILE.read_text())


def save_tokens(tokens: dict) -> None:
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))


def clear_tokens() -> None:
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


def auth_url(state: str) -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "access_type": "offline",
        "scope": " ".join(SCOPES),
        "state": state,
        "prompt": "consent",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "--max-time",
            "30",
            "-X",
            "POST",
            TOKEN_URL,
            "-d",
            f"code={code}&client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}"
            f"&redirect_uri={REDIRECT_URI}&grant_type=authorization_code",
            "-w",
            "\n__HTTP__%{http_code}",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AuthError(proc.stderr or "curl failed")
    payload, status_str = proc.stdout.rsplit("\n__HTTP__", 1)
    if int(status_str) >= 400:
        raise AuthError(f"Token exchange failed: {payload}")
    return json.loads(payload)


def _redirect_port() -> int:
    parsed = urlparse(REDIRECT_URI)
    if parsed.port:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def login_interactive() -> None:
    if not CLIENT_ID or not CLIENT_SECRET:
        raise AuthError("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env")

    state = secrets.token_urlsafe(16)
    url = auth_url(state)
    code_box: dict[str, str] = {}
    port = _redirect_port()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            query = parse_qs(urlparse(self.path).query)
            if query.get("state", [None])[0] != state:
                self.send_error(400, "Invalid state")
                return
            code = query.get("code", [None])[0]
            if not code:
                self.send_error(400, "Missing code")
                return
            code_box["code"] = code
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Authorized. You can close this tab and return to the terminal.")

        def log_message(self, *_args) -> None:
            pass

    server = HTTPServer(("127.0.0.1", port), CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print(f"\nOpen this URL in your browser:\n\n  {url}\n")
    print(f"Waiting for callback on {REDIRECT_URI} ...")
    thread.join(timeout=120)
    server.server_close()

    if "code" not in code_box:
        raise AuthError("Timed out waiting for authorization. Run: fitbit login")

    save_tokens(exchange_code(code_box["code"]))
    print("Signed in. Tokens saved.\n")


def get_client() -> HealthClient:
    if not CLIENT_ID or not CLIENT_SECRET:
        raise AuthError("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env")

    tokens = load_tokens()
    if not tokens:
        raise AuthError("Not signed in. Run: fitbit login")

    access_token = tokens.get("access_token")
    if access_token:
        client = HealthClient(access_token)
        try:
            client.get_identity()
            return client
        except HealthApiError as exc:
            if exc.status != 401:
                raise

    refresh = tokens.get("refresh_token")
    if not refresh:
        raise AuthError("Session expired. Run: fitbit login")

    tokens.update(refresh_access_token(CLIENT_ID, CLIENT_SECRET, refresh))
    save_tokens(tokens)
    return HealthClient(tokens["access_token"])
