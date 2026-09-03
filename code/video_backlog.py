#!/usr/bin/env python3
"""Backlog fürs Posten an Nicht-Fahr-Tagen — was ist noch nicht auf Instagram?

Quellen:
- content/video-log.csv (Spalte `status`: gepostet | verfügbar | reel-erstellt).
  Clips mit status=gepostet gelten als verbraucht; verfügbar/reel-erstellt = Backlog.
- Roh-Clips im Dropbox-Ordner, die noch gar nicht katalogisiert sind.
- Fertige, noch nicht gepostete Reels in Dropbox/reels/ (nicht in posted/).

  ./video_backlog.py [--days N]
"""
import os, csv, glob, sys, argparse
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reel

LOG = os.path.join(HERE, "content", "video-log.csv")


def load_log():
    if not os.path.exists(LOG):
        return {}
    return {r["clip"].strip(): r for r in csv.DictReader(open(LOG))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21)
    a = ap.parse_args()
    folder = os.path.expanduser(reel.cfg_reel()["folder"])
    log = load_log()
    posted = {c for c, r in log.items() if (r.get("status") or "").startswith("gepostet")}
    cutoff = datetime.now(timezone.utc) - timedelta(days=a.days)

    vids = [p for p in glob.glob(os.path.join(folder, "*"))
            if os.path.splitext(p)[1].lower() in reel.VIDEO_EXT]
    recent = [(p, reel.creation_time(p)) for p in vids]
    recent = [(p, ct) for p, ct in recent if ct and ct >= cutoff]
    backlog = [(p, ct) for p, ct in recent if os.path.basename(p) not in posted]

    acts = reel.load_activities()
    matches = reel.match_clip([p for p, _ in backlog if os.path.basename(p) not in log], acts)

    print(f"Backlog (letzte {a.days} Tage): {len(backlog)} verfügbar / "
          f"{len(recent)} Clips, {len(posted)} gepostet\n")
    for p, ct in sorted(backlog, key=lambda x: x[1], reverse=True):
        name = os.path.basename(p)
        dur = reel.duration(p) or 0
        r = log.get(name)
        if r:
            info = f"📋 {r.get('status', '?')}: {r.get('topic', '')}"
        else:
            m = matches.get(p)
            info = (f"{m[0].get('name', '?')} ({m[0]['id']})" if m
                    else "kein Ride-Match (Reserve/Standbild?)")
        print(f"  {name:32s} {ct.astimezone().strftime('%a %d.%m %H:%M')}  ~{dur:>3.0f}s  → {info}")

    # Fertig gerenderte, noch nicht gepostete Reels (Dropbox/reels, ohne posted/)
    reels_dir = os.path.expanduser(os.path.join(os.path.dirname(folder), "reels"))
    ready = [p for p in glob.glob(os.path.join(reels_dir, "*.mp4"))]
    if ready:
        print(f"\nFertige Reels bereit zum Posten (Dropbox/reels/): {len(ready)}")
        for p in sorted(ready):
            print(f"  🎬 {os.path.basename(p)}")


if __name__ == "__main__":
    main()
