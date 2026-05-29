#!/usr/bin/env python3
"""
FX lunch-fade on EURUSD / GBPUSD / USDJPY (M5).

Thesis: experiments/fx_lunch_fade/fx_lunch_fade.md

Mechanism: fade the 08:00-12:00 ET morning move during the 12:00-13:00 ET
NY-lunch / London-handoff vacuum window. Direct port of NDX lunch_fade template
to spot FX. Strong prior against (lesson #1 + sharpened lesson #48); running
to definitively close the FX-lunch-fade question.

Run:
    FX_SYMBOL=EURUSD venv/Scripts/python.exe experiments/fx_lunch_fade/fx_lunch_fade_demo.py
    FX_SYMBOL=GBPUSD venv/Scripts/python.exe experiments/fx_lunch_fade/fx_lunch_fade_demo.py
    FX_SYMBOL=USDJPY venv/Scripts/python.exe experiments/fx_lunch_fade/fx_lunch_fade_demo.py
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

SYMBOL = os.environ.get("FX_SYMBOL", "EURUSD")
TIMEFRAME = "M5"
START_DATE = "2019-01-01"
END_DATE = "2026-05-23"

# FX intraday window for the lunch-fade test
SESSION_OPEN = dtime(8, 0)       # 08:00 ET — NY arrival
SESSION_CLOSE = dtime(13, 0)     # 13:00 ET — end of NY-lunch vacuum
SESSION_TZ = "US/Eastern"

SESSION_MINUTES = (
    (SESSION_CLOSE.hour * 60 + SESSION_CLOSE.minute)
    - (SESSION_OPEN.hour * 60 + SESSION_OPEN.minute)
)
BARS_PER_DAY = SESSION_MINUTES // 5  # 60 bars in 08:00-13:00 ET window
DAYS_PER_YEAR = 252
BARS_PER_YEAR = BARS_PER_DAY * DAYS_PER_YEAR

MORNING_END_MIN = 240            # 240min after 08:00 ET = 12:00 ET
AFTERNOON_END_MIN = 300          # 300min after 08:00 ET = 13:00 ET
MIN_MOVE_ATR = 0.5
ATR_LOOKBACK_DAYS = 20

PIP_SIZE = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "USDJPY": 0.01,
    "AUDUSD": 0.0001,
    "USDCHF": 0.0001,
}

COST_PIPS_ROUND_TRIP = 1.0       # 1 pip RT — realistic retail cost on FX majors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f"\n{'=' * 80}\n  {t}\n{'=' * 80}\n")


def pip(symbol: str) -> float:
    return PIP_SIZE.get(symbol, 0.0001)


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
    df = df.loc[(t >= SESSION_OPEN) & (t < SESSION_CLOSE)]
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
    session_open_min = SESSION_OPEN.hour * 60 + SESSION_OPEN.minute
    h = np.asarray(idx.hour, dtype=np.int32)
    m = np.asarray(idx.minute, dtype=np.int32)
    return h * 60 + m - session_open_min


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

def simulate_fx_lunch_fade(
    bars: pd.DataFrame,
    pip_size: float,
    morning_end_min: int = MORNING_END_MIN,
    afternoon_end_min: int = AFTERNOON_END_MIN,
    min_move_atr: float = MIN_MOVE_ATR,
    cost_pips: float = COST_PIPS_ROUND_TRIP,
    direction: str = "fade",
    atr_lookback_days: int = ATR_LOOKBACK_DAYS,
    long_only: bool = False,
    short_only: bool = False,
) -> tuple[pd.Series, list[dict]]:
    """Numpy-inner-loop FX lunch-fade simulator.

    Per day: measure 08:00 -> 12:00 ET return; if |r| > ATR-proxy threshold,
    take opposite position at next bar open. Exit at 13:00 ET bar close.
    """
    idx = bars.index
    n_bars = len(bars)
    if n_bars == 0:
        return pd.Series(dtype=float, name="fxlf_ret"), []

    open_arr = bars["open"].to_numpy(dtype=np.float64)
    close_arr = bars["close"].to_numpy(dtype=np.float64)
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

    cost_price_unit = cost_pips * pip_size  # absolute price cost (RT)

    for d_i in range(n_days):
        s, e = int(day_starts[d_i]), int(day_ends[d_i])
        n = e - s
        if n < morning_bars + 4:
            continue

        day_mod = minute_of_day[s:e]
        day_close = close_arr[s:e]
        day_open = open_arr[s:e]

        cand_m = np.flatnonzero(day_mod >= morning_end_min)
        if cand_m.size == 0:
            continue
        morning_end_bar = int(cand_m[0]) - 1
        if morning_end_bar <= 0 or morning_end_bar + 1 >= n:
            continue

        open_px = float(day_open[0])
        morning_close = float(day_close[morning_end_bar])
        if open_px <= 0:
            continue
        r_morning = morning_close / open_px - 1.0

        atr_m5 = float(atr_arr[d_i])
        if not np.isfinite(atr_m5) or atr_m5 <= 0:
            continue
        thr = min_move_atr * atr_m5 * morning_bars
        if abs(r_morning) < thr:
            continue

        sign_move = 1.0 if r_morning > 0 else -1.0
        pos = -sign_move if direction == "fade" else sign_move
        if long_only and pos < 0:
            continue
        if short_only and pos > 0:
            continue

        cand_a = np.flatnonzero(day_mod >= afternoon_end_min)
        if cand_a.size == 0:
            # no exit bar inside session — use last bar of day
            exit_bar = n - 1
        else:
            exit_bar = int(cand_a[0])
        entry_fill = morning_end_bar + 1
        if entry_fill >= exit_bar:
            continue

        entry_px = float(day_open[entry_fill])
        exit_px = float(day_close[exit_bar])

        cost_ret = cost_price_unit / entry_px
        pnl = pos * (exit_px / entry_px - 1.0) - cost_ret

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
            "r_morning": r_morning,
            "pnl_pct": float(pnl),
            "reason": "afternoon",
        })

    return pd.Series(ret_arr, index=idx, name="fxlf_ret"), trades


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
    print(f"    WR>=50 or PF>=1.05  : {v(wr >= 0.50 or pf >= 1.05)}  "
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
    section(f"Loading {SYMBOL} M5 (FX 08:00-13:00 ET window)")
    try:
        bars = load_m5(SYMBOL)
    except RuntimeError as e:
        print(f"  {e}")
        return 1
    print(f"  bars     : {len(bars):,}")
    print(f"  range    : {bars.index[0]} -> {bars.index[-1]}")
    print(f"  days     : {len(set(bars.index.date))}")
    print(f"  pip size : {pip(SYMBOL)}")

    ps = pip(SYMBOL)

    section("Baseline (fade, morning=240min[12:00ET], afternoon=300min[13:00ET], thr=0.5, cost=1pip)")
    r, t = simulate_fx_lunch_fade(bars, pip_size=ps)
    report_run("baseline", r, t)

    section("Phase 2 kill-criteria")
    kill_criteria_check("baseline", r, t)

    section("Regime breakdown")
    regime_breakdown(r, t)

    section("Variant sweep — morning measurement window (min)")
    for me in (120, 180, 240, 300):
        r_v, t_v = simulate_fx_lunch_fade(bars, pip_size=ps, morning_end_min=me)
        sh = annualized_sharpe(r_v.to_numpy())
        mdd = max_drawdown((1 + r_v).cumprod().to_numpy())
        print(f"  morning={me:>3d}min  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  trades {len(t_v):>4d}")

    section("Variant sweep — afternoon exit (min into 08:00 ET session)")
    for ae in (240, 270, 300, 330):
        r_v, t_v = simulate_fx_lunch_fade(bars, pip_size=ps, afternoon_end_min=ae)
        sh = annualized_sharpe(r_v.to_numpy())
        mdd = max_drawdown((1 + r_v).cumprod().to_numpy())
        print(f"  afternoon={ae:>3d}min  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  trades {len(t_v):>4d}")

    section("Variant sweep — threshold (MIN_MOVE_ATR)")
    for thr in (0.0, 0.15, 0.25, 0.4, 0.5, 0.75, 1.0):
        r_v, t_v = simulate_fx_lunch_fade(bars, pip_size=ps, min_move_atr=thr)
        sh = annualized_sharpe(r_v.to_numpy())
        mdd = max_drawdown((1 + r_v).cumprod().to_numpy())
        print(f"  thr={thr:>4.2f}  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  trades {len(t_v):>4d}")

    section("Variant sweep — cost sensitivity (pips RT)")
    for c in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0):
        r_v, t_v = simulate_fx_lunch_fade(bars, pip_size=ps, cost_pips=c)
        sh = annualized_sharpe(r_v.to_numpy())
        print(f"  cost={c:>3.1f}pip  Sharpe {sh:>+6.2f}  trades {len(t_v):>4d}")

    section("Null-check — continuation direction")
    r_n, t_n = simulate_fx_lunch_fade(bars, pip_size=ps, direction="cont")
    report_run("cont", r_n, t_n)
    base_sh = annualized_sharpe(r.to_numpy())
    null_sh = annualized_sharpe(r_n.to_numpy())
    gap = base_sh - null_sh
    print(f"\n  direction-gap (fade - cont) = {gap:+.2f}")
    if gap >= 0.30:
        print("    PASS: fade signal has directional content.")
    elif gap <= -0.30:
        print("    INVERTED: continuation wins — thesis sign is wrong.")
    else:
        print("    FAIL: |gap| < 0.30 — no directional content.")

    section("Long/short asymmetry split (baseline fade)")
    r_l, t_l = simulate_fx_lunch_fade(bars, pip_size=ps, long_only=True)
    r_s, t_s = simulate_fx_lunch_fade(bars, pip_size=ps, short_only=True)
    print(f"  LONG-only   Sharpe {annualized_sharpe(r_l.to_numpy()):+.2f}  "
          f"MDD {max_drawdown((1+r_l).cumprod().to_numpy())*100:+.2f}%  "
          f"trades {len(t_l)}")
    print(f"  SHORT-only  Sharpe {annualized_sharpe(r_s.to_numpy()):+.2f}  "
          f"MDD {max_drawdown((1+r_s).cumprod().to_numpy())*100:+.2f}%  "
          f"trades {len(t_s)}")

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
