"""Fetch OHLC bars from Yahoo Finance into the datalake.

Backup/fallback to the MT5 fetcher for instruments the broker doesn't carry
deep history for — soft commodities (cocoa/coffee/sugar via futures front
months), US ETFs (SPY/EWZ/XLE/...), and anything else Yahoo serves.

Symbol syntax
-------------
Plain Yahoo ticker (used as both datalake name and Yahoo ticker)::

    python scripts/yahoo_fetch.py --symbols EWZ,SPY --timeframes D1 --from 2015-01-01

Aliased ``DISPLAY:TICKER`` (lets you keep a clean filename/instrument name
while hitting a messy Yahoo ticker like ``CC=F``)::

    python scripts/yahoo_fetch.py --symbols COCOA:CC=F,COFFEE:KC=F --timeframes D1 --from 2015-01-01

Built-in aliases are provided for common softs so the short name Just Works::

    python scripts/yahoo_fetch.py --symbols COCOA,COFFEE,SUGAR --timeframes D1 --from 2015-01-01
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# Inter-call delay to avoid Yahoo's aggressive rate limiting on bulk fetches.
# Yahoo bans the session-IP after roughly 10+ rapid requests; 300 ms spacing
# keeps us under the threshold for arbitrary-sized ticker lists.
INTER_CALL_DELAY_S = 0.3

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _datalake import DATA_DIR, PROJECT_ROOT, inject_to_datalake, merge_with_existing, write_csv

try:
    import yfinance as yf  # type: ignore
except ImportError:
    sys.stderr.write("yfinance is not installed. Install it with:\n    pip install yfinance\n")
    raise


# Short-name aliases for common instruments that have ugly Yahoo tickers.
# Pass any of these as --symbols and the right Yahoo ticker is used.
ALIASES: dict[str, str] = {
    # Soft commodity front-month futures
    "COCOA": "CC=F",
    "COFFEE": "KC=F",
    "SUGAR": "SB=F",
    "COTTON": "CT=F",
    "LUMBER": "LBR=F",
    "ORANGE_JUICE": "OJ=F",
    # Grains
    "WHEAT": "ZW=F",
    "CORN": "ZC=F",
    "SOYBEAN": "ZS=F",
    # Metals/energy (handy fallbacks; prefer MT5 when available)
    "GOLD": "GC=F",
    "SILVER": "SI=F",
    "WTI": "CL=F",
    "BRENT": "BZ=F",
    "NATGAS": "NG=F",
}

# MT5-style timeframe codes -> (yfinance interval, max-history warning)
TIMEFRAME_MAP: dict[str, tuple[str, str | None]] = {
    "M1": ("1m", "Yahoo limits 1m data to ~7 days"),
    "M2": ("2m", "Yahoo limits 2m data to ~60 days"),
    "M5": ("5m", "Yahoo limits 5m data to ~60 days"),
    "M15": ("15m", "Yahoo limits 15m data to ~60 days"),
    "M30": ("30m", "Yahoo limits 30m data to ~60 days"),
    "H1": ("1h", "Yahoo limits 1h data to ~730 days"),
    "D1": ("1d", None),
    "W1": ("1wk", None),
    "MN1": ("1mo", None),
}


def parse_symbol_spec(spec: str) -> tuple[str, str]:
    """Return (display_name, yahoo_ticker) for a ``DISPLAY:TICKER`` spec.

    - ``COCOA:CC=F`` -> ("COCOA", "CC=F")
    - ``EWZ`` -> ("EWZ", "EWZ")
    - ``COFFEE`` (in ALIASES) -> ("COFFEE", "KC=F")
    """
    if ":" in spec:
        display, ticker = spec.split(":", 1)
        return display.strip().upper(), ticker.strip()
    key = spec.strip().upper()
    return key, ALIASES.get(key, key)


def fetch_bars(display: str, ticker: str, tf_code: str, start: datetime, end: datetime, adjusted: bool = False) -> pd.DataFrame:
    """Pull bars from Yahoo and shape them into the datalake schema.

    ``adjusted=True`` applies yfinance auto-adjustment (splits + dividends
    back-applied to OHLC). Required for single-name equities where splits and
    dividends would otherwise look like spurious price jumps.
    """
    if tf_code not in TIMEFRAME_MAP:
        raise ValueError(f"Unknown timeframe {tf_code!r}. Supported: {', '.join(TIMEFRAME_MAP)}")
    interval, warning = TIMEFRAME_MAP[tf_code]
    if warning:
        print(f"  note: {warning}", file=sys.stderr)

    raw = yf.download(
        ticker,
        start=start.date().isoformat(),
        end=end.date().isoformat(),
        interval=interval,
        auto_adjust=adjusted,
        progress=False,
        threads=False,
    )

    if raw is None or raw.empty:
        return pd.DataFrame(columns=["instrument", "timeframe", "timestamp", "open", "high", "low", "close"])

    # yfinance returns a MultiIndex on columns even for single-ticker calls in
    # some versions (('Open', 'CC=F'), ('High', 'CC=F'), ...). Flatten it.
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0] for c in raw.columns]

    raw = raw.reset_index()
    # The index column is named "Date" for daily+ and "Datetime" for intraday.
    ts_col = "Datetime" if "Datetime" in raw.columns else "Date"
    ts = pd.to_datetime(raw[ts_col])
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")

    df = pd.DataFrame({
        "instrument": display,
        "timeframe": tf_code,
        "timestamp": ts,
        "open": raw["Open"].astype(float),
        "high": raw["High"].astype(float),
        "low": raw["Low"].astype(float),
        "close": raw["Close"].astype(float),
        "source": "yahoo",
        "fetched_at": pd.Timestamp.now("UTC"),
    })
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    return df


def parse_date(s: str, *, end: bool = False) -> datetime:
    dt = datetime.strptime(s, "%Y-%m-%d")
    if end:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt.replace(tzinfo=timezone.utc)


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch Yahoo Finance OHLC bars into the local datalake.")
    p.add_argument(
        "--symbols",
        required=True,
        help="Comma-separated symbols. Supports 'EWZ', 'COCOA' (alias), or 'DISPLAY:TICKER'",
    )
    p.add_argument(
        "--timeframes",
        default="D1",
        help=f"Comma-separated timeframes ({', '.join(TIMEFRAME_MAP)}). Default: D1",
    )
    p.add_argument("--from", dest="date_from", default="2015-01-01", help="Start date YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", default=None, help="End date YYYY-MM-DD (default: today UTC)")
    p.add_argument("--overwrite", action="store_true", help="Replace existing CSVs instead of merging")
    p.add_argument("--adjusted", action="store_true", help="Apply split/dividend adjustment (yfinance auto_adjust=True). Required for single-name equities.")
    p.add_argument("--dry-run", action="store_true", help="Fetch and report, but don't write files")
    p.add_argument(
        "--datalake",
        dest="datalake",
        action="store_true",
        default=True,
        help="POST bars to the datalake (default if DATALAKE_API_KEY is set)",
    )
    p.add_argument("--no-datalake", dest="datalake", action="store_false", help="Skip the datalake POST")
    p.add_argument("--csv-only", action="store_true", help="Alias for --no-datalake")
    args = p.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    start = parse_date(args.date_from)
    end = parse_date(args.date_to, end=True) if args.date_to else datetime.now(timezone.utc)

    specs = [parse_symbol_spec(s) for s in args.symbols.split(",") if s.strip()]
    tfs = [t.strip().upper() for t in args.timeframes.split(",") if t.strip()]

    import os
    inject = args.datalake and not args.csv_only and bool(os.getenv("DATALAKE_API_KEY", "").strip())

    total_new = 0
    total_injected = 0
    first_call = True
    for display, ticker in specs:
        for tf in tfs:
            if not first_call:
                time.sleep(INTER_CALL_DELAY_S)
            first_call = False
            df_new = fetch_bars(display, ticker, tf, start, end, adjusted=args.adjusted)
            path = DATA_DIR / f"{display}_{tf}.csv"

            if args.overwrite or not path.exists():
                merged = df_new
                added = len(df_new)
            else:
                before = pd.read_csv(path)
                merged = merge_with_existing(df_new, path)
                added = max(0, len(merged) - len(before))

            label = f"{display} {tf} ({ticker})"
            if args.dry_run:
                target = "datalake+csv" if inject else "csv"
                print(f"[dry-run] {label}: fetched {len(df_new)} bars, +{added} new -> {target}")
            elif not df_new.empty:
                write_csv(merged, path)
                msg = f"{label}: fetched {len(df_new)} bars, +{added} new -> {path}"
                if inject:
                    try:
                        sent = inject_to_datalake(df_new, display, tf)
                        total_injected += sent
                        msg += f" | datalake: +{sent}"
                    except Exception as e:
                        msg += f" | datalake FAILED: {e}"
                print(msg)
            else:
                print(f"{label}: no bars returned for {start.date()}..{end.date()}")

            total_new += added

    print(f"\nTotal new bars written to CSV: {total_new}")
    if inject:
        print(f"Total rows injected to datalake: {total_injected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
