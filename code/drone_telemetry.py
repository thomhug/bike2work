#!/usr/bin/env python3
"""Flugdaten aus dem DJI-Video lesen und als Overlay einblenden.

DJI legt die Telemetrie in einen **Datenstrom im MP4** (`codec_tag djmd`),
protobuf-kodiert und ohne oeffentliches Schema. Eine separate `.SRT` schreibt
die App nur, wenn „Videountertitel" eingeschaltet ist — das war hier nicht der
Fall, darum wird der Strom direkt gelesen.

Gemessen und gegengeprueft (12.09.2026, Mini 5 Pro / FC9313):

| Feld        | Bedeutung                    | Pruefung |
|-------------|------------------------------|----------|
| `.3.4.1.2/3`| Breite / Laenge (Grad)       | liegt auf dem Radweg |
| `.3.2.1/2`  | Geschwindigkeit Nord/Ost m/s | Betrag == GPS-Versatz pro Zeit |
| `.3.5.1`    | Hoehe ueber Start, mm, **NED** (negativ = oben) | passt zum Blickwinkel, Tom bestaetigt |
| `.2.9.1`    | ISO                          | steigt in der Daemmerung |
| `.1.2`      | Zeitstempel in Mikrosekunden | Differenz == Videolaenge |

⚠️ Die Feldnamen sind **abgeleitet, nicht dokumentiert**. Geschwindigkeit und
Position sind gegen unabhaengige Quellen geprueft und belastbar.

ℹ️ **Die Hoehe hat kein unabhaengiges Gegenstueck**, ist aber in sich stimmig:
beim Start um null, 14.8 m dort, wo das Bild fast senkrecht nach unten schaut,
2.8 m dort, wo es flach neben dem Velo herfliegt (Sur-Ron-Szene). Genau diese
Reihenfolge hat Tom bestaetigt. Ein erster Einwand — „2.8 m passt nicht zu 11 m
Abstand" — war falsch: bei 14 Grad Blickwinkel sieht man die Sur-Ron tatsaechlich
von der Seite, und so sieht die Aufnahme auch aus.
Wer es endgueltig belegen will: DJI Fly kann eine `.SRT` mit
Klartext-Telemetrie schreiben (Einstellung „Videountertitel") — die waere die
Referenz fuer alle Felder hier.

  ./drone_telemetry.py <video.MP4> --von 816 --bis 831           # nur anzeigen
  ./drone_telemetry.py <video.MP4> --von 816 --bis 831 \
      --clip <schnitt.mp4> --srt <srt> --out <reel.mp4> \
      [--strava-id <id>] [--felder speed,hoehe,distanz] [--hook "…"]

`--strava-id` schaltet die **Distanz zum Velo** frei: Toms Position kommt aus
dem Strava-Stream, die der Drohne aus dem Video — der Rest ist Pythagoras.

Nebenbei faellt damit eine **unabhaengige Uhrenpruefung** ab: Die Drohne folgt
mit ungefaehr gleichbleibendem Abstand, also ist der Zeitversatz richtig, bei
dem die Distanz am wenigsten schwankt. Am 12.09.2026 lag das Minimum bei 6 s
Vorlauf (Streuung 2.0 m statt 8.2 m ohne Korrektur) — derselbe Wert, den auch
Zaunpfosten und Kopfdreher im Bild ergeben haben.
"""
import os, sys, json, math, struct, argparse, subprocess, urllib.request, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "src"))
import reel

F_LAT, F_LON = ".3.4.1.2", ".3.4.1.3"
F_VN, F_VE = ".3.2.1", ".3.2.2"
F_DOWN = ".3.5.1"                 # Millimeter, NED: negativ = ueber dem Startpunkt
F_ISO = ".2.9.1"
F_US = ".1.2"                     # Mikrosekunden seit Aufnahmestart


def _varint(b, i):
    r = s = 0
    while True:
        x = b[i]; r |= (x & 0x7F) << s; i += 1; s += 7
        if not x & 0x80:
            return r, i


def _signed(v):
    return v - (1 << 64) if v >= (1 << 63) else v


def _walk(b, path="", out=None, depth=0):
    """Protobuf ohne Schema aufklappen. Wiederholte Felder: der erste gewinnt —
    fuer die hier genutzten Skalare ist das richtig."""
    if out is None:
        out = {}
    if depth > 7:
        return out
    i = 0
    while i < len(b):
        try:
            tag, i = _varint(b, i)
        except Exception:
            return out
        f, wt = tag >> 3, tag & 7
        p = f"{path}.{f}"
        try:
            if wt == 0:
                v, i = _varint(b, i); out.setdefault(p, _signed(v))
            elif wt == 2:
                l, i = _varint(b, i)
                if i + l > len(b):
                    return out
                _walk(b[i:i + l], p, out, depth + 1); i += l
            elif wt == 5:
                out.setdefault(p, struct.unpack("<f", b[i:i + 4])[0]); i += 4
            elif wt == 1:
                out.setdefault(p, struct.unpack("<d", b[i:i + 8])[0]); i += 8
            else:
                return out
        except Exception:
            return out
    return out


def telemetrie(video, von, bis):
    """Datenstrom auslesen → eine Zeile pro Sekunde im Fenster [von, bis].

    ⚠️ **Kein `-ss` auf dem Datenstrom.** Der springt nicht dorthin, wo das Video
    springt: Am 15.09.2026 lieferte `-ss 172` in Wahrheit Sekunde 269 — 97 s
    daneben, und die Zahlen im fertigen Video waren entsprechend falsch. Darum
    immer von vorn lesen und in Python schneiden. Das kostet nur Lesezeit bis
    `bis`, nicht mehr.
    """
    roh = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", video, "-t", str(int(bis) + 2),
         "-map", "0:d:0", "-c", "copy", "-f", "data", "-"],
        capture_output=True).stdout
    if not roh:
        sys.exit("Kein DJI-Datenstrom gefunden — ist das wirklich ein DJI-Video?")
    saetze, i = [], 0
    while i < len(roh) - 3:
        if roh[i] != 0x1A:                     # Feld 3, laengenkodiert
            i += 1; continue
        try:
            l, j = _varint(roh, i + 1)
        except Exception:
            break
        if j + l > len(roh):
            break
        saetze.append(_walk(roh[j:j + l])); i = j + l
    if not saetze:
        sys.exit("Datenstrom gefunden, aber nicht lesbar.")
    t0 = saetze[0].get(F_US, 0)
    reihen = {}
    for s in saetze:
        if F_LAT not in s:
            continue
        sek = int(round((s.get(F_US, t0) - t0) / 1e6))
        reihen.setdefault(sek, s)
    return [{"sek": k - int(von),
             "lat": v[F_LAT], "lon": v[F_LON],
             "kmh": math.hypot(v.get(F_VN, 0), v.get(F_VE, 0)) * 3.6,
             "hoehe": -v.get(F_DOWN, 0) / 1000.0,
             "iso": v.get(F_ISO)}
            for k, v in sorted(reihen.items()) if von <= k <= bis]


def velo_positionen(strava_id):
    """Toms Position pro Sekunde aus dem Strava-Stream."""
    spec = importlib.util.spec_from_file_location("se", os.path.join(HERE, "strava_enrich.py"))
    se = importlib.util.module_from_spec(spec); spec.loader.exec_module(se); se.load_env()
    url = (f"https://www.strava.com/api/v3/activities/{strava_id}"
           f"/streams?keys=time,latlng&key_by_type=true")
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {se.strava_token()}")
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    return dict(zip(d["time"]["data"], d["latlng"]["data"]))


def meter(a_lat, a_lon, b_lat, b_lon):
    """Kurze Distanzen: eine ebene Naeherung reicht, der Fehler liegt unter 1 cm."""
    mlat = 111_320.0
    mlon = 111_320.0 * math.cos(math.radians((a_lat + b_lat) / 2))
    return math.hypot((a_lat - b_lat) * mlat, (a_lon - b_lon) * mlon)


def cues(reihen, felder, distanzen=None, kopf="DROHNE"):
    """Kopfzeile ist Absicht: Die Box sieht aus wie das Garmin-/Strava-Overlay,
    zeigt aber Flugdaten. Ohne Beschriftung verwechselt man beides."""
    out = []
    for r in reihen:
        zeilen = [kopf] if kopf else []
        if "speed" in felder:
            zeilen.append(f"{r['kmh']:.0f} km/h")
        if "hoehe" in felder:
            zeilen.append(f"{r['hoehe']:.0f} m hoch")
        if "distanz" in felder and distanzen and r["sek"] in distanzen:
            zeilen.append(f"{distanzen[r['sek']]:.0f} m weg")
        if "iso" in felder and r["iso"]:
            zeilen.append(f"ISO {r['iso']:.0f}")
        if zeilen:
            out.append({"start": r["sek"], "end": r["sek"] + 1,
                        "text": "\\N".join(zeilen)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="das DJI-Originalvideo (nicht der Schnitt)")
    ap.add_argument("--von", type=float, required=True, help="Startsekunde im Originalvideo")
    ap.add_argument("--bis", type=float, required=True)
    ap.add_argument("--clip", help="fertiger 9:16-Schnitt, auf den gerendert wird")
    ap.add_argument("--inset", help="Handy-Clip; schaltet auf Picture-in-Picture um")
    ap.add_argument("--inset-pos", default="tl", choices=["tl", "tr", "bl", "br"],
                    help="Die Datenbox sitzt oben rechts — Default ist darum oben links")
    ap.add_argument("--inset-scale", type=float, default=0.25)
    ap.add_argument("--srt")
    ap.add_argument("--out")
    ap.add_argument("--hook")
    ap.add_argument("--strava-id", help="schaltet die Distanz zum Velo frei")
    ap.add_argument("--uhr-vorlauf", type=float, default=6.0,
                    help="Sekunden, die die Drohnenuhr VORgeht (12.09.2026: 6 s). "
                         "Unabhaengig bestimmbar: der Wert mit der kleinsten Streuung "
                         "der Distanz zum Velo ist der richtige.")
    ap.add_argument("--felder", default="speed,distanz",
                    help="speed | hoehe | distanz | iso, mit Komma getrennt")
    a = ap.parse_args()

    reihen = telemetrie(a.video, a.von, a.bis)
    felder = [f.strip() for f in a.felder.split(",")]

    distanzen = None
    if a.strava_id and "distanz" in felder:
        pos = velo_positionen(a.strava_id)
        # Videosekunde → Fahrtsekunde: Aufnahmezeit der Drohne + Versatz
        start = reel.creation_time(a.video)
        akt = [x for x in reel.load_activities() if str(x["id"]) == str(a.strava_id)][0]
        from datetime import datetime
        fahrt = datetime.fromisoformat(akt["start_date"].replace("Z", "+00:00"))
        off = (start - fahrt).total_seconds() + a.von - a.uhr_vorlauf
        distanzen = {}
        for r in reihen:
            fs = int(round(off + r["sek"]))
            p = pos.get(fs) or pos.get(fs - 1) or pos.get(fs + 1)
            if p:
                # nur die Grundriss-Distanz: die Hoehe ist nicht belastbar
                distanzen[r["sek"]] = meter(r["lat"], r["lon"], p[0], p[1])

    print(f"  Sek  {'km/h':>6} {'Hoehe':>7} {'Distanz':>8}  ISO")
    for r in reihen:
        dd = f"{distanzen[r['sek']]:7.0f}m" if distanzen and r["sek"] in distanzen else "       –"
        print(f"  {r['sek']:4} {r['kmh']:6.1f} {r['hoehe']:6.1f}m {dd}  {r['iso'] or '–'}")

    if a.clip and a.out:
        c = cues(reihen, felder, distanzen)
        if a.inset:
            reel.pip(a.clip, a.inset, a.out, scale=a.inset_scale, pos=a.inset_pos,
                     srt=a.srt, hook=a.hook, fit="square", overlay=c)
        else:
            reel.burn(a.clip, a.srt, a.out, hook=a.hook, fit="square", overlay=c)
        print(f"\n→ {a.out}")


if __name__ == "__main__":
    main()
