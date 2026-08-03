"""Interactive setup helpers."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent
ENV_FILE = REPO_ROOT / ".env"
TOKEN_FILE = REPO_ROOT / "data" / "tokens.json"


def _prompt(label: str, secret: bool = False) -> str:
    import getpass

    if secret:
        value = getpass.getpass(f"{label}: ")
    else:
        value = input(f"{label}: ")
    return value.strip()


def write_env(client_id: str, client_secret: str) -> None:
    ENV_FILE.write_text(
        f"GOOGLE_CLIENT_ID={client_id}\n"
        f"GOOGLE_CLIENT_SECRET={client_secret}\n"
        f"REDIRECT_URI=http://localhost:8080/auth/callback\n"
    )


def run_setup(*, login_after: bool = True) -> int:
    print("\n  fitbit setup\n")

    missing = [c for c in ("curl", "python3") if not shutil.which(c)]
    if missing:
        print(f"  error: install first: {', '.join(missing)}", file=sys.stderr)
        return 1
    print("  ✓ curl and python3")

    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    if not venv_python.exists():
        print("  ! no .venv — run ./install.sh first (or: python3 -m venv .venv && pip install -r requirements.txt)")
        return 1
    print("  ✓ virtualenv")

    if not ENV_FILE.exists():
        print("\n  Google Cloud (one-time, free):")
        print("    • Enable Google Health API")
        print("    • OAuth Web client → redirect http://localhost:8080/auth/callback")
        print("    • Add your Gmail as test user + Health API scopes\n")
        client_id = _prompt("  Client ID")
        client_secret = _prompt("  Client Secret", secret=True)
        if not client_id or not client_secret:
            print("  error: credentials required", file=sys.stderr)
            return 1
        write_env(client_id, client_secret)
        print(f"  ✓ wrote {ENV_FILE}")
    else:
        print(f"  ✓ {ENV_FILE} exists")

    bin_dir = Path.home() / ".local" / "bin"
    wrapper = bin_dir / "fitbit"
    bin_dir.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        f'#!/usr/bin/env bash\nexec "{venv_python}" "{REPO_ROOT / "cli.py"}" "$@"\n'
    )
    wrapper.chmod(0o755)
    print(f"  ✓ {wrapper}")

    if login_after and not TOKEN_FILE.exists():
        ans = input("\n  Sign in now? [Y/n] ").strip().lower()
        if ans in ("", "y", "yes"):
            from auth import login_interactive

            login_interactive()
        else:
            print("  → run: fitbit login")
    elif TOKEN_FILE.exists():
        print("  ✓ already signed in")

    print("\n  done — run: fitbit\n")
    return 0


def check_ready() -> str | None:
    if not shutil.which("curl"):
        return "curl not found"
    if not ENV_FILE.exists():
        return "not configured — run: fitbit setup  (or ./install.sh)"
    if not TOKEN_FILE.exists():
        return "not signed in — run: fitbit login"
    return None
