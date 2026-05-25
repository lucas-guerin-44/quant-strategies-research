"""Earnings-fade Phase 1a — fetch earnings-announcement dates for the 24-name universe.

Uses yfinance Ticker.get_earnings_dates(limit=N) to pull historical announcements.
For each name, captures (ticker, ann_datetime_et, eps_estimate, eps_actual, surprise).

Outputs:
  experiments/earnings_fade/data/earnings_calendar.csv
    columns: ticker, ann_dt_et, ann_session (AMC|BMO|DURING), trade_date, eps_est, eps_act, surprise_pct

Where:
  - ann_dt_et         = announcement timestamp in US/Eastern.
  - ann_session       = AMC if hour >= 16, BMO if hour < 9.5, else DURING.
  - trade_date        = next RTH date if AMC; same date if BMO; same date if DURING (rare).
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
    print('ERROR: yfinance not installed', file=sys.stderr)
    sys.exit(1)


TARGET_NAMES = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM', 'BAC', 'GS',  # MS dropped (no broker symbol)
    'V', 'MA',
    'UNH', 'WMT', 'HD', 'LOW', 'KO', 'PEP', 'JNJ',
    'XOM', 'CVX',
    'ORCL', 'CRM', 'AVGO',
]

LIMIT_PER_NAME = 40  # quarters; ~10 years; yfinance returns what it can
OUT_DIR = Path(__file__).resolve().parent / 'data'
OUT_PATH = OUT_DIR / 'earnings_calendar.csv'


def classify_session(et_ts: pd.Timestamp) -> str:
    t = et_ts.time()
    if t >= dtime(16, 0):
        return 'AMC'
    if t < dtime(9, 30):
        return 'BMO'
    return 'DURING'


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for i, name in enumerate(TARGET_NAMES):
        print(f'  [{i+1:>2d}/{len(TARGET_NAMES)}] {name:<6s} fetching... ', end='', flush=True)
        try:
            tk = yf.Ticker(name)
            df = tk.get_earnings_dates(limit=LIMIT_PER_NAME)
        except Exception as e:  # noqa: BLE001
            print(f'ERROR: {e}')
            continue
        if df is None or df.empty:
            print('no data')
            continue
        # Index is tz-aware datetime in US/Eastern (yfinance default).
        df = df.copy()
        df['ticker'] = name
        df = df.reset_index().rename(columns={
            'Earnings Date': 'ann_dt_et',
            'EPS Estimate': 'eps_est',
            'Reported EPS': 'eps_act',
            'Surprise(%)': 'surprise_pct',
        })
        # Ensure ann_dt_et is timezone-aware in US/Eastern.
        if df['ann_dt_et'].dt.tz is None:
            df['ann_dt_et'] = df['ann_dt_et'].dt.tz_localize('US/Eastern')
        else:
            df['ann_dt_et'] = df['ann_dt_et'].dt.tz_convert('US/Eastern')
        df['ann_session'] = df['ann_dt_et'].apply(classify_session)

        # Compute trade_date — next NY RTH session if AMC, same date otherwise.
        def to_trade_date(ts: pd.Timestamp, sess: str) -> pd.Timestamp:
            d = ts.normalize().tz_localize(None)
            if sess == 'AMC':
                # Roll to next weekday.
                d = d + pd.Timedelta(days=1)
                while d.weekday() >= 5:
                    d = d + pd.Timedelta(days=1)
            else:
                # If BMO or DURING, today (or next weekday if weekend).
                while d.weekday() >= 5:
                    d = d + pd.Timedelta(days=1)
            return d

        df['trade_date'] = df.apply(lambda r: to_trade_date(r['ann_dt_et'], r['ann_session']), axis=1)
        rows.append(df[['ticker', 'ann_dt_et', 'ann_session', 'trade_date', 'eps_est', 'eps_act', 'surprise_pct']])
        print(f'{len(df)} events  (range {df["ann_dt_et"].min().date()} -> {df["ann_dt_et"].max().date()})')
        time.sleep(0.4)  # rate-limit hygiene per yahoo_fetch.md memory

    if not rows:
        print('No events fetched; aborting.')
        return 1
    out = pd.concat(rows, ignore_index=True).sort_values(['trade_date', 'ticker'])
    # Format datetimes as ISO strings (UTC) for CSV portability.
    out['ann_dt_et'] = out['ann_dt_et'].dt.strftime('%Y-%m-%d %H:%M:%S %Z')
    out['trade_date'] = out['trade_date'].dt.strftime('%Y-%m-%d')
    out.to_csv(OUT_PATH, index=False)
    print(f'\n  Wrote {len(out)} events to {OUT_PATH}')

    # Summary by ticker.
    print('\n  Per-ticker event counts:')
    counts = out.groupby('ticker').size().sort_values(ascending=False)
    for ticker, n in counts.items():
        dates = out.loc[out['ticker'] == ticker, 'trade_date']
        print(f'    {ticker:<6s} {n:>4d}  range {dates.min()} -> {dates.max()}')
    print(f'\n  Total: {len(out)} events across {len(counts)} tickers')
    return 0


if __name__ == '__main__':
    sys.exit(main())
