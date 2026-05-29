#!/usr/bin/env python3
"""
Structural-flow calendar audit — Phase 0 screen across event x instrument x window grids.

Thesis: experiments/structural_flow_audit/structural_flow_audit.md

Surfaces candidate structural-flow event cells worth Phase 2 thesis lock.
NOT a deploy-decision; ranks (event, instrument, window) cells by composite
score = |t-stat| * sign(cost_headroom).

Usage:
  venv/Scripts/python.exe experiments/structural_flow_audit/structural_flow_audit.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))

from data import fetch_ohlc  # noqa: E402


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

START_DATE = "2019-01-01"
END_DATE = "2026-05-26"

# Cost floors (Eightcap retail CFD, approximate RT in bps)
COST_FLOOR_BPS = {
    "SPX500": 5.0, "NDX100": 4.0, "GER40": 4.0,
    "EURUSD": 1.5, "USDJPY": 2.0, "GBPUSD": 2.0,
    "XAUUSD": 7.0,
}

# Decision tier thresholds
TIER_STRONG = {"t": 2.5, "cost_headroom_bps": 1.0, "n_min": 20}
TIER_MEDIUM = {"t": 1.8, "cost_headroom_bps": 0.0, "n_min": 15}
TIER_WEAK   = {"t": 1.3, "cost_headroom_bps": 2.0, "n_min": 10}


def section(t: str) -> None:
    print(f"\n{'=' * 92}\n  {t}\n{'=' * 92}\n")


# -----------------------------------------------------------------------------
# Calendar generators (pure rule-based, no external CSV)
# -----------------------------------------------------------------------------

def is_business_day(d: date) -> bool:
    return d.weekday() < 5


def last_business_day(year: int, month: int) -> date:
    # Find last day of month, walk back to weekday
    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    while not is_business_day(d):
        d -= timedelta(days=1)
    return d


def nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """weekday: 0=Mon..6=Sun. n=1..5."""
    d = date(year, month, 1)
    count = 0
    while True:
        if d.weekday() == weekday:
            count += 1
            if count == n:
                return d
        d += timedelta(days=1)
        if d.month != month:
            raise ValueError(f"no {n}th weekday {weekday} in {year}-{month}")


def gen_jpm_collar_dates(years: range) -> list[date]:
    """Last biz day of Mar/Jun/Sep/Dec."""
    out = []
    for y in years:
        for m in (3, 6, 9, 12):
            out.append(last_business_day(y, m))
    return out


def gen_month_end_dates(years: range) -> list[date]:
    """Last biz day of every month."""
    out = []
    for y in years:
        for m in range(1, 13):
            out.append(last_business_day(y, m))
    return out


def gen_vix_soq_dates(years: range) -> list[date]:
    """Wednesday before 3rd Friday of each month."""
    out = []
    for y in years:
        for m in range(1, 13):
            try:
                third_fri = nth_weekday_of_month(y, m, weekday=4, n=3)
                wed_before = third_fri - timedelta(days=2)  # Friday - 2 = Wednesday
                out.append(wed_before)
            except ValueError:
                continue
    return out


def gen_opex_day_after_dates(years: range) -> list[date]:
    """Monday after 3rd Friday of each month."""
    out = []
    for y in years:
        for m in range(1, 13):
            try:
                third_fri = nth_weekday_of_month(y, m, weekday=4, n=3)
                mon_after = third_fri + timedelta(days=3)  # Fri + 3 = Mon
                out.append(mon_after)
            except ValueError:
                continue
    return out


def gen_triple_witch_dates(years: range) -> list[date]:
    """3rd Friday of Mar/Jun/Sep/Dec."""
    out = []
    for y in years:
        for m in (3, 6, 9, 12):
            try:
                out.append(nth_weekday_of_month(y, m, weekday=4, n=3))
            except ValueError:
                continue
    return out


# -----------------------------------------------------------------------------
# Data loading
# -----------------------------------------------------------------------------

def load_m5(symbol: str) -> pd.DataFrame | None:
    """Load M5 bars (UTC-indexed)."""
    try:
        df = fetch_ohlc(symbol, "M5", START_DATE, END_DATE)
    except Exception as e:
        print(f"  [WARN] {symbol}: load error {e}")
        return None
    if df is None or df.empty:
        print(f"  [WARN] {symbol}: no data")
        return None
    df = df[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


# -----------------------------------------------------------------------------
# Window-return computation in local timezone
# -----------------------------------------------------------------------------

def compute_window_returns(
    bars_utc: pd.DataFrame,
    event_dates: list[date],
    tz_name: str,
    start_hour: int, start_min: int,
    end_hour: int, end_min: int,
) -> tuple[np.ndarray, list[date]]:
    """
    For each event_date, compute window return = (close at end_of_window - open at start_of_window) / open_of_window * 1e4 bps.
    Returns array of bp-returns + corresponding actual event dates kept.
    """
    bars_local = bars_utc.copy()
    bars_local.index = bars_local.index.tz_convert(tz_name)
    local_dates = bars_local.index.normalize()
    local_hour = bars_local.index.hour
    local_min = bars_local.index.minute

    # Pre-build a date -> [(hour,minute,open,close)] dict for fast lookup
    date_to_bars: dict[date, pd.DataFrame] = {}
    grouped = bars_local.groupby(local_dates)
    for ld, sub in grouped:
        date_to_bars[ld.date()] = sub

    rets = []
    kept_dates = []
    for ev in event_dates:
        sub = date_to_bars.get(ev)
        if sub is None:
            continue
        sub_h = sub.index.hour
        sub_m = sub.index.minute
        # Window mask: minute-of-day in [start, end)
        sod = sub_h * 60 + sub_m
        start_mod = start_hour * 60 + start_min
        end_mod = end_hour * 60 + end_min
        mask = (sod >= start_mod) & (sod < end_mod)
        if mask.sum() < 2:
            continue
        win = sub.loc[mask]
        win_open = float(win["open"].iloc[0])
        win_close = float(win["close"].iloc[-1])
        if win_open <= 0 or not np.isfinite(win_open) or not np.isfinite(win_close):
            continue
        ret_bps = (win_close - win_open) / win_open * 1e4
        rets.append(ret_bps)
        kept_dates.append(ev)
    return np.asarray(rets, dtype=np.float64), kept_dates


def compute_placebo_returns(
    bars_utc: pd.DataFrame,
    event_dates: set[date],
    tz_name: str,
    weekdays: set[int],
    start_hour: int, start_min: int,
    end_hour: int, end_min: int,
    max_samples: int = 1500,
) -> np.ndarray:
    """
    Compute returns over the same window on non-event days that fall on the same weekdays
    as the event population. Used as null baseline for the t-test.
    """
    bars_local = bars_utc.copy()
    bars_local.index = bars_local.index.tz_convert(tz_name)
    local_dates = bars_local.index.normalize()

    all_dates = sorted({d.date() for d in local_dates})
    rng = np.random.default_rng(42)
    # Filter: same weekday(s), NOT an event date
    candidates = [d for d in all_dates if d.weekday() in weekdays and d not in event_dates]
    if len(candidates) > max_samples:
        chosen_idx = rng.choice(len(candidates), size=max_samples, replace=False)
        candidates = [candidates[i] for i in sorted(chosen_idx)]

    rets, _ = compute_window_returns(
        bars_utc, candidates, tz_name, start_hour, start_min, end_hour, end_min,
    )
    return rets


# -----------------------------------------------------------------------------
# Welch's t-test
# -----------------------------------------------------------------------------

def welch_t(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return float("nan"), float("nan")
    mean_diff = a.mean() - b.mean()
    var_a = a.var(ddof=1) / len(a)
    var_b = b.var(ddof=1) / len(b)
    se = np.sqrt(var_a + var_b)
    if se == 0:
        return float("nan"), float("nan")
    return float(mean_diff / se), float(mean_diff)


# -----------------------------------------------------------------------------
# Grid evaluation
# -----------------------------------------------------------------------------

def evaluate_grid(
    event_label: str,
    instrument: str,
    bars: pd.DataFrame,
    event_dates: list[date],
    tz_name: str,
    start_hour: int, start_min: int,
    end_hour: int, end_min: int,
) -> dict | None:
    """One row of the output ranking table."""
    if bars is None or bars.empty:
        return None
    event_set = set(event_dates)
    weekdays = {d.weekday() for d in event_dates}

    ev_rets, kept = compute_window_returns(
        bars, event_dates, tz_name, start_hour, start_min, end_hour, end_min,
    )
    pl_rets = compute_placebo_returns(
        bars, event_set, tz_name, weekdays, start_hour, start_min, end_hour, end_min,
    )

    if len(ev_rets) < 5 or len(pl_rets) < 30:
        return {
            "event": event_label, "instrument": instrument,
            "n_events": len(ev_rets), "n_placebo": len(pl_rets),
            "event_mean_bps": float("nan"), "placebo_mean_bps": float("nan"),
            "null_gap_bps": float("nan"), "t_stat": float("nan"),
            "cost_floor_bps": COST_FLOOR_BPS.get(instrument, 5.0),
            "cost_headroom_bps": float("nan"), "tier": "INSUFFICIENT_N",
            "score": float("nan"),
        }

    t_stat, null_gap = welch_t(ev_rets, pl_rets)
    event_mean = float(ev_rets.mean())
    placebo_mean = float(pl_rets.mean())
    cost_floor = COST_FLOOR_BPS.get(instrument, 5.0)
    cost_headroom = abs(null_gap) - cost_floor

    # Tier
    abs_t = abs(t_stat) if not np.isnan(t_stat) else 0.0
    n = len(ev_rets)
    if (abs_t >= TIER_STRONG["t"] and cost_headroom >= TIER_STRONG["cost_headroom_bps"]
            and n >= TIER_STRONG["n_min"]):
        tier = "STRONG"
    elif (abs_t >= TIER_MEDIUM["t"] and cost_headroom >= TIER_MEDIUM["cost_headroom_bps"]
            and n >= TIER_MEDIUM["n_min"]):
        tier = "MEDIUM"
    elif (abs_t >= TIER_WEAK["t"] or cost_headroom >= TIER_WEAK["cost_headroom_bps"]) \
            and n >= TIER_WEAK["n_min"]:
        tier = "WEAK"
    else:
        tier = "REJECT"

    score = abs_t * (1.0 if cost_headroom > 0 else -1.0)

    return {
        "event": event_label, "instrument": instrument,
        "n_events": n, "n_placebo": len(pl_rets),
        "event_mean_bps": event_mean, "placebo_mean_bps": placebo_mean,
        "null_gap_bps": null_gap, "t_stat": t_stat,
        "cost_floor_bps": cost_floor, "cost_headroom_bps": cost_headroom,
        "tier": tier, "score": score,
    }


# -----------------------------------------------------------------------------
# Grid definitions
# -----------------------------------------------------------------------------

YEARS = range(2019, 2027)


def build_grids():
    """Returns list of (event_label, gen_fn, instruments, tz, window)."""
    return [
        ("jpm_collar_close",       gen_jpm_collar_dates,    ["SPX500", "NDX100"],
            "US/Eastern", (15, 0, 16, 0)),
        ("month_end_wmr_fix",      gen_month_end_dates,     ["EURUSD", "USDJPY", "GBPUSD"],
            "Europe/London", (15, 45, 16, 15)),
        ("vix_soq_settle",         gen_vix_soq_dates,       ["SPX500"],
            "US/Eastern", (8, 30, 9, 30)),
        ("opex_day_after_am",      gen_opex_day_after_dates, ["SPX500", "NDX100"],
            "US/Eastern", (9, 30, 12, 0)),
        ("triple_witch_close",     gen_triple_witch_dates,  ["SPX500", "NDX100"],
            "US/Eastern", (15, 0, 16, 0)),
        ("month_end_usd_funding",  gen_month_end_dates,     ["EURUSD", "USDJPY", "GBPUSD"],
            "US/Eastern", (14, 0, 15, 0)),
        ("quarter_end_last_2h",    gen_jpm_collar_dates,    ["SPX500", "NDX100", "XAUUSD", "EURUSD"],
            "US/Eastern", (14, 0, 16, 0)),
    ]


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> int:
    section("Structural-flow calendar audit — Phase 0 screen")
    print(f"  Period   : {START_DATE} -> {END_DATE}")
    print(f"  Years    : {list(YEARS)}")

    grids = build_grids()
    print(f"  Grids    : {len(grids)} event-types")

    # Load all instruments upfront
    section("Loading instruments")
    all_instruments = sorted({inst for _, _, insts, _, _ in grids for inst in insts})
    bars_map: dict[str, pd.DataFrame] = {}
    for inst in all_instruments:
        df = load_m5(inst)
        if df is not None:
            bars_map[inst] = df
            print(f"  {inst:<8s}: {len(df):>8,} bars  {df.index[0].date()} -> {df.index[-1].date()}")
        else:
            print(f"  {inst:<8s}: SKIPPED")

    section("Evaluating grids")
    rows = []
    for event_label, gen_fn, insts, tz_name, win in grids:
        event_dates = gen_fn(YEARS)
        print(f"\n  [{event_label}] tz={tz_name} window={win[0]:02d}:{win[1]:02d}-{win[2]:02d}:{win[3]:02d} "
              f"n_events_cal={len(event_dates)}")
        for inst in insts:
            if inst not in bars_map:
                continue
            row = evaluate_grid(
                event_label, inst, bars_map[inst], event_dates, tz_name,
                win[0], win[1], win[2], win[3],
            )
            if row is None:
                continue
            print(f"    {inst:<8s} n_ev={row['n_events']:>3d} n_pl={row['n_placebo']:>4d}  "
                  f"ev_mean={row['event_mean_bps']:>+6.2f}  pl_mean={row['placebo_mean_bps']:>+6.2f}  "
                  f"gap={row['null_gap_bps']:>+6.2f}bp  t={row['t_stat']:>+5.2f}  "
                  f"cost_room={row['cost_headroom_bps']:>+6.2f}bp  [{row['tier']}]")
            rows.append(row)

    if not rows:
        print("\n  No rows. Check data loading.")
        return 1

    # ---- Ranked output ----
    df = pd.DataFrame(rows)
    df_sorted = df.sort_values(["tier", "score"], key=lambda c: c.map({
        "STRONG": 0, "MEDIUM": 1, "WEAK": 2, "REJECT": 3, "INSUFFICIENT_N": 4,
    }) if c.name == "tier" else -c, ascending=[True, True], na_position="last")

    section("Ranked output (all cells)")
    print(df_sorted[["event", "instrument", "n_events", "event_mean_bps",
                     "placebo_mean_bps", "null_gap_bps", "t_stat",
                     "cost_headroom_bps", "tier", "score"]]
          .to_string(index=False, float_format=lambda x: f"{x:+.2f}"))

    section("Survivors (STRONG + MEDIUM only)")
    surv = df_sorted[df_sorted["tier"].isin(["STRONG", "MEDIUM"])]
    if len(surv) == 0:
        print("  No STRONG or MEDIUM cells.")
    else:
        print(surv[["event", "instrument", "n_events", "null_gap_bps",
                    "t_stat", "cost_headroom_bps", "tier"]]
              .to_string(index=False, float_format=lambda x: f"{x:+.2f}"))

    section("Summary")
    tier_counts = df_sorted["tier"].value_counts()
    for tier in ["STRONG", "MEDIUM", "WEAK", "REJECT", "INSUFFICIENT_N"]:
        cnt = int(tier_counts.get(tier, 0))
        print(f"  {tier:<16s}: {cnt}")

    print(f"\n  Next move: each STRONG cell -> Phase 2 thesis lock with pre-committed kill criteria.")
    print(f"             each MEDIUM cell  -> queue, refine window/direction first.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
