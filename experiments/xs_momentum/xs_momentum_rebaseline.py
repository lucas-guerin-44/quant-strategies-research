#!/usr/bin/env python3
"""
Cross-Sectional Momentum (XS-mom) long-only RE-BASELINE with honest IS/OOS
methodology.

The previous "baseline" (top_k=5, lookback=252, skip=21, rebalance=21) gave
Sharpe 0.61 / +130.14%, but subsequent parameter sweeps that suggested
top_k=3 / lookback=315 were run on the FULL 2015-2026 period -- classic
look-ahead leakage (the sweep "peeks" at the holdout to pick the winner).

This script fixes that by:
  Step 1. IS-only grid search on 2015-01-01 -> 2022-12-31 (180 configs).
  Step 2. Select the top-1 config by IS Sharpe.
  Step 3. Evaluate that config on the OOS holdout 2023-01-01 -> 2026-04-18.
  Step 4. Report the same config on the full 2015-2026 period for reference.
  Step 5. Regime stability: run IS-optimal params in 4 time slices.
  Step 6. Robustness: run top-10 IS configs OOS; report mean / std.

The simulation function ``run_xs_momentum`` is IMPORTED from
``examples/xs_momentum_validation.py`` unchanged. No files are modified.
"""

from __future__ import annotations

import os
import statistics
import sys
from itertools import product

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)  # research repo root
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))  # engine
sys.path.insert(0, _HERE)  # this strategy's directory (for xs_momentum_validation)
sys.path.insert(0, os.path.join(_EXPERIMENTS, 'tsmom'))  # sibling: tsmom_demo

# Re-use the validated simulation logic verbatim from the sibling file.
from xs_momentum_validation import (  # noqa: E402
    BARS_PER_YEAR,
    STARTING_CASH_DEFAULT,
    load_data,
    run_xs_momentum,
)

# Universe + cost schedule from tsmom_demo (as required by the task).
from tsmom_demo import COSTS_BY_SYMBOL, DEFAULT_COSTS, UNIVERSE  # noqa: E402


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

IS_START = "2015-01-01"
IS_END = "2022-12-31"
OOS_START = "2023-01-01"
OOS_END = "2026-04-18"
FULL_START = "2015-01-01"
FULL_END = "2026-04-18"

STABILITY_WINDOWS = [
    ("2015-01-01", "2017-10-15"),
    ("2017-10-16", "2020-07-31"),
    ("2020-08-01", "2023-05-15"),
    ("2023-05-16", "2026-04-18"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'=' * 80}\n  {title}\n{'=' * 80}\n")


def run_cfg(
    dataframes: dict[str, pd.DataFrame],
    start: str,
    end: str,
    cfg: dict,
) -> dict:
    return run_xs_momentum(
        dataframes,
        start_date=start,
        end_date=end,
        lookback_bars=cfg["lookback_bars"],
        skip_bars=cfg["skip_bars"],
        rebalance_bars=cfg["rebalance_bars"],
        top_k=cfg["top_k"],
        bottom_k=0,
        starting_cash=STARTING_CASH_DEFAULT,
        costs_bps=COSTS_BY_SYMBOL,
    )


def fmt_cfg(cfg: dict) -> str:
    return (f"lookback={cfg['lookback_bars']:>3d} "
            f"skip={cfg['skip_bars']:>2d} "
            f"rebal={cfg['rebalance_bars']:>2d} "
            f"top_k={cfg['top_k']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    section("Loading data (full span -- later sliced per window)")
    dataframes: dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        df = load_data(sym, FULL_START, FULL_END)
        if df is None or len(df) < 400:
            if df is not None:
                print(f"  {sym:<8s}  skipped ({len(df)} bars -- need >= 400)")
            continue
        dataframes[sym] = df
        print(f"  {sym:<8s}  {len(df):>5,} bars  "
              f"{df.index[0].date()} -> {df.index[-1].date()}")
    print(f"\n  {len(dataframes)} instruments loaded")

    if len(dataframes) < 6:
        print("Not enough instruments. Populate ohlc_data/ first.")
        sys.exit(1)

    # ------------------------------------------------------------------
    section("Step 1: IS-only grid search (2015-01-01 -> 2022-12-31)")
    # ------------------------------------------------------------------

    lookback_grid = [126, 189, 252, 315, 378]
    skip_grid = [0, 10, 21, 42]
    rebalance_grid = [21, 42, 63]
    top_k_grid = [3, 5, 7]

    n_configs = (len(lookback_grid) * len(skip_grid)
                 * len(rebalance_grid) * len(top_k_grid))
    print(f"  Grid size: {len(lookback_grid)} x {len(skip_grid)} x "
          f"{len(rebalance_grid)} x {len(top_k_grid)} = {n_configs} configs")
    print(f"  Evaluating on IS window {IS_START} -> {IS_END}")
    print("  (OOS window is untouched during this step.)\n")

    results: list[dict] = []
    for i, (lb, sk, rb, tk) in enumerate(
        product(lookback_grid, skip_grid, rebalance_grid, top_k_grid), 1
    ):
        cfg = dict(lookback_bars=lb, skip_bars=sk, rebalance_bars=rb, top_k=tk)
        r = run_cfg(dataframes, IS_START, IS_END, cfg)
        results.append({
            "cfg": cfg,
            "is_sharpe": r["sharpe"],
            "is_return": r["total_return"],
            "is_max_dd": r["max_dd"],
            "is_rebalances": r["rebalance_count"],
            "is_turnover": r["turnover_mean"],
        })
        if i % 30 == 0:
            print(f"  ...{i}/{n_configs} evaluated")

    # Rank by IS Sharpe.
    results.sort(key=lambda d: d["is_sharpe"], reverse=True)

    print(f"\n  Top 10 IS configs (by IS Sharpe):")
    print(f"  {'Rank':>4s}  {'Config':<42s} {'Sharpe':>8s} "
          f"{'Return %':>10s} {'MaxDD %':>10s}")
    print("  " + "-" * 80)
    for rank, row in enumerate(results[:10], 1):
        print(f"  {rank:>4d}  {fmt_cfg(row['cfg']):<42s} "
              f"{row['is_sharpe']:>+8.4f} "
              f"{row['is_return'] * 100:>+9.2f}% "
              f"{row['is_max_dd'] * 100:>+9.2f}%")

    # ------------------------------------------------------------------
    section("Step 2: Select IS-optimal params (top-1 by IS Sharpe)")
    # ------------------------------------------------------------------

    winner = results[0]
    is_cfg = winner["cfg"]

    print(f"  IS-optimal: {fmt_cfg(is_cfg)}")
    print(f"    IS Sharpe : {winner['is_sharpe']:+.4f}")
    print(f"    IS Return : {winner['is_return'] * 100:+.2f}%")
    print(f"    IS MaxDD  : {winner['is_max_dd'] * 100:+.2f}%")
    print(f"    IS Rebals : {winner['is_rebalances']}")
    print(f"    IS Turn.  : {winner['is_turnover']:.4f}")

    # ------------------------------------------------------------------
    section("Step 3: OOS holdout with IS-optimal params "
            "(2023-01-01 -> 2026-04-18)")
    # ------------------------------------------------------------------

    oos_res = run_cfg(dataframes, OOS_START, OOS_END, is_cfg)

    print(f"  {'Metric':<18s} {'IS':>12s} {'OOS':>12s}")
    print("  " + "-" * 44)
    print(f"  {'Return %':<18s} "
          f"{winner['is_return'] * 100:>+11.2f}% "
          f"{oos_res['total_return'] * 100:>+11.2f}%")
    print(f"  {'Sharpe':<18s} "
          f"{winner['is_sharpe']:>+12.4f} "
          f"{oos_res['sharpe']:>+12.4f}")
    print(f"  {'Max DD %':<18s} "
          f"{winner['is_max_dd'] * 100:>+11.2f}% "
          f"{oos_res['max_dd'] * 100:>+11.2f}%")
    print(f"  {'Rebalances':<18s} "
          f"{winner['is_rebalances']:>12d} "
          f"{oos_res['rebalance_count']:>12d}")
    print(f"  {'Avg turnover':<18s} "
          f"{winner['is_turnover']:>12.4f} "
          f"{oos_res['turnover_mean']:>12.4f}")

    degradation = winner["is_sharpe"] - oos_res["sharpe"]
    if degradation < 0.2:
        degr_tag = "robust"
    elif degradation < 0.5:
        degr_tag = "some overfitting"
    else:
        degr_tag = "heavily overfit"

    print(f"\n  Degradation (IS - OOS Sharpe): {degradation:+.4f}  [{degr_tag}]")

    # ------------------------------------------------------------------
    section("Step 4: Full-period reference (2015-2026) with IS-optimal params")
    # ------------------------------------------------------------------

    full_res = run_cfg(dataframes, FULL_START, FULL_END, is_cfg)

    print(f"  {'Metric':<22s} {'Value':>14s}")
    print("  " + "-" * 38)
    print(f"  {'Return':<22s} "
          f"{full_res['total_return'] * 100:>+13.2f}%")
    print(f"  {'Sharpe':<22s} "
          f"{full_res['sharpe']:>+14.4f}")
    print(f"  {'Max DD':<22s} "
          f"{full_res['max_dd'] * 100:>+13.2f}%")
    print(f"  {'Rebalances':<22s} "
          f"{full_res['rebalance_count']:>14d}")
    print(f"  {'Avg turnover / rebal':<22s} "
          f"{full_res['turnover_mean']:>14.4f}")

    # ------------------------------------------------------------------
    section("Step 5: Regime stability of IS-optimal config (4 windows)")
    # ------------------------------------------------------------------

    print(f"  Using IS-optimal params: {fmt_cfg(is_cfg)}\n")
    print(f"  {'Window':<28s} {'Return %':>10s} {'Sharpe':>8s} "
          f"{'MaxDD %':>10s} {'Rebals':>7s}")
    print("  " + "-" * 70)

    stability_sharpes = []
    for ws, we in STABILITY_WINDOWS:
        r = run_cfg(dataframes, ws, we, is_cfg)
        stability_sharpes.append(r["sharpe"])
        label = f"{ws} -> {we}"
        print(f"  {label:<28s} {r['total_return'] * 100:>+9.2f}% "
              f"{r['sharpe']:>+8.3f} {r['max_dd'] * 100:>+9.2f}% "
              f"{r['rebalance_count']:>7d}")

    n_pos_windows = sum(1 for s in stability_sharpes if s > 0)
    print(f"\n  Sharpe positive in {n_pos_windows}/{len(STABILITY_WINDOWS)} "
          f"windows")

    # ------------------------------------------------------------------
    section("Step 6: Top-10 IS configs evaluated OOS (robustness check)")
    # ------------------------------------------------------------------

    print(f"  {'Rank':>4s}  {'Config':<42s} "
          f"{'IS Sh':>8s} {'OOS Sh':>8s} {'OOS Ret %':>11s} {'OOS DD %':>10s}")
    print("  " + "-" * 90)

    top10_oos: list[dict] = []
    for rank, row in enumerate(results[:10], 1):
        oos_r = run_cfg(dataframes, OOS_START, OOS_END, row["cfg"])
        top10_oos.append({
            "rank": rank,
            "cfg": row["cfg"],
            "is_sharpe": row["is_sharpe"],
            "oos_sharpe": oos_r["sharpe"],
            "oos_return": oos_r["total_return"],
            "oos_max_dd": oos_r["max_dd"],
        })
        print(f"  {rank:>4d}  {fmt_cfg(row['cfg']):<42s} "
              f"{row['is_sharpe']:>+8.3f} "
              f"{oos_r['sharpe']:>+8.3f} "
              f"{oos_r['total_return'] * 100:>+10.2f}% "
              f"{oos_r['max_dd'] * 100:>+9.2f}%")

    oos_sharpes = [d["oos_sharpe"] for d in top10_oos]
    top10_mean = statistics.mean(oos_sharpes)
    top10_std = statistics.stdev(oos_sharpes) if len(oos_sharpes) > 1 else 0.0
    n_pos_oos = sum(1 for s in oos_sharpes if s > 0)

    print(f"\n  Top-10 OOS Sharpe: mean {top10_mean:+.4f}, "
          f"std {top10_std:.4f}")
    print(f"  Positive OOS: {n_pos_oos}/10")

    # ------------------------------------------------------------------
    section("FINAL REPORT")
    # ------------------------------------------------------------------

    # Overall decision logic.
    oos_sh = oos_res["sharpe"]
    if oos_sh > 0.3 and top10_mean > 0.3:
        overall = "KEEP"
        verdict_note = "Robust, real edge (OOS Sharpe > 0.3 AND top-10 mean > 0.3)."
    elif oos_sh > 0.3 and top10_mean < 0.0:
        overall = "INVESTIGATE"
        verdict_note = ("OOS Sharpe > 0.3 but top-10 mean < 0: we got lucky "
                        "with our single pick.")
    elif oos_sh < 0.2 and top10_mean < 0.2:
        overall = "REJECT"
        verdict_note = ("OOS Sharpe < 0.2 AND top-10 mean < 0.2: post-hoc "
                        "illusion, IS search did not generalize.")
    elif degradation >= 0.5:
        overall = "REJECT"
        verdict_note = ("Heavy degradation (IS - OOS >= 0.5): the IS "
                        "selection overfit.")
    elif oos_sh > 0.2 and top10_mean > 0.1 and n_pos_oos >= 6:
        overall = "KEEP"
        verdict_note = ("Decent OOS + majority of top-10 positive OOS: edge "
                        "appears to hold up.")
    else:
        overall = "INVESTIGATE"
        verdict_note = ("Mixed signals -- neither a clear KEEP nor a clear "
                        "REJECT. Needs more data or variant testing.")

    print("XS-MOM RE-BASELINED (IS-selected params)")
    print("=======================================")
    print(f"IS-optimal params:      lookback={is_cfg['lookback_bars']}, "
          f"skip={is_cfg['skip_bars']}, "
          f"rebalance={is_cfg['rebalance_bars']}, "
          f"top_k={is_cfg['top_k']}")
    print(f"IS performance:         "
          f"Return {winner['is_return'] * 100:+.2f}%  "
          f"Sharpe {winner['is_sharpe']:+.4f}  "
          f"DD {winner['is_max_dd'] * 100:+.2f}%")
    print(f"OOS performance:        "
          f"Return {oos_res['total_return'] * 100:+.2f}%  "
          f"Sharpe {oos_res['sharpe']:+.4f}  "
          f"DD {oos_res['max_dd'] * 100:+.2f}%")
    print(f"Degradation:            IS - OOS = {degradation:+.2f} "
          f"({degr_tag})")
    print(f"Full-period:            "
          f"Return {full_res['total_return'] * 100:+.2f}%  "
          f"Sharpe {full_res['sharpe']:+.4f}  "
          f"DD {full_res['max_dd'] * 100:+.2f}%")
    print()
    print(f"Regime stability:       Sharpe positive in "
          f"{n_pos_windows}/{len(STABILITY_WINDOWS)} windows")
    print(f"Top-10 IS configs OOS:  mean Sharpe {top10_mean:+.2f}, "
          f"std {top10_std:.2f}")
    print(f"                        ({n_pos_oos} of 10 positive OOS)")
    print()
    print(f"Overall:                {overall}")
    print(f"                        {verdict_note}")

    print()
    print("Interpretation guide")
    print("--------------------")
    print("  - OOS Sharpe > 0.3 AND top-10 OOS mean > 0.3 -> robust, real edge")
    print("  - OOS Sharpe > 0.3 but top-10 OOS mean < 0    -> lucky pick")
    print("  - OOS Sharpe < 0.2 AND top-10 OOS mean < 0.2  -> post-hoc illusion")

    print("\nDone.")


if __name__ == "__main__":
    main()
