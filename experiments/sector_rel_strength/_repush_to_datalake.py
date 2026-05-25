"""Re-push extension stocks to datalake.

The original _universe_extension.py ingest calls returned success but the catalog
shows 73 of 77 names didn't actually persist. Re-pushing from local CSVs with
explicit per-name retry + verify.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_ROOT / 'scripts'))

from _datalake import DATA_DIR, inject_to_datalake  # noqa: E402


MISSING = [
    'ADBE', 'AMD', 'CSCO', 'CMCSA', 'INTC', 'NFLX', 'PYPL', 'QCOM', 'TXN', 'INTU',
    'IBM', 'MU', 'AMAT', 'ADI', 'ASML', 'NOW', 'SHOP', 'SNOW', 'COIN', 'PLTR',
    'KLAC', 'MRVL', 'ADP', 'CDNS', 'ADSK', 'BRK.A', 'WFC', 'AXP', 'BLK', 'SPGI',
    'PRU', 'SCHW', 'USB', 'C', 'PFE', 'MRK', 'ABBV', 'LLY', 'TMO', 'ABT', 'DHR',
    'BMY', 'AMGN', 'GILD', 'CVS', 'ELV', 'ISRG', 'VRTX', 'REGN', 'BA', 'CAT',
    'DE', 'MMM', 'GE', 'HON', 'UPS', 'FDX', 'NKE', 'SBUX', 'MCD', 'COST', 'DIS',
    'BKNG', 'MO', 'PM', 'KHC', 'T', 'VZ', 'CHTR', 'TMUS', 'BABA', 'BIDU', 'PDD',
]


def get_catalog_instruments() -> set[str]:
    url = os.getenv('DATALAKE_URL'); key = os.getenv('DATALAKE_API_KEY')
    r = requests.get(f'{url.rstrip("/")}/catalog', headers={'X-API-Key': key}, timeout=30)
    data = r.json()
    return {i['instrument'] for i in data['database']['instruments']}


def main() -> int:
    load_dotenv(_ROOT / '.env')
    if not os.getenv('DATALAKE_API_KEY'):
        print('DATALAKE_API_KEY not set'); return 1

    print(f'  Re-pushing {len(MISSING)} stocks from local CSVs...')

    success = []
    fail = []
    for i, name in enumerate(MISSING):
        path = DATA_DIR / f'{name}_M5.csv'
        if not path.exists():
            print(f'  [{i+1:>3d}/{len(MISSING)}] {name:<8s} CSV missing'); fail.append(name); continue
        try:
            df = pd.read_csv(path, parse_dates=['timestamp'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        except Exception as e:
            print(f'  [{i+1:>3d}/{len(MISSING)}] {name:<8s} CSV read FAIL: {e}'); fail.append(name); continue

        # Retry up to 3 times with backoff.
        last_err = None
        for attempt in range(3):
            try:
                sent = inject_to_datalake(df, name, 'M5')
                print(f'  [{i+1:>3d}/{len(MISSING)}] {name:<8s} {sent} rows OK (attempt {attempt+1})')
                success.append(name)
                last_err = None
                break
            except Exception as e:
                last_err = e
                time.sleep(2 ** attempt)
        if last_err:
            print(f'  [{i+1:>3d}/{len(MISSING)}] {name:<8s} FAIL after 3 attempts: {last_err}')
            fail.append(name)
        # Tiny inter-call delay to avoid hammering ingest endpoint.
        time.sleep(0.3)

    print(f'\n  Success: {len(success)}; Fail: {len(fail)}')

    # Verify against catalog.
    print('\n  Verifying via /catalog...')
    catalog = get_catalog_instruments()
    still_missing = [n for n in MISSING if n not in catalog]
    print(f'  Still missing after retries: {len(still_missing)}')
    if still_missing:
        print(f'    -> {still_missing}')
    return 0 if not still_missing else 1


if __name__ == '__main__':
    sys.exit(main())
