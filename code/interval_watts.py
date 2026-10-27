#!/usr/bin/env python3
"""Intervall-Watt pro Block, zeitgewichtet über alle Laps des Blocks — so wie der Edge es zeigt.

    ./interval_watts.py <strava_id> [--min 240] [--thresh 1.2]

Blöcke = zusammenhängende Laps mit Ø-Watt > thresh × Fahrtschnitt (und > 260 W), die
zusammen mindestens --min Sekunden dauern. Der Edge legt die letzten ~60 s eines
Intervalls oft als eigene Runde ab (CLAUDE.md, 21.09.2026) — darum werden benachbarte
harte Laps zu einem Block zusammengezogen. Ausgabe: Σ(W·t)/Σt je Block, HFmax, Dauer.

Grund für das Skript (27.10.2026): Kopfrechnen ging zweimal daneben (314 statt 316 W).
"""
import argparse
import glob
import json
import sys


def load(aid: str) -> dict:
    for f in glob.glob(f"activities/cycling/*/*/{aid}.json"):
        return json.load(open(f))
    sys.exit(f"activities/…/{aid}.json nicht gefunden — zuerst ./sync.sh")


def blocks(laps, avg, thresh, min_sec):
    out, cur = [], []
    for l in laps:
        w = l.get("average_watts") or 0
        hard = w > max(260, thresh * avg)
        if hard:
            cur.append(l)
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [b for b in out if sum(l["moving_time"] for l in b) >= min_sec]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id")
    ap.add_argument("--min", type=int, default=240, help="Mindestdauer eines Blocks in s")
    ap.add_argument("--thresh", type=float, default=1.2, help="Faktor über Fahrtschnitt")
    a = ap.parse_args()
    act = load(a.id)
    laps = act.get("laps") or []
    avg = act.get("average_watts") or 0
    if not laps or not avg:
        sys.exit("keine Laps oder keine Leistung in der Aktivität")
    print(f"{act['name']}  {act['start_date_local'][:16]}  Ø {avg:.0f} W, {len(laps)} Laps")
    res = []
    for i, b in enumerate(blocks(laps, avg, a.thresh, a.min), 1):
        t = sum(l["moving_time"] for l in b)
        w = sum((l.get("average_watts") or 0) * l["moving_time"] for l in b) / t
        hr = max((l.get("max_heartrate") or 0) for l in b)
        nums = ", ".join(f"Lap {laps.index(l)+1}: {l['moving_time']} s / {l.get('average_watts', 0):.1f} W" for l in b)
        print(f"Block {i}: {w:.1f} W  ({t} s, HFmax {hr:.0f})   [{nums}]")
        res.append(round(w))
    if res:
        print("→ " + " → ".join(str(r) for r in res) + " W")


if __name__ == "__main__":
    main()
