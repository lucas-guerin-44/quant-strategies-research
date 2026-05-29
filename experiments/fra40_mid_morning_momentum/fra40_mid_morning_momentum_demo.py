#!/usr/bin/env python3
"""
FRA40 mid-morning momentum — CFD-session first-hour drift.

Thesis: experiments/fra40_mid_morning_momentum/fra40_mid_morning_momentum.md

Mechanism:
  The direction of the first ~60 min of the FRA40 CFD session (starting at
  ~09:00 UTC = 10:00-11:00 Paris local) persists over the next ~2-3 hours.
  Same mechanism family as orb_dax (GER40 opening-impulse Sh +0.76), but
  measured through the CFD-lens rather than the cash-auction lens — the CFD
  session first bar arrives 1-2h after the Euronext Paris cash open, so
  we test residual morning momentum rather than primary opening impulse.

Rules:
  Session start = first bar at or after 09:00 UTC (the CFD day-open).
  Measure return over the first MEASURE_BARS of the session.
  If |return| >= ATR_THRESHOLD * atr_proxy: take trade in that direction.
  Hold for HOLD_BARS after the measurement window ends.
  Exit at hold-end (no intra-trade stop — pure directional hold).
  Flat overnight.

Cost model: 1.5 index point round-trip applied as return drag of COST_PT / entry_px.
  FRA40 level ~8400, so 1.5pt ≈ 1.8bp RT.

Expects ohlc_data/FRA40_M5.csv produced by scripts/mt5_fetch.py.
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

SYMBOL = os.environ.get("FRA40_SYMBOL", "FRA40")
TIMEFRAME = "M5"
START_DATE = "2019-01-01"
END_DATE = "2026-04-18"

# Session start (CFD day-open). FRA40 CFD first bar arrives at ~09:00 UTC.
SESSION_START_UTC = dtime(9, 0)

# Measurement window: first N bars of the CFD session.
MEASURE_BARS = 12       # 60 min (12 * 5min)
# Hold window: hold for N bars after measurement.
HOLD_BARS = 36          # 180 min (36 * 5min)
# ATR threshold: skip days where |morning_move| / atr < this.
ATR_THRESHOLD = 0.20
# Mode: 'momentum' (follow the morning direction) or 'fade' (null check).
MODE = "momentum"
# Cost in index points round-trip.
COST_POINTS_RT = 1.5

# Session filter — we define RTH as the period where we expect bars.
# The CFD session runs roughly 09:00-23:00 UTC on weekdays.
# We don't hard-filter to a close time; we just use available bars.
SESSION_TZ = "UTC"

ATR_LOOKBACK_DAYS = 20
# FRA40 CFD session: first bar ~09:00 UTC, last bar ~23:00 UTC = 14h = 168 M5 bars.
BARS_PER_DAY = 168
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
    # Drop weekends.
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

def simulate_momentum(
    bars: pd.DataFrame,
    measure_bars: int = MEASURE_BARS,
    hold_bars: int = HOLD_BARS,
    atr_threshold: float = ATR_THRESHOLD,
    cost_points: float = COST_POINTS_RT,
    mode: str = "momentum",           # 'momentum' or 'fade' (null)
    direction: str = "both",          # 'both' / 'long' / 'short'
    atr_lookback_days: int = ATR_LOOKBACK_DAYS,
    max_allowed_gap_bars: int = 6,    # skip day if first bar is >6 bars after 09:00 UTC
) -> tuple[pd.Series, list[dict]]:
    """First-hour momentum simulator (numpy inner loop).

    Per day: find first bar >= SESSION_START_UTC, measure first N bars return,
    if |return| >= threshold * atr → take trade in direction of move.
    Hold for M bars, exit.

    Returns (bar_ret, trades).
    """
    idx = bars.index
    n_bars = len(bars)
    if n_bars == 0:
        return pd.Series(dtype=float, name="mm_ret"), []

    open_arr = bars["open"].to_numpy(dtype=np.float64)
    high_arr = bars["high"].to_numpy(dtype=np.float64)
    low_arr = bars["low"].to_numpy(dtype=np.float64)
    close_arr = bars["close"].to_numpy(dtype=np.float64)

    UTC_OPEN_MIN = SESSION_START_UTC.hour * 60 + SESSION_START_UTC.minute

    # Pre-compute minute-of-day in UTC.
    hours = np.asarray(idx.hour, dtype=np.int32)
    minutes = np.asarray(idx.minute, dtype=np.int32)
    minute_of_day = hours * 60 + minutes

    # Detect day boundaries.
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

    long_ok = direction in ("both", "long")
    short_ok = direction in ("both", "short")
    is_momentum = (mode == "momentum")

    # Rolling ATR buffer: store daily mid-morning |return| for the last N days.
    daily_move_buffer: list[float] = []

    for d_i in range(len(day_starts)):
        s = int(day_starts[d_i])
        e = int(day_ends[d_i])
        day_n = e - s
        if day_n < measure_bars + hold_bars + 2:
            continue

        day_mod = minute_of_day[s:e]
        day_close = close_arr[s:e]
        day_open = open_arr[s:e]

        # Find first bar at or after session start.
        session_start_idx_arr = np.flatnonzero(day_mod >= UTC_OPEN_MIN)
        if session_start_idx_arr.size == 0:
            continue
        first_bar_i = int(session_start_idx_arr[0])

        # If first bar is too late, skip (data gap).
        if first_bar_i >= max_allowed_gap_bars:
            continue

        # Ensure we have enough bars for measurement + hold (+1 for the
        # next-bar-open entry that avoids same-bar look-ahead).
        if first_bar_i + measure_bars + 1 + hold_bars >= day_n:
            continue

        # Morning measurement.
        morning_start_px = float(day_close[first_bar_i])
        morning_end_px = float(day_close[first_bar_i + measure_bars])
        r_morning = (morning_end_px - morning_start_px) / morning_start_px

        # Daily move for ATR (absolute mid-morning return).
        atr_proxy = float(np.mean(daily_move_buffer)) if daily_move_buffer else 0.0
        daily_move_buffer.append(abs(r_morning))
        if len(daily_move_buffer) > atr_lookback_days:
            daily_move_buffer.pop(0)
        threshold = atr_threshold * atr_proxy

        if abs(r_morning) < threshold:
            continue

        # Direction.
        if is_momentum:
            pos = 1 if r_morning > 0 else -1
        else:
            pos = -1 if r_morning > 0 else 1  # fade = opposite

        if pos == 1 and not long_ok:
            continue
        if pos == -1 and not short_ok:
            continue

        # Entry and hold. Entry is the OPEN of the bar AFTER the
        # measurement-window close — signal is observed at close[fb+meas],
        # so entering at open[fb+meas+1] avoids same-bar look-ahead
        # (matches the orb_demo convention).
        entry_i = first_bar_i + measure_bars + 1
        exit_i = entry_i + hold_bars
        if exit_i >= day_n:
            exit_i = day_n - 1

        entry_px = float(day_open[entry_i])
        cost_ret = cost_points / entry_px

        # Daily mark-to-market returns (matching repo convention).
        # Accumulate position PnL as bar-by-bar MTM.
        for j in range(entry_i, exit_i + 1):
            if j == entry_i:
                bar_ret = pos * (day_close[j] - entry_px) / entry_px
            else:
                bar_ret = pos * (day_close[j] - day_close[j - 1]) / day_close[j - 1]
            if j == exit_i:
                # On the exit bar, use the actual exit price.
                exit_px = float(day_close[exit_i])
                bar_ret = pos * (exit_px - (entry_px if j == entry_i else day_close[j - 1])) / (entry_px if j == entry_i else day_close[j - 1])
                bar_ret -= cost_ret
            ret_arr[s + j] += bar_ret

        gross_ret = pos * (exit_px - entry_px) / entry_px - cost_ret

        trades.append({
            "date": dates[s],
            "direction": "LONG" if pos == 1 else "SHORT",
            "entry_ts": idx[s + entry_i],
            "exit_ts": idx[s + exit_i],
            "entry_px": entry_px,
            "exit_px": exit_px,
            "r_morning": r_morning,
            "atr_proxy": atr_proxy,
            "threshold": threshold,
            "pnl_pct": gross_ret,
        })

    bar_ret = pd.Series(ret_arr, index=idx, name="mm_ret")
    return bar_ret, trades


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_run(label: str, bar_ret: pd.Series, trades: list[dict]) -> None:
    if len(bar_ret) == 0:
        print(f"  [{label}]  no data")
        return
    r_arr = bar_ret.to_numpy()
    if np.all(r_arr == 0):
        print(f"  [{label}]  no trades")
        return
    eq = (1.0 + bar_ret).cumprod()
    years = max((bar_ret.index[-1] - bar_ret.index[0]).days / 365.25, 1e-9)
    total = float(eq.iloc[-1] - 1.0)
    cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
    sh = annualized_sharpe(r_arr)
    mdd = max_drawdown(eq.to_numpy())
    n_trades = len(trades)
    trades_per_year = n_trades / years if years > 0 else 0.0
    wins = [t for t in trades if t["pnl_pct"] > 0]
    win_rate = len(wins) / n_trades if n_trades else 0.0
    gross_win = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gross_loss = -sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0)
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")

    print(f"  [{label}]")
    print(f"    period   : {bar_ret.index[0].date()} -> {bar_ret.index[-1].date()} ({years:.1f}y)")
    print(f"    total    : {total * 100:+.2f}%")
    print(f"    CAGR     : {cagr * 100:+.2f}%")
    print(f"    Sharpe   : {sh:+.2f}")
    print(f"    MDD      : {mdd * 100:+.2f}%")
    print(f"    trades   : {n_trades}  ({trades_per_year:.1f}/yr)")
    print(f"    WR       : {win_rate * 100:.1f}%")
    print(f"    PF       : {pf:.2f}")


def kill_criteria_check(label: str, bar_ret: pd.Series, trades: list[dict],
                        sh_floor: float = 0.30, mdd_floor: float = 0.25,
                        trade_floor: int = 200, wr_floor: float = 0.40,
                        pf_floor: float = 1.1) -> None:
    r_arr = bar_ret.to_numpy()
    if np.all(r_arr == 0):
        print(f"  [{label}]  no trades — all FAIL")
        return
    sh = annualized_sharpe(r_arr)
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
    print(f"    Sharpe > {sh_floor:.2f}       : {v(sh > sh_floor)}  ({sh:+.2f})")
    print(f"    MDD < {mdd_floor * 100:.0f}%        : {v(abs(mdd) < mdd_floor)}  ({mdd * 100:+.2f}%)")
    print(f"    Trades >= {trade_floor}      : {v(n_trades >= trade_floor)}  ({n_trades})")
    print(f"    WR >= {wr_floor * 100:.0f}% AND PF >= {pf_floor:.1f} : "
          f"{v(win_rate >= wr_floor and pf >= pf_floor)}  "
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
        if len(sub_trades) < 5:
            print(f"  {label:<22s}  (insufficient trades: {len(sub_trades)})")
            continue
        eq = (1.0 + sub_ret).cumprod()
        years = max((sub_ret.index[-1] - sub_ret.index[0]).days / 365.25, 1e-9)
        cagr = (float(eq.iloc[-1])) ** (1 / max(years, 1e-9)) - 1
        sh = annualized_sharpe(sub_ret.to_numpy())
        mdd = max_drawdown(eq.to_numpy())
        print(f"  {label:<22s}  CAGR {cagr * 100:>+7.2f}%  Sharpe {sh:>+6.2f}  "
              f"MDD {mdd * 100:>+7.2f}%  trades {len(sub_trades):>4d}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section(f"Loading {SYMBOL} {TIMEFRAME}")
    bars = load_m5(SYMBOL)
    n_days = len(set(bars.index.date))
    print(f"  bars     : {len(bars):,}")
    print(f"  range    : {bars.index[0]} -> {bars.index[-1]}")
    print(f"  days     : {n_days}")

    # ------------------------------------------------------------------
    # Baseline (momentum, measure=60min, hold=180min, ATR=0.20, cost=1.5pt)
    # ------------------------------------------------------------------
    section("Baseline (momentum, measure=12, hold=36, ATR=0.20, cost=1.5pt)")
    bar_ret, trades = simulate_momentum(bars)
    report_run("baseline-momentum", bar_ret, trades)

    section("Phase 2 kill-criteria")
    kill_criteria_check("baseline-momentum", bar_ret, trades)

    section("Regime breakdown (baseline-momentum)")
    regime_breakdown(bar_ret, trades)

    # Cost-zero check.
    bar_ret_zc, trades_zc = simulate_momentum(bars, cost_points=0.0)
    sh_zc = annualized_sharpe(bar_ret_zc.to_numpy())
    bar_ret, trades = simulate_momentum(bars)  # re-run baseline for subsequent use
    print(f"\n  Cost-zero Sharpe: {sh_zc:+.2f}  (must be > 0 for signal-present)")

    # ------------------------------------------------------------------
    # Null check: fade (same setup, opposite direction)
    # ------------------------------------------------------------------
    section("Null check: fade (opposite direction)")
    bar_ret_fade, trades_fade = simulate_momentum(bars, mode="fade")
    report_run("fade-null", bar_ret_fade, trades_fade)
    sh_mom = annualized_sharpe(bar_ret.to_numpy())
    sh_fade_val = annualized_sharpe(bar_ret_fade.to_numpy())
    print(f"\n  dir-gap (momentum - fade) Sharpe: {sh_mom - sh_fade_val:+.2f}")
    print(f"    (must be >= +0.30 for directional content)")

    # ------------------------------------------------------------------
    # LONG/SHORT split
    # ------------------------------------------------------------------
    section("Long/short asymmetry (momentum)")
    for d in ("long", "short"):
        r_v, t_v = simulate_momentum(bars, direction=d)
        if len(t_v) == 0:
            print(f"  dir={d:<5s}  no trades")
            continue
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in t_v if t["pnl_pct"] > 0) / max(len(t_v), 1)
        print(f"  dir={d:<5s}  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  "
              f"trades {len(t_v):>4d}  WR {wr*100:>4.1f}%")

    # ------------------------------------------------------------------
    # Measurement window sweep
    # ------------------------------------------------------------------
    section("Measurement window sweep (momentum, hold=36, ATR=0.20, cost=1.5pt)")
    for meas in (6, 9, 12, 18):
        r_v, t_v = simulate_momentum(bars, measure_bars=meas)
        if len(t_v) == 0:
            print(f"  meas={meas*5:>3d}min  no trades")
            continue
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        print(f"  meas={meas*5:>3d}min  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  "
              f"trades {len(t_v):>4d}")

    # ------------------------------------------------------------------
    # Hold window sweep
    # ------------------------------------------------------------------
    section("Hold window sweep (momentum, measure=12, ATR=0.20, cost=1.5pt)")
    for hold in (12, 24, 36, 48):
        r_v, t_v = simulate_momentum(bars, hold_bars=hold)
        if len(t_v) == 0:
            print(f"  hold={hold*5:>3d}min  no trades")
            continue
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        print(f"  hold={hold*5:>3d}min  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  "
              f"trades {len(t_v):>4d}")

    # ------------------------------------------------------------------
    # ATR threshold sweep
    # ------------------------------------------------------------------
    section("ATR threshold sweep (momentum, measure=12, hold=36, cost=1.5pt)")
    for thr in (0.0, 0.10, 0.20, 0.30, 0.50):
        r_v, t_v = simulate_momentum(bars, atr_threshold=thr)
        if len(t_v) == 0:
            print(f"  thr={thr:>4.2f}  no trades")
            continue
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        print(f"  thr={thr:>4.2f}  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  "
              f"trades {len(t_v):>4d}")

    # ------------------------------------------------------------------
    # Cost sensitivity
    # ------------------------------------------------------------------
    section("Cost sensitivity (momentum, measure=12, hold=36, ATR=0.20)")
    for c in (0.0, 1.0, 1.5, 2.0, 3.0):
        r_v, t_v = simulate_momentum(bars, cost_points=c)
        if len(t_v) == 0:
            print(f"  cost={c:>3.1f}pt  no trades")
            continue
        sh = annualized_sharpe(r_v.to_numpy())
        print(f"  cost={c:>3.1f}pt  Sharpe {sh:>+6.2f}  trades {len(t_v):>4d}")

    # ------------------------------------------------------------------
    # Walk-forward (3 rolling splits, ~4.5y IS / ~2.5y OOS)
    # ------------------------------------------------------------------
    section("Walk-forward (baseline, 3 rolling splits)")
    wf_splits = [
        ("S1: IS 2019-01 / OOS 2023-07", "2019-01-01", "2023-06-30", "2023-07-01", "2026-04-18"),
        ("S2: IS 2019-07 / OOS 2024-01", "2019-07-01", "2024-01-31", "2024-02-01", "2026-04-18"),
        ("S3: IS 2020-01 / OOS 2024-07", "2020-01-01", "2024-07-31", "2024-08-01", "2026-04-18"),
    ]
    oos_sharpes = []
    for label, is_s, is_e, oos_s, oos_e in wf_splits:
        is_bars = bars.loc[is_s:is_e]
        oos_bars = bars.loc[oos_s:oos_e]
        r_is, t_is = simulate_momentum(is_bars)
        r_oos, t_oos = simulate_momentum(oos_bars)
        sh_is = annualized_sharpe(r_is.to_numpy())
        sh_oos = annualized_sharpe(r_oos.to_numpy())
        oos_sharpes.append(sh_oos)
        print(f"  {label:<40s}  IS Sh {sh_is:>+6.2f}  OOS Sh {sh_oos:>+6.2f}  "
              f"trades IS={len(t_is):>4d} OOS={len(t_oos):>4d}")
    mean_oos = np.mean(oos_sharpes)
    min_oos = min(oos_sharpes)
    print(f"\n  WF OOS mean: {mean_oos:+.2f}  (need > +0.30)")
    print(f"  WF OOS min:  {min_oos:+.2f}  (need > 0)")

    # ------------------------------------------------------------------
    # Top variants regime breakdown
    # ------------------------------------------------------------------
    section("Top variants — regime breakdown")
    candidates: list[tuple[str, dict]] = [
        ("mom-both-M12-H36-A20",  dict()),
        ("mom-long-M12-H36-A20",  dict(direction="long")),
        ("mom-short-M12-H36-A20", dict(direction="short")),
        ("mom-both-M12-H48-A20",  dict(hold_bars=48)),
        ("mom-both-M18-H36-A20",  dict(measure_bars=18)),
        ("mom-both-M12-H36-A00",  dict(atr_threshold=0.0)),
    ]
    for cname, kwargs in candidates:
        r_v, t_v = simulate_momentum(bars, **kwargs)
        print(f"\n  -- {cname} --")
        regime_breakdown(r_v, t_v)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    section("Summary")
    sh_baseline = annualized_sharpe(bar_ret.to_numpy())
    eq = (1.0 + bar_ret).cumprod()
    years = max((bar_ret.index[-1] - bar_ret.index[0]).days / 365.25, 1e-9)
    total = float(eq.iloc[-1] - 1.0)
    cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
    mdd = max_drawdown(eq.to_numpy())
    print(f"  baseline-momentum")
    print(f"    CAGR      : {cagr * 100:+.2f}%")
    print(f"    Sharpe    : {sh_baseline:+.2f}")
    print(f"    MDD       : {mdd * 100:+.2f}%")
    print(f"    trades    : {len(trades)} ({len(trades) / max(years, 1e-9):.1f}/yr)")
    print(f"    dir-gap   : {sh_mom - sh_fade_val:+.2f}")
    print(f"    cost-zero : {sh_zc:+.2f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
