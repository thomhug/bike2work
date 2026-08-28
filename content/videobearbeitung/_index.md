---
title: "Videobearbeitung"
weight: 50
summary: "Von der Handyaufnahme zum fertigen Reel: Schweizerdeutsch transkribieren, Untertitel einbrennen, Live-Daten einblenden — und die Fallstricke, die dabei Stunden gekostet haben."
---

Unterwegs entstehen kurze Clips auf dem Handy, gesprochen auf Schweizerdeutsch.
Daraus wird automatisch ein fertiges Reel: 9:16, Untertitel auf Hochdeutsch
eingebrannt, Hook im ersten Frame, Cover fürs Grid, Bildtext mit den Fahrdaten.

Der Code dazu liegt offen:
[github.com/thomhug/bike2work](https://github.com/thomhug/bike2work)

```
Clip finden ─▶ Fahrt zuordnen ─▶ transkribieren ─▶ Zahlen korrigieren
            ─▶ Untertitel einbrennen ─▶ Hook + Cover ─▶ Caption
```

## Womit

Alles Open Source, alles lokal auf dem eigenen Rechner — kein Cloud-Dienst, keine
laufenden Kosten.

| Werkzeug | wofür |
|---|---|
| **[FFmpeg](https://ffmpeg.org/)** 7.1 | das Arbeitspferd: Zuschnitt auf 9:16, Untertitel einbrennen, Hook und Overlay zeichnen, Farbraum wandeln, encodieren |
| **FFprobe** | Metadaten lesen — Aufnahmezeit, GPS, Rotation, Farbraum, Dauer |
| **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** 1.2 | Transkription, auf Basis von **[CTranslate2](https://github.com/OpenNMT/CTranslate2)** |
| **[Whisper large-v3-turbo](https://huggingface.co/jayr23/whisper-large-v3-turbo-swiss-german-ct2)**, auf Schweizerdeutsch feinabgestimmt | erkennt Dialekt und gibt direkt Hochdeutsch aus |
| **libass** (über FFmpegs `subtitles`-Filter) | Untertitel und Daten-Overlay im ASS-Format |
| **libx264** / **AAC** | Video- und Audio-Encoding |
| **zimg** (`zscale`) + `tonemap` | HDR nach BT.709 |
| **[Python](https://www.python.org/)** 3.13 | die Pipeline selbst — Standardbibliothek plus PyYAML |
| **[fitparse](https://github.com/dtcooper/python-fitparse)**, **[garminconnect](https://github.com/cyberjunky/python-garminconnect)** | Velo-Erkennung über Sensor-Seriennummern aus der Original-Aufzeichnung |
| **[Strava-API](https://developers.strava.com/)** | Fahrdaten, Sekunden-Streams und Segment-Höhenprofile |
| **DejaVu Sans** / **DejaVu Sans Mono** | Schrift für Untertitel und Overlay |

Die eingesetzten FFmpeg-Filter im Einzelnen: `scale`, `crop`, `overlay`, `gblur`
(unscharfer Hintergrund), `drawtext` (Hook und Cover-Titel), `subtitles`
(Untertitel und Overlay), `zscale` und `tonemap` (Farbraum), `setparams`
(Farb-Tags), `setsar`, `format`.

Ein 50-Sekunden-Clip braucht auf 20 CPU-Kernen rund 30 Sekunden für die
Transkription und knapp eine Minute fürs Rendern — ohne Grafikkarte.

## Schweizerdeutsch → Hochdeutsch

Whisper kann das erstaunlich gut, aber es lohnt sich, das richtige Modell zu
nehmen. Ein auf Schweizerdeutsch feinabgestimmtes Modell schlägt das Basismodell
bei gleicher Grösse und Geschwindigkeit deutlich:

| gesprochen | Basismodell | Fine-Tune |
|---|---|---|
| über die Helmkapuze | „Helm kaputzen" | **„Helmkapuze"** ✓ |
| mitten im Anstieg, keuchend | „schon 6 Minuten pro 10" | **„noch sechs Minuten von zehn"** ✓ |

Der zweite Fall ist der interessante: Bei Atemnot und Fahrtwind liefert das
Fine-Tune noch verwertbaren — und inhaltlich richtigen — Text.

Ein weiterer Unterschied zeigte sich bei einem Clip **ohne Sprache** (20 Sekunden
Wasserrauschen beim Velowaschen): Das Fine-Tune gab korrekt nichts zurück, das
Basismodell halluzinierte „Wir sehen uns beim nächsten Mal." Genau der Fehler, der
unbemerkt in einen Post rutscht.

**Zahlen verhauen beide Modelle zuverlässig** — und ausgerechnet die machen die
Videos glaubwürdig:

| erkannt | richtig | Quelle der Korrektur |
|---|---|---|
| „33 Watt" | 330 W | Fahrdaten |
| „Fight to work" | Bike to Work | Vokabular |
| „von Kamm auf Zürich" | von Cham nach Zürich | Ortskenntnis |
| „Zwei-Training" | Zone-2-Training | Kontext |

Deshalb die Arbeitsteilung: **Das Modell liefert die Wörter, die Fahrdaten liefern
die Zahlen.**

Ein Beispiel, wo Nachsehen besser war als Korrigieren: Im Video war von „17 Grad"
die Rede, während die Fahrt im Mittel 15,8 °C hatte. Naheliegend wäre gewesen, das
zu „korrigieren" — der Temperaturstream zeigte zum Zeitpunkt des Clips aber
tatsächlich 17 °C. Der Sensor kühlte von 21 °C (drinnen) langsam herunter.

## Live-Daten im Bild

Oben rechts laufen im Sekundentakt die Messwerte mit: **korrigierte Watt**, Puls,
Tempo und Steigung. Korrigiert heisst: Anzeige plus gemessener Geräteoffset, also
335 statt 314 Watt. Das kann kein Standard-Tool, weil dafür der Offset des
konkreten Messers bekannt sein muss.

Umgesetzt als zweiter Untertitel-Stil (ASS, `Alignment 9`) statt hunderter
`drawtext`-Filter — eine Filterstufe statt zweihundert.

### Zwei Fallstricke, die stundenlang kosteten

**Der Array-Index eines Aktivitäts-Streams ist nicht die Sekunde.** Die Testfahrt
hatte 3831 Datenpunkte über 3893 Sekunden — 63 Sekunden Lücken. Direkt indexiert
lag das Overlay 47 bis 63 Sekunden daneben, also 186 Meter Fahrstrecke. Aufgefallen
ist es nur, weil die GPS-Koordinate des Clips gegen die Position im Stream gehalten
wurde. Richtig ist der Umweg über den `time`-Stream; danach: 3 bis 29 Meter
Abweichung, das ist die GPS-Genauigkeit des Handys.

Diese Gegenprobe läuft seither bei jedem Overlay mit und warnt ab 60 Metern. Ein
falsch ausgerichtetes Overlay wäre sonst *unsichtbar* falsch — die Zahlen sähen
plausibel aus und kämen von woanders.

**Der Höhenstream einer Aktivität taugt nicht für Steigungen.** Er ist barometrisch
und auf kurzen Distanzen stark geglättet. An einer Stelle mit real 7,8 % lieferte
er:

| Fenster | Ergebnis |
|---|---:|
| 50 m | **0,8 %** |
| 200 m | 2,5 % |
| 600 m | 5,8 % |

Global stimmt der Stream (454 gegen 445 gemeldete Höhenmeter) — nur die
kurzfristige Ableitung ist unbrauchbar. Die Lösung: das **Höhenprofil des Segments**
verwenden, das aus dem Geländemodell stammt. Über ein 150-Meter-Fenster darauf
stimmt die Steigung mit der physikalisch aus Leistung, Tempo und Masse
zurückgerechneten auf 0,1 bis 0,5 Prozentpunkte überein.

## HDR: warum alles blass aussah

Das iPhone filmt in **HLG/BT.2020** (Dolby Vision). Das gerenderte Video behielt
diese Tags, sodass es auf dem eigenen Rechner richtig aussah — auf Instagram aber
sichtbar fahler als das Original. Die Plattform rekodiert und ignoriert dabei die
HDR-Kennzeichnung auf einem 8-Bit-Stream.

Die Lösung ist eine echte Tonwert-Abbildung nach BT.709, **vor** allen anderen
Filtern:

```
zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,
tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p
```

Zwei Details, die dabei aufhalten:

- **Die `-color_primaries`/`-color_trc`/`-colorspace`-Flags greifen bei
  `-filter_complex` nicht.** Die Datei behielt die HDR-Tags der Quelle, obwohl die
  Pixel längst BT.709 waren — ein Player hätte die Umwandlung ein zweites Mal
  angewendet.
- **`setparams` muss ans Ende der Filterkette.** Innerhalb der Tonemap-Stufe
  reicht es nicht, weil Overlay-, Untertitel- und `drawtext`-Filter die
  Farbeigenschaften nicht weitergeben.

Kontrolle: `ffprobe` muss `bt709/bt709/bt709` zeigen. Man sieht es dem Bild lokal
nicht an — die Prüfung ist der einzige verlässliche Weg.

## Kleinigkeiten mit Wirkung

**Untertitel-Position.** Sie sassen zunächst auf Kinnhöhe, weil `libass` ohne
Auflösungsangabe die Skalierung rät. Mit explizitem `PlayResX/Y` von 1080×1920
sind Schriftgrad und Rand echte Pixel. Ausserdem müssen sie hoch genug liegen, um
nicht in der Instagram-Bedienzone zu verschwinden.

**Umbruch an Satzgrenzen.** Zeilen, die auf „Es" oder „mit in die" enden, lesen
sich schlecht. Der Text wird deshalb zuerst in Sätze zerlegt und dann *innerhalb*
umgebrochen.

**Zweizeilige Hooks bündig setzen.** Jede Zeile ist ein eigener `drawtext` mit
eigener halbtransparenter Box. Ist der Zeilenabstand kleiner als die Boxhöhe,
überlappen sich die Kästen und der Überlappungsstreifen wird sichtbar dunkler. Die
Regel: Abstand = Schriftgrad + 2 × Randbreite.

**Querformat.** Hochkant gefilmte Clips füllen 9:16 von selbst. Querformat mit
unscharfem Hintergrund lässt nur etwa ein Drittel Bildhöhe übrig — ein
quadratischer Zuschnitt kommt auf rund 56 % und ist der bessere Kompromiss. Die
Erkennung liest die Rotation aus der **Display Matrix**; iPhone-Clips haben
mehrere Metadatenblöcke, und nur dieser enthält den Wert.

**Atomar schreiben.** Gerendert wird in eine temporäre Datei, erst am Ende wird
verschoben. Sonst liegt eine halbfertige Datei im synchronisierten Ordner — und
zwei gleichzeitige Läufe auf dasselbe Ziel vermischen sich.

---

*Alle Angaben stammen aus eigenen Fahrten, Messwerten oder veröffentlichten Studien — Belege sind verlinkt. Was sich nicht belegen liess, steht als solches gekennzeichnet da. [Quellenregel](https://github.com/thomhug/bike2work/blob/main/CONTENT-REGELN.md)*
