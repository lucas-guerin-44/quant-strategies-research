"""Fetch earnings-announcement dates + EPS surprises for the PEAD mid-cap universe
via yfinance. Mirrors `experiments/earnings_fade/_fetch_earnings_calendar.py`.

Outputs:
  experiments/pead_midcap/data/earnings_calendar_midcap.csv
    columns: ticker, ann_dt_et, ann_session (AMC|BMO|DURING), trade_date, eps_est, eps_act, surprise_pct
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed", file=sys.stderr)
    sys.exit(1)


_HERE = Path(__file__).resolve().parent
UNIVERSE_PATH = _HERE.parent.parent / "experiments" / ".us_stock_universe.txt"
# When the script is run from the project root, _HERE = experiments/pead_midcap;
# resolve fallback to absolute project layout.
if not UNIVERSE_PATH.exists():
    UNIVERSE_PATH = Path(__file__).resolve().parents[2] / "experiments" / ".us_stock_universe.txt"

OUT_DIR = _HERE / "data"
OUT_PATH = OUT_DIR / "earnings_calendar_midcap.csv"

LIMIT_PER_NAME = 60        # yfinance returns up to ~12-15 yr of quarters
INTER_CALL_DELAY_S = 0.5   # be polite — yf rate-limits


def classify_session(et_ts: pd.Timestamp) -> str:
    t = et_ts.time()
    if t >= dtime(16, 0):
        return "AMC"
    if t < dtime(9, 30):
        return "BMO"
    return "DURING"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not UNIVERSE_PATH.exists():
        print(f"ERROR: universe file missing: {UNIVERSE_PATH}", file=sys.stderr)
        return 1
    universe = [s.strip() for s in UNIVERSE_PATH.read_text().splitlines() if s.strip()]
    print(f"Universe: {len(universe)} names from {UNIVERSE_PATH.name}")

    rows: list[dict] = []
    failed: list[str] = []
    for i, name in enumerate(universe):
        print(f"  [{i+1:>3d}/{len(universe)}] {name:<6s} fetching...", end=" ", flush=True)
        try:
            tk = yf.Ticker(name)
            df = tk.get_earnings_dates(limit=LIMIT_PER_NAME)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: {e}")
            failed.append(name)
            time.sleep(INTER_CALL_DELAY_S)
            continue
        if df is None or df.empty:
            print("no data")
            failed.append(name)
            time.sleep(INTER_CALL_DELAY_S)
            continue
        df = df.copy()
        df["ticker"] = name
        df = df.reset_index().rename(columns={
            "Earnings Date": "ann_dt_et",
            "EPS Estimate": "eps_est",
            "Reported EPS": "eps_act",
            "Surprise(%)": "surprise_pct",
        })
        if df["ann_dt_et"].dt.tz is None:
            df["ann_dt_et"] = df["ann_dt_et"].dt.tz_localize("US/Eastern")
        else:
            df["ann_dt_et"] = df["ann_dt_et"].dt.tz_convert("US/Eastern")
        df["ann_session"] = df["ann_dt_et"].apply(classify_session)

        def to_trade_date(ts: pd.Timestamp, sess: str) -> pd.Timestamp:
            d = ts.normalize().tz_localize(None)
            if sess == "AMC":
                d = d + pd.Timedelta(days=1)
                while d.weekday() >= 5:
                    d = d + pd.Timedelta(days=1)
            return d

        df["trade_date"] = [
            to_trade_date(r.ann_dt_et, r.ann_session) for r in df.itertuples(index=False)
        ]
        df = df[["ticker", "ann_dt_et", "ann_session", "trade_date",
                 "eps_est", "eps_act", "surprise_pct"]]
        # Drop rows missing EPS (future/forecast-only rows)
        df = df.dropna(subset=["eps_act"])
        rows.extend(df.to_dict(orient="records"))
        print(f"{len(df)} events")
        time.sleep(INTER_CALL_DELAY_S)

    if not rows:
        print("No data fetched — check rate limits / connectivity.")
        return 1
    out = pd.DataFrame(rows).sort_values(["ticker", "ann_dt_et"])
    # Convert ann_dt_et to ISO string for stable CSV serialization
    out["ann_dt_et"] = out["ann_dt_et"].astype(str)
    out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.strftime("%Y-%m-%d")
    out.to_csv(OUT_PATH, index=False)
    print(f"\nWrote {len(out)} events for {out['ticker'].nunique()} tickers -> {OUT_PATH}")
    if failed:
        print(f"Failed ({len(failed)}): {','.join(failed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
