#!/usr/bin/env python3
"""Passt b2w/b2h-Aktivitäten auf Strava an: Titel (b2w/b2h/Albis + Intervalle + Regen)
und Velo (gear_id via Garmin-FIT-Fingerprint).

SICHERHEIT:
- Standard = **Dry-Run** (zeigt nur, was es ändern *würde*). Erst --write schreibt.
- Umbenannt wird nur, wenn der aktuelle Name ein **Strava-Default** ist
  („Fahrt am Morgen", „Abendradfahrt", …). Eigener Name → nur mit --force.
  (--force ist Tom vorbehalten; Claude nutzt es nicht.)
- Regen kommt via --rain N (SLX = immer 0; SL fragt Claude Tom).
- Eine **bestehende `description`** wird nicht ueberschrieben: --append-desc
  haengt an, --force ersetzt. Sonst bricht das Skript ab.

  ./strava_enrich.py <strava_id> [--rain N] [--write] [--force] [--no-gear]
"""
import os, re, sys, json, glob, argparse, tempfile, subprocess, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))
B2W_S, B2W_E = (47.185, 8.467), (47.373, 8.528)
SL, SLX = "b14743198", "b18052102"
BIKE_NAME = {SL: "Canyon Ultimate CF SL 7 Di2", SLX: "Canyon Ultimate CF SLX 8 Di2"}
# Strava-Default-Namen (DE + EN), die gefahrlos überschrieben werden dürfen
DEFAULT_RE = re.compile(
    r"^(Fahrt am (Morgen|Mittag|Nachmittag|Abend)|(Morgen|Vormittag|Mittag|Nachmittag|Abend|Nacht)radfahr(en|t)|"
    r"Radfahren|(Morning|Lunch|Afternoon|Evening|Night) Ride|Ride|"
    r"[A-Za-zÄÖÜäöü]+ (Radfahren|Rennradfahren|Cycling))\s*$")


def load_env():
    for line in open(os.path.join(HERE, ".env")):
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())


def near(p, q, tol=0.004):
    return p and q and abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol


def find_json(aid):
    hits = glob.glob(os.path.join(HERE, f"activities/*/*/*/{aid}.json"))
    if not hits:
        sys.exit(f"Aktivität {aid} nicht in activities/ gefunden (erst syncen).")
    return hits[0], json.load(open(hits[0]))


def route_prefix(d):
    s, e = tuple(d.get("start_latlng") or []), tuple(d.get("end_latlng") or [])
    if near(s, B2W_S) and near(e, B2W_E):
        return "b2w"
    if near(s, B2W_E) and near(e, B2W_S):
        # b2h; Albis, wenn viel Höhe am Stück
        return "b2h Albis" if (d.get("total_elevation_gain") or 0) > 350 else "b2h"
    return None


def interval_label(d):
    """Erkennt harte Intervalle aus den Laps → z. B. '3x8'. Best-effort."""
    laps = d.get("laps") or []
    avg = d.get("average_watts") or 0
    if not laps or not avg:
        return ""
    hard = []  # (dauer_s) zusammenhängender harter Blöcke
    cur = 0
    for l in laps:
        w = l.get("average_watts") or 0
        t = l.get("moving_time") or 0
        # 1.2×Ø statt 1.25×: bei einer schnellen Fahrt (Ø 250 W, 21.09.) lag die Schwelle
        # sonst bei 312 W und die 304/308-W-Blöcke der 3×8 fielen durch → Titel ohne „3x8".
        if w > max(260, 1.2 * avg) and t >= 30:
            cur += t
        else:
            if cur >= 180:
                hard.append(cur)
            cur = 0
    if cur >= 180:
        hard.append(cur)
    if len(hard) < 2:
        return ""
    mins = round(sum(hard) / len(hard) / 60)
    return f"{len(hard)}x{mins}"


def build_name(prefix, intervals, rain):
    parts = [prefix]
    if intervals:
        parts.append(intervals)
    if rain > 0:
        parts.append("🌧️" * min(rain, 3))
    return " ".join(parts)


def fingerprint_gear(d):
    """Garmin-FIT über Startzeit matchen → gear_id. Sparsam (Rate-Limit)."""
    from garmin_sync import garmin
    import importlib.util
    spec = importlib.util.spec_from_file_location("bf", os.path.join(HERE, "bike_fingerprint.py"))
    bf = importlib.util.module_from_spec(spec); spec.loader.exec_module(bf)
    st = datetime.strptime(d["start_date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    c = garmin.login()
    for a in c.get_activities(0, 12):
        gt = a.get("startTimeGMT")
        if not gt:
            continue
        agt = datetime.strptime(gt, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if abs((agt - st).total_seconds()) < 120:
            data = c.download_activity(a["activityId"], dl_fmt=c.ActivityDownloadFormat.ORIGINAL)
            p = os.path.join(tempfile.gettempdir(), f"{a['activityId']}.zip"); open(p, "wb").write(data)
            gear, name, _ = bf.identify(p)
            return gear, name
    return None, "kein Garmin-Match"


def strava_client():
    from strava_sync.strava import StravaClient
    cl = StravaClient(Path(os.path.join(HERE, ".strava_tokens.json")))
    cl._ensure_fresh()
    return cl


def strava_token():
    return strava_client().tokens["access_token"]


def refetch(aid, path):
    """Lokales JSON nach dem Strava-Write neu holen, damit local == Strava.
    Danach .md neu erzeugen. Verhindert die JSON/Strava-Divergenz."""
    detail = strava_client().get_activity(int(aid))
    Path(path).write_text(json.dumps(detail, indent=2, default=str))
    subprocess.run([sys.executable, os.path.join(HERE, "activity_report.py"), path], check=False)
    print(f"   ↻ lokales JSON + .md aktualisiert (jetzt = Strava)")


def strava_update(aid, fields):
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(f"https://www.strava.com/api/v3/activities/{aid}", data=body, method="PUT")
    req.add_header("Authorization", f"Bearer {strava_token()}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("aid")
    ap.add_argument("--rain", type=int, default=0)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-gear", action="store_true")
    ap.add_argument("--route", choices=["b2w", "b2h", "b2h Albis"],
                    help="Route ausdruecklich setzen, wenn der Koordinatenfilter nicht "
                         "greift (z. B. Fahrt endet 900 m vor zuhause, weil noch ein "
                         "Umweg folgte — 21.09.2026)")
    ap.add_argument("--desc-file", help="Textdatei → Strava-description")
    ap.add_argument("--append-desc", action="store_true",
                    help="an eine bestehende Beschreibung anhaengen statt ersetzen")
    a = ap.parse_args()
    load_env()
    path, d = find_json(a.aid)
    prefix = a.route or route_prefix(d)
    if not prefix:
        sys.exit(f"{a.aid}: keine b2w/b2h-Route — übersprungen. "
                 f"(Mit --route b2w|b2h|'b2h Albis' ausdruecklich setzen.)")
    if a.route and a.route != route_prefix(d):
        print(f"ℹ️  Route von Hand gesetzt: {a.route} "
              f"(Filter sagte: {route_prefix(d) or 'keine'})")

    cur_name = (d.get("name") or "").strip()
    is_default = bool(DEFAULT_RE.match(cur_name))

    # Velo bestimmen — MUSS vor dem Regen-Entscheid laufen: das lokale JSON trägt
    # oft noch den Profil-Default (SLX), der Fingerprint korrigiert das. Wer den
    # Regen am Default festmacht, verschluckt an SL-Regentagen das 🌧️.
    fp_gear = fp_name = None
    if not a.no_gear:
        try:
            fp_gear, fp_name = fingerprint_gear(d)
        except Exception as e:
            fp_name = f"Fingerprint-Fehler: {type(e).__name__}"

    # SLX = Schönwetter-Velo → nie Regen. Massgeblich ist das fingerprintete Velo,
    # sonst der bestehende gear_id.
    effective_gear = fp_gear or d.get("gear_id")
    rain = 0 if effective_gear == SLX else a.rain
    target = build_name(prefix, interval_label(d), rain)

    print(f"Aktivität {a.aid}  ({d.get('start_date_local','')[:16]})")
    print(f"  Name:  '{cur_name}'  →  '{target}'"
          + ("" if is_default or a.force else "   ⛔ kein Default-Name → NICHT umbenennen (bräuchte --force)"))
    cur_gear = d.get("gear_id")
    if fp_gear:
        chg = "" if fp_gear == cur_gear else f"   ⚠️ ÄNDERUNG von {BIKE_NAME.get(cur_gear, cur_gear)}"
        print(f"  Velo:  {BIKE_NAME.get(fp_gear, fp_gear)} (Fingerprint){chg}")
    else:
        print(f"  Velo:  – ({fp_name})")

    fields = {}
    if (is_default or a.force) and target != cur_name:
        fields["name"] = target
    if fp_gear and fp_gear != cur_gear:
        fields["gear_id"] = fp_gear
    if a.desc_file:
        new_desc = Path(a.desc_file).read_text().strip()
        # Die bestehende Beschreibung MUSS live von Strava kommen: das lokale
        # JSON stammt aus der Listen-API und fuehrt `description` immer als
        # None — ein Schutz auf dieser Basis wuerde nie ausloesen.
        cur_desc = (strava_client().get_activity(int(a.aid)).get("description") or "").strip()
        # Schutz analog zum Namen: eine bereits geschriebene Beschreibung wird
        # nicht stillschweigend ueberschrieben. Aus einer Fahrt entstehen oft
        # mehrere Reels — dann gehoeren alle in dieselbe Beschreibung.
        # (Am 28.08.2026 hat genau das die Drift-Antwort geloescht.)
        if cur_desc and not (a.force or a.append_desc):
            print(f"\n⛔ Aktivitaet hat bereits eine Beschreibung ({len(cur_desc)} Zeichen):")
            print("   " + "\n   ".join(cur_desc.splitlines()[:6]))
            if len(cur_desc.splitlines()) > 6:
                print("   …")
            sys.exit("\n→ NICHT ueberschrieben. --append-desc haengt an, --force ersetzt.")
        fields["description"] = (cur_desc + "\n\n" + new_desc) if (cur_desc and a.append_desc) else new_desc
    if not fields:
        print("\n→ nichts zu ändern.")
        return
    if not a.write:
        print(f"\n[DRY-RUN] würde schreiben: {fields}   (mit --write ausführen)")
        return
    strava_update(a.aid, fields)
    print(f"\n✅ geschrieben: {fields}")
    refetch(a.aid, path)


if __name__ == "__main__":
    main()
