#!/usr/bin/env python3
"""Erkennt anhand der Sensor-Seriennummern in einer FIT-Datei, welches Velo gefahren wurde.

Strava liefert keine Sensor-IDs — `device_name` ist immer der Edge, der zwischen den
Velos wandert. Die originale FIT-Datei aus Garmin Connect enthält dagegen `device_info`-
Records mit Hersteller, Produkt und Seriennummer je gekoppeltem Sensor. Powermeter und
Di2 sind pro Velo verschieden und damit ein eindeutiger Fingerabdruck.

  ./bike_fingerprint.py <datei.fit|datei.zip> [...]     # Velo bestimmen
  ./bike_fingerprint.py --dump <datei>                  # alle device_info-Records zeigen

Verifiziert am 2026-08-25 gegen je eine bekannte SL- und SLX-Fahrt.
"""
import sys
import glob
import os
import tempfile
import zipfile

from fitparse import FitFile

# Powermeter-Seriennummer → (gear_id, Name). Die Di2-Serial dient als Gegenprobe.
BIKES = {
    2297797936: ("b14743198", "Canyon Ultimate CF SL 7 Di2"),
    2135169775: ("b18052102", "Canyon Ultimate CF SLX 8 Di2"),
}
DI2 = {
    2766562321: "b14743198",
    3329877614: "b18052102",
}
POWERMETER_MANUFACTURER = "4iiiis"
SHIMANO = 41


def device_records(path: str) -> list[dict]:
    """device_info-Records lesen; .zip wird transparent entpackt."""
    if path.lower().endswith(".zip"):
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(path) as z:
                z.extractall(tmp)
            fits = glob.glob(os.path.join(tmp, "*.fit"))
            if not fits:
                raise SystemExit(f"{path}: keine .fit im Archiv")
            return device_records(fits[0])
    out = []
    for msg in FitFile(path).get_messages("device_info"):
        out.append({f.name: f.value for f in msg})
    return out


def identify(path: str) -> tuple[str | None, str, list[str]]:
    """(gear_id, Beschreibung, Hinweise) für eine Aktivitätsdatei."""
    recs = device_records(path)
    notes = []
    pm = di2 = None
    for d in recs:
        serial = d.get("serial_number")
        if serial is None:
            continue
        if d.get("manufacturer") == POWERMETER_MANUFACTURER and serial in BIKES:
            pm = serial
        elif d.get("manufacturer") == SHIMANO and serial in DI2:
            di2 = serial

    if pm is None and di2 is None:
        unknown = sorted({d.get("serial_number") for d in recs if d.get("serial_number")})
        return None, "unbekannt", [f"keine bekannte Serial gefunden; gesehen: {unknown}"]

    gear, name = BIKES[pm] if pm else (DI2[di2], "(nur über Di2 erkannt)")
    if pm and di2 and DI2[di2] != gear:
        notes.append(f"⚠ Powermeter sagt {gear}, Di2 sagt {DI2[di2]} — widersprüchlich")
    if pm is None:
        notes.append("Powermeter nicht erkannt, nur Di2")
    if di2 is None:
        notes.append("Di2 nicht erkannt, nur Powermeter")
    return gear, name, notes


def dump(path: str) -> None:
    for d in device_records(path):
        print(f"  idx={str(d.get('device_index')):10} "
              f"hersteller={str(d.get('manufacturer')):10} "
              f"produkt={str(d.get('product') or d.get('garmin_product')):8} "
              f"serial={str(d.get('serial_number')):12} "
              f"sw={d.get('software_version')}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    if args[0] == "--dump":
        for p in args[1:]:
            print(f"=== {p} ===")
            dump(p)
        return
    for p in args:
        gear, name, notes = identify(p)
        tag = f"{gear}  {name}" if gear else "?  unbekannt"
        print(f"{os.path.basename(p):40} → {tag}")
        for n in notes:
            print(f"{'':40}   {n}")


if __name__ == "__main__":
    main()
