---
title: "Velos"
weight: 30
summary: "Zwei Rennvelos mit klaren Rollen, 24 Watt Messunterschied, und was Reifen und Ketten wirklich halten."
---

Zwei Canyon Ultimate: ein **SLX** für trockene Tage und ein **SL** mit
Schutzblechen für Nässe, Winter und Salz. Die Aufteilung hat einen praktischen
Grund — Streusalz bleibt dem Schönwetter-Velo erspart.

| | fahrfertig |
|---|---:|
| Ultimate CF SLX 8 Di2 | 7,80 kg |
| Ultimate CF SL 7 Di2 | 8,50 kg |
| … mit Schutzblechen | 8,80 kg |
| Kleidung kurz/kurz inkl. Helm, Schuhe, Minimalrucksack | 2,05 kg |

{{< figure src="/img/velo-slx.webp" alt="Canyon Ultimate CF SLX 8 Di2, schwarz, ohne Schutzbleche" caption="Das SLX — Schönwetter-Velo, 7,80 kg fahrfertig. Kein Salz, keine Schutzbleche." >}}

{{< figure src="/img/velo-sl.webp" alt="Canyon Ultimate CF SL 7 Di2, grau-schwarz, mit Schutzblechen" caption="Das SL mit Schutzblechen — 8,80 kg. Nässe, Winter, Salz. Die Bleche wiegen 300 Gramm und machen das Velo ganzjahresfähig." >}}

Keine Bidons, keine Halter — wegen Aero und Gewicht natürlich. 😉 Auf einer
Stunde Fahrweg braucht es sie schlicht nicht.

## Zwei Powermeter, 24 Watt Unterschied

Das ist der Befund, der am meisten überrascht hat. Dieselben Beine, dieselbe
Strecke, zwei Velos — und die Anzeigen liegen systematisch auseinander.

Nachrechnen geht über die Physik. Für einen Anstieg gilt:

```
P = (m·g·Δh/t  +  Crr·m·g·v  +  ½·ρ·CdA·v³) / Antriebswirkungsgrad
```

Alles darin ist bekannt oder messbar: Systemmasse aus Tagesgewicht plus Velo plus
Kleidung, Höhendifferenz und Distanz aus dem Segment, die Zeit aus der Fahrt.
Vergleicht man das Ergebnis mit der Anzeige, bleibt der Gerätefehler übrig.

| | Offset (Anzeige − Physik) | Fahrten |
|---|---:|---:|
| SL | **+3,7 W** | 79 |
| SLX | **−20,4 W** | 20 |

Das SL ist also praktisch geeicht, das SLX liest gut 20 Watt zu tief. **Wer die
zwei Anzeigen vergleicht, vergleicht Geräte, nicht Form.**

Eine Probe aufs Exempel, zwei Fahrten im Abstand einer Woche:

| Fahrt | Zeit | Anzeige | physikalisch | Puls |
|---|---|---:|---:|---:|
| [20.08.2026](https://www.strava.com/activities/19825461167) (SL) | 10:54 | 333 W | 323 W | 164,4 |
| [27.08.2026](https://www.strava.com/activities/19924734015) (SLX) | **10:33** | 314 W | **335 W** | 164,2 |

Die zweite Fahrt war 21 Sekunden schneller mit 13 Watt mehr echter Leistung — bei
identischem Puls, 0,9 kg mehr Körpergewicht und 3 °C mehr Hitze. Die Anzeige sagte
das Gegenteil.

## Temperaturdrift

Der SL-Messer hat zusätzlich eine Temperaturabhängigkeit: **rund −0,8 W/°C**. Bei
etwa 24–25 °C liest er korrekt, in der Kälte zu hoch (+11 W bei 10 °C), in der
Hitze zu tief. Ein zweiter Rechenweg über die flache Strecke ergab −1,05 W/°C —
gleiche Grössenordnung, unabhängig ermittelt.

Praktische Folge: vor Kälte- oder Hitzeextremen den Nullpunkt kalibrieren.

## Gewicht am Berg

Am Albis (7,8 % Steigung, ~15 km/h) gilt als Faustregel: **1 kg kostet 3,3 Watt.**

Wichtiger als das Velogewicht ist dabei das eigene. Über alle Fahrten schwankt die
Systemmasse um **4 kg** — und der Löwenanteil davon ist Körpergewicht, nicht
Material. Der Unterschied zwischen den beiden Velos (0,7 kg) verschwindet in der
Tagesschwankung. Jede Bergrechnung muss deshalb das Tagesgewicht verwenden, nie
einen Durchschnitt; sonst fällt der berechnete Geräteoffset um mehrere Watt falsch
aus.

## Verschleiss

Alle Wechsel erfolgten erst, als das Gewebe sichtbar war — nie vorsorglich. Die
Zahlen sind also echte Standzeiten, keine Wartungsintervalle.

### Reifen hinten (Schwalbe One TLE)

| bei km | Standzeit |
|---:|---:|
| 3'000 | 3'000 km (Erstbereifung) |
| 8'000 | **5'000 km** |
| 12'050 | **4'050 km** |

### Reifen vorne

Die Erstbereifung hielt **14'450 km** — ebenfalls bis aufs Gewebe. Das Verhältnis
vorne zu hinten liegt bei **3,6 : 1**, weil hinten Antrieb und rund 60 % des
Gewichts wirken. Praktische Folge: Ersatz lohnt sich nur hinten vorzuhalten.

### Kette

| bei km | Standzeit |
|---:|---:|
| 2'360 | 2'360 km |
| 4'860 | ~2'500 km |
| 8'000 | 3'140 km |
| 14'450 | **6'450 km** |

Der Sprung auf 6'450 km fällt mit dem Umstieg aufs **Wachsen** zusammen. Ein
einzelner Datenpunkt, aber ein auffälliger — Wachs bindet weniger Schmutz als Öl,
und Schmutz ist der Schleifstein im Antrieb.

## Was sich nicht belegen liess

Die Vermutung, Reifen hielten über den Winter länger, liess sich **nicht
bestätigen** — der länger haltende Reifen lief sogar im wärmeren Schnitt. Und sie
ist mit diesen Daten auch nicht prüfbar: Bei rund 4'000 km Standzeit dauert ein
Reifenleben etwa zwei Jahre und mittelt immer über alle Jahreszeiten.

---

*Alle Angaben stammen aus eigenen Fahrten, Messwerten oder veröffentlichten Studien — Belege sind verlinkt. Was sich nicht belegen liess, steht als solches gekennzeichnet da. [Quellenregel](https://github.com/thomhug/bike2work/blob/main/CONTENT-REGELN.md)*
