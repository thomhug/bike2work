#!/usr/bin/env python3
"""Velo-Videos zu fertigen Instagram-Reels verarbeiten.

Pipeline:  Clip finden → Fahrt zuordnen → transkribieren (CH-Dt → Hochdeutsch)
           → Untertitel einbrennen → Hook-Frame → Caption aus den Fahrdaten

  ./reel.py clips --date 2026-08-25          # welche Clips gehören zu welcher Fahrt?
  ./reel.py caption <activity-id> [--topic z2]
  ./reel.py build <clip> [--activity <id>]   # (folgt: Transkript + Untertitel)

Quellen (`--source`):
  folder        Ordner, den Dropbox/Nextcloud/Syncthing füllt   (Linux + Mac)
  apple-photos  Apple-Photos-Mediathek über osxphotos           (nur Mac)

Konfiguration in config.yaml unter `reel:`.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))


def _ensure_ffmpeg_path() -> None:
    """ffmpeg-full in den PATH heben — nur auf dem Mac (Homebrew keg-only,
    das System-ffmpeg dort kann kein zscale/tonemap → HDR-Clips scheitern).
    Auf Linux ein No-op: das System-ffmpeg ist voll ausgestattet.
    Gleiche Logik wie reel_render.sh / reel_transcribe.sh, damit auch der
    direkte Aufruf (z. B. `reel.py burn --overlay`, ohne Wrapper) läuft."""
    extra = os.environ.get("FFMPEG_FULL_BIN")
    if extra and os.path.isdir(extra):
        os.environ["PATH"] = extra + os.pathsep + os.environ["PATH"]
    mac = "/opt/homebrew/opt/ffmpeg-full/bin"
    if sys.platform == "darwin" and os.path.isdir(mac):
        os.environ["PATH"] = mac + os.pathsep + os.environ["PATH"]


_ensure_ffmpeg_path()

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi"}
# Clips zählen zur Fahrt, wenn sie in dieses Fenster um sie herum fallen
PAD = timedelta(minutes=20)

TOPICS = {
    "z2": "Z2-Training",
    "kleidung": "Kleidung fürs Ganzjahres-Bike2Work",
    "material": "Material: tubeless, Wachskette, Schutzbleche, Di2",
    "claude": "Auswertung & Automatisierung mit Claude Code",
}


# --------------------------------------------------------------------------- Quellen

def clips_from_folder(root: str, start: datetime, end: datetime) -> list[str]:
    """Clips im Zeitfenster. Vorfilter über Dateiname/mtime, damit ffprobe nur
    auf Kandidaten läuft — die Mediathek hat schnell hunderte Dateien.

    Das Fenster ist bewusst der ganze Tag, nicht die Fahrt: Velo-Inhalte
    entstehen auch neben dem Sattel (Kette wachsen, Velo waschen, Material).
    Die Fahrt-Zuordnung ist eine Anreicherung, kein Filter.
    """
    out = []
    for path in glob.glob(os.path.join(os.path.expanduser(root), "**", "*"), recursive=True):
        if os.path.splitext(path)[1].lower() not in VIDEO_EXT:
            continue
        if not _plausible(path, start, end):
            continue
        ts = creation_time(path)
        if ts and start <= ts <= end:
            out.append(path)
    return sorted(out)


def is_landscape(path: str) -> bool:
    try:
        r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                            "-show_streams", "-select_streams", "v:0", path],
                           capture_output=True, text=True, timeout=30)
        st = json.loads(r.stdout)["streams"][0]
        w, h = int(st["width"]), int(st["height"])
        # Rotation steht nur in der Display Matrix. Nicht über alle side_data
        # iterieren — danach folgen weitere Einträge ohne Rotationsfeld.
        rot = 0
        for sd in st.get("side_data_list", []):
            if sd.get("side_data_type") == "Display Matrix":
                rot = abs(int(sd.get("rotation", 0) or 0)) % 360
        if rot in (90, 270):
            w, h = h, w
        return w > h
    except Exception:
        return False


def duration(path: str) -> float | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, text=True, timeout=30)
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return None


def _plausible(path: str, start: datetime, end: datetime) -> bool:
    """Billiger Vorfilter: Dropbox nennt Dateien 'YYYY-MM-DD HH.MM.SS.mov'.
    Greift der Name nicht, entscheidet die mtime mit grosszügigem Puffer."""
    name = os.path.basename(path)
    if len(name) >= 10 and name[4] == "-" and name[7] == "-":
        day = name[:10]
        if start.date().isoformat() <= day <= end.date().isoformat():
            return True
        if day[:4].isdigit():
            return False
    try:
        mt = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    except OSError:
        return False
    return start - timedelta(days=1) <= mt <= end + timedelta(days=1)


def clips_from_apple_photos(start: datetime, end: datetime) -> list[str]:
    """Apple Photos über osxphotos (nur macOS)."""
    if sys.platform != "darwin":
        raise SystemExit("apple-photos geht nur auf macOS — auf Linux `--source folder` nutzen.")
    try:
        import osxphotos  # noqa: F401
    except ImportError:
        raise SystemExit("osxphotos fehlt:  pip install osxphotos")
    import osxphotos
    db = osxphotos.PhotosDB()
    out = []
    for p in db.photos(movies=True, images=False):
        ts = p.date
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts and start <= ts <= end and p.path:
            out.append(p.path)
    return sorted(out)


def probe_tags(path: str) -> dict:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout).get("format", {}).get("tags", {})
    except Exception:
        return {}


def creation_time(path: str) -> datetime | None:
    """Aufnahmezeit aus den Container-Metadaten; Fallback auf mtime.

    Reihenfolge ist wichtig: Apple schreibt zwei Zeitstempel, und der generische
    `creation_time` ist nicht immer die Aufnahmezeit (am 25.08.2026 wich er bei
    einem Clip um 31 min ab). `com.apple.quicktime.creationdate` stimmt und
    bringt zusätzlich den UTC-Offset mit. mtime allein taugt nicht — Dropbox
    setzt sie beim Kopieren neu.
    """
    tags = probe_tags(path)
    for key in ("com.apple.quicktime.creationdate", "creation_time"):
        if key in tags:
            try:
                return datetime.fromisoformat(tags[key].replace("Z", "+00:00"))
            except ValueError:
                continue
    try:
        return datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    except OSError:
        return None


def clip_latlng(path: str) -> tuple[float, float] | None:
    """GPS aus `location.ISO6709` (z. B. '+47.3731+008.5283+413.628/')."""
    iso = probe_tags(path).get("com.apple.quicktime.location.ISO6709")
    if not iso:
        return None
    import re
    nums = re.findall(r"[+-]\d+\.\d+", iso)
    return (float(nums[0]), float(nums[1])) if len(nums) >= 2 else None


# --------------------------------------------------------------------------- Fahrten

def load_activities(day: str | None = None) -> list[dict]:
    pattern = f"activities/*/{day[:4]}/{day[5:7]}/*.json" if day else "activities/*/*/*/*.json"
    out = []
    for f in glob.glob(os.path.join(HERE, pattern)):
        a = json.load(open(f))
        if day and a["start_date_local"][:10] != day:
            continue
        out.append(a)
    return sorted(out, key=lambda a: a["start_date"])


def ride_window(act: dict) -> tuple[datetime, datetime]:
    start = datetime.fromisoformat(act["start_date"].replace("Z", "+00:00"))
    return start - PAD, start + timedelta(seconds=act["elapsed_time"]) + PAD


def match_clip(clips: list[str], acts: list[dict]) -> dict[str, tuple[dict, str]]:
    """Clip-Pfad → (Aktivität, Bezug).

    Bezug unterscheidet `waehrend` von `vor`/`nach` — Clips kurz nach der Ankunft
    sind typischerweise Material-Inhalte (Velo waschen, Kette wachsen), nicht
    Aufnahmen aus dem Sattel.
    """
    hits = {}
    for c in clips:
        ts = creation_time(c)
        if not ts:
            continue
        for a in acts:
            start = datetime.fromisoformat(a["start_date"].replace("Z", "+00:00"))
            end = start + timedelta(seconds=a["elapsed_time"])
            if start <= ts <= end:
                hits[c] = (a, "waehrend")
                break
            if end < ts <= end + PAD:
                hits[c] = (a, f"nach (+{int((ts - end).total_seconds() // 60)} min)")
                break
            if start - PAD <= ts < start:
                hits[c] = (a, f"vor (−{int((start - ts).total_seconds() // 60)} min)")
                break
    return hits


# --------------------------------------------------------------------------- Transkript

# Fine-Tune auf Schweizerdeutsch, gibt direkt Hochdeutsch aus. Schlägt das
# Basismodell bei gleicher Grösse und Geschwindigkeit deutlich (siehe Commit
# 29ab215). Zahlen verhaut es trotzdem — die kommen aus den Fahrdaten.
MODEL = "jayr23/whisper-large-v3-turbo-swiss-german-ct2"
# Das Repo liefert keine preprocessor_config.json mit. faster-whisper fällt dann
# auf 80 Mel-Bänder zurück, das Modell braucht aber 128 → harter Crash.
PREPROC = {"feature_size": 128, "sampling_rate": 16000, "hop_length": 160,
           "chunk_length": 30, "n_fft": 400}


def model_path() -> str:
    from huggingface_hub import snapshot_download
    p = snapshot_download(MODEL)
    cfg = os.path.join(p, "preprocessor_config.json")
    if not os.path.exists(cfg):
        json.dump(PREPROC, open(cfg, "w"), indent=2)
    return p


def extract_audio(clip: str, wav: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip,
                    "-ac", "1", "-ar", "16000", "-vn", wav], check=True)


def transcribe(clip: str) -> list[dict]:
    """Wörter mit Zeitstempeln. Timing kommt vom Modell, Text wird danach
    gegen die Fahrdaten korrigiert."""
    from faster_whisper import WhisperModel
    import tempfile
    m = WhisperModel(model_path(), device="cpu", compute_type="int8",
                     cpu_threads=max(1, (os.cpu_count() or 4) - 4))
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        extract_audio(clip, wav)
        segs, _ = m.transcribe(wav, language="de", beam_size=5, vad_filter=True,
                               condition_on_previous_text=False, word_timestamps=True)
        words = []
        for s in segs:
            for w in (s.words or []):
                words.append({"start": w.start, "end": w.end, "word": w.word.strip()})
    return words


def cues(words: list[dict], max_chars: int = 34, max_dur: float = 3.0) -> list[dict]:
    """Wörter zu Untertitel-Zeilen bündeln — kurz genug fürs Handy.

    Bricht bevorzugt am Satzende: eine Zeile, die mit „Es" aufhört, liest sich
    schlecht.
    """
    # Erst in Sätze zerlegen — so kann keine Zeile über eine Satzgrenze laufen.
    sentences, cur_s = [], []
    for w in words:
        cur_s.append(w)
        if w["word"].rstrip().endswith((".", "!", "?", "…")):
            sentences.append(cur_s)
            cur_s = []
    if cur_s:
        sentences.append(cur_s)

    out = []
    for sent in sentences:
        cur = None
        for w in sent:
            if cur and (len(cur["text"]) + 1 + len(w["word"]) <= max_chars
                        and w["end"] - cur["start"] <= max_dur):
                cur["text"] += " " + w["word"]
                cur["end"] = w["end"]
                continue
            if cur:
                out.append(cur)
            cur = {"start": w["start"], "end": w["end"], "text": w["word"]}
        if cur:
            out.append(cur)
    # Winzlinge an den Vorgänger hängen, wenn es passt
    merged: list[dict] = []
    for c in out:
        if (merged and len(c["text"]) <= 8
                and len(merged[-1]["text"]) + 1 + len(c["text"]) <= max_chars + 6):
            merged[-1]["text"] += " " + c["text"]
            merged[-1]["end"] = c["end"]
        else:
            merged.append(c)
    return merged


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(cs: list[dict], path: str) -> None:
    with open(path, "w") as f:
        for i, c in enumerate(cs, 1):
            f.write(f"{i}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n\n")


W, H = 1080, 1920


def srt_to_ass(srt: str, ass: str, overlay: list[dict] | None = None) -> None:
    """SRT → ASS mit expliziter Pixelauflösung.

    Ohne PlayResX/Y rät libass die Skalierung — die Untertitel wurden dadurch
    zu gross und sassen auf Kinnhöhe. In ASS sind Fontsize und MarginV echte
    Pixel, damit ist die Platzierung vorhersagbar.
    """
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Reel,DejaVu Sans,58,&H00FFFFFF,&H00000000,&H80000000,-1,1,4,2,2,80,80,380,1
Style: Data,DejaVu Sans Mono,44,&H0000E5FF,&H00000000,&HB4000000,-1,3,4,0,9,0,50,120,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    def t(x: str) -> str:                      # 00:00:01,200 → 0:00:01.20
        hh, mm, rest = x.split(":")
        ss, ms = rest.split(",")
        return f"{int(hh)}:{mm}:{ss}.{ms[:2]}"

    lines = []
    for block in open(srt).read().strip().split("\n\n"):
        parts = block.strip().split("\n")
        if len(parts) < 3:
            continue
        a, b = parts[1].split(" --> ")
        text = "\\N".join(p.strip() for p in parts[2:])
        lines.append(f"Dialogue: 0,{t(a)},{t(b)},Reel,,0,0,0,,{text}")
    for c in (overlay or []):
        lines.append(f"Dialogue: 0,{_ass_t(c['start'])},{_ass_t(c['end'])},Data,,0,0,0,,{c['text']}")
    open(ass, "w").write(head + "\n".join(lines) + "\n")


def _ass_t(sec: float) -> str:
    h, r = divmod(sec, 3600); m, ss = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{ss:05.2f}"


def video_filter(fit: str, clip: str | None = None) -> str:
    """Quellformat auf 9:16 bringen.

    blur   Video mittig, unscharfer Hintergrund füllt oben/unten. Zeigt alles,
           lässt bei Querformat aber nur ~1/3 Bildhöhe übrig.
    square Quelle mittig auf 1:1 beschnitten → ~56 % Höhe. Guter Kompromiss.
    fill   Voll auf 9:16 beschnitten. Füllt den Schirm, schneidet die Seiten weg.
    """
    if fit == "auto":
        # Hochformat füllt 9:16 ohnehin; Querformat käme mit `blur` auf ~1/3
        # Bildhöhe — dafür ist `square` der bessere Kompromiss.
        fit = "square" if clip and is_landscape(clip) else "blur"
    bg = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H},gblur=sigma=28[bg]")
    if fit == "fill":
        return (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},setsar=1[v]")
    if fit == "square":
        fg = f"[0:v]crop='min(iw,ih)':'min(iw,ih)',scale={W}:{W},setsar=1[fg]"
    else:
        fg = f"[0:v]scale={W}:-2,setsar=1[fg]"
    return f"{fg};{bg};[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"


def burn(clip: str, srt: str, out: str, hook: str | None = None, crf: int = 23,
         fit: str = "auto", overlay: list[dict] | None = None,
         image: str | None = None, image_at: float = 0.0,
         image_dur: float = 3.0) -> None:
    """9:16 rendern: Video mittig auf 1080 skaliert, unscharfer Hintergrund
    füllt oben/unten (greift nur bei Querformat-Clips). Untertitel eingebrannt,
    weil Reels meist ohne Ton laufen."""
    ass = os.path.splitext(out)[0] + ".ass"
    srt_to_ass(srt, ass, overlay)
    vf = _with_tonemap(video_filter(fit, clip), clip)
    filt = f"{vf};[v]subtitles={_esc(ass)}[vs]"
    last = "[vs]"
    if hook:
        # "|" trennt Zeilen — einzeilig läuft ein Satz schnell über die Breite.
        size, txt = _hook_file(hook, out, "hook")
        # EIN drawtext mit Zeilenumbruch statt einer Box pro Zeile: sonst hängt
        # die Boxhöhe am konkreten Text (Unterlängen!) und der feste Zeilen-
        # abstand passt mal genau, mal bleibt ein Spalt.
        filt += (f";{last}drawtext=expansion=none:textfile={_esc(txt)}:fontcolor=white:fontsize={size}:"
                 f"box=1:boxcolor=black@0.62:boxborderw=22:line_spacing=16:text_align=C:"
                 f"x=(w-text_w)/2:y=300:enable='lt(t,2.5)'[vh]")
        last = "[vh]"
    if image:
        # Standbild einblenden (z. B. das Segmentprofil), 88 % Breite, mittig.
        # Kommt nach den Untertiteln, damit es sie überdeckt statt umgekehrt.
        filt += (f";[1:v]scale={int(W*0.88)}:-1[img]"
                 f";{last}[img]overlay=(W-w)/2:(H-h)/2:"
                 f"enable='between(t,{image_at},{image_at + image_dur})'[vi]")
        last = "[vi]"
    if is_hdr(clip):
        # Ans ENDE der Kette: Overlay-, Untertitel- und drawtext-Filter reichen
        # die Farbeigenschaften nicht durch, und bei -filter_complex greifen die
        # -color_*-Flags nicht. Ohne das behält die Datei die HDR-Tags der
        # Quelle, obwohl die Pixel schon BT.709 sind — der Player würde die
        # Umwandlung ein zweites Mal anwenden.
        filt += (f";{last}setparams=color_primaries=bt709:color_trc=bt709:"
                 f"colorspace=bt709[vout]")
        last = "[vout]"

    # Farb-Tags explizit setzen: ffmpeg übernimmt sonst die HDR-Tags der Quelle,
    # obwohl die Pixel bereits nach BT.709 gewandelt sind — der Player würde die
    # Umwandlung ein zweites Mal anwenden.
    col = ["-color_primaries", "bt709", "-color_trc", "bt709",
           "-colorspace", "bt709"] if is_hdr(clip) else []
    # In eine temporäre Datei rendern und erst am Ende atomar verschieben:
    # sonst liegt eine halbfertige Datei im Dropbox-Ordner (die dann synct), und
    # zwei gleichzeitige Läufe auf dasselbe Ziel würden sich vermischen.
    tmp = f"{out}.part{os.getpid()}.mp4"
    try:
        inputs = ["-i", clip] + (["-i", image] if image else [])
        subprocess.run(["ffmpeg", "-v", "error", "-y"] + inputs +
                       ["-filter_complex", filt, "-map", last, "-map", "0:a?",
                        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                        *col,
                        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                        tmp], check=True)
        os.replace(tmp, out)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# iPhone filmt in HLG/BT.2020 (Dolby Vision). Ohne Tonwert-Abbildung landen die
# Werte ungewandelt im JPEG und wirken blass — im Video fällt es nicht auf, weil
# die HDR-Tags mitwandern und der Player sie interpretiert.
HDR_TRC = {"arib-std-b67", "smpte2084"}
TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
           "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def is_hdr(path: str) -> bool:
    try:
        r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                            "-show_streams", "-select_streams", "v:0", path],
                           capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout)["streams"][0].get("color_transfer") in HDR_TRC
    except Exception:
        return False


def _hook_file(text: str, out: str, kind: str) -> tuple[int, str]:
    """Mehrzeiligen Text als Datei ablegen und passende Schriftgrösse liefern.

    `textfile` statt `text=`, weil Umlaute und Satzzeichen im Filtergraph sonst
    aufwendig zu escapen sind. "|" trennt die Zeilen.
    """
    lines = [_ascii_safe(l.strip()) for l in text.split("|") if l.strip()]
    longest = max(len(l) for l in lines)
    if kind == "title":
        size = 88 if longest <= 16 else 70
    else:
        size = 76 if longest <= 18 else 62
    path = f"{os.path.splitext(out)[0]}.{kind}.txt"
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return size, path


def _with_tonemap(chain: str, clip: str) -> str:
    """HDR-Quelle vor die Filterkette hängen — sonst wirkt das Ergebnis blass.

    Betrifft beide Zweige (Vorder- und Hintergrund), deshalb ein eigenes Label
    statt einer Teil-Ersetzung. Bestätigt am 27.08.: das gepostete Reel war auf
    Instagram sichtbar fahler als das Original, weil die Plattform beim
    Rekodieren die HLG-Tags ignoriert.
    """
    if not is_hdr(clip):
        return chain
    return f"[0:v]{TONEMAP}[src];" + chain.replace("[0:v]", "[src]")


def pip(main: str, inset: str, out: str, offset: float = 0.0, scale: float = 0.30,
        pos: str = "bl", srt: str | None = None, hook: str | None = None,
        fit: str = "auto", overlay: list[dict] | None = None) -> None:
    """Picture-in-Picture: Drohnenbild gross, Handy-Selfie klein dazu.

    Die Drohne liefert das Bild, das Handy den Ton — darum kommt der Ton
    grundsätzlich aus dem *Inset*. Beide Aufnahmen laufen parallel, sind aber
    nie gleichzeitig gestartet; `--offset` verschiebt das Inset gegen das
    Hauptbild (positiv = Inset startet später).
    """
    MARGIN = 48
    iw = int(W * scale)
    xy = {"bl": (MARGIN, f"H-h-{MARGIN}"), "br": (f"W-w-{MARGIN}", f"H-h-{MARGIN}"),
          "tl": (MARGIN, MARGIN), "tr": (f"W-w-{MARGIN}", MARGIN)}[pos]
    chain = _with_tonemap(video_filter(fit, main), main)          # [v] = Hauptbild 9:16
    # Dünner heller Rand, damit sich das Inset vom Hintergrund abhebt
    chain += (f";[1:v]scale={iw}:-1,setsar=1,"
              f"pad=iw+6:ih+6:3:3:color=white@0.85[pip]")
    chain += f";[v][pip]overlay={xy[0]}:{xy[1]}[pv]"
    last = "[pv]"
    if srt or overlay:
        # gleiche Aufbereitung wie in burn(): SRT → ASS mit fester Pixelauflösung.
        # Die Datenbox sitzt oben RECHTS — das Inset gehört dann nach links.
        ass = os.path.splitext(out)[0] + ".ass"
        srt_to_ass(srt, ass, overlay)
        chain += f";{last}subtitles={_esc(ass)}[sv]"
        last = "[sv]"
    if hook:
        size, txt = _hook_file(hook, out, "hook")
        chain += (f";{last}drawtext=expansion=none:textfile={_esc(txt)}:fontcolor=white:"
                  f"fontsize={size}:box=1:boxcolor=black@0.6:boxborderw=20:line_spacing=14:"
                  f"text_align=C:x=(w-text_w)/2:y=200:enable='lt(t,2.5)'[hv]")
        last = "[hv]"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", main]
    if offset:
        cmd += ["-itsoffset", str(offset)]
    cmd += ["-i", inset, "-filter_complex", chain,
            "-map", last, "-map", "1:a?",          # Ton vom Handy, nicht von der Drohne
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
            "-shortest", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)


def cover(clip: str, out: str, title: str, at: float = 1.0,
          fit: str = "auto", data: list[str] | None = None) -> None:
    """Standbild fürs Grid und die Vorschau — bei Instagram separat hochladen.

    Nicht zu verwechseln mit dem eingebrannten Hook: der steht 2,5 s im Video
    und hält den Scroll auf. Das Cover sieht man, *bevor* abgespielt wird.
    """
    size, txt = _hook_file(title, out, "title")
    filt = _with_tonemap(video_filter(fit, clip), clip)
    last = "[v]"
    if data:
        # Wie im Video: eine Box PRO ZEILE, nicht ein Block um alles. Der
        # ASS-Style "Data" macht das automatisch (BorderStyle 3), drawtext
        # nicht — also je Zeile ein eigener Filter.
        FS, LH = 44, 50                      # Schriftgrösse, Zeilenabstand
        for i, line in enumerate(data):
            _, ltxt = _hook_file(line, out, f"data{i}")
            filt += (f";{last}drawtext=expansion=none:textfile={_esc(ltxt)}:"
                     f"fontcolor=0xFFE500:fontsize={FS}:"
                     f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf:"
                     f"box=1:boxcolor=black@0.70:boxborderw=8:"
                     f"x=w-text_w-58:y={120 + i * LH}[d{i}]")
            last = f"[d{i}]"
    # Titel tiefer, wenn die Datenbox oben rechts steht — sonst überlappen sie.
    ty = 480 if data else 320
    filt += (f";{last}drawtext=expansion=none:textfile={_esc(txt)}:fontcolor=white:fontsize={size}:"
             f"box=1:boxcolor=black@0.66:boxborderw=24:line_spacing=18:text_align=C:"
             f"x=(w-text_w)/2:y={ty}[c]")
    last = "[c]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", clip,
                    "-filter_complex", filt, "-map", last, "-frames:v", "1",
                    "-q:v", "2", out], check=True)


YT_W, YT_H = 1280, 720          # YouTube-Thumbnail: 16:9, nicht 9:16


def thumb16(clip: str, out: str, title: str, at: float = 1.0) -> None:
    """Eigenes 16:9-Thumbnail fuer YouTube.

    Das 9:16-Cover taugt dafuer nicht: YouTube legt Thumbnails in 16:9 ab und
    beschneidet ein Hochformat mittig — genau dort, wo der Hook NICHT steht.
    Bei 1080x1920 bleibt vom Bild der Streifen y=656..1263 uebrig, der Titel
    bei y=320 faellt komplett weg. Im Swipe-Feed sieht man das nie, auf der
    Kanalseite, in der Suche und im Abo-Feed dagegen immer.

    Aufbau: unscharfer Vollbild-Hintergrund, das Hochformat rechts in voller
    Hoehe, der Titel links gross daneben.
    """
    lines = [_ascii_safe(l.strip()) for l in title.split("|") if l.strip()]
    txt = f"{os.path.splitext(out)[0]}.t16.txt"
    with open(txt, "w") as f:
        f.write("\n".join(lines))
    longest = max(len(l) for l in lines)
    size = 62 if longest <= 20 else 48
    fg_w = int(YT_H * 9 / 16)                       # 405 px bei 720 Hoehe
    chain = (f"[0:v]scale={YT_W}:{YT_H}:force_original_aspect_ratio=increase,"
             f"crop={YT_W}:{YT_H},gblur=sigma=30[bg];"
             f"[0:v]scale=-1:{YT_H},crop={fg_w}:{YT_H},setsar=1[fg];"
             f"[bg][fg]overlay={YT_W - fg_w - 40}:0[base]")
    chain = _with_tonemap(chain, clip)
    chain += (f";[base]drawtext=expansion=none:textfile={_esc(txt)}:fontcolor=white:"
              f"fontsize={size}:box=1:boxcolor=black@0.72:boxborderw=22:"
              f"line_spacing=14:text_align=L:x=56:y=(h-text_h)/2[c]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", clip,
                    "-filter_complex", chain, "-map", "[c]", "-frames:v", "1",
                    "-q:v", "2", out], check=True)


def _esc(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:") + "'"


def _ascii_safe(s: str) -> str:
    """Tofu vermeiden: fehlende Glyphen mappen/entfernen. Nur für eingebrannten
    drawtext-Text (Cover/Hook) — Untertitel (libass) bleiben Unicode/Emoji-fähig."""
    for a, b in {"→": "->", "←": "<-", "↔": "<->", "·": "-",
                 "–": "-", "—": "-", "×": "x", "≈": "~"}.items():
        s = s.replace(a, b)
    s = "".join(c for c in s if ord(c) < 0x2000)   # Pfeile/Symbole/Emojis raus
    return " ".join(s.split())


# --------------------------------------------------------------------------- Overlay

# Gemessener Instrumenten-Offset je Velo (Anzeige − Physik, aus albis_offset.py,
# n=79 bzw. n=20). Wird auf die Anzeige addiert, um die echte Leistung zu zeigen.
METER_OFFSET = {"b14743198": -3.7, "b18052102": +20.4}


def ride_streams(activity_id: int) -> dict:
    """Streams holen und in reels_work/ cachen (Strava-Limits schonen)."""
    cache = os.path.join(HERE, "reels_work", f"{activity_id}.streams.json")
    if os.path.exists(cache):
        return json.load(open(cache))
    sys.path.insert(0, os.path.join(HERE, "src"))
    from dotenv import load_dotenv
    load_dotenv(os.path.join(HERE, ".env"))
    from strava_sync import strava
    from pathlib import Path
    cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
    c = strava.StravaClient(Path(os.path.join(HERE, cfg["strava_token_file"])))
    st = c.get_streams(activity_id, ["time", "watts", "heartrate",
                                     "velocity_smooth", "altitude", "distance", "latlng"])
    data = {k: v["data"] for k, v in st.items() if isinstance(v, dict) and "data" in v}
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump(data, open(cache, "w"))
    return data


def _smooth(xs: list, i: int, n: int = 5):
    w = [x for x in xs[max(0, i - n + 1):i + 1] if x is not None]
    return sum(w) / len(w) if w else None


def segment_profile(segment_id: int) -> dict | None:
    """Höhenprofil eines Strava-Segments (DEM-basiert, gecacht).

    Der Höhenstream einer *Aktivität* ist barometrisch und stark geglättet — am
    Albis lieferte er 0,8 % statt 7,8 %. Der Stream des *Segments* kommt aus dem
    Geländemodell und ist für Steigungen brauchbar.
    """
    cache = os.path.join(HERE, "reels_work", f"seg{segment_id}.json")
    if os.path.exists(cache):
        return json.load(open(cache))
    try:
        sys.path.insert(0, os.path.join(HERE, "src"))
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(os.path.join(HERE, ".env"))
        from strava_sync import strava
        cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
        c = strava.StravaClient(Path(os.path.join(HERE, cfg["strava_token_file"])))
        st = c._get(f"/segments/{segment_id}/streams",
                    keys="distance,altitude", key_by_type="true")
        d = {k: v["data"] for k, v in st.items() if isinstance(v, dict) and "data" in v}
        if "altitude" not in d or "distance" not in d:
            return None
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        json.dump(d, open(cache, "w"))
        return d
    except Exception as e:
        print(f"  (Segment-Profil {segment_id} nicht abrufbar: {str(e)[:60]})")
        return None


def grade_at(prof: dict, dist_in_seg: float, window: float = 150.0) -> float | None:
    """Steigung im Segmentprofil an einer Position, über ein Distanzfenster."""
    A, D = prof["altitude"], prof["distance"]
    if not D or dist_in_seg < 0 or dist_in_seg > D[-1]:
        return None
    def alt(x):
        lo, hi = 0, len(D) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if D[mid] <= x: lo = mid
            else: hi = mid
        if D[hi] == D[lo]:
            return A[lo]
        f = (x - D[lo]) / (D[hi] - D[lo])
        return A[lo] + f * (A[hi] - A[lo])
    a = max(0.0, dist_in_seg - window / 2)
    b = min(D[-1], dist_in_seg + window / 2)
    if b - a < 20:
        return None
    return (alt(b) - alt(a)) / (b - a) * 100


# Welche Werte das Overlay zeigt. Default passt für Training/Berg; bei
# Kleidungs- und Wetterthemen ist die Temperatur die aussagekräftige Grösse
# und Watt lenken nur ab.
OVERLAY_SETS = {
    "training": ["watts", "hr", "speed", "grade"],   # Intervalle, Berg, Z2
    "flach":    ["watts", "hr", "speed"],            # b2w ohne nennenswerte Steigung
    "wetter":   ["temp", "speed", "hr"],             # Kleidung, Regen, Kälte
    "minimal":  ["speed", "grade"],                  # Material-Themen während der Fahrt
}


def outdoor_temp(ts: float) -> float | None:
    """Aussentemperatur Cham aus Prometheus. Referenz für den Edge-Sensor, der
    aufgeheizt aus der Wohnung startet und erst im Fahrtwind auskühlt.

    Endpoint und Credentials-Datei kommen aus der Umgebung (keine privaten
    Pfade im Code):
      PROMETHEUS_URL       Basis-URL, z. B. https://host/prometheus
      PROMETHEUS_ENV_FILE  Datei mit PROMETHEUS_USER / PROMETHEUS_PASSWORD
    Fehlt eines davon, gibt es keine Referenz (Feature ist optional)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(HERE, ".env"))
    except Exception:
        pass
    base = os.environ.get("PROMETHEUS_URL")
    env = os.environ.get("PROMETHEUS_ENV_FILE")
    if not base or not env:
        return None
    env = os.path.expanduser(env)
    if not os.path.isabs(env):
        env = os.path.join(HERE, env)  # relativ zum Skript, nicht zum CWD
    try:
        creds = {}
        for line in open(env):
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip().strip("\"'")
        u, pw = creds["PROMETHEUS_USER"], creds["PROMETHEUS_PASSWORD"]
    except Exception:
        return None
    import urllib.request, urllib.parse, base64
    q = urllib.parse.urlencode({
        "query": 'sensor{location="cham",kind="outdoor",position="outdoor",type="temp"}',
        "time": int(ts)})
    r = urllib.request.Request(base.rstrip("/") + "/api/v1/query?" + q)
    r.add_header("Authorization", "Basic " + base64.b64encode(f"{u}:{pw}".encode()).decode())
    try:
        with urllib.request.urlopen(r, timeout=20) as f:
            res = json.load(f)["data"]["result"]
        return float(res[0]["value"][1]) if res else None
    except Exception:
        return None


def check_temp(clip: str, act: dict, edge: float | None) -> None:
    """Warnt, wenn das Wetter-Overlay in der Aufwärmphase des Sensors liegt.
    Erfahrungswert: im Winter braucht der Edge 10–15 min bis zum echten Wert."""
    ts = creation_time(clip)
    if not ts:
        return
    start = datetime.fromisoformat(act["start_date"].replace("Z", "+00:00"))
    mins = (ts - start).total_seconds() / 60
    ref = outdoor_temp(ts.timestamp())
    if ref is None:
        print(f"  ⚠ Temperatur: keine Referenz erreichbar (Clip bei Minute {mins:.0f})")
        return
    line = f"  Temperatur-Gegenprobe: Referenz Cham {ref:.1f} °C, Clip bei Minute {mins:.0f}"
    if edge is not None:
        line += f", Edge-Schnitt {edge:.0f} °C (Δ {edge - ref:+.1f})"
    print(line)
    if mins < 15:
        print(f"  ⚠ Erste 15 Minuten — der Sensor ist noch am Auskühlen. "
              f"Im Text die {ref:.0f} °C aus der Referenz nehmen, nicht den Displaywert.")


def overlay_cues(clip: str, activity_id: int, act: dict,
                 fields: list[str] | None = None) -> list[dict]:
    """Pro Videosekunde die Messwerte der Fahrt. `fields` wählt aus
    watts/hr/speed/grade/temp; Default ist das Training-Set."""
    fields = fields or OVERLAY_SETS["training"]
    d = ride_streams(activity_id)
    start = datetime.fromisoformat(act["start_date"].replace("Z", "+00:00"))
    ts = creation_time(clip)
    if not ts:
        raise SystemExit("Clip hat keine Aufnahmezeit — Overlay nicht möglich.")
    off = int((ts - start).total_seconds())
    dur = duration(clip) or 0
    corr = METER_OFFSET.get(act.get("gear_id"), 0.0)
    W_, HR, V, AL, DI = (d.get(k) or [] for k in
                         ("watts", "heartrate", "velocity_smooth", "altitude", "distance"))
    TP = d.get("temp") or []
    # Der Array-Index ist NICHT die Sekunde: Strava-Streams haben Lücken (hier
    # 3831 Punkte über 3893 s). Ohne diese Zuordnung lag das Overlay 47–63 s
    # daneben — per GPS gegengeprüft.
    T = d.get("time") or list(range(len(W_)))
    idx = {}
    for j, t in enumerate(T):
        idx.setdefault(int(t), j)
    last = 0
    for t in range(0, (int(T[-1]) if T else 0) + 1):
        if t in idx:
            last = idx[t]
        else:
            idx[t] = last

    # Gegenprobe: Position im Stream vs. GPS im Clip. Grosse Abweichung heisst,
    # dass die Zuordnung nicht stimmt — dann lügt das Overlay.
    g = clip_latlng(clip)
    LL = d.get("latlng")
    if g and LL and idx.get(off) is not None:
        import math
        p0 = LL[idx[off]]
        dev = math.dist((g[0] * 111320, g[1] * 75000), (p0[0] * 111320, p0[1] * 75000))
        flag = "" if dev < 60 else "   ⚠ Zuordnung prüfen!"
        print(f"  GPS-Gegenprobe: {dev:.0f} m Abweichung{flag}")

    # Segmente, die den Clip abdecken könnten — längstes zuerst (spezifischer)
    segs = []
    for eff in sorted(act.get("segment_efforts", []),
                      key=lambda e: -(e["segment"].get("distance") or 0)):
        prof = segment_profile(eff["segment"]["id"])
        if prof:
            segs.append((eff, prof))
        if len(segs) >= 6:
            break

    out = []
    for sec in range(int(dur)):
        i = idx.get(off + sec)
        if i is None or i >= len(W_ or []):
            continue
        w = _smooth(W_, i, 5)
        hr = _smooth(HR, i, 3) if HR else None
        v = _smooth(V, i, 3) if V else None
        alt = AL[i] if AL and i < len(AL) else None
        # Steigung aus dem Segmentprofil, nicht aus dem Aktivitätsstream.
        grad = None
        for eff, prof in segs:
            if eff["start_index"] <= i <= eff["end_index"] and DI:
                grad = grade_at(prof, DI[i] - DI[eff["start_index"]])
                if grad is not None:
                    break
        tp = TP[i] if TP and i < len(TP) else None
        vals = {
            "watts": f"{w + corr:.0f} W" if w is not None else None,
            "hr":    f"{hr:.0f} bpm" if hr is not None else None,
            "speed": f"{v * 3.6:.1f} km/h" if v is not None else None,
            # Ohne Segmentprofil ersatzweise die Höhe — besser als nichts.
            "grade": (f"{grad:+.1f} %" if grad is not None
                      else (f"{alt:.0f} m" if alt is not None else None)),
            "temp":  f"{tp:.0f} °C" if tp is not None else None,
        }
        lines = [vals[k] for k in fields if vals.get(k)]
        if lines:
            out.append({"start": sec, "end": sec + 1, "text": "\\N".join(lines)})
    return out


# --------------------------------------------------------------------------- Caption

def ride_facts(act: dict) -> dict:
    """Die Zahlen, mit denen sich eine Caption belegen lässt."""
    weights = {}
    p = os.path.join(HERE, "weights.json")
    if os.path.exists(p):
        weights = json.load(open(p))
    day = act["start_date_local"][:10]
    sp = (act.get("average_speed") or 0) * 3.6
    f = {
        "datum": day,
        "name": act.get("name", "").strip(),
        "km": round(act["distance"] / 1000, 1),
        "dauer": f"{act['moving_time'] // 60}:{act['moving_time'] % 60:02d}",
        "hm": round(act.get("total_elevation_gain") or 0),
        "kmh": round(sp, 1),
        "temp": act.get("average_temp"),
        "watt": round(act["average_watts"]) if act.get("average_watts") else None,
        "np": act.get("weighted_average_watts"),
        "hf": round(act["average_heartrate"]) if act.get("average_heartrate") else None,
        "hf_max": round(act["max_heartrate"]) if act.get("max_heartrate") else None,
        "gewicht": weights.get(day),
        "velo": {"b14743198": "Canyon Ultimate CF SL 7",
                 "b18052102": "Canyon Ultimate CF SLX 8"}.get(act.get("gear_id")),
    }
    if f["watt"] and f["hf"]:
        f["w_pro_hf"] = round(f["watt"] / f["hf"], 2)
    return f


def caption(act: dict, topic: str | None = None) -> str:
    """Caption-Entwurf. Bewusst ein Entwurf — der Ton kommt von Tom, nicht von mir."""
    f = ride_facts(act)
    lines = [f"{f['name']}", ""]
    stat = f"📊 {f['km']} km · {f['dauer']} · {f['hm']} hm · {f['kmh']} km/h"
    if f["temp"] is not None:
        stat += f" · {f['temp']} °C"
    lines.append(stat)
    if f["watt"]:
        p = f"⚡ {f['watt']} W"
        if f["np"]:
            p += f" (NP {f['np']})"
        if f["hf"]:
            p += f" · ❤️ {f['hf']} bpm"
        if f.get("w_pro_hf"):
            p += f" · {f['w_pro_hf']} W/Schlag"
        lines.append(p)
    lines += ["", "— dein Text hier —", ""]
    lines.append(hashtags(topic))
    return "\n".join(lines)


BASE_TAGS = ["#bike2work", "#velo", "#cycling", "#pendeln", "#roadcycling", "#schweiz"]
TOPIC_TAGS = {
    "z2": ["#z2training", "#basetraining", "#polarizedtraining", "#ausdauer", "#trainingsplan"],
    "kleidung": ["#ganzjahresradfahrer", "#radbekleidung", "#allwetter", "#wintercycling"],
    "material": ["#tubeless", "#wachskette", "#di2", "#schutzbleche", "#velotech"],
    "claude": ["#claudecode", "#ai", "#datenanalyse", "#quantifiedself", "#automation"],
}


def hashtags(topic: str | None) -> str:
    tags = list(BASE_TAGS)
    if topic in TOPIC_TAGS:
        tags = TOPIC_TAGS[topic] + tags
    return " ".join(tags[:12])


# --------------------------------------------------------------------------- CLI

def cfg_reel() -> dict:
    p = os.path.join(HERE, "config.yaml")
    return (yaml.safe_load(open(p)) or {}).get("reel", {}) if os.path.exists(p) else {}


def cmd_clips(args) -> None:
    c = cfg_reel()
    day = datetime.fromisoformat(args.date).replace(tzinfo=timezone.utc)
    lo, hi = day, day + timedelta(days=1)
    src = args.source or c.get("source", "folder")
    if src == "folder":
        root = args.folder or c.get("folder")
        if not root:
            raise SystemExit("Kein Ordner: --folder <pfad> oder config.yaml → reel.folder")
        clips = clips_from_folder(root, lo, hi)
    elif src == "apple-photos":
        clips = clips_from_apple_photos(lo, hi)
    else:
        raise SystemExit(f"Unbekannte Quelle: {src}")

    acts = load_activities(args.date)
    print(f"Fahrten am {args.date}:")
    for a in acts:
        print(f"  {a['start_date_local'][11:16]}  {a['id']}  {a.get('name', '')[:40]}")
    if not clips:
        print("\nKeine Clips gefunden.")
        return
    hits = match_clip(clips, acts)
    riding = sum(1 for v in hits.values() if v[1] == "waehrend")
    print(f"\n{len(clips)} Clip(s) an diesem Tag ({riding} aus dem Sattel):")
    for path in clips:
        ts = creation_time(path)
        dur = duration(path)
        d = f"{dur:5.1f}s" if dur else "    ?"
        loc = clip_latlng(path)
        gps = f" {loc[0]:.4f},{loc[1]:.4f}" if loc else ""
        hit = hits.get(path)
        if hit and hit[1] == "waehrend":
            tag = f"🚴 während {hit[0].get('name', '')[:24]} ({hit[0]['id']})"
        elif hit:
            tag = f"🔧 {hit[1]} {hit[0].get('name', '')[:24]}"
        else:
            tag = "🏠 ohne Bezug zu einer Fahrt"
        print(f"  {os.path.basename(path):32} {ts:%H:%M:%S} {d}{gps}  {tag}")
    print("\nWas das Video zeigt, entscheidet am Ende das Transkript — nicht der Zeitstempel.")

    if not getattr(args, "transcribe", False):
        return
    # Alle Clips aus dem Sattel transkribieren. Der geteilte Cache sorgt dafür,
    # dass nichts doppelt gerechnet wird, was die andere Maschine schon hatte.
    todo = [p for p in clips if (hits.get(p) or (None, ""))[1] == "waehrend"]
    if getattr(args, "last", False) and acts:
        # Nur die letzte Fahrt des Tages — der Normalfall beim sync, wenn man
        # gerade heimgekommen ist und die Morgenfahrt laengst erledigt war.
        newest = max(acts, key=lambda a: a["start_date_local"])
        todo = [p for p in todo if hits[p][0]["id"] == newest["id"]]
        print(f"\n(nur letzte Fahrt: {newest['start_date_local'][11:16]} "
              f"{newest.get('name','')[:30]})")
    if not todo:
        print("\nKeine Clips aus dem Sattel — nichts zu transkribieren.")
        return
    print(f"\n── {len(todo)} Clip(s) transkribieren")
    os.makedirs("reels_work", exist_ok=True)
    for p in todo:
        key = os.path.splitext(os.path.basename(p))[0]
        out = os.path.join("reels_work", key)
        c_words, _ = cache_paths(p)
        print(f"\n  {key}  {'(Cache)' if os.path.exists(c_words) else '(rechnen…)'}")
        cmd_transcribe(argparse.Namespace(clip=p, out=out, force=False))
    print(f"\n→ Rohtranskripte in reels_work/. Zahlen gegen die Fahrdaten "
          f"korrigieren, dann als <name>.srt speichern.")


def cmd_caption(args) -> None:
    acts = [a for a in load_activities() if str(a["id"]) == str(args.activity)]
    if not acts:
        raise SystemExit(f"Aktivität {args.activity} nicht gefunden.")
    print(caption(acts[0], args.topic))


# Geteilter Transkript-Cache. Beide Maschinen (Mac im Buero, Linux daheim)
# sehen denselben Dropbox-Ordner — wer zuerst transkribiert, spart es dem
# anderen. Schluessel ist der Original-Dateiname des Clips.
CACHE = os.path.expanduser("~/Dropbox/reels/transcripts")


def cache_paths(clip: str) -> tuple[str, str]:
    key = os.path.splitext(os.path.basename(clip))[0]
    return os.path.join(CACHE, key + ".words.json"), os.path.join(CACHE, key + ".raw.srt")


def cmd_transcribe(args) -> None:
    base = args.out or os.path.splitext(args.clip)[0]
    c_words, c_raw = cache_paths(args.clip)
    if os.path.exists(c_words) and not getattr(args, "force", False):
        shutil.copy(c_words, base + ".words.json")
        if os.path.exists(c_raw):
            shutil.copy(c_raw, base + ".raw.srt")
        print(f"↩ aus dem Cache: {c_raw}")
        print(f"  (schon transkribiert — mit --force neu rechnen)")
        print(open(base + ".raw.srt").read() if os.path.exists(base + ".raw.srt") else "")
        return
    words = transcribe(args.clip)
    json.dump(words, open(base + ".words.json", "w"), ensure_ascii=False, indent=1)
    cs = cues(words)
    write_srt(cs, base + ".raw.srt")
    print(f"{len(words)} Wörter, {len(cs)} Untertitel-Zeilen")
    print(f"  {base}.words.json\n  {base}.raw.srt")
    for c in cs:
        print(f"  [{c['start']:5.1f}–{c['end']:5.1f}] {c['text']}")
    print("\n→ Zahlen und Fachbegriffe gegen die Fahrdaten korrigieren, "
          "dann als .srt speichern (Zeiten unverändert lassen).")
    try:                                   # in den geteilten Cache legen
        os.makedirs(CACHE, exist_ok=True)
        c_words, c_raw = cache_paths(args.clip)
        shutil.copy(base + ".words.json", c_words)
        shutil.copy(base + ".raw.srt", c_raw)
        print(f"  ↗ im Cache abgelegt: {c_raw}")
    except OSError as e:
        print(f"  ⚠ Cache nicht beschreibbar ({e}) — nur lokal gespeichert.")


def cmd_burn(args) -> None:
    ov = None
    if getattr(args, "overlay", None):
        acts = [a for a in load_activities() if str(a["id"]) == str(args.overlay)]
        if not acts:
            raise SystemExit(f"Aktivität {args.overlay} nicht gefunden.")
        fset = getattr(args, "overlay_fields", None) or "training"
        fields = OVERLAY_SETS.get(fset) or [x.strip() for x in fset.split(",")]
        ov = overlay_cues(args.clip, int(args.overlay), acts[0], fields)
        print(f"Overlay-Felder: {', '.join(fields)}")
        if "temp" in fields:
            check_temp(args.clip, acts[0], acts[0].get("average_temp"))
        print(f"Overlay: {len(ov)} Sekunden Messwerte")
    burn(args.clip, args.srt, args.out, args.hook, args.crf, args.fit, ov,
         getattr(args, "image", None), getattr(args, "image_at", 0.0) or 0.0,
         getattr(args, "image_dur", 3.0) or 3.0)
    print(f"→ {args.out}")


def cmd_cover(args) -> None:
    data = None
    if getattr(args, "overlay", None):
        acts = [a for a in load_activities() if str(a["id"]) == str(args.overlay)]
        if acts:
            fset = getattr(args, "overlay_fields", None) or "training"
            fields = OVERLAY_SETS.get(fset) or [x.strip() for x in fset.split(",")]
            cues = overlay_cues(args.clip, int(args.overlay), acts[0], fields)
            hit = [c for c in cues if c["start"] <= args.at <= c["end"]] or cues
            if hit:
                data = hit[0]["text"].split("\\N")
                print(f"Cover-Daten (Sek. {args.at}): {' · '.join(data)}")
    cover(args.clip, args.out, args.title, args.at, args.fit, data)


<<<<<<< Updated upstream
=======
def cmd_pip(args) -> None:
    pip(args.main, args.inset, args.out, args.offset, args.scale,
        args.pos, args.srt, args.hook, args.fit)
    print(f"→ {args.out}   (Ton aus dem Inset, Bild aus der Drohne)")


>>>>>>> Stashed changes
def cmd_thumb16(args) -> None:
    thumb16(args.clip, args.out, args.title, args.at)
    print(f"→ {args.out}  (1280x720 fuer die YouTube-Kanalseite und die Suche)")
    print(f"→ {args.out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("clips", help="Clips einer Fahrt zuordnen")
    c.add_argument("--date", required=True, help="YYYY-MM-DD")
    c.add_argument("--source", choices=["folder", "apple-photos"])
    c.add_argument("--folder")
    c.add_argument("--last", action="store_true",
                   help="nur die Clips der letzten Fahrt des Tages")
    c.add_argument("--transcribe", action="store_true",
                   help="alle Clips aus dem Sattel gleich transkribieren (nutzt den geteilten Cache)")
    c.set_defaults(func=cmd_clips)
    cp = sub.add_parser("caption", help="Caption-Entwurf aus den Fahrdaten")
    cp.add_argument("activity")
    cp.add_argument("--topic", choices=sorted(TOPICS))
    cp.set_defaults(func=cmd_caption)
    t = sub.add_parser("transcribe", help="Rohtranskript + SRT (Text danach korrigieren!)")
    t.add_argument("clip")
    t.add_argument("--out", help="Zielbasis ohne Endung (Default: neben dem Clip)")
    t.add_argument("--force", action="store_true",
                   help="neu rechnen, auch wenn im geteilten Cache schon eines liegt")
    t.set_defaults(func=cmd_transcribe)
    b = sub.add_parser("burn", help="9:16 rendern, Untertitel einbrennen")
    b.add_argument("clip")
    b.add_argument("--srt", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--hook", help="Hook-Text, 2,5 s eingebrannt ('|' = Zeilenumbruch)")
    b.add_argument("--crf", type=int, default=23, help="Qualität, kleiner = besser/grösser")
    b.add_argument("--fit", choices=["auto", "blur", "square", "fill"], default="auto",
                   help="Querformat auf 9:16 bringen (Default auto)")
    b.add_argument("--image", help="Standbild einblenden (z. B. Segmentprofil)")
    b.add_argument("--image-at", type=float, help="ab welcher Sekunde (Default 0)")
    b.add_argument("--image-dur", type=float, help="wie lange (Default 3 s)")
    b.add_argument("--overlay-fields", metavar="SET",
                   help="training (Default) | flach | wetter | minimal — oder eigene Liste, "
                        "z. B. temp,speed,hr")
    b.add_argument("--overlay", metavar="ACTIVITY_ID",
                   help="Live-Daten oben rechts einblenden (korrigierte Watt, Puls, Tempo, Steigung)")
    b.set_defaults(func=cmd_burn)
    cv = sub.add_parser("cover", help="Standbild fürs Grid (separat hochladen)")
    cv.add_argument("clip")
    cv.add_argument("--out", required=True)
    cv.add_argument("--title", required=True, help="'|' = Zeilenumbruch")
    cv.add_argument("--at", type=float, default=1.0, help="Sekunde im Clip")
    cv.add_argument("--overlay", metavar="ACTIVITY_ID",
                    help="Messwerte der Fahrt mit ins Cover (wie im Video-Overlay)")
    cv.add_argument("--overlay-fields", metavar="SET",
                    help="training (Default) | flach | wetter | minimal")
    cv.add_argument("--fit", choices=["auto", "blur", "square", "fill"], default="auto")
    cv.set_defaults(func=cmd_cover)
<<<<<<< Updated upstream
=======
    pp = sub.add_parser("pip", help="Drohnenbild gross + Handy-Selfie klein (Ton vom Handy)")
    pp.add_argument("--main", required=True, help="Drohnenclip (Vollbild)")
    pp.add_argument("--inset", required=True, help="Handyclip (klein eingeblendet, liefert den Ton)")
    pp.add_argument("--out", required=True)
    pp.add_argument("--offset", type=float, default=0.0,
                    help="Inset gegen das Hauptbild verschieben, Sekunden (positiv = spaeter)")
    pp.add_argument("--scale", type=float, default=0.30, help="Inset-Breite als Anteil (Default 0.30)")
    pp.add_argument("--pos", choices=["bl", "br", "tl", "tr"], default="bl")
    pp.add_argument("--srt")
    pp.add_argument("--hook")
    pp.add_argument("--fit", choices=["auto", "blur", "square", "fill"], default="auto")
    pp.set_defaults(func=cmd_pip)
>>>>>>> Stashed changes
    t16 = sub.add_parser("thumb16", help="16:9-Thumbnail fuer YouTube (das 9:16-Cover wird dort beschnitten)")
    t16.add_argument("clip")
    t16.add_argument("--out", required=True)
    t16.add_argument("--title", required=True, help="'|' = Zeilenumbruch")
    t16.add_argument("--at", type=float, default=1.0, help="Sekunde im Clip")
    t16.set_defaults(func=cmd_thumb16)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
