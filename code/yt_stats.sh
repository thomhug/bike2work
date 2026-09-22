#!/usr/bin/env bash
# YouTube-Aufrufe des Kanals via RSS — ohne API-Key, ohne Login.
# Der Feed ist aktueller als die Kanalseite (dort hängen die Zahlen nach).
# <published> steht im Feed in UTC (+00:00). Ausgabe in Europe/Zurich, sonst wird
# 05:30 als Publish-Zeit gelesen, obwohl der Post um 07:30 live ging (22.09.2026).
set -eu
CHANNEL="${1:-UCosMUN_fK7YYC6R3Y22gMPg}"
curl -s --max-time 25 "https://www.youtube.com/feeds/videos.xml?channel_id=$CHANNEL" \
| python3 -c "$(cat <<'PY'
import sys, re
from datetime import datetime
from zoneinfo import ZoneInfo
x = sys.stdin.read()
print(f'{"id":11}  {"live (Zürich)":16}  {"Aufrufe":>6}  Likes  Titel')
for e in re.findall(r'<entry>(.*?)</entry>', x, re.S):
    vid = re.search(r'<yt:videoId>(.*?)</yt:videoId>', e)
    ttl = re.search(r'<title>(.*?)</title>', e)
    pub = re.search(r'<published>(.*?)</published>', e)
    vws = re.search(r'views="(\d+)"', e)
    lks = re.search(r'thumbsUp="(\d+)"', e)
    when = "?"
    if pub:
        when = datetime.fromisoformat(pub.group(1)).astimezone(ZoneInfo("Europe/Zurich")).strftime("%Y-%m-%d %H:%M")
    print(f'{vid.group(1) if vid else "?"}  {when:16}  '
          f'{vws.group(1) if vws else "?":>6}  {lks.group(1) if lks else "0":>3}  {ttl.group(1)[:52] if ttl else "?"}')
PY
)"
