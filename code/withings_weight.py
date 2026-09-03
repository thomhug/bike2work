#!/usr/bin/env python3
"""Withings-Gewichtsdaten (meastype=1) für die Sport-Analysen.

Eigene Token-Kette für diese lokale Umgebung (unabhängig vom Server-Scraper).
Tokens in .withings_tokens.json (gitignored), client_id/secret aus .env.

Befehle:
  ./withings_weight.py auth-url            # OAuth-URL zum Autorisieren ausgeben
  ./withings_weight.py exchange <code>     # code aus dem Redirect gegen Tokens tauschen
  ./withings_weight.py weight [--start YYYY-MM-DD] [--end YYYY-MM-DD]
  ./withings_weight.py weight --json       # maschinenlesbar (fürs Analyse-Skript)
"""
import os, re, sys, json, time, socket, argparse
import urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, ".env")
STORE = os.path.join(HERE, "weights.json")

# Jede Maschine hat ihre eigene Withings-App (client_id) + eigene Token-Datei.
# So killen sich Mac und Linux nicht gegenseitig die Tokens (Withings-Refresh
# rotiert und macht die Kette der anderen App NICHT ungültig).
HOSTKEY = re.sub(r"\W", "_", socket.gethostname().split(".")[0])
TOKENS = os.path.join(HERE, f".withings_tokens_{HOSTKEY}.json")
REDIRECT_URI = "https://tom.li/withings"
SCOPE = "user.metrics"
AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
MEAS_URL = "https://wbsapi.withings.net/measure"


def env_opt(key):
    with open(ENV) as f:
        for line in f:
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return None


def env(key):
    v = env_opt(key)
    if v is None:
        sys.exit(f"{key} fehlt in {ENV}")
    return v


def creds():
    """client_id/secret der zu DIESER Maschine gehörenden Withings-App."""
    cid = env_opt(f"WITHINGS_CLIENT_ID_{HOSTKEY}")
    sec = env_opt(f"WITHINGS_CLIENT_SECRET_{HOSTKEY}")
    if not cid or not sec:
        sys.exit(f"Keine Withings-App für Host '{HOSTKEY}' in {ENV}.\n"
                 f"→ Eigene App auf developer.withings.com anlegen und ergänzen:\n"
                 f"   WITHINGS_CLIENT_ID_{HOSTKEY}=<client id>\n"
                 f"   WITHINGS_CLIENT_SECRET_{HOSTKEY}=<secret>")
    return cid, sec


def post(url, data):
    body = urllib.parse.urlencode(data).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=30) as r:
        return json.load(r)


def save_tokens(body):
    body["_expires_at"] = int(time.time()) + int(body.get("expires_in", 10800)) - 60
    with open(TOKENS, "w") as f:
        json.dump(body, f, indent=2)
    os.chmod(TOKENS, 0o600)


def load_tokens():
    if not os.path.exists(TOKENS):
        sys.exit("Keine .withings_tokens.json — erst 'auth-url' + 'exchange <code>' ausführen.")
    return json.load(open(TOKENS))


def cmd_auth_url():
    cid, _ = creds()
    params = urllib.parse.urlencode({
        "response_type": "code", "client_id": cid, "scope": SCOPE,
        "redirect_uri": REDIRECT_URI, "state": "sportcal"})
    print("\n1) Öffne diese URL im Browser und autorisiere:\n")
    print(f"{AUTH_URL}?{params}\n")
    print("2) Nach 'Allow' wirst du zu https://tom.li/withings?code=XXXX&state=sportcal")
    print("   umgeleitet. Kopiere den 'code'-Wert und führe aus:")
    print("   ./withings_weight.py exchange <code>\n")


def cmd_exchange(code):
    cid, sec = creds()
    r = post(TOKEN_URL, {"action": "requesttoken", "grant_type": "authorization_code",
                         "client_id": cid, "client_secret": sec,
                         "code": code, "redirect_uri": REDIRECT_URI})
    if r.get("status") != 0:
        sys.exit(f"Fehler beim Token-Tausch: {r}")
    save_tokens(r["body"])
    print(f"✓ Tokens gespeichert in {os.path.basename(TOKENS)}")


def get_access_token():
    t = load_tokens()
    if t.get("_expires_at", 0) > time.time():
        return t["access_token"]
    # refresh (rotiert die eigene Kette — unabhängig vom Scraper)
    cid, sec = creds()
    r = post(TOKEN_URL, {"action": "requesttoken", "grant_type": "refresh_token",
                         "client_id": cid, "client_secret": sec,
                         "refresh_token": t["refresh_token"]})
    if r.get("status") != 0:
        sys.exit(f"Refresh fehlgeschlagen ({r.get('status')}). Neu autorisieren via 'auth-url'.")
    save_tokens(r["body"])
    return r["body"]["access_token"]


def fetch_weights(start_ts, end_ts):
    tok = get_access_token()
    params = urllib.parse.urlencode({
        "action": "getmeas", "meastype": 1, "category": 1,
        "startdate": start_ts, "enddate": end_ts})
    req = urllib.request.Request(f"{MEAS_URL}?{params}")
    req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if data.get("status") != 0:
        sys.exit(f"getmeas-Fehler: {data}")
    out = []
    for g in data["body"]["measuregrps"]:
        for m in g["measures"]:
            if m["type"] == 1:
                kg = m["value"] * (10 ** m["unit"])
                out.append((g["date"], round(kg, 2)))
    return sorted(out)


def cmd_weight(args):
    end = datetime.now(timezone.utc) if not args.end else \
        datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start = end - timedelta(days=30) if not args.start else \
        datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    rows = fetch_weights(int(start.timestamp()), int(end.timestamp()))
    if args.json:
        print(json.dumps([{"date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
                           "kg": kg} for ts, kg in rows]))
        return
    for ts, kg in rows:
        print(f"{datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')}  {kg:.2f} kg")


def cmd_store(args):
    """Letzte N Tage holen und in weights.json mergen (ein Morgen-Wert pro Tag)."""
    days = args.days or 35
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    rows = fetch_weights(int(start.timestamp()), int(end.timestamp()))  # sortiert aufsteigend
    day_kg = {}
    for ts, kg in rows:                       # erster (= frühester) Wert pro Tag = Morgen-Wert
        d = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        day_kg.setdefault(d, kg)
    store = json.load(open(STORE)) if os.path.exists(STORE) else {}
    before = len(store)
    store.update(day_kg)
    store = dict(sorted(store.items()))
    with open(STORE, "w") as f:
        json.dump(store, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"weights.json: {len(store)} Tage total (+{len(store)-before} neu, "
          f"{len(day_kg)} im {days}d-Fenster).")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth-url")
    ex = sub.add_parser("exchange"); ex.add_argument("code")
    wt = sub.add_parser("weight")
    wt.add_argument("--start"); wt.add_argument("--end"); wt.add_argument("--json", action="store_true")
    st = sub.add_parser("store"); st.add_argument("--days", type=int)
    a = ap.parse_args()
    if a.cmd == "auth-url": cmd_auth_url()
    elif a.cmd == "exchange": cmd_exchange(a.code)
    elif a.cmd == "weight": cmd_weight(a)
    elif a.cmd == "store": cmd_store(a)


if __name__ == "__main__":
    main()
