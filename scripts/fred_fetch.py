#!/usr/bin/env python3
"""
Fetch short-term interest rates from FRED for the FX carry strategy.

No API key required -- uses FRED's public fredgraph CSV endpoint.  For each
currency, pulls daily (or monthly, ffilled later) rates from 2015-01-01
onward, writes them to ``ohlc_data/rates/{CCY}_rate.csv`` with columns
``date,rate_pct`` (rate in percent, e.g. 5.25 not 0.0525).

Idempotent: re-running overwrites the per-currency CSV with the freshest
snapshot.  If any single series fails to download, it is logged and skipped.
"""

from __future__ import annotations

import io
import os
import sys
from datetime import datetime

import pandas as pd
import requests


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"

# currency -> FRED series id
SERIES_MAP: dict[str, str] = {
    "USD": "DFF",                 # Federal Funds Effective Rate, daily
    "EUR": "ECBDFR",              # ECB Deposit Facility Rate, daily
    "GBP": "IR3TIB01GBM156N",     # 3m interbank GB, monthly
    "JPY": "IR3TIB01JPM156N",     # 3m interbank JP, monthly
    "AUD": "IR3TIB01AUM156N",
    "NZD": "IR3TIB01NZM156N",
    "CAD": "IR3TIB01CAM156N",
    "NOK": "IR3TIB01NOM156N",
    # Note: the originally-specified INTDSRZAM193N discount-rate series ends
    # in 2013 on FRED (SARB stopped reporting), so we substitute the 3m
    # interbank series (same definition as the other non-USD/EUR entries).
    "ZAR": "IR3TIB01ZAM156N",     # 3m interbank ZA, monthly (INTDSRZAM193N ended 2013)
}

START_DATE = "2015-01-01"
OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ohlc_data",
    "rates",
)
REQUEST_TIMEOUT_S = 30


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def fetch_series(ccy: str, series_id: str) -> pd.DataFrame | None:
    """Fetch a single FRED series as a DataFrame[date, rate_pct].

    Returns ``None`` on any failure (logged).  The FRED CSV endpoint uses
    ``.`` as a missing-value marker; those rows are dropped.
    """
    url = FRED_CSV_URL.format(series_id=series_id)
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
    except Exception as e:
        print(f"  {ccy:<3s}  FAILED to download {series_id}: {e}")
        return None

    try:
        df = pd.read_csv(io.StringIO(resp.text))
    except Exception as e:
        print(f"  {ccy:<3s}  FAILED to parse CSV for {series_id}: {e}")
        return None

    if df.empty or df.shape[1] < 2:
        print(f"  {ccy:<3s}  empty or malformed CSV for {series_id}")
        return None

    # FRED CSV: first column is the date (either "DATE" legacy or
    # "observation_date" newer), second column is the series id.
    date_col = df.columns[0]
    val_col = df.columns[1]

    df = df.rename(columns={date_col: "date", val_col: "rate_pct"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    # FRED uses "." for missing; convert and drop.
    df["rate_pct"] = pd.to_numeric(df["rate_pct"], errors="coerce")
    df = df.dropna(subset=["rate_pct"])

    # Filter to start date.
    start_ts = pd.Timestamp(START_DATE)
    df = df[df["date"] >= start_ts].copy()

    df = df.sort_values("date").drop_duplicates(subset="date", keep="last")
    df = df.reset_index(drop=True)

    return df[["date", "rate_pct"]]


def write_series(ccy: str, df: pd.DataFrame) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{ccy}_rate.csv")
    # Write date as YYYY-MM-DD for cleanliness and easy re-parse.
    out = df.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out["source"] = "fred"
    out["fetched_at"] = pd.Timestamp.now(tz="UTC").isoformat()
    out.to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    # requests availability check (it's in requirements.txt; just sanity).
    try:
        import requests as _req  # noqa: F401
    except ImportError:
        print("ERROR: 'requests' package not installed. Run: pip install 'requests>=2.31.0'")
        return 1

    print(f"Fetching FRED rate series for {len(SERIES_MAP)} currencies, "
          f"from {START_DATE}...\n")

    os.makedirs(OUT_DIR, exist_ok=True)

    results: list[dict] = []
    for ccy, series_id in SERIES_MAP.items():
        df = fetch_series(ccy, series_id)
        if df is None or df.empty:
            results.append({
                "currency": ccy,
                "series": series_id,
                "status": "SKIPPED",
                "rows": 0,
                "first": "-",
                "last": "-",
                "last_rate": None,
            })
            continue
        path = write_series(ccy, df)
        results.append({
            "currency": ccy,
            "series": series_id,
            "status": "OK",
            "rows": len(df),
            "first": df["date"].iloc[0].strftime("%Y-%m-%d"),
            "last": df["date"].iloc[-1].strftime("%Y-%m-%d"),
            "last_rate": float(df["rate_pct"].iloc[-1]),
            "path": path,
        })
        print(f"  {ccy:<3s}  {series_id:<22s}  {len(df):>5d} rows  "
              f"{results[-1]['first']} -> {results[-1]['last']}  "
              f"last={results[-1]['last_rate']:.4f}%")

    # Summary table
    print()
    print("Summary")
    print("=======")
    print(f"  {'CCY':<4s} {'Series':<22s} {'Status':<8s} {'Rows':>6s}  "
          f"{'From':<12s} {'To':<12s} {'Last rate %':>12s}")
    print("  " + "-" * 82)
    n_ok = 0
    for r in results:
        last_str = f"{r['last_rate']:.4f}" if r["last_rate"] is not None else "-"
        print(f"  {r['currency']:<4s} {r['series']:<22s} {r['status']:<8s} "
              f"{r['rows']:>6d}  {r['first']:<12s} {r['last']:<12s} "
              f"{last_str:>12s}")
        if r["status"] == "OK":
            n_ok += 1

    print(f"\n  {n_ok}/{len(results)} series written to {OUT_DIR}")
    print(f"  Run time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    return 0 if n_ok > 0 else 2


if __name__ == "__main__":
    sys.exit(main())
