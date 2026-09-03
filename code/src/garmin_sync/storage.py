"""Persist downloaded activities to disk."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path


def _activity_dir(base: Path, start_time_local: str) -> Path:
    year = start_time_local[:4]
    month = start_time_local[5:7]
    return base / year / month


def _extract_fit(blob: bytes) -> bytes | None:
    """ORIGINAL download is a zip containing one .fit file."""
    if not blob:
        return None
    if blob[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".fit"):
                    return zf.read(name)
        return None
    return blob


def save(
    base_dir: Path,
    activity_id: int,
    start_time_local: str,
    fit_blob: bytes | None,
    gpx_blob: bytes | None,
    summary: dict,
) -> Path:
    out = _activity_dir(base_dir, start_time_local)
    out.mkdir(parents=True, exist_ok=True)
    fit_path = out / f"{activity_id}.fit"
    gpx_path = out / f"{activity_id}.gpx"
    json_path = out / f"{activity_id}.json"

    fit_data = _extract_fit(fit_blob) if fit_blob else None
    if fit_data and not fit_path.exists():
        fit_path.write_bytes(fit_data)
    if gpx_blob and not gpx_path.exists():
        gpx_path.write_bytes(gpx_blob)
    if not json_path.exists():
        json_path.write_text(json.dumps(summary, indent=2, default=str))
    return fit_path
