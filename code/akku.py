#!/usr/bin/env python3
"""Akkustände der Sensoren aus den Garmin-FIT-Files der letzten Fahrten.

    ./akku.py            # letzte 6 Velofahrten
    ./akku.py --n 20

Shimano Di2 meldet nur Stufen (new > good > ok > low > critical), keine Prozent.
4iiii-Powermeter und Pulsgurt/Uhr liefern die Spannung. Den Edge-Akku selbst
schreibt Garmin nicht in die Standardfelder.

Anlass (12.11.2026): Di2 am SL sprang von „ok" (10./11.11.) direkt auf
„critical" — Tom: „sonst könnt ihr mich da etwas mehr vorwarnen".
→ Im Sync laufen lassen und bei ok/low/critical im Bericht melden.
"""
import argparse, io, json, glob, zipfile, datetime as dt
import gear_overlay  # setzt den Pfad für garmin_sync
from garmin_sync import garmin
from fitparse import FitFile

STUFEN = ["new", "good", "ok", "low", "critical"]
VELO = {"b14743198": "SL", "b18052102": "SLX"}
CR2032_WARN = 2.75  # 4iiii: Find-My-Fall 04.11.2026 endete bei 2.5 V


def velo_fuer(start_local):
    """Velo aus dem lokalen Strava-JSON (Startzeit ±3 min)."""
    t = dt.datetime.fromisoformat(start_local)
    for f in glob.glob(f"activities/cycling/{t:%Y}/{t:%m}/*.json"):
        d = json.load(open(f))
        s = dt.datetime.fromisoformat(d["start_date_local"].replace("Z", ""))
        if abs((s - t).total_seconds()) < 180:
            return VELO.get(d.get("gear_id"), "?")
    return "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6)
    a = ap.parse_args()
    c = garmin.login()
    n = 0
    warn, neueste = [], {}
    for act in c.get_activities(0, 40):
        k = (act.get("activityType") or {}).get("typeKey", "")
        if "bik" not in k and "cycl" not in k:
            continue
        data = c.download_activity(act["activityId"], dl_fmt=c.ActivityDownloadFormat.ORIGINAL)
        z = zipfile.ZipFile(io.BytesIO(data))
        fn = [x for x in z.namelist() if x.lower().endswith(".fit")][0]
        di2, pm = [], []
        for m in FitFile(io.BytesIO(z.read(fn))).get_messages("device_info"):
            v = {f.name: f.value for f in m}
            if v.get("manufacturer") in (41, "shimano") and v.get("battery_status"):
                di2.append(v["battery_status"])
            if v.get("manufacturer") == "4iiiis" and v.get("battery_voltage"):
                pm.append(v["battery_voltage"])
        start = act["startTimeLocal"][:16]
        velo = velo_fuer(act["startTimeLocal"].replace(" ", "T"))
        d = di2[-1] if di2 else "-"
        p = f"{pm[-1]:.2f} V" if pm else "-"
        print(f"{start}  {velo:3}  Di2 {d:9}  4iiii {p}")
        if velo not in neueste:  # Liste ist absteigend: erster Treffer = aktueller Stand
            neueste[velo] = velo
            if d in ("ok", "low", "critical"):
                warn.append(f"Di2 am {velo}: {d} ({start}) — laden")
            if pm and pm[-1] < CR2032_WARN:
                warn.append(f"4iiii am {velo}: {pm[-1]:.2f} V ({start}) — CR2032 bereitlegen")
        n += 1
        if n >= a.n:
            break
    print()
    for w in warn:
        print("⚠️ ", w)
    if not warn:
        print("✅ Akkus in Ordnung")


if __name__ == "__main__":
    main()
