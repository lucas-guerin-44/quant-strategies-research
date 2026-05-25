#!/usr/bin/env python3
"""Exploratory: vol-target the high-variance Q1 (risk-off) bucket.

Hypothesis from the variance diagnostic: Q1 contributes ~30% of total trade
variance with ~9% of trades. Halving Q1 weight should free risk budget for a
~1.13x book-wide scale-up at unchanged ex-ante daily vol.

Test: w_q1 in {1.0, 0.5, 0.3} × book scale {1.00, 1.13, 1.20}. Report Sharpe,
MDD, holdout, trade count. Not a formal experiment.
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


def apply_voltarget(
    ret_arr: np.ndarray,
    trades: list[dict],
    composite_by_date: dict,
    breaks_idx: dict,
    w_q1: float,
    w_q5: float,
    book_scale: float,
) -> np.ndarray:
    new_ret = ret_arr.copy()
    for tr in trades:
        d = tr["entry_date"]
        comp = composite_by_date.get(d, np.nan)
        b = breaks_idx.get(d, None)
        if b is None or not np.isfinite(comp) or not np.isfinite(b[0]) or not np.isfinite(b[1]):
            continue
        lo, hi = b
        if comp <= lo:
            w = w_q1
        elif comp >= hi:
            w = w_q5
        else:
            w = 1.0
        if w != 1.0:
            i0, i1 = tr["entry_bar_idx"], tr["exit_bar_idx"]
            new_ret[i0:i1 + 1] *= w
    if book_scale != 1.0:
        new_ret *= book_scale
    return new_ret


def regime_lines(label: str, ret_arr: np.ndarray, bars: pd.DataFrame) -> str:
    years = bars.index.year.values
    windows = [("19-20", (years >= 2019) & (years <= 2020)),
               ("21-22", (years >= 2021) & (years <= 2022)),
               ("23-26", years >= 2023)]
    parts = []
    for name, mask in windows:
        r = ret_arr[mask]
        eq = np.cumprod(1.0 + r)
        sh = annualized_sharpe_bar(r)
        dd = max_drawdown(eq)
        parts.append(f"{name} Sh {sh:+.2f}/DD {dd*100:+.1f}%")
    return f"  {label:<22}  " + "   ".join(parts)


def report(label: str, ret_arr: np.ndarray) -> dict:
    eq = np.cumprod(1.0 + ret_arr)
    sh = annualized_sharpe_bar(ret_arr)
    dd = max_drawdown(eq)
    tot = float(eq[-1] - 1.0)
    years = len(ret_arr) / BARS_PER_YEAR
    cagr = (1.0 + tot) ** (1.0 / years) - 1.0 if years > 0 and tot > -1 else float("nan")
    # ex-ante daily vol (approx): scale bar std to daily.
    bar_std = ret_arr.std(ddof=1)
    daily_vol_pct = bar_std * np.sqrt(BARS_PER_YEAR / 252) * 100
    return {
        "label": label, "sh": sh, "mdd": dd, "tot": tot, "cagr": cagr, "daily_vol": daily_vol_pct,
    }


def main() -> None:
    print(f"Loading data + composite...")
    bars = load_m5(SYMBOL)
    comp_df = build_composite()
    composite_by_date = dict(zip(comp_df.index, comp_df["composite"].values))
    breaks = expanding_quintile_break(comp_df["composite"], 0.2, 0.8)
    breaks_idx = {d: (lo, hi) for d, lo, hi in zip(breaks.index, breaks["lo"], breaks["hi"])}
    ret_arr, trades = simulate_orb_long_t180(bars, cost_points=COST_POINTS_ROUND_TRIP)

    print(f"\n{len(trades)} trades.  Bars: {len(ret_arr):,}\n")

    # Variant matrix.
    variants = [
        ("baseline",            1.0, 1.0, 1.00),
        ("w_Q1=0.5",            0.5, 1.0, 1.00),
        ("w_Q1=0.5  *1.13",     0.5, 1.0, 1.13),
        ("w_Q1=0.5  *1.20",     0.5, 1.0, 1.20),
        ("w_Q1=0.3",            0.3, 1.0, 1.00),
        ("w_Q1=0.3  *1.20",     0.3, 1.0, 1.20),
        ("w_Q1=0.3  *1.30",     0.3, 1.0, 1.30),
        ("w_Q1=0.0 (skip Q1)",  0.0, 1.0, 1.00),
        ("w_Q1=0.0  *1.13",     0.0, 1.0, 1.13),
        # combo: vol-target Q1 AND skip Q5 (from mirror result)
        ("w_Q1=0.5  w_Q5=0.0",  0.5, 0.0, 1.00),
        ("w_Q1=0.5  w_Q5=0.0  *1.20", 0.5, 0.0, 1.20),
    ]

    print(f"{'variant':<30}  {'Sh':>6}  {'MDD %':>7}  {'CAGR %':>7}  {'TotRet %':>8}  {'~vol %':>7}")
    print("-" * 80)
    results = []
    for name, wq1, wq5, scale in variants:
        new_ret = apply_voltarget(ret_arr, trades, composite_by_date, breaks_idx, wq1, wq5, scale)
        r = report(name, new_ret)
        r["new_ret"] = new_ret
        results.append(r)
        print(f"{name:<30}  {r['sh']:+6.3f}  {r['mdd']*100:+7.2f}  "
              f"{r['cagr']*100:+7.2f}  {r['tot']*100:+8.2f}  {r['daily_vol']:7.3f}")

    # Regime breakdown for baseline and top 3 variants by Sharpe.
    print(f"\nRegime breakdown (top variants by Sharpe)")
    print("-" * 80)
    by_sh = sorted(results, key=lambda r: -r["sh"])[:4]
    for r in by_sh:
        print(regime_lines(r["label"], r["new_ret"], bars))

    # Honest summary.
    baseline = next(r for r in results if r["label"] == "baseline")
    best = max(results, key=lambda r: r["sh"])
    print(f"\nBaseline Sharpe {baseline['sh']:+.3f} (vol {baseline['daily_vol']:.3f}%)")
    print(f"Best variant '{best['label']}': Sharpe {best['sh']:+.3f} (vol {best['daily_vol']:.3f}%)")
    print(f"Delta Sh: {best['sh'] - baseline['sh']:+.3f}")
    print(f"Vol parity check: scale the BASELINE so its daily-vol matches '{best['label']}' "
          f"({best['daily_vol']:.3f}%) -- this gives the same Sharpe ({baseline['sh']:+.3f}) "
          f"by construction, but useful as a CAGR-at-equal-risk comparison:")
    parity_scale = best['daily_vol'] / baseline['daily_vol']
    parity_ret = baseline['new_ret'] if 'new_ret' in baseline else baseline.get('new_ret')
    # baseline doesn't store new_ret -- recompute:
    base_ret = apply_voltarget(ret_arr, trades, composite_by_date, breaks_idx, 1.0, 1.0, parity_scale)
    base_r = report(f"baseline *{parity_scale:.3f}", base_ret)
    print(f"  baseline *{parity_scale:.3f}:  Sh {base_r['sh']:+.3f}  CAGR {base_r['cagr']*100:+.2f}%  "
          f"MDD {base_r['mdd']*100:+.2f}%  vol {base_r['daily_vol']:.3f}%")
    print(f"  '{best['label']}':  Sh {best['sh']:+.3f}  CAGR {best['cagr']*100:+.2f}%  "
          f"MDD {best['mdd']*100:+.2f}%  vol {best['daily_vol']:.3f}%")
    print(f"  CAGR delta at equal risk: {(best['cagr'] - base_r['cagr'])*100:+.3f} pp")


if __name__ == "__main__":
    main()
