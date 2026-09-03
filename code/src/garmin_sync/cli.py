"""CLI entrypoint."""
from __future__ import annotations

from pathlib import Path

import click
import yaml
from dotenv import load_dotenv

from . import garmin, sheets, splits, state, storage

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _is_cycling(act: dict, type_keys: list[str]) -> bool:
    tk = (act.get("activityType") or {}).get("typeKey", "")
    return tk in type_keys or "cycl" in tk or "biking" in tk


def _process(act: dict, cfg: dict, client) -> None:
    activity_id = int(act["activityId"])
    start_time = act["startTimeLocal"]
    click.echo(f"  -> {activity_id} {start_time} {act.get('activityName', '')}")

    fit_blob, gpx_blob, summary = garmin.download(client, activity_id)
    activities_dir = REPO_ROOT / cfg["activities_dir"]
    fit_path = storage.save(
        activities_dir, activity_id, start_time, fit_blob, gpx_blob, summary
    )

    if _is_cycling(act, cfg["cycling_type_keys"]):
        sp_list = []
        if fit_path.exists():
            try:
                sp_list = splits.compute_splits(fit_path, cfg["split_distance_m"])
            except Exception as e:
                click.echo(f"     splits failed: {e}", err=True)
        sheet_id = cfg["sheet_id"]
        if sheet_id:
            inserted = sheets.upsert_cycling(
                sheet_id=sheet_id,
                worksheet=cfg["worksheet"],
                activity_id=activity_id,
                start_time_local=start_time,
                duration_s=float(act.get("duration") or 0),
                distance_m=float(act.get("distance") or 0),
                avg_power_w=act.get("avgPower"),
                splits=sp_list,
            )
            click.echo(f"     sheet: {'inserted' if inserted else 'skip (exists)'}")
        else:
            click.echo("     sheet: skipped (no sheet_id in config.yaml)")

    state_path = REPO_ROOT / cfg["state_file"]
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
def sync(cfg: dict) -> None:
    """Inkrementeller Sync ab letzter bekannter Activity-ID."""
    state_path = REPO_ROOT / cfg["state_file"]
    since_id = state.last_activity_id(state_path)
    click.echo(f"Sync since activity_id={since_id}")
    client = garmin.login()
    acts = garmin.list_new_activities(client, since_id)
    click.echo(f"{len(acts)} new activities")
    for act in acts:
        _process(act, cfg, client)


@main.command()
@click.option("--since", required=True, help="Datum YYYY-MM-DD")
@click.pass_obj
def backfill(cfg: dict, since: str) -> None:
    """Alle Aktivitäten seit Datum laden."""
    client = garmin.login()
    acts = garmin.list_activities_since(client, since)
    click.echo(f"{len(acts)} activities since {since}")
    for act in acts:
        _process(act, cfg, client)


if __name__ == "__main__":
    main()
