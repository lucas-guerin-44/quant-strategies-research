#!/usr/bin/env python3
"""Non-Mag7 earnings-gap fade — fresh pre-commit on the 17-name sub-universe of earnings_fade.

Wraps earnings_fade_demo's run_backtest with:
  - universe restricted to 17 non-Mag7 names
  - direction='fade' (the parent's pre-committed direction; survived dir-gap +1.35)
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
sys.path.insert(0, str(_EXPERIMENTS / 'earnings_fade'))

import earnings_fade_demo as efd  # type: ignore

NONMAG7 = [
    'JPM', 'BAC', 'GS',
    'V', 'MA',
    'UNH', 'WMT', 'HD', 'LOW', 'KO', 'PEP', 'JNJ',
    'XOM', 'CVX',
    'ORCL', 'CRM', 'AVGO',
]
efd.UNIVERSE = NONMAG7  # type: ignore[attr-defined]


def section(t: str) -> None:
    print(f'\n{"=" * 80}\n  {t}\n{"=" * 80}\n')


def event_sharpe(pnl: np.ndarray, events_per_year: int = 50) -> float:
    pnl = pnl[np.isfinite(pnl)]
    if pnl.size == 0:
        return 0.0
    std = pnl.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(pnl.mean() / std * np.sqrt(events_per_year))


def report(label: str, ev: pd.DataFrame) -> None:
    if ev.empty:
        print(f'  [{label}] no events'); return
    e = ev.copy()
    e['trade_date'] = pd.to_datetime(e['trade_date'])
    sh = event_sharpe(e['pnl'].to_numpy())
    _, eq = efd.equity_curve_from_events(e)
    mdd = efd.max_drawdown(eq)
    wr = (e['pnl'] > 0).mean()
    gw = float(e.loc[e['pnl'] > 0, 'pnl'].sum())
    gl = float(-e.loc[e['pnl'] <= 0, 'pnl'].sum())
    pf = gw / gl if gl > 0 else float('inf')
    years = (e['trade_date'].max() - e['trade_date'].min()).days / 365.25
    total = float(eq[-1] - 1.0) if eq.size else 0.0
    cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
    print(f'  [{label}]')
    print(f'    period   : {e["trade_date"].min().date()} -> {e["trade_date"].max().date()} ({years:.1f}y)')
    print(f'    Sharpe   : {sh:+.2f}')
    print(f'    Max DD   : {mdd*100:+.2f}%')
    print(f'    events   : {len(e)}  ({len(e)/max(years,1e-9):.1f}/yr)')
    print(f'    CAGR     : {cagr*100:+.2f}%')
    print(f'    WR       : {wr*100:.1f}%   PF: {pf:.2f}')


def kill_check(label: str, ev: pd.DataFrame) -> None:
    sh = event_sharpe(ev['pnl'].to_numpy())
    _, eq = efd.equity_curve_from_events(ev.assign(trade_date=pd.to_datetime(ev['trade_date'])))
    mdd = efd.max_drawdown(eq)
    n = len(ev)
    wr = (ev['pnl'] > 0).mean()
    gw = float(ev.loc[ev['pnl'] > 0, 'pnl'].sum())
    gl = float(-ev.loc[ev['pnl'] <= 0, 'pnl'].sum())
    pf = gw / gl if gl > 0 else float('inf')
    v = lambda ok: 'PASS' if ok else 'FAIL'
    print(f'  [{label}]')
    print(f'    Sharpe > +0.45   : {v(sh > 0.45)}  ({sh:+.2f})')
    print(f'    Max DD < 20%     : {v(abs(mdd) < 0.20)}  ({mdd*100:+.2f}%)')
    print(f'    Events >= 150    : {v(n >= 150)}  ({n})')
    print(f'    WR>=50 or PF>=1.15: {v(wr >= 0.50 or pf >= 1.15)}  (WR {wr*100:.1f}%, PF {pf:.2f})')


def regime_breakdown(ev: pd.DataFrame) -> None:
    e = ev.copy(); e['trade_date'] = pd.to_datetime(e['trade_date'])
    for label, s, ee in [
        ('2018-2020 pre/COVID', '2018-01-01', '2020-12-31'),
        ('2021-2022 vol      ', '2021-01-01', '2022-12-31'),
        ('2023-2026 holdout  ', '2023-01-01', '2026-12-31'),
    ]:
        sub = e[(e['trade_date'] >= pd.Timestamp(s)) & (e['trade_date'] <= pd.Timestamp(ee))]
        if len(sub) < 5:
            print(f'  {label:<22s} n={len(sub):>3d}  (insufficient)'); continue
        sh = event_sharpe(sub['pnl'].to_numpy())
        _, eq = efd.equity_curve_from_events(sub)
        mdd = efd.max_drawdown(eq)
        print(f'  {label:<22s} n={len(sub):>3d}  Sh {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%')


def walk_forward(cache: dict[str, pd.DataFrame]) -> None:
    """3 rolling 3y-IS / 1.5y-OOS splits, similar to earnings_continuation_mag7."""
    splits = [
        ('2021-09-01', '2024-09-01', '2026-05-21'),
        ('2022-09-01', '2025-09-01', '2026-05-21'),
        ('2021-09-01', '2023-09-01', '2025-09-01'),
    ]
    print(f'  {"split":<38s} {"IS Sh":>8s} {"OOS Sh":>8s} {"OOS n":>6s} {"OOS MDD":>10s}')
    oos_sharpes = []
    ev_full = efd.run_backtest(direction='fade', cached_bars=cache)
    ev_full['trade_date'] = pd.to_datetime(ev_full['trade_date'])
    for is_s, is_e, oos_e in splits:
        is_mask = (ev_full['trade_date'] >= pd.Timestamp(is_s)) & (ev_full['trade_date'] < pd.Timestamp(is_e))
        oos_mask = (ev_full['trade_date'] >= pd.Timestamp(is_e)) & (ev_full['trade_date'] <= pd.Timestamp(oos_e))
        is_sh = event_sharpe(ev_full.loc[is_mask, 'pnl'].to_numpy())
        oos_pnl = ev_full.loc[oos_mask, 'pnl'].to_numpy()
        oos_sh = event_sharpe(oos_pnl)
        oos_n = int(oos_pnl.size)
        if oos_n:
            _, eq = efd.equity_curve_from_events(ev_full.loc[oos_mask])
            oos_mdd = efd.max_drawdown(eq) * 100
        else:
            oos_mdd = 0.0
        print(f'  IS {is_s[:7]}->{is_e[:7]} / OOS->{oos_e[:7]} '
              f'{is_sh:>+7.2f}  {oos_sh:>+7.2f}  {oos_n:>6d}  {oos_mdd:>+8.2f}%')
        oos_sharpes.append(oos_sh)
    mean_oos = float(np.mean(oos_sharpes)); min_oos = float(np.min(oos_sharpes))
    print(f'\n  Walk-forward mean OOS Sharpe: {mean_oos:+.2f}  (kill if < +0.30)')
    print(f'  Walk-forward min  OOS Sharpe: {min_oos:+.2f}  (kill if < 0)')
    if mean_oos >= 0.30 and min_oos >= 0:
        print('  -> PASS walk-forward.')
    else:
        print('  -> FAIL walk-forward.')


def main() -> int:
    section('Non-Mag7 earnings-gap FADE — Phase 2 + walk-forward')
    cache: dict[str, pd.DataFrame] = {}

    section('Baseline (fade, MIN_GAP=1.5%, T+60min, stop=1.5x, cost=4bp RT) — 17 non-Mag7')
    ev = efd.run_backtest(direction='fade', cached_bars=cache)
    report('baseline', ev)

    section('Phase 2 kill criteria')
    kill_check('baseline', ev)

    section('Regime breakdown')
    regime_breakdown(ev)

    section('Direction null-check (continuation should LOSE)')
    ev_n = efd.run_backtest(direction='cont', cached_bars=cache)
    report('continuation null', ev_n)
    base_sh = event_sharpe(ev['pnl'].to_numpy())
    null_sh = event_sharpe(ev_n['pnl'].to_numpy())
    gap = base_sh - null_sh
    print(f'\n  Direction-gap (fade - cont) = {gap:+.2f}  (kill if < +0.40)')
    print(f'    -> {"PASS" if gap >= 0.40 else "FAIL"}')

    section('LONG / SHORT split (fade)')
    for d, sub in ev.groupby('direction'):
        sh = event_sharpe(sub['pnl'].to_numpy())
        wr = (sub['pnl'] > 0).mean()
        print(f'  {d:<5s} n={len(sub):>3d}  Sh {sh:>+6.2f}  WR {wr*100:>5.1f}%')

    section('Per-ticker breakdown (full sample)')
    rows = []
    for tk in NONMAG7:
        sub = ev[ev['ticker'] == tk]
        if sub.empty: continue
        sh = event_sharpe(sub['pnl'].to_numpy())
        total = float(sub['pnl'].sum()); wr = (sub['pnl'] > 0).mean()
        rows.append((tk, len(sub), sh, total, wr))
    rows.sort(key=lambda r: -r[3])
    for tk, n, sh, total, wr in rows:
        print(f'  {tk:<6s} n={n:>3d}  Sh {sh:>+6.2f}  total {total*100:>+7.2f}%  WR {wr*100:>5.1f}%')

    section('Variant sweep — MIN_GAP_PCT')
    for g in (0.010, 0.015, 0.020, 0.030, 0.050):
        ev_v = efd.run_backtest(min_gap_pct=g, direction='fade', cached_bars=cache)
        sh = event_sharpe(ev_v['pnl'].to_numpy())
        _, eq = efd.equity_curve_from_events(ev_v.assign(trade_date=pd.to_datetime(ev_v['trade_date'])))
        mdd = efd.max_drawdown(eq) if eq.size else 0.0
        print(f'  min_gap={g*100:>4.1f}%  Sh {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  n {len(ev_v):>3d}')

    section('Variant sweep — TIME_EXIT_MIN')
    for t in (30, 45, 60, 90, 120, 180):
        ev_v = efd.run_backtest(time_exit_min=t, direction='fade', cached_bars=cache)
        sh = event_sharpe(ev_v['pnl'].to_numpy())
        _, eq = efd.equity_curve_from_events(ev_v.assign(trade_date=pd.to_datetime(ev_v['trade_date'])))
        mdd = efd.max_drawdown(eq) if eq.size else 0.0
        print(f'  T+{t:>3d}min  Sh {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  n {len(ev_v):>3d}')

    section('Cost sensitivity')
    for c in (0.0, 2.0, 4.0, 8.0, 15.0):
        ev_v = efd.run_backtest(cost_bps_rt=c, direction='fade', cached_bars=cache)
        sh = event_sharpe(ev_v['pnl'].to_numpy())
        print(f'  cost={c:>5.1f}bp  Sh {sh:>+6.2f}  n {len(ev_v):>3d}')

    section('Phase 6 — walk-forward')
    walk_forward(cache)

    section('Summary')
    sh = event_sharpe(ev['pnl'].to_numpy())
    _, eq = efd.equity_curve_from_events(ev.assign(trade_date=pd.to_datetime(ev['trade_date'])))
    mdd = efd.max_drawdown(eq)
    years = (pd.to_datetime(ev['trade_date'].max()) - pd.to_datetime(ev['trade_date'].min())).days / 365.25
    print(f'  earnings_fade_nonmag7: Sharpe {sh:+.2f}  MDD {mdd*100:+.2f}%  '
          f'n {len(ev)} ({len(ev)/max(years,1e-9):.1f}/yr)  dir-gap {gap:+.2f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
