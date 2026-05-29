#!/usr/bin/env python3
"""Single-stock earnings-gap fade — intraday Phase 2 backtest.

Thesis: experiments/earnings_fade/earnings_fade.md

Mechanism: fade the post-earnings opening gap for ~10-60 min, then flat.
- universe: 24 Mag7/large-cap names (MS dropped — not on Eightcap)
- earnings calendar: yfinance ticker.earnings_dates (50 events / name, 2014+)
- bars: M5 from MT5 (broker-server timestamps stored as UTC labels; RTH-only)

Per-event:
    prior_close = last M5 close on day D-1 (RTH closing bar)
    today_open  = first M5 OPEN on trade_date D (~09:30-09:35 ET)
    gap_pct     = today_open / prior_close - 1.0
    if abs(gap_pct) < MIN_GAP_PCT: skip
    position    = -sign(gap_pct)        # FADE (baseline) or +sign(gap_pct) for null-check
    entry_bar   = bar_index_in_day=1   # SECOND M5 bar (09:35 ET) — conservative slippage
    entry_px    = day_open[entry_bar]
    stop_px     = entry_px ± abs(gap_pct in $) * STOP_GAP_FRAC
    exit:       stop OR T+TIME_EXIT_MIN OR last RTH bar of day
    Max 1 trade per (ticker, event).

Cost: 2 bp basket median (Phase 0 confirmed); deploy assumption 4 bp RT.
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
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM', 'BAC', 'GS',
    'V', 'MA',
    'UNH', 'WMT', 'HD', 'LOW', 'KO', 'PEP', 'JNJ',
    'XOM', 'CVX',
    'ORCL', 'CRM', 'AVGO',
]

TIMEFRAME = 'M5'
START_DATE = '2018-01-01'
END_DATE = '2026-05-21'

CALENDAR_PATH = _HERE / 'data' / 'earnings_calendar.csv'

# Baseline parameters.
MIN_GAP_PCT = 0.015        # 1.5% — minimum gap magnitude to trade
ENTRY_BAR_INDEX = 1         # SECOND M5 bar (entry at 09:35 ET, conservative)
TIME_EXIT_MIN = 60          # default 60-min hold
STOP_GAP_FRAC = 1.5         # stop at 1.5x the gap magnitude (in price)
COST_BPS_RT = 4.0           # 4 bps round-trip (Phase 0 confirmed 2 bps + slippage buffer)

EVENTS_PER_YEAR_ANN = 100   # annualization for per-event Sharpe (~100 events/yr basket)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f'\n{"=" * 80}\n  {t}\n{"=" * 80}\n')


def load_m5(symbol: str) -> pd.DataFrame:
    """Load RTH M5 bars; bars are broker-server-time labelled as UTC.

    For US stocks the broker streams only during NYSE RTH, so bars cluster
    16:30-23:00 (EEST) or 14:30-21:00 (EET) — i.e. always the same calendar date
    as the trade_date in US/Eastern. We can group by `.date` without TZ conversion.
    """
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f'No bars for {symbol} {TIMEFRAME}')
    df = raw[['timestamp', 'open', 'high', 'low', 'close']].copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.set_index('timestamp').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    return df


def load_calendar() -> pd.DataFrame:
    df = pd.read_csv(CALENDAR_PATH)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df[['ticker', 'trade_date', 'ann_session']].drop_duplicates()
    df = df.sort_values(['trade_date', 'ticker']).reset_index(drop=True)
    return df


def max_drawdown(eq: np.ndarray) -> float:
    if eq.size == 0:
        return 0.0
    rm = np.maximum.accumulate(eq)
    dd = (eq - rm) / rm
    return float(dd.min())


def event_sharpe(pnl: np.ndarray, events_per_year: int = EVENTS_PER_YEAR_ANN) -> float:
    pnl = pnl[np.isfinite(pnl)]
    if pnl.size == 0:
        return 0.0
    std = pnl.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(pnl.mean() / std * np.sqrt(events_per_year))


def equity_curve_from_events(events_df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Daily-aggregated equity curve.

    On a given trade_date with K simultaneous events, position-size is 1/K so the
    daily PnL is the equal-weight mean of event PnL. Sharpe and DD computed on
    the per-event series (annualized by ~100/yr), per-day series used only for DD.
    """
    if events_df.empty:
        return np.array([]), np.array([])
    daily = events_df.groupby('trade_date')['pnl'].mean().sort_index()
    eq = (1.0 + daily.values).cumprod()
    return daily.values, eq


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

def simulate_ticker(
    bars: pd.DataFrame,
    ticker_events: pd.DataFrame,
    *,
    min_gap_pct: float = MIN_GAP_PCT,
    entry_bar_index: int = ENTRY_BAR_INDEX,
    time_exit_min: int = TIME_EXIT_MIN,
    stop_gap_frac: float = STOP_GAP_FRAC,
    cost_bps_rt: float = COST_BPS_RT,
    direction: str = 'fade',  # 'fade' | 'cont'
) -> list[dict]:
    """Numpy-inner-loop simulator for one ticker. Returns list-of-trade-dicts."""
    if bars.empty or ticker_events.empty:
        return []

    open_arr = bars['open'].to_numpy(dtype=np.float64)
    high_arr = bars['high'].to_numpy(dtype=np.float64)
    low_arr = bars['low'].to_numpy(dtype=np.float64)
    close_arr = bars['close'].to_numpy(dtype=np.float64)
    idx = bars.index
    dates = np.array(idx.date)

    # Day-grouping.
    change = np.empty(len(idx), dtype=bool)
    change[0] = True
    change[1:] = dates[1:] != dates[:-1]
    day_starts = np.flatnonzero(change)
    day_ends = np.empty_like(day_starts)
    day_ends[:-1] = day_starts[1:]
    day_ends[-1] = len(idx)
    n_days = len(day_starts)
    day_keys = pd.Series(dates[day_starts])  # date per day index

    # Map trade_date -> day_idx in this ticker's bars.
    date_to_dayidx = {dk: i for i, dk in enumerate(day_keys.values)}

    bars_per_exit = max(1, time_exit_min // 5)
    cost_pct = cost_bps_rt / 1e4

    trades: list[dict] = []
    for _, ev in ticker_events.iterrows():
        td = ev['trade_date'].date() if hasattr(ev['trade_date'], 'date') else ev['trade_date']
        if td not in date_to_dayidx:
            continue
        d_i = date_to_dayidx[td]
        if d_i == 0:
            continue  # need prior day close
        s, e = int(day_starts[d_i]), int(day_ends[d_i])
        n_bars = e - s
        if n_bars <= entry_bar_index + bars_per_exit:
            continue

        # Prior day close (last RTH bar of D-1).
        prev_s, prev_e = int(day_starts[d_i - 1]), int(day_ends[d_i - 1])
        if prev_e <= prev_s:
            continue
        prior_close = float(close_arr[prev_e - 1])
        if prior_close <= 0:
            continue

        # Today's first M5 OPEN — proxy for opening-auction print.
        today_open_for_gap = float(open_arr[s])
        gap_pct = today_open_for_gap / prior_close - 1.0
        if not np.isfinite(gap_pct) or abs(gap_pct) < min_gap_pct:
            continue

        # Entry at bar index ENTRY_BAR_INDEX (default 1 = second bar, 09:35 ET).
        entry_idx = s + entry_bar_index
        if entry_idx >= e - 1:
            continue
        entry_px = float(open_arr[entry_idx])
        if entry_px <= 0:
            continue

        sign_gap = 1.0 if gap_pct > 0 else -1.0
        pos = -sign_gap if direction == 'fade' else sign_gap

        # Stop: 1.5x gap (in $) beyond entry, against position.
        gap_abs = abs(gap_pct * prior_close)
        stop_dist = gap_abs * stop_gap_frac
        stop_px = entry_px - pos * stop_dist  # LONG=stop below, SHORT=stop above

        # Time exit bar.
        exit_idx_t = min(entry_idx + bars_per_exit, e - 1)

        # Walk bars from entry_idx+1 to exit_idx_t looking for stop hit.
        exit_idx = exit_idx_t
        reason = 'time'
        for j in range(entry_idx + 1, exit_idx_t + 1):
            hi, lo = high_arr[j], low_arr[j]
            if pos > 0 and lo <= stop_px:
                exit_idx = j
                reason = 'stop'
                exit_px = stop_px
                break
            if pos < 0 and hi >= stop_px:
                exit_idx = j
                reason = 'stop'
                exit_px = stop_px
                break
        else:
            exit_px = float(close_arr[exit_idx])

        pnl = pos * (exit_px / entry_px - 1.0) - cost_pct

        trades.append({
            'ticker': str(ev['ticker']),
            'trade_date': td,
            'ann_session': ev['ann_session'],
            'direction': 'LONG' if pos > 0 else 'SHORT',
            'gap_pct': float(gap_pct),
            'entry_idx': entry_idx - s,
            'exit_idx': exit_idx - s,
            'entry_px': entry_px,
            'exit_px': float(exit_px),
            'stop_px': float(stop_px),
            'pnl': float(pnl),
            'reason': reason,
        })
    return trades


def run_backtest(
    *,
    min_gap_pct: float = MIN_GAP_PCT,
    entry_bar_index: int = ENTRY_BAR_INDEX,
    time_exit_min: int = TIME_EXIT_MIN,
    stop_gap_frac: float = STOP_GAP_FRAC,
    cost_bps_rt: float = COST_BPS_RT,
    direction: str = 'fade',
    verbose: bool = False,
    cached_bars: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Run across the full universe. Returns events DataFrame with PnL column."""
    cal = load_calendar()
    all_trades: list[dict] = []
    for ticker in UNIVERSE:
        if cached_bars is not None and ticker in cached_bars:
            bars = cached_bars[ticker]
        else:
            try:
                bars = load_m5(ticker)
            except RuntimeError as e:
                if verbose:
                    print(f'  {ticker}: {e}')
                continue
            if cached_bars is not None:
                cached_bars[ticker] = bars
        tk_events = cal[cal['ticker'] == ticker].copy()
        trades = simulate_ticker(
            bars,
            tk_events,
            min_gap_pct=min_gap_pct,
            entry_bar_index=entry_bar_index,
            time_exit_min=time_exit_min,
            stop_gap_frac=stop_gap_frac,
            cost_bps_rt=cost_bps_rt,
            direction=direction,
        )
        if verbose:
            print(f'  {ticker:<6s} bars={len(bars):>6d}  events_in_cal={len(tk_events):>3d}  trades={len(trades):>3d}')
        all_trades.extend(trades)
    return pd.DataFrame(all_trades)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_run(label: str, events: pd.DataFrame) -> None:
    if events.empty:
        print(f'  [{label}] NO TRADES')
        return
    ev = events.copy()
    ev['trade_date'] = pd.to_datetime(ev['trade_date'])
    pnl = ev['pnl'].to_numpy()
    sh = event_sharpe(pnl)
    daily_ret, eq = equity_curve_from_events(ev)
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
    years = (ev['trade_date'].max() - ev['trade_date'].min()).days / 365.25
    total = float(eq[-1] - 1.0) if eq.size else 0.0
    cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
    print(f'  [{label}]')
    print(f'    period     : {ev["trade_date"].min().date()} -> {ev["trade_date"].max().date()} ({years:.1f}y)')
    print(f'    total ret  : {total * 100:+.2f}%')
    print(f'    CAGR       : {cagr * 100:+.2f}%')
    print(f'    Sharpe     : {sh:+.2f}')
    print(f'    Max DD     : {mdd * 100:+.2f}%')
    print(f'    events     : {n}  ({n/years:.1f}/yr)')
    print(f'    win rate   : {wr * 100:.1f}%')
    print(f'    profit fac : {pf:.2f}')
    print(f'    avg win    : {avg_w * 100:+.3f}%   avg loss: {avg_l * 100:+.3f}%')


def kill_criteria_check(label: str, events: pd.DataFrame, sharpe_floor: float = 0.30) -> None:
    if events.empty:
        print(f'  [{label}] NO TRADES — KILL')
        return
    pnl = events['pnl'].to_numpy()
    sh = event_sharpe(pnl)
    _, eq = equity_curve_from_events(events)
    mdd = max_drawdown(eq)
    n = len(events)
    wins = events[events['pnl'] > 0]
    losses = events[events['pnl'] <= 0]
    wr = len(wins) / n
    gw = float(wins['pnl'].sum())
    gl = float(-losses['pnl'].sum())
    pf = gw / gl if gl > 0 else float('inf')
    v = lambda ok: 'PASS' if ok else 'FAIL'
    print(f'  [{label}]')
    print(f'    Sharpe > {sharpe_floor:.2f}    : {v(sh > sharpe_floor)}  ({sh:+.2f})')
    print(f'    Max DD < 25%      : {v(abs(mdd) < 0.25)}  ({mdd * 100:+.2f}%)')
    print(f'    Events >= 200     : {v(n >= 200)}  ({n})')
    print(f'    WR>=45 or PF>=1.1 : {v(wr >= 0.45 or pf >= 1.1)}  (WR {wr*100:.1f}%, PF {pf:.2f})')


def regime_breakdown(events: pd.DataFrame) -> None:
    windows = [
        ('2018-2020 pre/COVID', '2018-01-01', '2020-12-31'),
        ('2021-2022 vol',       '2021-01-01', '2022-12-31'),
        ('2023-2026 holdout',   '2023-01-01', '2026-12-31'),
    ]
    ev = events.copy()
    ev['trade_date'] = pd.to_datetime(ev['trade_date'])
    for label, s, e in windows:
        s_dt, e_dt = pd.Timestamp(s), pd.Timestamp(e)
        sub = ev[(ev['trade_date'] >= s_dt) & (ev['trade_date'] <= e_dt)]
        if len(sub) < 5:
            print(f'  {label:<22s} (n={len(sub)}, insufficient)')
            continue
        pnl = sub['pnl'].to_numpy()
        sh = event_sharpe(pnl)
        _, eq = equity_curve_from_events(sub)
        mdd = max_drawdown(eq)
        years = (sub['trade_date'].max() - sub['trade_date'].min()).days / 365.25
        total = float(eq[-1] - 1.0) if eq.size else 0.0
        cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
        print(f'  {label:<22s} CAGR {cagr * 100:>+7.2f}%  Sharpe {sh:>+6.2f}  '
              f'MDD {mdd * 100:>+7.2f}%  events {len(sub):>4d}')


def per_ticker_breakdown(events: pd.DataFrame) -> None:
    rows = []
    ev = events.copy()
    ev['trade_date'] = pd.to_datetime(ev['trade_date'])
    for tk, sub in ev.groupby('ticker'):
        pnl = sub['pnl'].to_numpy()
        sh = event_sharpe(pnl, events_per_year=max(1, int(len(sub) / max(0.1, (sub['trade_date'].max() - sub['trade_date'].min()).days / 365.25))))
        wins = sub[sub['pnl'] > 0]
        wr = len(wins) / len(sub)
        avg = float(sub['pnl'].mean())
        total = float(sub['pnl'].sum())
        rows.append((tk, len(sub), wr, avg, total, sh))
    rows.sort(key=lambda r: -r[4])
    print(f'  {"ticker":<6s} {"n":>4s} {"WR":>6s} {"avg":>10s} {"total":>10s} {"Sh*":>7s}')
    for tk, n, wr, avg, total, sh in rows:
        print(f'  {tk:<6s} {n:>4d} {wr*100:>5.1f}% {avg*100:>+8.3f}% {total*100:>+8.2f}% {sh:>+7.2f}')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section('Loading universe (24 names) M5 + earnings calendar')
    cache: dict[str, pd.DataFrame] = {}
    events_base = run_backtest(cached_bars=cache, verbose=True)
    print(f'\n  Total events traded (baseline): {len(events_base)}')

    section('Baseline — fade, MIN_GAP=1.5%, entry=bar1, T+60min, stop=1.5x gap, cost=4bp RT')
    report_run('baseline', events_base)

    section('Phase 2 kill-criteria')
    kill_criteria_check('baseline', events_base)

    section('Regime breakdown')
    regime_breakdown(events_base)

    section('Per-ticker breakdown (baseline)')
    per_ticker_breakdown(events_base)

    section('Variant sweep — MIN_GAP_PCT')
    for g in (0.005, 0.010, 0.015, 0.020, 0.030, 0.050):
        ev = run_backtest(min_gap_pct=g, cached_bars=cache)
        if ev.empty:
            print(f'  min_gap={g*100:.1f}%  (no events)')
            continue
        sh = event_sharpe(ev['pnl'].to_numpy())
        _, eq = equity_curve_from_events(ev)
        mdd = max_drawdown(eq)
        print(f'  min_gap={g*100:>4.1f}%  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  events {len(ev):>4d}')

    section('Variant sweep — TIME_EXIT_MIN')
    for t in (15, 30, 45, 60, 90, 120, 180):
        ev = run_backtest(time_exit_min=t, cached_bars=cache)
        sh = event_sharpe(ev['pnl'].to_numpy())
        _, eq = equity_curve_from_events(ev)
        mdd = max_drawdown(eq)
        print(f'  T+{t:>3d}min  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  events {len(ev):>4d}')

    section('Variant sweep — STOP_GAP_FRAC')
    for sf in (0.5, 1.0, 1.5, 2.0, 3.0, 5.0):
        ev = run_backtest(stop_gap_frac=sf, cached_bars=cache)
        sh = event_sharpe(ev['pnl'].to_numpy())
        _, eq = equity_curve_from_events(ev)
        mdd = max_drawdown(eq)
        print(f'  stop={sf:>4.1f}x gap  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  events {len(ev):>4d}')

    section('Cost sensitivity — bps RT')
    for c in (0.0, 2.0, 4.0, 8.0, 15.0, 30.0):
        ev = run_backtest(cost_bps_rt=c, cached_bars=cache)
        sh = event_sharpe(ev['pnl'].to_numpy())
        print(f'  cost={c:>5.1f}bp  Sharpe {sh:>+6.2f}  events {len(ev):>4d}')

    section('Direction null-check — continuation (opposite sign of fade)')
    events_cont = run_backtest(direction='cont', cached_bars=cache)
    report_run('cont', events_cont)
    base_sh = event_sharpe(events_base['pnl'].to_numpy())
    cont_sh = event_sharpe(events_cont['pnl'].to_numpy())
    gap = base_sh - cont_sh
    print(f'\n  Direction-gap (fade - cont) = {gap:+.2f}')
    if gap >= 0.30:
        print('    PASS: fade direction has directional content (lesson #39 pre-commit honored).')
    elif gap <= -0.30:
        print('    INVERTED: continuation wins — thesis sign refuted. Tombstone, do NOT pivot.')
    else:
        print('    FAIL: |gap| < 0.30 — no directional content.')

    section('Long-side / Short-side split (baseline)')
    if not events_base.empty:
        for d, sub in events_base.groupby('direction'):
            sh = event_sharpe(sub['pnl'].to_numpy())
            _, eq = equity_curve_from_events(sub)
            mdd = max_drawdown(eq)
            wr = (sub['pnl'] > 0).mean()
            print(f'  {d:<5s} n={len(sub):>4d}  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  WR {wr*100:.1f}%')

    section('Summary')
    ev_b = events_base.copy()
    ev_b['trade_date'] = pd.to_datetime(ev_b['trade_date'])
    sh = event_sharpe(ev_b['pnl'].to_numpy())
    _, eq = equity_curve_from_events(ev_b)
    mdd = max_drawdown(eq)
    years = (ev_b['trade_date'].max() - ev_b['trade_date'].min()).days / 365.25
    print(f'  earnings_fade baseline : Sharpe {sh:+.2f}  MDD {mdd*100:+.2f}%  '
          f'events {len(events_base)} ({len(events_base)/years:.1f}/yr)  '
          f'dir-gap {gap:+.2f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
