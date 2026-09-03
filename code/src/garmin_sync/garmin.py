"""Garmin Connect Client via python-garminconnect (neue Mobile-SSO-Auth)."""
from __future__ import annotations

import os
from pathlib import Path

from garminconnect import Garmin

TOKENSTORE = Path(__file__).resolve().parents[2] / "garmin_tokens.json"


def login() -> Garmin:
    email = os.environ["GARMIN_EMAIL"]
    password = os.environ["GARMIN_PASSWORD"]
    client = Garmin(email=email, password=password)
    if TOKENSTORE.exists():
        try:
            client.login(str(TOKENSTORE))
            return client
        except Exception:
            pass
    client.login()
    try:
        client.garth.dump(str(TOKENSTORE))
    except Exception:
        pass
    return client


def list_new_activities(client: Garmin, since_id: int | None) -> list[dict]:
    page_size = 50
    start = 0
    collected: list[dict] = []
    while True:
        batch = client.get_activities(start, page_size)
        if not batch:
            break
        for act in batch:
            if since_id is not None and int(act["activityId"]) <= since_id:
                return list(reversed(collected))
            collected.append(act)
        if len(batch) < page_size:
            break
        start += page_size
    return list(reversed(collected))


def list_activities_since(client: Garmin, since_iso: str) -> list[dict]:
    page_size = 50
    start = 0
    collected: list[dict] = []
    while True:
        batch = client.get_activities(start, page_size)
        if not batch:
            break
        for act in batch:
            if act["startTimeLocal"][:10] < since_iso:
                return list(reversed(collected))
            collected.append(act)
        if len(batch) < page_size:
            break
        start += page_size
    return list(reversed(collected))


def download(
    client: Garmin, activity_id: int
) -> tuple[bytes | None, bytes | None, dict]:
    fit_bytes: bytes | None = None
    gpx_bytes: bytes | None = None
    try:
        fit_bytes = client.download_activity(
            activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
        )
    except Exception:
        fit_bytes = None
    try:
        gpx_bytes = client.download_activity(
            activity_id, dl_fmt=Garmin.ActivityDownloadFormat.GPX
        )
    except Exception:
        gpx_bytes = None
    summary = client.get_activity(activity_id)
    return fit_bytes, gpx_bytes, summary
