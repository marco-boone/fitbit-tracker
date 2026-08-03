#!/usr/bin/env bash
# One-time installer: venv, deps, .env, and `fitbit` on PATH.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
WRAPPER="${BIN_DIR}/fitbit"
VENV="${REPO_ROOT}/.venv"
ENV_FILE="${REPO_ROOT}/.env"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
dim()  { printf '\033[2m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: '$1' is required but not installed." >&2
    exit 1
  fi
}

bold "fitbit-tracker install"
dim "Repo: ${REPO_ROOT}"
echo

need_cmd python3
need_cmd curl
ok "python3 and curl found"

if [[ ! -d "${VENV}" ]]; then
  dim "Creating virtualenv..."
  python3 -m venv "${VENV}"
fi
ok "virtualenv ready"

dim "Installing Python dependencies..."
if grep -qE '^[^#[:space:]]' "${REPO_ROOT}/requirements.txt" 2>/dev/null; then
  "${VENV}/bin/pip" install -q -r "${REPO_ROOT}/requirements.txt"
  ok "dependencies installed"
else
  ok "no pip dependencies"
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo
  bold "Google OAuth credentials"
  dim "One-time Google Cloud setup (free, ~5 min):"
  dim "  1. console.cloud.google.com → new project"
  dim "  2. Enable 'Google Health API'"
  dim "  3. OAuth client (Web app), redirect: http://localhost:8080/auth/callback"
  dim "  4. Audience → add your Gmail as test user"
  dim "  5. Data Access → Health API scopes (activity, sleep, heart metrics)"
  echo
  read -rp "Google Client ID: " client_id
  read -rsp "Google Client Secret: " client_secret
  echo
  cat >"${ENV_FILE}" <<EOF
GOOGLE_CLIENT_ID=${client_id}
GOOGLE_CLIENT_SECRET=${client_secret}
REDIRECT_URI=http://localhost:8080/auth/callback
EOF
  ok "wrote ${ENV_FILE}"
else
  ok ".env already exists (skipped)"
fi

mkdir -p "${BIN_DIR}"
cat >"${WRAPPER}" <<EOF
#!/usr/bin/env bash
exec "${VENV}/bin/python" "${REPO_ROOT}/cli.py" "\$@"
EOF
chmod +x "${WRAPPER}"
ok "installed ${WRAPPER}"

if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
  warn "~/.local/bin is not on PATH — add this to your shell config:"
  dim '  export PATH="$HOME/.local/bin:$PATH"'
  dim "  Linux: ~/.bashrc   macOS: ~/.zshrc"
fi

echo
if [[ ! -f "${REPO_ROOT}/data/tokens.json" ]]; then
  read -rp "Sign in to Google/Fitbit now? [Y/n] " do_login
  do_login="${do_login:-Y}"
  if [[ "${do_login}" =~ ^[Yy]$ ]]; then
    "${WRAPPER}" login
  else
    dim "Run 'fitbit login' when ready."
  fi
else
  ok "existing login found"
fi

echo
bold "Done. Run: fitbit"
