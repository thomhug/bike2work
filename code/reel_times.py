#!/usr/bin/env python3
"""Post-Zeiten (Spalte `uhrzeit`, Europe/Zurich lokal) in content/reel-stats.csv füllen.

Woher die Zeit kommt — je Plattform aus der ID/dem Feed, keine API nötig:
- **TikTok:** die Video-ID kodiert den Upload-Zeitstempel (obere 32 Bit = Unix-UTC).
- **Instagram:** der Shortcode ist base64 der Media-ID; deren obere Bits sind der
  Zeitstempel: `ms = (media_id >> 23) + 1314220021721`. (Die Verschiebung ist 23,
  nicht 22 — gegen bekannte Posts kalibriert.)
- **YouTube:** IDs sind zufällig → aus dem Kanal-RSS (`<published>`), deckt aber
  nur die ~15 neuesten Videos ab; ältere/noch nicht live bleiben leer.

Alle Zeiten werden auf **Europe/Zurich** umgerechnet (Lokalzeit des Publikums).
Nur leere `uhrzeit`-Zellen werden gefüllt (idempotent); `--force` überschreibt.

  ./reel_times.py [--force]
"""
import csv, re, sys, os, urllib.request, datetime as dt
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "content", "reel-stats.csv")
TZ = ZoneInfo("Europe/Zurich")
YT_CHANNEL = "UCosMUN_fK7YYC6R3Y22gMPg"  # @velo-tom
_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def tiktok_time(vid):
    return dt.datetime.fromtimestamp(int(vid) >> 32, TZ)


def insta_time(code):
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", code):
        return None                       # z. B. eigene Labels wie "25.8-c"
    n = 0
    for ch in code:
        n = n * 64 + _B64.index(ch)
    return dt.datetime.fromtimestamp(((n >> 23) + 1314220021721) / 1000, TZ)


def youtube_map():
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YT_CHANNEL}"
    x = urllib.request.urlopen(url, timeout=25).read().decode()
    out = {}
    for e in re.findall(r"<entry>(.*?)</entry>", x, re.S):
        v = re.search(r"<yt:videoId>(.*?)</yt:videoId>", e)
        p = re.search(r"<published>(.*?)</published>", e)
        if v and p:
            out[v.group(1)] = dt.datetime.fromisoformat(p.group(1)).astimezone(TZ)
    return out


def main():
    force = "--force" in sys.argv
    yt = youtube_map()
    rows = list(csv.reader(open(CSV)))
    hdr = rows[0]
    if "uhrzeit" not in hdr:
        hdr.insert(3, "uhrzeit")
        for r in rows[1:]:
            r.insert(3, "")
    ui = hdr.index("uhrzeit")
    filled = blank = 0
    for r in rows[1:]:
        if r[ui].strip() and not force:
            continue
        rid, plat = r[0], r[1]
        when = None
        try:
            when = {"tiktok": tiktok_time, "instagram": insta_time}.get(plat, lambda _: None)(rid)
            if plat == "youtube":
                when = yt.get(rid)
        except Exception:
            when = None
        if when:
            r[ui] = when.strftime("%H:%M"); filled += 1
        else:
            blank += 1
    csv.writer(open(CSV, "w", newline="")).writerows(rows)
    print(f"uhrzeit: {filled} gefüllt, {blank} offen (leer = nicht dekodierbar / YouTube nicht im RSS)")


if __name__ == "__main__":
    main()
