#!/usr/bin/env python3
"""
ORB Compression / Inside-Day Fade -- companion to experiments/orb (GER40 only).

Thesis: experiments/orb_compression/orb_compression.md

Rules:
  Opening range = first OR_MINUTES of session (same as parent orb_dax).
  An "inside day" = no M5 close outside [OR_low, OR_high] during
                    [or_end, snapshot_min). I.e. parent ORB did not fire either side.
  Snapshot trade taken on inside-days at the bar after mod == snapshot_min.
  Direction (fade): short if close > OR_mid, long if close < OR_mid.
  Direction (continuation, null check): inverse.
  Stop: same-side OR boundary breakout (close beyond OR boundary toward us).
  Exit: stop hit, OR T+tod_exit_minutes after entry, OR 17:25 Berlin hard flat.
  Max 1 trade per inside-day. Flat overnight.

Cost model: 1 index point round-trip applied as return drag of COST_PT / entry_px.

Expects ohlc_data/GER40_M5.csv produced by scripts/mt5_fetch.py.
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

SYMBOL = os.environ.get("ORB_SYMBOL", "GER40")
TIMEFRAME = "M5"
START_DATE = "2019-01-01"
END_DATE = "2026-04-18"

OR_MINUTES = 30
SNAPSHOT_MIN = 180          # 12:00 Berlin (parent strategy's entry cutoff)
TOD_EXIT_MIN = 180          # T+180min after entry, like parent
EXIT_MIN_BEFORE_CLOSE = 5   # 17:25 Berlin hard flat

# Berlin RTH (Xetra cash session). Hard-coded; this strategy is GER40-only.
RTH_OPEN = dtime(9, 0)
RTH_CLOSE = dtime(17, 30)
SESSION_TZ = "Europe/Berlin"

COST_POINTS_ROUND_TRIP = 1.0

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
        raise RuntimeError(f"No bars for {symbol} {TIMEFRAME}")
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

def simulate_compression(
    bars: pd.DataFrame,
    or_minutes: int = OR_MINUTES,
    snapshot_min: int = SNAPSHOT_MIN,
    tod_exit_minutes: int = TOD_EXIT_MIN,
    exit_min_before_close: int = EXIT_MIN_BEFORE_CLOSE,
    cost_points: float = COST_POINTS_ROUND_TRIP,
    mode: str = "fade",           # 'fade' or 'continuation' (null)
    direction: str = "both",      # 'both' / 'long' / 'short'
    min_or_width_pct: float | None = None,
    max_or_width_pct: float | None = None,
) -> tuple[pd.Series, list[dict]]:
    """Inside-day snapshot fade simulator (numpy inner loop).

    Per day: build OR, classify inside-day (no closes outside OR during
    [or_end, snapshot_min)), if inside take a snapshot trade at bar after
    mod==snapshot_min. Stop at same-side OR break; exit at T+tod_exit or 17:25.

    Returns (bar_ret, trades) on the same schema as orb_demo.simulate_orb.
    """
    idx = bars.index
    n_bars = len(bars)
    if n_bars == 0:
        return pd.Series(dtype=float, name="comp_ret"), []

    open_arr = bars["open"].to_numpy(dtype=np.float64)
    high_arr = bars["high"].to_numpy(dtype=np.float64)
    low_arr = bars["low"].to_numpy(dtype=np.float64)
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

    ret_arr = np.zeros(n_bars, dtype=np.float64)
    trades: list[dict] = []

    rth_minutes = rth_close_min - rth_open_min
    exit_cutoff = rth_minutes - exit_min_before_close
    or_end = or_minutes
    long_ok = direction in ("both", "long")
    short_ok = direction in ("both", "short")
    has_width_min = min_or_width_pct is not None
    has_width_max = max_or_width_pct is not None
    is_fade = (mode == "fade")

    n_inside_days = 0

    for d_i in range(len(day_starts)):
        s = int(day_starts[d_i])
        e = int(day_ends[d_i])
        n = e - s
        if n < (or_end // 5) + 4:
            continue

        day_open = open_arr[s:e]
        day_high = high_arr[s:e]
        day_low = low_arr[s:e]
        day_close = close_arr[s:e]
        day_mod = minute_of_day[s:e]

        or_mask = day_mod < or_end
        if not or_mask.any():
            continue
        or_high = float(day_high[or_mask].max())
        or_low = float(day_low[or_mask].min())
        if not (np.isfinite(or_high) and np.isfinite(or_low)) or or_high <= or_low:
            continue
        or_width = or_high - or_low
        or_mid = 0.5 * (or_high + or_low)

        # Inside-day check: no close outside OR during [or_end, snapshot_min).
        window_mask = (day_mod >= or_end) & (day_mod < snapshot_min)
        if not window_mask.any():
            continue
        window_closes = day_close[window_mask]
        broke_up = bool(np.any(window_closes > or_high))
        broke_dn = bool(np.any(window_closes < or_low))
        if broke_up or broke_dn:
            continue  # parent ORB owns this day

        n_inside_days += 1

        # Snapshot bar: closest bar with mod >= snapshot_min.
        snap_idx_arr = np.flatnonzero(day_mod >= snapshot_min)
        if snap_idx_arr.size == 0 or snap_idx_arr[0] + 1 >= n:
            continue
        snap_i = int(snap_idx_arr[0])
        snap_close = float(day_close[snap_i])
        entry_i = snap_i + 1
        entry_px = float(day_open[entry_i])

        # Width filter.
        if has_width_min and or_width / entry_px < min_or_width_pct:
            continue
        if has_width_max and or_width / entry_px > max_or_width_pct:
            continue

        # Direction logic.
        if snap_close > or_mid:
            # fade => SHORT, continuation => LONG
            pos = -1 if is_fade else 1
        elif snap_close < or_mid:
            pos = 1 if is_fade else -1
        else:
            continue  # exactly on midpoint, no signal

        if pos == 1 and not long_ok:
            continue
        if pos == -1 and not short_ok:
            continue

        # Stop = same-side OR boundary breakout direction.
        # For fade SHORT (price in upper half): stop = OR_high (a close above OR_high).
        # We approximate with bar high/low touch -> conservative.
        if pos == 1:
            stop_px = or_low
        else:
            stop_px = or_high

        position = pos
        entry_bar_i = entry_i

        # Walk forward bars.
        for j in range(entry_i, n):
            mod_j = int(day_mod[j])
            is_last = (j == n - 1)
            bar_h = day_high[j]
            bar_l = day_low[j]

            if j > entry_i:
                prev_close = day_close[j - 1]
                cur_close = day_close[j]
                ret_arr[s + j] = position * (cur_close - prev_close) / prev_close

            if position == 1:
                hit_stop = bar_l <= stop_px
            else:
                hit_stop = bar_h >= stop_px
            tod_forced = (j - entry_bar_i) * 5 >= tod_exit_minutes
            forced_close = (mod_j >= exit_cutoff) or is_last or tod_forced

            if hit_stop or forced_close:
                if hit_stop:
                    exit_px = stop_px
                    exit_reason = "stop"
                elif tod_forced:
                    exit_px = float(day_close[j])
                    exit_reason = "tod"
                else:
                    exit_px = float(day_close[j])
                    exit_reason = "eod"
                if j > entry_i:
                    prev_close = day_close[j - 1]
                    ret_arr[s + j] = position * (exit_px - prev_close) / prev_close
                else:
                    ret_arr[s + j] = position * (exit_px - entry_px) / entry_px
                cost_ret = cost_points / entry_px
                ret_arr[s + j] -= cost_ret
                trades.append({
                    "date": dates[s],
                    "direction": "LONG" if position == 1 else "SHORT",
                    "entry_ts": idx[s + entry_i],
                    "exit_ts": idx[s + j],
                    "entry_px": entry_px,
                    "exit_px": float(exit_px),
                    "or_high": or_high,
                    "or_low": or_low,
                    "or_width_pct": or_width / entry_px,
                    "snap_close": snap_close,
                    "pnl_pct": position * (exit_px - entry_px) / entry_px - cost_ret,
                    "reason": exit_reason,
                })
                break

    bar_ret = pd.Series(ret_arr, index=idx, name="comp_ret")
    bar_ret.attrs["inside_days"] = n_inside_days
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
    if "inside_days" in bar_ret.attrs:
        print(f"    inside days : {bar_ret.attrs['inside_days']}")


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
    print(f"    Sharpe > 0.30       : {v(sh > 0.30)}  ({sh:+.2f})")
    print(f"    Max DD < 25%        : {v(abs(mdd) < 0.25)}  ({mdd * 100:+.2f}%)")
    print(f"    Trades >= 100       : {v(n_trades >= 100)}  ({n_trades})")
    print(f"    WR>=38 or PF>=1.1   : {v(win_rate >= 0.38 or pf >= 1.1)}  "
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
    section(f"Loading {SYMBOL} {TIMEFRAME} (Berlin RTH)")
    bars = load_m5(SYMBOL)
    n_days = len(set(bars.index.date))
    print(f"  bars     : {len(bars):,}")
    print(f"  range    : {bars.index[0]} -> {bars.index[-1]}")
    print(f"  days     : {n_days}")

    section("Baseline (snapshot=180, T+180 exit, fade, both, cost=1pt)")
    bar_ret, trades = simulate_compression(bars)
    report_run("baseline-fade", bar_ret, trades)

    section("Phase 2 kill-criteria")
    kill_criteria_check("baseline-fade", bar_ret, trades)

    section("Regime breakdown (baseline-fade)")
    regime_breakdown(bar_ret, trades)

    section("Null check: continuation (same setup, opposite direction)")
    bar_ret_cont, trades_cont = simulate_compression(bars, mode="continuation")
    report_run("continuation-null", bar_ret_cont, trades_cont)
    sh_fade = annualized_sharpe(bar_ret.to_numpy())
    sh_cont = annualized_sharpe(bar_ret_cont.to_numpy())
    print(f"\n  fade-gap (fade - continuation) Sharpe: {sh_fade - sh_cont:+.2f}")
    print(f"    (must be >= +0.30 for directional content to be considered real)")

    section("Long/short asymmetry (fade)")
    for d in ("long", "short"):
        r_v, t_v = simulate_compression(bars, direction=d)
        eq = (1.0 + r_v).cumprod()
        sh = annualized_sharpe(r_v.to_numpy())
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in t_v if t["pnl_pct"] > 0) / max(len(t_v), 1)
        print(f"  dir={d:<5s}  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  "
              f"trades {len(t_v):>4d}  WR {wr*100:>4.1f}%")

    section("Snapshot timing sweep (fade, both, T+180)")
    for snap in (120, 150, 180, 210, 240, 300):
        r_v, t_v = simulate_compression(bars, snapshot_min=snap)
        eq = (1.0 + r_v).cumprod()
        sh = annualized_sharpe(r_v.to_numpy())
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in t_v if t["pnl_pct"] > 0) / max(len(t_v), 1)
        n_inside = r_v.attrs.get("inside_days", 0)
        print(f"  snap={snap:>3d}min  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  "
              f"trades {len(t_v):>4d}  WR {wr*100:>4.1f}%  inside_days {n_inside}")

    section("Time-exit sweep (fade, both, snapshot=180)")
    for tex in (30, 60, 120, 180, 240, 999):
        # 999 = effectively EOD (will hit exit_cutoff first)
        r_v, t_v = simulate_compression(bars, tod_exit_minutes=tex)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        label = "EOD" if tex == 999 else f"T+{tex}"
        print(f"  exit={label:>5s}  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  trades {len(t_v):>4d}")

    section("OR-width filter sweep (fade, both, snapshot=180, T+180)")
    # Compression-within-compression: does narrower OR yield tighter fade?
    width_bands = [
        ("all",            None, None),
        ("<= 0.50%",       None, 0.0050),
        ("<= 0.75%",       None, 0.0075),
        ("<= 1.00%",       None, 0.0100),
        (">= 0.30%",       0.0030, None),
        ("0.30%-0.75%",    0.0030, 0.0075),
        (">= 0.75%",       0.0075, None),
    ]
    for label, wmin, wmax in width_bands:
        r_v, t_v = simulate_compression(bars, min_or_width_pct=wmin, max_or_width_pct=wmax)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in t_v if t["pnl_pct"] > 0) / max(len(t_v), 1)
        print(f"  width={label:<14s}  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  "
              f"trades {len(t_v):>4d}  WR {wr*100:>4.1f}%")

    section("Cost sensitivity (baseline-fade)")
    for c in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0):
        r_v, t_v = simulate_compression(bars, cost_points=c)
        sh = annualized_sharpe(r_v.to_numpy())
        print(f"  cost={c:>3.1f}pt  Sharpe {sh:>+6.2f}  trades {len(t_v):>4d}")

    section("Top variants — regime breakdown")
    candidates: list[tuple[str, dict]] = [
        ("fade-both-T180",   dict()),
        ("fade-long-T180",   dict(direction="long")),
        ("fade-short-T180",  dict(direction="short")),
        ("fade-both-EOD",    dict(tod_exit_minutes=999)),
        ("fade-long-EOD",    dict(direction="long", tod_exit_minutes=999)),
    ]
    for cname, kwargs in candidates:
        r_v, t_v = simulate_compression(bars, **kwargs)
        print(f"\n  -- {cname} --")
        regime_breakdown(r_v, t_v)

    section("Summary (baseline-fade)")
    eq = (1.0 + bar_ret).cumprod()
    years = (bar_ret.index[-1] - bar_ret.index[0]).days / 365.25
    total = float(eq.iloc[-1] - 1.0)
    cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
    print(f"  baseline-fade : CAGR {cagr * 100:+.2f}%  Sharpe {annualized_sharpe(bar_ret.to_numpy()):+.2f}  "
          f"MDD {max_drawdown(eq.to_numpy()) * 100:+.2f}%  "
          f"trades {len(trades)} ({len(trades) / max(years, 1e-9):.1f}/year)")
    print(f"  fade-gap      : {sh_fade - sh_cont:+.2f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
