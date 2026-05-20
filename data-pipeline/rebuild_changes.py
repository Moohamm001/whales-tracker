"""Rebuild HoldingChanges from authoritative Holdings data.

Drops all HoldingChanges rows, then for each fund recomputes Q-over-Q
diffs from chronologically-ordered Filings using the same logic as the
crawler's compute_changes.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "hedge_data.db"


def quarter_for(period_of_report: str) -> str:
    y, m, _ = period_of_report.split("-")
    q = (int(m) - 1) // 3 + 1
    return f"{y}Q{q}"


def rebuild():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM HoldingChanges")
    print(f"Cleared {cur.rowcount} HoldingChanges rows")

    cur.execute("SELECT id, manager_name, name FROM Funds ORDER BY id")
    funds = cur.fetchall()

    total_changes = 0
    for fund_id, mgr, fname in funds:
        cur.execute(
            """SELECT id, period_of_report FROM Filings
               WHERE fund_id = ? ORDER BY period_of_report ASC""",
            (fund_id,),
        )
        filings = cur.fetchall()
        if len(filings) < 2:
            continue

        prev_filing_id = filings[0][0]
        for fid, period in filings[1:]:
            q = quarter_for(period)

            # Load prev and current holdings
            cur.execute("SELECT stock_id, shares, value FROM Holdings WHERE filing_id = ?", (prev_filing_id,))
            prev = {sid: (sh, v) for sid, sh, v in cur.fetchall()}

            cur.execute("SELECT stock_id, shares, value FROM Holdings WHERE filing_id = ?", (fid,))
            curr = {sid: (sh, v) for sid, sh, v in cur.fetchall()}

            n = 0
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
                    (fund_id, stock_id, q, change_type, sh_before, sh_after, val_before, val_after, pct),
                )
                n += 1

            for stock_id, (sh_before, val_before) in prev.items():
                if stock_id not in curr:
                    cur.execute(
                        """INSERT OR REPLACE INTO HoldingChanges
                           (fund_id, stock_id, quarter, change_type, shares_before, shares_after, value_before, value_after, pct_change)
                           VALUES (?, ?, ?, 'SOLD', ?, 0, ?, 0, -100.0)""",
                        (fund_id, stock_id, q, sh_before, val_before),
                    )
                    n += 1

            total_changes += n
            prev_filing_id = fid

        print(f"  {mgr:<22}: {len(filings)} filings -> rebuilt changes")

    conn.commit()
    conn.close()
    print(f"\n[DONE] Total HoldingChanges rebuilt: {total_changes:,}")


if __name__ == "__main__":
    rebuild()
