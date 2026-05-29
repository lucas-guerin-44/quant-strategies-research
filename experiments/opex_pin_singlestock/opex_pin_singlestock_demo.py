#!/usr/bin/env python3
"""Single-stock OPEX pin (round-strike proxy) on 15-name M5 basket.

Thesis: experiments/opex_pin_singlestock/opex_pin_singlestock.md

Mechanism (per Ni-Pearson-Poteshman 2005): single-stock prices on monthly
OPEX Fridays cluster to round-number strikes at the cash close, driven by
dealer net-short-gamma hedging. Without options OI feed, use round-strike
proxy: at 11:30 ET (AM reference), identify nearest round strike; if spot
is sufficiently far away (clears MIN_DIST), fade toward strike, exit at
15:55 ET.

Bars are broker-server-time labelled as UTC; for US RTH-only feeds the
broker streams during NYSE hours so each calendar date in UTC labels =
one NYSE session (per earnings_fade convention).

Run:
    venv/Scripts/python.exe experiments/opex_pin_singlestock/opex_pin_singlestock_demo.py
"""
from __future__ import annotations

import os
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


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

UNIVERSE = [
    'LULU', 'COIN', 'MSTR', 'NFLX', 'SHOP', 'CRWD', 'NET',
    'AVGO', 'ASML', 'MU', 'ROKU', 'DOCU', 'PLTR', 'SNOW', 'NOW',
]

TIMEFRAME = 'M5'
START_DATE = '2019-01-01'
END_DATE = '2026-05-24'

# Baseline parameters (pre-committed).
MORNING_END_MIN = 120          # bar index from session-open: 24 bars in = ~2hrs after open
AFTERNOON_END_MIN = 385        # ~6.4hrs in (15:55 ET assuming 9:30 ET open)
MIN_DIST_FROM_PIN_PCT = 0.50   # require spot ≥ 0.5% away from nearest strike
MAX_DIST_FROM_PIN_PCT = 3.00   # if too far, abort
COST_BPS_RT = 15.0
EVENTS_PER_YEAR = 100          # per-event Sharpe annualization (basket)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f'\n{"=" * 80}\n  {t}\n{"=" * 80}\n')


def load_m5(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f'No bars for {symbol} {TIMEFRAME}')
    df = raw[['timestamp', 'open', 'high', 'low', 'close']].copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.set_index('timestamp').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    return df


def max_drawdown(eq: np.ndarray) -> float:
    if eq.size == 0:
        return 0.0
    rm = np.maximum.accumulate(eq)
    dd = (eq - rm) / rm
    return float(dd.min())


def event_sharpe(pnl: np.ndarray, events_per_year: int = EVENTS_PER_YEAR) -> float:
    pnl = pnl[np.isfinite(pnl)]
    if pnl.size == 0:
        return 0.0
    std = pnl.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(pnl.mean() / std * np.sqrt(events_per_year))


def round_strike(px: float) -> float:
    """Nearest round-number strike based on price band."""
    if px < 50:
        grid = 1.0
    elif px < 200:
        grid = 5.0
    elif px < 500:
        grid = 10.0
    else:
        grid = 25.0
    return round(px / grid) * grid


def is_monthly_opex_friday(d) -> bool:
    """3rd Friday of the month."""
    if d.weekday() != 4:
        return False
    return 15 <= d.day <= 21


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

def simulate_ticker(
    bars: pd.DataFrame,
    *,
    morning_end_min: int = MORNING_END_MIN,
    afternoon_end_min: int = AFTERNOON_END_MIN,
    min_dist_pct: float = MIN_DIST_FROM_PIN_PCT,
    max_dist_pct: float = MAX_DIST_FROM_PIN_PCT,
    cost_bps_rt: float = COST_BPS_RT,
    direction: str = 'fade',     # 'fade' (baseline) | 'cont' (null)
    opex_only: bool = True,
    friday_only: bool = False,
) -> list[dict]:
    """Numpy-inner-loop pin-fade simulator for one ticker."""
    if bars.empty:
        return []
    open_arr = bars['open'].to_numpy(dtype=np.float64)
    close_arr = bars['close'].to_numpy(dtype=np.float64)
    idx = bars.index
    dates_arr = np.array(idx.date)
    n = len(bars)

    # Day grouping.
    change = np.empty(n, dtype=bool)
    change[0] = True
    change[1:] = dates_arr[1:] != dates_arr[:-1]
    day_starts = np.flatnonzero(change)
    day_ends = np.empty_like(day_starts)
    day_ends[:-1] = day_starts[1:]
    day_ends[-1] = n
    n_days = len(day_starts)
    day_first_dates = np.array([dates_arr[int(day_starts[i])] for i in range(n_days)])

    # Eligibility mask
    eligible = np.zeros(n_days, dtype=bool)
    for i, d in enumerate(day_first_dates):
        if opex_only:
            eligible[i] = is_monthly_opex_friday(d)
        elif friday_only:
            eligible[i] = (d.weekday() == 4)
        else:
            eligible[i] = True

    cost_pct = cost_bps_rt / 1e4
    morning_bar_offset = morning_end_min // 5
    afternoon_bar_offset = afternoon_end_min // 5

    trades: list[dict] = []
    for d_i in range(n_days):
        if not eligible[d_i]:
            continue
        s, e = int(day_starts[d_i]), int(day_ends[d_i])
        n_bars = e - s
        # Need at least morning + 1 entry bar + 1 exit bar
        if n_bars < morning_bar_offset + 3:
            continue
        # Bar index into the day, then absolute index
        morning_bar = s + morning_bar_offset
        if morning_bar >= e:
            continue
        morning_px = float(close_arr[morning_bar])
        if morning_px <= 0:
            continue
        strike = round_strike(morning_px)
        if strike <= 0:
            continue
        dist_pct = (morning_px / strike - 1.0) * 100.0  # in %

        if abs(dist_pct) < min_dist_pct:
            continue
        if abs(dist_pct) > max_dist_pct:
            continue

        sign_dist = 1.0 if dist_pct > 0 else -1.0
        pos = -sign_dist if direction == 'fade' else sign_dist

        # Exit bar
        exit_bar = min(s + afternoon_bar_offset, e - 1)
        entry_bar = morning_bar + 1
        if entry_bar >= exit_bar:
            continue

        entry_px = float(open_arr[entry_bar])
        exit_px = float(close_arr[exit_bar])
        if entry_px <= 0 or exit_px <= 0:
            continue

        pnl = pos * (exit_px / entry_px - 1.0) - cost_pct

        trades.append({
            'date': pd.Timestamp(day_first_dates[d_i]),
            'direction': 'LONG' if pos > 0 else 'SHORT',
            'morning_px': morning_px,
            'strike': strike,
            'dist_pct': float(dist_pct),
            'entry_px': entry_px,
            'exit_px': exit_px,
            'pnl': float(pnl),
        })
    return trades


def run_basket(
    bars_by_ticker: dict[str, pd.DataFrame],
    **sim_kwargs,
) -> pd.DataFrame:
    rows = []
    for tk, bars in bars_by_ticker.items():
        trades = simulate_ticker(bars, **sim_kwargs)
        for t in trades:
            t['ticker'] = tk
            rows.append(t)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_basket(label: str, ev: pd.DataFrame) -> None:
    if ev.empty:
        print(f'  [{label}] NO TRADES')
        return
    pnl = ev['pnl'].to_numpy()
    sh = event_sharpe(pnl)
    daily = ev.groupby('date')['pnl'].mean().sort_index()
    eq = (1.0 + daily.values).cumprod()
    mdd = max_drawdown(eq)
    n = len(ev)
    wins = ev[ev['pnl'] > 0]
    losses = ev[ev['pnl'] <= 0]
    wr = len(wins) / n
    gw = float(wins['pnl'].sum())
    gl = float(-losses['pnl'].sum())
    pf = gw / gl if gl > 0 else float('inf')
    avg_w = float(wins['pnl'].mean()) if len(wins) else 0.0
    avg_l = float(losses['pnl'].mean()) if len(losses) else 0.0
    years = (ev['date'].max() - ev['date'].min()).days / 365.25
    total = float(eq[-1] - 1.0) if eq.size else 0.0
    cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
    print(f'  [{label}]')
    print(f'    period   : {ev["date"].min().date()} -> {ev["date"].max().date()} ({years:.1f}y)')
    print(f'    total ret: {total * 100:+.2f}%  CAGR {cagr * 100:+.2f}%')
    print(f'    Sharpe   : {sh:+.2f}')
    print(f'    Max DD   : {mdd * 100:+.2f}%')
    print(f'    events   : {n}  ({n/years:.1f}/yr)  (across {ev["ticker"].nunique()} tickers)')
    print(f'    WR / PF  : {wr*100:.1f}% / {pf:.2f}')
    print(f'    avg w/l  : {avg_w * 100:+.3f}% / {avg_l * 100:+.3f}%')


def kill_check(ev: pd.DataFrame, floor: float = 0.30) -> None:
    if ev.empty:
        print('  NO EVENTS — KILL')
        return
    pnl = ev['pnl'].to_numpy()
    sh = event_sharpe(pnl)
    daily = ev.groupby('date')['pnl'].mean().sort_index()
    eq = (1.0 + daily.values).cumprod()
    mdd = max_drawdown(eq)
    n = len(ev)
    wins = ev[ev['pnl'] > 0]
    losses = ev[ev['pnl'] <= 0]
    wr = len(wins) / n
    gw = float(wins['pnl'].sum()); gl = float(-losses['pnl'].sum())
    pf = gw / gl if gl > 0 else float('inf')
    v = lambda ok: 'PASS' if ok else 'FAIL'
    print(f'    Sharpe > {floor:.2f}    : {v(sh > floor)}  ({sh:+.2f})')
    print(f'    MDD < 25%        : {v(abs(mdd) < 0.25)}  ({mdd * 100:+.2f}%)')
    print(f'    Events >= 300    : {v(n >= 300)}  ({n})')
    print(f'    WR>=50 or PF>=1.1: {v(wr >= 0.50 or pf >= 1.1)}  (WR {wr*100:.1f}%, PF {pf:.2f})')


def regime_breakdown(ev: pd.DataFrame) -> None:
    windows = [
        ('2019-2020 pre/COVID', '2019-01-01', '2020-12-31'),
        ('2021-2022 vol',       '2021-01-01', '2022-12-31'),
        ('2023-2026 holdout',   '2023-01-01', '2026-12-31'),
    ]
    for label, s, e in windows:
        sub = ev[(ev['date'] >= s) & (ev['date'] <= e)]
        if len(sub) < 10:
            print(f'  {label:<22s} (n={len(sub)}, insufficient)')
            continue
        pnl = sub['pnl'].to_numpy()
        sh = event_sharpe(pnl)
        daily = sub.groupby('date')['pnl'].mean().sort_index()
        eq = (1.0 + daily.values).cumprod()
        mdd = max_drawdown(eq)
        years = (sub['date'].max() - sub['date'].min()).days / 365.25
        total = float(eq[-1] - 1.0) if eq.size else 0.0
        cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
        print(f'  {label:<22s} CAGR {cagr * 100:>+7.2f}%  Sharpe {sh:>+6.2f}  '
              f'MDD {mdd * 100:>+7.2f}%  events {len(sub):>4d}')


def per_ticker_breakdown(ev: pd.DataFrame) -> None:
    rows = []
    for tk, sub in ev.groupby('ticker'):
        pnl = sub['pnl'].to_numpy()
        n = len(sub)
        if n < 3:
            continue
        sh = event_sharpe(pnl)
        rows.append({'ticker': tk, 'n': n, 'sh': sh,
                     'mean_pnl': sub['pnl'].mean() * 100,
                     'wr': (sub['pnl'] > 0).mean() * 100})
    df = pd.DataFrame(rows).sort_values('sh', ascending=False)
    for _, r in df.iterrows():
        print(f"  {r['ticker']:<6s}  n={int(r['n']):>3d}  Sh {r['sh']:+6.2f}  "
              f"mean {r['mean_pnl']:+5.2f}%  WR {r['wr']:5.1f}%")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section('Loading M5 bars for OPEX-pin single-stock basket')
    bars_by = {}
    for tk in UNIVERSE:
        try:
            b = load_m5(tk)
            bars_by[tk] = b
            n_opex = sum(1 for d in set(b.index.date) if is_monthly_opex_friday(d))
            print(f'  {tk:<6s} bars={len(b):>6d}  range={b.index[0].date()}->{b.index[-1].date()}  OPEX-days={n_opex}')
        except RuntimeError as e:
            print(f'  {tk}: SKIP — {e}')

    section('Baseline (fade, OPEX-only, AM=120min, PM=385min, MIN_DIST=0.50%, cost=15bp)')
    ev = run_basket(bars_by)
    report_basket('basket fade', ev)

    section('Phase 2 kill criteria')
    kill_check(ev)

    section('Regime breakdown')
    regime_breakdown(ev)

    section('Per-ticker breakdown (full sample)')
    per_ticker_breakdown(ev)

    section('Variant sweep — MIN_DIST_FROM_PIN (% — minimum spot-to-strike at 11:30)')
    for md in (0.25, 0.5, 1.0, 1.5, 2.0):
        ev_v = run_basket(bars_by, min_dist_pct=md)
        sh = event_sharpe(ev_v['pnl'].to_numpy()) if not ev_v.empty else 0.0
        print(f'  MIN_DIST={md:>4.2f}%  Sharpe {sh:+.2f}  events {len(ev_v):>4d}')

    section('Variant sweep — PM exit minute (385=15:55, 360=15:30, 330=15:00, 300=14:30)')
    for ae in (240, 300, 330, 360, 385):
        ev_v = run_basket(bars_by, afternoon_end_min=ae)
        sh = event_sharpe(ev_v['pnl'].to_numpy()) if not ev_v.empty else 0.0
        print(f'  PM={ae:>3d}min  Sharpe {sh:+.2f}  events {len(ev_v):>4d}')

    section('Variant sweep — cost sensitivity (bps RT)')
    for c in (0.0, 5.0, 15.0, 30.0, 50.0):
        ev_v = run_basket(bars_by, cost_bps_rt=c)
        sh = event_sharpe(ev_v['pnl'].to_numpy()) if not ev_v.empty else 0.0
        print(f'  cost={c:>4.1f}bp  Sharpe {sh:+.2f}')

    section('Null check — continuation direction (anti-pin)')
    ev_cont = run_basket(bars_by, direction='cont')
    report_basket('basket cont', ev_cont)
    base_sh = event_sharpe(ev['pnl'].to_numpy()) if not ev.empty else 0.0
    cont_sh = event_sharpe(ev_cont['pnl'].to_numpy()) if not ev_cont.empty else 0.0
    gap = base_sh - cont_sh
    print(f'\n  direction-gap (fade - cont) = {gap:+.2f}')
    if gap >= 0.30:
        print('    PASS: fade signal has directional content.')
    elif gap <= -0.30:
        print('    INVERTED: continuation wins — pin thesis sign-wrong on this basket.')
    else:
        print('    FAIL: |gap| < 0.30 — no directional content.')

    section('All-Friday null (does OPEX-day calendar lock matter?)')
    ev_fri = run_basket(bars_by, opex_only=False, friday_only=True)
    fri_sh = event_sharpe(ev_fri['pnl'].to_numpy()) if not ev_fri.empty else 0.0
    report_basket('basket all-Friday fade', ev_fri)
    delta = base_sh - fri_sh
    print(f'\n  OPEX-only Sharpe - all-Friday Sharpe = {delta:+.2f}')
    if delta >= 0.20:
        print('    PASS: OPEX calendar lock adds signal.')
    else:
        print('    FAIL: OPEX-only not better than all-Friday — calendar lock not load-bearing.')

    section('Summary')
    print(f'  Basket: {len(bars_by)} tickers')
    print(f'  Phase 2 basket fade: Sharpe {base_sh:+.2f}  events {len(ev)}')
    print(f'  Direction-gap (fade-cont): {gap:+.2f}')
    print(f'  OPEX-vs-all-Friday delta: {delta:+.2f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
