#!/usr/bin/env python3
"""Post-Earnings Announcement Drift on the ~168-name mid/large-cap Eightcap universe.

Thesis: experiments/pead_midcap/pead_midcap.md

Mechanism: long top-quantile positive SUE / short bottom-quantile negative SUE,
hold N days post-announcement. Phase 1: per-event book. Phase 2: cross-sectional
basket by week.

Run:
    venv/Scripts/python.exe experiments/pead_midcap/pead_midcap_demo.py
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

from utils import fetch_ohlc  # noqa: E402


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

UNIVERSE_PATH = _ROOT / 'experiments' / '.us_stock_universe.txt'
CALENDAR_PATH = _HERE / 'data' / 'earnings_calendar_midcap.csv'

TIMEFRAME = 'D1'
START_DATE = '2014-01-01'
END_DATE = '2026-05-24'

# Baseline parameters (pre-committed).
MIN_SUE_PCT = 5.0          # |surprise%| floor
HOLD_DAYS = 20             # business-day hold
COST_BPS_RT = 10.0         # 10 bps mid-cap CFD round-trip
EVENTS_PER_YEAR = 100      # per-event Sharpe annualization

# Cross-sectional decile parameters
XS_QUINTILE_FRAC = 0.20    # top/bottom 20% by SUE rank per week


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f'\n{"=" * 80}\n  {t}\n{"=" * 80}\n')


def load_universe() -> list[str]:
    return [s.strip() for s in UNIVERSE_PATH.read_text().splitlines() if s.strip()]


def load_d1(symbol: str) -> pd.DataFrame | None:
    try:
        raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    except Exception:
        return None
    if raw is None or raw.empty:
        return None
    df = raw[['timestamp', 'open', 'high', 'low', 'close']].copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.set_index('timestamp').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    # Normalize to date (drop intraday components for D1).
    df.index = pd.DatetimeIndex(df.index.date)
    return df


def load_calendar() -> pd.DataFrame:
    df = pd.read_csv(CALENDAR_PATH)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['surprise_pct'] = pd.to_numeric(df['surprise_pct'], errors='coerce')
    df = df.dropna(subset=['surprise_pct'])
    return df.sort_values(['trade_date', 'ticker']).reset_index(drop=True)


def load_all_bars(universe: list[str]) -> dict[str, pd.DataFrame]:
    bars = {}
    missing = []
    for tk in universe:
        b = load_d1(tk)
        if b is None or len(b) < 50:
            missing.append(tk)
            continue
        bars[tk] = b
    print(f"  bars loaded: {len(bars)}/{len(universe)}  (missing: {len(missing)})")
    if missing:
        print(f"  missing names: {','.join(missing[:30])}{'...' if len(missing) > 30 else ''}")
    return bars


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

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


def equity_from_daily(daily_ret: np.ndarray) -> np.ndarray:
    return (1.0 + daily_ret).cumprod()


# ---------------------------------------------------------------------------
# Phase 1 — per-event simulator (numpy-inner-loop)
# ---------------------------------------------------------------------------

def simulate_per_event(
    bars_by_ticker: dict[str, pd.DataFrame],
    events: pd.DataFrame,
    *,
    min_sue_pct: float = MIN_SUE_PCT,
    hold_days: int = HOLD_DAYS,
    cost_bps_rt: float = COST_BPS_RT,
    direction: str = 'drift',  # 'drift' (baseline) or 'fade' (null)
) -> pd.DataFrame:
    """Per-event PEAD: enter at open(trade_date), exit at close(trade_date+HOLD_DAYS-1).

    Position = +1 if sue>0, -1 if sue<0 (drift); inverted for 'fade'.
    """
    cost_pct = cost_bps_rt / 1e4
    out: list[dict] = []
    for tk, sub in events.groupby('ticker'):
        bars = bars_by_ticker.get(tk)
        if bars is None or bars.empty:
            continue
        open_arr = bars['open'].to_numpy(dtype=np.float64)
        close_arr = bars['close'].to_numpy(dtype=np.float64)
        dates_arr = bars.index.to_numpy()
        n = len(bars)
        date_to_idx = {d: i for i, d in enumerate(dates_arr)}
        for _, ev in sub.iterrows():
            sue = float(ev['surprise_pct'])
            if abs(sue) < min_sue_pct:
                continue
            td = np.datetime64(ev['trade_date'].date()) if hasattr(ev['trade_date'], 'date') else np.datetime64(ev['trade_date'])
            # Skip events whose trade_date is before bars-history starts (avoid bunching
            # all pre-history events onto the first available bar date).
            if td < dates_arr[0]:
                continue
            # Find entry bar — next bar on/after trade_date.
            if td not in date_to_idx:
                cand = dates_arr[dates_arr >= td]
                if len(cand) == 0:
                    continue
                entry_i = date_to_idx[cand[0]]
            else:
                entry_i = date_to_idx[td]
            exit_i = entry_i + hold_days - 1
            if exit_i >= n:
                continue
            entry_px = float(open_arr[entry_i])
            exit_px = float(close_arr[exit_i])
            if entry_px <= 0 or exit_px <= 0:
                continue
            sign_sue = 1.0 if sue > 0 else -1.0
            pos = sign_sue if direction == 'drift' else -sign_sue
            pnl = pos * (exit_px / entry_px - 1.0) - cost_pct
            out.append({
                'ticker': tk,
                'trade_date': pd.Timestamp(dates_arr[entry_i]),
                'exit_date': pd.Timestamp(dates_arr[exit_i]),
                'sue_pct': sue,
                'direction': 'LONG' if pos > 0 else 'SHORT',
                'entry_px': entry_px,
                'exit_px': exit_px,
                'pnl': float(pnl),
            })
    return pd.DataFrame(out)


def equity_curve_per_event(events: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Equal-weight basket: per trade_date, mean of all events' pnl entering that day.

    Per-event horizon (HOLD_DAYS) overlaps multiple positions in the air;
    daily-aggregated by entry-date approximates basket-rebalanced book.
    """
    if events.empty:
        return np.array([]), np.array([])
    daily = events.groupby('trade_date')['pnl'].mean().sort_index()
    eq = (1.0 + daily.values).cumprod()
    return daily.values, eq


def equity_curve_concurrent(events: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Concurrent-position basket: at any business day t, the open positions are
    those entered in [t-HOLD+1, t]. PnL per event amortized linearly over its
    HOLD days. Daily portfolio return = mean of per-event daily increments
    across open positions (1/N gross weighting; gross exposure capped at 100%).
    Approximate but properly diversified across overlapping events.
    """
    if events.empty:
        return np.array([]), np.array([])
    ev = events.copy()
    ev['hold_d'] = (ev['exit_date'] - ev['trade_date']).dt.days.clip(lower=1)
    ev['daily_inc'] = ev['pnl'] / ev['hold_d']
    # Build a daily timeline.
    start = ev['trade_date'].min()
    end = ev['exit_date'].max()
    timeline = pd.date_range(start, end, freq='D')
    daily_contribs: list[list[float]] = [[] for _ in range(len(timeline))]
    date_to_i = {d: i for i, d in enumerate(timeline)}
    for _, e in ev.iterrows():
        s_i = date_to_i.get(e['trade_date'])
        e_i = date_to_i.get(e['exit_date'])
        if s_i is None or e_i is None:
            continue
        for j in range(s_i, e_i + 1):
            daily_contribs[j].append(e['daily_inc'])
    daily_ret = np.array([float(np.mean(c)) if c else 0.0 for c in daily_contribs])
    eq = (1.0 + daily_ret).cumprod()
    return daily_ret, eq


# ---------------------------------------------------------------------------
# Phase 2 — cross-sectional weekly basket
# ---------------------------------------------------------------------------

def simulate_cross_sectional(
    bars_by_ticker: dict[str, pd.DataFrame],
    events: pd.DataFrame,
    *,
    quintile_frac: float = XS_QUINTILE_FRAC,
    min_sue_pct: float = MIN_SUE_PCT,
    hold_days: int = HOLD_DAYS,
    cost_bps_rt: float = COST_BPS_RT,
    direction: str = 'drift',
    min_per_week: int = 5,
) -> pd.DataFrame:
    """Cross-sectional weekly basket.

    Each Mon-Sun calendar week, rank that week's events by SUE; long top
    `quintile_frac`, short bottom `quintile_frac`. Each name held HOLD_DAYS.
    PnL summed equal-weight inside the long-short basket; returned as per-week.
    """
    cost_pct = cost_bps_rt / 1e4
    ev = events.copy()
    ev = ev[ev['surprise_pct'].abs() >= min_sue_pct].copy()
    if ev.empty:
        return pd.DataFrame()
    ev['week'] = ev['trade_date'].dt.to_period('W').dt.start_time

    # Precompute per-event raw return (no cost yet)
    raw_pnl = {}
    for tk, sub in ev.groupby('ticker'):
        bars = bars_by_ticker.get(tk)
        if bars is None or bars.empty:
            continue
        open_arr = bars['open'].to_numpy(dtype=np.float64)
        close_arr = bars['close'].to_numpy(dtype=np.float64)
        dates_arr = bars.index.to_numpy()
        n = len(bars)
        date_to_idx = {d: i for i, d in enumerate(dates_arr)}
        for _, e_row in sub.iterrows():
            td = np.datetime64(e_row['trade_date'].date()) if hasattr(e_row['trade_date'], 'date') else np.datetime64(e_row['trade_date'])
            if td < dates_arr[0]:
                continue
            if td in date_to_idx:
                entry_i = date_to_idx[td]
            else:
                cand = dates_arr[dates_arr >= td]
                if len(cand) == 0:
                    continue
                entry_i = date_to_idx[cand[0]]
            exit_i = entry_i + hold_days - 1
            if exit_i >= n:
                continue
            entry_px = float(open_arr[entry_i])
            exit_px = float(close_arr[exit_i])
            if entry_px <= 0 or exit_px <= 0:
                continue
            raw_pnl[(tk, e_row['trade_date'])] = exit_px / entry_px - 1.0

    weeks_out = []
    for wk, wk_ev in ev.groupby('week'):
        # Attach raw return.
        wk_ev = wk_ev.copy()
        wk_ev['raw_ret'] = [raw_pnl.get((r['ticker'], r['trade_date'])) for _, r in wk_ev.iterrows()]
        wk_ev = wk_ev.dropna(subset=['raw_ret'])
        if len(wk_ev) < min_per_week:
            continue
        n = len(wk_ev)
        k = max(1, int(round(quintile_frac * n)))
        wk_ev = wk_ev.sort_values('surprise_pct')
        bottom = wk_ev.iloc[:k]    # negative SUE -> SHORT (drift) / LONG (fade)
        top = wk_ev.iloc[-k:]      # positive SUE -> LONG (drift) / SHORT (fade)
        long_basket = top if direction == 'drift' else bottom
        short_basket = bottom if direction == 'drift' else top
        long_mean = long_basket['raw_ret'].mean() if len(long_basket) else 0.0
        short_mean = -short_basket['raw_ret'].mean() if len(short_basket) else 0.0
        # Equal-weight long-short, gross 2x; book scale = 1x.
        gross = 0.5 * (long_mean + short_mean)
        # Cost: each leg pays full round-trip cost on its slice; basket cost = cost_pct.
        net = gross - cost_pct
        weeks_out.append({
            'week': wk,
            'n_events': n,
            'n_long': len(long_basket),
            'n_short': len(short_basket),
            'long_ret': float(long_mean),
            'short_ret': float(short_mean),
            'gross': float(gross),
            'pnl': float(net),
        })
    return pd.DataFrame(weeks_out).sort_values('week').reset_index(drop=True)


def cross_sectional_sharpe(weekly: pd.DataFrame) -> float:
    if weekly.empty:
        return 0.0
    r = weekly['pnl'].to_numpy()
    if r.std(ddof=1) == 0:
        return 0.0
    return float(r.mean() / r.std(ddof=1) * np.sqrt(52))


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_per_event(label: str, events: pd.DataFrame) -> None:
    if events.empty:
        print(f'  [{label}] NO TRADES')
        return
    pnl = events['pnl'].to_numpy()
    sh = event_sharpe(pnl)
    _, eq = equity_curve_per_event(events)
    mdd = max_drawdown(eq)
    _, eq_conc = equity_curve_concurrent(events)
    mdd_conc = max_drawdown(eq_conc)
    total_conc = float(eq_conc[-1] - 1.0) if eq_conc.size else 0.0
    n = len(events)
    wins = events[events['pnl'] > 0]
    losses = events[events['pnl'] <= 0]
    wr = len(wins) / n
    gw = float(wins['pnl'].sum())
    gl = float(-losses['pnl'].sum())
    pf = gw / gl if gl > 0 else float('inf')
    avg_w = float(wins['pnl'].mean()) if len(wins) else 0.0
    avg_l = float(losses['pnl'].mean()) if len(losses) else 0.0
    years = (events['trade_date'].max() - events['trade_date'].min()).days / 365.25
    total = float(eq[-1] - 1.0) if eq.size else 0.0
    cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
    print(f'  [{label}]')
    print(f'    period     : {events["trade_date"].min().date()} -> {events["trade_date"].max().date()} ({years:.1f}y)')
    print(f'    total ret  : {total * 100:+.2f}%')
    print(f'    CAGR       : {cagr * 100:+.2f}%')
    print(f'    Sharpe     : {sh:+.2f}')
    print(f'    Max DD     : {mdd * 100:+.2f}%  (entry-day basket — proxy)')
    print(f'    MDD (conc) : {mdd_conc * 100:+.2f}%  total_ret_conc {total_conc * 100:+.2f}%')
    print(f'    events     : {n}  ({n/years:.1f}/yr)')
    print(f'    win rate   : {wr * 100:.1f}%')
    print(f'    profit fac : {pf:.2f}')
    print(f'    avg win    : {avg_w * 100:+.3f}%   avg loss: {avg_l * 100:+.3f}%')


def report_xs(label: str, weekly: pd.DataFrame) -> None:
    if weekly.empty:
        print(f'  [{label}] NO BASKETS')
        return
    sh = cross_sectional_sharpe(weekly)
    eq = (1.0 + weekly['pnl'].to_numpy()).cumprod()
    mdd = max_drawdown(eq)
    n = len(weekly)
    total = float(eq[-1] - 1.0)
    years = (weekly['week'].max() - weekly['week'].min()).days / 365.25
    cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
    wins = (weekly['pnl'] > 0).sum()
    wr = wins / n if n else 0.0
    print(f'  [{label}]')
    print(f'    period     : {weekly["week"].min().date()} -> {weekly["week"].max().date()} ({years:.1f}y)')
    print(f'    total ret  : {total * 100:+.2f}%')
    print(f'    CAGR       : {cagr * 100:+.2f}%')
    print(f'    Sharpe     : {sh:+.2f}')
    print(f'    Max DD     : {mdd * 100:+.2f}%')
    print(f'    weeks      : {n}  ({n/years:.1f}/yr)')
    print(f'    week WR    : {wr * 100:.1f}%')
    print(f'    avg n_evts : {weekly["n_events"].mean():.1f}')


def kill_check_per_event(events: pd.DataFrame, floor: float = 0.30) -> None:
    if events.empty:
        print('  NO EVENTS — KILL')
        return
    pnl = events['pnl'].to_numpy()
    sh = event_sharpe(pnl)
    _, eq_conc = equity_curve_concurrent(events)
    mdd_conc = max_drawdown(eq_conc)
    n = len(events)
    wins = events[events['pnl'] > 0]
    losses = events[events['pnl'] <= 0]
    wr = len(wins) / n
    gw = float(wins['pnl'].sum()); gl = float(-losses['pnl'].sum())
    pf = gw / gl if gl > 0 else float('inf')
    v = lambda ok: 'PASS' if ok else 'FAIL'
    print(f'    Sharpe > {floor:.2f}   : {v(sh > floor)}  ({sh:+.2f})')
    print(f'    Concurrent MDD<25%: {v(abs(mdd_conc) < 0.25)}  ({mdd_conc * 100:+.2f}%)')
    print(f'    Events >= 500    : {v(n >= 500)}  ({n})')
    print(f'    WR>=50 or PF>=1.1: {v(wr >= 0.50 or pf >= 1.1)}  (WR {wr*100:.1f}%, PF {pf:.2f})')


def regime_breakdown_per_event(events: pd.DataFrame) -> None:
    windows = [
        ('2015-2019 pre-COVID', '2015-01-01', '2019-12-31'),
        ('2020-2022 vol',       '2020-01-01', '2022-12-31'),
        ('2023-2026 holdout',   '2023-01-01', '2026-12-31'),
    ]
    for label, s, e in windows:
        sub = events[(events['trade_date'] >= s) & (events['trade_date'] <= e)]
        if len(sub) < 20:
            print(f'  {label:<22s} (n={len(sub)}, insufficient)')
            continue
        pnl = sub['pnl'].to_numpy()
        sh = event_sharpe(pnl)
        _, eq = equity_curve_per_event(sub)
        mdd = max_drawdown(eq)
        years = (sub['trade_date'].max() - sub['trade_date'].min()).days / 365.25
        total = float(eq[-1] - 1.0) if eq.size else 0.0
        cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
        print(f'  {label:<22s} CAGR {cagr * 100:>+7.2f}%  Sharpe {sh:>+6.2f}  '
              f'MDD {mdd * 100:>+7.2f}%  events {len(sub):>5d}')


def regime_breakdown_xs(weekly: pd.DataFrame) -> None:
    windows = [
        ('2015-2019 pre-COVID', '2015-01-01', '2019-12-31'),
        ('2020-2022 vol',       '2020-01-01', '2022-12-31'),
        ('2023-2026 holdout',   '2023-01-01', '2026-12-31'),
    ]
    for label, s, e in windows:
        sub = weekly[(weekly['week'] >= s) & (weekly['week'] <= e)]
        if len(sub) < 10:
            print(f'  {label:<22s} (weeks={len(sub)}, insufficient)')
            continue
        sh = cross_sectional_sharpe(sub)
        eq = (1.0 + sub['pnl'].to_numpy()).cumprod()
        mdd = max_drawdown(eq)
        years = (sub['week'].max() - sub['week'].min()).days / 365.25
        total = float(eq[-1] - 1.0) if eq.size else 0.0
        cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
        print(f'  {label:<22s} CAGR {cagr * 100:>+7.2f}%  Sharpe {sh:>+6.2f}  '
              f'MDD {mdd * 100:>+7.2f}%  weeks {len(sub):>4d}')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section('Loading universe + calendar + D1 bars')
    universe = load_universe()
    print(f'  universe size: {len(universe)}')
    cal = load_calendar()
    print(f'  calendar rows: {len(cal)}  ({cal["ticker"].nunique()} tickers, '
          f'{cal["trade_date"].min().date()} -> {cal["trade_date"].max().date()})')
    bars = load_all_bars(universe)
    # Restrict universe to names with bars + with calendar events.
    cal = cal[cal['ticker'].isin(bars.keys())]
    print(f'  calendar events with bars: {len(cal)}')

    section('Phase 1 — per-event PEAD (baseline: drift, HOLD=20, MIN_SUE=5%, cost=10bp)')
    ev = simulate_per_event(bars, cal)
    report_per_event('baseline (drift)', ev)

    section('Phase 1 — kill criteria')
    kill_check_per_event(ev)

    section('Phase 1 — regime breakdown')
    regime_breakdown_per_event(ev)

    section('Phase 1 — direction null check (FADE: long losers, short winners)')
    ev_fade = simulate_per_event(bars, cal, direction='fade')
    report_per_event('fade null', ev_fade)
    drift_sh = event_sharpe(ev['pnl'].to_numpy()) if not ev.empty else 0.0
    fade_sh = event_sharpe(ev_fade['pnl'].to_numpy()) if not ev_fade.empty else 0.0
    gap = drift_sh - fade_sh
    print(f'\n  direction-gap (drift - fade) = {gap:+.2f}')
    if gap >= 0.40:
        print('    PASS: drift has directional content vs fade.')
    elif gap <= -0.40:
        print('    INVERTED: fade beats drift — post-2022 inversion or wrong-direction prior.')
    else:
        print('    FAIL: |gap| < 0.40 — no decisive direction.')

    section('Phase 1 — HOLD_DAYS sweep (drift)')
    for h in (1, 5, 10, 20, 40, 60):
        ev_h = simulate_per_event(bars, cal, hold_days=h)
        sh = event_sharpe(ev_h['pnl'].to_numpy()) if not ev_h.empty else 0.0
        n_ev = len(ev_h)
        _, eq = equity_curve_per_event(ev_h)
        mdd = max_drawdown(eq)
        print(f'  HOLD={h:>3d}d  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  events {n_ev:>5d}')

    section('Phase 1 — MIN_SUE sweep (drift, HOLD=20)')
    for ms in (0.0, 2.5, 5.0, 10.0, 20.0):
        ev_m = simulate_per_event(bars, cal, min_sue_pct=ms)
        sh = event_sharpe(ev_m['pnl'].to_numpy()) if not ev_m.empty else 0.0
        n_ev = len(ev_m)
        print(f'  MIN_SUE={ms:>5.1f}%  Sharpe {sh:>+6.2f}  events {n_ev:>5d}')

    section('Phase 1 — cost sensitivity (drift, HOLD=20)')
    for c in (0.0, 5.0, 10.0, 20.0, 30.0):
        ev_c = simulate_per_event(bars, cal, cost_bps_rt=c)
        sh = event_sharpe(ev_c['pnl'].to_numpy()) if not ev_c.empty else 0.0
        print(f'  cost={c:>4.1f}bp  Sharpe {sh:>+6.2f}')

    section('Phase 2 — cross-sectional weekly basket (drift, HOLD=20, top/bot 20%)')
    wk = simulate_cross_sectional(bars, cal)
    report_xs('xs drift', wk)

    section('Phase 2 — XS regime breakdown')
    regime_breakdown_xs(wk)

    section('Phase 2 — XS null check (fade)')
    wk_fade = simulate_cross_sectional(bars, cal, direction='fade')
    report_xs('xs fade null', wk_fade)
    xs_drift_sh = cross_sectional_sharpe(wk)
    xs_fade_sh = cross_sectional_sharpe(wk_fade)
    print(f'\n  XS direction-gap = {xs_drift_sh - xs_fade_sh:+.2f}')

    section('Summary')
    print(f'  Universe:    {len(bars)} tickers with bars (of {len(universe)} requested)')
    print(f'  Calendar:    {len(cal)} events  ({cal["trade_date"].min().date()} -> {cal["trade_date"].max().date()})')
    print(f'  Phase 1 Sh:  drift {drift_sh:+.2f} / fade {fade_sh:+.2f} / gap {gap:+.2f}')
    print(f'  Phase 2 Sh:  drift {xs_drift_sh:+.2f} / fade {xs_fade_sh:+.2f} / gap {xs_drift_sh - xs_fade_sh:+.2f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
