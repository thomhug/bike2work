---
title: "Prozess"
weight: 60
summary: "Wie aus einer Fahrt ein ausgewerteter Datensatz, ein beschrifteter Strava-Eintrag und ein eingeplantes Reel auf drei Plattformen wird. Ich filme und prüfe, Claude macht den Rest."
---

**Stand November 2026: Ich filme, rede und prüfe. Alles andere macht Claude.**
Das reicht von der Auswertung der Fahrt über das fertige Reel bis zur
Einplanung auf YouTube, Instagram und TikTok. Danach sammelt Claude die Zahlen
ein und entwirft Antworten auf Kommentare. Was bei mir bleibt, steht weiter
unten unter [Was ich noch selbst mache](#was-ich-noch-selbst-mache).

## Von der Fahrt zum Reel

Der ganze Ablauf hängt an einem Wort: **„sync".** Danach läuft ohne Rückfragen
durch:

1. **Fahrten holen.** Strava-Aktivitäten als JSON ablegen, Gewicht von der Waage
   nachziehen, Kennzahlen in ein Tabellenblatt schreiben.
2. **Anreichern.** Fahrten mit generischem Namen („Fahrt am Morgen") bekommen
   einen richtigen Titel. Welches Velo es war, entscheidet nicht die Vermutung,
   sondern der Fingerabdruck aus der Aufzeichnung.
3. **Clips finden.** Alle Videos des Tages aus dem synchronisierten Ordner, über
   den Zeitstempel einer Fahrt zugeordnet.
4. **Transkribieren.** Jeden Clip, auch die ohne offensichtlichen Bezug.
5. **Texte schreiben.** Beschreibung und Caption aus Videoinhalt *und* Fahrdaten.
6. **Reel bauen.** Untertitel, Hook, Cover, YouTube-Titel. Gesichter und
   lesbare Autonummern werden verpixelt (siehe
   [Videobearbeitung](/videobearbeitung/#verpixeln-gesichter-und-autonummern)).
7. **Akkus prüfen.** Stand der Di2-Schaltung und des Powermeters aus der
   Aufzeichnung, mit Warnung, bevor etwas leer ist.

Aus *jedem* Clip vom Velo entsteht ein Reel, auch aus stummen. Dort schreibt
Claude die Untertitel selbst. Ein stummer Clip von 18 Sekunden über ein
Ventil war eine Zeit lang mein bestes Instagram-Video.

## Vom Reel zum Post

Fertige Reels durchlaufen vier Ordner:

| Ordner | heisst | wer schiebt |
|---|---|---|
| `neu` | frisch gerendert, wartet auf meine Prüfung | Claude |
| `ready` | geprüft, wartet auf einen Termin | ich |
| `planned` | eingeplant | Claude |
| `posted` | veröffentlicht | Claude |

Aus `ready` stellt Claude einen Postplan zusammen, meist zwei Termine pro Tag
(07:30 und 17:00, am Wochenende 10:00 und 17:00), und plant jedes Reel
**gleichzeitig auf allen drei Plattformen** ein:

- **YouTube** über die offizielle Schnittstelle: Video, Titel, Beschreibung,
  Untertitelspur und Veröffentlichungszeit. Nur das Cover eines Shorts lässt
  sich dort nicht setzen, das macht Claude im Browser in YouTube Studio.
- **Instagram und TikTok** über eine Browser-Erweiterung in meiner eigenen,
  angemeldeten Sitzung. Claude lädt das Video hoch, setzt Cover und Text und
  stellt Datum und Uhrzeit ein. Danach prüft es im Kalender, ob alles richtig
  steht.

Am 06.11.2026 lief das zum ersten Mal durch, mit neun Reels auf einen Schlag.
Seither läuft die Einplanung so.

## Nach dem Post

Auf das Stichwort **„stats"** holt Claude die Aufrufe, Likes und Kommentare
von allen drei Plattformen in eine Tabelle, inzwischen fast 500 Zeilen. Dort
steht pro Post die Uhrzeit, die Kategorie und die Reichweite. Daraus entsteht
der nächste Postplan: Welche Themen ziehen gerade, was läuft auf welcher
Plattform.

Kommentare werden seit dem 05.11.2026 gesichert, weil die Plattformen nur den
aktuellen Stand zeigen und Gelöschtes verschwindet. **Antworten entwirft
Claude, aber keine geht ohne mein Okay raus**, jede einzeln. Auf YouTube und
Instagram schickt Claude sie danach selbst ab, bei TikTok gibt es dafür keine
Schnittstelle.

Und diese Website: Auch die schreibt Claude, nach einer strengen
[Quellenregel](https://github.com/thomhug/bike2work/blob/main/CONTENT-REGELN.md).
Drauf kommt nur, was ich gesagt, notiert oder gemessen habe.

## Welches Velo war es? Der Fingerabdruck

Strava verrät es nicht: Das Feld `device_name` nennt den Velocomputer, und der
wandert zwischen den Velos. Der Standardwert im Profil ist zudem immer dasselbe
Velo — unbearbeitete Fahrten sind also systematisch falsch zugeordnet.

Die originale Aufzeichnung aus dem Velocomputer enthält dagegen pro gekoppeltem
Sensor Hersteller, Produkt und **Seriennummer**. Powermeter und elektronische
Schaltung unterscheiden sich zwischen den Velos — zwei unabhängige Fingerabdrücke,
die gegeneinander geprüft werden können.

## Wenn Zahlen im Video vorkommen

In den Clips stelle ich oft direkte Fragen: *„Claude, schau mal nach, wie es mit
dem Drift aussieht, und vergleich es mit der letzten Woche."* Solche Fragen gehören
in der Beschreibung beantwortet — mit echten Zahlen, nicht mit Floskeln.

Das setzt voraus, dass der Videoinhalt *vor* dem Schreiben bekannt ist. Deshalb
steht die Transkription im Ablauf vor dem Text, nicht danach.

## Warum Repo und Plattform auseinanderlaufen

Ein Problem, das zweimal von Hand repariert wurde, bevor es strukturell gelöst war:
Der Abgleich holt neue Fahrten, aktualisiert aber keine bestehenden. Alles, was
nachträglich auf der Plattform geändert wird — umbenennen, Velo zuweisen —, kommt
lokal nie an. Und weil der Standardwert immer dasselbe Velo ist, tragen
unbearbeitete Fahrten dauerhaft das falsche.

Aufgefallen ist es über eine einfache Regel: **An einem Tag kann nicht mit zwei
verschiedenen Velos gependelt werden.** Über 401 Tage fanden sich zwölf
Verdachtsfälle; zehn waren erklärbar (Kettenriss und Wechsel aufs Ersatzvelo, kurze
Abendrunden mit dem Mountainbike, die Testfahrt des neuen Velos). Zwei waren echte
Abweichungen — und die stellten sich als veraltete lokale Kopien heraus, nicht als
Fehler bei der Zuordnung.

Die Lehre: Wer in beide Richtungen schreibt, muss auch in beide Richtungen lesen.

## Was dokumentiert wird

Jeder Post bekommt eine Datei mit Status, Video-Pfad, Hook und dem fertigen Text.
Dazu ein Log über alle Clips — welcher verwendet wurde, welcher noch offen ist. Das
klingt bürokratisch, verhindert aber, dass gutes Material liegen bleibt: Von 18
erfassten Clips waren zeitweise sieben ungenutzt, darunter die inhaltlich stärksten.

## Was ich noch selbst mache

- **Filmen und reden.** Jeder Clip ist von mir, jede Aussage im Video auch.
- **Jedes Reel prüfen, bevor es eingeplant wird.** Das ist keine Formsache.
  Im November habe ich so einen falschen Ortsnamen gefunden: „Sihltal" für
  Clips, die zwischen Cham und Baar entstanden sind. Ein andermal stand
  „Nächste Velolichter" im Untertitel, wo ich „Nervige Velolichter" gesagt
  hatte.
- **Antworten auf Kommentare freigeben**, jede einzeln.
- **Bestehende Strava-Einträge ändern lassen.** Neue Fahrten beschriftet
  Claude selbst, alte fasst es nur mit meiner ausdrücklichen Erlaubnis an.
- **Bei Zahlen widersprechen, wenn sie sich falsch anfühlen.** Das passiert
  öfter, als man denkt, und mein Gefühl lag dabei mehrmals richtig, die erste
  Rechnung falsch.

## Grenzen

**Die Instagram-Schnittstelle kann veröffentlichen, aber nicht einplanen.**
Ein Video geht damit sofort live. Für einen festen Termin bräuchte es einen
Zeitschalter auf einem Rechner, und den wollte ich nicht. Darum der Weg über
den Browser.

**Die Browser-Steuerung braucht meinen Rechner.** Sie läuft in meiner Sitzung,
also nur, wenn der Rechner an ist. Und sie hängt an der Oberfläche der
Plattformen: Ändert sich dort etwas, muss der Ablauf angepasst werden. Ein
geplanter TikTok-Beitrag lässt sich zudem nicht mehr bearbeiten, er muss also
auf Anhieb stimmen.

**Strava schneidet Videos nach 30 Sekunden ab.** Der ausführliche Text passt
deshalb oft gar nicht zum dort sichtbaren Ausschnitt — die vollständigen Videos
laufen auf Instagram, die Zahlen stehen auf Strava.

---

*Alle Angaben stammen aus eigenen Fahrten, Messwerten oder veröffentlichten Studien — Belege sind verlinkt. Was sich nicht belegen liess, steht als solches gekennzeichnet da. [Quellenregel](https://github.com/thomhug/bike2work/blob/main/CONTENT-REGELN.md)*
