"""Earnings-fade Phase 0 — Eightcap single-stock CFD discovery + spread distribution + M5 depth.

For each of the 25 target Mag7 / large-cap names:
  1. Resolve the broker's exact ticker (try multiple suffixes: "", ".US", ".NAS", "#").
  2. Report tradability flags (trade_mode, visible, min volume, point size).
  3. Pull last 30d of M1 bars (which include `spread` column) and compute median
     RT spread in bps across the deploy-relevant hours (13:30-15:00 UTC = 09:30-11:00 ET).
  4. Pull M5 bars from 2018-01-01 to detect history depth.

Decision rule (pre-committed in earnings_fade.md):
  - basket median spread < 10 bps RT during deploy window  -> Phase 0 PASS
  - >= 15 of 25 names tradeable                            -> Phase 0 PASS
  - M5 history depth >= 3y on median name                  -> Phase 0 PASS
  Any FAIL => shelve thesis.

Run:
  PYTHONIOENCODING=utf-8 venv/Scripts/python.exe experiments/earnings_fade/_check_stock_spreads.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    print('ERROR: MetaTrader5 package not installed', file=sys.stderr)
    sys.exit(1)


TARGET_NAMES = [
    # Mag7
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    # Banks
    'JPM', 'BAC', 'GS', 'MS',
    # Payments
    'V', 'MA',
    # Health / retail / staples
    'UNH', 'WMT', 'HD', 'LOW', 'KO', 'PEP', 'JNJ',
    # Energy
    'XOM', 'CVX',
    # Software
    'ORCL', 'CRM', 'AVGO',
]

# Common broker-suffix patterns to try.
SUFFIX_CANDIDATES = ['', '.US', '.NAS', '.NYSE', '.NYS', '.OQ', '.N', '-USD']
PREFIX_CANDIDATES = ['', '#']

SPREAD_LOOKBACK_DAYS = 30
M5_DEPTH_START = datetime(2018, 1, 1, tzinfo=timezone.utc)

# MT5 broker server time = EET/EEST (UTC+2 winter / UTC+3 summer). NYSE RTH first 90 min
# (09:30-11:00 ET) = 16:30-18:00 server in summer (EDT + EEST) = hours [16, 17].
# Across DST winter (EST + EET), 09:30-11:00 ET = 15:30-17:00 server = hours [15, 16].
DEPLOY_HOURS_SERVER_SUMMER = [16, 17]
DEPLOY_HOURS_SERVER_WINTER = [15, 16]


def resolve_symbol(name: str) -> str | None:
    """Try common suffix/prefix permutations until MT5 returns a symbol_info."""
    for pfx in PREFIX_CANDIDATES:
        for sfx in SUFFIX_CANDIDATES:
            candidate = f'{pfx}{name}{sfx}'
            si = mt5.symbol_info(candidate)
            if si is not None:
                return candidate
    return None


def main() -> int:
    if not mt5.initialize():
        print(f'MT5 init failed: {mt5.last_error()}', file=sys.stderr)
        return 1
    try:
        info = mt5.terminal_info()
        if info:
            print(f'  Connected to: {info.company} / {info.name}')

        print(f'\n  === Phase 0a — symbol discovery (n={len(TARGET_NAMES)}) ===\n')

        resolved: dict[str, str] = {}
        unresolved: list[str] = []
        for name in TARGET_NAMES:
            sym = resolve_symbol(name)
            if sym is None:
                unresolved.append(name)
                print(f'  {name:<6s}  NOT FOUND on broker')
                continue
            resolved[name] = sym
            # Enable for trading data pulls.
            if not mt5.symbol_select(sym, True):
                print(f'  {name:<6s} -> {sym:<14s}  WARN: symbol_select failed')
                continue
            si = mt5.symbol_info(sym)
            tradeable = si.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL
            mark = '' if tradeable else '  (NOT fully tradeable)'
            print(f'  {name:<6s} -> {sym:<14s}  bid={si.bid:>9.3f}  ask={si.ask:>9.3f}  '
                  f'pt={si.point:.5f}  digits={si.digits}{mark}')

        n_resolved = len(resolved)
        print(f'\n  Resolved: {n_resolved}/{len(TARGET_NAMES)}')
        if unresolved:
            print(f'  Unresolved: {", ".join(unresolved)}')
        if n_resolved < 15:
            print(f'\n  KILL: only {n_resolved} names resolved (need >=15 for Phase 0 PASS)')

        # ---- Phase 0b: spread distribution ----
        print(f'\n  === Phase 0b — spread distribution (last {SPREAD_LOOKBACK_DAYS}d, M1 spread column) ===\n')
        print(f'  {"name":<6s} {"sym":<14s} {"n bars":>8s} '
              f'{"all med":>9s} {"all p90":>9s} '
              f'{"deploy med":>11s} {"deploy p90":>11s}')

        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=SPREAD_LOOKBACK_DAYS)

        per_name_med: dict[str, float] = {}
        per_name_p90: dict[str, float] = {}
        per_name_deploy_med: dict[str, float] = {}

        for name, sym in resolved.items():
            rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, start_dt, end_dt)
            if rates is None or len(rates) == 0:
                print(f'  {name:<6s} {sym:<14s} no M1 bars ({mt5.last_error()})')
                continue
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
            df['hour'] = df['time'].dt.hour
            si = mt5.symbol_info(sym)
            if 'spread' not in df.columns:
                # Fallback to H-L as proxy.
                df['spread_pts'] = (df['high'] - df['low']) / si.point
            else:
                df['spread_pts'] = df['spread']
            df['spread_usd'] = df['spread_pts'] * si.point
            df['mid'] = (df['open'] + df['close']) / 2.0
            df['spread_bps'] = df['spread_usd'] / df['mid'].replace(0, np.nan) * 1e4

            full = df['spread_bps'].dropna()
            deploy_mask = df['hour'].isin(DEPLOY_HOURS_SERVER_SUMMER + DEPLOY_HOURS_SERVER_WINTER)
            deploy = df.loc[deploy_mask, 'spread_bps'].dropna()

            all_med = float(full.median()) if not full.empty else float('nan')
            all_p90 = float(full.quantile(0.90)) if not full.empty else float('nan')
            dep_med = float(deploy.median()) if not deploy.empty else float('nan')
            dep_p90 = float(deploy.quantile(0.90)) if not deploy.empty else float('nan')

            per_name_med[name] = all_med
            per_name_p90[name] = all_p90
            per_name_deploy_med[name] = dep_med

            print(f'  {name:<6s} {sym:<14s} {len(df):>8d} '
                  f'{all_med:>8.2f}bp {all_p90:>8.2f}bp '
                  f'{dep_med:>10.2f}bp {dep_p90:>10.2f}bp')

        # Basket aggregates.
        if per_name_deploy_med:
            arr = np.array([v for v in per_name_deploy_med.values() if np.isfinite(v)])
            if arr.size:
                print(f'\n  Basket median(deploy-window medians) = {np.median(arr):.2f} bps')
                print(f'  Basket mean(deploy-window medians)   = {np.mean(arr):.2f} bps')
                print(f'  Basket max(deploy-window medians)    = {np.max(arr):.2f} bps  '
                      f'(worst name: {max(per_name_deploy_med, key=per_name_deploy_med.get)})')
                basket_med = float(np.median(arr))
                print()
                if basket_med < 10:
                    print(f'  -> Spread PASS: basket median {basket_med:.2f}bp < 10bp threshold')
                else:
                    print(f'  -> Spread KILL: basket median {basket_med:.2f}bp >= 10bp threshold')

        # ---- Phase 0c: M5 history depth ----
        print(f'\n  === Phase 0c — M5 history depth (start probe {M5_DEPTH_START.date()}) ===\n')
        print(f'  {"name":<6s} {"sym":<14s} {"first bar":>20s} {"last bar":>20s} {"bars":>10s} {"years":>6s}')

        end_dt = datetime.now(timezone.utc)
        per_name_years: dict[str, float] = {}

        for name, sym in resolved.items():
            rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, M5_DEPTH_START, end_dt)
            if rates is None or len(rates) == 0:
                print(f'  {name:<6s} {sym:<14s} no M5 bars ({mt5.last_error()})')
                continue
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
            first_t = df['time'].iloc[0]
            last_t = df['time'].iloc[-1]
            years = (last_t - first_t).days / 365.25
            per_name_years[name] = years
            print(f'  {name:<6s} {sym:<14s} {str(first_t)[:19]:>20s} '
                  f'{str(last_t)[:19]:>20s} {len(df):>10d} {years:>6.2f}')

        if per_name_years:
            yrs_arr = np.array(list(per_name_years.values()))
            print(f'\n  Median history depth: {np.median(yrs_arr):.2f}y; min: {yrs_arr.min():.2f}y')
            if np.median(yrs_arr) >= 3.0:
                print('  -> M5-depth PASS (median >= 3y)')
            else:
                print('  -> M5-depth KILL (median < 3y)')

        # Final Phase 0 verdict.
        print('\n  === Phase 0 verdict ===\n')
        verdicts = []
        verdicts.append(('symbol coverage', n_resolved >= 15, f'{n_resolved} resolved, need >=15'))
        if per_name_deploy_med:
            arr = np.array([v for v in per_name_deploy_med.values() if np.isfinite(v)])
            basket_med = float(np.median(arr)) if arr.size else float('inf')
            verdicts.append(('spread', basket_med < 10, f'basket median {basket_med:.2f}bp'))
        if per_name_years:
            med_yrs = float(np.median(list(per_name_years.values())))
            verdicts.append(('history depth', med_yrs >= 3.0, f'median {med_yrs:.2f}y'))
        for label, ok, detail in verdicts:
            mark = 'PASS' if ok else 'FAIL'
            print(f'  [{mark}] {label}: {detail}')

        if all(ok for _, ok, _ in verdicts):
            print('\n  Phase 0 overall PASS -> proceed to Phase 1 (earnings calendar + M5 backfill).')
        else:
            print('\n  Phase 0 FAIL -> shelve earnings_fade thesis (institutional-only or different broker).')

        return 0
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    sys.exit(main())
