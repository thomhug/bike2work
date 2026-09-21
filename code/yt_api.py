#!/usr/bin/env python3
"""YouTube-Kanal per Data API v3 (+ optional Analytics) abfragen — auch geplante/private Videos.

Der RSS-Feed (`./yt_stats.sh`) zeigt nur **öffentliche** Videos. Diese Skript
loggt sich als Kanalinhaber ein und sieht damit auch `private` und
`scheduled` Uploads — inklusive Titel, Beschreibung, Thumbnail und Untertiteln,
also genau das, was sich vor der Veröffentlichung noch korrigieren lässt.

  ./yt_api.py auth              # einmalig: Login (Consent-URL → Code zurückgeben)
  ./yt_api.py list [--all]      # Videos; ohne --all nur geplant/privat
  ./yt_api.py check <videoId>   # Titel/Beschreibung/Thumbnail/SRT eines Videos prüfen
  ./yt_api.py analytics [--days N]   # Studio-Zahlen (braucht YouTube Analytics API)

OAuth-Client: youtube-sport-oauth.json (Typ "web", gitignored — enthaelt das client_secret).
Token landet in .yt_token.json — steht in .gitignore, nie committen.
"""
import os, sys, json, re, argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIENT = HERE / "youtube-sport-oauth.json"
TOKEN = HERE / ".yt_token.json"
CHANNEL = "UCosMUN_fK7YYC6R3Y22gMPg"          # @velo-tom
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]
# captions.list gibt es nur mit dem Schreib-Scope. Wer die Untertitel pruefen
# will, meldet sich einmal mit `auth --captions` neu an; sonst bleibt der
# Zugriff bewusst nur-lesend.
CAPTION_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


def _cfg():
    d = json.loads(CLIENT.read_text())
    return d.get("web") or d.get("installed")


def creds():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    if not TOKEN.exists():
        sys.exit("Kein Token — zuerst `./yt_api.py auth` ausführen.")
    c = Credentials.from_authorized_user_file(str(TOKEN))
    if not c.valid and c.refresh_token:
        c.refresh(Request())
        TOKEN.write_text(c.to_json())
    return c


def api(name="youtube", version="v3"):
    from googleapiclient.discovery import build
    return build(name, version, credentials=creds(), cache_discovery=False)


def cmd_auth(a):
    """Manueller Code-Flow: der eingetragene Redirect zeigt auf tom.li, dort
    landet der Code in der Adresszeile und wird von Hand zurückgegeben.
    Das spart es, in der Cloud-Console einen localhost-Redirect nachzutragen."""
    from google_auth_oauthlib.flow import Flow
    cfg = _cfg()
    scopes = SCOPES + ([CAPTION_SCOPE] if a.captions else [])
    redirect = cfg["redirect_uris"][0]
    flow = Flow.from_client_config({"web": cfg}, scopes=scopes, redirect_uri=redirect)
    url, _ = flow.authorization_url(access_type="offline", prompt="consent",
                                    include_granted_scopes="true")
    print("1. Diesen Link im Browser öffnen und den Zugriff bestätigen:\n")
    print(f"   {url}\n")
    print(f"2. Danach landest du auf {redirect}?code=…")
    print("   Den Wert von `code=` aus der Adresszeile hier einfügen.\n")
    code = input("code = ").strip()
    if "code=" in code:                       # ganze URL eingefügt? dann rausschneiden
        code = code.split("code=", 1)[1].split("&", 1)[0]
    from urllib.parse import unquote
    flow.fetch_token(code=unquote(code))
    TOKEN.write_text(flow.credentials.to_json())
    os.chmod(TOKEN, 0o600)
    print(f"\n✅ Token gespeichert: {TOKEN.name} (gitignored)")


def uploads_playlist(yt):
    r = yt.channels().list(part="contentDetails", id=CHANNEL).execute()
    return r["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]


def all_video_ids(yt):
    ids, page = [], None
    pl = uploads_playlist(yt)
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=pl,
                                    maxResults=50, pageToken=page).execute()
        ids += [i["contentDetails"]["videoId"] for i in r["items"]]
        page = r.get("nextPageToken")
        if not page:
            return ids


def videos(yt, ids):
    out = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="snippet,status,statistics,contentDetails",
                             id=",".join(ids[i:i + 50])).execute()
        out += r["items"]
    return out


def cmd_list(a):
    yt = api()
    vs = videos(yt, all_video_ids(yt))
    rows = []
    for v in vs:
        st, sn = v["status"], v["snippet"]
        pub = st.get("publishAt") or sn.get("publishedAt", "")
        priv = st.get("privacyStatus")
        state = "geplant" if st.get("publishAt") else priv
        if not a.all and state not in ("geplant", "private", "unlisted"):
            continue
        rows.append((pub, v["id"], state,
                     v.get("statistics", {}).get("viewCount", "–"),
                     sn["title"][:54]))
    rows.sort(reverse=True)
    if not rows:
        print("Keine geplanten oder privaten Videos." if not a.all else "Keine Videos.")
        return
    print(f"{'veröffentlicht':17} {'videoId':12} {'Status':9} {'Views':>6}  Titel")
    for pub, vid, state, vw, ttl in rows:
        print(f"{pub[:16]:17} {vid:12} {state:9} {vw:>6}  {ttl}")


def cmd_check(a):
    """Vor dem Live-Gehen prüfen: hängen Titel, Beschreibung, eigenes Thumbnail
    und vor allem die Untertitel wirklich dran? Die SRT ist der SEO-Hebel und
    geht beim manuellen Hochladen am ehesten vergessen."""
    yt = api()
    v = videos(yt, [a.video_id])
    if not v:
        sys.exit(f"Video {a.video_id} nicht gefunden (gehört es dem Kanal?).")
    v = v[0]
    sn, st = v["snippet"], v["status"]
    # captions.list verlangt den Schreib-Scope force-ssl — mit readonly gibt es 403.
    # Kein Grund abzubrechen: alles andere ist auch so prüfbar.
    caps, caps_err = [], None
    try:
        caps = yt.captions().list(part="snippet", videoId=a.video_id).execute().get("items", [])
    except Exception as e:
        t = str(e).lower()
        caps_err = ("Scope fehlt — captions.list braucht youtube.force-ssl, siehe `auth --captions`"
                    if "insufficient" in t else
                    "Tageskontingent erschoepft — nach 09:00 nochmal" if "exceeded your" in t
                    else type(e).__name__)
    custom_thumb = "maxres" in sn.get("thumbnails", {}) or "standard" in sn.get("thumbnails", {})
    print(f"Titel        : {sn['title']}")
    print(f"Status       : {st.get('privacyStatus')}"
          + (f" · geplant für {st['publishAt'][:16]}" if st.get("publishAt") else ""))
    print(f"Beschreibung : {len(sn.get('description',''))} Zeichen"
          + ("" if sn.get("description") else "   ⚠️ LEER"))
    print(f"Tags         : {len(sn.get('tags') or [])}")
    print(f"Thumbnail    : {'eigenes vorhanden' if custom_thumb else '⚠️ nur Auto-Standbild'}")
    if caps_err:
        print(f"Untertitel   : nicht abfragbar — {caps_err}")
    elif caps:
        for c in caps:
            s = c["snippet"]
            # trackKind kommt je nach Antwort als 'ASR' oder 'asr' zurueck
            asr = (s.get("trackKind") or "").lower() == "asr"
            print(f"Untertitel   : {s['language']} · "
                  f"{'automatisch erzeugt' if asr else 'hochgeladen ✓'}")
    else:
        print("Untertitel   : ⚠️ KEINE — SRT nachreichen, das ist der SEO-Hebel")
    print(f"Link         : https://youtube.com/shorts/{a.video_id}")


def cmd_analytics(a):
    """Die Studio-Zahlen: Aufrufe, Wiedergabezeit, Haltequote, Impressionen/CTR.
    Der RSS-Wert kennt davon nichts — und genau diese Felder sagen, *warum*
    ein Video läuft oder nicht."""
    import datetime
    ya = api("youtubeAnalytics", "v2")
    end = datetime.date.today()
    start = end - datetime.timedelta(days=a.days)
    r = ya.reports().query(
        ids=f"channel=={CHANNEL}", startDate=str(start), endDate=str(end),
        metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
        dimensions="video", sort="-views", maxResults=25).execute()
    rows = r.get("rows", [])
    if not rows:
        print("Keine Daten (Analytics hinkt ~1-2 Tage nach).")
        return
    yt = api()
    titles = {v["id"]: v["snippet"]["title"] for v in videos(yt, [x[0] for x in rows])}
    print(f"Letzte {a.days} Tage · {start} bis {end}\n")
    print(f"{'videoId':12} {'Views':>6} {'Min':>7} {'Ø Sek':>6} {'Ø %':>5}  Titel")
    for vid, views, mins, avgdur, avgpct in rows:
        print(f"{vid:12} {views:>6} {mins:>7} {avgdur:>6} {avgpct:>5.1f}  {titles.get(vid,'?')[:44]}")


def cmd_sources(a):
    """Zugriffsquellen pro Video. Das ist die Frage hinter dem 17:00-Fenster:
    laufen die Videos ueber den Shorts-Feed (dann zaehlt die Uhrzeit) oder
    ueber die Suche (dann zaehlt der Titel und die Uhrzeit war Zufall)?"""
    import datetime, collections
    ya = api("youtubeAnalytics", "v2")
    end = datetime.date.today(); start = end - datetime.timedelta(days=a.days)
    q = dict(ids=f"channel=={CHANNEL}", startDate=str(start), endDate=str(end),
             metrics="views", dimensions="insightTrafficSourceType", sort="-views")
    if a.video:
        q["filters"] = f"video=={a.video}"
    rows = ya.reports().query(**q).execute().get("rows", [])
    total = sum(r[1] for r in rows) or 1
    print(f"Zugriffsquellen · {start} bis {end}" + (f" · Video {a.video}" if a.video else " · ganzer Kanal") + "\n")
    NAME = {"SHORTS": "Shorts-Feed", "YT_SEARCH": "YouTube-Suche",
            "RELATED_VIDEO": "Vorgeschlagen", "YT_CHANNEL": "Kanalseite",
            "SUBSCRIBER": "Abo-Feed / Startseite", "EXT_URL": "Externe Links",
            "NO_LINK_OTHER": "Direkt / unbekannt", "PLAYLIST": "Playlist",
            "NOTIFICATION": "Benachrichtigung", "YT_OTHER_PAGE": "Andere YT-Seite"}
    for src, views in rows:
        bar = "\u2588" * max(1, round(views / total * 40))
        print(f"  {NAME.get(src, src):24} {views:6}  {views/total*100:5.1f}%  {bar}")


REELS = Path.home() / "Dropbox" / "reels"


# Toms Archiv fuer fertig gepostete Reels — liegt bewusst ausserhalb von Dropbox,
# nach Jahr sortiert. Ohne diesen Pfad findet `recaption` die SRT alter Videos nicht
# (18.09.2026: deshalb stand "Velo mit unter die Dusche" ohne Untertitel da).
ARCHIV = Path.home() / "pics"


def _archiv_dirs():
    return sorted((p for p in ARCHIV.glob("*/reels") if p.is_dir()), reverse=True)


def _find(base):
    """mp4/srt/cover/_youtube.txt zu einem Basisnamen suchen — flach in reels/,
    im Alt-Backlog reels/youtube/, in posted/ oder im Archiv ~/pics/<jahr>/reels/."""
    for d in (REELS, REELS / "youtube", REELS / "posted",
              REELS / "youtube" / "posted", *_archiv_dirs()):
        if (d / f"{base}.mp4").exists():
            return {"mp4": d / f"{base}.mp4", "srt": d / f"{base}.srt",
                    "cover": next((c for c in (d / f"{base}_cover.jpg",
                                                d / f"{base}_thumbnail.jpg") if c.exists()),
                                  d / f"{base}_cover.jpg"),
                    "meta": d / f"{base}_youtube.txt"}
    sys.exit(f"{base}.mp4 nicht gefunden (reels/, reels/youtube/, posted/, ~/pics/*/reels/).")


def _hat_eigenes_cover(yt, vid):
    """Tom setzt die Shorts-Thumbnails von Hand in Studio (die API kann das nicht,
    s.u.). Ein spaeterer `meta`-Lauf darf dieses Bild NICHT ueberschreiben — darum
    vorher fragen, ob am Video schon ein eigenes Cover haengt."""
    try:
        r = yt.videos().list(part="snippet", id=vid).execute()
        th = (r.get("items") or [{}])[0].get("snippet", {}).get("thumbnails", {})
        return "maxres" in th or "standard" in th
    except Exception:
        return False   # im Zweifel nicht blockieren


def set_thumbnail(yt, vid, path):
    from googleapiclient.http import MediaFileUpload
    if not Path(path).exists():
        print(f"  ⚠️ kein Cover gefunden ({Path(path).name})")
        return False
    if _hat_eigenes_cover(yt, vid):
        print("  ⏭️ Thumbnail uebersprungen — Video hat schon ein eigenes Cover")
        return False
    try:
        # ⚠️ Bei SHORTS greift das nicht: YouTube meldet Erfolg, setzt das Bild aber
        # nicht. Bekannter Fehler, offen im Google Issue Tracker (#381127084, dazu die
        # Funktionsanfrage #391129953). Von Hand ueber Studio geht dasselbe JPG problemlos.
        # → Thumbnails fuer Shorts IMMER in Studio setzen, hier nur der Vollstaendigkeit
        #   halber. mimetype ist trotzdem explizit, das war frueher geraten.
        yt.thumbnails().set(
            videoId=vid,
            media_body=MediaFileUpload(str(path), mimetype="image/jpeg",
                                       resumable=False)).execute()
        print("  ✅ Thumbnail gesetzt (von Hand in Studio gegenpruefen)"); return True
    except Exception as e:
        print(f"  ⚠️ Thumbnail fehlgeschlagen: {e}"); return False


def set_captions(yt, vid, path):
    """Direkt nach dem Upload antwortet die Caption-API gelegentlich mit 403,
    obwohl der Scope stimmt — das Video ist dann noch nicht ganz durch. Darum
    mehrere Anlaeufe statt Abbruch."""
    import time
    from googleapiclient.http import MediaFileUpload
    if not Path(path).exists():
        print(f"  ⚠️ keine SRT gefunden ({Path(path).name})")
        return False
    for versuch in range(4):
        try:
            # ⚠️ Sprache MUSS "de" sein, nicht "de-CH". YouTubes Spracherkennung legt
            # ihre eigene Spur unter "de" an und zerlegt Schweizerdeutsch dabei voellig
            # ("Claude Code" -> "Clot Code"). Eine Spur unter "de-CH" ist fuer YouTube
            # eine ANDERE Sprache — sie verdraengt die Automatik nicht, sondern liegt
            # daneben, und wer auf Deutsch eingestellt ist, bekommt den Maschinentext.
            # Unter "de" hochgeladen ersetzt unsere Spur die automatische.
            yt.captions().insert(part="snippet",
                body={"snippet": {"videoId": vid, "language": "de",
                                  "name": "", "isDraft": False}},
                media_body=MediaFileUpload(str(path))).execute()
            print("  ✅ Untertitel hochgeladen"); return True
        except Exception as e:
            if versuch == 3:
                print(f"  ⚠️ Untertitel fehlgeschlagen: {e}"); return False
            time.sleep(5 * (versuch + 1))


def cmd_fix(a):
    """Thumbnail und/oder SRT an ein bereits hochgeladenes Video nachreichen."""
    yt = api()
    f = _find(a.base)
    set_thumbnail(yt, a.video_id, f["cover"])
    set_captions(yt, a.video_id, f["srt"])


def cmd_upload(a):
    """Video hochladen und auf einen Zeitpunkt planen — inklusive Thumbnail und SRT.

    publishAt setzt voraus, dass das Video beim Upload `private` ist; YouTube
    schaltet es dann selbst oeffentlich. Achtung: Projekte ohne API-Audit
    duerfen zwar hochladen, das Video bleibt aber dauerhaft privat — in dem
    Fall meldet `check` spaeter weiter `private` statt `geplant`."""
    import datetime
    from googleapiclient.http import MediaFileUpload
    f = _find(a.base)
    if not f["meta"].exists():
        sys.exit(f"{f['meta'].name} fehlt — ohne Titel/Beschreibung kein Upload.")
    lines = f["meta"].read_text().splitlines()
    title = lines[0].replace("TITEL:", "").strip()
    desc = "\n".join(lines[1:]).strip()
    tags = [w.lstrip("#") for w in desc.split() if w.startswith("#")]

    # Ortszeit → UTC. Europe/Zurich ist im September UTC+2.
    local = datetime.datetime.strptime(a.at, "%Y-%m-%d %H:%M")
    tz = datetime.timezone(datetime.timedelta(hours=2))
    publish_at = local.replace(tzinfo=tz).astimezone(datetime.timezone.utc)

    yt = api()
    body = {"snippet": {"title": title[:100], "description": desc,
                        "tags": tags[:20], "categoryId": "17",   # 17 = Sport
                        # Ohne diese zwei Felder raet YouTube die Sprache — und riet
                        # bei 15 Videos auf en-US. Dann gilt die de-CH-Spur als
                        # Uebersetzung aus dem Englischen statt als Originalton.
                        "defaultLanguage": "de-CH",
                        "defaultAudioLanguage": "de-CH"},
            "status": {"privacyStatus": "private",
                       "publishAt": publish_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "selfDeclaredMadeForKids": False}}
    print(f"↑ {f['mp4'].name}  ({f['mp4'].stat().st_size/1e6:.1f} MB)")
    print(f"  Titel   : {title}")
    print(f"  geplant : {a.at} Ortszeit  ({body['status']['publishAt']} UTC)")
    if a.dry_run:
        print(f"  Tags    : {len(tags)}   SRT: {'ja' if f['srt'].exists() else 'NEIN'}"
              f"   Cover: {'ja' if f['cover'].exists() else 'NEIN'}")
        print("\n[DRY-RUN] nichts hochgeladen (mit --write ausfuehren)")
        return
    r = yt.videos().insert(part="snippet,status", body=body,
                           media_body=MediaFileUpload(str(f["mp4"]), chunksize=-1,
                                                      resumable=True)).execute()
    vid = r["id"]
    print(f"  ✅ hochgeladen: {vid}")
    set_thumbnail(yt, vid, f["cover"])
    set_captions(yt, vid, f["srt"])
    st = yt.videos().list(part="status", id=vid).execute()["items"][0]["status"]
    if st.get("publishAt"):
        print(f"  ✅ geplant fuer {st['publishAt'][:16]} UTC")
    else:
        print(f"  ⚠️ KEIN publishAt gesetzt — Status {st.get('privacyStatus')}. "
              f"Vermutlich fehlt dem Projekt das API-Audit; dann bleibt das Video privat.")
    print(f"  https://youtube.com/shorts/{vid}")


def _meta_body(f, at):
    """Titel/Beschreibung/Tags aus _youtube.txt + Publish-Zeit in Ortszeit."""
    import datetime
    if not f["meta"].exists():
        sys.exit(f"{f['meta'].name} fehlt — ohne Titel/Beschreibung kein Sinn.")
    lines = f["meta"].read_text().splitlines()
    title = lines[0].replace("TITEL:", "").strip()
    desc = "\n".join(lines[1:]).strip()
    tags = [w.lstrip("#") for w in desc.split() if w.startswith("#")]
    tz = datetime.timezone(datetime.timedelta(hours=2))      # Europe/Zurich, Sommerzeit
    pub = datetime.datetime.strptime(at, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    return title, desc, tags, pub.astimezone(datetime.timezone.utc)


def cmd_meta(a):
    """Ein von Hand hochgeladenes Video fertig einrichten: Titel, Beschreibung,
    Tags, Thumbnail, Untertitel, Publish-Zeit.

    Das ist die sparsame Variante — videos.insert kostet 1600 Einheiten,
    videos.update nur 50. Wer die Datei selbst hochlaedt, kommt so mit rund
    500 statt 2050 Einheiten pro Video aus."""
    yt = api()
    f = _find(a.base)
    title, desc, tags, pub = _meta_body(f, a.at)
    print(f"{a.video_id}  ←  {a.base}")
    print(f"  Titel   : {title}")
    print(f"  geplant : {a.at} Ortszeit  ({pub:%Y-%m-%dT%H:%M:%SZ} UTC)")
    if a.dry_run:
        print(f"  Tags    : {len(tags)}   SRT: {'ja' if f['srt'].exists() else 'NEIN'}"
              f"   Cover: {'ja' if Path(f['cover']).exists() else 'NEIN'}")
        print("\n[DRY-RUN] nichts geaendert (mit --write ausfuehren)")
        return
    yt.videos().update(part="snippet,status", body={
        "id": a.video_id,
        "snippet": {"title": title[:100], "description": desc,
                    "tags": tags[:20], "categoryId": "17",
                    "defaultLanguage": "de-CH",
                    "defaultAudioLanguage": "de-CH"},
        "status": {"privacyStatus": "private",
                   "publishAt": pub.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "selfDeclaredMadeForKids": False}}).execute()
    print("  ✅ Titel, Beschreibung, Tags und Publish-Zeit gesetzt")
    set_thumbnail(yt, a.video_id, f["cover"])
    set_captions(yt, a.video_id, f["srt"])


PLAYLIST_MAP = HERE / "content" / "youtube-playlists.json"


def cmd_recaption(a):
    """Bestehende de-CH-Spur durch eine gleichwertige unter "de" ersetzen.

    Grund siehe set_captions(): unter de-CH liegt unsere Spur NEBEN YouTubes
    Maschinenuntertiteln statt an ihrer Stelle, und der Player nimmt dann die
    Maschinenfassung.

    `base` ist optional. Fehlt die lokale SRT (Tom archiviert fertige Reels aus
    Dropbox weg), wird die vorhandene Spur von YouTube heruntergeladen und
    unveraendert wieder hochgeladen — dasselbe Ergebnis, nur 200 Einheiten teurer.

    Kosten: mit lokaler SRT 450, mit Download 650."""
    yt = api()
    srt = None
    if a.base:
        f = _find(a.base)
        if f["srt"].exists():
            srt = f["srt"]
        else:
            print(f"  ℹ️ keine lokale SRT fuer {a.base} — hole sie von YouTube")
    cs = yt.captions().list(part="snippet", videoId=a.video_id).execute()
    eigene = [c for c in cs.get("items", [])
              if (c["snippet"].get("trackKind") or "").lower() != "asr"]
    print(f"{a.video_id}" + (f"  ←  {a.base}" if a.base else ""))
    if not eigene:
        print("  ⚠️ keine eigene Spur vorhanden — nichts umzustellen"); return
    for c in eigene:
        print(f"  vorhanden: {c['snippet']['language']} "
              f"({c['snippet'].get('name') or 'ohne Namen'})")
    if all(c["snippet"]["language"] == "de" for c in eigene) and len(eigene) == 1:
        print("  ✓ liegt schon unter 'de' — nichts zu tun"); return
    if a.dry_run:
        quelle = "lokale SRT" if srt else "Download von YouTube"
        print(f"  [DRY-RUN] wuerde loeschen und als 'de' neu hochladen ({quelle})")
        return

    tmp = None
    if srt is None:
        roh = yt.captions().download(id=eigene[0]["id"], tfmt="srt").execute()
        tmp = Path("reels_work") / f"_recaption_{a.video_id}.srt"
        tmp.parent.mkdir(exist_ok=True)
        tmp.write_bytes(roh)
        srt = tmp
        print(f"  ⬇️ Spur geladen ({len(roh)} Bytes)")

    # ⚠️ ERST hochladen, DANN loeschen. Andersherum steht das Video ohne eigene
    # Spur da, wenn der Upload scheitert — am 18.09.2026 genau so passiert, als
    # mitten im Stapel das Quota ausging (wK_sPV_R8ww, 1265 Aufrufe).
    # "de" und "de-CH" sind fuer YouTube verschiedene Sprachen, die neue Spur
    # kollidiert also nicht mit der alten.
    if not set_captions(yt, a.video_id, srt):
        print("  ⛔ Upload fehlgeschlagen — alte Spur bleibt unangetastet")
        if tmp:
            print(f"     heruntergeladene SRT behalten: {tmp}")
        return
    for c in eigene:
        yt.captions().delete(id=c["id"]).execute()
        print(f"  🗑️ {c['snippet']['language']} geloescht")
    if tmp:
        tmp.unlink(missing_ok=True)


def cmd_audit(a):
    """Jedes Video des Kanals gegen die Regeln pruefen, die schon einmal schiefgingen:
    Roh-Titel stehengeblieben, leere Beschreibung, en-US statt de-CH, fehlende
    Publish-Zeit, fehlendes Cover, fehlende hochgeladene Untertitelspur.

    Billig: videos.list kostet 1 Einheit je 50 Videos. Die Untertitelpruefung
    (`--captions`) kostet 50 pro Video — nur bei Bedarf."""
    yt = api()
    ids = all_video_ids(yt)
    roh = re.compile(r"^\d{4}[ -]\d{2}[ -]\d{2}[ _]")
    befunde = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="snippet,status,contentDetails",
                             id=",".join(ids[i:i+50])).execute()
        for it in r["items"]:
            sn, st = it["snippet"], it["status"]
            p = []
            if roh.match(sn["title"]):                      p.append("Roh-Titel")
            if len(sn.get("description") or "") < 40:       p.append("Beschreibung fehlt")
            if sn.get("defaultAudioLanguage") != "de-CH":
                p.append(f"Audiosprache {sn.get('defaultAudioLanguage') or '(keine)'}")
            if sn.get("defaultLanguage") != "de-CH":
                p.append(f"Sprache {sn.get('defaultLanguage') or '(keine)'}")
            th = sn.get("thumbnails", {})
            if not ("maxres" in th or "standard" in th):    p.append("kein eigenes Cover")
            if st.get("privacyStatus") == "private" and not st.get("publishAt"):
                p.append("privat ohne Publish-Zeit")
            if a.captions:
                cs = yt.captions().list(part="snippet", videoId=it["id"]).execute()
                eigene = [c["snippet"].get("language")
                          for c in cs.get("items", [])
                          if c["snippet"].get("trackKind") == "standard"]
                if not eigene:
                    p.append("keine hochgeladene Untertitelspur")
                elif "de" not in eigene:
                    # de-CH liegt NEBEN der Maschinenspur statt an ihrer Stelle
                    p.append(f"Untertitel als {'/'.join(eigene)} statt de → recaption")
            if p:
                befunde.append((it["id"], sn["title"][:44], p))
    print(f"{len(ids)} Videos geprueft — {len(befunde)} mit Befund\n")
    for v, tl, p in befunde:
        print(f"  {v}  {tl:46} {' · '.join(p)}")
    if not befunde:
        print("  Alles in Ordnung.")
        return
    recap = [v for v, _, p in befunde if any("recaption" in x for x in p)]
    if recap:
        print(f"\n{len(recap)} Video(s) brauchen recaption — je 450 Einheiten,"
              f" Tagesbudget 10'000:\n")
        for v in recap:
            print(f"  ./yt_api.py recaption {v} --write")


def cmd_playlist(a):
    """Videos gemaess content/youtube-playlists.json einsortieren.

    Idempotent: was schon drin ist, wird uebersprungen. Gedacht zum Nachholen,
    wenn das Tageskontingent mitten in einem Lauf ausgeht — einfach nochmal
    starten. playlistItems.insert kostet 50 Einheiten pro Video."""
    cfg = json.loads(PLAYLIST_MAP.read_text())
    namen, zuordnung = cfg["playlists"], cfg["zuordnung"]
    yt = api()
    drin = {}
    for pid in set(zuordnung.values()):
        page = None
        while True:
            r = yt.playlistItems().list(part="contentDetails", playlistId=pid,
                                        maxResults=50, pageToken=page).execute()
            for it in r["items"]:
                drin.setdefault(it["contentDetails"]["videoId"], set()).add(pid)
            page = r.get("nextPageToken")
            if not page:
                break
    offen = [(v, p) for v, p in zuordnung.items() if p not in drin.get(v, set())]
    if not offen:
        print("Alles eingeordnet — nichts zu tun.")
        return
    print(f"{len(offen)} Video(s) einzuordnen" + ("" if not a.dry_run else "   [DRY-RUN]"))
    for vid, pid in offen:
        if a.dry_run:
            print(f"  {namen.get(pid, pid):26} ← {vid}")
            continue
        try:
            yt.playlistItems().insert(part="snippet", body={"snippet": {
                "playlistId": pid,
                "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
            print(f"  ✅ {namen.get(pid, pid):26} ← {vid}")
        except Exception as e:
            if "exceeded your" in str(e):
                print(f"  ⛔ Tageskontingent erschoepft — Rest morgen nach 09:00 nachholen.")
                return
            print(f"  ⚠️ {vid}: {str(e)[:80]}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("auth")
    p.add_argument("--captions", action="store_true",
                   help="zusaetzlich den Scope fuer captions.list anfordern (Schreib-Scope)")
    p.set_defaults(fn=cmd_auth)
    p = sub.add_parser("list"); p.add_argument("--all", action="store_true"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("check"); p.add_argument("video_id"); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("analytics"); p.add_argument("--days", type=int, default=14); p.set_defaults(fn=cmd_analytics)
    p = sub.add_parser("upload")
    p.add_argument("base", help="Basisname des Reels, z. B. 2026-09-09_b2w_kamera-iphone")
    p.add_argument("--at", required=True, help="Publish-Zeit Ortszeit, 'YYYY-MM-DD HH:MM'")
    p.add_argument("--write", dest="dry_run", action="store_false", default=True)
    p.set_defaults(fn=cmd_upload)
    p = sub.add_parser("fix")
    p.add_argument("video_id"); p.add_argument("base")
    p.set_defaults(fn=cmd_fix)
    p = sub.add_parser("meta")
    p.add_argument("video_id"); p.add_argument("base")
    p.add_argument("--at", required=True, help="Publish-Zeit Ortszeit, 'YYYY-MM-DD HH:MM'")
    p.add_argument("--write", dest="dry_run", action="store_false", default=True)
    p.set_defaults(fn=cmd_meta)
    p = sub.add_parser("recaption")
    p.add_argument("video_id"); p.add_argument("base", nargs="?", default=None)
    p.add_argument("--write", dest="dry_run", action="store_false", default=True)
    p.set_defaults(fn=cmd_recaption)
    p = sub.add_parser("audit")
    p.add_argument("--captions", action="store_true",
                   help="auch die Untertitelspuren pruefen (50 Einheiten pro Video)")
    p.set_defaults(fn=cmd_audit)
    p = sub.add_parser("playlist")
    p.add_argument("--write", dest="dry_run", action="store_false", default=True)
    p.set_defaults(fn=cmd_playlist)
    p = sub.add_parser("sources"); p.add_argument("--days", type=int, default=14)
    p.add_argument("--video", help="nur dieses Video statt des ganzen Kanals")
    p.set_defaults(fn=cmd_sources)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
