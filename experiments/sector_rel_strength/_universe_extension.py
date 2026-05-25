"""Universe extension — backfill ~75 more Eightcap stocks for sector_mean_reversion validation.

Tries each candidate ticker via MT5 symbol_info; if found and tradeable, fetches M5 from 2018-01-01
and pushes to datalake via existing mt5_fetch infrastructure.
"""
from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_ROOT / 'scripts'))

try:
    import MetaTrader5 as mt5
except ImportError:
    print('ERROR: MetaTrader5 not installed', file=sys.stderr)
    sys.exit(1)

from _datalake import DATA_DIR, inject_to_datalake, merge_with_existing, write_csv  # noqa: E402


EXTENSION_CANDIDATES = [
    # Tech
    'ADBE', 'AMD', 'CSCO', 'CMCSA', 'INTC', 'NFLX', 'PYPL', 'QCOM', 'TXN', 'INTU',
    'IBM', 'MU', 'AMAT', 'ADI', 'ASML', 'PANW', 'NOW', 'ABNB', 'UBER', 'SHOP',
    'SNOW', 'COIN', 'PLTR', 'ON', 'ANET', 'KLAC', 'MRVL', 'ADP', 'CDNS', 'ADSK',
    # Financials
    'BRK.B', 'BRK.A', 'WFC', 'AXP', 'BLK', 'SPGI', 'MMC', 'AON', 'MET', 'PRU',
    'COF', 'SCHW', 'USB', 'PNC', 'C',
    # Health
    'PFE', 'MRK', 'ABBV', 'LLY', 'TMO', 'ABT', 'DHR', 'BMY', 'AMGN', 'GILD',
    'CI', 'CVS', 'ELV', 'ISRG', 'VRTX', 'REGN',
    # Energy
    'COP', 'EOG', 'SLB', 'PSX',
    # Industrials
    'BA', 'CAT', 'DE', 'MMM', 'GE', 'HON', 'RTX', 'LMT', 'NOC', 'GD',
    'UPS', 'FDX',
    # Consumer / Discret / Staples
    'NKE', 'SBUX', 'MCD', 'TGT', 'DG', 'COST', 'DIS', 'BKNG', 'CL', 'PG',
    'MO', 'PM', 'KHC',
    # Comms
    'T', 'VZ', 'CHTR', 'TMUS',
    # Misc large-cap
    'BABA', 'BIDU', 'PDD',
]


def main() -> int:
    if not mt5.initialize():
        print(f'MT5 init failed: {mt5.last_error()}', file=sys.stderr)
        return 1
    try:
        start_dt = datetime(2018, 1, 1, tzinfo=timezone.utc)
        end_dt = datetime.now(timezone.utc)
        inject = bool(os.getenv('DATALAKE_API_KEY', '').strip())

        resolved = []
        unresolved = []
        for name in EXTENSION_CANDIDATES:
            si = mt5.symbol_info(name)
            if si is None:
                unresolved.append(name)
                continue
            if not mt5.symbol_select(name, True):
                unresolved.append(name)
                continue
            resolved.append(name)
        print(f'  Resolved: {len(resolved)}/{len(EXTENSION_CANDIDATES)}')
        if unresolved:
            print(f'  Unresolved: {", ".join(unresolved)}')

        print(f'\n  Backfilling M5 from 2018-01-01 -> {end_dt.date()}...')
        n_done = 0
        for name in resolved:
            rates = mt5.copy_rates_range(name, mt5.TIMEFRAME_M5, start_dt, end_dt)
            if rates is None or len(rates) == 0:
                print(f'    {name:<8s} NO BARS')
                continue
            df = pd.DataFrame(rates)
            df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)
            df['instrument'] = name
            df['timeframe'] = 'M5'
            df_out = df[['instrument', 'timeframe', 'timestamp', 'open', 'high', 'low', 'close']]
            path = DATA_DIR / f'{name}_M5.csv'
            if path.exists():
                merged = merge_with_existing(df_out, path)
            else:
                merged = df_out
            write_csv(merged, path)
            msg = f'    {name:<8s} {len(df_out):>7d} bars -> {path.name}'
            if inject:
                try:
                    sent = inject_to_datalake(df_out, name, 'M5')
                    msg += f' | datalake +{sent}'
                except Exception as e:
                    msg += f' | datalake FAIL: {e}'
            print(msg)
            n_done += 1

        print(f'\n  Backfilled {n_done} new tickers to ohlc_data + datalake.')
        # Print final extended-universe list (for use in re-run).
        original = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
                    'JPM', 'BAC', 'GS', 'V', 'MA', 'UNH', 'WMT', 'HD', 'LOW',
                    'KO', 'PEP', 'JNJ', 'XOM', 'CVX', 'ORCL', 'CRM', 'AVGO']
        extended = sorted(set(original + resolved))
        print(f'\n  Extended universe size: {len(extended)} names')
        # Write to a file for the validation script to consume.
        out_path = _HERE / 'extended_universe.txt'
        out_path.write_text('\n'.join(extended) + '\n')
        print(f'  Wrote {out_path}')
        return 0
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    sys.exit(main())
