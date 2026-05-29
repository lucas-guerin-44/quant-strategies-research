#!/usr/bin/env python3
"""Sector-internal relative-strength rotation on the 24-name universe.

Daily-D1 D close-to-close strategy. Rank by trailing-N-day return, long top-K,
short bottom-K, hold HOLD_DAYS, equal-weight basket.
"""
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


UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM', 'BAC', 'GS', 'V', 'MA',
    'UNH', 'WMT', 'HD', 'LOW', 'KO', 'PEP', 'JNJ',
    'XOM', 'CVX', 'ORCL', 'CRM', 'AVGO',
]
TIMEFRAME = 'M5'
START_DATE = '2018-01-01'
END_DATE = '2026-05-21'

LOOKBACK_DAYS = 5
HOLD_DAYS = 5
K = 5
COST_BPS_RT = 4.0


def section(t: str) -> None:
    print(f'\n{"=" * 80}\n  {t}\n{"=" * 80}\n')


def load_m5(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f'No bars for {symbol}')
    df = raw[['timestamp', 'close']].copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.set_index('timestamp').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    return df


def to_daily_close(bars: pd.DataFrame) -> pd.Series:
    idx_date = pd.Series(bars.index.date, index=bars.index)
    df = bars.assign(date=idx_date.values)
    daily = df.groupby('date')['close'].last()
    daily.index = pd.to_datetime(daily.index)
    return daily.sort_index()


def build_close_panel(cache: dict[str, pd.Series] | None = None) -> pd.DataFrame:
    if cache is None:
        cache = {}
    cols = {}
    for tk in UNIVERSE:
        if tk in cache:
            cols[tk] = cache[tk]
            continue
        try:
            bars = load_m5(tk)
            d = to_daily_close(bars)
            cache[tk] = d
            cols[tk] = d
        except RuntimeError:
            continue
    panel = pd.DataFrame(cols).sort_index()
    return panel


def max_drawdown(eq: np.ndarray) -> float:
    if eq.size == 0:
        return 0.0
    rm = np.maximum.accumulate(eq)
    return float(((eq - rm) / rm).min())


def event_sharpe(r: np.ndarray, periods_per_year: int = 252) -> float:
    r = r[np.isfinite(r)]
    if r.size == 0:
        return 0.0
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(periods_per_year))


def simulate(
    panel: pd.DataFrame,
    *,
    lookback: int = LOOKBACK_DAYS,
    hold_days: int = HOLD_DAYS,
    k: int = K,
    cost_bps_rt: float = COST_BPS_RT,
    direction: str = 'long_top_short_bottom',
) -> tuple[pd.Series, dict]:
    """Returns (daily_pnl, stats). Daily PnL is mean(long_basket_daily_ret) - mean(short_basket_daily_ret)."""
    ret_d = panel.pct_change()
    ret_lb = panel.pct_change(lookback)
    daily_pnl = pd.Series(0.0, index=panel.index)

    # Rebalance every hold_days. Determine basket on day t using ret_lb[t-1] (avoid lookahead).
    rebal_dates = panel.index[::hold_days]
    n_rebals = len(rebal_dates)
    if n_rebals < 4:
        return daily_pnl, {'rebalances': n_rebals, 'flips': 0}

    cost_pct = cost_bps_rt / 1e4
    long_basket = []
    short_basket = []
    prev_long = set(); prev_short = set()
    flips = 0
    for i, r_date in enumerate(rebal_dates):
        sig_date = panel.index[panel.index.get_loc(r_date) - 1] if panel.index.get_loc(r_date) > 0 else r_date
        ranks = ret_lb.loc[sig_date].dropna()
        if len(ranks) < k * 2:
            continue
        sorted_tickers = ranks.sort_values(ascending=False).index.tolist()
        if direction == 'long_top_short_bottom':
            long_basket = sorted_tickers[:k]
            short_basket = sorted_tickers[-k:]
        else:  # null: long bottom short top
            long_basket = sorted_tickers[-k:]
            short_basket = sorted_tickers[:k]

        # Apply daily PnL from r_date to next rebal_date.
        end_date = rebal_dates[i + 1] if i + 1 < n_rebals else panel.index[-1]
        sub_dates = panel.loc[r_date:end_date].index[1:]  # skip r_date itself (signal day)
        for d in sub_dates:
            long_ret = ret_d.loc[d, long_basket].mean()
            short_ret = ret_d.loc[d, short_basket].mean()
            day_pnl = (long_ret - short_ret) if np.isfinite(long_ret) and np.isfinite(short_ret) else 0.0
            daily_pnl.loc[d] = day_pnl

        # Apply transaction cost at rebalance (proportional to turnover).
        new_long = set(long_basket); new_short = set(short_basket)
        turnover = (len(new_long.symmetric_difference(prev_long)) + len(new_short.symmetric_difference(prev_short))) / (2 * k)
        if i > 0:
            daily_pnl.loc[r_date] -= cost_pct * turnover
            flips += int(turnover * k)
        prev_long, prev_short = new_long, new_short

    daily_pnl = daily_pnl.fillna(0.0)
    daily_pnl = daily_pnl[daily_pnl.index >= rebal_dates[0]]  # trim warmup
    return daily_pnl, {'rebalances': n_rebals, 'flips': flips}


def report(label: str, pnl: pd.Series) -> None:
    if pnl.empty or pnl.std() == 0:
        print(f'  [{label}] no signal'); return
    pnl = pnl.loc[pnl.index >= pnl.index[pnl.values.nonzero()[0][0]]]  # trim leading zeros
    sh = event_sharpe(pnl.values)
    eq = (1 + pnl.values).cumprod()
    mdd = max_drawdown(eq)
    years = (pnl.index[-1] - pnl.index[0]).days / 365.25
    total = float(eq[-1] - 1.0)
    cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
    n_trade_days = (pnl != 0).sum()
    print(f'  [{label}]')
    print(f'    period   : {pnl.index[0].date()} -> {pnl.index[-1].date()} ({years:.1f}y)')
    print(f'    Sharpe   : {sh:+.2f}')
    print(f'    MDD      : {mdd*100:+.2f}%')
    print(f'    CAGR     : {cagr*100:+.2f}%')
    print(f'    Total    : {total*100:+.1f}%')
    print(f'    trade days: {n_trade_days}  ({n_trade_days/years:.0f}/yr)')


def regime_breakdown(pnl: pd.Series) -> None:
    for label, s, ee in [
        ('2018-2020 pre/COVID', '2018-01-01', '2020-12-31'),
        ('2021-2022 vol      ', '2021-01-01', '2022-12-31'),
        ('2023-2026 holdout  ', '2023-01-01', '2026-12-31'),
    ]:
        sub = pnl[(pnl.index >= pd.Timestamp(s)) & (pnl.index <= pd.Timestamp(ee))]
        if len(sub) < 50:
            print(f'  {label:<22s} n={len(sub):>4d}  (insufficient)'); continue
        sh = event_sharpe(sub.values)
        eq = (1 + sub.values).cumprod()
        mdd = max_drawdown(eq)
        years = (sub.index[-1] - sub.index[0]).days / 365.25
        total = float(eq[-1] - 1.0)
        cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
        print(f'  {label:<22s} n={len(sub):>4d}  Sh {sh:>+6.2f}  CAGR {cagr*100:>+7.2f}%  MDD {mdd*100:>+7.2f}%')


def main() -> int:
    section('Sector-relative-strength rotation — 24-name proof-of-concept')
    cache: dict[str, pd.Series] = {}
    panel = build_close_panel(cache)
    print(f'  Panel shape: {panel.shape[0]} days x {panel.shape[1]} names')
    print(f'  Range: {panel.index[0].date()} -> {panel.index[-1].date()}')

    section('Baseline (lookback=5d, K=5, hold=5d, cost=4bp RT)')
    pnl, stats = simulate(panel)
    report('baseline', pnl)
    print(f'    rebalances: {stats["rebalances"]}  total-flips: {stats["flips"]}')

    section('Regime breakdown — baseline')
    regime_breakdown(pnl)

    section('Direction null-check (long-bottom short-top should LOSE)')
    pnl_n, _ = simulate(panel, direction='other')
    report('null', pnl_n)
    base_sh = event_sharpe(pnl.values); null_sh = event_sharpe(pnl_n.values)
    gap = base_sh - null_sh
    print(f'\n  Direction-gap (top-bottom - bottom-top) = {gap:+.2f}  (kill if < +0.20)')
    print(f'    -> {"PASS" if gap >= 0.20 else "FAIL"}')

    section('Lookback sweep (K=5, hold=5d)')
    print(f'  {"lookback":>8s} {"Sharpe":>8s} {"CAGR":>8s} {"MDD":>8s}')
    for lb in (3, 5, 10, 20, 60, 90):
        pnl_v, _ = simulate(panel, lookback=lb)
        sh = event_sharpe(pnl_v.values)
        eq = (1 + pnl_v.values).cumprod()
        years = (pnl_v.index[-1] - pnl_v.index[0]).days / 365.25
        cagr = ((1 + (eq[-1]-1))**(1/max(years,1e-9))) - 1
        mdd = max_drawdown(eq)
        print(f'  {lb:>8d} {sh:>+8.2f} {cagr*100:>+7.2f}% {mdd*100:>+7.2f}%')

    section('K (basket size) sweep (lookback=5d, hold=5d)')
    print(f'  {"K":>3s} {"Sharpe":>8s} {"CAGR":>8s} {"MDD":>8s}')
    for k in (3, 5, 8, 12):
        pnl_v, _ = simulate(panel, k=k)
        sh = event_sharpe(pnl_v.values)
        eq = (1 + pnl_v.values).cumprod()
        years = (pnl_v.index[-1] - pnl_v.index[0]).days / 365.25
        cagr = ((1 + (eq[-1]-1))**(1/max(years,1e-9))) - 1
        mdd = max_drawdown(eq)
        print(f'  {k:>3d} {sh:>+8.2f} {cagr*100:>+7.2f}% {mdd*100:>+7.2f}%')

    section('Hold-period sweep (lookback=5d, K=5)')
    print(f'  {"hold_d":>7s} {"Sharpe":>8s} {"CAGR":>8s} {"MDD":>8s}')
    for h in (1, 3, 5, 10, 20):
        pnl_v, _ = simulate(panel, hold_days=h)
        sh = event_sharpe(pnl_v.values)
        eq = (1 + pnl_v.values).cumprod()
        years = (pnl_v.index[-1] - pnl_v.index[0]).days / 365.25
        cagr = ((1 + (eq[-1]-1))**(1/max(years,1e-9))) - 1
        mdd = max_drawdown(eq)
        print(f'  {h:>7d} {sh:>+8.2f} {cagr*100:>+7.2f}% {mdd*100:>+7.2f}%')

    section('Cost sensitivity (lookback=5d, K=5, hold=5d)')
    for c in (0.0, 2.0, 4.0, 8.0, 15.0):
        pnl_v, _ = simulate(panel, cost_bps_rt=c)
        sh = event_sharpe(pnl_v.values)
        print(f'  cost={c:>5.1f}bp  Sh {sh:>+6.2f}')

    # 2D grid: lookback × hold
    section('2D heatmap — lookback × hold (Sharpe)')
    lbs = [3, 5, 10, 20, 60]; hs = [1, 3, 5, 10, 20]
    print(f'  {"":>10s} ' + ''.join(f'{"h="+str(h):>10s}' for h in hs))
    for lb in lbs:
        row = []
        for h in hs:
            pnl_v, _ = simulate(panel, lookback=lb, hold_days=h)
            row.append(event_sharpe(pnl_v.values))
        print(f'  {"lb="+str(lb):>10s} ' + ''.join(f'{r:>+9.2f} ' for r in row))

    return 0


if __name__ == '__main__':
    sys.exit(main())
