#!/usr/bin/env python3
"""
Quarter-end XAU SHORT (14:00-16:00 ET, last biz day of Mar/Jun/Sep/Dec) —
Phase 0+ diagnostics BEFORE Phase 2 thesis lock.

Three pre-commit-gating checks:
  1. Regime breakdown (W1 2019-2020 / W2 2021-2022 / W3 2023-2026 holdout)
  2. Direction null-check (cost-stripped LONG vs SHORT)
  3. Corr-tombstone vs deployed xau_br_h1 (NY 12-18 UTC FADE)

If all three pass, Phase 2 thesis lock is justified.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))
sys.path.insert(0, os.path.join(_ROOT, "experiments", "_live", "xau_break_retest_m15"))
sys.path.insert(0, os.path.join(_ROOT, "experiments", "_live", "xau_break_retest_h1"))
sys.path.insert(0, _HERE)

from data import fetch_ohlc  # noqa: E402
from structural_flow_audit import (  # noqa: E402
    gen_jpm_collar_dates, compute_window_returns,
    COST_FLOOR_BPS, welch_t,
)
from xau_break_retest_m15_demo import (  # type: ignore  # noqa: E402
    simulate_break_retest_m15,
)
from xau_break_retest_h1_demo import (  # type: ignore  # noqa: E402
    load_h1,
    SESSION_START_UTC as H1_SESSION_START,
    SESSION_END_UTC as H1_SESSION_END,
    ENTRY_CUTOFF_UTC as H1_ENTRY_CUTOFF,
    H1_SWING_LOOKBACK, H1_RETEST_WINDOW, H1_RETEST_TOL_ATR,
    H1_STOP_ATR_MULT, H1_TIME_EXIT_BARS,
    COST_POINTS_DEFAULT as H1_COST,
)


START_DATE = "2019-01-01"
END_DATE = "2026-05-26"
TZ_NAME = "US/Eastern"
WIN_START_H, WIN_START_M = 14, 0
WIN_END_H, WIN_END_M = 16, 0
COST_FLOOR_XAU_BPS = COST_FLOOR_BPS["XAUUSD"]
YEARS = range(2019, 2027)


def section(t: str) -> None:
    print(f"\n{'=' * 92}\n  {t}\n{'=' * 92}\n")


def label_regime(d: date) -> str:
    if d.year <= 2020:
        return "W1_2019_2020"
    if d.year <= 2022:
        return "W2_2021_2022"
    return "W3_2023_2026"


def per_event_metrics(rets: np.ndarray, label: str = "") -> dict:
    rets = rets[np.isfinite(rets)]
    if len(rets) < 2:
        return {"n": len(rets), "mean": float("nan"), "std": float("nan"),
                "t": float("nan"), "wr": float("nan"), "sh_trade": float("nan")}
    mean = float(rets.mean())
    std = float(rets.std(ddof=1))
    se = std / np.sqrt(len(rets))
    t = mean / se if se > 0 else float("nan")
    wr = float((rets > 0).mean())
    sh_trade = mean / std if std > 0 else 0.0
    return {"n": len(rets), "mean": mean, "std": std, "t": t, "wr": wr,
            "sh_trade": sh_trade}


# -----------------------------------------------------------------------------
# Load data
# -----------------------------------------------------------------------------

def load_xau_m5() -> pd.DataFrame:
    df = fetch_ohlc("XAUUSD", "M5", START_DATE, END_DATE)
    df = df[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> int:
    section("Loading XAU M5")
    bars = load_xau_m5()
    print(f"  bars: {len(bars):,}  range {bars.index[0].date()} -> {bars.index[-1].date()}")

    event_dates = gen_jpm_collar_dates(YEARS)
    print(f"  candidate events (last biz day of Mar/Jun/Sep/Dec): {len(event_dates)}")

    section("Computing per-event LONG returns (14:00-16:00 ET)")
    long_rets_bps, kept_dates = compute_window_returns(
        bars, event_dates, TZ_NAME,
        WIN_START_H, WIN_START_M, WIN_END_H, WIN_END_M,
    )
    print(f"  kept events: {len(kept_dates)} (some dropped for missing bars)")
    long_m = per_event_metrics(long_rets_bps)
    print(f"  LONG: n={long_m['n']} mean={long_m['mean']:+.2f}bp "
          f"std={long_m['std']:.2f}bp t={long_m['t']:+.2f} WR={long_m['wr']*100:.1f}%")

    # SHORT is just negated bps
    short_rets_bps = -long_rets_bps
    short_m = per_event_metrics(short_rets_bps)
    print(f"  SHORT (no cost): n={short_m['n']} mean={short_m['mean']:+.2f}bp t={short_m['t']:+.2f} "
          f"WR={short_m['wr']*100:.1f}%")
    print(f"  SHORT (cost {COST_FLOOR_XAU_BPS}bp RT): mean_net={short_m['mean'] - COST_FLOOR_XAU_BPS:+.2f}bp")

    # =========================================================================
    # Diagnostic 1: Regime breakdown
    # =========================================================================
    section("Diagnostic 1 — Regime breakdown (SHORT direction, cost-net)")
    regimes = ["W1_2019_2020", "W2_2021_2022", "W3_2023_2026"]
    labels_arr = np.array([label_regime(d) for d in kept_dates])
    all_regimes_pos = True
    regime_results = {}
    print(f"  {'window':<16s} {'n':>3s} {'gross_bps':>10s} {'net_bps':>9s} {'t':>6s} {'sh_tr':>7s} {'wr':>6s}")
    for w in regimes:
        mask = labels_arr == w
        if mask.sum() < 2:
            print(f"  {w:<16s} INSUFFICIENT_N (n={mask.sum()})")
            all_regimes_pos = False
            regime_results[w] = None
            continue
        sub = short_rets_bps[mask]
        sub_m = per_event_metrics(sub)
        net_bps = sub_m['mean'] - COST_FLOOR_XAU_BPS
        regime_results[w] = {"gross": sub_m['mean'], "net": net_bps, "t": sub_m['t'],
                             "n": sub_m['n'], "sh": sub_m['sh_trade'], "wr": sub_m['wr']}
        marker = " " if net_bps > 0 else " <-- NET NEG"
        print(f"  {w:<16s} {sub_m['n']:>3d} {sub_m['mean']:>+9.2f} {net_bps:>+8.2f} "
              f"{sub_m['t']:>+5.2f} {sub_m['sh_trade']:>+6.2f} {sub_m['wr']*100:>5.1f}%{marker}")
        if net_bps <= 0:
            all_regimes_pos = False
    diag1_pass = all_regimes_pos
    print(f"\n  Diagnostic 1: {'PASS — all 3 regimes positive net of cost' if diag1_pass else 'FAIL — at least one regime is cost-net negative'}")

    # =========================================================================
    # Diagnostic 2: Direction null-check (cost-stripped)
    # =========================================================================
    section("Diagnostic 2 — Direction null-check (cost-stripped LONG vs SHORT)")
    long_gross_sh = long_rets_bps.mean() / long_rets_bps.std(ddof=1) if long_rets_bps.std(ddof=1) > 0 else 0.0
    short_gross_sh = -long_gross_sh
    dir_gap = short_gross_sh - long_gross_sh
    print(f"  LONG  zero-cost trade-Sharpe : {long_gross_sh:+.3f}  (mean {long_rets_bps.mean():+.2f}bp)")
    print(f"  SHORT zero-cost trade-Sharpe : {short_gross_sh:+.3f}  (mean {short_rets_bps.mean():+.2f}bp)")
    print(f"  Direction-gap (SHORT - LONG) : {dir_gap:+.3f}")
    diag2_pass = (short_gross_sh > 0) and (long_gross_sh < 0) and (dir_gap > 0.30)
    print(f"\n  Diagnostic 2: {'PASS — asymmetric edge, SHORT wins cleanly' if diag2_pass else 'FAIL — directional signal weak or symmetric (no edge above variance)'}")

    # =========================================================================
    # Diagnostic 3: Corr-tombstone vs deployed xau_br_h1
    # =========================================================================
    section("Diagnostic 3 — Corr-tombstone vs deployed xau_br_h1 (NY 12-18 UTC FADE)")
    # Run h1 simulator
    df_h1 = load_h1()
    h1_rets, h1_trades = simulate_break_retest_m15(
        df_h1, direction="fade",
        swing_lookback=H1_SWING_LOOKBACK,
        retest_window=H1_RETEST_WINDOW,
        retest_tol_atr=H1_RETEST_TOL_ATR,
        stop_atr_mult=H1_STOP_ATR_MULT,
        session_start_utc=H1_SESSION_START,
        session_end_utc=H1_SESSION_END,
        entry_cutoff_utc=H1_ENTRY_CUTOFF,
        time_exit_bars=H1_TIME_EXIT_BARS,
        cost_points=H1_COST,
    )
    print(f"  xau_br_h1 base: n_trades={len(h1_trades)}  total_period")

    # Per-day PnL aggregation for h1
    h1_daily = pd.DataFrame({
        "date": [pd.Timestamp(t["entry_ts"]).date() for t in h1_trades],
        "ret": h1_rets,
    }).groupby("date")["ret"].sum()

    # Candidate per-day PnL: SHORT, NET of cost
    # rets are in bps; convert to fractional via /1e4 to be comparable with h1 fractional
    candidate_daily_net = pd.Series(
        (short_rets_bps - COST_FLOOR_XAU_BPS) / 1e4,
        index=pd.Index(kept_dates, name="date"),
    )

    # Intersect on event dates
    common_dates = candidate_daily_net.index.intersection(h1_daily.index)
    print(f"  candidate events: {len(candidate_daily_net)}")
    print(f"  quarter-end days where h1 ALSO traded: {len(common_dates)}")
    if len(common_dates) < 5:
        print("  WARNING: too few overlap days for meaningful correlation")
        diag3_pass = True  # cannot reject for redundancy if h1 doesn't trade these days
        per_day_corr = float("nan")
        h1_qe_mean = float("nan")
        candidate_qe_mean = float("nan")
    else:
        cand_sub = candidate_daily_net.loc[common_dates].to_numpy()
        h1_sub = h1_daily.loc[common_dates].to_numpy()
        if h1_sub.std() == 0 or cand_sub.std() == 0:
            per_day_corr = float("nan")
        else:
            per_day_corr = float(np.corrcoef(cand_sub, h1_sub)[0, 1])
        h1_qe_mean = float(h1_sub.mean())
        candidate_qe_mean = float(cand_sub.mean())
        print(f"  per-day PnL correlation (candidate SHORT vs h1 FADE, on quarter-end days): {per_day_corr:+.3f}")
        print(f"  h1 mean PnL on quarter-end days: {h1_qe_mean * 1e4:+.2f}bp")
        print(f"  candidate mean PnL on quarter-end days: {candidate_qe_mean * 1e4:+.2f}bp")
        # Tombstone if corr > 0.70 (significant redundancy with existing deploy)
        diag3_pass = abs(per_day_corr) < 0.70
    print(f"\n  Diagnostic 3: {'PASS — independent of deployed h1 (corr < 0.70)' if diag3_pass else 'FAIL — significant overlap with h1, candidate is redundant'}")

    # =========================================================================
    # Summary
    # =========================================================================
    section("Summary — Phase 0+ diagnostics for quarter_end_xau_short")
    print(f"  Candidate          : XAU SHORT, 14:00-16:00 ET, last biz day of Mar/Jun/Sep/Dec")
    print(f"  n events           : {long_m['n']}")
    print(f"  SHORT mean (gross) : {short_m['mean']:+.2f}bp")
    print(f"  SHORT mean (net)   : {short_m['mean'] - COST_FLOOR_XAU_BPS:+.2f}bp")
    print(f"  SHORT t-stat       : {short_m['t']:+.2f}")
    print()
    print(f"  Diag 1 (regime breakdown) : {'PASS' if diag1_pass else 'FAIL'}")
    print(f"  Diag 2 (direction null)   : {'PASS' if diag2_pass else 'FAIL'}")
    print(f"  Diag 3 (corr vs h1)       : {'PASS' if diag3_pass else 'FAIL'}")
    all_pass = diag1_pass and diag2_pass and diag3_pass
    print()
    if all_pass:
        print(f"  -> ALL 3 PASS. Justified to lock Phase 2 thesis for quarter_end_xau_short.")
    else:
        print(f"  -> NOT all PASS. Phase 2 thesis lock NOT justified.")
        if not diag1_pass:
            print(f"     - Regime fragility: at least one window is net-negative")
        if not diag2_pass:
            print(f"     - Direction null: edge is symmetric, no real asymmetry")
        if not diag3_pass:
            print(f"     - Redundant with h1 (corr >= 0.70)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
