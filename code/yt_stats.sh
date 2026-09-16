#!/usr/bin/env bash
# YouTube-Aufrufe des Kanals via RSS — ohne API-Key, ohne Login.
# Der Feed ist aktueller als die Kanalseite (dort hängen die Zahlen nach).
set -eu
CHANNEL="${1:-UCosMUN_fK7YYC6R3Y22gMPg}"
curl -s --max-time 25 "https://www.youtube.com/feeds/videos.xml?channel_id=$CHANNEL" \
| python3 -c "
import sys, re
x = sys.stdin.read()
for e in re.findall(r'<entry>(.*?)</entry>', x, re.S):
    vid = re.search(r'<yt:videoId>(.*?)</yt:videoId>', e)
    ttl = re.search(r'<title>(.*?)</title>', e)
    pub = re.search(r'<published>(.*?)T(\d\d:\d\d)', e)
    vws = re.search(r'views=\"(\d+)\"', e)
    lks = re.search(r'thumbsUp=\"(\d+)\"', e)
    print(f'{vid.group(1) if vid else \"?\"}  {pub.group(1)+\" \"+pub.group(2) if pub else \"?\":16}  '
          f'{vws.group(1) if vws else \"?\":>6}  {lks.group(1) if lks else \"0\":>3}  {ttl.group(1)[:52] if ttl else \"?\"}')
"
