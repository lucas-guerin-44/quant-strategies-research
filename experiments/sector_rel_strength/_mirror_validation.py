"""Mirror-direction validation — mean-reversion as the live signal.

Tests whether the +0.53 Sharpe mirror finding from baseline survives:
  - Regime breakdown (Phase 4)
  - Walk-forward (Phase 6)
  - Multiple parameter cells (robustness, not curve-fit)
  - Per-ticker contribution (is it driven by 1-2 names?)
  - Sector concentration (is "long-bottom" just "long banks in 2022"?)

Does NOT commit to deploying this. Output informs whether to write a fresh
sector_mean_reversion thesis with proper pre-commits.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from sector_rel_strength_demo import (  # type: ignore
    UNIVERSE, build_close_panel, event_sharpe, max_drawdown, simulate,
)


SECTORS = {
    'tech':     {'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'ORCL', 'CRM', 'AVGO'},
    'fin':      {'JPM', 'BAC', 'GS', 'V', 'MA'},
    'health':   {'UNH', 'JNJ'},
    'staples':  {'KO', 'PEP'},
    'discret':  {'WMT', 'HD', 'LOW'},
    'energy':   {'XOM', 'CVX'},
}
TICKER_TO_SECTOR = {tk: sec for sec, names in SECTORS.items() for tk in names}


def section(t: str) -> None:
    print(f'\n{"=" * 80}\n  {t}\n{"=" * 80}\n')


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


def walk_forward(panel: pd.DataFrame, lookback: int, hold: int, k: int) -> None:
    splits = [
        ('2021-09-01', '2024-09-01', '2026-05-21'),
        ('2022-09-01', '2025-09-01', '2026-05-21'),
        ('2021-09-01', '2023-09-01', '2025-09-01'),
    ]
    print(f'  {"split":<38s} {"IS Sh":>8s} {"OOS Sh":>8s} {"OOS days":>10s} {"OOS MDD":>10s}')
    pnl, _ = simulate(panel, lookback=lookback, hold_days=hold, k=k, direction='other')
    oos_sharpes = []
    for is_s, is_e, oos_e in splits:
        is_mask = (pnl.index >= pd.Timestamp(is_s)) & (pnl.index < pd.Timestamp(is_e))
        oos_mask = (pnl.index >= pd.Timestamp(is_e)) & (pnl.index <= pd.Timestamp(oos_e))
        is_pnl = pnl[is_mask].values
        oos_pnl = pnl[oos_mask].values
        is_sh = event_sharpe(is_pnl) if is_pnl.size else 0.0
        oos_sh = event_sharpe(oos_pnl) if oos_pnl.size else 0.0
        oos_mdd = max_drawdown((1 + oos_pnl).cumprod()) * 100 if oos_pnl.size else 0.0
        print(f'  IS {is_s[:7]}->{is_e[:7]} / OOS->{oos_e[:7]} '
              f'{is_sh:>+7.2f}  {oos_sh:>+7.2f}  {int(oos_mask.sum()):>10d}  {oos_mdd:>+8.2f}%')
        oos_sharpes.append(oos_sh)
    mean_oos = float(np.mean(oos_sharpes)); min_oos = float(np.min(oos_sharpes))
    print(f'\n  Walk-forward mean OOS Sharpe: {mean_oos:+.2f}  (kill if < +0.20)')
    print(f'  Walk-forward min  OOS Sharpe: {min_oos:+.2f}  (kill if < 0)')
    print(f'  -> {"PASS" if mean_oos >= 0.20 and min_oos >= 0 else "FAIL"}')


def per_ticker_contribution(panel: pd.DataFrame, lookback: int, hold: int, k: int) -> None:
    """For each ticker, compute its contribution to the mirror-direction strategy."""
    ret_d = panel.pct_change()
    ret_lb = panel.pct_change(lookback)
    rebal_dates = panel.index[::hold]

    contribution_long = {tk: 0.0 for tk in UNIVERSE}
    contribution_short = {tk: 0.0 for tk in UNIVERSE}
    count_long = {tk: 0 for tk in UNIVERSE}
    count_short = {tk: 0 for tk in UNIVERSE}
    sector_long = {sec: 0 for sec in SECTORS}
    sector_short = {sec: 0 for sec in SECTORS}

    for i, r_date in enumerate(rebal_dates):
        sig_loc = panel.index.get_loc(r_date) - 1
        if sig_loc < 0: continue
        sig_date = panel.index[sig_loc]
        ranks = ret_lb.loc[sig_date].dropna()
        if len(ranks) < k * 2: continue
        sorted_t = ranks.sort_values(ascending=False).index.tolist()
        # Mirror: long-bottom, short-top.
        long_basket = sorted_t[-k:]
        short_basket = sorted_t[:k]
        end_date = rebal_dates[i + 1] if i + 1 < len(rebal_dates) else panel.index[-1]
        sub_dates = panel.loc[r_date:end_date].index[1:]
        for d in sub_dates:
            for tk in long_basket:
                r = ret_d.loc[d, tk]
                if np.isfinite(r):
                    contribution_long[tk] += r
                    count_long[tk] += 1
                    if tk in TICKER_TO_SECTOR:
                        sector_long[TICKER_TO_SECTOR[tk]] += 1
            for tk in short_basket:
                r = ret_d.loc[d, tk]
                if np.isfinite(r):
                    contribution_short[tk] -= r  # short side: -ret
                    count_short[tk] += 1
                    if tk in TICKER_TO_SECTOR:
                        sector_short[TICKER_TO_SECTOR[tk]] += 1

    print(f'\n  Per-ticker contribution (long side: positive = winner on the long-bottom side):')
    print(f'  {"ticker":<6s} {"side":>6s} {"days":>6s} {"contrib":>10s}')
    rows = []
    for tk in UNIVERSE:
        rows.append((tk, 'LONG', count_long[tk], contribution_long[tk]))
        rows.append((tk, 'SHORT', count_short[tk], contribution_short[tk]))
    rows.sort(key=lambda r: -r[3])
    for tk, side, n, c in rows[:30]:
        print(f'  {tk:<6s} {side:>6s} {n:>6d} {c*100:>+8.2f}%')

    print(f'\n  Sector exposure (days-on-side):')
    print(f'  {"sector":<10s} {"LONG":>8s} {"SHORT":>8s} {"net":>8s}')
    for sec in SECTORS:
        ln = sector_long[sec]; sh = sector_short[sec]
        print(f'  {sec:<10s} {ln:>8d} {sh:>8d} {ln - sh:>+8d}')


def main() -> int:
    section('Mirror-direction (mean-reversion) validation')
    cache = {}
    panel = build_close_panel(cache)
    print(f'  Panel: {panel.shape[0]} days x {panel.shape[1]} names')

    # Parameter cells to test (informed by sector_rel_strength heatmap mirror-direction extraction).
    cells = [
        (3, 5, 5), (5, 5, 5), (10, 5, 5),
        (3, 3, 5), (5, 1, 5),
        (5, 5, 3), (5, 5, 8),
    ]
    section('Mirror direction across parameter cells')
    print(f'  {"lookback":>8s} {"hold":>5s} {"K":>3s} {"Sharpe":>8s} {"CAGR":>8s} {"MDD":>8s}')
    for lb, h, k in cells:
        pnl, _ = simulate(panel, lookback=lb, hold_days=h, k=k, direction='other')
        sh = event_sharpe(pnl.values)
        eq = (1 + pnl.values).cumprod()
        years = (pnl.index[-1] - pnl.index[0]).days / 365.25
        cagr = ((1 + (eq[-1]-1))**(1/max(years,1e-9))) - 1
        mdd = max_drawdown(eq)
        print(f'  {lb:>8d} {h:>5d} {k:>3d} {sh:>+8.2f} {cagr*100:>+7.2f}% {mdd*100:>+7.2f}%')

    section('Regime breakdown — lead cell (lb=5, h=5, K=5)')
    pnl, _ = simulate(panel, lookback=5, hold_days=5, k=5, direction='other')
    regime_breakdown(pnl)

    section('Phase 6 — walk-forward (lb=5, h=5, K=5)')
    walk_forward(panel, lookback=5, hold=5, k=5)

    section('Walk-forward — alternate cell (lb=3, h=5, K=5)')
    walk_forward(panel, lookback=3, hold=5, k=5)

    section('Walk-forward — alternate cell (lb=10, h=5, K=5)')
    walk_forward(panel, lookback=10, hold=5, k=5)

    section('Per-ticker + sector concentration check (lb=5, h=5, K=5)')
    per_ticker_contribution(panel, lookback=5, hold=5, k=5)

    section('Cost sensitivity (mirror, lb=5, h=5, K=5)')
    for c in (0.0, 2.0, 4.0, 8.0, 15.0):
        pnl_c, _ = simulate(panel, lookback=5, hold_days=5, k=5, cost_bps_rt=c, direction='other')
        sh = event_sharpe(pnl_c.values)
        eq = (1 + pnl_c.values).cumprod()
        years = (pnl_c.index[-1] - pnl_c.index[0]).days / 365.25
        cagr = ((1 + (eq[-1]-1))**(1/max(years,1e-9))) - 1
        print(f'  cost={c:>5.1f}bp  Sh {sh:>+6.2f}  CAGR {cagr*100:>+7.2f}%')

    return 0


if __name__ == '__main__':
    sys.exit(main())
