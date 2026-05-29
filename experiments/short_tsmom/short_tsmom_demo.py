#!/usr/bin/env python3
"""
Short-only TSMOM with V-recovery defense — equity-index bear-hedge.

Thesis: experiments/short_tsmom/short_tsmom.md

Rules (per instrument):
  Entry (must satisfy ALL):
    mom_6m[t]      < 0
    close[t-1]     < SMA_200[t-1]
    DD_52w[t]      < -10%      (close[t-1] / max(close[t-252..t-1]) - 1)
  -> SHORT next-day open, vol-targeted 15% annualized.

  Exit (ANY triggers):
    mom_20d[t]     > 0          (fast V-recovery defense)
    open_pnl       < -10%       (adverse-move stop)
    hold_days     >= 60         (time stop)
  -> Flat at next-day open. 1pt RT cost.

Reports:
  Per-instrument: full-sample Sharpe, MDD, trades, regime breakdown
  Portfolio: equal-weight equity curve
  Stress windows: 2020-Q1, 2022-full
  Null-check: long-only same signal (must underperform)
  Cost sweep: 0.5/1/2/3 pt
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))

from data import fetch_ohlc  # noqa: E402


# --- Config ---------------------------------------------------------------

UNIVERSE = ['SPX500', 'NDX100', 'GER40', 'UK100']
TIMEFRAME = 'D1'
START_DATE = '2018-01-01'
END_DATE = '2026-04-22'

MOM_ENTRY_DAYS = 126        # ~6 months
MOM_EXIT_DAYS = 20          # ~1 month
SMA_DAYS = 200
DD_LOOKBACK = 252           # ~52 weeks
DD_THRESHOLD = -0.10        # -10% drawdown from 52w high gate

VOL_LOOKBACK = 60
VOL_TARGET_ANN = 0.15
MAX_HOLD_DAYS = 60
ADVERSE_STOP_PCT = -0.10

COST_POINTS_RT = 1.0
DAYS_PER_YEAR = 252


# --- Helpers --------------------------------------------------------------

def section(t: str) -> None:
    print(f'\n{"=" * 88}\n  {t}\n{"=" * 88}')


def load_daily(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f'No {TIMEFRAME} bars for {symbol}')
    df = raw[['timestamp', 'open', 'high', 'low', 'close']].copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.set_index('timestamp').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    df.index = df.index.tz_convert('UTC').tz_localize(None).normalize()
    df = df[~df.index.duplicated(keep='first')]
    df = df[df.index.dayofweek < 5]
    return df


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
    dd = (eq - peak) / peak
    return float(dd.min())


# --- Simulator ------------------------------------------------------------

def simulate_short_tsmom(
    bars: pd.DataFrame,
    mom_entry_days: int = MOM_ENTRY_DAYS,
    mom_exit_days: int = MOM_EXIT_DAYS,
    sma_days: int = SMA_DAYS,
    dd_lookback: int = DD_LOOKBACK,
    dd_threshold: float = DD_THRESHOLD,
    vol_lookback: int = VOL_LOOKBACK,
    vol_target_ann: float = VOL_TARGET_ANN,
    max_hold_days: int = MAX_HOLD_DAYS,
    adverse_stop_pct: float = ADVERSE_STOP_PCT,
    cost_points_rt: float = COST_POINTS_RT,
    direction: int = -1,   # -1 = short-only (baseline), +1 = long-only (null-check)
) -> tuple[pd.Series, list[dict]]:
    """Single-instrument short-only TSMOM with V-recovery defense.

    Returns daily-return series (vol-targeted, post-cost) and a list of trade dicts.
    """
    close = bars['close'].to_numpy(dtype=np.float64)
    open_ = bars['open'].to_numpy(dtype=np.float64)
    n = len(close)
    if n < max(mom_entry_days, sma_days, dd_lookback) + 5:
        return pd.Series(dtype=float, index=bars.index, name='ret'), []

    daily_ret = np.zeros(n, dtype=np.float64)
    daily_ret[1:] = np.diff(close) / close[:-1]

    # Pre-compute signals (vectorized, all from PRIOR day close to avoid lookahead).
    sma200 = pd.Series(close).rolling(sma_days).mean().to_numpy()
    rolling_max_52w = pd.Series(close).rolling(dd_lookback).max().to_numpy()
    vol_60 = pd.Series(daily_ret).rolling(vol_lookback).std(ddof=1).to_numpy()  # daily vol

    # All signals indexed by t use values from <= t-1 (no lookahead): we shift below.
    pos = 0          # 0 = flat, -1 = short (baseline), +1 = long (null-check direction param)
    entry_idx = -1
    entry_px = 0.0
    size = 0.0       # position scaling factor (vol-target)

    strat_ret = np.zeros(n, dtype=np.float64)
    trades: list[dict] = []
    start_idx = max(mom_entry_days, sma_days, dd_lookback, vol_lookback) + 2

    for t in range(start_idx, n - 1):
        # Use prior-bar (t-1) signal values
        c_prev = close[t - 1]
        s200 = sma200[t - 1]
        max52 = rolling_max_52w[t - 1]
        vol = vol_60[t - 1]

        if not np.isfinite(s200) or not np.isfinite(max52) or not np.isfinite(vol) or vol <= 0:
            continue

        mom_entry = c_prev / close[t - 1 - mom_entry_days] - 1.0 if (t - 1 - mom_entry_days) >= 0 else np.nan
        mom_exit = c_prev / close[t - 1 - mom_exit_days] - 1.0 if (t - 1 - mom_exit_days) >= 0 else np.nan
        dd52 = c_prev / max52 - 1.0

        # Mark-to-market PnL on existing position (vol-target sized)
        if pos != 0:
            day_ret = pos * size * (close[t] / close[t - 1] - 1.0)
            strat_ret[t] = day_ret

            # Check exit conditions on prior-bar close
            hold_days = t - entry_idx
            open_pnl = pos * (c_prev / entry_px - 1.0)

            exit_triggered = False
            exit_reason = ''
            # For short-only (direction=-1): exit on mom_exit > 0 (rebounding)
            # For long-only null-check (direction=+1): exit on mom_exit < 0
            if direction == -1 and np.isfinite(mom_exit) and mom_exit > 0:
                exit_triggered = True; exit_reason = 'mom_flip'
            elif direction == +1 and np.isfinite(mom_exit) and mom_exit < 0:
                exit_triggered = True; exit_reason = 'mom_flip'
            elif open_pnl < adverse_stop_pct:
                exit_triggered = True; exit_reason = 'adverse_stop'
            elif hold_days >= max_hold_days:
                exit_triggered = True; exit_reason = 'time_stop'

            if exit_triggered:
                exit_px = open_[t + 1] if t + 1 < n else close[t]
                cost_ret = cost_points_rt / entry_px * size  # 2-sided cost charged on exit
                strat_ret[t] -= cost_ret
                trades.append({
                    'entry_dt': bars.index[entry_idx],
                    'exit_dt': bars.index[t + 1] if t + 1 < n else bars.index[t],
                    'entry_px': float(entry_px),
                    'exit_px': float(exit_px),
                    'direction': pos,
                    'size': float(size),
                    'pnl_pct': float(pos * size * (exit_px / entry_px - 1.0) - cost_ret),
                    'hold_days': int(hold_days),
                    'reason': exit_reason,
                })
                pos = 0
                entry_idx = -1
                entry_px = 0.0
                size = 0.0

        # Entry logic (only if flat)
        if pos == 0 and np.isfinite(mom_entry):
            if direction == -1:
                # SHORT entry: mom_6m<0 AND close<SMA200 AND DD<-10%
                want_short = (mom_entry < 0) and (c_prev < s200) and (dd52 < dd_threshold)
                if want_short:
                    pos = -1
                    entry_idx = t
                    entry_px = float(open_[t + 1]) if t + 1 < n else float(close[t])
                    daily_vol_ann = vol * np.sqrt(DAYS_PER_YEAR)
                    size = vol_target_ann / max(daily_vol_ann, 1e-6)
                    size = min(size, 5.0)  # cap leverage
            elif direction == +1:
                # LONG null-check: mom_6m>0 AND close>SMA200 AND drawup > +10%
                drawup = c_prev / pd.Series(close).rolling(dd_lookback).min().iloc[t - 1] - 1.0
                want_long = (mom_entry > 0) and (c_prev > s200) and (drawup > -dd_threshold)
                if want_long:
                    pos = +1
                    entry_idx = t
                    entry_px = float(open_[t + 1]) if t + 1 < n else float(close[t])
                    daily_vol_ann = vol * np.sqrt(DAYS_PER_YEAR)
                    size = vol_target_ann / max(daily_vol_ann, 1e-6)
                    size = min(size, 5.0)

    # Close any open position at end of series
    if pos != 0:
        exit_px = close[-1]
        cost_ret = cost_points_rt / entry_px * size
        strat_ret[-1] -= cost_ret
        trades.append({
            'entry_dt': bars.index[entry_idx],
            'exit_dt': bars.index[-1],
            'entry_px': float(entry_px),
            'exit_px': float(exit_px),
            'direction': pos,
            'size': float(size),
            'pnl_pct': float(pos * size * (exit_px / entry_px - 1.0) - cost_ret),
            'hold_days': int(len(bars) - 1 - entry_idx),
            'reason': 'end_of_data',
        })

    return pd.Series(strat_ret, index=bars.index, name='ret'), trades


# --- Reporting ------------------------------------------------------------

def report_run(label: str, ret: pd.Series, trades: list[dict]) -> dict:
    r = ret.to_numpy()
    eq = (1.0 + ret).cumprod().to_numpy()
    sh = annual_sharpe(r)
    mdd = max_drawdown(eq)
    n_tr = len(trades)
    wins = sum(1 for t in trades if t['pnl_pct'] > 0)
    wr = wins / max(n_tr, 1)
    avg_hold = np.mean([t['hold_days'] for t in trades]) if trades else 0
    total = float(eq[-1] - 1.0) if len(eq) else 0.0
    print(f'  [{label}]  Sharpe={sh:+.2f}  total={total:+.2%}  MDD={mdd*100:+.2f}%  '
          f'trades={n_tr}  WR={wr*100:.1f}%  avg_hold={avg_hold:.0f}d')
    return {'sharpe': sh, 'mdd': mdd, 'trades': n_tr, 'wr': wr, 'total': total,
            'series': ret}


def regime_breakdown(ret: pd.Series, label: str) -> None:
    print(f'\n  Regime breakdown — {label}:')
    windows = [
        ('2018-01-01', '2019-12-31', 'W1 2018-2019'),
        ('2020-01-01', '2020-12-31', 'W2 2020 (COVID)'),
        ('2020-02-19', '2020-04-30', '  >> 2020 stress (COVID crash + recovery)'),
        ('2021-01-01', '2021-12-31', 'W3 2021'),
        ('2022-01-01', '2022-12-31', 'W4 2022 (bear)'),
        ('2023-01-01', '2024-12-31', 'W5 2023-2024'),
        ('2025-01-01', '2026-04-22', 'W6 2025-2026'),
    ]
    for start, end, lbl in windows:
        sub = ret.loc[start:end]
        if len(sub) < 5:
            print(f'    {lbl:<48s}  (insufficient data)')
            continue
        sh = annual_sharpe(sub.to_numpy())
        tot = float((1 + sub).cumprod().iloc[-1] - 1)
        active = int((sub != 0).sum())
        print(f'    {lbl:<48s}  Sh={sh:+.2f}  total={tot:+.2%}  active_days={active}')


def cost_sweep(bars: pd.DataFrame, label: str) -> None:
    print(f'\n  Cost sensitivity — {label}:')
    for c in (0.0, 0.5, 1.0, 2.0, 3.0):
        ret, tr = simulate_short_tsmom(bars, cost_points_rt=c)
        sh = annual_sharpe(ret.to_numpy())
        eq = (1.0 + ret).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        print(f'    cost={c:.1f}pt  Sharpe={sh:+.2f}  MDD={mdd*100:+.2f}%  trades={len(tr)}')


# --- main -----------------------------------------------------------------

def main() -> int:
    section('Loading data')
    instrument_data = {}
    for sym in UNIVERSE:
        try:
            bars = load_daily(sym)
            instrument_data[sym] = bars
            print(f'  {sym:8s}  {len(bars)} bars  '
                  f'{bars.index.min().date()} -> {bars.index.max().date()}')
        except Exception as e:
            print(f'  {sym}: FAILED — {e}')

    section('Baseline — SHORT-only TSMOM with V-recovery defense (per instrument)')
    base_results = {}
    for sym, bars in instrument_data.items():
        ret, tr = simulate_short_tsmom(bars)
        base_results[sym] = report_run(sym, ret, tr)

    # Portfolio: equal-weight across instruments (sum of vol-targeted legs)
    section('Portfolio — equal-weight (sum across instruments)')
    portfolio_ret = sum(base_results[s]['series'] for s in base_results) / len(base_results)
    portfolio_ret = portfolio_ret.dropna()
    p_metrics = report_run('PORTFOLIO', portfolio_ret, sum(
        ([t for t in simulate_short_tsmom(instrument_data[s])[1]] for s in instrument_data), []))

    section('Regime breakdown — portfolio (load-bearing kill criteria are here)')
    regime_breakdown(portfolio_ret, 'PORTFOLIO short-only')

    section('Null-check — LONG-only same signal structure (must underperform)')
    null_results = {}
    for sym, bars in instrument_data.items():
        ret, tr = simulate_short_tsmom(bars, direction=+1)
        null_results[sym] = report_run(f'{sym} long-only', ret, tr)
    null_portfolio = sum(null_results[s]['series'] for s in null_results) / len(null_results)
    null_portfolio = null_portfolio.dropna()
    n_metrics = report_run('PORTFOLIO long-only', null_portfolio, [])
    dir_gap = p_metrics['sharpe'] - n_metrics['sharpe']
    print(f'\n  direction-gap (short - long) = {dir_gap:+.2f}')
    print(f'    PASS bar: > +0.30 (signal has bear-direction content)')

    section('Cost sensitivity — portfolio (per-instrument avg)')
    for sym, bars in instrument_data.items():
        cost_sweep(bars, sym)

    section('Param sensitivity — entry momentum lookback (SPX500)')
    bars_spx = instrument_data.get('SPX500')
    if bars_spx is not None:
        for mom_days in (63, 126, 189, 252):  # 3, 6, 9, 12 months
            ret, tr = simulate_short_tsmom(bars_spx, mom_entry_days=mom_days)
            sh = annual_sharpe(ret.to_numpy())
            mdd = max_drawdown((1.0 + ret).cumprod().to_numpy())
            print(f'    mom_entry={mom_days:>3d}d  Sharpe={sh:+.2f}  MDD={mdd*100:+.2f}%  trades={len(tr)}')

    section('Kill-criteria check (hedge-asset framework)')
    sh = p_metrics['sharpe']
    mdd = p_metrics['mdd']
    n_tr = p_metrics['trades']
    sub_2020q1 = portfolio_ret.loc['2020-02-19':'2020-04-30']
    sub_2022 = portfolio_ret.loc['2022-01-01':'2022-12-31']
    sub_2024_26 = portfolio_ret.loc['2024-01-01':]
    sh_2020 = annual_sharpe(sub_2020q1.to_numpy())
    sh_2022 = annual_sharpe(sub_2022.to_numpy())
    sh_24_26 = annual_sharpe(sub_2024_26.to_numpy())

    def check(name: str, val: float, op: str, bar: float, weight: str = '') -> None:
        if op == '>':
            ok = val > bar
        elif op == '<':
            ok = val < bar
        else:
            ok = False
        flag = 'PASS' if ok else 'FAIL'
        print(f'    {flag}  {name:<48s}  {val:+.2f}  {op}  {bar:+.2f}  {weight}')

    check('Full-sample Sharpe > -0.30', sh, '>', -0.30)
    check('MDD > -40% (less negative)', mdd, '>', -0.40)
    check('Trades >= 50', float(n_tr), '>', 49.0)
    check('2020-Q1 stress Sharpe > +1.0  [LOAD-BEARING]', sh_2020, '>', 1.0, 'LB')
    check('2022 stress Sharpe > +0.5  [LOAD-BEARING]', sh_2022, '>', 0.5, 'LB')
    check('2024-2026 bull-drag Sharpe > -0.50', sh_24_26, '>', -0.50)
    check('Direction null-gap > +0.30', dir_gap, '>', 0.30)

    section('Done — see thesis doc for verdict')
    return 0


if __name__ == '__main__':
    sys.exit(main())
