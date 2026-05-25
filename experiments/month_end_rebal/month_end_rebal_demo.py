#!/usr/bin/env python3
"""Month-End 60/40 Rebalancing Flow — SPX500 daily-bar.

Thesis: experiments/month_end_rebal/month_end_rebal.md

Mechanism: enter SPX N business days before month-end close in the direction
opposite to the prior-21d SPX-vs-TLT return spread (over-equity months → short
SPX; under-equity months → long SPX). Exit at month-end close.

Run:
    venv/Scripts/python.exe experiments/month_end_rebal/month_end_rebal_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT.parent / 'backtesting-engine-2.0'))

from utils import fetch_ohlc  # noqa: E402


# ---------------------------------------------------------------------------
# Config (pre-committed baseline)
# ---------------------------------------------------------------------------

TIMEFRAME = 'D1'
START_DATE = '2015-01-01'
END_DATE   = '2026-05-25'

ENTRY_DAYS_BEFORE_EOM = 5
SPREAD_LOOKBACK_DAYS  = 21
SPREAD_THRESHOLD_PCT  = 2.0
COST_BPS_RT           = 5.0     # 5 bps round-trip on SPX500 CFD


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f'\n{"=" * 78}\n  {t}\n{"=" * 78}')


def load_d1(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    df = raw[['timestamp', 'open', 'high', 'low', 'close']].copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.set_index('timestamp').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    df.index = pd.DatetimeIndex(df.index.date)
    return df


# ---------------------------------------------------------------------------
# Simulator (numpy inner loop)
# ---------------------------------------------------------------------------

def find_eom_indices(dates: np.ndarray) -> np.ndarray:
    """Indices of the LAST trading day of each calendar month."""
    months = pd.DatetimeIndex(dates).month.to_numpy()
    next_month = np.roll(months, -1)
    next_month[-1] = -1   # final bar always counts as EOM
    return np.where(months != next_month)[0]


def simulate(
    spx_close: np.ndarray,
    tlt_close: np.ndarray,
    dates: np.ndarray,
    entry_days: int,
    lookback: int,
    spread_threshold_pct: float,
    cost_bps_rt: float,
    *,
    invert: bool = False,
    placebo: bool = False,
) -> tuple[np.ndarray, list[dict]]:
    """Returns (per-trade pct returns net of cost, list of trade dicts).

    invert=True flips entry direction (null check).
    placebo=True re-anchors entry/exit to mid-month windows (entry = EOM-15,
                 exit = EOM-10) keeping the same conditioning logic.
    """
    eom_idx = find_eom_indices(dates)
    cost = cost_bps_rt / 10000.0
    trades: list[dict] = []
    rets: list[float] = []

    for em in eom_idx:
        if placebo:
            exit_i = em - 10
            entry_i = em - 15
        else:
            exit_i = em
            entry_i = em - entry_days

        spread_end = entry_i        # spread measured up to (and excluding) entry
        spread_start = spread_end - lookback
        if spread_start < 0 or entry_i < 0 or exit_i <= entry_i:
            continue

        # 21-day cumulative return spread, in percent.
        spx_ret = (spx_close[spread_end] / spx_close[spread_start] - 1.0) * 100.0
        tlt_ret = (tlt_close[spread_end] / tlt_close[spread_start] - 1.0) * 100.0
        spread = spx_ret - tlt_ret

        if abs(spread) < spread_threshold_pct:
            continue

        # Default: spread > 0 → SHORT SPX (rebalancers sell equities).
        direction = -1 if spread > 0 else +1
        if invert:
            direction = -direction

        gross = direction * (spx_close[exit_i] / spx_close[entry_i] - 1.0)
        net = gross - cost
        rets.append(net)
        trades.append({
            'entry_date': dates[entry_i],
            'exit_date': dates[exit_i],
            'spread_pct': float(spread),
            'direction': int(direction),
            'ret_net': float(net),
        })

    return np.asarray(rets, dtype=float), trades


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report(rets: np.ndarray, label: str, trades_per_year: float = 12.0) -> dict:
    if len(rets) == 0:
        print(f'  {label:<32s}  (no trades)')
        return {}
    n = len(rets)
    mean = rets.mean()
    std = rets.std(ddof=1) if n > 1 else np.nan
    sharpe = (mean / std) * np.sqrt(trades_per_year) if std and std > 0 else np.nan
    eq = np.cumsum(rets)
    peak = np.maximum.accumulate(eq)
    mdd = float((eq - peak).min())
    wins = float((rets > 0).sum())
    wr = wins / n * 100.0
    gross_wins = rets[rets > 0].sum()
    gross_losses = -rets[rets < 0].sum()
    pf = (gross_wins / gross_losses) if gross_losses > 0 else np.inf
    t_stat = (mean / (std / np.sqrt(n))) if std and std > 0 else np.nan
    print(
        f'  {label:<32s}  n={n:4d}  mean={mean*100:+.3f}%  '
        f'Sh={sharpe:+.2f}  MDD={mdd*100:+.1f}%  WR={wr:4.1f}%  PF={pf:.2f}  '
        f't={t_stat:+.2f}'
    )
    return {
        'n': n, 'mean': mean, 'sharpe': sharpe, 'mdd': mdd,
        'wr': wr, 'pf': pf, 't': t_stat,
    }


def regime_breakdown(trades: list[dict]) -> None:
    if not trades:
        return
    df = pd.DataFrame(trades)
    df['exit_date'] = pd.to_datetime(df['exit_date'])
    df = df.set_index('exit_date').sort_index()
    windows = [
        ('W1 2019-2020', '2019-01-01', '2020-12-31'),
        ('W2 2021-2022', '2021-01-01', '2022-12-31'),
        ('W3 2023-2026', '2023-01-01', '2026-12-31'),
    ]
    print('  Regime breakdown:')
    for name, lo, hi in windows:
        sub = df.loc[lo:hi]
        rets = sub['ret_net'].to_numpy()
        report(rets, f'    {name}')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    section('Loading SPX500 + TLT daily bars')
    spx = load_d1('SPX500')
    tlt = load_d1('TLT')
    # Align.
    joined = spx[['close']].join(tlt[['close']], how='inner', lsuffix='_spx', rsuffix='_tlt')
    joined = joined.dropna()
    print(f'  SPX bars: {len(spx)}    TLT bars: {len(tlt)}    aligned: {len(joined)}')
    print(f'  Range: {joined.index.min()} -> {joined.index.max()}')

    spx_close = joined['close_spx'].to_numpy(dtype=float)
    tlt_close = joined['close_tlt'].to_numpy(dtype=float)
    dates = joined.index.to_numpy()

    # -----------------------------------------------------------------
    section('BASELINE — 5d entry, 2.0% spread, 5bp RT, SPX500 vs TLT')
    rets, trades = simulate(
        spx_close, tlt_close, dates,
        ENTRY_DAYS_BEFORE_EOM, SPREAD_LOOKBACK_DAYS,
        SPREAD_THRESHOLD_PCT, COST_BPS_RT,
    )
    baseline_stats = report(rets, 'baseline')
    regime_breakdown(trades)

    # -----------------------------------------------------------------
    section('NULL CHECK — invert direction')
    rets_inv, _ = simulate(
        spx_close, tlt_close, dates,
        ENTRY_DAYS_BEFORE_EOM, SPREAD_LOOKBACK_DAYS,
        SPREAD_THRESHOLD_PCT, COST_BPS_RT,
        invert=True,
    )
    inv_stats = report(rets_inv, 'inverted-direction')
    if baseline_stats and inv_stats:
        gap = baseline_stats['sharpe'] - inv_stats['sharpe']
        print(f'  >>> Direction null-gap: {gap:+.2f} Sharpe   '
              f'(threshold ≥ +0.30 → {"PASS" if gap >= 0.30 else "FAIL"})')

    # -----------------------------------------------------------------
    section('PLACEBO -- mid-month re-anchor (EOM-15 -> EOM-10)')
    rets_pl, _ = simulate(
        spx_close, tlt_close, dates,
        ENTRY_DAYS_BEFORE_EOM, SPREAD_LOOKBACK_DAYS,
        SPREAD_THRESHOLD_PCT, COST_BPS_RT,
        placebo=True,
    )
    pl_stats = report(rets_pl, 'mid-month placebo')
    if pl_stats:
        pl_ok = (abs(pl_stats['mean']) < 0.001) or (abs(pl_stats['t']) < 1.5)
        print(f'  >>> Placebo benign? {"YES" if pl_ok else "NO"}  '
              f'(mean={pl_stats["mean"]*100:+.3f}%, |t|={abs(pl_stats["t"]):.2f})')

    # -----------------------------------------------------------------
    section('ENTRY-DAYS SWEEP — 3 / 5 / 7 / 10')
    for ed in (3, 5, 7, 10):
        rets, _ = simulate(
            spx_close, tlt_close, dates,
            ed, SPREAD_LOOKBACK_DAYS, SPREAD_THRESHOLD_PCT, COST_BPS_RT,
        )
        report(rets, f'entry_days={ed}')

    # -----------------------------------------------------------------
    section('SPREAD-THRESHOLD SWEEP — 0 / 1 / 2 / 3 / 5 %')
    for th in (0.0, 1.0, 2.0, 3.0, 5.0):
        rets, _ = simulate(
            spx_close, tlt_close, dates,
            ENTRY_DAYS_BEFORE_EOM, SPREAD_LOOKBACK_DAYS,
            th, COST_BPS_RT,
        )
        report(rets, f'threshold={th:.1f}%')

    # -----------------------------------------------------------------
    section('COST SWEEP — 0 / 5 / 10 / 20 bp RT')
    for c in (0.0, 5.0, 10.0, 20.0):
        rets, _ = simulate(
            spx_close, tlt_close, dates,
            ENTRY_DAYS_BEFORE_EOM, SPREAD_LOOKBACK_DAYS,
            SPREAD_THRESHOLD_PCT, c,
        )
        report(rets, f'cost={c:.0f}bp')

    # -----------------------------------------------------------------
    section('BOND-PROXY ROBUSTNESS — IEF (7-10y) instead of TLT')
    try:
        ief = load_d1('IEF')
        joined2 = spx[['close']].join(ief[['close']], how='inner',
                                       lsuffix='_spx', rsuffix='_ief').dropna()
        spx_close2 = joined2['close_spx'].to_numpy(dtype=float)
        ief_close = joined2['close_ief'].to_numpy(dtype=float)
        dates2 = joined2.index.to_numpy()
        rets, _ = simulate(
            spx_close2, ief_close, dates2,
            ENTRY_DAYS_BEFORE_EOM, SPREAD_LOOKBACK_DAYS,
            SPREAD_THRESHOLD_PCT, COST_BPS_RT,
        )
        report(rets, 'SPX-IEF baseline')
    except Exception as e:
        print(f'  IEF load failed: {e}')

    # -----------------------------------------------------------------
    section('KILL-CRITERIA CHECK (baseline)')
    if baseline_stats:
        b = baseline_stats
        checks = [
            ('Sharpe ≥ +0.30',     b['sharpe'] >= 0.30,       f'{b["sharpe"]:+.2f}'),
            ('Mean ≥ +0.10%',      b['mean']*100 >= 0.10,     f'{b["mean"]*100:+.3f}%'),
            ('MDD > -25%',         b['mdd']*100 > -25.0,      f'{b["mdd"]*100:+.1f}%'),
            ('Trades ≥ 60',        b['n'] >= 60,              f'{b["n"]}'),
        ]
        for label, ok, val in checks:
            print(f'  [{"PASS" if ok else "FAIL"}]  {label:<24s}  actual={val}')


if __name__ == '__main__':
    main()
