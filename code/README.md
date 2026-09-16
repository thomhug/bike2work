# Skripte

Die Werkzeuge hinter den Auswertungen und Reels auf
[velo.tom.li](https://velo.tom.li). Sie werden aus dem Arbeits-Repo hierher
**gespiegelt** — die Quelle der Wahrheit liegt dort, dieser Ordner ist die
veröffentlichte Kopie.

| Datei | Aufgabe |
|---|---|
| `reel.py` | Kern der Video-Pipeline: Clips einer Fahrt zuordnen, Schweizerdeutsch transkribieren, Untertitel + Hook + Cover rendern, Live-Messwerte einblenden |
| `strava_enrich.py` | b2w/b2h-Fahrten auf Strava benennen (Route, Intervalle, Regen), Velo per FIT-Fingerprint setzen, Beschreibung schreiben |
| `activity_report.py` | pro Fahrt eine Markdown-Zusammenfassung mit Kennzahlen (Watt, W/HF, Zonen, Gewicht, Bestzeit-Abgleich) |
| `bike_fingerprint.py` | erkennt aus den Sensor-Seriennummern einer FIT-Datei, welches Velo gefahren wurde |
| `albis_offset.py` | Powermeter-Offset SL vs. SLX am Albispass, physikbasiert aus Leistung, Zeit und Systemmasse |
| `video_backlog.py` | zeigt, welche Clips noch nicht gepostet sind |
| `withings_weight.py` | holt die Morgengewichte von Withings für die Analysen |
| `gear_overlay.py` | Di2-Gang (Blatt : Ritzel) und Trittfrequenz als Overlay — die Gangwahl steckt nur im Garmin-FIT |
| `drone_telemetry.py` | liest die DJI-Flugdaten aus dem Datenstrom im MP4 und blendet Tempo/Höhe ein |
| `yt_api.py` | YouTube Data API: Upload als `private` mit Publish-Zeit, Titel/Beschreibung/Tags/Untertitel/Playlist setzen, geplante Videos prüfen |
| `yt_stats.sh` | Aufrufe der öffentlichen Videos aus dem Kanal-RSS — ohne API-Key |
| `reel_times.py` | Post-Zeitpunkte aus den Plattform-IDs rekonstruieren (TikTok-ID, Instagram-Shortcode, YouTube-RSS) |
| `src/garmin_sync/` | Garmin-Login, Aktivitäts-Download, FIT-Parsing, Google-Sheet |
| `src/strava_sync/` | Strava-OAuth, Aktivitäts-Sync, Segment- und Split-Auswertung |

Wie diese Teile zusammenspielen, steht ausführlich unter
[velo.tom.li/videobearbeitung](https://velo.tom.li/videobearbeitung/) und
[/prozess](https://velo.tom.li/prozess/).

## Konfiguration

- `.env.example` — Vorlage für Zugangsdaten (Garmin, Strava). Die echten Werte
  stehen in `.env` und sind nie eingecheckt.
- `config.example.yaml` — Beispielkonfiguration (Sheet-ID, Ordnerpfade). Die
  echte `config.yaml` bleibt privat.

## Hinweis

Alles hier ist mit [Claude Code](https://claude.com/claude-code) entstanden. Die
Skripte lesen sämtliche Zugangsdaten aus der Umgebung bzw. `.env` — im Code
stehen keine Geheimnisse.
