"""One-shot fix: scale up filings where value was reported in thousands.

SEC began requiring whole-dollar values from filings reporting periods ending
on/after 2022-12-31, but adoption was uneven — some filers were already in
dollars earlier, while at least one (Berkshire) used thousands.

Detection: per-filing AVERAGE per-share value across all positions with
shares > 0. If avg < $5 the filing is almost certainly in thousands.
(No realistic equity portfolio averages below $5/share across its book.)

Idempotent: re-scaled filings will have avg per-share in normal range and
will be skipped on subsequent runs.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "hedge_data.db"
AVG_PER_SHARE_THRESHOLD = 5.0


def fix():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """SELECT id, period_of_report
           FROM Filings
           ORDER BY period_of_report DESC"""
    )
    all_filings = cur.fetchall()

    fixed_filings = 0
    fixed_holdings = 0
    skipped = 0
    for fid, period in all_filings:
        cur.execute(
            """SELECT AVG(value*1.0 / shares)
               FROM Holdings WHERE filing_id = ? AND shares > 0""",
            (fid,),
        )
        avg_per_share = (cur.fetchone()[0] or 0)
        if avg_per_share == 0:
            continue
        if avg_per_share >= AVG_PER_SHARE_THRESHOLD:
            skipped += 1
            continue

        # Scale up
        cur.execute("UPDATE Holdings SET value = value * 1000 WHERE filing_id = ?", (fid,))
        n = cur.rowcount
        fixed_holdings += n
        cur.execute("UPDATE Filings SET total_value = total_value * 1000 WHERE id = ?", (fid,))
        cur.execute(
            """UPDATE Holdings
               SET pct_portfolio = value * 100.0 / (SELECT total_value FROM Filings WHERE id = ?)
               WHERE filing_id = ?""",
            (fid, fid),
        )
        fixed_filings += 1
        print(f"  Scaled {period} (filing #{fid}): avg per-share was ${avg_per_share:.4f}, {n} holdings")

    print(f"\nScaled {fixed_filings} filings, {fixed_holdings} holdings total")
    print(f"Skipped {skipped} already-scaled filings")

    # Rescale HoldingChanges that point to the scaled filings (value_before/value_after).
    cur.execute("""
        UPDATE HoldingChanges
        SET value_before = value_before * 1000
        WHERE value_before > 0
          AND shares_before > 0
          AND value_before * 1.0 / shares_before < 5.0
    """)
    print(f"HoldingChanges.value_before rescaled: {cur.rowcount}")

    cur.execute("""
        UPDATE HoldingChanges
        SET value_after = value_after * 1000
        WHERE value_after > 0
          AND shares_after > 0
          AND value_after * 1.0 / shares_after < 5.0
    """)
    print(f"HoldingChanges.value_after rescaled: {cur.rowcount}")

    conn.commit()
    conn.close()
    print("[DONE]")


if __name__ == "__main__":
    fix()
