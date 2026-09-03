#!/usr/bin/env python3
"""Erzeugt pro b2w/b2h-Fahrt eine <id>.md mit Standard-Kennzahlen neben dem JSON.

  ./activity_report.py --new        # alle b2w/b2h-Rides ohne .md (schnell, JSON-only)
  ./activity_report.py <pfad.json>  # gezielt (überschreibt vorhandene .md)

Metrik-Konventionen: siehe CLAUDE.md. W/HF = Fitness (velo-/wetterunabhängig),
W/km/h = Bedingungen/Aero. HF-Zonen aus analysis/b2w-pb-und-form.md.
"""
import os, sys, json, glob

HERE = os.path.dirname(os.path.abspath(__file__))
SL, SLX = "b14743198", "b18052102"
B2W_S, B2W_E = (47.185, 8.467), (47.373, 8.528)          # Sihltal → Zürich
# HF-Zonen nach %HFmax (HFmax ~188) — siehe analysis/trainings-evidenz.md.
# Grundlage/Tempo-Grenze bei VT1 ~140, persönlich kalibriert (Tom: HF 135 ≈ 220 W klar
# locker; ab 140 Richtung Tempo) — nicht die generische 75%-Formel.
ZONES = [(113, "Z1 Recovery (<60%)"), (140, "Z2 Grundlage (bis VT1 ~140)"),
         (156, "Z3 Tempo/graue Zone (140–155)"), (165, "Schwelle/MIT (83–87%)"),
         (175, "Z4 (88–92%)"), (999, "VO2max (>93%)")]


def near(p, q, tol=0.004):
    return p and q and abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol


def route(d):
    s, e = tuple(d.get("start_latlng") or []), tuple(d.get("end_latlng") or [])
    if near(s, B2W_S) and near(e, B2W_E):
        return "b2w"
    if near(s, B2W_E) and near(e, B2W_S):
        return "b2h-Albis"
    nm = (d.get("name") or "").lower()
    if "b2w" in nm:
        return "b2w?"
    if "b2h" in nm:
        return "b2h?"
    return None


def zone(hr):
    for hi, name in ZONES:
        if hr < hi:
            return name
    return ZONES[-1][1]


def load_weights():
    p = os.path.join(HERE, "weights.json")
    return json.load(open(p)) if os.path.exists(p) else {}


def b2w_times():
    """moving_time aller b2w-Morgenfahrten für den PB-Rang."""
    ts = []
    for f in glob.glob(os.path.join(HERE, "activities/cycling/*/*/*.json")):
        d = json.load(open(f))
        if route(d) == "b2w" and d.get("moving_time"):
            ts.append((d["moving_time"], d["id"]))
    return sorted(ts)


def gen(path, weights, pb):
    d = json.load(open(path))
    if d.get("type") != "Ride":
        return None
    r = route(d)
    if not r:
        return None
    out = os.path.splitext(path)[0] + ".md"
    day = (d.get("start_date_local") or "")[:10]
    bike = {SL: "SL", SLX: "SLX"}.get(d.get("gear_id"), "?")
    sp = d.get("average_speed", 0) * 3.6
    w = d.get("average_watts")
    hr = d.get("average_heartrate")
    np = d.get("weighted_average_watts")
    mt = d.get("moving_time", 0)
    L = [f"# {day} — {d.get('name', '').strip()} ({bike})", ""]
    L.append(f"*Auto-Report ({r}). Route/Metrik-Konventionen: siehe `CLAUDE.md`.*")
    L.append("")
    L.append(f"- **Zeit:** {mt // 60}:{mt % 60:02d} · **{sp:.1f} km/h** · "
             f"max {d.get('max_speed', 0) * 3.6:.1f} · {d.get('total_elevation_gain') or 0:.0f} hm · {d.get('average_temp')} °C")
    if w and hr:
        L.append(f"- **Leistung:** {w:.0f} W (NP {np or '?'}) · **W/HF {w / hr:.2f}** · "
                 f"W/km/h {w / sp:.2f} · Kadenz {d.get('average_cadence') or '?'}")
    if w and np:
        vi = np / w
        flag = ""
        if r == "b2w" and hr and hr < 141 and vi > 1.12:
            flag = " — ⚠️ **punchy trotz Grundlage-HF** (Surges über Kuppen? auf Locker-Tagen ≤ ~250 W)"
        L.append(f"- **Gleichmässigkeit (NP/Ø):** {vi:.2f}{flag}")
    if hr:
        L.append(f"- **HF:** Ø {hr:.0f} / max {d.get('max_heartrate') or 0:.0f} → **{zone(hr)}**")
    wt = weights.get(day)
    if wt:
        L.append(f"- **Gewicht (Tag):** {wt:.1f} kg")
    if bike == "SLX" and w:
        L.append(f"- ⚠️ SLX-Meter liest ~+18 W tief vs. SL-Referenz — Watt velo-übergreifend nicht 1:1.")
    # PB-Check nur für saubere b2w-Morgenroute
    if r == "b2w" and mt:
        rank = next((i for i, (t, i2) in enumerate(pb, 1) if i2 == d["id"]), None)
        if rank == 1:
            L.append(f"- 🏆 **Schnellste b2w-Zeit** aller {len(pb)} Fahrten (PB!)")
        elif rank and rank <= 5:
            L.append(f"- ⭐ Rang **{rank}/{len(pb)}** der schnellsten b2w-Fahrten")
    L.append("")
    with open(out, "w") as fh:
        fh.write("\n".join(L) + "\n")
    return out


def main():
    args = sys.argv[1:]
    weights = load_weights()
    pb = b2w_times()
    if args == ["--new"]:
        paths = [f for f in glob.glob(os.path.join(HERE, "activities/cycling/*/*/*.json"))
                 if not os.path.exists(os.path.splitext(f)[0] + ".md")]
    else:
        paths = args
    n = 0
    for p in paths:
        if gen(p, weights, pb):
            n += 1
    print(f"activity_report: {n} .md erzeugt.")


if __name__ == "__main__":
    main()
