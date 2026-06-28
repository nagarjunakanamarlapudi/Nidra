#!/usr/bin/env python3
"""
Generate the two memory files for the demo:

  demo/raw_memory.md      <- the giant unprocessed log. Feed THIS to Claude Code.
  demo/curated_memory.md  <- what Nidra's learning loop distilled (~500 tokens).

The whole point: a real memory is enormous and 99.99% junk. Dumping it at a model
does not scale -- at 1,000,000 entries the raw log is ~18M tokens, far past any
context window, while Nidra's learned model stays ~500 tokens. The ~29 meaningful
Tokyo signals are scattered through the haystack so it's a fair test.

  python3 demo/gen_memory.py                 # 1,000,000 entries (~75MB, ~18M tokens)
  python3 demo/gen_memory.py --entries 12000 # ~180k tokens: fits Claude's window so
                                             #   it loads but drowns (returns a weak answer)

Stdlib only, 3.9-safe.
"""
import argparse
import os

# --------------------------------------------------------------------------- #
#  The ~29 meaningful signals (genuine browsing for a Tokyo trip). No stated   #
#  preferences -- curation must induce them. Buried in the junk below.         #
# --------------------------------------------------------------------------- #
TRIP = [
    ("browser",  "Jun 20 '26", "Searched: 'flights SFO to Tokyo'"),
    ("browser",  "Jun 20 '26", "Visited: united.com/booking - flight to Tokyo (HND), depart Jul 14"),
    ("calendar", "Jun 28 '26", "Event: 'Tokyo - on the ground' Jul 14-16 (2 days, Tokyo only)"),
    ("browser",  "Jun 21 '26", "Read article: 'Top 10 Hakone Ryokans with Private Onsen' (saved 3)"),
    ("browser",  "Jun 21 '26", "Saved: 'Hakone Yumoto Onsen Ryokan' (4.7 stars)"),
    ("browser",  "Jun 21 '26", "Saved: 'Gora Kadan, Hakone'"),
    ("browser",  "Jun 28 '26", "Read: 'You can do Kyoto as a day trip from Tokyo (Shinkansen 2h15)'"),
    ("calendar", "Jun 24 '26", "Declined: 'Standup' 8:30 AM (3rd morning decline this month)"),
    ("email",    "Jun 26 '26", "Sent: 'mornings are dead for me, anything before 2 is a no'"),
]
PREFS = [
    ("browser",  "May 12 '26", "Searched: 'best tonkotsu ramen tokyo'"),
    ("browser",  "Jun 05 '26", "Searched: 'tokyo ramen worth the line'"),
    ("browser",  "Jun 19 '26", "Searched: 'tonkotsu vs shoyu ramen'"),
    ("finance",  "Mar 20 '26", "Txn: 'Ichiran Ramen' $19 (last Tokyo trip)"),
    ("finance",  "Jun 16 '26", "Txn: 'Blue Bottle Coffee' $6.50 (near-daily)"),
    ("browser",  "Jun 10 '26", "Read: 'Tokyo neighborhood izakayas - skip the tourist spots'"),
    ("browser",  "Jun 11 '26", "Saved: 'casual omakase counters under $100, Tokyo'"),
    ("browser",  "Jun 12 '26", "Searched: 'specialty coffee tokyo fuglen koffee mameya'"),
    ("review",   "Apr 02 '26", "Reviews: 5* 'tiny ramen counter, no english menu, perfect' / 2* 'overpriced tourist sushi in Ginza'"),
    ("browser",  "Jun 09 '26", "Searched: 'boutique design hotels tokyo walkable to station'"),
    ("finance",  "Feb 14 '26", "Txn: 'Ace Hotel' $240 (design hotel, last trip)"),
    ("finance",  "Jun 19 '26", "Txn: 'Muji' $84 - minimalist travel goods"),
    ("browser",  "Jun 23 '26", "Visited: booking.com - 'Hotel Metropolitan Tokyo, Marunouchi' (by JR)"),
    ("browser",  "Jun 14 '26", "Read: 'teamLab Planets vs Borderless - which is better'"),
    ("browser",  "Jun 15 '26", "Searched: 'tokyo jazz bars - local spots not blue note'"),
    ("browser",  "Jun 16 '26", "Visited: 'Daikanyama T-Site / Tsutaya bookstore' guide"),
    ("browser",  "Jun 18 '26", "Bounced at 9%: 'Top 10 Tokyo Tourist Attractions You Must See'"),
    ("calendar", "Jun 14 '26", "Recurring: 'Run - Embarcadero loop' 6:00 PM (x12 this month)"),
    ("browser",  "Jun 22 '26", "Searched: 'running routes tokyo - imperial palace loop'"),
    ("browser",  "Jun 06 '26", "Searched: 'koffee mameya omotesando reservation'"),
]

# --------------------------------------------------------------------------- #
#  Junk pools - lots of variants; i-based numbers make variety effectively     #
#  unlimited so a million entries don't look copy-pasted.                      #
# --------------------------------------------------------------------------- #
SITES = ["news.ycombinator.com", "github.com/notifications", "reddit.com/r/programming", "stackoverflow.com",
         "x.com/home", "youtube.com/feed", "linear.app", "notion.so", "arxiv.org", "figma.com", "espn.com",
         "amazon.com/orders", "docs.google.com", "linkedin.com/feed", "weather.com", "maps.google.com",
         "open.spotify.com", "mail.google.com", "wikipedia.org", "medium.com", "substack.com", "twitch.tv"]
QUERIES = ["k8s ingress 502", "sourdough not rising", "noise cancelling headphones", "postgres index bloat",
           "standing desk reddit", "grpc vs rest", "wireguard setup", "tailwind dark mode", "asyncio gather error",
           "mac fan loud", "espresso grind size", "deload week", "vscode keybindings", "docker layer cache",
           "nextjs app router", "fold fitted sheet", "redis vs memcached", "macbook battery", "rust borrow checker",
           "terraform state lock", "keyboard switches", "boil an egg", "typescript satisfies", "ipad monitor",
           "github actions cache", "pytest fixtures", "lambda cold start", "css grid vs flexbox", "homebrew uninstall",
           "zsh vs fish", "airpods firmware", "rsync ssh", "tax deadline", "carry on backpack", "mortgage rates"]
ARTICLES = ["Why we rewrote it in Rust", "The case against microservices", "How DNS works", "A primer on Raft",
            "Postgres for the application developer", "The cost of abstraction", "Latency numbers every dev should know",
            "Designing data-intensive apps notes", "What is a vector database", "On call survival guide",
            "The pragmatic guide to logging", "Stop using JWT for sessions", "How to read a paper", "API design tips"]
MERCH = ["Whole Foods", "Uber", "Amazon", "Spotify", "Chipotle", "Trader Joe's", "Lyft", "Netflix", "Sweetgreen",
         "CVS", "PG&E", "Comcast", "Shell", "Costco", "Apple", "DoorDash", "Walgreens", "AT&T", "Peet's", "Target",
         "Safeway", "Starbucks", "BART", "Cloudflare", "Vercel", "GitHub", "OpenAI", "AWS", "Notion", "Figma"]
SUBJECTS = ["Standup notes", "PR review requested", "new comment on #", "Your statement is ready", "Slack digest",
            "Calendar: invitation", "Receipt", "Package delivered", "Security alert: new sign-in", "Team lunch?",
            "Invoice paid", "Subscription renews soon", "Weekly sync", "Verify your email", "Order shipped",
            "Newsletter", "Reminder: 1:1", "Password changed", "Monthly usage report", "Welcome!"]
BRANDS = ["Nike", "Samsung", "Booking.com", "Coursera", "Audible", "Squarespace", "Grammarly", "NordVPN"]
APPS = ["Slack", "Spotify", "Messages", "Maps", "Calendar", "VS Code", "Terminal", "Notes", "Photos", "Chrome"]
DAYS = []
for _yy, _mx in (("'23", 365), ("'24", 366), ("'25", 365), ("'26", 180)):
    for _d in range(_mx):
        DAYS.append("day{:03d} {}".format(_d % 365, _yy))


def junk(i):
    """One mundane, irrelevant signal, fully deterministic from i."""
    ts = DAYS[i % len(DAYS)]
    v = i % 12
    if v == 0:
        return ("browser", ts, "Visited: {}/p/{}".format(SITES[i % len(SITES)], i % 97))
    if v == 1:
        return ("browser", ts, "Searched: '{}'".format(QUERIES[i % len(QUERIES)]))
    if v == 2:
        return ("finance", ts, "Txn: '{}' ${}.{:02d}".format(MERCH[i % len(MERCH)], (i * 7) % 480 + 1, i % 100))
    if v == 3:
        return ("email", ts, "Received: '{} {}'".format(SUBJECTS[i % len(SUBJECTS)], i))
    if v == 4:
        return ("email", ts, "Sent: 're: {}'".format(SUBJECTS[(i // 3) % len(SUBJECTS)]))
    if v == 5:
        return ("browser", ts, "Read: '{}' ({}%)".format(ARTICLES[i % len(ARTICLES)], i % 100))
    if v == 6:
        return ("browser", ts, "Clicked ad: {} promo".format(BRANDS[i % len(BRANDS)]))
    if v == 7:
        return ("finance", ts, "Txn: '{}' ${}.{:02d}".format(MERCH[(i // 5) % len(MERCH)], (i * 3) % 90 + 1, i % 100))
    if v == 8:
        return ("app", ts, "Opened app: {}".format(APPS[i % len(APPS)]))
    if v == 9:
        return ("email", ts, "Received: '{} #{}'".format(BRANDS[i % len(BRANDS)], i))
    if v == 10:
        return ("browser", ts, "Visited: {}".format(SITES[(i // 2) % len(SITES)]))
    return ("social", ts, "Liked a post ({})".format(i))


def write_raw(path, target):
    signals = PREFS + TRIP
    step = max(1, target // (len(signals) + 1))
    sig_idx = 0
    written = i = 0
    with open(path, "w") as f:
        f.write("# Alex Chen - raw activity log\n\n")
        f.write("_Unprocessed signals: browser, email, payments, apps, social - years of it._\n")
        f.write("_The entire memory, flat: {} entries. The relevant ones ARE in here._\n\n".format(target))
        while written < target:
            if sig_idx < len(signals) and i >= (sig_idx + 1) * step:
                surface, ts, text = signals[sig_idx]
                sig_idx += 1
            else:
                surface, ts, text = junk(i)
            f.write("- [{} | {}] {}\n".format(ts, surface.upper(), text))
            written += 1
            i += 1
    return written, os.path.getsize(path)


CURATED = """# Alex Chen - Nidra user model (curated + validated)

_Not a summary. Every belief is grounded in real signals, carries provenance and
confidence, and is revised when new signals contradict it. Dreams are speculative
until reality corroborates them._

## Opinions (grounded beliefs)
- **food:local-ramen-omakase-coffee** = Tonkotsu ramen + casual omakase; specialty coffee daily; local spots over Michelin/tourist  · conf 0.90 · Browser+Finance+Reviews
- **stay:boutique-walkable-minimalist** = Mid-range boutique/design hotels, walkable, near transit; minimalist  · conf 0.86 · Browser+Finance
- **activities:immersive-not-touristy** = Digital art, design districts, bookstores, local jazz; daily runner; skips checklist tourism  · conf 0.84 · Browser+Calendar
- **schedule:no-mornings** = Won't start before ~2pm  · conf 0.92 · Calendar+Email
- **trip:tokyo-compact** = Tokyo Jul 14-16, 2 days, Tokyo-based, mid-range, walkable  · conf 0.84 · Calendar+Browser

## Dreams (foresight - confirmed by later activity)
- teamLab Planets over Borderless (matches local-authentic pattern) · CORROBORATED
- Hakone ryokans don't fit a 2-day Tokyo trip -> central Tokyo; Kyoto only as a day trip · CORROBORATED
"""


def est_tokens_from_bytes(n):
    return n // 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entries", type=int, default=1_000_000, help="raw log size (default 1,000,000)")
    args = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))

    raw_path = os.path.join(here, "raw_memory.md")
    n, size = write_raw(raw_path, args.entries)
    with open(os.path.join(here, "curated_memory.md"), "w") as f:
        f.write(CURATED)

    rt = est_tokens_from_bytes(size)
    ct = len(CURATED) // 4
    mb = size / 1_000_000
    print("\n  Generated:")
    print("    demo/raw_memory.md      {:,} entries  {:.0f}MB  ~{:,} tokens".format(n, mb, rt))
    print("    demo/curated_memory.md             ~{:,} tokens".format(ct))
    print("    -> raw is ~{:,}x bigger than the learned model".format(rt // max(ct, 1)))
    if rt > 1_000_000:
        print("    NOTE: ~{:,} tokens is past every context window -- Claude Code".format(rt))
        print("          literally cannot load it. That's the point. For a 'loads but")
        print("          drowns' answer on camera, use:  --entries 12000  (~180k tokens)\n")
    print("  Question (ask both):")
    print("    \"Plan my Tokyo trip - itinerary for stay, food, and activities, based")
    print("     on my preferences.\"\n")


if __name__ == "__main__":
    main()
