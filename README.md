# Bike to Work mit Daten

Quellcode der Website [velo.tom.li](https://velo.tom.li/) — dokumentiert, wie aus
Velo-Videos und Fahrdaten fertige Reels und ausgewertete Fahrten entstehen.

Dreimal pro Woche 30 km pro Weg ins Büro, das ganze Jahr — dokumentiert mit
Powermeter, Waage und Physik statt Bauchgefühl.

## Was hier drin ist

- **Website** — Hugo mit [PaperMod](https://github.com/adityatelange/hugo-PaperMod),
  Inhalte als Markdown unter `content/`

Die Reel-Pipeline (Clips einer Fahrt zuordnen, Schweizerdeutsch nach Hochdeutsch
transkribieren, Untertitel einbrennen, Live-Messwerte einblenden, Cover erzeugen)
lebt in einem eigenen Repository und ist hier nicht enthalten.

## Lokal bauen

```bash
git clone https://github.com/thomhug/bike2work.git
cd bike2work
hugo server
```

## Deployment

Zweistufiger Docker-Build: Alpine baut die Seite mit Hugo, nginx liefert sie aus.

```bash
docker build -t bike2work .
docker run -p 8080:80 bike2work
```

## Hinweis

Alles hier — Analysen, Skripte, Texte und die Website — ist mit
[Claude Code](https://claude.com/claude-code) entstanden.

## Lizenz

MIT für den Code. Texte und Bilder © Thomas Hug.
