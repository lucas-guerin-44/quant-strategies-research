#!/usr/bin/env python3
"""Single-stock lunch fade — generalize deployed lunch_fade NDX mechanism to 24 single names.

Re-implements simulate_lunch_fade using BAR-INDEX-IN-DAY rather than minute-of-day,
because single-stock M5 timestamps from Eightcap are stored in broker-server time
(EEST/EET, NOT real UTC) — lunch_fade's tz_convert("US/Eastern") workflow doesn't
align timestamps with NYSE wall-clock on this data shape.

Bar-index convention:
  bar 0          = first quoted broker bar after NYSE open (~09:35 ET)
  morning_end   = bar index 24 (= 120 min after first bar; approximates 11:35 ET)
  afternoon_end = bar index 48 (= 240 min; approximates 13:35 ET)
  RTH last bar  ≈ bar 77

Same threshold logic and direction null-check as parent lunch_fade.
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
    'JPM', 'BAC', 'GS',
    'V', 'MA',
    'UNH', 'WMT', 'HD', 'LOW', 'KO', 'PEP', 'JNJ',
    'XOM', 'CVX',
    'ORCL', 'CRM', 'AVGO',
]
MAG7 = {'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA'}

TIMEFRAME = 'M5'
START_DATE = '2018-01-01'
END_DATE = '2026-05-21'

MORNING_END_BAR = 24       # ~11:35 ET (120 min from broker first bar @ ~09:35 ET)
AFTERNOON_END_BAR = 48     # ~13:35 ET
MIN_MOVE_ATR = 0.25        # NDX-deployed value (cadence-passing knee)
ATR_LOOKBACK_DAYS = 20
COST_BPS_RT = 4.0          # single-stock Eightcap Phase-0 confirmed

EVENTS_PER_YEAR_ANN = 200  # ~30 per name × 24 names / ~3-4× correlation deflation


def section(t: str) -> None:
    print(f'\n{"=" * 80}\n  {t}\n{"=" * 80}\n')


def load_m5(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f'No bars for {symbol}')
    df = raw[['timestamp', 'open', 'high', 'low', 'close']].copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.set_index('timestamp').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    return df


def max_drawdown(eq: np.ndarray) -> float:
    if eq.size == 0:
        return 0.0
    rm = np.maximum.accumulate(eq)
    return float(((eq - rm) / rm).min())


def event_sharpe(pnl: np.ndarray, events_per_year: int = EVENTS_PER_YEAR_ANN) -> float:
    pnl = pnl[np.isfinite(pnl)]
    if pnl.size == 0:
        return 0.0
    std = pnl.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(pnl.mean() / std * np.sqrt(events_per_year))


def equity_curve_from_events(events_df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    if events_df.empty:
        return np.array([]), np.array([])
    daily = events_df.groupby('trade_date')['pnl'].mean().sort_index()
    eq = (1.0 + daily.values).cumprod()
    return daily.values, eq


def simulate_ticker(
    bars: pd.DataFrame,
    *,
    ticker: str,
    morning_end_bar: int = MORNING_END_BAR,
    afternoon_end_bar: int = AFTERNOON_END_BAR,
    min_move_atr: float = MIN_MOVE_ATR,
    cost_bps_rt: float = COST_BPS_RT,
    direction: str = 'fade',
    atr_lookback_days: int = ATR_LOOKBACK_DAYS,
) -> list[dict]:
    if bars.empty:
        return []
    open_arr = bars['open'].to_numpy(dtype=np.float64)
    close_arr = bars['close'].to_numpy(dtype=np.float64)
    idx = bars.index
    dates = np.asarray(idx.date)

    change = np.empty(len(idx), dtype=bool)
    change[0] = True
    change[1:] = dates[1:] != dates[:-1]
    day_starts = np.flatnonzero(change)
    day_ends = np.empty_like(day_starts)
    day_ends[:-1] = day_starts[1:]
    day_ends[-1] = len(idx)
    n_days = len(day_starts)

    # Daily vol proxy (mean abs M5 return per day).
    bar_abs_ret = np.abs(np.diff(close_arr, prepend=close_arr[0])) / np.maximum(close_arr, 1e-9)
    daily_vol = np.zeros(n_days, dtype=np.float64)
    for d_i in range(n_days):
        s, e = int(day_starts[d_i]), int(day_ends[d_i])
        daily_vol[d_i] = float(np.mean(bar_abs_ret[s:e])) if e > s else 0.0
    atr_arr = np.zeros(n_days, dtype=np.float64)
    for d_i in range(n_days):
        lo = max(0, d_i - atr_lookback_days)
        atr_arr[d_i] = float(daily_vol[lo:d_i].mean()) if d_i > 0 else 0.0

    cost_pct = cost_bps_rt / 1e4
    trades: list[dict] = []
    for d_i in range(n_days):
        s, e = int(day_starts[d_i]), int(day_ends[d_i])
        n = e - s
        if n <= afternoon_end_bar + 1:
            continue
        morning_end_idx = morning_end_bar  # bar index relative to day start
        if morning_end_idx >= n:
            continue
        open_px = float(open_arr[s])
        morning_close = float(close_arr[s + morning_end_idx])
        if open_px <= 0:
            continue
        r_morning = morning_close / open_px - 1.0
        atr_v = float(atr_arr[d_i])
        if not np.isfinite(atr_v) or atr_v <= 0:
            continue
        thr = min_move_atr * atr_v * morning_end_bar
        if abs(r_morning) < thr:
            continue
        sign_move = 1.0 if r_morning > 0 else -1.0
        pos = -sign_move if direction == 'fade' else sign_move

        entry_fill = morning_end_idx + 1
        exit_idx = min(afternoon_end_bar, n - 1)
        if entry_fill >= exit_idx:
            continue
        entry_px = float(open_arr[s + entry_fill])
        exit_px = float(close_arr[s + exit_idx])
        if entry_px <= 0:
            continue
        pnl = pos * (exit_px / entry_px - 1.0) - cost_pct
        trades.append({
            'ticker': ticker,
            'trade_date': dates[s],
            'direction': 'LONG' if pos > 0 else 'SHORT',
            'r_morning': float(r_morning),
            'entry_px': entry_px,
            'exit_px': exit_px,
            'pnl': float(pnl),
        })
    return trades


def run_backtest(
    *,
    morning_end_bar: int = MORNING_END_BAR,
    afternoon_end_bar: int = AFTERNOON_END_BAR,
    min_move_atr: float = MIN_MOVE_ATR,
    cost_bps_rt: float = COST_BPS_RT,
    direction: str = 'fade',
    cached_bars: dict[str, pd.DataFrame] | None = None,
    universe: list[str] | None = None,
    verbose: bool = False,
) -> pd.DataFrame:
    if universe is None:
        universe = UNIVERSE
    all_trades: list[dict] = []
    for tk in universe:
        if cached_bars is not None and tk in cached_bars:
            bars = cached_bars[tk]
        else:
            try:
                bars = load_m5(tk)
            except RuntimeError as e:
                if verbose:
                    print(f'  {tk}: {e}')
                continue
            if cached_bars is not None:
                cached_bars[tk] = bars
        trades = simulate_ticker(
            bars,
            ticker=tk,
            morning_end_bar=morning_end_bar,
            afternoon_end_bar=afternoon_end_bar,
            min_move_atr=min_move_atr,
            cost_bps_rt=cost_bps_rt,
            direction=direction,
        )
        if verbose:
            print(f'  {tk:<6s} bars={len(bars):>6d}  trades={len(trades):>4d}')
        all_trades.extend(trades)
    return pd.DataFrame(all_trades)


def report(label: str, ev: pd.DataFrame) -> None:
    if ev.empty:
        print(f'  [{label}] no events'); return
    e = ev.copy()
    e['trade_date'] = pd.to_datetime(e['trade_date'])
    sh = event_sharpe(e['pnl'].to_numpy())
    _, eq = equity_curve_from_events(e)
    mdd = max_drawdown(eq)
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
    if ev.empty:
        print(f'  [{label}] no events — KILL'); return
    sh = event_sharpe(ev['pnl'].to_numpy())
    _, eq = equity_curve_from_events(ev.assign(trade_date=pd.to_datetime(ev['trade_date'])))
    mdd = max_drawdown(eq)
    n = len(ev)
    wr = (ev['pnl'] > 0).mean()
    gw = float(ev.loc[ev['pnl'] > 0, 'pnl'].sum())
    gl = float(-ev.loc[ev['pnl'] <= 0, 'pnl'].sum())
    pf = gw / gl if gl > 0 else float('inf')
    v = lambda ok: 'PASS' if ok else 'FAIL'
    print(f'  [{label}]')
    print(f'    Sharpe > +0.30   : {v(sh > 0.30)}  ({sh:+.2f})')
    print(f'    Max DD < 25%     : {v(abs(mdd) < 0.25)}  ({mdd*100:+.2f}%)')
    print(f'    Events >= 200    : {v(n >= 200)}  ({n})')
    print(f'    WR>=45 or PF>=1.1: {v(wr >= 0.45 or pf >= 1.1)}  (WR {wr*100:.1f}%, PF {pf:.2f})')


def regime_breakdown(ev: pd.DataFrame) -> None:
    e = ev.copy(); e['trade_date'] = pd.to_datetime(e['trade_date'])
    for label, s, ee in [
        ('2019-2020 pre/COVID', '2019-01-01', '2020-12-31'),
        ('2021-2022 vol      ', '2021-01-01', '2022-12-31'),
        ('2023-2026 holdout  ', '2023-01-01', '2026-12-31'),
    ]:
        sub = e[(e['trade_date'] >= pd.Timestamp(s)) & (e['trade_date'] <= pd.Timestamp(ee))]
        if len(sub) < 10:
            print(f'  {label:<22s} n={len(sub):>4d}  (insufficient)'); continue
        sh = event_sharpe(sub['pnl'].to_numpy())
        _, eq = equity_curve_from_events(sub)
        mdd = max_drawdown(eq)
        print(f'  {label:<22s} n={len(sub):>4d}  Sh {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%')


def walk_forward(cache: dict[str, pd.DataFrame]) -> None:
    splits = [
        ('2021-09-01', '2024-09-01', '2026-05-21'),
        ('2022-09-01', '2025-09-01', '2026-05-21'),
        ('2021-09-01', '2023-09-01', '2025-09-01'),
    ]
    print(f'  {"split":<38s} {"IS Sh":>8s} {"OOS Sh":>8s} {"OOS n":>6s} {"OOS MDD":>10s}')
    ev_full = run_backtest(cached_bars=cache)
    ev_full['trade_date'] = pd.to_datetime(ev_full['trade_date'])
    oos_sharpes = []
    for is_s, is_e, oos_e in splits:
        is_mask = (ev_full['trade_date'] >= pd.Timestamp(is_s)) & (ev_full['trade_date'] < pd.Timestamp(is_e))
        oos_mask = (ev_full['trade_date'] >= pd.Timestamp(is_e)) & (ev_full['trade_date'] <= pd.Timestamp(oos_e))
        is_sh = event_sharpe(ev_full.loc[is_mask, 'pnl'].to_numpy())
        oos_pnl = ev_full.loc[oos_mask, 'pnl'].to_numpy()
        oos_sh = event_sharpe(oos_pnl)
        oos_n = int(oos_pnl.size)
        if oos_n:
            _, eq = equity_curve_from_events(ev_full.loc[oos_mask])
            oos_mdd = max_drawdown(eq) * 100
        else:
            oos_mdd = 0.0
        print(f'  IS {is_s[:7]}->{is_e[:7]} / OOS->{oos_e[:7]} '
              f'{is_sh:>+7.2f}  {oos_sh:>+7.2f}  {oos_n:>6d}  {oos_mdd:>+8.2f}%')
        oos_sharpes.append(oos_sh)
    mean_oos = float(np.mean(oos_sharpes)); min_oos = float(np.min(oos_sharpes))
    print(f'\n  Walk-forward mean OOS Sharpe: {mean_oos:+.2f}  (kill if < +0.20)')
    print(f'  Walk-forward min  OOS Sharpe: {min_oos:+.2f}  (kill if < -0.10)')
    if mean_oos >= 0.20 and min_oos >= -0.10:
        print('  -> PASS walk-forward.')
    else:
        print('  -> FAIL walk-forward.')


def main() -> int:
    section('Single-stock lunch fade — Phase 2 (24-name basket generalization of lunch_fade NDX)')
    cache: dict[str, pd.DataFrame] = {}
    print('  Loading 24 names + running baseline...')
    ev = run_backtest(cached_bars=cache, verbose=True)

    section('Baseline (fade, morning=24bar, afternoon=48bar, thr=0.25, cost=4bp RT)')
    report('baseline', ev)

    section('Phase 2 kill criteria')
    kill_check('baseline', ev)

    section('Regime breakdown')
    regime_breakdown(ev)

    section('Direction null-check (continuation should LOSE)')
    ev_c = run_backtest(direction='cont', cached_bars=cache)
    report('cont null', ev_c)
    base_sh = event_sharpe(ev['pnl'].to_numpy()); null_sh = event_sharpe(ev_c['pnl'].to_numpy())
    gap = base_sh - null_sh
    print(f'\n  Direction-gap (fade - cont) = {gap:+.2f}  (kill if < +0.30)')
    print(f'    -> {"PASS" if gap >= 0.30 else "FAIL"}')

    section('LONG / SHORT split (fade)')
    for d, sub in ev.groupby('direction'):
        sh = event_sharpe(sub['pnl'].to_numpy()); wr = (sub['pnl'] > 0).mean()
        print(f'  {d:<5s} n={len(sub):>4d}  Sh {sh:>+6.2f}  WR {wr*100:>5.1f}%')

    section('Mag7 vs non-Mag7 split (per lesson #44)')
    mag7_ev = ev[ev['ticker'].isin(MAG7)]
    nonmag7_ev = ev[~ev['ticker'].isin(MAG7)]
    report('Mag7', mag7_ev)
    report('non-Mag7', nonmag7_ev)

    section('Per-ticker breakdown')
    rows = []
    for tk in UNIVERSE:
        sub = ev[ev['ticker'] == tk]
        if sub.empty: continue
        sh = event_sharpe(sub['pnl'].to_numpy()); total = float(sub['pnl'].sum())
        wr = (sub['pnl'] > 0).mean()
        rows.append((tk, len(sub), sh, total, wr))
    rows.sort(key=lambda r: -r[3])
    for tk, n, sh, total, wr in rows:
        print(f'  {tk:<6s} n={n:>4d}  Sh {sh:>+6.2f}  total {total*100:>+7.2f}%  WR {wr*100:>5.1f}%')

    section('Threshold sweep (MIN_MOVE_ATR)')
    for thr in (0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50):
        ev_v = run_backtest(min_move_atr=thr, cached_bars=cache)
        sh = event_sharpe(ev_v['pnl'].to_numpy())
        _, eq = equity_curve_from_events(ev_v.assign(trade_date=pd.to_datetime(ev_v['trade_date'])))
        mdd = max_drawdown(eq) if eq.size else 0.0
        print(f'  thr={thr:>4.2f}  Sh {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  n {len(ev_v):>5d}')

    section('Afternoon-exit sweep')
    for ae in (36, 42, 48, 54, 60, 72):
        ev_v = run_backtest(afternoon_end_bar=ae, cached_bars=cache)
        sh = event_sharpe(ev_v['pnl'].to_numpy())
        print(f'  afternoon={ae:>3d}bar  Sh {sh:>+6.2f}  n {len(ev_v):>5d}')

    section('Cost sensitivity')
    for c in (0.0, 2.0, 4.0, 8.0, 15.0):
        ev_v = run_backtest(cost_bps_rt=c, cached_bars=cache)
        sh = event_sharpe(ev_v['pnl'].to_numpy())
        print(f'  cost={c:>5.1f}bp  Sh {sh:>+6.2f}  n {len(ev_v):>5d}')

    section('Phase 6 — walk-forward')
    walk_forward(cache)

    section('Summary')
    sh = event_sharpe(ev['pnl'].to_numpy())
    _, eq = equity_curve_from_events(ev.assign(trade_date=pd.to_datetime(ev['trade_date'])))
    mdd = max_drawdown(eq)
    years = (pd.to_datetime(ev['trade_date'].max()) - pd.to_datetime(ev['trade_date'].min())).days / 365.25
    print(f'  single_stock_lunch_fade: Sharpe {sh:+.2f}  MDD {mdd*100:+.2f}%  '
          f'n {len(ev)} ({len(ev)/max(years,1e-9):.1f}/yr)  dir-gap {gap:+.2f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
