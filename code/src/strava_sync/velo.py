"""Velo-Sheet Writer im benutzerdefinierten Schema.

Layout pro Zeile (1 Tag = 1 Zeile, erste Ride = Hin, zweite = Rück):
  A  Datum             ("Do., 19.02.2026")
  B  Hin Zeit (h:mm:ss)
  C  Hin Km
  D  Hin Watt
  E-J  Hin Splits 1-6 (mm:ss)
  K  Bemerkung Hin (leer)
  L  Zurück Zeit
  M  Zurück Km
  N  Zurück Watt
  O-T  Zurück Splits 1-6 (mm:ss)
  U  Bemerkung Zurück (leer)
  X-AA  Formeln (von einer Quellzeile kopiert)
  AB-AG  Hin Watts pro Split 1-6
  AH-AM  Zurück Watts pro Split 1-6
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

import gspread

from . import splits as strava_splits
from . import strava

CYCLING_TYPES = {
    "Ride",
    "VirtualRide",
    "GravelRide",
    "MountainBikeRide",
    "EBikeRide",
    "EMountainBikeRide",
}

DE_WD = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
DATE_RE = re.compile(r"^[A-Z][a-z]\., (\d{2})\.(\d{2})\.(\d{4})$")
FORMULA_SOURCE_ROW = 230  # bekannt-gute Quellzeile mit X-AA Formeln


def _de_date(iso_day: str) -> str:
    y, m, d = int(iso_day[:4]), int(iso_day[5:7]), int(iso_day[8:10])
    wd = DE_WD[date(y, m, d).weekday()]
    return f"{wd}., {d:02d}.{m:02d}.{y}"


def _hms(seconds: float | None) -> str:
    if not seconds:
        return ""
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}"


def _mmss(seconds: float | None) -> str:
    if not seconds:
        return ""
    s = int(round(seconds))
    m, sec = divmod(s, 60)
    return f"{m:02d}:{sec:02d}"


def _km(distance_m: float | None) -> str:
    if not distance_m:
        return ""
    return f"{distance_m / 1000:.2f}"


def _w(watts: float | None) -> str:
    if watts is None:
        return ""
    return str(int(round(watts)))


def _parse_date(val: str) -> date | None:
    m = DATE_RE.match(val)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def find_last_date_and_insert_row(ws: gspread.Worksheet) -> tuple[date | None, int, set[date], int | None]:
    """Returns (last_date, first_empty_row, existing_dates, last_date_row)."""
    col = ws.col_values(1)
    last_date: date | None = None
    last_row = 0
    existing: set[date] = set()
    for i, v in enumerate(col, start=1):
        d = _parse_date(v)
        if d is not None:
            existing.add(d)
            if last_date is None or d >= last_date:
                last_date = d
                last_row = i
    return last_date, (last_row + 1 if last_row else 1), existing, (last_row if last_row else None)


def check_incomplete_last_row(ws: gspread.Worksheet, last_date_row: int) -> bool:
    """True wenn Spalte L (Zurück Zeit) in der letzten Datumszeile leer ist."""
    val = ws.cell(last_date_row, 12).value  # col L = 12
    return not val or not val.strip()


def group_pairs(
    activities: list[dict], cutoff_day: date, existing_dates: set[date] | None = None
) -> list[tuple[str, dict, dict | None]]:
    """Gruppiere Cycling-Activities nach Tag, sortiere, nimm 1./2. als Hin/Rück."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for a in activities:
        if a.get("type") not in CYCLING_TYPES and a.get("sport_type") not in CYCLING_TYPES:
            continue
        day = a["start_date_local"][:10]
        d = date(int(day[:4]), int(day[5:7]), int(day[8:10]))
        if d < cutoff_day:
            continue
        if existing_dates and d in existing_dates:
            continue
        by_day[day].append(a)
    pairs: list[tuple[str, dict, dict | None]] = []
    for day in sorted(by_day):
        acts = sorted(by_day[day], key=lambda x: x["start_date_local"])
        hin = acts[0]
        rueck = acts[1] if len(acts) >= 2 else None
        pairs.append((day, hin, rueck))
    return pairs


def _split_lists(
    client: strava.StravaClient, act: dict | None, split_distance_m: float
) -> tuple[list[str], list[str]]:
    """Returns (durations_mmss[6], watts[6]) padded to 6."""
    if act is None:
        return [""] * 6, [""] * 6
    try:
        streams = client.get_streams(act["id"], ["distance", "time", "watts"])
        sp = strava_splits.compute_splits_from_streams(streams, split_distance_m)
    except Exception:
        sp = []
    durs = [_mmss(s.duration_s) for s in sp[:6]] + [""] * max(0, 6 - len(sp))
    watts = [_w(s.avg_power_w) for s in sp[:6]] + [""] * max(0, 6 - len(sp))
    return durs[:6], watts[:6]


def build_row(
    day: str,
    hin: dict,
    rueck: dict | None,
    hin_durs: list[str],
    hin_watts: list[str],
    rueck_durs: list[str],
    rueck_watts: list[str],
) -> tuple[list[str], list[str]]:
    """Returns (cells_A_U[21], cells_AB_AM[12])."""
    main = [
        _de_date(day),
        _hms(hin.get("moving_time")),
        _km(hin.get("distance")),
        _w(hin.get("average_watts")),
        *hin_durs,  # E-J
        "",  # K Bemerkung
        _hms(rueck.get("moving_time")) if rueck else "",
        _km(rueck.get("distance")) if rueck else "",
        _w(rueck.get("average_watts")) if rueck else "",
        *rueck_durs,  # O-T
        "",  # U Bemerkung
    ]
    assert len(main) == 21, len(main)
    watts = hin_watts + rueck_watts
    assert len(watts) == 12, len(watts)
    return main, watts


def update_rueck(
    ws: gspread.Worksheet,
    row: int,
    rueck: dict,
    rueck_durs: list[str],
    rueck_watts: list[str],
) -> None:
    """Rückfahrt-Felder (L-T + AH-AM) in bestehende Zeile schreiben."""
    rueck_cells = [
        _hms(rueck.get("moving_time")),
        _km(rueck.get("distance")),
        _w(rueck.get("average_watts")),
        *rueck_durs,
        "",  # U Bemerkung
    ]
    ws.batch_update(
        [
            {"range": f"L{row}:U{row}", "values": [rueck_cells]},
            {"range": f"AH{row}:AM{row}", "values": [rueck_watts]},
        ],
        value_input_option="USER_ENTERED",
    )


def write_pairs(
    ws: gspread.Worksheet,
    pairs_with_data: list[tuple[list[str], list[str]]],
    start_row: int,
    formula_source_row: int = FORMULA_SOURCE_ROW,
) -> None:
    """Insert N blank rows at start_row, dann Werte + Formeln in einem Batch."""
    n = len(pairs_with_data)
    if n == 0:
        return
    sheet_id = ws.id

    # 1) N leere Zeilen einfügen ab start_row
    ws.spreadsheet.batch_update(
        {
            "requests": [
                {
                    "insertDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": start_row - 1,
                            "endIndex": start_row - 1 + n,
                        },
                        "inheritFromBefore": False,
                    }
                }
            ]
        }
    )

    # Falls Quellzeile durch das Insert verschoben wurde, korrigieren
    src_row = formula_source_row
    if formula_source_row >= start_row:
        src_row = formula_source_row + n

    # 2) Werte (A-U und AB-AM) in einem Batch
    value_ranges = []
    for i, (main, watts) in enumerate(pairs_with_data):
        r = start_row + i
        value_ranges.append({"range": f"A{r}:U{r}", "values": [main]})
        value_ranges.append({"range": f"AB{r}:AM{r}", "values": [watts]})
    ws.batch_update(value_ranges, value_input_option="USER_ENTERED")

    # 3) X-AA Formeln aus src_row in alle neuen Zeilen kopieren
    copy_requests = []
    for i in range(n):
        r = start_row + i
        copy_requests.append(
            {
                "copyPaste": {
                    "source": {
                        "sheetId": sheet_id,
                        "startRowIndex": src_row - 1,
                        "endRowIndex": src_row,
                        "startColumnIndex": 23,  # X
                        "endColumnIndex": 27,  # AA exclusive
                    },
                    "destination": {
                        "sheetId": sheet_id,
                        "startRowIndex": r - 1,
                        "endRowIndex": r,
                        "startColumnIndex": 23,
                        "endColumnIndex": 27,
                    },
                    "pasteType": "PASTE_FORMULA",
                }
            }
        )
    ws.spreadsheet.batch_update({"requests": copy_requests})
