"""Extended-universe mirror-direction validation (101 names).

Loads extended_universe.txt (101 large-cap tickers), runs same mirror direction simulator
as _mirror_validation.py. Tests whether the +1.09 walk-forward OOS finding is robust
to a 4x larger universe.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# Monkey-patch UNIVERSE before importing the simulator helpers.
import sector_rel_strength_demo as srs  # type: ignore

UNIVERSE_PATH = _HERE / 'extended_universe.txt'
EXTENDED = UNIVERSE_PATH.read_text().strip().split('\n')
srs.UNIVERSE = EXTENDED  # type: ignore[attr-defined]

from sector_rel_strength_demo import (  # type: ignore  # noqa: E402
    build_close_panel, event_sharpe, max_drawdown, simulate,
)


def section(t: str) -> None:
    print(f'\n{"=" * 80}\n  {t}\n{"=" * 80}\n')


def report(label: str, pnl: pd.Series, k: int) -> None:
    if pnl.empty or pnl.std() == 0:
        print(f'  [{label}] no signal'); return
    sh = event_sharpe(pnl.values)
    eq = (1 + pnl.values).cumprod()
    mdd = max_drawdown(eq)
    years = (pnl.index[-1] - pnl.index[0]).days / 365.25
    total = float(eq[-1] - 1.0)
    cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
    print(f'  [{label}]   K={k}')
    print(f'    period   : {pnl.index[0].date()} -> {pnl.index[-1].date()} ({years:.1f}y)')
    print(f'    Sharpe   : {sh:+.2f}')
    print(f'    MDD      : {mdd*100:+.2f}%')
    print(f'    CAGR     : {cagr*100:+.2f}%')
    print(f'    Total    : {total*100:+.1f}%')


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


def walk_forward(panel: pd.DataFrame, lookback: int, hold: int, k: int) -> tuple[float, float]:
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
    print(f'\n  Walk-forward mean OOS Sharpe: {mean_oos:+.2f}  min OOS: {min_oos:+.2f}')
    print(f'  -> {"PASS" if mean_oos >= 0.20 and min_oos >= 0 else "FAIL"}')
    return mean_oos, min_oos


def main() -> int:
    section(f'Extended-universe mirror validation (n={len(EXTENDED)} names)')
    print(f'  Universe: {", ".join(EXTENDED[:8])}, ... {", ".join(EXTENDED[-4:])}')
    cache = {}
    panel = build_close_panel(cache)
    print(f'  Panel shape: {panel.shape[0]} days x {panel.shape[1]} names loaded')

    # K should scale with universe — 5/24 → ~21% concentration; on 101 names use K=20.
    section('Baseline (lb=5, h=5, K=20 — 20% top/bottom concentration)')
    pnl, _ = simulate(panel, lookback=5, hold_days=5, k=20, direction='other')
    report('mirror K=20', pnl, 20)
    regime_breakdown(pnl)

    section('K sweep (lb=5, h=5)')
    print(f'  {"K":>3s} {"Sharpe":>8s} {"CAGR":>8s} {"MDD":>8s}')
    for k in (5, 10, 15, 20, 25, 30, 40):
        pnl_v, _ = simulate(panel, lookback=5, hold_days=5, k=k, direction='other')
        sh = event_sharpe(pnl_v.values)
        eq = (1 + pnl_v.values).cumprod()
        years = (pnl_v.index[-1] - pnl_v.index[0]).days / 365.25
        cagr = ((1 + (eq[-1]-1))**(1/max(years,1e-9))) - 1
        mdd = max_drawdown(eq)
        print(f'  {k:>3d} {sh:>+8.2f} {cagr*100:>+7.2f}% {mdd*100:>+7.2f}%')

    section('Lookback sweep (h=5, K=20)')
    print(f'  {"lookback":>8s} {"Sharpe":>8s} {"CAGR":>8s} {"MDD":>8s}')
    for lb in (3, 5, 10, 20, 60, 90):
        pnl_v, _ = simulate(panel, lookback=lb, hold_days=5, k=20, direction='other')
        sh = event_sharpe(pnl_v.values)
        eq = (1 + pnl_v.values).cumprod()
        years = (pnl_v.index[-1] - pnl_v.index[0]).days / 365.25
        cagr = ((1 + (eq[-1]-1))**(1/max(years,1e-9))) - 1
        mdd = max_drawdown(eq)
        print(f'  {lb:>8d} {sh:>+8.2f} {cagr*100:>+7.2f}% {mdd*100:>+7.2f}%')

    section('Walk-forward — lead cell (lb=5, h=5, K=20)')
    walk_forward(panel, lookback=5, hold=5, k=20)

    section('Walk-forward — alternate cells')
    for lb, h, k in [(3, 5, 20), (10, 5, 20), (5, 5, 15), (5, 5, 25)]:
        print(f'\n  Cell (lb={lb}, h={h}, K={k}):')
        walk_forward(panel, lookback=lb, hold=h, k=k)

    section('Direction null-check — 101-name momentum direction should LOSE')
    pnl_n, _ = simulate(panel, lookback=5, hold_days=5, k=20, direction='long_top_short_bottom')
    report('momentum null', pnl_n, 20)
    mirror_sh = event_sharpe(simulate(panel, lookback=5, hold_days=5, k=20, direction='other')[0].values)
    null_sh = event_sharpe(pnl_n.values)
    print(f'\n  Direction-gap (mirror - momentum) = {mirror_sh - null_sh:+.2f}')

    section('Cost sensitivity (mirror, lb=5, h=5, K=20)')
    for c in (0.0, 2.0, 4.0, 8.0, 15.0):
        pnl_c, _ = simulate(panel, lookback=5, hold_days=5, k=20, cost_bps_rt=c, direction='other')
        sh = event_sharpe(pnl_c.values)
        eq = (1 + pnl_c.values).cumprod()
        years = (pnl_c.index[-1] - pnl_c.index[0]).days / 365.25
        cagr = ((1 + (eq[-1]-1))**(1/max(years,1e-9))) - 1
        print(f'  cost={c:>5.1f}bp  Sh {sh:>+6.2f}  CAGR {cagr*100:>+7.2f}%')

    return 0


if __name__ == '__main__':
    sys.exit(main())
