#!/usr/bin/env python3
"""
End-of-Day Leverage Unwind on index CFDs (M5) -- Phase 2 demo (instrument-agnostic).

Thesis: experiments/eod_unwind/eod_unwind.md

Rules:
  At ENTRY_MIN_BEFORE_CLOSE minutes before RTH close, take the day-move
  (session_open -> current bar close). If |day_move| >= MIN_MOVE_ATR * ATR20,
  enter:
    - direction='fade'  : position = -sign(day_move)   (baseline, unwind hypothesis)
    - direction='cont'  : position = +sign(day_move)   (null-check)
  Exit by exit_mode:
    - 'eod'        : flat at T - EXIT_MIN_BEFORE_CLOSE
    - 't15'        : 15 min after entry (or EOD, whichever first)
    - 't30'        : 30 min after entry (or EOD, whichever first)
    - 'overnight'  : carry to next RTH session's open
  One trade per day max.

Cost: 1 index point round-trip (pessimistic retail CFD), applied as cost/entry_px.

Expects data at ``ohlc_data/<SYMBOL>_M5.csv``.

Instrument + session via env vars. Examples::

    EOD_SYMBOL=SPX500 python experiments/eod_unwind/eod_unwind_demo.py
    EOD_SYMBOL=NDX100 python experiments/eod_unwind/eod_unwind_demo.py
    EOD_SYMBOL=GER40  EOD_SESSION=EU python experiments/eod_unwind/eod_unwind_demo.py
    EOD_SYMBOL=UK100  EOD_SESSION=UK python experiments/eod_unwind/eod_unwind_demo.py
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

SYMBOL = os.environ.get("EOD_SYMBOL", "SPX500")
TIMEFRAME = "M5"
START_DATE = "2019-01-01"
END_DATE = "2026-04-18"

ENTRY_MIN_BEFORE_CLOSE = 45
MIN_MOVE_ATR = 0.5
EXIT_MIN_BEFORE_CLOSE = 5
ATR_LOOKBACK_DAYS = 20

COST_POINTS_ROUND_TRIP = 1.0

SESSIONS = {
    "US": (dtime(9, 30), dtime(16, 0), "US/Eastern"),
    "EU": (dtime(9, 0), dtime(17, 30), "Europe/Berlin"),
    "UK": (dtime(8, 0), dtime(16, 30), "Europe/London"),
}
SESSION_KEY = os.environ.get("EOD_SESSION", "US").upper()
if SESSION_KEY not in SESSIONS:
    raise RuntimeError(f"Unknown EOD_SESSION={SESSION_KEY!r}; options: {list(SESSIONS)}")
RTH_OPEN, RTH_CLOSE, SESSION_TZ = SESSIONS[SESSION_KEY]

_rth_minutes = (RTH_CLOSE.hour * 60 + RTH_CLOSE.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)
BARS_PER_DAY = _rth_minutes // 5
DAYS_PER_YEAR = 252
BARS_PER_YEAR = BARS_PER_DAY * DAYS_PER_YEAR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f"\n{'=' * 80}\n  {t}\n{'=' * 80}\n")


def load_m5(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(
            f"No bars for {symbol} {TIMEFRAME}. Fetch with:\n"
            f"  python scripts/mt5_fetch.py --symbols {symbol} --timeframes M5 "
            f"--from {START_DATE}"
        )
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df.index = df.index.tz_convert(SESSION_TZ)
    times = df.index.time
    mask = (times >= RTH_OPEN) & (times < RTH_CLOSE)
    df = df.loc[mask]
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


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

def simulate_eod_unwind(
    bars: pd.DataFrame,
    entry_min_before_close: int = ENTRY_MIN_BEFORE_CLOSE,
    min_move_atr: float = MIN_MOVE_ATR,
    exit_mode: str = "eod",                     # 'eod' | 't15' | 't30' | 'overnight'
    direction: str = "fade",                    # 'fade' | 'cont'
    cost_points: float = COST_POINTS_ROUND_TRIP,
    exit_min_before_close: int = EXIT_MIN_BEFORE_CLOSE,
    atr_lookback: int = ATR_LOOKBACK_DAYS,
    leg: str = "both",                          # 'both' | 'long' | 'short'
) -> tuple[pd.Series, list[dict]]:
    """Bar-level EOD-unwind simulator — numpy inner loop.

    Returns
    -------
    bar_ret : pd.Series
        Bar-by-bar strategy return (net of costs), indexed by bar timestamp.
    trades : list[dict]
    """
    idx = bars.index
    n_bars = len(bars)
    if n_bars == 0:
        return pd.Series(dtype=float, name="eod_ret"), []

    open_arr = bars["open"].to_numpy(dtype=np.float64)
    close_arr = bars["close"].to_numpy(dtype=np.float64)

    rth_open_min = RTH_OPEN.hour * 60 + RTH_OPEN.minute
    rth_close_min = RTH_CLOSE.hour * 60 + RTH_CLOSE.minute
    hours = np.asarray(idx.hour, dtype=np.int32)
    minutes = np.asarray(idx.minute, dtype=np.int32)
    minute_of_day = hours * 60 + minutes - rth_open_min

    dates = np.asarray(idx.date)
    change = np.empty(n_bars, dtype=bool)
    change[0] = True
    change[1:] = dates[1:] != dates[:-1]
    day_starts = np.flatnonzero(change)
    day_ends = np.empty_like(day_starts)
    day_ends[:-1] = day_starts[1:]
    day_ends[-1] = n_bars

    n_days = len(day_starts)

    # Per-day daily-closes and ATR (rolling mean of |close-prev_close|) for threshold.
    daily_close = np.empty(n_days, dtype=np.float64)
    daily_open = np.empty(n_days, dtype=np.float64)
    for d_i in range(n_days):
        s = int(day_starts[d_i])
        e = int(day_ends[d_i])
        daily_open[d_i] = open_arr[s]
        daily_close[d_i] = close_arr[e - 1]
    abs_move = np.abs(np.diff(daily_close, prepend=daily_close[0]))
    atr_arr = np.zeros(n_days, dtype=np.float64)
    for d_i in range(n_days):
        lo = max(0, d_i - atr_lookback)
        if d_i == 0:
            atr_arr[d_i] = 0.0
        else:
            atr_arr[d_i] = abs_move[lo:d_i].mean()  # prior-day ATR (no look-ahead)

    rth_minutes = rth_close_min - rth_open_min
    entry_target_mod = rth_minutes - entry_min_before_close  # minutes-since-open
    exit_cutoff_mod = rth_minutes - exit_min_before_close

    ret_arr = np.zeros(n_bars, dtype=np.float64)
    trades: list[dict] = []

    # Pre-compute per-day entry bar index (first bar with mod >= entry_target_mod).
    for d_i in range(n_days):
        s = int(day_starts[d_i])
        e = int(day_ends[d_i])
        n = e - s
        if n < 4:
            continue

        day_open_px = daily_open[d_i]
        atr_px = atr_arr[d_i]
        if not np.isfinite(atr_px) or atr_px <= 0:
            continue

        day_mod = minute_of_day[s:e]
        day_close = close_arr[s:e]

        # Entry bar: first bar where mod >= entry_target_mod.
        candidates = np.flatnonzero(day_mod >= entry_target_mod)
        if candidates.size == 0:
            continue
        entry_bar = int(candidates[0])
        if entry_bar + 1 >= n:
            continue

        entry_close_mod = int(day_mod[entry_bar])
        if entry_close_mod >= exit_cutoff_mod:
            continue

        day_move_px = float(day_close[entry_bar]) - float(day_open_px)
        if abs(day_move_px) < min_move_atr * atr_px:
            continue

        sign_move = 1.0 if day_move_px > 0 else -1.0
        if direction == "fade":
            pos = -sign_move
        elif direction == "cont":
            pos = sign_move
        else:
            raise ValueError(f"unknown direction {direction!r}")

        if leg == "long" and pos < 0:
            continue
        if leg == "short" and pos > 0:
            continue

        # Enter on next bar open.
        entry_fill_i = entry_bar + 1
        entry_px = float(open_arr[s + entry_fill_i])

        # Find exit bar by mode.
        if exit_mode == "eod":
            mask = day_mod >= exit_cutoff_mod
            cand = np.flatnonzero(mask)
            if cand.size == 0:
                exit_bar = n - 1
            else:
                exit_bar = int(cand[0])
            # Exit at close of that bar.
            exit_px = float(day_close[exit_bar])
            exit_global_i = s + exit_bar
            exit_reason = "eod"
        elif exit_mode == "overnight":
            # Hold to next day's first-bar open.
            if d_i + 1 >= n_days:
                exit_bar = n - 1
                exit_px = float(day_close[exit_bar])
                exit_global_i = s + exit_bar
                exit_reason = "eod-safety"
            else:
                exit_global_i = int(day_starts[d_i + 1])
                exit_px = float(open_arr[exit_global_i])
                exit_bar = None
                exit_reason = "overnight"
        elif exit_mode in ("t15", "t30"):
            minutes_hold = 15 if exit_mode == "t15" else 30
            bars_hold = minutes_hold // 5
            tod_bar = entry_fill_i + bars_hold
            eod_mask = day_mod >= exit_cutoff_mod
            eod_cand = np.flatnonzero(eod_mask)
            eod_bar = int(eod_cand[0]) if eod_cand.size > 0 else n - 1
            exit_bar = min(tod_bar, eod_bar, n - 1)
            exit_px = float(day_close[exit_bar])
            exit_global_i = s + exit_bar
            exit_reason = exit_mode if exit_bar < eod_bar else "eod"
        else:
            raise ValueError(f"unknown exit_mode {exit_mode!r}")

        cost_ret = cost_points / entry_px
        pnl = pos * (exit_px - entry_px) / entry_px - cost_ret

        # Write bar-by-bar returns over the holding window (continuous-session portion).
        # For overnight, only the intraday leg is recorded as bar returns; the gap return
        # is appended to the entry-day last bar to keep bar_ret aligned with idx.
        if exit_mode == "overnight":
            # Intraday portion: entry_fill_i .. n-1 on day d_i using close-to-close.
            for j in range(entry_fill_i, n):
                if j == entry_fill_i:
                    prev_px = entry_px
                else:
                    prev_px = day_close[j - 1]
                ret_arr[s + j] = pos * (day_close[j] - prev_px) / prev_px
            # Apply cost on the intraday final bar; overnight gap in next-day first bar.
            ret_arr[s + n - 1] -= cost_ret
            next_s = int(day_starts[d_i + 1]) if d_i + 1 < n_days else None
            if next_s is not None:
                gap_prev = float(day_close[n - 1])
                gap_next = float(open_arr[next_s])
                ret_arr[next_s] = pos * (gap_next - gap_prev) / gap_prev
        else:
            # Continuous intraday hold.
            end_j = exit_bar
            for j in range(entry_fill_i, end_j + 1):
                if j == entry_fill_i:
                    prev_px = entry_px
                else:
                    prev_px = day_close[j - 1]
                if j == end_j:
                    ret_arr[s + j] = pos * (exit_px - prev_px) / prev_px - cost_ret
                else:
                    ret_arr[s + j] = pos * (day_close[j] - prev_px) / prev_px

        trades.append({
            "date": dates[s],
            "direction": "LONG" if pos > 0 else "SHORT",
            "entry_ts": idx[s + entry_fill_i],
            "exit_ts": idx[exit_global_i],
            "entry_px": float(entry_px),
            "exit_px": float(exit_px),
            "day_move_px": float(day_move_px),
            "atr_px": float(atr_px),
            "day_move_atr": float(day_move_px / atr_px) if atr_px > 0 else 0.0,
            "pnl_pct": float(pnl),
            "reason": exit_reason,
        })

    bar_ret = pd.Series(ret_arr, index=idx, name="eod_ret")
    return bar_ret, trades


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
    n_trades = len(trades)
    trades_per_week = n_trades / (years * 52) if years > 0 else 0.0
    wins = [t for t in trades if t["pnl_pct"] > 0]
    win_rate = len(wins) / n_trades if n_trades else 0.0
    gross_win = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gross_loss = -sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0)
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    avg_win = np.mean([t["pnl_pct"] for t in wins]) if wins else 0.0
    losses = [t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0]
    avg_loss = np.mean(losses) if losses else 0.0

    print(f"  [{label}]")
    print(f"    period      : {bar_ret.index[0].date()} -> {bar_ret.index[-1].date()} ({years:.1f}y)")
    print(f"    total ret   : {total * 100:+.2f}%")
    print(f"    CAGR        : {cagr * 100:+.2f}%")
    print(f"    Sharpe      : {sh:+.2f}")
    print(f"    Max DD      : {mdd * 100:+.2f}%")
    print(f"    trades      : {n_trades}  ({trades_per_week:.2f}/week)")
    print(f"    win rate    : {win_rate * 100:.1f}%")
    print(f"    profit fac. : {pf:.2f}")
    print(f"    avg win     : {avg_win * 100:+.3f}%   avg loss: {avg_loss * 100:+.3f}%")


def kill_criteria_check(label: str, bar_ret: pd.Series, trades: list[dict]) -> None:
    sh = annualized_sharpe(bar_ret.to_numpy())
    eq = (1.0 + bar_ret).cumprod()
    mdd = max_drawdown(eq.to_numpy())
    n_trades = len(trades)
    wins = [t for t in trades if t["pnl_pct"] > 0]
    win_rate = len(wins) / n_trades if n_trades else 0.0
    gw = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gl = -sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0)
    pf = gw / gl if gl > 0 else float("inf")

    def v(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    print(f"  [{label}]")
    print(f"    Sharpe > 0.30         : {v(sh > 0.30)}  ({sh:+.2f})")
    print(f"    Max DD < 25%          : {v(abs(mdd) < 0.25)}  ({mdd * 100:+.2f}%)")
    print(f"    Trades >= 200         : {v(n_trades >= 200)}  ({n_trades})")
    print(f"    WR>=48 or PF>=1.05    : {v(win_rate >= 0.48 or pf >= 1.05)}  "
          f"(WR {win_rate * 100:.1f}%, PF {pf:.2f})")


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
    section(f"Loading {SYMBOL} {TIMEFRAME}")
    try:
        bars = load_m5(SYMBOL)
    except RuntimeError as e:
        print(f"  {e}")
        return 1
    print(f"  bars     : {len(bars):,}")
    print(f"  range    : {bars.index[0]} -> {bars.index[-1]}")
    print(f"  session  : {bars.index.time.min()} -> {bars.index.time.max()} ({SESSION_TZ})")
    print(f"  days     : {len(set(bars.index.date))}")

    section("Baseline (fade, entry=T-45min, min_move=0.5*ATR, EOD exit, cost=1pt)")
    bar_ret, trades = simulate_eod_unwind(bars)
    report_run("baseline", bar_ret, trades)

    section("Phase 2 kill-criteria")
    kill_criteria_check("baseline", bar_ret, trades)

    section("Regime breakdown")
    regime_breakdown(bar_ret, trades)

    section("Variant sweep — entry timing (min before close)")
    for em in (30, 45, 60, 90):
        r_v, t_v = simulate_eod_unwind(bars, entry_min_before_close=em)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        print(f"  T-{em:>3d}min  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  trades {len(t_v):>4d}")

    section("Variant sweep — threshold (|day_move| / ATR20)")
    for thr in (0.0, 0.25, 0.5, 1.0, 1.5):
        r_v, t_v = simulate_eod_unwind(bars, min_move_atr=thr)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        print(f"  thr={thr:>4.2f}  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  trades {len(t_v):>4d}")

    section("Variant sweep — exit mode")
    for ex in ("eod", "t15", "t30", "overnight"):
        r_v, t_v = simulate_eod_unwind(bars, exit_mode=ex)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        print(f"  exit={ex:<10s}  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  trades {len(t_v):>4d}")

    section("Variant sweep — cost sensitivity")
    for cost in (0.5, 1.0, 2.0, 3.0):
        r_v, t_v = simulate_eod_unwind(bars, cost_points=cost)
        sh = annualized_sharpe(r_v.to_numpy())
        print(f"  cost={cost:>3.1f}pt  Sharpe {sh:>+6.2f}  trades {len(t_v):>4d}")

    section("Null-check — continuation direction (same thresholds, opposite sign)")
    r_null, t_null = simulate_eod_unwind(bars, direction="cont")
    report_run("continuation", r_null, t_null)
    baseline_sh = annualized_sharpe(bar_ret.to_numpy())
    null_sh = annualized_sharpe(r_null.to_numpy())
    gap = baseline_sh - null_sh
    print(f"\n  fade-gap (baseline - continuation) = {gap:+.2f}")
    if gap >= 0.30:
        print(f"    PASS: fade signal has directional content (gap >= +0.30).")
    elif gap <= -0.30:
        print(f"    INVERTED: continuation wins — thesis sign is wrong.")
    else:
        print(f"    FAIL: |gap| < 0.30 — no directional content, noise trading.")

    section("Overnight-confound check (exit=overnight vs exit=eod)")
    r_on, t_on = simulate_eod_unwind(bars, exit_mode="overnight")
    r_eod, t_eod = simulate_eod_unwind(bars, exit_mode="eod")
    sh_on = annualized_sharpe(r_on.to_numpy())
    sh_eod = annualized_sharpe(r_eod.to_numpy())
    print(f"  EOD exit Sharpe     : {sh_eod:+.2f}")
    print(f"  Overnight Sharpe    : {sh_on:+.2f}")
    if sh_on > sh_eod + 0.15:
        print(f"  CONFOUND: overnight drift dominates — not the unwind mechanism.")
    elif sh_eod > sh_on + 0.15:
        print(f"  OK: EOD exit wins — mechanism is intraday-specific, as predicted.")
    else:
        print(f"  INDETERMINATE: EOD vs overnight within 0.15 Sharpe — weak evidence.")

    section("Summary")
    years = (bar_ret.index[-1] - bar_ret.index[0]).days / 365.25
    eq = (1.0 + bar_ret).cumprod()
    total = float(eq.iloc[-1] - 1.0)
    cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
    print(f"  baseline : CAGR {cagr * 100:+.2f}%  Sharpe {annualized_sharpe(bar_ret.to_numpy()):+.2f}  "
          f"MDD {max_drawdown(eq.to_numpy()) * 100:+.2f}%  "
          f"trades {len(trades)} ({len(trades) / max(years * 52, 1e-9):.2f}/week)  "
          f"fade-gap {gap:+.2f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
