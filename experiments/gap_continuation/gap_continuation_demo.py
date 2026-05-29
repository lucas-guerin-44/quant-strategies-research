#!/usr/bin/env python3
"""
Overnight gap continuation on US index CFDs (M5).

Thesis: experiments/gap_continuation/gap_continuation.md

Mechanism: 15:55-ET prior close → 09:30-ET current open gap is information-
loaded (Asia/EU overnight + earnings + macro). Continuation thesis: ride the
gap direction through the first 60-240 min of the session.

Default symbol SPX500; set GAP_SYMBOL=NDX100 for tech.

Run:
    venv/Scripts/python.exe experiments/gap_continuation/gap_continuation_demo.py
    GAP_SYMBOL=NDX100 venv/Scripts/python.exe experiments/gap_continuation/gap_continuation_demo.py
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

from data import fetch_ohlc  # noqa: E402


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SYMBOL = os.environ.get("GAP_SYMBOL", "SPX500")
TIMEFRAME = "M5"
START_DATE = "2019-01-01"
END_DATE = "2026-04-18"

RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)
SESSION_TZ = "US/Eastern"

RTH_MINUTES = (RTH_CLOSE.hour * 60 + RTH_CLOSE.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)
BARS_PER_DAY = RTH_MINUTES // 5
DAYS_PER_YEAR = 252
BARS_PER_YEAR = BARS_PER_DAY * DAYS_PER_YEAR

HOLD_MINUTES = 120
MIN_GAP_ATR = 0.5
COST_POINTS_ROUND_TRIP = 1.0
ATR_LOOKBACK_DAYS = 20
# Overnight is ~17.5h vs 6.5h RTH = 17.5/6.5 ≈ 2.7x the day's bars worth of price
# evolution. We scale the threshold by sqrt of bar-equivalents.
OVERNIGHT_BAR_EQUIVALENT = 210


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f"\n{'=' * 80}\n  {t}\n{'=' * 80}\n")


def load_m5(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f"No bars for {symbol} {TIMEFRAME}.")
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
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
    if r.size == 0:
        return 0.0
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(BARS_PER_YEAR))


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


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

def simulate_gap_continuation(
    bars: pd.DataFrame,
    hold_minutes: int = HOLD_MINUTES,
    min_gap_atr: float = MIN_GAP_ATR,
    cost_points: float = COST_POINTS_ROUND_TRIP,
    direction: str = "cont",           # 'cont' (baseline) | 'fade'
    atr_lookback_days: int = ATR_LOOKBACK_DAYS,
    long_only: bool = False,
    short_only: bool = False,
) -> tuple[pd.Series, list[dict]]:
    """Numpy-inner-loop overnight gap continuation simulator.

    Per day:
      1. gap = day_open[0] / prev_day_close[-1] - 1
      2. Threshold = MIN_GAP_ATR * atr_m5_proxy * sqrt(OVERNIGHT_BAR_EQUIVALENT)
      3. If |gap| >= threshold: enter cont (or fade in null mode) at day_open[0]
      4. Exit at first bar with mod >= hold_minutes (or last bar if hold beyond
         session), last close.
    """
    idx = bars.index
    n_bars = len(bars)
    if n_bars == 0:
        return pd.Series(dtype=float, name="gc_ret"), []

    open_arr = bars["open"].to_numpy(dtype=np.float64)
    close_arr = bars["close"].to_numpy(dtype=np.float64)
    minute_of_day = compute_minute_of_day(idx)
    dates, day_starts, day_ends = compute_day_groups(idx)

    # Per-day ATR proxy: mean |bar-to-bar return| within day, then 20-day rolling mean.
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

    ret_arr = np.zeros(n_bars, dtype=np.float64)
    trades: list[dict] = []

    for d_i in range(1, n_days):  # start at 1 — need prior day's close for gap
        s, e = int(day_starts[d_i]), int(day_ends[d_i])
        n = e - s
        if n < 10:
            continue

        # Prior day's last close.
        prev_s, prev_e = int(day_starts[d_i - 1]), int(day_ends[d_i - 1])
        if prev_e <= prev_s:
            continue
        prev_close = float(close_arr[prev_e - 1])
        if prev_close <= 0:
            continue

        day_mod = minute_of_day[s:e]
        day_close = close_arr[s:e]
        day_open = open_arr[s:e]

        today_open = float(day_open[0])
        gap_pct = today_open / prev_close - 1.0

        atr_m5 = float(atr_arr[d_i])
        if not np.isfinite(atr_m5) or atr_m5 <= 0:
            continue
        threshold = min_gap_atr * atr_m5 * np.sqrt(OVERNIGHT_BAR_EQUIVALENT)
        if abs(gap_pct) < threshold:
            continue

        sign_gap = 1.0 if gap_pct > 0 else -1.0
        pos = sign_gap if direction == "cont" else -sign_gap
        if long_only and pos < 0:
            continue
        if short_only and pos > 0:
            continue

        # Exit bar = first bar at or after hold_minutes; or last bar.
        cand = np.flatnonzero(day_mod >= hold_minutes)
        exit_bar = int(cand[0]) if cand.size > 0 else n - 1
        if exit_bar <= 0:
            continue

        # Entry at today's open (bar 0 open). Fill price = day_open[0].
        entry_fill = 0
        entry_px = today_open
        exit_px = float(day_close[exit_bar])

        cost_ret = cost_points / entry_px
        pnl = pos * (exit_px / entry_px - 1.0) - cost_ret

        # Bar-by-bar accrual for accurate Sharpe denominator.
        for j in range(entry_fill, exit_bar + 1):
            prev = entry_px if j == entry_fill else day_close[j - 1]
            cur = exit_px if j == exit_bar else day_close[j]
            step = pos * (cur - prev) / prev
            if j == exit_bar:
                step -= cost_ret
            ret_arr[s + j] = step

        trades.append({
            "date": dates[s],
            "direction": "LONG" if pos > 0 else "SHORT",
            "entry_ts": idx[s + entry_fill],
            "exit_ts": idx[s + exit_bar],
            "entry_px": entry_px,
            "exit_px": exit_px,
            "gap_pct": float(gap_pct),
            "threshold": float(threshold),
            "pnl_pct": float(pnl),
            "reason": "tod",
        })

    return pd.Series(ret_arr, index=idx, name="gc_ret"), trades


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_run(label: str, bar_ret: pd.Series, trades: list[dict]) -> None:
    eq = (1.0 + bar_ret).cumprod()
    years = (bar_ret.index[-1] - bar_ret.index[0]).days / 365.25
    total = float(eq.iloc[-1] - 1.0)
    cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
    sh = annualized_sharpe(bar_ret.to_numpy())
    mdd = max_drawdown(eq.to_numpy())
    n = len(trades)
    tpw = n / (years * 52) if years > 0 else 0.0
    wins = [t for t in trades if t["pnl_pct"] > 0]
    wr = len(wins) / n if n else 0.0
    gw = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gl = -sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0)
    pf = gw / gl if gl > 0 else float("inf")
    avg_w = np.mean([t["pnl_pct"] for t in wins]) if wins else 0.0
    losses = [t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0]
    avg_l = np.mean(losses) if losses else 0.0
    print(f"  [{label}]")
    print(f"    period      : {bar_ret.index[0].date()} -> {bar_ret.index[-1].date()} ({years:.1f}y)")
    print(f"    total ret   : {total * 100:+.2f}%")
    print(f"    CAGR        : {cagr * 100:+.2f}%")
    print(f"    Sharpe      : {sh:+.2f}")
    print(f"    Max DD      : {mdd * 100:+.2f}%")
    print(f"    trades      : {n}  ({tpw:.2f}/week)")
    print(f"    win rate    : {wr * 100:.1f}%")
    print(f"    profit fac. : {pf:.2f}")
    print(f"    avg win     : {avg_w * 100:+.3f}%   avg loss: {avg_l * 100:+.3f}%")


def kill_criteria_check(label: str, bar_ret: pd.Series, trades: list[dict]) -> None:
    sh = annualized_sharpe(bar_ret.to_numpy())
    eq = (1.0 + bar_ret).cumprod()
    mdd = max_drawdown(eq.to_numpy())
    n = len(trades)
    wins = [t for t in trades if t["pnl_pct"] > 0]
    wr = len(wins) / n if n else 0.0
    gw = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gl = -sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0)
    pf = gw / gl if gl > 0 else float("inf")

    def v(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    print(f"  [{label}]")
    print(f"    Sharpe > 0.30       : {v(sh > 0.30)}  ({sh:+.2f})")
    print(f"    Max DD < 25%        : {v(abs(mdd) < 0.25)}  ({mdd * 100:+.2f}%)")
    print(f"    Trades >= 200       : {v(n >= 200)}  ({n})")
    print(f"    WR>=48 or PF>=1.05  : {v(wr >= 0.48 or pf >= 1.05)}  "
          f"(WR {wr * 100:.1f}%, PF {pf:.2f})")


def regime_breakdown(bar_ret: pd.Series, trades: list[dict]) -> None:
    windows = [
        ("2019-2020 pre/COVID", "2019-01-01", "2020-12-31"),
        ("2021-2022 vol",       "2021-01-01", "2022-12-31"),
        ("2023-2026 holdout",   "2023-01-01", "2026-12-31"),
    ]
    for label, s, e in windows:
        sub_ret = bar_ret.loc[s:e]
        sub_trades = [t for t in trades if s <= str(t["date"]) <= e]
        if len(sub_ret) < 200:
            print(f"  {label:<22s} (insufficient bars)")
            continue
        eq = (1.0 + sub_ret).cumprod()
        years = (sub_ret.index[-1] - sub_ret.index[0]).days / 365.25
        cagr = (float(eq.iloc[-1])) ** (1 / max(years, 1e-9)) - 1
        sh = annualized_sharpe(sub_ret.to_numpy())
        mdd = max_drawdown(eq.to_numpy())
        print(f"  {label:<22s} CAGR {cagr * 100:>+7.2f}%  Sharpe {sh:>+6.2f}  "
              f"MDD {mdd * 100:>+7.2f}%  trades {len(sub_trades):>4d}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section(f"Loading {SYMBOL} M5 (US session, 09:30-16:00 ET)")
    try:
        bars = load_m5(SYMBOL)
    except RuntimeError as e:
        print(f"  {e}")
        return 1
    print(f"  bars     : {len(bars):,}")
    print(f"  range    : {bars.index[0]} -> {bars.index[-1]}")
    print(f"  days     : {len(set(bars.index.date))}")

    section("Baseline (cont, hold=120min=11:30ET exit, thr=0.5, cost=1pt)")
    r, t = simulate_gap_continuation(bars)
    report_run("baseline", r, t)

    section("Phase 2 kill-criteria")
    kill_criteria_check("baseline", r, t)

    section("Regime breakdown")
    regime_breakdown(r, t)

    section("Variant sweep — hold window (min)")
    for hm in (30, 60, 90, 120, 180, 240, 300):
        r_v, t_v = simulate_gap_continuation(bars, hold_minutes=hm)
        sh = annualized_sharpe(r_v.to_numpy())
        mdd = max_drawdown((1 + r_v).cumprod().to_numpy())
        et_h = 9 + (30 + hm) // 60
        et_m = (30 + hm) % 60
        print(f"  hold={hm:>3d}min (exit {et_h:02d}:{et_m:02d} ET)  "
              f"Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  trades {len(t_v):>4d}")

    section("Variant sweep — threshold (MIN_GAP_ATR)")
    for thr in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5):
        r_v, t_v = simulate_gap_continuation(bars, min_gap_atr=thr)
        sh = annualized_sharpe(r_v.to_numpy())
        mdd = max_drawdown((1 + r_v).cumprod().to_numpy())
        print(f"  thr={thr:>4.2f}  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  trades {len(t_v):>4d}")

    section("Variant sweep — cost sensitivity")
    for c in (0.5, 1.0, 2.0, 3.0):
        r_v, t_v = simulate_gap_continuation(bars, cost_points=c)
        sh = annualized_sharpe(r_v.to_numpy())
        print(f"  cost={c:>3.1f}pt  Sharpe {sh:>+6.2f}  trades {len(t_v):>4d}")

    section("Null-check — fade direction (opposite sign of continuation)")
    r_n, t_n = simulate_gap_continuation(bars, direction="fade")
    report_run("fade", r_n, t_n)
    base_sh = annualized_sharpe(r.to_numpy())
    null_sh = annualized_sharpe(r_n.to_numpy())
    gap = base_sh - null_sh
    print(f"\n  direction-gap (cont - fade) = {gap:+.2f}")
    if gap >= 0.30:
        print("    PASS: continuation signal has directional content.")
    elif gap <= -0.30:
        print("    INVERTED: fade wins — thesis sign is wrong.")
    else:
        print("    FAIL: |gap| < 0.30 — no directional content.")

    section("Long/short asymmetry split (baseline cont)")
    r_l, t_l = simulate_gap_continuation(bars, long_only=True)
    r_s, t_s = simulate_gap_continuation(bars, short_only=True)
    print(f"  LONG-only   (long after gap-up)   Sharpe {annualized_sharpe(r_l.to_numpy()):+.2f}  "
          f"MDD {max_drawdown((1+r_l).cumprod().to_numpy())*100:+.2f}%  trades {len(t_l)}")
    print(f"  SHORT-only  (short after gap-dn)  Sharpe {annualized_sharpe(r_s.to_numpy()):+.2f}  "
          f"MDD {max_drawdown((1+r_s).cumprod().to_numpy())*100:+.2f}%  trades {len(t_s)}")

    section("Summary")
    eq = (1 + r).cumprod()
    years = (r.index[-1] - r.index[0]).days / 365.25
    print(f"  {SYMBOL} baseline : CAGR {(float(eq.iloc[-1])) ** (1/max(years,1e-9)) - 1:+.2%}  "
          f"Sharpe {base_sh:+.2f}  MDD {max_drawdown(eq.to_numpy())*100:+.2f}%  "
          f"trades {len(t)} ({len(t)/max(years*52,1e-9):.2f}/week)  "
          f"dir-gap {gap:+.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
