#!/usr/bin/env python3
"""Exploratory: per-quintile variance of ORB_DAX trades.

Question: do top-quintile (risk-on) days have HIGHER per-trade variance, or
just lower mean? If higher variance, a vol-targeting size-down rule has a real
ex-ante justification (independent of the rejected directional thesis).

Not a formal experiment. No thesis-doc / STATE updates intended.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# Reuse the existing simulator + composite to avoid duplication.
from sentiment_demo import (  # noqa: E402
    SYMBOL,
    COST_POINTS_ROUND_TRIP,
    QUINTILE_MIN_HISTORY,
    load_m5,
    simulate_orb_long_t180,
    build_composite,
    expanding_quintile_break,
)


def main() -> None:
    bars = load_m5(SYMBOL)
    comp_df = build_composite()
    composite_by_date = dict(zip(comp_df.index, comp_df["composite"].values))
    composite = comp_df["composite"]
    breaks = expanding_quintile_break(composite, 0.2, 0.8)
    breaks_idx = {d: (lo, hi) for d, lo, hi in zip(breaks.index, breaks["lo"], breaks["hi"])}

    _, trades = simulate_orb_long_t180(bars, cost_points=COST_POINTS_ROUND_TRIP)

    buckets: dict[str, list[float]] = {"Q1 (risk-off)": [], "mid Q2-Q4": [], "Q5 (risk-on)": []}
    for tr in trades:
        d = tr["entry_date"]
        comp = composite_by_date.get(d, np.nan)
        b = breaks_idx.get(d, None)
        if b is None or not np.isfinite(comp) or not np.isfinite(b[0]) or not np.isfinite(b[1]):
            continue
        lo, hi = b
        if comp <= lo:
            buckets["Q1 (risk-off)"].append(tr["pnl_net"])
        elif comp >= hi:
            buckets["Q5 (risk-on)"].append(tr["pnl_net"])
        else:
            buckets["mid Q2-Q4"].append(tr["pnl_net"])

    print(f"\n{'bucket':<18}  {'n':>5}  {'mean %':>9}  {'std %':>9}  {'mean/std':>10}  "
          f"{'down-stdev %':>13}  {'p05 %':>9}  {'p95 %':>9}")
    print("-" * 100)
    rows = []
    for name, arr in buckets.items():
        a = np.array(arr, dtype=np.float64) * 100  # to %
        mu = a.mean()
        sd = a.std(ddof=1)
        ms = mu / sd if sd > 0 else 0.0
        down = a[a < 0]
        down_sd = down.std(ddof=1) if down.size > 1 else 0.0
        p05 = np.quantile(a, 0.05)
        p95 = np.quantile(a, 0.95)
        rows.append((name, len(a), mu, sd, ms, down_sd, p05, p95))
        print(f"{name:<18}  {len(a):>5}  {mu:+9.4f}  {sd:9.4f}  {ms:+10.4f}  "
              f"{down_sd:13.4f}  {p05:+9.4f}  {p95:+9.4f}")

    # Levene / variance-ratio inferences.
    q5_arr = np.array(buckets["Q5 (risk-on)"]) * 100
    q1_arr = np.array(buckets["Q1 (risk-off)"]) * 100
    mid_arr = np.array(buckets["mid Q2-Q4"]) * 100

    print(f"\nVariance ratios (sample, not corrected for n)")
    print(f"  Q5 var / mid var  = {q5_arr.var(ddof=1) / mid_arr.var(ddof=1):+.4f}")
    print(f"  Q5 var / Q1 var   = {q5_arr.var(ddof=1) / q1_arr.var(ddof=1):+.4f}")
    print(f"  Q1 var / mid var  = {q1_arr.var(ddof=1) / mid_arr.var(ddof=1):+.4f}")

    # F-test rough p-value for Q5 vs mid (one-sided, "is Q5 more dispersed than mid").
    from scipy.stats import f as f_dist, levene  # type: ignore
    F = q5_arr.var(ddof=1) / mid_arr.var(ddof=1)
    df1, df2 = len(q5_arr) - 1, len(mid_arr) - 1
    p_upper = 1.0 - f_dist.cdf(F, df1, df2)
    print(f"  F-test  Q5 vs mid:  F={F:.3f}  df=({df1},{df2})  p(Q5>mid)={p_upper:.4f}")
    # Levene is more robust to non-normality.
    lev_stat, lev_p = levene(q5_arr, mid_arr, center='median')
    print(f"  Levene  Q5 vs mid:  W={lev_stat:.3f}  p={lev_p:.4f}")
    lev_stat2, lev_p2 = levene(q1_arr, mid_arr, center='median')
    print(f"  Levene  Q1 vs mid:  W={lev_stat2:.3f}  p={lev_p2:.4f}")

    # If Q5 is higher variance, what does vol-target sizing actually do?
    # Simulate: scale Q5 trades by w_q5 such that the WEIGHTED per-trade std matches the mid bucket.
    if q5_arr.std(ddof=1) > mid_arr.std(ddof=1):
        target_sd = mid_arr.std(ddof=1)
        w_q5 = target_sd / q5_arr.std(ddof=1)
    else:
        w_q5 = 1.0
    if q1_arr.std(ddof=1) > mid_arr.std(ddof=1):
        w_q1 = mid_arr.std(ddof=1) / q1_arr.std(ddof=1)
    else:
        w_q1 = 1.0
    print(f"\nVol-target weights (cap each tail at mid-bucket std):")
    print(f"  w_Q1 = {w_q1:.3f}   w_mid = 1.000   w_Q5 = {w_q5:.3f}")

    # What does the per-trade-EV-after-sizing look like?
    weighted_mean = (w_q1 * q1_arr.sum() + mid_arr.sum() + w_q5 * q5_arr.sum()) / \
                    (w_q1 * len(q1_arr) + len(mid_arr) + w_q5 * len(q5_arr))
    baseline_mean = (q1_arr.sum() + mid_arr.sum() + q5_arr.sum()) / \
                    (len(q1_arr) + len(mid_arr) + len(q5_arr))
    print(f"\nWeighted per-trade mean PnL (%):")
    print(f"  baseline (1/1/1):       {baseline_mean:+.4f}%")
    print(f"  vol-target (w_q1/1/w_q5): {weighted_mean:+.4f}%")
    print(f"  delta:                   {weighted_mean - baseline_mean:+.4f}%")
    print(f"  (only useful if positive AND if the freed risk budget allows a book-wide scale-up)")


if __name__ == "__main__":
    main()
