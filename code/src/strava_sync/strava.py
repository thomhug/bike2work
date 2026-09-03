"""Strava API client mit OAuth2 Refresh-Token-Flow."""
from __future__ import annotations

import json
import os
import time
import webbrowser
from pathlib import Path
from typing import Any

import requests

API = "https://www.strava.com/api/v3"
OAUTH = "https://www.strava.com/oauth"
SCOPES = "read,activity:read_all,activity:write"


class StravaClient:
    def __init__(self, token_path: Path) -> None:
        self.token_path = token_path
        self.client_id = os.environ["STRAVA_CLIENT_ID"]
        self.client_secret = os.environ["STRAVA_CLIENT_SECRET"]
        self.tokens = json.loads(token_path.read_text())
        self._ensure_fresh()

    def _ensure_fresh(self) -> None:
        if self.tokens.get("expires_at", 0) - 60 > time.time():
            return
        r = requests.post(
            f"{OAUTH}/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.tokens["refresh_token"],
            },
            timeout=30,
        )
        r.raise_for_status()
        self.tokens = r.json()
        self.token_path.write_text(json.dumps(self.tokens, indent=2))

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens['access_token']}"}

    def _get(self, path: str, **params: Any) -> Any:
        self._ensure_fresh()
        for attempt in range(3):
            try:
                r = requests.get(
                    f"{API}{path}", headers=self._headers(), params=params, timeout=120
                )
                r.raise_for_status()
                return r.json()
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def list_activities(self, after_epoch: int | None = None) -> list[dict]:
        """Alle Activities mit start_date >= after_epoch, älteste zuerst."""
        per_page = 100
        page = 1
        out: list[dict] = []
        while True:
            params: dict[str, Any] = {"per_page": per_page, "page": page}
            if after_epoch is not None:
                params["after"] = after_epoch
            batch = self._get("/athlete/activities", **params)
            if not batch:
                break
            out.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        out.sort(key=lambda a: a["start_date"])
        return out

    def get_activity(self, activity_id: int) -> dict:
        return self._get(f"/activities/{activity_id}")

    def get_streams(self, activity_id: int, keys: list[str]) -> dict:
        return self._get(
            f"/activities/{activity_id}/streams",
            keys=",".join(keys),
            key_by_type="true",
        )


def auth_flow(token_path: Path) -> None:
    """Einmaliger OAuth-Setup. Druckt Auth-URL, fragt nach ?code= aus Redirect."""
    client_id = os.environ["STRAVA_CLIENT_ID"]
    client_secret = os.environ["STRAVA_CLIENT_SECRET"]
    redirect = "http://localhost"
    url = (
        f"{OAUTH}/authorize?client_id={client_id}"
        f"&response_type=code&redirect_uri={redirect}"
        f"&approval_prompt=auto&scope={SCOPES}"
    )
    print("Öffne diese URL im Browser und autorisiere:")
    print(url)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print()
    print("Nach Autorisierung wirst du auf http://localhost/?...&code=XXX&... umgeleitet.")
    print("Kopiere den Wert von 'code' aus der URL hier rein:")
    code = input("code: ").strip()
    r = requests.post(
        f"{OAUTH}/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    r.raise_for_status()
    tokens = r.json()
    token_path.write_text(json.dumps(tokens, indent=2))
    print(f"Tokens gespeichert in {token_path}")
