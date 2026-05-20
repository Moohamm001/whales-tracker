"""SEC EDGAR 13F-HR crawler for whales-tracker.

For each fund in the DB:
  1. Pull the submissions JSON from data.sec.gov
  2. Find the most recent 13F-HR (and the one before, for Q-over-Q deltas)
  3. Locate the information table XML inside the filing directory
  4. Parse, aggregate by CUSIP, map CUSIPs to tickers via OpenFIGI (cached)
  5. Insert into Filings / Stocks / Holdings, then compute HoldingChanges

SEC requires a real User-Agent (company/name + email). We use the operator's email.
Rate limit: SEC says <=10 req/s. We pace at ~5 req/s to be safe.
"""

import sqlite3
import time
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


DB_PATH = Path(__file__).resolve().parent.parent / "hedge_data.db"

USER_AGENT = "Whales Tracker mooham.00771@gmail.com"
SEC_HEADERS = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}
OPENFIGI_HEADERS = {"Content-Type": "application/json", "User-Agent": USER_AGENT}

SEC_REQ_INTERVAL = 0.2          # 5 req/s, half of the 10 req/s limit
OPENFIGI_BATCH = 10             # unauthenticated: 10 jobs / request
OPENFIGI_INTERVAL = 0.3         # unauthenticated: 25 requests / 6s, so ~0.25s/req min


_last_sec_call = [0.0]


def _http_get(url: str, headers=None) -> bytes:
    headers = headers or SEC_HEADERS
    if "sec.gov" in url:
        wait = SEC_REQ_INTERVAL - (time.time() - _last_sec_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_sec_call[0] = time.time()

    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as resp:
        data = resp.read()
    if resp.headers.get("Content-Encoding") == "gzip":
        import gzip
        data = gzip.decompress(data)
    return data


def _http_post_json(url: str, payload, headers=None) -> dict:
    headers = headers or OPENFIGI_HEADERS
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, headers=headers, method="POST")
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------- SEC EDGAR ----------

def fetch_submissions(cik: str) -> dict:
    padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded}.json"
    return json.loads(_http_get(url).decode("utf-8"))


def _extract_13fs(block: dict) -> list[dict]:
    """Pull all 13F-HR entries out of a submissions block (recent or archive)."""
    forms = block.get("form", [])
    accessions = block.get("accessionNumber", [])
    primary_docs = block.get("primaryDocument", [])
    filing_dates = block.get("filingDate", [])
    report_dates = block.get("reportDate", [])
    out = []
    for i, form in enumerate(forms):
        if form == "13F-HR":
            out.append({
                "accession": accessions[i],
                "primary_doc": primary_docs[i],
                "filed_date": filing_dates[i],
                "period_of_report": report_dates[i],
            })
    return out


def all_13f_filings(submissions: dict, *, include_archives: bool = True) -> list[dict]:
    """All 13F-HR filings for a fund, newest first.

    SEC's submissions JSON has a `recent` block (~last 1000 filings) plus a
    `files` array pointing to archive JSON files for older history. Following
    `files` lets us reach a fund's earliest 13F (often the late 1990s).
    """
    recent = submissions.get("filings", {}).get("recent", {})
    out = _extract_13fs(recent)

    if include_archives:
        files = submissions.get("filings", {}).get("files", [])
        for f in files:
            name = f.get("name")
            if not name:
                continue
            try:
                arc = json.loads(_http_get(
                    f"https://data.sec.gov/submissions/{name}"
                ).decode("utf-8"))
            except Exception as e:
                print(f"  [WARN] archive fetch failed for {name}: {e}")
                continue
            out.extend(_extract_13fs(arc))

    # Sort newest-first by period_of_report
    out.sort(key=lambda r: r["period_of_report"], reverse=True)
    return out


def latest_13f_filings(submissions: dict, limit: int = 200) -> list[dict]:
    """Backwards-compat wrapper: most recent N 13F-HRs across recent + archives.

    Default raised to 200 (50 years) so we get every filing a fund has on
    record. Limit is capped after merging recent + archive results.
    """
    return all_13f_filings(submissions, include_archives=True)[:limit]


def find_info_table_xml(cik: str, accession: str) -> str | None:
    """Locate the holdings XML file inside a filing directory."""
    cik_int = int(cik)
    acc_nodash = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}"
    index = json.loads(_http_get(f"{base}/index.json").decode("utf-8"))

    candidates = []
    for item in index.get("directory", {}).get("item", []):
        name = item["name"].lower()
        if name.endswith(".xml"):
            candidates.append(item["name"])

    # Prefer files that look like an info table, fall back to the largest .xml
    for name in candidates:
        low = name.lower()
        if "infotable" in low or "informationtable" in low or "information_table" in low:
            return f"{base}/{name}"

    # Heuristic: the holdings table is usually the larger of the .xml files
    candidates_with_size = []
    for item in index.get("directory", {}).get("item", []):
        name = item["name"]
        if name.lower().endswith(".xml"):
            try:
                size = int(item.get("size", 0))
            except (TypeError, ValueError):
                size = 0
            candidates_with_size.append((size, name))
    if candidates_with_size:
        candidates_with_size.sort(reverse=True)
        return f"{base}/{candidates_with_size[0][1]}"

    return None


# ---------- 13F XML parsing ----------

NS_PATTERN = re.compile(r"^\{[^}]+\}")


def _strip_ns(tag: str) -> str:
    return NS_PATTERN.sub("", tag)


def parse_info_table(xml_bytes: bytes) -> list[dict]:
    """Parse a 13F information table into rows: {cusip, name, value, shares}.

    Values are reported in USD (post-2023 13F amendments) or in thousands
    (pre-2023). We normalize by detecting the filing-era convention:
    if max value is small (<1e6), we assume thousands.
    """
    root = ET.fromstring(xml_bytes)
    rows = []
    for info in root.iter():
        if _strip_ns(info.tag) != "infoTable":
            continue
        row = {}
        for child in info:
            tag = _strip_ns(child.tag)
            if tag == "nameOfIssuer":
                row["name"] = (child.text or "").strip()
            elif tag == "cusip":
                row["cusip"] = (child.text or "").strip().upper()
            elif tag == "value":
                try:
                    row["value"] = float(child.text or 0)
                except ValueError:
                    row["value"] = 0.0
            elif tag == "shrsOrPrnAmt":
                for sub in child:
                    if _strip_ns(sub.tag) == "sshPrnamt":
                        try:
                            row["shares"] = int(child[0].text)
                        except (ValueError, TypeError, IndexError):
                            try:
                                row["shares"] = int(sub.text)
                            except (ValueError, TypeError):
                                row["shares"] = 0
                    if _strip_ns(sub.tag) == "sshPrnamtType":
                        row["sh_type"] = (sub.text or "").strip()
        if row.get("cusip"):
            row.setdefault("shares", 0)
            row.setdefault("value", 0.0)
            rows.append(row)
    return rows


def aggregate_by_cusip(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(lambda: {"name": "", "shares": 0, "value": 0.0})
    for r in rows:
        # Only count share-denominated positions (SH); skip principal/bond entries
        if r.get("sh_type") and r["sh_type"].upper() != "SH":
            continue
        g = grouped[r["cusip"]]
        g["name"] = g["name"] or r.get("name", "")
        g["shares"] += r.get("shares", 0)
        g["value"] += r.get("value", 0.0)
    return [{"cusip": k, **v} for k, v in grouped.items()]


def normalize_values(rows: list[dict], period_of_report: str | None = None) -> list[dict]:
    """SEC technically required whole-dollar values from periods ending
    2022-12-31 onward, but adoption was uneven — some filers were already in
    dollars years earlier (Bridgewater, Pershing Square), while others
    (Berkshire) stayed in thousands until the cutoff.

    Rule: rescale to dollars when the AVERAGE implied per-share value across
    positions with shares > 0 is < $5. No real equity portfolio averages
    below $5/share, so this catches thousands-denominated filings cleanly.
    """
    if not rows:
        return rows

    total_ps = 0.0
    n = 0
    for r in rows:
        if r.get("shares"):
            total_ps += r["value"] / r["shares"]
            n += 1
    if n == 0:
        return rows
    avg_ps = total_ps / n

    if avg_ps < 5.0:
        for r in rows:
            r["value"] *= 1000.0
    return rows


# ---------- OpenFIGI CUSIP -> ticker ----------

def load_cusip_cache(conn) -> dict[str, tuple[str | None, str | None]]:
    cur = conn.cursor()
    cur.execute("SELECT cusip, ticker, name FROM CusipCache")
    return {row[0]: (row[1], row[2]) for row in cur.fetchall()}


def save_cusip_cache(conn, cusip: str, ticker: str | None, name: str | None):
    conn.execute(
        "INSERT OR REPLACE INTO CusipCache (cusip, ticker, name) VALUES (?, ?, ?)",
        (cusip, ticker, name),
    )


def lookup_cusips_openfigi(cusips: list[str]) -> dict[str, dict]:
    """Returns {cusip: {'ticker': ..., 'name': ...}} for resolved CUSIPs.

    Circuit breaker: if we hit 3 consecutive rate-limit errors, abort the rest
    of the lookups for this fund. Failed CUSIPs are NOT cached, so they'll be
    retried on the next crawler run.
    """
    out = {}
    consecutive_429 = 0
    for i in range(0, len(cusips), OPENFIGI_BATCH):
        if consecutive_429 >= 3:
            remaining = len(cusips) - i
            print(f"  [WARN] OpenFIGI circuit open after 3x 429; skipping {remaining} remaining lookups (will retry next run)")
            break
        batch = cusips[i : i + OPENFIGI_BATCH]
        payload = [{"idType": "ID_CUSIP", "idValue": c} for c in batch]
        try:
            resp = _http_post_json("https://api.openfigi.com/v3/mapping", payload)
            consecutive_429 = 0
        except HTTPError as e:
            if e.code == 429:
                consecutive_429 += 1
                print(f"  [WARN] OpenFIGI rate-limited (run {consecutive_429}/3), backing off 15s...")
                time.sleep(15)
                continue
            else:
                print(f"  [WARN] OpenFIGI HTTP {e.code}: {e}")
                continue
        except URLError as e:
            print(f"  [WARN] OpenFIGI network error: {e}")
            continue

        for cusip, item in zip(batch, resp):
            if isinstance(item, dict) and "data" in item and item["data"]:
                # Prefer US Common Stock ticker
                pick = None
                for d in item["data"]:
                    if d.get("exchCode") in ("US", "UN", "UA", "UQ", "UR", "UW"):
                        pick = d
                        break
                if pick is None:
                    pick = item["data"][0]
                out[cusip] = {
                    "ticker": pick.get("ticker"),
                    "name": pick.get("name") or pick.get("securityName"),
                }
        time.sleep(OPENFIGI_INTERVAL)
    return out


def resolve_tickers(conn, cusip_to_name: dict[str, str],
                    cusip_value_order: list[str] | None = None) -> dict[str, dict]:
    """For all cusips, return {cusip: {ticker, name}} using cache + OpenFIGI.

    cusip_value_order, if provided, is the list of cusips sorted by value desc
    so the largest positions get their tickers first if the circuit opens.
    """
    cache = load_cusip_cache(conn)
    order = cusip_value_order if cusip_value_order is not None else list(cusip_to_name)
    unresolved = [c for c in order if c not in cache]

    if unresolved:
        print(f"  Looking up {len(unresolved)} CUSIPs via OpenFIGI (cached: {len(cache)})...")
        figi_results = lookup_cusips_openfigi(unresolved)
        for cusip in unresolved:
            if cusip not in figi_results:
                # Failed lookup -> don't cache, leave for retry next run
                continue
            r = figi_results[cusip]
            ticker = r.get("ticker")
            name = r.get("name") or cusip_to_name.get(cusip)
            save_cusip_cache(conn, cusip, ticker, name)
            cache[cusip] = (ticker, name)
        conn.commit()

    result = {}
    for c in cusip_to_name:
        if c in cache:
            result[c] = {"ticker": cache[c][0], "name": cache[c][1] or cusip_to_name[c]}
        else:
            result[c] = {"ticker": None, "name": cusip_to_name[c]}
    return result


# ---------- DB writes ----------

def quarter_for(period_of_report: str) -> str:
    """'2025-03-31' -> '2025Q1' """
    y, m, _ = period_of_report.split("-")
    q = (int(m) - 1) // 3 + 1
    return f"{y}Q{q}"


def upsert_stock(conn, cusip: str, ticker: str | None, name: str | None) -> int:
    cur = conn.cursor()
    cur.execute("SELECT id, ticker, name FROM Stocks WHERE cusip = ?", (cusip,))
    row = cur.fetchone()
    if row:
        # Backfill ticker/name if previously missing
        if (ticker and not row[1]) or (name and not row[2]):
            cur.execute(
                "UPDATE Stocks SET ticker = COALESCE(?, ticker), name = COALESCE(?, name) WHERE id = ?",
                (ticker, name, row[0]),
            )
        return row[0]
    cur.execute("INSERT INTO Stocks (cusip, ticker, name) VALUES (?, ?, ?)", (cusip, ticker, name))
    return cur.lastrowid


def compute_changes(conn, fund_id: int, current_filing_id: int, quarter: str):
    """Diff current filing vs the immediately preceding filing for the same fund."""
    cur = conn.cursor()
    cur.execute(
        """SELECT id FROM Filings
           WHERE fund_id = ?
             AND period_of_report < (SELECT period_of_report FROM Filings WHERE id = ?)
           ORDER BY period_of_report DESC LIMIT 1""",
        (fund_id, current_filing_id),
    )
    prev_row = cur.fetchone()
    if not prev_row:
        return
    prev_filing_id = prev_row[0]

    cur.execute(
        "SELECT stock_id, shares, value FROM Holdings WHERE filing_id = ?",
        (prev_filing_id,),
    )
    prev = {sid: (sh, v) for sid, sh, v in cur.fetchall()}

    cur.execute(
        "SELECT stock_id, shares, value FROM Holdings WHERE filing_id = ?",
        (current_filing_id,),
    )
    curr = {sid: (sh, v) for sid, sh, v in cur.fetchall()}

    for stock_id, (sh_after, val_after) in curr.items():
        if stock_id not in prev:
            change_type = "NEW"
            sh_before, val_before = 0, 0.0
            pct = None
        else:
            sh_before, val_before = prev[stock_id]
            if sh_after > sh_before:
                change_type = "ADDED"
            elif sh_after < sh_before:
                change_type = "REDUCED"
            else:
                continue
            pct = ((sh_after - sh_before) / sh_before * 100.0) if sh_before else None

        cur.execute(
            """INSERT OR REPLACE INTO HoldingChanges
               (fund_id, stock_id, quarter, change_type, shares_before, shares_after, value_before, value_after, pct_change)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fund_id, stock_id, quarter, change_type, sh_before, sh_after, val_before, val_after, pct),
        )

    for stock_id, (sh_before, val_before) in prev.items():
        if stock_id not in curr:
            cur.execute(
                """INSERT OR REPLACE INTO HoldingChanges
                   (fund_id, stock_id, quarter, change_type, shares_before, shares_after, value_before, value_after, pct_change)
                   VALUES (?, ?, ?, 'SOLD', ?, 0, ?, 0, -100.0)""",
                (fund_id, stock_id, quarter, sh_before, val_before),
            )


def insert_filing(conn, fund_id: int, filing_meta: dict, holdings: list[dict],
                  ticker_map: dict[str, dict]) -> int | None:
    cur = conn.cursor()
    cur.execute("SELECT id FROM Filings WHERE accession_no = ?", (filing_meta["accession"],))
    existing = cur.fetchone()
    if existing:
        print(f"  [SKIP] Filing {filing_meta['accession']} already in DB")
        return existing[0]

    total_value = sum(h["value"] for h in holdings)
    quarter = quarter_for(filing_meta["period_of_report"])

    cur.execute(
        """INSERT INTO Filings (fund_id, accession_no, quarter, filed_date, period_of_report, total_value, holdings_count)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (fund_id, filing_meta["accession"], quarter, filing_meta["filed_date"],
         filing_meta["period_of_report"], total_value, len(holdings)),
    )
    filing_id = cur.lastrowid

    for h in holdings:
        info = ticker_map.get(h["cusip"], {})
        stock_id = upsert_stock(conn, h["cusip"], info.get("ticker"), info.get("name") or h["name"])
        pct = (h["value"] / total_value * 100.0) if total_value else 0.0
        cur.execute(
            """INSERT INTO Holdings (filing_id, stock_id, shares, value, pct_portfolio)
               VALUES (?, ?, ?, ?, ?)""",
            (filing_id, stock_id, h["shares"], h["value"], pct),
        )

    conn.commit()
    return filing_id


# ---------- Pipeline ----------

def backfill_changes(conn, fund_id: int):
    """For each filing in the fund, ensure HoldingChanges exists vs the
    immediately-preceding filing. Skips filings that already have changes
    or no preceding filing.
    """
    cur = conn.cursor()
    cur.execute(
        """SELECT id, period_of_report, quarter FROM Filings
           WHERE fund_id = ? ORDER BY period_of_report ASC""",
        (fund_id,),
    )
    filings = cur.fetchall()
    for i, (fid, _, q) in enumerate(filings):
        if i == 0:
            continue
        cur.execute(
            "SELECT 1 FROM HoldingChanges WHERE fund_id = ? AND quarter = ? LIMIT 1",
            (fund_id, q),
        )
        if cur.fetchone():
            continue
        compute_changes(conn, fund_id, fid, q)
    conn.commit()


def process_fund(conn, fund_row: tuple):
    fund_id, cik, name = fund_row
    print(f"\n[FUND] {name} (CIK {cik})")
    try:
        subs = fetch_submissions(cik)
    except HTTPError as e:
        print(f"  [ERR] Cannot fetch submissions: HTTP {e.code}")
        return
    except URLError as e:
        print(f"  [ERR] Network error: {e}")
        return

    filings = latest_13f_filings(subs, limit=200)  # all available
    if not filings:
        print(f"  [WARN] No 13F-HR filings found")
        return

    print(f"  Found {len(filings)} recent 13F-HR filing(s)")

    # Process oldest first so Q-over-Q diffs work on the newest
    filings_chrono = sorted(filings, key=lambda f: f["period_of_report"])

    for meta in filings_chrono:
        cur = conn.cursor()
        cur.execute("SELECT id FROM Filings WHERE accession_no = ?", (meta["accession"],))
        if cur.fetchone():
            print(f"  [SKIP] {meta['period_of_report']} (accession {meta['accession']}) already in DB")
            continue

        try:
            xml_url = find_info_table_xml(cik, meta["accession"])
        except Exception as e:
            print(f"  [ERR] Index lookup failed for {meta['accession']}: {e}")
            continue
        if not xml_url:
            print(f"  [WARN] No info table XML in {meta['accession']}")
            continue

        print(f"  Fetching {meta['period_of_report']} info table...")
        try:
            xml_bytes = _http_get(xml_url)
        except Exception as e:
            print(f"  [ERR] XML fetch failed: {e}")
            continue

        rows = parse_info_table(xml_bytes)
        agg = aggregate_by_cusip(rows)
        agg = normalize_values(agg, period_of_report=meta.get("period_of_report"))
        if not agg:
            print(f"  [WARN] No holdings parsed")
            continue

        cusip_to_name = {h["cusip"]: h["name"] for h in agg}
        # Process largest positions first so tickers for the top holdings always resolve
        value_order = [h["cusip"] for h in sorted(agg, key=lambda x: x["value"], reverse=True)]
        ticker_map = resolve_tickers(conn, cusip_to_name, value_order)

        filing_id = insert_filing(conn, fund_id, meta, agg, ticker_map)
        if filing_id:
            print(f"  [OK] Inserted {len(agg)} holdings, total ${sum(h['value'] for h in agg):,.0f}")
            compute_changes(conn, fund_id, filing_id, quarter_for(meta["period_of_report"]))
            conn.commit()

    # After all filings processed, backfill any missing Q/Q changes for this fund.
    backfill_changes(conn, fund_id)


def main():
    import sys
    cik_filter = None
    for a in sys.argv[1:]:
        if a.startswith("--cik="):
            cik_filter = a.split("=", 1)[1]

    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    conn.execute("PRAGMA busy_timeout = 60000")
    cur = conn.cursor()
    if cik_filter:
        cur.execute("SELECT id, cik, name FROM Funds WHERE cik = ?", (cik_filter,))
    else:
        cur.execute("SELECT id, cik, name FROM Funds ORDER BY id")
    funds = cur.fetchall()

    for fund_row in funds:
        try:
            process_fund(conn, fund_row)
        except Exception as e:
            print(f"  [ERR] Fund {fund_row[2]} failed: {e}")

    conn.close()
    print("\n[DONE] Crawl complete")


if __name__ == "__main__":
    main()
