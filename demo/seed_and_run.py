#!/usr/bin/env python3
"""
Drive the REAL Nidra infra end to end. Targets the DEPLOYED DigitalOcean stack by
default; pass --local to hit a local backend.

  1. ingest browser-activity events  -> POST /connectors/browser_activity/ingest
  2. curate opinions (claude-code)    -> POST /opinions/refresh
  3. dream (claude-code)              -> POST /dreams/run
  4. read what got stored            -> GET  /dreams
  5. ask the chat API the question   -> POST /chat

The events below are genuine browsing signals (searches / reading / saves) for one
person planning a Tokyo trip. No preferences are stated outright -- the curation
has to induce them. Then the chat answers the itinerary question from the curated
user model, not from the raw events.

Usage:
  python3 demo/seed_and_run.py                 # all steps, against DO prod
  python3 demo/seed_and_run.py --chat          # just re-ask the chat (prod)
  python3 demo/seed_and_run.py --local         # against local backend (:APP_PORT)
  python3 demo/seed_and_run.py --ingest --opinions --dreams --chat   # pick steps

Token resolution (never hardcoded):
  prod : $NIDRA_TOKEN  ->  infra/k8s/secret.env  (API_AUTH_TOKEN)
  local: $NIDRA_TOKEN  ->  .env                  (API_AUTH_TOKEN)
Base override: $NIDRA_BASE. Stdlib only, 3.9-safe.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

PROD_BASE = "https://api.134-199-180-135.sslip.io"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

QUESTION = (
    "Plan my Tokyo trip - suggest an itinerary (where to stay, what to eat, and what "
    "to do) based on my preferences. Use what you know about me."
)

# set in main()
BASE = PROD_BASE
TOKEN = ""


def read_env_file(path):
    env = {}
    if not os.path.exists(path):
        return env
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def resolve_target(local):
    """Return (base, token) without ever hardcoding the secret."""
    if local:
        env = read_env_file(os.path.join(ROOT, ".env"))
        base = os.environ.get("NIDRA_BASE", "http://localhost:{}".format(env.get("APP_PORT", "8088")))
        token = os.environ.get("NIDRA_TOKEN") or env.get("API_AUTH_TOKEN", "")
    else:
        base = os.environ.get("NIDRA_BASE", PROD_BASE)
        token = os.environ.get("NIDRA_TOKEN")
        if not token:
            secret = read_env_file(os.path.join(ROOT, "infra", "k8s", "secret.env"))
            token = secret.get("API_AUTH_TOKEN", "")
    return base, token


def req(method, path, body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"content-type": "application/json", "authorization": "Bearer " + TOKEN},
    )
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}


# --------------------------------------------------------------------------- #
#  Genuine browsing signals (no stated preferences -- curation must induce).   #
# --------------------------------------------------------------------------- #
DAY = 86400_000


def _ts(days_ago, n=0):
    return int(time.time() * 1000) - days_ago * DAY + n * 60000


def search(i, q, days_ago):
    return {"id": "seed-s{}".format(i), "type": "search", "ts": _ts(days_ago, i),
            "domain": "google.com", "source": "search",
            "data": {"query": q}}


def reading(i, title, read_pct, dwell_min, days_ago, domain="medium.com"):
    return {"id": "seed-r{}".format(i), "type": "reading", "ts": _ts(days_ago, i),
            "domain": domain, "title": title, "source": "reading",
            "data": {"title": title}, "metrics": {"readPct": read_pct, "dwellMs": dwell_min * 60000}}


def choose(i, value, group, days_ago, domain="booking.com"):
    return {"id": "seed-c{}".format(i), "type": "interaction", "ts": _ts(days_ago, i),
            "domain": domain, "source": "interaction",
            "data": {"action": "choose", "value": value, "group": group}}


def action(i, milestone, funnel, days_ago, domain="united.com"):
    return {"id": "seed-a{}".format(i), "type": "action", "ts": _ts(days_ago, i),
            "domain": domain, "source": "action",
            "data": {"milestone": milestone, "funnel": funnel}}


EVENTS = [
    # --- food: ramen / coffee / omakase, local over touristy ---
    search(1, "best tonkotsu ramen tokyo", 21),
    search(2, "tokyo ramen worth the line", 12),
    search(3, "specialty coffee tokyo fuglen koffee mameya", 11),
    search(4, "casual omakase tokyo counter under 100", 9),
    reading(5, "Tokyo neighborhood izakayas - skip the tourist spots", 96, 6, 10, "timeout.com"),
    reading(6, "Fuglen Tokyo and the third-wave coffee scene", 92, 5, 8, "eater.com"),
    # --- activities: immersive / design / jazz / running, anti-checklist ---
    reading(7, "teamLab Planets vs Borderless - which is better", 90, 5, 14, "timeout.com"),
    search(8, "tokyo jazz bars local spots not blue note", 13),
    reading(9, "Daikanyama T-Site and the best Tokyo bookstores", 88, 4, 12, "spoon-tamago.com"),
    reading(10, "Top 10 Tokyo Tourist Attractions You Must See", 9, 0, 15, "tripadvisor.com"),  # bounced
    search(11, "running routes tokyo imperial palace loop", 7),
    # --- staying: boutique / walkable / minimalist + the Hakone signal ---
    search(12, "boutique design hotels tokyo walkable to station", 9),
    reading(13, "Top 10 Hakone Ryokans with Private Onsen", 72, 4, 18, "japan-guide.com"),
    choose(14, "Hakone Yumoto Onsen Ryokan", "ryokan-saved", 18),
    choose(15, "Hotel Metropolitan Tokyo, Marunouchi", "hotel-shortlist", 5),
    # --- logistics: Tokyo-based trip, Kyoto as a day trip ---
    action(16, "viewed flight to Tokyo HND depart Jul 14", "tokyo-trip", 22),
    search(17, "2 day tokyo itinerary first timer", 6),
    reading(18, "You can do Kyoto as a day trip from Tokyo (Shinkansen 2h15)", 80, 3, 5, "japan-guide.com"),
]


def step_ingest():
    print("\n[1/5] INGEST {} browsing events -> /connectors/browser_activity/ingest".format(len(EVENTS)))
    print("      ->", req("POST", "/connectors/browser_activity/ingest", {"events": EVENTS}))


def step_opinions():
    print("\n[2/5] CURATE opinions (claude-code: investigate -> cite -> review) -> /opinions/refresh")
    print("      (calls the model, ~30-120s)...")
    t = time.time()
    out = req("POST", "/opinions/refresh", {})
    print("      -> {}   ({:.0f}s)".format(out, time.time() - t))


def step_dreams():
    print("\n[3/5] DREAM across signals (claude-code) -> /dreams/run")
    print("      (~30-120s)...")
    t = time.time()
    out = req("POST", "/dreams/run", {})
    print("      -> {}   ({:.0f}s)".format(out, time.time() - t))


def step_show():
    print("\n[4/5] STORED dreams -> GET /dreams")
    out = req("GET", "/dreams")
    for d in out.get("dreams", []):
        print("      * [{}] {}  (conf {}, {})".format(d.get("kind"), d.get("hypothesis"),
              d.get("confidence"), "+".join(d.get("provenance") or [])))
    if not out.get("dreams"):
        print("      (none)")


def step_chat():
    print("\n[5/5] ASK the chat API (it reads the curated user model) -> /chat")
    print("      Q:", QUESTION)
    t = time.time()
    out = req("POST", "/chat", {"message": QUESTION})
    print("      ({:.0f}s)\n".format(time.time() - t))
    print("=" * 72)
    print(out.get("reply", out))
    print("=" * 72)


def main():
    global BASE, TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="target local backend instead of DO prod")
    ap.add_argument("--ingest", action="store_true")
    ap.add_argument("--opinions", action="store_true")
    ap.add_argument("--dreams", action="store_true")
    ap.add_argument("--chat", action="store_true")
    args = ap.parse_args()
    all_steps = not (args.ingest or args.opinions or args.dreams or args.chat)

    BASE, TOKEN = resolve_target(args.local)
    if not TOKEN:
        sys.exit("No API token (set $NIDRA_TOKEN, or fill infra/k8s/secret.env / .env)")
    masked = (TOKEN[:4] + "..." + TOKEN[-3:]) if len(TOKEN) > 8 else "set"
    print("Target: {}  (token {})".format(BASE, masked))

    try:
        if all_steps or args.ingest:
            step_ingest()
        if all_steps or args.opinions:
            step_opinions()
        if all_steps or args.dreams:
            step_dreams()
        if all_steps:
            step_show()
        if all_steps or args.chat:
            step_chat()
    except urllib.error.HTTPError as e:
        sys.exit("HTTP {}: {}".format(e.code, e.read().decode()[:500]))
    except urllib.error.URLError as e:
        sys.exit("Connection failed: {}".format(e))


if __name__ == "__main__":
    main()
