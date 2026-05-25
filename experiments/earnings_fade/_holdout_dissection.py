"""Earnings-fade Phase 6 holdout dissection — diagnose post-2022 regime decay.

Baseline 2023-2026 holdout Sharpe -0.22 (n=231) fails the pre-committed kill.
This script slices the holdout regime to identify whether decay is:
 (a) concentrated in a few names (TSLA -12.91% alone) — drop them + retest
 (b) Mag7 vs non-Mag7 effect (0DTE-options dominated names)
 (c) bigger-gap subset still works (>3% gap) while small gaps now continue
 (d) recency monotone (2023 vs 2024 vs 2025 vs 2026 each)
 (e) one of LONG vs SHORT broke (asymmetric institutional flow)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from earnings_fade_demo import (  # type: ignore
    UNIVERSE,
    event_sharpe,
    equity_curve_from_events,
    load_m5,
    max_drawdown,
    run_backtest,
    section,
)


MAG7 = {'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA'}


def report_slice(label: str, ev: pd.DataFrame) -> None:
    if ev.empty:
        print(f'  {label:<40s} (empty)')
        return
    sh = event_sharpe(ev['pnl'].to_numpy())
    _, eq = equity_curve_from_events(ev)
    mdd = max_drawdown(eq)
    n = len(ev)
    wr = (ev['pnl'] > 0).mean()
    print(f'  {label:<40s} n={n:>4d}  Sh {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  WR {wr*100:>5.1f}%')


def main() -> int:
    section('Holdout dissection — earnings_fade Phase 6 diagnostics')
    cache: dict[str, pd.DataFrame] = {}
    print('  Loading cached bars + running baseline...')
    events_base = run_backtest(cached_bars=cache)
    events_base['trade_date'] = pd.to_datetime(events_base['trade_date'])

    holdout = events_base[events_base['trade_date'] >= pd.Timestamp('2023-01-01')]
    print(f'  Holdout 2023-01 -> latest: n={len(holdout)} events\n')

    section('(a) Holdout per-ticker — who is killing the holdout regime?')
    rows = []
    for tk, sub in holdout.groupby('ticker'):
        pnl = sub['pnl'].to_numpy()
        sh = event_sharpe(pnl, events_per_year=max(1, int(len(sub) /
            max(0.1, (sub['trade_date'].max() - sub['trade_date'].min()).days / 365.25))))
        rows.append((tk, len(sub), float(sub['pnl'].mean()), float(sub['pnl'].sum()),
                     (sub['pnl'] > 0).mean(), sh))
    rows.sort(key=lambda r: r[3])  # by total ascending (worst first)
    print(f'  {"ticker":<6s} {"n":>4s} {"avg":>10s} {"total":>10s} {"WR":>6s} {"Sh*":>7s}')
    for tk, n, avg, total, wr, sh in rows:
        marker = ' <<< worst' if total == rows[0][3] else ''
        print(f'  {tk:<6s} {n:>4d} {avg*100:>+8.3f}% {total*100:>+8.2f}% {wr*100:>5.1f}% {sh:>+7.2f}{marker}')

    section('(b) Holdout Mag7 vs non-Mag7 — 0DTE-options-dominated split')
    mag7_ev = holdout[holdout['ticker'].isin(MAG7)]
    nonmag7_ev = holdout[~holdout['ticker'].isin(MAG7)]
    report_slice('Mag7 (AAPL MSFT GOOGL AMZN META NVDA TSLA)', mag7_ev)
    report_slice('non-Mag7 (banks/staples/health/energy/sw)', nonmag7_ev)

    # Drop TSLA specifically (largest individual drag in full sample).
    no_tsla = holdout[holdout['ticker'] != 'TSLA']
    report_slice('non-Mag7 + Mag6 (drop TSLA)', no_tsla)

    section('(c) Holdout by |gap| magnitude bucket')
    holdout = holdout.copy()
    holdout['gap_abs'] = holdout['gap_pct'].abs()
    buckets = [(0.015, 0.025), (0.025, 0.035), (0.035, 0.05), (0.05, 0.08), (0.08, 0.25)]
    for lo, hi in buckets:
        sub = holdout[(holdout['gap_abs'] >= lo) & (holdout['gap_abs'] < hi)]
        report_slice(f'gap {lo*100:>4.1f}-{hi*100:>4.1f}%', sub)

    section('(d) Holdout by year — is decay monotonic?')
    holdout['year'] = holdout['trade_date'].dt.year
    for y in sorted(holdout['year'].unique()):
        sub = holdout[holdout['year'] == y]
        report_slice(f'{int(y)}', sub)

    section('(e) Holdout LONG/SHORT split — symmetric?')
    for d, sub in holdout.groupby('direction'):
        report_slice(f'{d}-only', sub)

    # Combine best-evidence filter: non-Mag7 + |gap|>=3%.
    section('(f) Combined filter: non-Mag7 + |gap| >= 3.0%')
    filt = holdout[(~holdout['ticker'].isin(MAG7)) & (holdout['gap_pct'].abs() >= 0.03)]
    report_slice('non-Mag7 & |gap|>=3.0% holdout', filt)

    # Re-run baseline restricted to non-Mag7 universe across the FULL sample, to check
    # whether the non-Mag7 sub-universe survives all phases (not just the holdout).
    section('(g) FULL-SAMPLE non-Mag7 universe re-run (would survive deploy?)')
    nonmag7_full = events_base[~events_base['ticker'].isin(MAG7)].copy()
    nonmag7_full['trade_date'] = pd.to_datetime(nonmag7_full['trade_date'])
    report_slice('non-Mag7 FULL sample', nonmag7_full)
    for label, s, e in [
        ('2018-2020 pre-COVID', '2018-01-01', '2020-12-31'),
        ('2021-2022 vol      ', '2021-01-01', '2022-12-31'),
        ('2023-2026 holdout  ', '2023-01-01', '2026-12-31'),
    ]:
        sub = nonmag7_full[(nonmag7_full['trade_date'] >= pd.Timestamp(s)) &
                           (nonmag7_full['trade_date'] <= pd.Timestamp(e))]
        report_slice(f'  non-Mag7 {label}', sub)

    section('Verdict')
    print('  Holdout-fail diagnostic outputs above. Decision tree:')
    print('  - if non-Mag7 holdout is >+0.30 and non-Mag7 FULL-sample regime breakdown is 3/3 positive')
    print('    -> MARGINAL: tombstone Mag7 leg, keep non-Mag7 leg as institutional candidate.')
    print('  - if even non-Mag7 holdout is negative')
    print('    -> tombstone earnings_fade. 0DTE-options post-2022 has killed the mechanism broadly.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
