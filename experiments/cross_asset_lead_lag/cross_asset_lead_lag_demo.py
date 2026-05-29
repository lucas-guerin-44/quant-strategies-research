#!/usr/bin/env python3
"""Cross-asset M5 lead-lag — Phase 0 correlation hunt + Phase 2 strategy on top pairs."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_EXPERIMENTS = _HERE.parent
_ROOT = _EXPERIMENTS.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT.parent / 'backtesting-engine-2.0'))

from data import fetch_ohlc  # noqa: E402


LEADERS = ['USOUSD', 'NDX100', 'SPX500', 'GER40', 'BTCUSD']
FOLLOWERS_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM', 'BAC', 'GS', 'V', 'MA',
    'UNH', 'WMT', 'HD', 'LOW', 'KO', 'PEP', 'JNJ',
    'XOM', 'CVX', 'ORCL', 'CRM', 'AVGO',
]
LAGS = [-3, -2, -1, 0, 1, 2, 3, 5, 10, 20]

TIMEFRAME = 'M5'
START_DATE = '2021-09-01'  # post-data-start for stocks
END_DATE = '2026-05-21'


def section(t: str) -> None:
    print(f'\n{"=" * 80}\n  {t}\n{"=" * 80}\n')


def load_m5_close(symbol: str) -> pd.Series:
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f'No bars for {symbol}')
    df = raw[['timestamp', 'close']].copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.set_index('timestamp').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    return df['close']


def event_sharpe(r: np.ndarray, periods_per_year: int = 252 * 78) -> float:
    """For M5 bars, ~78 bars/day for US RTH."""
    r = r[np.isfinite(r)]
    if r.size == 0:
        return 0.0
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(periods_per_year))


def max_drawdown(eq: np.ndarray) -> float:
    if eq.size == 0:
        return 0.0
    rm = np.maximum.accumulate(eq)
    return float(((eq - rm) / rm).min())


def phase0_corr_hunt() -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """For each leader and each follower, compute corr(L[t-lag], F[t]) for lags in LAGS."""
    cache: dict[str, pd.Series] = {}
    for sym in LEADERS + FOLLOWERS_STOCKS:
        try:
            cache[sym] = load_m5_close(sym).pct_change()
        except RuntimeError as e:
            print(f'  WARN: {sym}: {e}')

    rows = []
    for leader in LEADERS:
        if leader not in cache:
            continue
        lret = cache[leader]
        for follower in FOLLOWERS_STOCKS + [l for l in LEADERS if l != leader]:
            if follower not in cache:
                continue
            fret = cache[follower]
            common = lret.dropna().index.intersection(fret.dropna().index)
            if len(common) < 5000:
                continue
            l = lret.loc[common]
            f = fret.loc[common]
            for lag in LAGS:
                if lag >= 0:
                    l_shift = l.shift(lag)
                else:
                    l_shift = l.shift(lag)
                cor = l_shift.corr(f)
                if not np.isfinite(cor):
                    continue
                rows.append({'leader': leader, 'follower': follower, 'lag': lag, 'corr': cor, 'n': len(common)})
    corr_df = pd.DataFrame(rows)
    return corr_df, cache


def report_top_correlations(corr_df: pd.DataFrame) -> list[tuple[str, str, int]]:
    """Returns top (leader, follower, best_lag) tuples."""
    # Focus on lag > 0 (genuine lead from leader to follower).
    lead = corr_df[corr_df['lag'].isin([1, 2, 3, 5])].copy()
    lag = corr_df[corr_df['lag'].isin([-1, -2, -3])].copy()
    if lead.empty:
        return []

    # Pivot to compare same-pair lead vs lag.
    lead['abs_corr'] = lead['corr'].abs()
    sorted_lead = lead.sort_values('abs_corr', ascending=False).head(30)

    # Asymmetry: for each (leader, follower), strongest forward-lag corr vs strongest reverse-lag corr.
    asymm_rows = []
    for (ld, fl), group in corr_df.groupby(['leader', 'follower']):
        if group.empty:
            continue
        pos_lags = group[group['lag'] > 0]
        neg_lags = group[group['lag'] < 0]
        if pos_lags.empty or neg_lags.empty:
            continue
        best_pos_idx = pos_lags['corr'].abs().idxmax()
        best_neg_idx = neg_lags['corr'].abs().idxmax()
        best_pos = pos_lags.loc[best_pos_idx]
        best_neg = neg_lags.loc[best_neg_idx]
        asymm = abs(best_pos['corr']) - abs(best_neg['corr'])
        asymm_rows.append({
            'leader': ld, 'follower': fl,
            'best_pos_lag': int(best_pos['lag']), 'pos_corr': best_pos['corr'],
            'best_neg_lag': int(best_neg['lag']), 'neg_corr': best_neg['corr'],
            'asymm': asymm,
            'n': int(best_pos['n']),
        })
    asymm_df = pd.DataFrame(asymm_rows).sort_values('asymm', ascending=False)

    print(f'\n  Top 20 lead-lag pairs by asymmetry (|forward| - |reverse|):')
    print(f'  {"leader":<8s} {"follower":<8s} {"+lag":>5s} {"+corr":>8s} {"-lag":>5s} {"-corr":>8s} {"asymm":>8s} {"n":>8s}')
    top_pairs: list[tuple[str, str, int]] = []
    for _, r in asymm_df.head(20).iterrows():
        marker = ''
        if abs(r['pos_corr']) > 0.10 and r['asymm'] > 0.02:
            marker = '  *'
            top_pairs.append((r['leader'], r['follower'], int(r['best_pos_lag'])))
        print(f'  {r["leader"]:<8s} {r["follower"]:<8s} {int(r["best_pos_lag"]):>5d} {r["pos_corr"]:>+8.4f} '
              f'{int(r["best_neg_lag"]):>5d} {r["neg_corr"]:>+8.4f} {r["asymm"]:>+8.4f} {int(r["n"]):>8d}{marker}')
    return top_pairs[:5]


def phase2_strategy(leader: str, follower: str, lag: int, cache: dict[str, pd.Series]) -> None:
    """Trade follower based on leader's previous-N-bar return."""
    if leader not in cache or follower not in cache:
        print(f'  ({leader},{follower}) cache miss')
        return
    lret = cache[leader].dropna()
    fret = cache[follower].dropna()
    common = lret.index.intersection(fret.index)
    if len(common) < 5000:
        print(f'  ({leader},{follower}) n={len(common)} insufficient')
        return
    l = lret.loc[common]
    f = fret.loc[common]
    # Sum leader returns over the previous 6 M5 bars (30 min); enter follower if magnitude > threshold.
    leader_30min = l.rolling(6).sum().shift(lag)  # value at index t = sum of last 6 bars at t-lag
    # Threshold: 0.5 × leader 30-min realized vol (expanding window).
    thr = leader_30min.expanding(min_periods=500).std() * 0.5
    signal = leader_30min.where(leader_30min.abs() > thr, 0.0)
    pos = np.sign(signal).fillna(0.0)
    # Hold for HOLD_BARS = 6 bars (30 min) — enter at t, exit at t+6.
    hold_bars = 6
    # PnL: follower return over next HOLD_BARS bars, position-direction.
    f_future = f.rolling(hold_bars).sum().shift(-hold_bars)  # cumulative return t to t+hold_bars
    # Cost: 4 bp RT per trade
    cost_pct = 4.0 / 1e4
    trade_pnl_series = pos * f_future - cost_pct * (pos.abs())
    trade_pnl_series = trade_pnl_series.dropna()
    # Filter to actual trade events.
    events = trade_pnl_series[pos.abs() > 0]
    if len(events) < 50:
        print(f'  ({leader},{follower}) trades n={len(events)} insufficient')
        return
    # Approximate trade-per-year cadence using bars-per-year.
    bars_per_year = 252 * 78
    # Sharpe annualized treating each EVENT as independent (some over-count due to overlapping holds).
    sh = float(events.mean() / events.std(ddof=1) * np.sqrt(bars_per_year / hold_bars))
    eq = (1 + events.values).cumprod()
    mdd = max_drawdown(eq)
    total = float(eq[-1] - 1.0)
    years = (events.index[-1] - events.index[0]).days / 365.25
    cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
    wr = (events > 0).mean()
    print(f'  ({leader} -> {follower}, lag={lag})')
    print(f'    trades   : {len(events)}  ({len(events)/years:.0f}/yr)')
    print(f'    Sharpe   : {sh:+.2f}')
    print(f'    MDD      : {mdd*100:+.2f}%')
    print(f'    CAGR     : {cagr*100:+.2f}%')
    print(f'    Total    : {total*100:+.1f}%')
    print(f'    WR       : {wr*100:.1f}%')

    # Direction null
    pos_n = -pos
    null_pnl = pos_n * f_future - cost_pct * (pos_n.abs())
    null_events = null_pnl.dropna()[pos_n.abs() > 0]
    if len(null_events) > 50:
        null_sh = float(null_events.mean() / null_events.std(ddof=1) * np.sqrt(bars_per_year / hold_bars))
        print(f'    null Sh  : {null_sh:+.2f}  (dir-gap {sh - null_sh:+.2f})')


def main() -> int:
    section('Cross-asset M5 lead-lag — Phase 0 correlation hunt')
    corr_df, cache = phase0_corr_hunt()
    print(f'  Computed {len(corr_df)} (pair, lag) correlations')
    top_pairs = report_top_correlations(corr_df)

    if not top_pairs:
        print('\n  Phase 0 finds no pair with |corr|>0.10 + asymmetry > 0.02. STOP.')
        return 0

    section(f'Phase 2 — strategy on top {len(top_pairs)} pairs')
    for ld, fl, lag in top_pairs:
        phase2_strategy(ld, fl, lag, cache)

    section('Same pairs at lag=1 (forced)')
    for ld, fl, _ in top_pairs:
        phase2_strategy(ld, fl, 1, cache)

    return 0


if __name__ == '__main__':
    sys.exit(main())
