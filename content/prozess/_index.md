---
title: "Prozess"
weight: 60
summary: "Wie aus einer Fahrt ein ausgewerteter Datensatz, ein beschrifteter Strava-Eintrag und ein fertiges Reel wird — auf ein Stichwort."
---

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
6. **Reel bauen.** Untertitel, Hook, Cover — und ablegen.

## Welches Velo war es? Der Fingerabdruck

Strava verrät es nicht: Das Feld `device_name` nennt den Fahrradcomputer, und der
wandert zwischen den Velos. Der Standardwert im Profil ist zudem immer dasselbe
Velo — unbearbeitete Fahrten sind also systematisch falsch zugeordnet.

Die originale Aufzeichnung aus dem Fahrradcomputer enthält dagegen pro gekoppeltem
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

## Grenzen

**Das Posten läuft von Hand — obwohl es zwei Wege gäbe.**

Der offizielle: eine Business-Anbindung an die Plattform-API. Sie verlangt ein
Freigabeverfahren von mehreren Wochen, ein öffentlich erreichbares Video-Hosting
(die Plattform lädt nicht hoch, sie holt ab) und begrenzt Reels auf 90 Sekunden.

Der pragmatische: **Claude kann den Browser fernsteuern** und den Upload klicken.
Das funktioniert, ist aber umständlich — es läuft in der eigenen Sitzung mit
jemandem davor, bricht bei jeder Änderung an der Oberfläche, und native
Dateidialoge liegen ausserhalb der Seite und damit ausserhalb dessen, was eine
Browser-Automatisierung zuverlässig bedienen kann.

Bei ein bis zwei Posts pro Tag ist der manuelle Upload schlicht schneller als
beide Alternativen. Er dauert eine halbe Minute — die Datei liegt fertig da,
Caption und Cover ebenso.

**Strava schneidet Videos nach 30 Sekunden ab.** Der ausführliche Text passt
deshalb oft gar nicht zum dort sichtbaren Ausschnitt — die vollständigen Videos
laufen auf Instagram, die Zahlen stehen auf Strava.

---

*Alle Angaben stammen aus eigenen Fahrten, Messwerten oder veröffentlichten Studien — Belege sind verlinkt. Was sich nicht belegen liess, steht als solches gekennzeichnet da. [Quellenregel](https://github.com/thomhug/bike2work/blob/main/CONTENT-REGELN.md)*
