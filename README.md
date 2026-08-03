# fitbit-tracker

Terminal Fitbit stats — install and run, like neofetch.

**macOS and Linux only.**

## Requirements

- Python 3.10+ (`python3`)
- `curl`
- `git`
- A Google account linked to your Fitbit app (**Sign in with Google**, same email)

## Install

### 1. Clone the repo

```bash
git clone git@github.com:marco-boone/fitbit-tracker.git ~/repos/fitbit-tracker
cd ~/repos/fitbit-tracker
```

HTTPS works too:

```bash
git clone https://github.com/marco-boone/fitbit-tracker.git ~/repos/fitbit-tracker
cd ~/repos/fitbit-tracker
```

### 2. Install system deps

**Linux (Debian/Ubuntu)**

```bash
sudo apt update
sudo apt install python3 python3-venv curl git
```

**Linux (Arch)**

```bash
sudo pacman -S python curl git
```

**macOS** (Homebrew)

```bash
brew install python curl git
```

### 3. Run the installer

```bash
chmod +x install.sh
./install.sh
```

The script will:

- create a Python virtualenv and install dependencies
- prompt for Google OAuth credentials (first run only)
- install `fitbit` to `~/.local/bin`
- offer to sign you in via browser

### 4. Put `fitbit` on your PATH

If `install.sh` warns that `~/.local/bin` is missing from PATH, add this line to your shell config:

**Linux (bash — default on most distros)** — `~/.bashrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

**macOS (zsh — default since Catalina)** — `~/.zshrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Reload your shell (`source ~/.bashrc` or `source ~/.zshrc`), then:

```bash
fitbit
```

## Commands

| Command | What it does |
|---------|----------------|
| `fitbit` | Print today's stats |
| `fitbit setup` | Re-run the config wizard |
| `fitbit login` | Sign in (opens browser) |
| `fitbit logout` | Clear saved tokens |

## Google Cloud (one-time, free)

You need your own OAuth app — the installer walks you through saving credentials to `.env`:

1. [Google Cloud Console](https://console.cloud.google.com/) → create a project
2. Enable **Google Health API**
3. **APIs & Services → Credentials** → OAuth client (**Web application**)
   - Authorized redirect URI: `http://localhost:8080/auth/callback`
4. **Audience** → add your Gmail as a **test user** (app stays in Testing mode)
5. **Data Access** → add Health API scopes: activity, sleep, heart metrics

Copy the Client ID and Client Secret when `install.sh` or `fitbit setup` asks for them.

Your Fitbit mobile app must use **Sign in with Google** with the same Gmail address.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `fitbit: command not found` | Add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` or `~/.zshrc`, then reload |
| `403` from Google Health API | Enable **Google Health API** in your GCP project |
| Login works but no data | Confirm Fitbit app is linked to the same Google account |
| Reconfigure credentials | `fitbit setup` |

## Files (local only, gitignored)

- `.env` — Google OAuth client ID/secret
- `data/tokens.json` — saved login tokens
