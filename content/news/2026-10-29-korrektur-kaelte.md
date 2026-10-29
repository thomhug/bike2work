---
title: "Korrektur: Oberhalb von 15 Grad kostet Kälte gar nichts"
date: 2026-10-29
---

Ein Zuschauer hat einen Fehler in meiner Kälte-Tabelle gefunden, und er hat recht.

Unter dem Video von heute Morgen schrieb **Zurigo**: *„von 15-30 Grad kann man im
gleichen Outfit fahren. Woher sollen dann die weiteren Leistungseinsparungen der
Kleidung herkommen?"*

Genau das ist der Punkt. Die Tabelle gab für jeden Temperaturschritt einen
Mehrbedarf an, von 0 bis 30 Grad, nach einer einzigen Geraden. Wenn der Effekt
aber von der Winterkleidung kommt, kann er oberhalb von 15 Grad nicht weiterlaufen
— dort trage ich ohnehin kurz/kurz.

Nachgerechnet, je Temperaturbereich getrennt:

| Datensatz | Fahrten | pro °C kälter | 95-%-Intervall |
|---|---:|---:|---|
| gleiches Outfit, 15–26 °C | 22 | −0.04 % | [−0.60, +0.52] |
| **unter 15 °C** | 48 | **+1.11 %** | [+0.69, +1.53] |
| 15 °C und wärmer | 16 | −0.52 % | [−1.47, +0.43] |

Nur die mittlere Zeile hält. Oberhalb von 15 Grad liegt die Null mitten im
Vertrauensintervall, und das auf beiden Velos.

Die Hauptaussage überlebt: **Bei 0 Grad kostet es 18 Prozent mehr Watt** für
dasselbe Tempo. Nur wandert der Bezugspunkt von 20 auf 15 Grad, und der warme Teil
der Tabelle verschwindet ersatzlos. Die −4 Prozent bei 25 Grad und −8 bei 30 waren
reine Extrapolation.

Mit korrigiert habe ich eine zweite Angabe, die zu selbstbewusst war: Die
„0.25 Prozent pro Grad aus der Luftdichte" sind eine theoretische Vorhersage, keine
Messung. Mein Datensatz gibt −0.28 ± 0.18 her, womit 0.25 verträglich ist — aber
null eben auch.

Die korrigierten Tabellen stehen auf [Kleider](/kleider/).

Was ich daraus mitnehme: Wenn die Erklärung für einen Effekt an einer Schwelle
hängt, darf das Modell keine durchgehende Gerade sein. Das hätte mir auffallen
müssen, bevor es jemand im Kommentar tut.
