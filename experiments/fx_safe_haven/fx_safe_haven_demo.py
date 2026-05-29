#!/usr/bin/env python3
"""
FX safe-haven: short JPY-crosses during equity stress regimes.

Thesis: experiments/fx_safe_haven/fx_safe_haven.md

Mechanism: when SPX500 enters stress regime (drawdown / vol-spike / below SMA),
short carry-pairs (NZDJPY/CADJPY/AUDJPY/USDJPY) to capture the carry-unwind
flow.

Universe:
  Primary: NZDJPY D1, CADJPY D1, AUDJPY (from H1), USDJPY (from H1)
  Regime signal: SPX500 D1

Variants tested:
  V1: spx_drawdown_60d < -5%
  V2: spx_rvol_20 > 1.5 * full-sample median
  V3: spx_close < spx_sma_50
  V4: V1 OR V2  (union)
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))

from data import fetch_ohlc  # noqa: E402


# --- Config ---------------------------------------------------------------

PAIRS = ['NZDJPY', 'CADJPY', 'AUDJPY', 'USDJPY']
START_DATE = '2018-01-01'
END_DATE = '2026-04-22'

# Regime params
SPX_DD_LOOKBACK = 60
SPX_DD_THRESH = -0.05
SPX_RVOL_LOOKBACK = 20
SPX_RVOL_MULT = 1.5
SPX_SMA_LEN = 50

VOL_TARGET_ANN = 0.10
COST_BPS_RT = 1.0
MAX_HOLD_DAYS = 90
ADVERSE_STOP_PCT = -0.08
DAYS_PER_YEAR = 252


# --- helpers --------------------------------------------------------------

def section(t: str) -> None:
    print(f'\n{"=" * 88}\n  {t}\n{"=" * 88}')


def load_pair_d1(symbol: str, prefer_h1: bool = False) -> pd.DataFrame:
    """Load D1 bars. For pairs without direct D1 (or with short D1 coverage),
    aggregate H1 from the local cache.
    """
    if not prefer_h1:
        # try D1 direct first
        try:
            raw = fetch_ohlc(symbol, 'D1', START_DATE, END_DATE)
            if raw is not None and not raw.empty and len(raw) > 1500:
                df = raw[['timestamp', 'open', 'high', 'low', 'close']].copy()
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
                df = df.set_index('timestamp').sort_index()
                df.index = df.index.tz_convert('UTC').tz_localize(None).normalize()
                df = df[~df.index.duplicated(keep='first')]
                df = df[df.index.dayofweek < 5]
                return df
        except Exception:
            pass

    # fall back to H1 aggregation
    path_h1 = os.path.join(_ROOT, 'ohlc_data', f'{symbol}_H1.csv')
    if not os.path.exists(path_h1):
        raise RuntimeError(f'No D1 or H1 data for {symbol}')
    h1 = pd.read_csv(path_h1, parse_dates=['timestamp'])
    h1['timestamp'] = pd.to_datetime(h1['timestamp'], utc=True)
    h1 = h1.sort_values('timestamp').set_index('timestamp')
    h1 = h1[~h1.index.duplicated(keep='first')]
    h1.index = h1.index.tz_convert('UTC').tz_localize(None)
    day = h1.index.normalize()
    d1 = pd.DataFrame({
        'open': h1.groupby(day)['open'].first(),
        'high': h1.groupby(day)['high'].max(),
        'low': h1.groupby(day)['low'].min(),
        'close': h1.groupby(day)['close'].last(),
    })
    d1 = d1[d1.index.dayofweek < 5]
    return d1


def annual_sharpe(r: np.ndarray, bpy: int = DAYS_PER_YEAR) -> float:
    r = r[np.isfinite(r)]
    if r.size < 2:
        return 0.0
    s = r.std(ddof=1)
    return 0.0 if s == 0 else float(r.mean() / s * np.sqrt(bpy))


def max_drawdown(eq: np.ndarray) -> float:
    if len(eq) == 0:
        return 0.0
    peak = np.maximum.accumulate(eq)
    return float(((eq - peak) / peak).min())


# --- regime signals -------------------------------------------------------

def build_spx_regime(spx: pd.DataFrame) -> pd.DataFrame:
    c = spx['close']
    rets = c.pct_change()
    rvol_20 = rets.rolling(SPX_RVOL_LOOKBACK).std(ddof=1) * np.sqrt(DAYS_PER_YEAR)
    rvol_median = rvol_20.median()
    spx_dd_60 = c / c.rolling(SPX_DD_LOOKBACK).max() - 1.0
    sma_50 = c.rolling(SPX_SMA_LEN).mean()

    reg = pd.DataFrame(index=c.index)
    reg['V1_drawdown'] = (spx_dd_60.shift(1) < SPX_DD_THRESH)
    reg['V2_rvol_spike'] = (rvol_20.shift(1) > rvol_median * SPX_RVOL_MULT)
    reg['V3_below_sma'] = (c.shift(1) < sma_50.shift(1))
    reg['V4_union_V1_V2'] = reg['V1_drawdown'] | reg['V2_rvol_spike']
    return reg


# --- simulator ------------------------------------------------------------

def simulate_fx_safe(
    pair_bars: pd.DataFrame,
    regime_signal: pd.Series,   # daily bool series
    direction: int = -1,        # -1 = short pair (long JPY), +1 = long pair (null check)
    vol_target_ann: float = VOL_TARGET_ANN,
    cost_bps_rt: float = COST_BPS_RT,
    max_hold_days: int = MAX_HOLD_DAYS,
    adverse_stop_pct: float = ADVERSE_STOP_PCT,
) -> tuple[pd.Series, list[dict]]:
    """Trade `direction` while regime is True. Exit when regime flips or stop.

    Returns daily-return series (vol-targeted, post-cost) and trade list.
    """
    # Align signals to pair bars
    sig = regime_signal.reindex(pair_bars.index).fillna(False)
    close = pair_bars['close'].to_numpy(dtype=np.float64)
    open_ = pair_bars['open'].to_numpy(dtype=np.float64)
    daily_ret = np.zeros(len(close), dtype=np.float64)
    daily_ret[1:] = np.diff(close) / close[:-1]

    rvol_60 = pd.Series(daily_ret).rolling(60).std(ddof=1).to_numpy()

    n = len(close)
    pos = 0
    entry_idx = -1
    entry_px = 0.0
    size = 0.0
    sig_arr = sig.to_numpy()

    strat_ret = np.zeros(n, dtype=np.float64)
    trades: list[dict] = []
    cost_pct = cost_bps_rt / 10000.0

    for t in range(60, n - 1):
        if pos != 0:
            day_ret = pos * size * (close[t] / close[t - 1] - 1.0)
            strat_ret[t] = day_ret
            hold_days = t - entry_idx
            open_pnl = pos * (close[t] / entry_px - 1.0)

            # Exit conditions
            exit_now = False
            reason = ''
            if not sig_arr[t]:
                exit_now = True; reason = 'regime_off'
            elif open_pnl < adverse_stop_pct:
                exit_now = True; reason = 'adverse_stop'
            elif hold_days >= max_hold_days:
                exit_now = True; reason = 'time_stop'

            if exit_now:
                exit_px = open_[t + 1] if t + 1 < n else close[t]
                strat_ret[t] -= cost_pct
                trades.append({
                    'entry_dt': pair_bars.index[entry_idx],
                    'exit_dt': pair_bars.index[t + 1] if t + 1 < n else pair_bars.index[t],
                    'entry_px': float(entry_px),
                    'exit_px': float(exit_px),
                    'direction': pos,
                    'size': float(size),
                    'pnl_pct': float(pos * size * (exit_px / entry_px - 1.0) - cost_pct),
                    'hold_days': int(hold_days),
                    'reason': reason,
                })
                pos = 0
                entry_idx = -1
                entry_px = 0.0
                size = 0.0
                continue

        # Entry: if flat and regime active
        if pos == 0 and sig_arr[t]:
            v = rvol_60[t - 1]
            if not np.isfinite(v) or v <= 0:
                continue
            daily_vol_ann = v * np.sqrt(DAYS_PER_YEAR)
            size = vol_target_ann / max(daily_vol_ann, 1e-6)
            size = min(size, 5.0)
            pos = direction
            entry_idx = t
            entry_px = float(open_[t + 1]) if t + 1 < n else float(close[t])

    # Close any open position at end
    if pos != 0:
        exit_px = close[-1]
        strat_ret[-1] -= cost_pct
        trades.append({
            'entry_dt': pair_bars.index[entry_idx],
            'exit_dt': pair_bars.index[-1],
            'entry_px': float(entry_px),
            'exit_px': float(exit_px),
            'direction': pos,
            'size': float(size),
            'pnl_pct': float(pos * size * (exit_px / entry_px - 1.0) - cost_pct),
            'hold_days': int(len(pair_bars) - 1 - entry_idx),
            'reason': 'end_of_data',
        })

    return pd.Series(strat_ret, index=pair_bars.index, name='ret'), trades


# --- reporting ------------------------------------------------------------

def report_run(label: str, ret: pd.Series, trades: list[dict]) -> dict:
    r = ret.to_numpy()
    eq = (1.0 + ret).cumprod().to_numpy()
    sh = annual_sharpe(r)
    mdd = max_drawdown(eq)
    n_tr = len(trades)
    wr = sum(1 for t in trades if t['pnl_pct'] > 0) / max(n_tr, 1)
    tot = float(eq[-1] - 1.0) if len(eq) else 0.0
    print(f'  [{label:<32s}]  Sh={sh:+.2f}  total={tot:+.2%}  MDD={mdd*100:+.2f}%  '
          f'trades={n_tr}  WR={wr*100:.1f}%')
    return {'sharpe': sh, 'mdd': mdd, 'trades': n_tr, 'wr': wr, 'total': tot, 'series': ret}


def regime_breakdown(ret: pd.Series, label: str) -> None:
    print(f'\n  Regime breakdown — {label}:')
    windows = [
        ('2018-01-01', '2019-12-31', 'W1 2018-2019'),
        ('2020-02-19', '2020-04-30', '  >> 2020 stress (COVID)'),
        ('2020-01-01', '2020-12-31', 'W2 2020 full'),
        ('2021-01-01', '2021-12-31', 'W3 2021'),
        ('2022-01-01', '2022-12-31', 'W4 2022'),
        ('2023-01-01', '2024-12-31', 'W5 2023-2024'),
        ('2025-01-01', '2026-04-22', 'W6 2025-2026'),
    ]
    for s, e, lbl in windows:
        sub = ret.loc[s:e]
        if len(sub) < 5:
            continue
        sh = annual_sharpe(sub.to_numpy())
        tot = float((1 + sub).cumprod().iloc[-1] - 1)
        active = int((sub != 0).sum())
        print(f'    {lbl:<40s}  Sh={sh:+.2f}  total={tot:+.2%}  active_days={active}')


# --- main -----------------------------------------------------------------

def main() -> int:
    section('Loading data')
    spx = load_pair_d1('SPX500')
    print(f'  SPX500     {len(spx)} bars  {spx.index.min().date()} -> {spx.index.max().date()}')

    pairs_data = {}
    for sym in PAIRS:
        try:
            # AUDJPY and USDJPY have only partial D1 from datalake; force H1 aggregation
            prefer_h1 = sym in ('AUDJPY', 'USDJPY')
            bars = load_pair_d1(sym, prefer_h1=prefer_h1)
            pairs_data[sym] = bars
            print(f'  {sym:8s}  {len(bars)} bars  {bars.index.min().date()} -> {bars.index.max().date()}')
        except Exception as e:
            print(f'  {sym}: SKIP -- {e}')

    if not pairs_data:
        print('No pairs loaded — aborting.')
        return 1

    section('SPX regime signals')
    reg = build_spx_regime(spx)
    for col in reg.columns:
        share = float(reg[col].mean())
        print(f'  {col:<20s}  active {share*100:.1f}% of days')

    # Run baseline (V4 union) on each pair, then portfolio
    section('Baseline — V4 (drawdown OR rvol-spike) trigger, short pair (long JPY)')
    baseline_results = {}
    for sym, bars in pairs_data.items():
        ret, tr = simulate_fx_safe(bars, reg['V4_union_V1_V2'], direction=-1)
        baseline_results[sym] = report_run(f'{sym} V4 short', ret, tr)

    section('Portfolio (equal-weight across pairs) — V4 baseline')
    if baseline_results:
        portfolio = pd.concat([baseline_results[s]['series'].rename(s) for s in baseline_results],
                              axis=1).fillna(0.0).mean(axis=1)
        p_metrics = report_run('PORTFOLIO V4 short', portfolio, [])
        regime_breakdown(portfolio, 'PORTFOLIO V4 short')

    section('Variant sweep — trigger choice (portfolio equal-weight)')
    variant_metrics = {}
    for variant in ('V1_drawdown', 'V2_rvol_spike', 'V3_below_sma', 'V4_union_V1_V2'):
        series_list = []
        all_trades = []
        for sym, bars in pairs_data.items():
            ret, tr = simulate_fx_safe(bars, reg[variant], direction=-1)
            series_list.append(ret)
            all_trades.extend(tr)
        port_ret = pd.concat([s.rename(i) for i, s in enumerate(series_list)],
                             axis=1).fillna(0.0).mean(axis=1)
        m = report_run(f'{variant:<22s}', port_ret, all_trades)
        variant_metrics[variant] = (m, port_ret)

    section('Null check — V4 trigger, LONG pair (short JPY) — must underperform')
    null_series = []
    for sym, bars in pairs_data.items():
        ret, tr = simulate_fx_safe(bars, reg['V4_union_V1_V2'], direction=+1)
        null_series.append(ret)
    null_portfolio = pd.concat([s.rename(i) for i, s in enumerate(null_series)],
                                axis=1).fillna(0.0).mean(axis=1)
    n_metrics = report_run('PORTFOLIO V4 long  (null check)', null_portfolio, [])
    base_sh = variant_metrics['V4_union_V1_V2'][0]['sharpe']
    dir_gap = base_sh - n_metrics['sharpe']
    print(f'\n  direction-gap (short_pair - long_pair) = {dir_gap:+.2f}')
    print(f'    PASS bar: > +0.30')

    section('Cost sensitivity — portfolio V4 short')
    for c in (0.0, 0.5, 1.0, 2.0, 5.0):
        series_list = []
        for sym, bars in pairs_data.items():
            ret, _ = simulate_fx_safe(bars, reg['V4_union_V1_V2'], direction=-1, cost_bps_rt=c)
            series_list.append(ret)
        port_ret = pd.concat([s.rename(i) for i, s in enumerate(series_list)],
                              axis=1).fillna(0.0).mean(axis=1)
        sh = annual_sharpe(port_ret.to_numpy())
        mdd = max_drawdown((1 + port_ret).cumprod().to_numpy())
        print(f'    cost={c:.1f}bp RT  Sharpe={sh:+.2f}  MDD={mdd*100:+.2f}%')

    section('Kill-criteria check (hedge-asset framework)')
    p_metrics, port_ret = variant_metrics['V4_union_V1_V2']
    sub_2020q1 = port_ret.loc['2020-02-19':'2020-04-30']
    sub_2022 = port_ret.loc['2022-01-01':'2022-12-31']
    sub_24_26 = port_ret.loc['2024-01-01':]
    sh_2020 = annual_sharpe(sub_2020q1.to_numpy())
    sh_2022 = annual_sharpe(sub_2022.to_numpy())
    sh_24_26 = annual_sharpe(sub_24_26.to_numpy())

    def check(name: str, val: float, op: str, bar: float, weight: str = '') -> None:
        ok = (val > bar) if op == '>' else (val < bar)
        flag = 'PASS' if ok else 'FAIL'
        print(f'    {flag}  {name:<52s}  {val:+.2f}  {op}  {bar:+.2f}  {weight}')

    check('Full-sample Sharpe > -0.50', p_metrics['sharpe'], '>', -0.50)
    check('MDD > -40%', p_metrics['mdd'], '>', -0.40)
    check('Trades >= 30', float(p_metrics['trades']), '>', 29.0)
    check('2020-Q1 stress Sharpe > +1.5  [LOAD-BEARING]', sh_2020, '>', 1.5, 'LB')
    check('2022 stress Sharpe > 0  (bonus)', sh_2022, '>', 0.0)
    check('Direction null-gap > +0.30', dir_gap, '>', 0.30)
    check('2024-2026 drag Sharpe > -0.50', sh_24_26, '>', -0.50)

    # Cross-variant 2020-Q1 check (must be robust across triggers)
    print('\n  2020-Q1 robustness across trigger variants:')
    for v, (m, pr) in variant_metrics.items():
        sub = pr.loc['2020-02-19':'2020-04-30']
        sh = annual_sharpe(sub.to_numpy())
        print(f'    {v:<22s}  2020-Q1 Sh={sh:+.2f}')

    section('Done — see thesis doc for verdict')
    return 0


if __name__ == '__main__':
    sys.exit(main())
