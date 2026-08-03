"""Google Health API client using curl."""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

HEALTH_API_BASE = "https://health.googleapis.com/v4"

SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
]


class HealthApiError(Exception):
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body[:200]}")


def _curl_json(
    method: str,
    url: str,
    token: str,
    *,
    params: dict[str, str] | None = None,
    body: dict | None = None,
) -> dict[str, Any]:
    if params:
        url = f"{url}?{urlencode(params)}"

    cmd = [
        "curl",
        "-sS",
        "--max-time",
        "30",
        "-X",
        method,
        "-H",
        f"Authorization: Bearer {token}",
        "-H",
        "Accept: application/json",
        "-w",
        "\n__HTTP__%{http_code}",
    ]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    cmd.append(url)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise HealthApiError(0, proc.stderr or "curl failed")

    raw = proc.stdout
    if "\n__HTTP__" not in raw:
        raise HealthApiError(0, raw or "empty response")
    payload, status_str = raw.rsplit("\n__HTTP__", 1)
    status = int(status_str)
    if status >= 400:
        raise HealthApiError(status, payload)
    if not payload.strip():
        return {}
    return json.loads(payload)


class HealthClient:
    def __init__(self, access_token: str) -> None:
        self.access_token = access_token

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        return _curl_json("GET", f"{HEALTH_API_BASE}{path}", self.access_token, params=params)

    def _post(self, path: str, body: dict) -> dict[str, Any]:
        return _curl_json("POST", f"{HEALTH_API_BASE}{path}", self.access_token, body=body)

    def get_identity(self) -> dict[str, Any]:
        return self._get("/users/me/identity")

    def get_daily_rollup(self, data_type: str, target: date) -> dict[str, Any] | None:
        body = {
            "range": {
                "start": _civil_time(target, 0, 0, 0),
                "end": _civil_time(target, 23, 59, 59),
            },
            "windowSizeDays": 1,
        }
        try:
            data = self._post(f"/users/me/dataTypes/{data_type}/dataPoints:dailyRollUp", body)
        except HealthApiError:
            return None
        points = data.get("rollupDataPoints", [])
        return points[0] if points else None

    def get_daily_steps(self, target: date) -> int:
        rollup = self.get_daily_rollup("steps", target)
        if not rollup:
            return 0
        return int(rollup.get("steps", {}).get("countSum", 0))

    def get_today_activity(self) -> dict[str, Any]:
        today = date.today()
        distance = self.get_daily_rollup("distance", today)
        distance_mm = int(distance.get("distance", {}).get("millimetersSum", 0) or 0) if distance else 0

        energy = self.get_daily_rollup("active-energy-burned", today)
        calories = round(energy.get("activeEnergyBurned", {}).get("kcalSum", 0) or 0) if energy else None

        azm = self.get_daily_rollup("active-zone-minutes", today)
        zone_minutes = None
        if azm:
            d = azm.get("activeZoneMinutes", {})
            zone_minutes = int(d.get("minutesSum", 0) or d.get("countSum", 0) or 0)

        floors_rollup = self.get_daily_rollup("floors", today)
        floors = None
        if floors_rollup:
            d = floors_rollup.get("floors", {})
            floors = int(d.get("countSum", 0) or d.get("floorsSum", 0) or 0)

        return {
            "distance_km": round(distance_mm / 1_000_000, 2),
            "calories": calories,
            "active_zone_minutes": zone_minutes,
            "floors": floors,
        }

    def get_recent_exercises(self, days: int = 7) -> list[dict[str, Any]]:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        filter_expr = f'exercise.interval.civil_start_time >= "{cutoff}T00:00:00"'
        data = self._get(
            "/users/me/dataTypes/exercise/dataPoints",
            params={"filter": filter_expr, "pageSize": "20"},
        )
        exercises = []
        for point in data.get("dataPoints", []):
            ex = point.get("exercise", {})
            interval = ex.get("interval", {})
            metrics = ex.get("metricsSummary", {})
            exercises.append(
                {
                    "name": ex.get("displayName") or ex.get("exerciseType", "Exercise"),
                    "start": interval.get("startTime", ""),
                    "duration_seconds": _parse_duration(ex.get("activeDuration", "0s")),
                    "steps": int(metrics.get("steps", 0) or 0),
                    "calories": metrics.get("caloriesKcal", 0),
                }
            )
        return exercises

    def get_recent_sleep(self, days: int = 7) -> list[dict[str, Any]]:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        filter_expr = f'sleep.interval.civil_end_time >= "{cutoff}"'
        data = self._get(
            "/users/me/dataTypes/sleep/dataPoints:reconcile",
            params={
                "dataSourceFamily": "users/me/dataSourceFamilies/google-wearables",
                "filter": filter_expr,
                "pageSize": "10",
            },
        )
        sessions = []
        for point in data.get("dataPoints", []):
            sleep = point.get("sleep", {})
            interval = sleep.get("interval", {})
            start = interval.get("startTime", "")
            end = interval.get("endTime", "")
            stages = sleep.get("stages", [])
            stage_minutes: dict[str, int] = {}
            for stage in stages:
                stype = stage.get("type", "")
                mins = _minutes_between(stage.get("startTime", ""), stage.get("endTime", ""))
                stage_minutes[stype] = stage_minutes.get(stype, 0) + mins
            sessions.append(
                {
                    "start": start,
                    "end": end,
                    "duration_minutes": _minutes_between(start, end),
                    "stages": stage_minutes,
                }
            )
        return sessions

    def get_resting_heart_rate(self) -> int | None:
        try:
            data = self._get(
                "/users/me/dataTypes/daily-resting-heart-rate/dataPoints",
                params={"pageSize": "1"},
            )
        except HealthApiError:
            return None
        points = data.get("dataPoints", [])
        if not points:
            return None
        bpm = points[0].get("dailyRestingHeartRate", {}).get("beatsPerMinute")
        return int(bpm) if bpm is not None else None


def fetch_all_stats(client: HealthClient) -> dict[str, Any]:
    """Fetch independent endpoints in parallel via curl."""
    today = date.today()
    jobs = {
        "today_steps": lambda: client.get_daily_steps(today),
        "today_activity": client.get_today_activity,
        "exercises": client.get_recent_exercises,
        "sleep_sessions": client.get_recent_sleep,
        "resting_heart_rate": client.get_resting_heart_rate,
    }
    result: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fn): key for key, fn in jobs.items()}
        for future in as_completed(futures):
            key = futures[future]
            result[key] = future.result()
    return result


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "--max-time",
            "30",
            "-X",
            "POST",
            "https://oauth2.googleapis.com/token",
            "-d",
            f"client_id={client_id}&client_secret={client_secret}"
            f"&refresh_token={refresh_token}&grant_type=refresh_token",
            "-w",
            "\n__HTTP__%{http_code}",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise HealthApiError(0, proc.stderr or "curl failed")
    payload, status_str = proc.stdout.rsplit("\n__HTTP__", 1)
    status = int(status_str)
    if status >= 400:
        raise HealthApiError(status, payload)
    return json.loads(payload)


def _civil_time(d: date, hours: int, minutes: int, seconds: int) -> dict:
    return {
        "date": {"year": d.year, "month": d.month, "day": d.day},
        "time": {"hours": hours, "minutes": minutes, "seconds": seconds, "nanos": 0},
    }


def _parse_duration(duration: str) -> int:
    if not duration or duration == "0s":
        return 0
    if duration.endswith("s"):
        try:
            return int(float(duration[:-1]))
        except ValueError:
            return 0
    return 0


def _minutes_between(start: str, end: str) -> int:
    if not start or not end:
        return 0
    try:
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return max(0, round((e - s).total_seconds() / 60))
    except ValueError:
        return 0
