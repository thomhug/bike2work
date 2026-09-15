"""Strava sync CLI."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import click
import yaml
from dotenv import load_dotenv

from datetime import date, timedelta

import gspread
from google.oauth2.service_account import Credentials

from garmin_sync import sheets, state

from . import splits as strava_splits
from . import strava
from . import velo as velo_mod

REPO_ROOT = Path(__file__).resolve().parents[2]

CYCLING_TYPES = {
    "Ride",
    "VirtualRide",
    "GravelRide",
    "MountainBikeRide",
    "EBikeRide",
    "EMountainBikeRide",
    "Velomobile",
    "Handcycle",
}

RUNNING_TYPES = {"Run", "TrailRun", "VirtualRun"}


def _load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _is_cycling(act: dict) -> bool:
    return act.get("type") in CYCLING_TYPES or act.get("sport_type") in CYCLING_TYPES


def _activity_category(act: dict) -> str:
    t = act.get("type") or act.get("sport_type") or "unknown"
    if t in CYCLING_TYPES:
        return "cycling"
    if t in RUNNING_TYPES:
        return "running"
    return "other"


def _save_activity(base: Path, act: dict, detail: dict) -> None:
    start = act["start_date_local"]
    cat = _activity_category(act)
    out = base / cat / start[:4] / start[5:7]
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{act['id']}.json").write_text(json.dumps(detail, indent=2, default=str))


def _process(
    act: dict,
    cfg: dict,
    client: strava.StravaClient,
    sheet: sheets.CyclingSheet | None,
) -> None:
    activity_id = int(act["id"])
    start = act["start_date_local"]
    click.echo(f"  -> {activity_id} {start} {act.get('name', '')}")

    activities_dir = REPO_ROOT / cfg["activities_dir"]
    cat = _activity_category(act)
    json_path = activities_dir / cat / start[:4] / start[5:7] / f"{activity_id}.json"
    if not json_path.exists():
        detail = client.get_activity(activity_id)
        _save_activity(activities_dir, act, detail)
    else:
        detail = act

    if _is_cycling(act) and sheet is not None:
        sp_list = []
        try:
            streams = client.get_streams(activity_id, ["distance", "time", "watts"])
            sp_list = strava_splits.compute_splits_from_streams(
                streams, cfg["split_distance_m"]
            )
        except Exception as e:
            click.echo(f"     splits failed: {e}", err=True)

        added = sheet.add(
            activity_id=activity_id,
            start_time_local=start,
            duration_s=float(act.get("moving_time") or act.get("elapsed_time") or 0),
            distance_m=float(act.get("distance") or 0),
            avg_power_w=act.get("average_watts"),
            splits=sp_list,
        )
        click.echo(f"     queued: {'yes' if added else 'skip (exists)'}")

    state_path = REPO_ROOT / cfg["strava_state_file"]
    state.update_last(state_path, activity_id)


@click.group()
@click.option(
    "--config",
    "config_path",
    default=str(REPO_ROOT / "config.yaml"),
    type=click.Path(exists=True),
)
@click.pass_context
def main(ctx: click.Context, config_path: str) -> None:
    load_dotenv(REPO_ROOT / ".env")
    ctx.obj = _load_config(Path(config_path))


@main.command()
@click.pass_obj
def auth(cfg: dict) -> None:
    """Einmaliger OAuth-Setup. Speichert refresh_token."""
    token_path = REPO_ROOT / cfg["strava_token_file"]
    strava.auth_flow(token_path)


@main.command()
@click.pass_obj
def sync(cfg: dict) -> None:
    """Inkrementeller Sync ab letzter bekannter Activity-ID."""
    state_path = REPO_ROOT / cfg["strava_state_file"]
    token_path = REPO_ROOT / cfg["strava_token_file"]
    if not token_path.exists():
        raise click.ClickException(
            f"{token_path} fehlt. Erst `python -m strava_sync.cli auth` laufen lassen."
        )
    client = strava.StravaClient(token_path)
    last_id = state.last_activity_id(state_path)

    acts = client.list_activities(after_epoch=None)
    if last_id is not None:
        acts = [a for a in acts if int(a["id"]) > last_id]
    click.echo(f"Sync: {len(acts)} new activities (since id={last_id})")
    sheet = sheets.CyclingSheet(cfg["sheet_id"], cfg["worksheet"]) if cfg.get("sheet_id") else None
    for act in acts:
        _process(act, cfg, client, sheet)
    if sheet:
        n = sheet.flush()
        click.echo(f"sheet: {n} rows written")


@main.command()
@click.option("--since", required=True, help="Datum YYYY-MM-DD")
@click.pass_obj
def backfill(cfg: dict, since: str) -> None:
    """Alle Aktivitäten seit Datum laden."""
    token_path = REPO_ROOT / cfg["strava_token_file"]
    client = strava.StravaClient(token_path)
    after_epoch = int(datetime.fromisoformat(since).timestamp())
    acts = client.list_activities(after_epoch=after_epoch)
    click.echo(f"{len(acts)} activities since {since}")
    sheet = sheets.CyclingSheet(cfg["sheet_id"], cfg["worksheet"]) if cfg.get("sheet_id") else None
    for act in acts:
        _process(act, cfg, client, sheet)
    if sheet:
        n = sheet.flush()
        click.echo(f"sheet: {n} rows written")


def _open_ws(cfg: dict) -> gspread.Worksheet:
    import os

    creds = Credentials.from_service_account_file(
        os.environ["GOOGLE_SA_JSON"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(cfg["sheet_id"]).worksheet(cfg["worksheet"])


@main.command()
@click.option("--start-row", type=int, default=None, help="Erzwinge Startzeile (Test)")
@click.option("--dry-run", is_flag=True)
@click.option(
    "--skip", "skip_ids", type=int, multiple=True,
    help="Strava-ID, die weder als Hin- noch als Rückfahrt zählt (mehrfach möglich)",
)
@click.pass_obj
def velo(cfg: dict, start_row: int | None, dry_run: bool, skip_ids: tuple[int, ...]) -> None:
    """Hin/Rück-Pairs ins Velo-Sheet schreiben (neues Schema)."""
    token_path = REPO_ROOT / cfg["strava_token_file"]
    client = strava.StravaClient(token_path)
    ws = _open_ws(cfg)
    # Kurzfahrten (Firmenevent → Büro, Testrunde) sind keine Pendelfahrten
    min_dist = cfg.get("min_ride_distance_m", 15000)
    skip = set(skip_ids)

    last_date, first_empty, existing_dates, last_date_row = velo_mod.find_last_date_and_insert_row(ws)
    cutoff = max(date(2026, 1, 27), (last_date + timedelta(days=1)) if last_date else date(2026, 1, 27))
    target = start_row if start_row is not None else first_empty

    # Sonderfall: letzter Tag hat nur Hinfahrt → Rückfahrt ergänzen
    incomplete_day: date | None = None
    if last_date and last_date_row and velo_mod.check_incomplete_last_row(ws, last_date_row):
        incomplete_day = last_date
        # cutoff einen Tag zurück, damit wir Activities für diesen Tag holen
        fetch_cutoff = last_date
    else:
        fetch_cutoff = cutoff

    click.echo(f"last_date={last_date} first_empty_row={first_empty} cutoff={cutoff} existing={len(existing_dates)} dates target_row={target}")
    if incomplete_day:
        click.echo(f"incomplete_day={incomplete_day} (Rückfahrt fehlt in Zeile {last_date_row})")

    after_epoch = int(date(fetch_cutoff.year, fetch_cutoff.month, fetch_cutoff.day).strftime("%s"))
    acts = client.list_activities(after_epoch=after_epoch)
    click.echo(f"{len(acts)} activities since {fetch_cutoff}")

    # Volle Details runterladen und speichern
    activities_dir = REPO_ROOT / cfg["activities_dir"]
    for a in acts:
        aid = a["id"]
        start = a["start_date_local"]
        cat = _activity_category(a)
        json_path = activities_dir / cat / start[:4] / start[5:7] / f"{aid}.json"
        if not json_path.exists():
            detail = client.get_activity(aid)
            _save_activity(activities_dir, a, detail)
            click.echo(f"  saved [{cat}] {aid} {start} {a.get('name','')}")

    # Backfill: bestehende Summary-JSONs auf volle Details upgraden (max 90 pro Run)
    backfill_limit = 90
    upgraded = 0
    for f in sorted(activities_dir.rglob("*.json")):
        if upgraded >= backfill_limit:
            break
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        if data.get("resource_state", 2) >= 3:
            continue
        aid = data.get("id") or int(f.stem)
        try:
            detail = client.get_activity(aid)
            f.write_text(json.dumps(detail, indent=2, default=str))
            upgraded += 1
        except Exception:
            break
    if upgraded:
        click.echo(f"backfill: {upgraded} activities upgraded to full detail")

    # Rückfahrt für unvollständigen Tag?
    if incomplete_day:
        day_str = incomplete_day.isoformat()
        day_rides = [
            a for a in acts
            if a["start_date_local"][:10] == day_str
            and velo_mod.is_commute(a, min_dist, skip)
        ]
        day_rides.sort(key=lambda x: x["start_date_local"])
        if len(day_rides) >= 2:
            rueck = day_rides[1]
            rd, rw = velo_mod._split_lists(client, rueck, cfg["split_distance_m"])
            if dry_run:
                click.echo(f"DRY-RUN — würde Rückfahrt ergänzen in Zeile {last_date_row}: {rueck.get('name','?')!r}")
            else:
                velo_mod.update_rueck(ws, last_date_row, rueck, rd, rw)
                click.echo(f"Rückfahrt ergänzt in Zeile {last_date_row}: {rueck.get('name','?')!r}")

    pairs = velo_mod.group_pairs(acts, cutoff, existing_dates, min_dist, skip)
    click.echo(f"{len(pairs)} cycling days to write")
    if not pairs:
        return

    pairs_with_data: list[tuple[list[str], list[str]]] = []
    for day, hin, rueck in pairs:
        hd, hw = velo_mod._split_lists(client, hin, cfg["split_distance_m"])
        rd, rw = velo_mod._split_lists(client, rueck, cfg["split_distance_m"])
        main, watts = velo_mod.build_row(day, hin, rueck, hd, hw, rd, rw)
        pairs_with_data.append((main, watts))
        click.echo(
            f"  {day}: hin={hin.get('name','?')[:30]!r} "
            f"rueck={(rueck or {}).get('name','-')[:30]!r}"
        )

    if dry_run:
        click.echo("DRY-RUN — würde schreiben ab Zeile {}:".format(target))
        for i, (main, watts) in enumerate(pairs_with_data):
            r = target + i
            click.echo(f"  row {r}: A-U={main}")
            click.echo(f"           AB-AM={watts}")
        return

    velo_mod.write_pairs(ws, pairs_with_data, target)
    click.echo(f"OK: {len(pairs_with_data)} Zeilen ab Zeile {target} eingefügt.")


if __name__ == "__main__":
    main()
