#!/usr/bin/env python3
"""Powermeter-Offset SL vs. SLX am Albispass East — physikbasiert.

Für jede Segment-Fahrt wird die *nötige* Leistung aus der Physik gerechnet
    P = (m·g·Δh/t + Crr·m·g·v + ½·ρ·CdA·v³) / Antriebswirkungsgrad
mit m = Tagesgewicht (weights.json) + Velo (fahrfertig) + Kleidung/Gepäck.
Die Differenz `gemessen − Physik` ist der Instrumenten-Offset des jeweiligen
Powermeters. Absolutwerte hängen von Crr/CdA ab; die *Differenz* SL−SLX ist
robust, weil beide dasselbe Segment bei fast gleicher Geschwindigkeit fahren.

  ./albis_offset.py            # alle Fahrten + Jahreszeit-Fenster
"""
import json
import glob
import statistics as st

SEGMENT_ID = 660784           # Albispass East
DIST_M = 2923.21
ELEV_M = 227.0                # 726.6 − 499.6
G = 9.81
CRR = 0.004                   # Rennrad, guter Asphalt
CDA = 0.32                    # Oberlenker/Bremsgriffe am Berg
RHO = 1.15                    # ~600 m ü. M., mild
DRIVE = 0.975                 # Antriebsstrang-Wirkungsgrad
KIT_KG = 2.05                 # kurz/kurz + Helm + Schuhe + Minimalrucksack (Normalfall)
BIKES = {"b14743198": ("SL", 8.50), "b18052102": ("SLX", 7.80)}


def efforts():
    weights = json.load(open("weights.json"))
    out = []
    for path in glob.glob("activities/cycling/*/*/*.json"):
        act = json.load(open(path))
        gear = act.get("gear_id")
        if gear not in BIKES:
            continue
        day = act["start_date_local"][:10]
        if day not in weights:
            continue
        for eff in act.get("segment_efforts", []):
            if eff["segment"]["id"] != SEGMENT_ID or not eff.get("average_watts"):
                continue
            name, bike_kg = BIKES[gear]
            mass = weights[day] + bike_kg + KIT_KG
            t = eff["moving_time"]
            v = DIST_M / t
            physics = (mass * G * ELEV_M / t
                       + CRR * mass * G * v
                       + 0.5 * RHO * CDA * v ** 3) / DRIVE
            out.append({"date": day, "bike": name, "time": t, "mass": mass,
                        "hr": eff.get("average_heartrate"),
                        "temp": act.get("average_temp"),
                        "watts": eff["average_watts"], "physics": physics,
                        "offset": eff["average_watts"] - physics})
    return sorted(out, key=lambda r: r["date"])


def linreg(xs, ys):
    """Kleinste-Quadrate-Fit y = a + b·x; gibt (b, a, r, se_b) zurück."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    b = sxy / sxx
    a = my - b * mx
    r = sxy / (sxx * syy) ** 0.5
    resid = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    se_b = (resid / (n - 2) / sxx) ** 0.5
    return b, a, r, se_b


def temp_drift(rows):
    """Instrumenten-Offset gegen Temperatur — quantifiziert die SL-Drift."""
    print("\nTemperatur-Abhängigkeit des Offsets (offset = a + b·°C):")
    for bike in ("SL", "SLX"):
        pts = [(r["temp"], r["offset"]) for r in rows
               if r["bike"] == bike and r["temp"] is not None]
        if len(pts) < 4:
            print(f"  {bike:4} zu wenige Punkte (n={len(pts)})")
            continue
        xs, ys = zip(*pts)
        b, a, r, se_b = linreg(xs, ys)
        print(f"  {bike:4} {b:+5.2f} ± {se_b:.2f} W/°C   r={r:+.2f}   "
              f"n={len(pts)}   Temp {min(xs):.0f}–{max(xs):.0f}°C   "
              f"(Offset@10°C {a + b * 10:+.0f}, @25°C {a + b * 25:+.0f} W)")


def report(rows, label):
    stats = {}
    for bike in ("SL", "SLX"):
        vals = [r["offset"] for r in rows if r["bike"] == bike]
        if len(vals) < 2:
            return
        stats[bike] = (st.mean(vals), st.stdev(vals) / len(vals) ** 0.5, len(vals))
    delta = stats["SL"][0] - stats["SLX"][0]
    se = (stats["SL"][1] ** 2 + stats["SLX"][1] ** 2) ** 0.5
    print(f"{label:24} SL {stats['SL'][0]:+6.1f} W (n={stats['SL'][2]:2d})   "
          f"SLX {stats['SLX'][0]:+6.1f} W (n={stats['SLX'][2]:2d})   "
          f"→ Δ {delta:+5.1f} ± {se:.1f} W")


def main():
    rows = efforts()
    print("Instrumenten-Offset (gemessen − Physik), echtes Tagesgewicht:\n")
    report(rows, "alle Fahrten 2026")
    report([r for r in rows if "2026-06" <= r["date"][:7] <= "2026-07"],
           "nur Jun–Jul (überlappend)")
    print("\nBike-unabhängige Physik-Leistung pro HF-Schlag (Kontrolle — sollte "
          "gleich sein):")
    for window, sel in (("alle 2026", lambda r: True),
                        ("Jun–Jul", lambda r: "2026-06" <= r["date"][:7] <= "2026-07")):
        parts = []
        for bike in ("SL", "SLX"):
            vals = [r["physics"] / r["hr"] for r in rows if r["bike"] == bike and r["hr"] and sel(r)]
            parts.append(f"{bike} {st.mean(vals):.3f}")
        print(f"  {window:10} " + "   ".join(parts))
    temp_drift(rows)
    masses = [r["mass"] for r in rows]
    print(f"\nSystemmasse über alle Fahrten: {min(masses):.2f}–{max(masses):.2f} kg "
          f"(Spannweite {max(masses) - min(masses):.2f} kg)")


if __name__ == "__main__":
    main()
