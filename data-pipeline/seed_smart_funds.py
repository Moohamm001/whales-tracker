"""Tag existing funds + provide a template for expanding the universe.

Why: the 12 famous investors are mega-cap-biased. 13F signal is strongest
in small/mid-caps the megas can't touch. This script:

  1. Tags each of the existing 12 with fund_type / cap_focus / style_tags
     so the UI can filter "deep-value contrarians" or "tiger-cubs growth"
     as cohorts.

  2. Documents an extension template at the bottom (CANDIDATES_TO_VERIFY).
     CIKs MUST be verified at https://www.sec.gov/cgi-bin/browse-edgar
     before adding — a wrong CIK pulls the wrong fund's filings.

Run:
  python data-pipeline/seed_smart_funds.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "hedge_data.db"


# ---------------------------------------------------------------------------
# Tag the existing 12 (CIKs are verified — these are already in the DB)
# ---------------------------------------------------------------------------
EXISTING_TAGS = {
    # cik: (fund_type, cap_focus, is_specialist, style_tags)
    "0001067983": ("value",       "all",   0, "quality,long-term,concentrated"),       # Berkshire
    "0001350694": ("macro",       "all",   0, "risk-parity,macro,systematic"),         # Bridgewater
    "0001336528": ("activist",    "large", 0, "concentrated,activist,catalyst"),       # Pershing Square
    "0001037389": ("quant",       "all",   0, "stat-arb,short-horizon"),               # Renaissance
    "0001649339": ("value",       "all",   1, "deep-value,contrarian,concentrated"),   # Scion (Burry)
    "0001079114": ("value",       "all",   0, "long-short,value,short-thesis"),        # Greenlight
    "0001029160": ("macro",       "all",   0, "macro,opportunistic"),                  # Soros
    "0001656456": ("value",       "all",   0, "distressed,opportunistic,value"),       # Appaloosa
    "0001167483": ("growth",      "all",   0, "tiger-cub,growth,tech"),                # Tiger Global
    "0001423053": ("multi-strat", "all",   0, "market-maker,multi-strat,quant"),       # Citadel
    "0001364742": ("index",       "mega",  0, "passive,index,systematic"),             # BlackRock
    "0001536411": ("macro",       "all",   0, "macro,concentrated"),                   # Duquesne
}


# ---------------------------------------------------------------------------
# CANDIDATES TO ADD — CIKs MUST be verified before insert.
#
# Look each one up at:
#   https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany
#     &company=<name>&type=13F-HR&dateb=&owner=include&count=40
#
# When you have a verified CIK, paste the row into FAMOUS_FUNDS in
# data-pipeline/setup_db.py (with the fund_type/cap_focus tag here applied
# afterwards via UPDATE), then re-run sec_crawler.py.
#
# Categories worth adding (rationale):
#   - SMALL-CAP DEEP VALUE: Donald Smith, Royce, Tweedy Browne, Bares Capital
#       → coverage in the cap segment Berkshire/BlackRock can't enter
#   - MICROCAP SPECIALISTS: Greenhaven Road, Eriksen, Bonhoeffer
#       → earliest signal of accumulation in tiny illiquid names
#   - ACTIVIST: Icahn, Starboard, Engaged Capital, Ancora, Voce
#       → catalyst plays — value unlock typically visible 1-2Q later
#   - CONCENTRATED QUALITY: Akre, Polen, Wedgewood, Giverny
#       → high-conviction long-term holdings
#   - TIGER CUBS GROWTH: Coatue, Lone Pine, Viking, Maverick
#       → covers growth side of cap spectrum
#   - QUANT/MULTI-STRAT: D.E. Shaw, Two Sigma, Millennium, Marshall Wace
#       → different signal type — short-horizon, factor-based
# ---------------------------------------------------------------------------
CANDIDATES_TO_VERIFY = [
    # (name, manager, fund_type, cap_focus, is_specialist, style_tags, rationale)
    ("Donald Smith & Co",        "Donald Smith",   "value",    "small", 1, "deep-value,small-cap,contrarian",   "Bottom-decile P/TBV strategy since 1980"),
    ("Royce Investment Partners","Chuck Royce",    "value",    "small", 1, "small-cap,value,quality",           "Longest-running small-cap shop"),
    ("Tweedy, Browne",           "Christopher Browne", "value","all",   0, "deep-value,global,quality",         "Graham-and-Dodd value, Buffett partner"),
    ("Bares Capital",            "Brian Bares",    "value",    "small", 1, "small-cap,concentrated,quality",    "Austin TX, low turnover concentrated"),
    ("Greenhaven Road Capital",  "Scott Miller",   "value",    "micro", 1, "microcap,concentrated,contrarian",  "Microcap value, letter-driven"),
    ("Pabrai Investment Funds",  "Mohnish Pabrai", "value",    "all",   0, "deep-value,concentrated,contrarian","Buffett-style, 10-20 names"),

    ("Engaged Capital",          "Glenn Welling",  "activist", "small", 1, "activist,small-cap,catalyst",       "Small/mid-cap value-unlock activist"),
    ("Starboard Value",          "Jeff Smith",     "activist", "mid",   1, "activist,mid-cap,catalyst",         "Mid-cap operational change activist"),
    ("Icahn Capital",            "Carl Icahn",     "activist", "all",   0, "activist,concentrated,catalyst",    "OG corporate activist"),

    ("Akre Capital Management",  "Chuck Akre",     "quality",  "all",   0, "quality,compounders,long-term",     "Compounder/quality concentrated"),
    ("Polen Capital",            "Dan Davidowitz", "quality",  "large", 0, "quality,growth,concentrated",       "Growth-at-quality, sub-30 holdings"),

    ("Coatue Management",        "Philippe Laffont","growth",  "large", 0, "tiger-cub,growth,tech",             "Tiger cub, tech crossover"),
    ("Viking Global",            "Andreas Halvorsen","growth", "large", 0, "tiger-cub,growth,global",           "Tiger cub, global long-short"),
    ("Lone Pine Capital",        "Steve Mandel",   "growth",   "large", 0, "tiger-cub,growth,global",           "Tiger cub, long-short growth"),

    ("D. E. Shaw & Co",          "David Shaw",     "quant",    "all",   0, "quant,multi-strat,systematic",      "Quant+fundamental hybrid"),
    ("Two Sigma Investments",    "Overdeck/Siegel","quant",    "all",   0, "quant,ml,systematic",               "Pure quant, ML strategies"),
    ("Millennium Management",    "Izzy Englander", "multi-strat","all", 0, "multi-strat,pod-shop,low-risk",     "Multi-strat pod shop"),

    ("Oakmark / Harris",         "Bill Nygren",    "value",    "large", 0, "value,long-term,mid-cap",           "Classic mid/large value mutual fund"),
    ("Southeastern (Longleaf)",  "Mason Hawkins",  "value",    "all",   0, "value,concentrated,long-term",      "Longleaf — concentrated value"),
    ("Wallace Weitz & Co",       "Wally Weitz",    "value",    "all",   0, "value,quality,long-term",           "Buffett-style mutual fund manager"),
]


def tag_existing(conn):
    cur = conn.cursor()
    n = 0
    for cik, (ftype, cap_focus, is_spec, tags) in EXISTING_TAGS.items():
        row = cur.execute("SELECT id, name FROM Funds WHERE cik = ?", (cik,)).fetchone()
        if not row:
            print(f"  [SKIP] CIK {cik} not in DB")
            continue
        cur.execute(
            """UPDATE Funds SET fund_type = ?, cap_focus = ?,
                      is_specialist = ?, style_tags = ?
               WHERE cik = ?""",
            (ftype, cap_focus, is_spec, tags, cik),
        )
        print(f"  + {row[1][:30]:<30} -> {ftype} / {cap_focus}")
        n += 1
    print(f"[OK] Tagged {n} existing funds")


def print_candidates():
    print()
    print("=" * 76)
    print("CANDIDATES TO EXPAND THE UNIVERSE")
    print("=" * 76)
    print("To add any of these, look up the CIK at SEC EDGAR, then add to")
    print("FAMOUS_FUNDS in setup_db.py with the tag below, and re-crawl:")
    print()
    for name, mgr, ftype, cap_focus, is_spec, tags, rationale in CANDIDATES_TO_VERIFY:
        print(f"  • {name:<28} [{ftype}/{cap_focus}]  — {rationale}")
    print()


def main():
    conn = sqlite3.connect(DB_PATH)
    tag_existing(conn)
    conn.commit()
    conn.close()
    print_candidates()


if __name__ == "__main__":
    main()
