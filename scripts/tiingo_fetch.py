"""Fetch daily OHLC bars from Tiingo into the local datalake.

Tiingo's daily endpoint returns split+dividend-adjusted prices out of the
box (``adjOpen/adjHigh/adjLow/adjClose``), which is what we want for
single-name equity research.

Requires ``TIINGO_API_KEY`` in ``.env``. Free tier: 50 req/hour, 1000 req/day
(practical for our 20-pair universe when re-fetches are cached).

Usage::

    python scripts/tiingo_fetch.py --symbols KO,PEP,XOM --from 2015-01-01

Writes to ``ohlc_data/{SYMBOL}_D1.csv`` in the shared datalake schema.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _datalake import DATA_DIR, PROJECT_ROOT, merge_with_existing, write_csv  # noqa: E402

TIINGO_BASE = "https://api.tiingo.com/tiingo/daily"
INTER_CALL_DELAY_S = 0.3


def fetch_one(ticker: str, start: str, end: str, api_key: str) -> pd.DataFrame:
    url = f"{TIINGO_BASE}/{ticker.lower()}/prices"
    params = {"startDate": start, "endDate": end, "format": "json"}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Token {api_key}",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=60)
    if resp.status_code == 404:
        raise RuntimeError(f"{ticker}: 404 — ticker not found in Tiingo")
    if not resp.ok:
        raise RuntimeError(f"{ticker}: {resp.status_code} {resp.reason} — {resp.text[:200]}")
    rows = resp.json()
    if not rows:
        return pd.DataFrame(columns=["instrument", "timeframe", "timestamp", "open", "high", "low", "close"])

    df = pd.DataFrame(rows)
    ts = pd.to_datetime(df["date"], utc=True)
    out = pd.DataFrame({
        "instrument": ticker,
        "timeframe": "D1",
        "timestamp": ts,
        "open": df["adjOpen"].astype(float),
        "high": df["adjHigh"].astype(float),
        "low": df["adjLow"].astype(float),
        "close": df["adjClose"].astype(float),
        "source": "tiingo",
        "fetched_at": pd.Timestamp.utcnow(),
    })
    out = out.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch daily OHLC from Tiingo into the local datalake.")
    p.add_argument("--symbols", required=True, help="Comma-separated ticker symbols (e.g. KO,PEP,XOM)")
    p.add_argument("--from", dest="date_from", default="2015-01-01", help="Start date YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", default=None, help="End date YYYY-MM-DD (default: today UTC)")
    p.add_argument("--overwrite", action="store_true", help="Replace existing CSVs instead of merging")
    p.add_argument("--dry-run", action="store_true", help="Fetch and report, don't write files")
    args = p.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("TIINGO_API_KEY", "").strip()
    if not api_key:
        sys.stderr.write("TIINGO_API_KEY is not set in .env\n")
        return 2

    end = args.date_to or datetime.now(timezone.utc).date().isoformat()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    total_new = 0
    saved = 0
    for i, t in enumerate(symbols):
        if i > 0:
            time.sleep(INTER_CALL_DELAY_S)
        try:
            df_new = fetch_one(t, args.date_from, end, api_key)
        except Exception as e:
            print(f"  {t}: FAILED ({e})")
            continue

        path = DATA_DIR / f"{t}_D1.csv"
        if args.overwrite or not path.exists():
            merged = df_new
            added = len(df_new)
        else:
            before = pd.read_csv(path)
            merged = merge_with_existing(df_new, path)
            added = max(0, len(merged) - len(before))

        if args.dry_run:
            print(f"[dry-run] {t}: fetched {len(df_new)} bars, +{added} new")
        elif not df_new.empty:
            write_csv(merged, path)
            print(f"  {t}: {len(df_new)} bars "
                  f"{df_new['timestamp'].iloc[0].date()} -> {df_new['timestamp'].iloc[-1].date()} "
                  f"(+{added} new) -> {path.name}")
            saved += 1
        else:
            print(f"  {t}: no bars returned for {args.date_from}..{end}")

        total_new += added

    print(f"\nSaved {saved}/{len(symbols)} tickers; {total_new} new rows written to CSV.")
    return 0 if saved == len(symbols) else 1


if __name__ == "__main__":
    raise SystemExit(main())
