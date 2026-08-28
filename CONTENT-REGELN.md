# Quellenregel für alle Inhalte

**Nur schreiben, was belegt ist.** Drei zulässige Quellen:

1. **Gesprochen** — aus einem Video-Transkript
2. **Gemessen** — aus den Fahrdaten, der Waage oder einer Berechnung darauf
3. **Notiert** — aus Toms Strava-Beschreibungen und Fahrtnamen

Alles andere gehört nicht auf die Seite. Kein „das kennt man ja", kein
plausibles Ausschmücken, keine Faustregeln aus dem Allgemeinwissen.

## Warum die Regel existiert

Die erste Fassung der Kleider-Seite enthielt frei erfundene Behauptungen:
„man muss in den ersten zehn Minuten frieren", „alles andere bleibt im Büro".
Beides klang plausibel und war nirgends belegt. Ausserdem stand dort **−3,9 °C**
als kälteste Fahrt — dieser Wert stammte aus einem einzelnen Fahrtnamen, während
die Daten **−13,5 °C** hergeben.

Der Schaden ist grösser als der Nutzen: Die ganze Seite lebt davon, dass Zahlen
stimmen. Eine erfundene Nebensächlichkeit stellt auch die belegten Aussagen
in Frage.

## Praktisch

Vor jeder inhaltlichen Aussage prüfen:

```bash
# Strava-Beschreibungen durchsuchen
grep -h description activities/cycling/*/*/*.json

# Messwerte pruefen (Beispiel Temperatur)
python3 -c "import json,glob; ..."
```

Wo eine Angabe aus einer Notiz stammt, **gehört das Datum dazu** — dann ist sie
für Leser nachprüfbar und für mich später wiederauffindbar.
