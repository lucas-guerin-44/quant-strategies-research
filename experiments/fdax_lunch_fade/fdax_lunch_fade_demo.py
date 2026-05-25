#!/usr/bin/env python3
"""FDAX (GER40) lunch fade — Berlin lunch-vacuum basis-arb test (lesson #48).

Direct sibling of deployed NDX100 lunch_fade. Same mechanism (morning move →
fade during institutional lunch vacuum), different instrument + timezone:

  - Session: 09:00-17:30 Europe/Berlin (Xetra cash + FDAX-tied CFD)
  - Morning end: 12:00 CET (180 min into session)
  - Afternoon end: 13:30 CET (270 min into session)
  - thr=0.25 (NDX-deployed baseline; sweep too)
  - cost=1pt RT (GER40 CFD retail typical)

If this works, lesson #48 generalization is confirmed and book gets a sibling
basis-arb-MR strategy. If it fails, lesson #48 is sharpened to "NDX/NQ-specific".
"""
from __future__ import annotations

import os
import sys
from datetime import time as dtime

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))

from utils import fetch_ohlc  # noqa: E402


SYMBOL = 'GER40'
TIMEFRAME = 'M5'
START_DATE = '2019-01-01'
END_DATE = '2026-04-18'

RTH_OPEN = dtime(9, 0)
RTH_CLOSE = dtime(17, 30)
SESSION_TZ = 'Europe/Berlin'

RTH_MINUTES = (RTH_CLOSE.hour * 60 + RTH_CLOSE.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)
BARS_PER_DAY = RTH_MINUTES // 5
DAYS_PER_YEAR = 252
BARS_PER_YEAR = BARS_PER_DAY * DAYS_PER_YEAR

MORNING_END_MIN = 180        # 12:00 CET
AFTERNOON_END_MIN = 270      # 13:30 CET
MIN_MOVE_ATR = 0.25          # NDX-deployed knee
COST_POINTS_ROUND_TRIP = 1.0
ATR_LOOKBACK_DAYS = 20


def section(t: str) -> None:
    print(f'\n{"=" * 80}\n  {t}\n{"=" * 80}\n')


def load_m5(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f'No bars for {symbol} {TIMEFRAME}.')
    df = raw[['timestamp', 'open', 'high', 'low', 'close']].copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.set_index('timestamp').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    df.index = df.index.tz_convert(SESSION_TZ)
    t = df.index.time
    df = df.loc[(t >= RTH_OPEN) & (t < RTH_CLOSE)]
    df = df.loc[df.index.dayofweek < 5]
    return df


def max_drawdown(eq: np.ndarray) -> float:
    rm = np.maximum.accumulate(eq)
    dd = (eq - rm) / rm
    return float(dd.min()) if len(dd) else 0.0


def annualized_sharpe(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if r.size == 0: return 0.0
    s = r.std(ddof=1)
    if s == 0 or not np.isfinite(s): return 0.0
    return float(r.mean() / s * np.sqrt(BARS_PER_YEAR))


def compute_day_groups(idx: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dates = np.asarray(idx.date)
    n = len(idx)
    change = np.empty(n, dtype=bool)
    change[0] = True
    change[1:] = dates[1:] != dates[:-1]
    day_starts = np.flatnonzero(change)
    day_ends = np.empty_like(day_starts)
    day_ends[:-1] = day_starts[1:]
    day_ends[-1] = n
    return dates, day_starts, day_ends


def compute_minute_of_day(idx: pd.DatetimeIndex) -> np.ndarray:
    rth_open_min = RTH_OPEN.hour * 60 + RTH_OPEN.minute
    h = np.asarray(idx.hour, dtype=np.int32)
    m = np.asarray(idx.minute, dtype=np.int32)
    return h * 60 + m - rth_open_min


def simulate_lunch_fade(
    bars: pd.DataFrame,
    morning_end_min: int = MORNING_END_MIN,
    afternoon_end_min: int = AFTERNOON_END_MIN,
    min_move_atr: float = MIN_MOVE_ATR,
    cost_points: float = COST_POINTS_ROUND_TRIP,
    direction: str = 'fade',
    atr_lookback_days: int = ATR_LOOKBACK_DAYS,
    long_only: bool = False,
    short_only: bool = False,
) -> tuple[pd.Series, list[dict]]:
    idx = bars.index
    n_bars = len(bars)
    if n_bars == 0: return pd.Series(dtype=float, name='lf_ret'), []

    open_arr = bars['open'].to_numpy(dtype=np.float64)
    close_arr = bars['close'].to_numpy(dtype=np.float64)
    minute_of_day = compute_minute_of_day(idx)
    dates, day_starts, day_ends = compute_day_groups(idx)

    bar_abs_ret = np.abs(np.diff(close_arr, prepend=close_arr[0])) / np.maximum(close_arr, 1e-9)
    n_days = len(day_starts)
    daily_vol = np.zeros(n_days, dtype=np.float64)
    for d_i in range(n_days):
        s, e = int(day_starts[d_i]), int(day_ends[d_i])
        daily_vol[d_i] = np.mean(bar_abs_ret[s:e]) if e > s else 0.0
    atr_arr = np.zeros(n_days, dtype=np.float64)
    for d_i in range(n_days):
        lo = max(0, d_i - atr_lookback_days)
        atr_arr[d_i] = daily_vol[lo:d_i].mean() if d_i > 0 else 0.0

    morning_bars = morning_end_min // 5
    ret_arr = np.zeros(n_bars, dtype=np.float64)
    trades: list[dict] = []

    for d_i in range(n_days):
        s, e = int(day_starts[d_i]), int(day_ends[d_i])
        n = e - s
        if n < morning_bars + 4: continue

        day_mod = minute_of_day[s:e]
        day_close = close_arr[s:e]
        day_open = open_arr[s:e]

        cand_m = np.flatnonzero(day_mod >= morning_end_min)
        if cand_m.size == 0: continue
        morning_end_bar = int(cand_m[0]) - 1
        if morning_end_bar <= 0 or morning_end_bar + 1 >= n: continue

        open_px = float(day_open[0])
        morning_close = float(day_close[morning_end_bar])
        if open_px <= 0: continue
        r_morning = morning_close / open_px - 1.0

        atr_m5 = float(atr_arr[d_i])
        if not np.isfinite(atr_m5) or atr_m5 <= 0: continue
        thr = min_move_atr * atr_m5 * morning_bars
        if abs(r_morning) < thr: continue

        sign_move = 1.0 if r_morning > 0 else -1.0
        pos = -sign_move if direction == 'fade' else sign_move
        if long_only and pos < 0: continue
        if short_only and pos > 0: continue

        cand_a = np.flatnonzero(day_mod >= afternoon_end_min)
        if cand_a.size == 0: continue
        exit_bar = int(cand_a[0])
        entry_fill = morning_end_bar + 1
        if entry_fill >= exit_bar: continue

        entry_px = float(day_open[entry_fill])
        exit_px = float(day_close[exit_bar])

        cost_ret = cost_points / entry_px
        pnl = pos * (exit_px / entry_px - 1.0) - cost_ret

        for j in range(entry_fill, exit_bar + 1):
            prev = entry_px if j == entry_fill else day_close[j - 1]
            cur = exit_px if j == exit_bar else day_close[j]
            step = pos * (cur - prev) / prev
            if j == exit_bar: step -= cost_ret
            ret_arr[s + j] = step

        trades.append({
            'date': dates[s],
            'direction': 'LONG' if pos > 0 else 'SHORT',
            'entry_ts': idx[s + entry_fill],
            'exit_ts': idx[s + exit_bar],
            'entry_px': entry_px,
            'exit_px': exit_px,
            'r_morning': r_morning,
            'pnl_pct': float(pnl),
        })

    return pd.Series(ret_arr, index=idx, name='lf_ret'), trades


def report_run(label: str, bar_ret: pd.Series, trades: list[dict]) -> None:
    eq = (1.0 + bar_ret).cumprod()
    years = (bar_ret.index[-1] - bar_ret.index[0]).days / 365.25
    total = float(eq.iloc[-1] - 1.0)
    cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
    sh = annualized_sharpe(bar_ret.to_numpy())
    mdd = max_drawdown(eq.to_numpy())
    n = len(trades)
    tpw = n / (years * 52) if years > 0 else 0.0
    wins = [t for t in trades if t['pnl_pct'] > 0]
    wr = len(wins) / n if n else 0.0
    gw = sum(t['pnl_pct'] for t in trades if t['pnl_pct'] > 0)
    gl = -sum(t['pnl_pct'] for t in trades if t['pnl_pct'] < 0)
    pf = gw / gl if gl > 0 else float('inf')
    avg_w = np.mean([t['pnl_pct'] for t in wins]) if wins else 0.0
    losses = [t['pnl_pct'] for t in trades if t['pnl_pct'] <= 0]
    avg_l = np.mean(losses) if losses else 0.0
    print(f'  [{label}]')
    print(f'    period      : {bar_ret.index[0].date()} -> {bar_ret.index[-1].date()} ({years:.1f}y)')
    print(f'    total ret   : {total * 100:+.2f}%')
    print(f'    CAGR        : {cagr * 100:+.2f}%')
    print(f'    Sharpe      : {sh:+.2f}')
    print(f'    Max DD      : {mdd * 100:+.2f}%')
    print(f'    trades      : {n}  ({tpw:.2f}/week)')
    print(f'    win rate    : {wr * 100:.1f}%')
    print(f'    profit fac. : {pf:.2f}')
    print(f'    avg win     : {avg_w * 100:+.3f}%   avg loss: {avg_l * 100:+.3f}%')


def kill_criteria_check(label: str, bar_ret: pd.Series, trades: list[dict]) -> None:
    sh = annualized_sharpe(bar_ret.to_numpy())
    eq = (1.0 + bar_ret).cumprod()
    mdd = max_drawdown(eq.to_numpy())
    n = len(trades)
    wins = [t for t in trades if t['pnl_pct'] > 0]
    wr = len(wins) / n if n else 0.0
    gw = sum(t['pnl_pct'] for t in trades if t['pnl_pct'] > 0)
    gl = -sum(t['pnl_pct'] for t in trades if t['pnl_pct'] < 0)
    pf = gw / gl if gl > 0 else float('inf')
    v = lambda ok: 'PASS' if ok else 'FAIL'
    print(f'  [{label}]')
    print(f'    Sharpe > +0.30      : {v(sh > 0.30)}  ({sh:+.2f})')
    print(f'    Max DD < 25%        : {v(abs(mdd) < 0.25)}  ({mdd * 100:+.2f}%)')
    print(f'    Trades >= 200       : {v(n >= 200)}  ({n})')
    print(f'    WR>=45 or PF>=1.10  : {v(wr >= 0.45 or pf >= 1.10)}  (WR {wr * 100:.1f}%, PF {pf:.2f})')


def regime_breakdown(bar_ret: pd.Series, trades: list[dict]) -> None:
    windows = [
        ('2019-2020 pre/COVID', '2019-01-01', '2020-12-31'),
        ('2021-2022 vol      ', '2021-01-01', '2022-12-31'),
        ('2023-2026 holdout  ', '2023-01-01', '2026-12-31'),
    ]
    for label, s, e in windows:
        sub_ret = bar_ret.loc[s:e]
        sub_trades = [t for t in trades if s <= str(t['date']) <= e]
        if len(sub_ret) < 200:
            print(f'  {label} (insufficient bars)')
            continue
        eq = (1.0 + sub_ret).cumprod()
        years = (sub_ret.index[-1] - sub_ret.index[0]).days / 365.25
        cagr = (float(eq.iloc[-1])) ** (1 / max(years, 1e-9)) - 1
        sh = annualized_sharpe(sub_ret.to_numpy())
        mdd = max_drawdown(eq.to_numpy())
        print(f'  {label} CAGR {cagr * 100:>+7.2f}%  Sharpe {sh:>+6.2f}  '
              f'MDD {mdd * 100:>+7.2f}%  trades {len(sub_trades):>4d}')


def main() -> int:
    section(f'Loading {SYMBOL} M5 (Xetra session 09:00-17:30 CET)')
    bars = load_m5(SYMBOL)
    print(f'  bars     : {len(bars):,}')
    print(f'  range    : {bars.index[0]} -> {bars.index[-1]}')
    print(f'  days     : {len(set(bars.index.date))}')

    section('Baseline (fade, morning=180min/12:00 CET, afternoon=270min/13:30 CET, thr=0.25, cost=1pt)')
    r, t = simulate_lunch_fade(bars)
    report_run('baseline', r, t)

    section('Phase 2 kill-criteria')
    kill_criteria_check('baseline', r, t)

    section('Regime breakdown')
    regime_breakdown(r, t)

    section('Variant sweep — threshold (MIN_MOVE_ATR)')
    for thr in (0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75):
        r_v, t_v = simulate_lunch_fade(bars, min_move_atr=thr)
        sh = annualized_sharpe(r_v.to_numpy())
        mdd = max_drawdown((1 + r_v).cumprod().to_numpy())
        print(f'  thr={thr:>4.2f}  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  trades {len(t_v):>4d}')

    section('Variant sweep — morning measurement window (min into Xetra session)')
    for me in (120, 150, 180, 210, 240):
        r_v, t_v = simulate_lunch_fade(bars, morning_end_min=me)
        sh = annualized_sharpe(r_v.to_numpy())
        mdd = max_drawdown((1 + r_v).cumprod().to_numpy())
        cet_h = 9 + me // 60; cet_m = me % 60
        print(f'  morning={me:>3d}min ({cet_h:02d}:{cet_m:02d} CET)  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  trades {len(t_v):>4d}')

    section('Variant sweep — afternoon exit (min into Xetra session)')
    for ae in (210, 240, 270, 300, 360, 420):
        r_v, t_v = simulate_lunch_fade(bars, afternoon_end_min=ae)
        sh = annualized_sharpe(r_v.to_numpy())
        mdd = max_drawdown((1 + r_v).cumprod().to_numpy())
        cet_h = 9 + ae // 60; cet_m = ae % 60
        print(f'  afternoon={ae:>3d}min ({cet_h:02d}:{cet_m:02d} CET)  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  trades {len(t_v):>4d}')

    section('Variant sweep — cost sensitivity (pts RT)')
    for c in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0):
        r_v, t_v = simulate_lunch_fade(bars, cost_points=c)
        sh = annualized_sharpe(r_v.to_numpy())
        print(f'  cost={c:>3.1f}pt  Sharpe {sh:>+6.2f}  trades {len(t_v):>4d}')

    section('Null-check — continuation direction (opposite sign)')
    r_n, t_n = simulate_lunch_fade(bars, direction='cont')
    report_run('cont', r_n, t_n)
    base_sh = annualized_sharpe(r.to_numpy())
    null_sh = annualized_sharpe(r_n.to_numpy())
    gap = base_sh - null_sh
    print(f'\n  direction-gap (fade - cont) = {gap:+.2f}  (kill if < +0.30)')
    if gap >= 0.30:
        print('    PASS: fade direction has decisive directional content.')
    elif gap <= -0.30:
        print('    INVERTED: continuation wins — lesson #48 generalization REFUTED on FDAX.')
    else:
        print('    FAIL: |gap| < 0.30 — no decisive direction.')

    section('Long/short asymmetry split (fade)')
    r_l, t_l = simulate_lunch_fade(bars, long_only=True)
    r_s, t_s = simulate_lunch_fade(bars, short_only=True)
    print(f'  LONG-only   Sharpe {annualized_sharpe(r_l.to_numpy()):+.2f}  '
          f'MDD {max_drawdown((1+r_l).cumprod().to_numpy())*100:+.2f}%  '
          f'trades {len(t_l)}')
    print(f'  SHORT-only  Sharpe {annualized_sharpe(r_s.to_numpy()):+.2f}  '
          f'MDD {max_drawdown((1+r_s).cumprod().to_numpy())*100:+.2f}%  '
          f'trades {len(t_s)}')

    section('Summary')
    eq = (1 + r).cumprod()
    years = (r.index[-1] - r.index[0]).days / 365.25
    print(f'  fdax_lunch_fade baseline: CAGR {(float(eq.iloc[-1])) ** (1/max(years,1e-9)) - 1:+.2%}  '
          f'Sharpe {base_sh:+.2f}  MDD {max_drawdown(eq.to_numpy())*100:+.2f}%  '
          f'trades {len(t)} ({len(t)/max(years*52,1e-9):.2f}/week)  '
          f'dir-gap {gap:+.2f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
