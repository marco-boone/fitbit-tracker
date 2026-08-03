#!/usr/bin/env python3
"""Fitbit stats — one-shot terminal output via Google Health API."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date, datetime
from typing import Any

from auth import AuthError, clear_tokens, get_client, login_interactive
from health_client import fetch_all_stats
from setup import check_ready, run_setup

STEP_GOAL = 10_000
LABEL_WIDTH = 22
BAR_WIDTH = 20


class Term:
    """Colors from the active terminal theme via tput."""

    def __init__(self) -> None:
        self.on = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        self.reset = self._cap("sgr0")
        self.bold = self._cap("bold")
        self.dim = self._cap("dim") or self._cap("setaf", "8")
        self.title = self._cap("setaf", "5")
        self.prefix = self._cap("setaf", "4")
        self.accent = self._cap("setaf", "6")
        self.muted = self._cap("setaf", "8")
        self.error = self._cap("setaf", "1")

    def _cap(self, *args: str) -> str:
        if not self.on:
            return ""
        try:
            r = subprocess.run(["tput", *args], capture_output=True, text=True, timeout=1)
            if r.returncode == 0 and r.stdout:
                return r.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return ""


T = Term()


def _fmt(v: Any, suffix: str = "") -> str:
    if v is None or v == "":
        return f"{T.muted}—{T.reset}"
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return f"{T.accent}{v}{suffix}{T.reset}"


def _fmt_num(n: int | float) -> str:
    if isinstance(n, float):
        s = f"{n:,.1f}" if n % 1 else f"{int(n):,}"
    else:
        s = f"{n:,}"
    return f"{T.accent}{s}{T.reset}"


def _row(label: str, value: str) -> str:
    dots = "." * max(1, LABEL_WIDTH - len(label) - 1)
    return f"  {T.muted}{label}{T.reset} {T.dim}{dots}{T.reset} {value}"


def _section(title: str) -> str:
    return f"\n  {T.prefix}>{T.reset} {T.bold}{title}{T.reset}"


def _progress_bar(steps: int, goal: int = STEP_GOAL, width: int = BAR_WIDTH) -> str:
    pct = min(100, round(steps / goal * 100)) if goal else 0
    filled = round(pct / 100 * width)
    bar = f"[{'=' * filled}{'.' * (width - filled)}] {pct}%"
    return f"{T.title}{bar}{T.reset}"


def _fmt_time(iso: str) -> str:
    if not iso:
        return f"{T.muted}—{T.reset}"
    s = datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    return f"{T.muted}{s}{T.reset}"


def _fmt_duration(seconds: int) -> str:
    m = round(seconds / 60)
    if m < 60:
        return f"{m}m"
    h, rem = divmod(m, 60)
    return f"{h}h {rem}m" if rem else f"{h}h"


def _sleep_stages(stages: dict[str, int]) -> str:
    if not stages:
        return ""
    order = ["DEEP", "REM", "LIGHT", "AWAKE"]
    parts = [f"{k.lower()} {stages[k]}m" for k in order if stages.get(k)]
    return f"{T.dim}{' · '.join(parts)}{T.reset}"


def format_report(data: dict[str, Any]) -> str:
    lines: list[str] = []
    today_str = date.today().strftime("%a %d %b %Y")
    lines.append("")
    lines.append(
        f"  {T.title}{T.bold}fitbit-tracker{T.reset}"
        f"{' ' * max(1, 40 - len('fitbit-tracker'))}"
        f"{T.dim}{today_str}{T.reset}"
    )

    steps = data["today_steps"]
    lines.append(_section("summary"))
    lines.append(_row("steps today", _fmt_num(steps)))
    lines.append(f"  {T.muted}{'goal':<{LABEL_WIDTH}}{T.reset} {_progress_bar(steps)} {T.dim}/ {_fmt_num(STEP_GOAL)}{T.reset}")
    rhr = data.get("resting_heart_rate")
    lines.append(_row("resting hr", _fmt(rhr, " bpm") if rhr is not None else f"{T.muted}—{T.reset}"))

    sleep = data.get("sleep_sessions") or []
    if sleep:
        hours = sleep[0]["duration_minutes"] / 60
        lines.append(_row("last sleep", f"{T.accent}{hours:.1f} h{T.reset}"))
    else:
        lines.append(_row("last sleep", f"{T.muted}—{T.reset}"))

    exercises = data.get("exercises") or []
    lines.append(_row("workouts (7d)", f"{T.accent}{len(exercises)}{T.reset}"))

    act = data.get("today_activity") or {}
    lines.append(_section("activity (today)"))
    lines.append(_row("distance", _fmt(act.get("distance_km"), " km")))
    lines.append(_row("calories burned", _fmt(act.get("calories"), " kcal")))
    lines.append(_row("active zone min", _fmt(act.get("active_zone_minutes"), " min")))
    lines.append(_row("floors", _fmt(act.get("floors"))))

    lines.append(_section("sleep (recent)"))
    if not sleep:
        lines.append(f"  {T.muted}(none){T.reset}")
    else:
        for s in sleep[:5]:
            dur = s["duration_minutes"] / 60
            stages = _sleep_stages(s.get("stages") or {})
            meta = stages or f"{T.dim}→ {_fmt_time(s.get('end', ''))}{T.reset}"
            lines.append(f"  {_fmt_time(s.get('start', ''))}  {T.accent}{dur:.1f}h{T.reset}  {meta}")

    lines.append(_section("workouts (recent)"))
    if not exercises:
        lines.append(f"  {T.muted}(none){T.reset}")
    else:
        for ex in exercises[:5]:
            stat = ""
            if ex.get("steps"):
                stat = f"{T.accent}{ex['steps']:,} steps{T.reset}"
            elif ex.get("calories"):
                stat = f"{T.accent}{ex['calories']} kcal{T.reset}"
            lines.append(
                f"  {T.bold}{ex.get('name', 'workout'):<12}{T.reset}  "
                f"{_fmt_time(ex.get('start', ''))}  "
                f"{T.dim}{_fmt_duration(ex.get('duration_seconds', 0))}{T.reset}  {stat}"
            )

    lines.append("")
    return "\n".join(lines)


def cmd_stats() -> int:
    hint = check_ready()
    if hint:
        print(f"{T.error}error:{T.reset} {hint}", file=sys.stderr)
        return 1
    client = get_client()
    data = fetch_all_stats(client)
    print(format_report(data))
    return 0


def cmd_login() -> int:
    login_interactive()
    return 0


def cmd_logout() -> int:
    clear_tokens()
    print("Signed out.")
    return 0


def cmd_setup() -> int:
    return run_setup()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="fitbit",
        description="Show Fitbit stats once in the terminal (Google Health API).",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="stats",
        choices=("stats", "login", "logout", "setup"),
        help="stats (default): print dashboard; setup: install wizard; login; logout",
    )
    args = parser.parse_args()

    try:
        if args.command == "stats":
            return cmd_stats()
        if args.command == "login":
            return cmd_login()
        if args.command == "setup":
            return cmd_setup()
        return cmd_logout()
    except AuthError as exc:
        print(f"{T.error}error:{T.reset} {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"{T.error}error:{T.reset} {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
