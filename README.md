# fitbit-tracker

Terminal app — run once, print Fitbit stats via **Google Health API** and **curl**.

## Setup

```bash
cd ~/repos/fitbit-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET in .env
```

Requires `curl` on PATH. Google Cloud: enable **Google Health API**, OAuth Web client, redirect  
`http://localhost:8080/auth/callback`, test user + Health API scopes.

## Install command

```bash
chmod +x ~/.local/bin/fitbit   # if needed
# ~/.local/bin is on PATH via ~/.bashrc
```

Or use the bash alias in `~/.bashrc`.

## Usage

```bash
fitbit login    # first time
fitbit          # print stats
fitbit logout
```

Colors use your terminal theme via `tput` (respects `NO_COLOR`).

Tokens: `data/tokens.json`
