#!/usr/bin/env python3
"""
ORB_DAX × Vol-Target Sizing + Event Blackout — Phase 2 demo.

Thesis: experiments/orb_dax_voltarget_events/orb_dax_voltarget_events.md

Base strategy: GER40 M5 T+180 LONG-only Xetra ORB (the deployed `orb_dax`
config). Simulator is the same numpy inner loop as `orb_dax_sentiment/
sentiment_demo.py`. On top of those trades we apply two structural overlays:

  A) Vol-target sizing — scale per-bar trade returns inversely to GER40 D1
     realized vol, with target = expanding median, clipped to [0.5, 2.0].
  B) Event blackout — skip Xetra-open entries on hardcoded FOMC / ECB / NFP
     dates 2019-01 → 2026-04.

PRE-COMMITTED params (NOT swept):
  VOL_LOOKBACK_DAYS   = 20
  VOL_CLIP            = (0.5, 2.0)
  Event calendars     = public FOMC/ECB/NFP schedules, hardcoded below.

Run: ``venv/Scripts/python.exe experiments/orb_dax_voltarget_events/voltarget_events_demo.py``
"""

from __future__ import annotations

import os
import sys
from datetime import date, time as dtime, timedelta

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))

from utils import fetch_ohlc  # noqa: E402


# ---------------------------------------------------------------------------
# Config (re-implementation of deployed orb_dax baseline; identical to
# orb_dax_sentiment/sentiment_demo.py so the re-impl baseline matches)
# ---------------------------------------------------------------------------

SYMBOL = "GER40"
TIMEFRAME = "M5"
START_DATE = "2019-01-01"
END_DATE = "2026-04-18"

OR_MINUTES = 30
ENTRY_CUTOFF_MIN = 180
TOD_EXIT_MIN = 180
EXIT_MIN_BEFORE_CLOSE = 5
COST_POINTS_ROUND_TRIP = 1.0

RTH_OPEN = dtime(9, 0)
RTH_CLOSE = dtime(17, 30)
SESSION_TZ = "Europe/Berlin"

_rth_minutes = (RTH_CLOSE.hour * 60 + RTH_CLOSE.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)
BARS_PER_DAY = _rth_minutes // 5
DAYS_PER_YEAR = 252
BARS_PER_YEAR = BARS_PER_DAY * DAYS_PER_YEAR

# Pre-committed lever parameters.
VOL_LOOKBACK_DAYS = 20
VOL_CLIP_LO = 0.5
VOL_CLIP_HI = 2.0
VOL_MIN_HISTORY_DAYS = 252  # need 1y of vol history before target_median is meaningful


# ---------------------------------------------------------------------------
# Pre-committed event calendars (NOT tuned — public schedules)
# ---------------------------------------------------------------------------

# FOMC scheduled monetary policy meetings 2019-01 → 2026-04 (federalreserve.gov).
# Day-of-decision basis; this is the calendar date the FOMC publishes its
# statement. Where a meeting spans 2 days, we use the announcement day.
FOMC_DATES = [
    # 2019
    "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19",
    "2019-07-31", "2019-09-18", "2019-10-30", "2019-12-11",
    # 2020 (incl. emergency cuts in March)
    "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29",
    "2020-06-10", "2020-07-29", "2020-09-16", "2020-11-05",
    "2020-12-16",
    # 2021
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16",
    "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    # 2022
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15",
    "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    # 2023
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14",
    "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    # 2024
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    # 2026 (through 2026-04 cutoff)
    "2026-01-28", "2026-03-18",
]

# ECB Governing Council monetary-policy meetings 2019-01 → 2026-04 (ecb.europa.eu).
# Each entry is the Thursday on which the rate decision is announced. Best-effort
# from public schedules; minor date errors do not invalidate the test since they
# affect the hypothesis and the null symmetrically.
ECB_DATES = [
    # 2019
    "2019-01-24", "2019-03-07", "2019-04-10", "2019-06-06",
    "2019-07-25", "2019-09-12", "2019-10-24", "2019-12-12",
    # 2020
    "2020-01-23", "2020-03-12", "2020-04-30", "2020-06-04",
    "2020-07-16", "2020-09-10", "2020-10-29", "2020-12-10",
    # 2021
    "2021-01-21", "2021-03-11", "2021-04-22", "2021-06-10",
    "2021-07-22", "2021-09-09", "2021-10-28", "2021-12-16",
    # 2022
    "2022-02-03", "2022-03-10", "2022-04-14", "2022-06-09",
    "2022-07-21", "2022-09-08", "2022-10-27", "2022-12-15",
    # 2023
    "2023-02-02", "2023-03-16", "2023-05-04", "2023-06-15",
    "2023-07-27", "2023-09-14", "2023-10-26", "2023-12-14",
    # 2024
    "2024-01-25", "2024-03-07", "2024-04-11", "2024-06-06",
    "2024-07-18", "2024-09-12", "2024-10-17", "2024-12-12",
    # 2025
    "2025-01-30", "2025-03-06", "2025-04-17", "2025-06-05",
    "2025-07-24", "2025-09-11", "2025-10-30", "2025-12-18",
    # 2026 (through 2026-04 cutoff)
    "2026-01-29", "2026-03-12",
]


def _first_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    # Monday=0 ... Friday=4. Add days until Friday.
    return d + timedelta(days=(4 - d.weekday()) % 7)


def _nfp_dates(start: date, end: date) -> list[date]:
    out: list[date] = []
    for y in range(start.year, end.year + 1):
        for m in range(1, 13):
            ff = _first_friday(y, m)
            if start <= ff <= end:
                out.append(ff)
    return out


def build_blackout_set() -> tuple[set[date], dict[str, set[date]]]:
    fomc = {date.fromisoformat(s) for s in FOMC_DATES}
    ecb = {date.fromisoformat(s) for s in ECB_DATES}
    nfp = set(_nfp_dates(date(2019, 1, 1), date(2026, 4, 30)))
    union = fomc | ecb | nfp
    return union, {"FOMC": fomc, "ECB": ecb, "NFP": nfp}


# ---------------------------------------------------------------------------
# Helpers (verbatim from sentiment_demo)
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f"\n{'=' * 78}\n  {t}\n{'=' * 78}")


def load_m5(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, "M5", START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f"No M5 bars for {symbol}.")
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df.index = df.index.tz_convert(SESSION_TZ)
    times = df.index.time
    df = df.loc[(times >= RTH_OPEN) & (times < RTH_CLOSE)]
    df = df.loc[df.index.dayofweek < 5]
    return df


def load_d1(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, "D1", "2017-01-01", END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f"No D1 bars for {symbol}.")
    df = raw[["timestamp", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df = df.rename(columns={"close": symbol})
    return df[[symbol]]


def max_drawdown(eq: np.ndarray) -> float:
    rm = np.maximum.accumulate(eq)
    dd = (eq - rm) / rm
    return float(dd.min()) if len(dd) else 0.0


def annualized_sharpe_bar(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if r.size == 0:
        return 0.0
    s = r.std(ddof=1)
    if s == 0 or not np.isfinite(s):
        return 0.0
    return float(r.mean() / s * np.sqrt(BARS_PER_YEAR))


# ---------------------------------------------------------------------------
# ORB long-only T+180 simulator — numpy inner loop (verbatim from sentiment_demo)
# ---------------------------------------------------------------------------

def simulate_orb_long_t180(
    bars: pd.DataFrame,
    cost_points: float = COST_POINTS_ROUND_TRIP,
) -> tuple[np.ndarray, list[dict]]:
    idx = bars.index
    n_bars = len(bars)
    open_arr = bars["open"].to_numpy(dtype=np.float64)
    high_arr = bars["high"].to_numpy(dtype=np.float64)
    low_arr = bars["low"].to_numpy(dtype=np.float64)
    close_arr = bars["close"].to_numpy(dtype=np.float64)

    rth_open_min = RTH_OPEN.hour * 60 + RTH_OPEN.minute
    rth_close_min = RTH_CLOSE.hour * 60 + RTH_CLOSE.minute
    hours = np.asarray(idx.hour, dtype=np.int32)
    minutes = np.asarray(idx.minute, dtype=np.int32)
    minute_of_day = hours * 60 + minutes - rth_open_min

    dates_obj = np.asarray(idx.date)
    change = np.empty(n_bars, dtype=bool)
    change[0] = True
    change[1:] = dates_obj[1:] != dates_obj[:-1]
    day_starts = np.flatnonzero(change)
    day_ends = np.empty_like(day_starts)
    day_ends[:-1] = day_starts[1:]
    day_ends[-1] = n_bars

    ret_arr = np.zeros(n_bars, dtype=np.float64)
    trades: list[dict] = []

    rth_minutes = rth_close_min - rth_open_min
    exit_cutoff = rth_minutes - EXIT_MIN_BEFORE_CLOSE
    or_end = OR_MINUTES
    entry_cutoff = ENTRY_CUTOFF_MIN
    min_day_bars = (OR_MINUTES // 5) + 4

    for d_i in range(len(day_starts)):
        s = int(day_starts[d_i])
        e = int(day_ends[d_i])
        n = e - s
        if n < min_day_bars:
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

        post_or = np.flatnonzero(day_mod >= or_end)
        if post_or.size == 0:
            continue
        first_post = int(post_or[0])

        position = 0
        entry_px = 0.0
        entry_bar_idx = -1
        stop_px = 0.0
        long_taken = False

        for i in range(first_post, n):
            mod = int(day_mod[i])
            is_last = (i == n - 1)

            if position != 0 and i > entry_bar_idx:
                prev_close = day_close[i - 1]
                cur_close = day_close[i]
                ret_arr[s + i] = position * (cur_close - prev_close) / prev_close

            if position != 0:
                bar_low = day_low[i]
                tod_forced = (i - entry_bar_idx) * 5 >= TOD_EXIT_MIN
                hit_stop = bar_low <= stop_px
                forced_close = (mod >= exit_cutoff) or is_last or tod_forced
                if hit_stop or forced_close:
                    if hit_stop:
                        exit_px = stop_px
                        reason = "stop"
                    elif tod_forced:
                        exit_px = float(day_close[i])
                        reason = "tod"
                    else:
                        exit_px = float(day_close[i])
                        reason = "eod"
                    cost_ret = cost_points / entry_px
                    ret_arr[s + i] -= cost_ret
                    pnl_net = (exit_px - entry_px) / entry_px - cost_ret
                    trades.append({
                        "entry_date": dates_obj[s + entry_bar_idx],
                        "entry_bar_idx": s + entry_bar_idx,
                        "exit_bar_idx": s + i,
                        "entry_px": entry_px,
                        "exit_px": exit_px,
                        "pnl_net": pnl_net,
                        "reason": reason,
                    })
                    position = 0
                    entry_bar_idx = -1
                if position != 0:
                    continue

            # Entry logic — LONG-only, max 1 entry per day, before entry-cutoff.
            if not long_taken and mod < entry_cutoff and i + 1 < n:
                if day_close[i] > or_high:
                    position = 1
                    entry_px = float(day_open[i + 1])
                    if not np.isfinite(entry_px) or entry_px <= 0:
                        position = 0
                        continue
                    stop_px = or_low
                    entry_bar_idx = i + 1
                    long_taken = True

    return ret_arr, trades


# ---------------------------------------------------------------------------
# Vol-target sizing: expanding-median target, clipped scale
# ---------------------------------------------------------------------------

def build_vol_scale(d1: pd.DataFrame) -> dict[date, float]:
    """Map trading-date -> scale factor available at that day's Xetra open.

    scale[t] = clip(target[t-1] / realized[t-1], CLIP_LO, CLIP_HI)
    where realized[d] = std of close-to-close returns over the prior 20 obs
    and target[d]    = expanding median of realized[:d] (so observable at d).
    """
    series = d1[SYMBOL].astype(float)
    ret = series.pct_change()
    realized = ret.rolling(VOL_LOOKBACK_DAYS, min_periods=VOL_LOOKBACK_DAYS).std(ddof=1)
    # Expanding median, using only history strictly before each row.
    target = realized.shift(1).expanding(min_periods=VOL_MIN_HISTORY_DAYS).median()
    raw_scale = target / realized
    scaled = raw_scale.clip(lower=VOL_CLIP_LO, upper=VOL_CLIP_HI)
    # Shift by 1: the scale that applies at trading-day t uses the value
    # computed from the close of day t-1 (the realized + target as of t-1
    # close). Both `realized` and `target` are already aligned to the day they
    # become observable (end-of-day d), so to use at day d+1's open we shift.
    scaled = scaled.shift(1)

    scaled.index = pd.to_datetime(scaled.index, utc=True).tz_convert(SESSION_TZ).normalize()
    out: dict[date, float] = {}
    for ts, v in scaled.items():
        if np.isfinite(v):
            out[ts.date()] = float(v)
    return out


def build_inverse_vol_scale(scale_by_date: dict[date, float]) -> dict[date, float]:
    """Inverse-direction null: if scale = target/realized (clip 0.5,2.0),
    inverse = clip(realized/target, 0.5, 2.0). Mathematically that's the
    reciprocal of the un-clipped raw ratio, re-clipped. We approximate by
    computing the reciprocal of the actual scale within the clip-aware bounds:

      raw   = target/realized  -> stored after clip into [0.5, 2.0]
      raw^-1 in [0.5, 2.0]    -> inverse scale

    For points where raw was inside [0.5, 2.0] the reciprocal is a faithful
    sign-flip. For points where raw was clipped, the inverse is also clipped.
    """
    out: dict[date, float] = {}
    for d, s in scale_by_date.items():
        # 1/s ∈ [0.5, 2.0] iff s ∈ [0.5, 2.0], which is always true given the clip.
        inv = 1.0 / s
        inv = max(VOL_CLIP_LO, min(VOL_CLIP_HI, inv))
        out[d] = inv
    return out


# ---------------------------------------------------------------------------
# Overlay application
# ---------------------------------------------------------------------------

def apply_overlay(
    ret_arr: np.ndarray,
    trades: list[dict],
    *,
    scale_by_date: dict[date, float] | None = None,
    blackout: set[date] | None = None,
    mode_event: str = "none",  # 'none' / 'skip' / 'only'
) -> tuple[np.ndarray, dict]:
    """Apply (optionally) vol-target scaling AND (optionally) event blackout.

    - scale_by_date None -> no sizing applied (unit-scale).
    - blackout None -> no event filter.
    - mode_event 'skip' -> zero out trades on blackout dates.
    - mode_event 'only' -> zero out trades NOT on blackout dates (null variant).

    Per-bar returns within a trade are multiplied by the trade-day scale (if
    provided). Bar 0 of the trade lifetime is the entry bar (zero return) and
    the cost charge on the exit bar is also scaled (so net is consistent with
    DV01-equivalent sizing).
    """
    new_ret = ret_arr.copy()
    n_kept = 0
    n_scaled_nonunit = 0
    n_skipped = 0
    n_missing_scale = 0

    for tr in trades:
        d = tr["entry_date"]
        if isinstance(d, np.datetime64):
            d = pd.Timestamp(d).date()
        elif isinstance(d, pd.Timestamp):
            d = d.date()

        i0, i1 = tr["entry_bar_idx"], tr["exit_bar_idx"]

        # Event filter.
        in_blackout = (blackout is not None) and (d in blackout)
        if blackout is not None:
            if mode_event == "skip" and in_blackout:
                new_ret[i0:i1 + 1] = 0.0
                n_skipped += 1
                continue
            if mode_event == "only" and not in_blackout:
                new_ret[i0:i1 + 1] = 0.0
                n_skipped += 1
                continue

        # Vol-target sizing.
        if scale_by_date is not None:
            s = scale_by_date.get(d, np.nan)
            if not np.isfinite(s):
                # Missing scale (e.g., before warmup) — keep unit scale.
                n_missing_scale += 1
                s = 1.0
            if s != 1.0:
                new_ret[i0:i1 + 1] *= s
                n_scaled_nonunit += 1
        n_kept += 1

    return new_ret, {
        "n_kept": n_kept,
        "n_scaled": n_scaled_nonunit,
        "n_skipped": n_skipped,
        "n_missing_scale": n_missing_scale,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_run(label: str, ret_arr: np.ndarray, counts: dict) -> dict:
    eq = np.cumprod(1.0 + ret_arr)
    sh = annualized_sharpe_bar(ret_arr)
    mdd = max_drawdown(eq)
    total_ret = float(eq[-1] - 1.0) if len(eq) else 0.0
    years = len(ret_arr) / BARS_PER_YEAR
    cagr = (1.0 + total_ret) ** (1.0 / years) - 1.0 if years > 0 and total_ret > -1 else float("nan")
    print(
        f"  {label:<22}  Sh {sh:+.3f}   MDD {mdd*100:+.2f}%   "
        f"TotRet {total_ret*100:+.1f}%   CAGR {cagr*100:+.2f}%   "
        f"trades(kept/scaled/skip): {counts['n_kept']}/{counts['n_scaled']}/{counts['n_skipped']}"
    )
    return {"label": label, "sharpe": sh, "mdd": mdd, "total_ret": total_ret, "cagr": cagr, **counts}


def regime_breakdown(label: str, ret_arr: np.ndarray, bars: pd.DataFrame) -> dict:
    idx = bars.index
    years = idx.year.values
    windows = [("2019-2020", (years >= 2019) & (years <= 2020)),
               ("2021-2022", (years >= 2021) & (years <= 2022)),
               ("2023-2026", years >= 2023)]
    print(f"  Regime breakdown — {label}")
    out: dict[str, dict] = {}
    for name, mask in windows:
        if not mask.any():
            continue
        r = ret_arr[mask]
        sh = annualized_sharpe_bar(r)
        eq = np.cumprod(1.0 + r)
        mdd = max_drawdown(eq)
        print(f"    {name}:  Sh {sh:+.3f}   MDD {mdd*100:+.2f}%   bars {mask.sum()}")
        out[name] = {"sharpe": sh, "mdd": mdd}
    return out


def cost_sensitivity(bars: pd.DataFrame, scale_by_date: dict, blackout: set) -> None:
    print(f"  Cost sensitivity — VT+EB combined")
    for cost in (0.5, 1.0, 1.5, 2.0):
        ret_arr, trades = simulate_orb_long_t180(bars, cost_points=cost)
        new_ret, counts = apply_overlay(
            ret_arr, trades,
            scale_by_date=scale_by_date,
            blackout=blackout,
            mode_event="skip",
        )
        sh = annualized_sharpe_bar(new_ret)
        print(f"    {cost:.1f}pt RT:  Sh {sh:+.3f}   kept/scaled/skipped "
              f"{counts['n_kept']}/{counts['n_scaled']}/{counts['n_skipped']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    section("Loading GER40 M5 (Xetra RTH)")
    bars = load_m5(SYMBOL)
    print(f"  {len(bars):,} M5 bars  |  {bars.index.min()} -> {bars.index.max()}")

    section("Loading GER40 D1 and building vol-target scale series")
    d1 = load_d1(SYMBOL)
    print(f"  {len(d1)} D1 bars  |  {d1.index.min()} -> {d1.index.max()}")
    scale_by_date = build_vol_scale(d1)
    inv_scale_by_date = build_inverse_vol_scale(scale_by_date)
    vals = np.array(list(scale_by_date.values()))
    print(f"  vol-target scale series: {len(vals)} dates with valid scale "
          f"(after {VOL_MIN_HISTORY_DAYS}d expanding-median warmup)")
    print(f"  scale stats: mean={vals.mean():.3f}  std={vals.std():.3f}  "
          f"min={vals.min():.3f}  max={vals.max():.3f}  "
          f"@clip-lo {(vals <= VOL_CLIP_LO + 1e-9).sum()}  "
          f"@clip-hi {(vals >= VOL_CLIP_HI - 1e-9).sum()}")

    section("Building event blackout calendar")
    blackout, parts = build_blackout_set()
    print(f"  FOMC: {len(parts['FOMC'])} dates  |  "
          f"ECB: {len(parts['ECB'])} dates  |  "
          f"NFP: {len(parts['NFP'])} dates  |  "
          f"Union: {len(blackout)} dates")
    # Per-year counts as a sanity sanity-check.
    yc: dict[int, int] = {}
    for d in blackout:
        yc[d.year] = yc.get(d.year, 0) + 1
    yc_str = ", ".join(f"{y}:{n}" for y, n in sorted(yc.items()))
    print(f"  per-year blackout-day counts: {yc_str}")

    section("Baseline ORB_DAX T+180 LONG-only — re-impl, same engine as sentiment_demo")
    ret_arr, trades = simulate_orb_long_t180(bars, cost_points=COST_POINTS_ROUND_TRIP)
    print(f"  {len(trades)} trades over {len(bars) / BARS_PER_DAY / DAYS_PER_YEAR:.2f} years")
    baseline_counts = {"n_kept": len(trades), "n_scaled": 0, "n_skipped": 0}
    baseline = report_run("baseline", ret_arr, baseline_counts)

    section("Variants — VT, EB, VT+EB, and null checks")
    # VT alone (no event filter).
    vt_ret, vt_counts = apply_overlay(
        ret_arr, trades,
        scale_by_date=scale_by_date, blackout=None, mode_event="none",
    )
    vt = report_run("VT (vol-target only)", vt_ret, vt_counts)

    # EB alone (skip event days; no vol-target).
    eb_ret, eb_counts = apply_overlay(
        ret_arr, trades,
        scale_by_date=None, blackout=blackout, mode_event="skip",
    )
    eb = report_run("EB (events only skip)", eb_ret, eb_counts)

    # Combined.
    combo_ret, combo_counts = apply_overlay(
        ret_arr, trades,
        scale_by_date=scale_by_date, blackout=blackout, mode_event="skip",
    )
    combo = report_run("VT+EB combined", combo_ret, combo_counts)

    # Null 1: Inverse VT (size UP in high vol).
    inv_vt_ret, inv_vt_counts = apply_overlay(
        ret_arr, trades,
        scale_by_date=inv_scale_by_date, blackout=None, mode_event="none",
    )
    inv_vt = report_run("Inv-VT (null)", inv_vt_ret, inv_vt_counts)

    # Null 2: Event-only (trade ONLY on event days).
    only_ret, only_counts = apply_overlay(
        ret_arr, trades,
        scale_by_date=None, blackout=blackout, mode_event="only",
    )
    only = report_run("Event-only (null)", only_ret, only_counts)

    section("Kill-criteria check — pre-committed (VT+EB combined)")
    delta_full = combo["sharpe"] - baseline["sharpe"]
    mdd_pp_worse = (combo["mdd"] - baseline["mdd"]) * 100  # negative if combo MDD is worse
    null_vt_gap = vt["sharpe"] - inv_vt["sharpe"]
    null_event_gap = baseline["sharpe"] - only["sharpe"]

    checks = [
        ("Sharpe lift ≥ +0.15 (full)", delta_full >= 0.15, f"{delta_full:+.3f}"),
        ("MDD not worse by >1pp", combo["mdd"] >= baseline["mdd"] - 0.01,
         f"baseline {baseline['mdd']*100:+.2f}% vs combo {combo['mdd']*100:+.2f}% (Δ {mdd_pp_worse:+.2f}pp)"),
        ("Trade count ≥ 1000", combo["n_kept"] >= 1000, f"{combo['n_kept']} kept"),
        ("Null check VT: VT − Inv-VT ≥ +0.20", null_vt_gap >= 0.20, f"gap {null_vt_gap:+.3f}"),
        ("Null check Events: baseline − event-only ≥ +0.20", null_event_gap >= 0.20, f"gap {null_event_gap:+.3f}"),
    ]
    for name, ok, detail in checks:
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {name}   ({detail})")

    section("Per-lever attribution")
    print(f"  baseline Sh             {baseline['sharpe']:+.3f}")
    print(f"  VT alone   Sh           {vt['sharpe']:+.3f}   (Δ vs baseline {vt['sharpe']-baseline['sharpe']:+.3f})")
    print(f"  EB alone   Sh           {eb['sharpe']:+.3f}   (Δ vs baseline {eb['sharpe']-baseline['sharpe']:+.3f})")
    print(f"  VT+EB combined Sh       {combo['sharpe']:+.3f}   (Δ vs baseline {combo['sharpe']-baseline['sharpe']:+.3f})")
    print(f"  expected if additive    {baseline['sharpe'] + (vt['sharpe']-baseline['sharpe']) + (eb['sharpe']-baseline['sharpe']):+.3f}")
    print(f"  interaction term        "
          f"{combo['sharpe'] - (baseline['sharpe'] + (vt['sharpe']-baseline['sharpe']) + (eb['sharpe']-baseline['sharpe'])):+.3f}")

    section("Regime breakdown — baseline vs VT+EB combined")
    reg_base = regime_breakdown("baseline", ret_arr, bars)
    reg_combo = regime_breakdown("VT+EB", combo_ret, bars)
    print(f"  Regime-consistency check:")
    consistent = 0
    for k in ("2019-2020", "2021-2022", "2023-2026"):
        if k in reg_base and k in reg_combo:
            lift = reg_combo[k]["sharpe"] - reg_base[k]["sharpe"]
            ok = lift >= 0.0
            consistent += int(ok)
            marker = "PASS" if ok else "FAIL"
            print(f"    [{marker}] {k}: baseline {reg_base[k]['sharpe']:+.3f} -> VT+EB {reg_combo[k]['sharpe']:+.3f}   (Δ {lift:+.3f})")
    print(f"  Regime-windows with non-negative lift: {consistent}/3  (need ≥ 2)")

    section("Cost sensitivity — VT+EB combined")
    cost_sensitivity(bars, scale_by_date, blackout)
    # Robustness gate: combo at 2pt must exceed baseline at 1pt.
    ret_2pt, tr_2pt = simulate_orb_long_t180(bars, cost_points=2.0)
    combo_2pt, _ = apply_overlay(
        ret_2pt, tr_2pt,
        scale_by_date=scale_by_date, blackout=blackout, mode_event="skip",
    )
    sh_combo_2pt = annualized_sharpe_bar(combo_2pt)
    print(f"  Robustness check: combo@2pt Sh {sh_combo_2pt:+.3f} vs baseline@1pt Sh {baseline['sharpe']:+.3f}  "
          f"-> {'PASS' if sh_combo_2pt >= baseline['sharpe'] else 'FAIL'}")

    section("Holdout 2023-2026 explicit check (the deploy-relevant window)")
    holdout_mask = bars.index.year.values >= 2023
    h_base = annualized_sharpe_bar(ret_arr[holdout_mask])
    h_combo = annualized_sharpe_bar(combo_ret[holdout_mask])
    h_lift = h_combo - h_base
    print(f"  Holdout baseline Sh {h_base:+.3f}  ->  VT+EB Sh {h_combo:+.3f}   (Δ {h_lift:+.3f})")
    print(f"  [{'PASS' if h_lift >= 0.10 else 'FAIL'}] Holdout lift ≥ +0.10")

    section("Summary")
    print(f"  baseline (re-impl):     Sh {baseline['sharpe']:+.3f}  MDD {baseline['mdd']*100:+.2f}%  "
          f"trades {baseline['n_kept']}")
    print(f"  VT+EB combined:         Sh {combo['sharpe']:+.3f}  MDD {combo['mdd']*100:+.2f}%  "
          f"trades {combo['n_kept']}  (skipped {combo['n_skipped']})")
    print(f"  Holdout VT+EB:          Sh {h_combo:+.3f}  (baseline {h_base:+.3f})")
    print(f"  Null gaps:              VT-vs-InvVT {null_vt_gap:+.3f}   "
          f"baseline-vs-event-only {null_event_gap:+.3f}")


if __name__ == "__main__":
    main()
