#!/usr/bin/env python3
"""Exploratory: symmetric null check on the vol-target-Q1 + skip-Q5 combo.

If the combo signal is real:
 - inverting BOTH levers should produce markedly worse Sharpe (gap >= +0.20)
 - decomposing the combo lift into its two parts shows how much is the
   defensible vol-target piece vs the post-hoc mirror-direction piece
"""

from __future__ import annotations

import os
import sys
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from sentiment_demo import (  # noqa: E402
    SYMBOL,
    COST_POINTS_ROUND_TRIP,
    BARS_PER_YEAR,
    load_m5,
    simulate_orb_long_t180,
    build_composite,
    expanding_quintile_break,
    annualized_sharpe_bar,
    max_drawdown,
)
from _explore_voltarget_q1 import apply_voltarget, regime_lines  # noqa: E402


def main() -> None:
    bars = load_m5(SYMBOL)
    comp_df = build_composite()
    composite_by_date = dict(zip(comp_df.index, comp_df["composite"].values))
    breaks = expanding_quintile_break(comp_df["composite"], 0.2, 0.8)
    breaks_idx = {d: (lo, hi) for d, lo, hi in zip(breaks.index, breaks["lo"], breaks["hi"])}
    ret_arr, trades = simulate_orb_long_t180(bars, cost_points=COST_POINTS_ROUND_TRIP)

    print(f"{len(trades)} trades.\n")

    # Decomposition + null grid.
    variants = [
        # (label, w_q1, w_q5, comment)
        ("baseline",                 1.0, 1.0, "control"),
        ("VOL-TARGET only (w_q1=0.5)",     0.5, 1.0, "ex-ante vol-target leg alone"),
        ("MIRROR only (w_q5=0.0)",         1.0, 0.0, "post-hoc Q5-skip leg alone"),
        ("COMBO (vol-target + mirror)",    0.5, 0.0, "both levers together"),
        # Symmetric null: invert both directions.
        ("NULL: SWAP both (w_q1=0.0, w_q5=0.5)", 0.0, 0.5, "full sign-flip of combo"),
        # Partial nulls: each leg inverted.
        ("NULL: w_q1=0.0 (skip the alpha bucket)",    0.0, 1.0, "invert vol-target leg only"),
        ("NULL: w_q5=2.0 (size up the loser bucket)", 1.0, 2.0, "invert mirror leg only"),
        # Random sanity: flip BOTH inversions on top of each other
        ("NULL: w_q1=0.0 + w_q5=2.0",                 0.0, 2.0, "double-null"),
    ]

    print(f"{'variant':<48}  {'Sh':>6}  {'MDD %':>7}  {'CAGR %':>7}  {'~vol %':>7}   note")
    print("-" * 110)
    results = {}
    for name, wq1, wq5, note in variants:
        new_ret = apply_voltarget(ret_arr, trades, composite_by_date, breaks_idx, wq1, wq5, 1.0)
        eq = np.cumprod(1.0 + new_ret)
        sh = annualized_sharpe_bar(new_ret)
        dd = max_drawdown(eq)
        tot = float(eq[-1] - 1.0)
        years = len(new_ret) / BARS_PER_YEAR
        cagr = (1.0 + tot) ** (1.0 / years) - 1.0
        vol = new_ret.std(ddof=1) * np.sqrt(BARS_PER_YEAR / 252) * 100
        results[name] = {"sh": sh, "mdd": dd, "cagr": cagr, "vol": vol, "ret": new_ret}
        print(f"{name:<48}  {sh:+6.3f}  {dd*100:+7.2f}  {cagr*100:+7.2f}  {vol:7.3f}   {note}")

    print()
    base = results["baseline"]["sh"]
    vol_only = results["VOL-TARGET only (w_q1=0.5)"]["sh"]
    mir_only = results["MIRROR only (w_q5=0.0)"]["sh"]
    combo = results["COMBO (vol-target + mirror)"]["sh"]
    null = results["NULL: SWAP both (w_q1=0.0, w_q5=0.5)"]["sh"]

    print(f"Decomposition:")
    print(f"  Baseline Sh:               {base:+.3f}")
    print(f"  + Vol-target leg adds:     {vol_only - base:+.3f}   (ex-ante defensible)")
    print(f"  + Mirror leg adds:         {mir_only - base:+.3f}   (post-hoc)")
    print(f"  Sum of legs would be:      {(vol_only - base) + (mir_only - base):+.3f}  (additive estimate)")
    print(f"  Combo actually delivers:   {combo - base:+.3f}  (delta = "
          f"{(combo - base) - ((vol_only - base) + (mir_only - base)):+.3f} interaction)")
    print()
    print(f"Null check (combo signal must hurt clearly when sign-flipped):")
    print(f"  Combo Sh:                  {combo:+.3f}")
    print(f"  Sign-flip null Sh:         {null:+.3f}")
    print(f"  Null-gap (combo - null):   {combo - null:+.3f}   (pre-committed threshold: +0.20)")
    if combo - null >= 0.20:
        print(f"  >>> PASS the +0.20 null-gap threshold")
    else:
        print(f"  >>> FAIL the +0.20 null-gap threshold by {0.20 - (combo - null):+.3f}")
    print()
    print(f"Per-leg null sanity (each null should also be markedly worse than baseline):")
    for nm in ["NULL: w_q1=0.0 (skip the alpha bucket)",
              "NULL: w_q5=2.0 (size up the loser bucket)"]:
        r = results[nm]
        print(f"  {nm:<48} Sh {r['sh']:+.3f}  (delta vs baseline {r['sh'] - base:+.3f})")

    print()
    print(f"Regime breakdown for null variants:")
    for nm in ["NULL: SWAP both (w_q1=0.0, w_q5=0.5)",
              "NULL: w_q1=0.0 (skip the alpha bucket)",
              "NULL: w_q5=2.0 (size up the loser bucket)",
              "NULL: w_q1=0.0 + w_q5=2.0"]:
        print(regime_lines(nm, results[nm]["ret"], bars))


if __name__ == "__main__":
    main()
