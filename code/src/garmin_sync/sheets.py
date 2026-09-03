"""Google Sheets upsert for cycling activities."""
from __future__ import annotations

import os
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from .splits import Split

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _client() -> gspread.Client:
    sa_path = os.environ["GOOGLE_SA_JSON"]
    creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    return gspread.authorize(creds)


def _open_worksheet(sheet_id: str, worksheet: str) -> gspread.Worksheet:
    sh = _client().open_by_key(sheet_id)
    try:
        return sh.worksheet(worksheet)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=worksheet, rows=1000, cols=30)


def _fmt_duration(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _fmt_split(sp: Split) -> str:
    s = int(round(sp.duration_s))
    m, sec = divmod(s, 60)
    base = f"{m:02d}:{sec:02d}"
    if sp.avg_power_w is not None:
        return f"{base} @ {int(round(sp.avg_power_w))}w"
    return base


_HEADER = ["activity_id", "datum", "dauer", "distanz_km", "avg_watt"]


class CyclingSheet:
    """Buffered writer: ein Read am Anfang, ein batch Write am Ende."""

    def __init__(self, sheet_id: str, worksheet: str) -> None:
        self.ws = _open_worksheet(sheet_id, worksheet)
        values = self.ws.get_all_values()
        if not values:
            self.ws.update("A1", [_HEADER])
            self.existing_ids: set[str] = set()
            self.split_cols = 0
        else:
            self.existing_ids = {row[0] for row in values[1:] if row}
            self.split_cols = max(0, len(values[0]) - len(_HEADER))
        self.pending: list[list[str]] = []
        self.max_splits = self.split_cols

    def add(
        self,
        activity_id: int,
        start_time_local: str,
        duration_s: float,
        distance_m: float,
        avg_power_w: float | None,
        splits: list[Split],
    ) -> bool:
        if str(activity_id) in self.existing_ids:
            return False
        self.existing_ids.add(str(activity_id))
        if len(splits) > self.max_splits:
            self.max_splits = len(splits)
        row = [
            str(activity_id),
            start_time_local[:10],
            _fmt_duration(duration_s),
            f"{distance_m / 1000:.2f}",
            f"{int(round(avg_power_w))}" if avg_power_w is not None else "",
        ] + [_fmt_split(sp) for sp in splits]
        self.pending.append(row)
        return True

    def flush(self) -> int:
        if self.max_splits > self.split_cols:
            new_header = _HEADER + [f"split_5km_{i+1}" for i in range(self.max_splits)]
            self.ws.update("A1", [new_header])
            self.split_cols = self.max_splits
        if not self.pending:
            return 0
        self.ws.append_rows(self.pending, value_input_option="USER_ENTERED")
        n = len(self.pending)
        self.pending = []
        return n
