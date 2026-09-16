#!/usr/bin/env python3
"""Di2-Gang- + Trittfrequenz-Overlay für einen Clip rendern.

Die Gangwahl steckt NICHT im Strava-Stream, nur im Garmin-FIT
(`gear_change`-Events mit Zeitstempel). Dieses Skript holt das FIT über
garminconnect, baut daraus eine Gang-Zeitreihe, ergänzt die Trittfrequenz aus
dem Strava-`cadence`-Stream, synchronisiert beides auf den Aufnahmezeitpunkt des
Clips und rendert via reel.burn(..., overlay=) in den gelben Data-Stil oben
rechts — „Blatt : Ritzel" (Zähne) und „U/min".

  ./gear_overlay.py "<clip.mov>" --strava-id <id> --srt <srt> --out <mp4> [--hook "…"] [--garmin-id <id>]

Ohne --garmin-id wird die Garmin-Aktivität über die Startzeit der Strava-Fahrt
gesucht (±120 s), wie beim Velo-Fingerprint.
"""
import os, sys, json, glob, argparse, tempfile, zipfile, urllib.request, importlib.util
import datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "src"))
from dotenv import load_dotenv; load_dotenv(os.path.join(HERE, ".env"))
import reel
from fitparse import FitFile


def strava_token():
    spec = importlib.util.spec_from_file_location("se", os.path.join(HERE, "strava_enrich.py"))
    se = importlib.util.module_from_spec(spec); spec.loader.exec_module(se); se.load_env()
    return se.strava_token()


def cadence_series(aid, tok):
    u = f"https://www.strava.com/api/v3/activities/{aid}/streams?keys=cadence,time&key_by_type=true"
    r = urllib.request.Request(u); r.add_header("Authorization", f"Bearer {tok}")
    s = json.load(urllib.request.urlopen(r, timeout=30))
    cad = s.get("cadence", {}).get("data") or []
    tstream = s.get("time", {}).get("data") or list(range(len(cad)))
    at = {}
    for j, t in enumerate(tstream):
        at.setdefault(int(t), cad[j] if j < len(cad) else None)
    return at


def resolve_garmin_id(ride_start, c):
    """Garmin-Aktivität über die Startzeit finden (±120 s)."""
    for a in c.get_activities(0, 15):
        gt = a.get("startTimeGMT")
        if not gt:
            continue
        agt = dt.datetime.strptime(gt, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
        if abs((agt - ride_start).total_seconds()) < 120:
            return a["activityId"]
    return None


def gear_events(fit_path):
    """(utc, front_teeth, rear_teeth) je Schaltvorgang, nur gültige Werte."""
    ff = FitFile(fit_path)
    ev = []
    for m in ff.get_messages("event"):
        f = {d.name: d.value for d in m}
        if "gear_change_data" not in f or f.get("timestamp") is None:
            continue
        ts = f["timestamp"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        fg, fn = f.get("front_gear"), f.get("front_gear_num")
        rg, rn = f.get("rear_gear"), f.get("rear_gear_num")
        ev.append((ts,
                   fg if (fg and fg not in (0, 255) and fn not in (None, 255)) else None,
                   rg if (rg and rg not in (0, 255) and rn not in (None, 255)) else None))
    ev.sort(key=lambda e: e[0])
    return ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--strava-id", type=int, required=True)
    ap.add_argument("--srt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hook", default=None)
    ap.add_argument("--garmin-id", type=int, default=None)
    a = ap.parse_args()

    act = json.load(open(glob.glob(os.path.join(HERE, f"activities/*/*/*/{a.strava_id}.json"))[0]))
    ride_start = dt.datetime.fromisoformat(act["start_date"].replace("Z", "+00:00"))
    tok = strava_token()
    cad_at = cadence_series(a.strava_id, tok)

    from garmin_sync import garmin
    c = garmin.login()
    gid = a.garmin_id or resolve_garmin_id(ride_start, c)
    if not gid:
        sys.exit("Keine passende Garmin-Aktivität gefunden (--garmin-id angeben).")
    data = c.download_activity(gid, dl_fmt=c.ActivityDownloadFormat.ORIGINAL)
    zp = os.path.join(tempfile.gettempdir(), f"{gid}.zip"); open(zp, "wb").write(data)
    with zipfile.ZipFile(zp) as z:
        fit = [n for n in z.namelist() if n.lower().endswith(".fit")][0]
        z.extract(fit, tempfile.gettempdir())
    ev = gear_events(os.path.join(tempfile.gettempdir(), fit))
    print(f"{len(ev)} Gang-Events, Fahrtstart {ride_start:%H:%M} UTC")

    def gear_at(when):
        f = r = None
        for ts, front, rear in ev:
            if ts > when:
                break
            if front is not None: f = front
            if rear is not None: r = rear
        return f, r

    clip_start = reel.creation_time(a.clip)
    if clip_start.tzinfo is None:
        clip_start = clip_start.replace(tzinfo=dt.timezone.utc)
    dur = int(reel.duration(a.clip) or 0)
    off = int((clip_start - ride_start).total_seconds())

    cues = []
    for sec in range(dur):
        f, r = gear_at(clip_start + dt.timedelta(seconds=sec))
        cd = cad_at.get(off + sec)
        lines = []
        if f and r: lines.append(f"{f} : {r}")
        if cd is not None: lines.append(f"{int(round(cd))} U/min")
        if lines:
            cues.append({"start": sec, "end": sec + 1, "text": "\\N".join(lines)})
    print(f"{len(cues)} Overlay-Sekunden; @5s: {gear_at(clip_start + dt.timedelta(seconds=5))}")
    reel.burn(a.clip, a.srt, a.out, hook=a.hook, overlay=cues)
    # Build-Zwischendateien wegräumen (reel.burn erzeugt sie neben --out;
    # der reel_render.sh-Wrapper täte das sonst).
    stem = os.path.splitext(a.out)[0]
    for ext in (".ass", ".hook.txt"):
        try:
            os.remove(stem + ext)
        except OSError:
            pass
    print("gerendert →", a.out)


if __name__ == "__main__":
    main()
