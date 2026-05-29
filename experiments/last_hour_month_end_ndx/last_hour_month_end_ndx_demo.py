#!/usr/bin/env python3
"""
Phase 2 simulator — Last-hour-of-month-end NDX100 (direction-neutral pre-commit).

Thesis: experiments/last_hour_month_end_ndx/last_hour_month_end_ndx.md

Rules:
  Universe : NDX100 M5
  Trigger  : last business day of every month
  Window   : 15:00 -> 16:00 ET local (last cash-equity hour, DST-aware)
  Direction: BOTH (pre-commit per lesson #54); data direction-selects
  Entry    : 15:00 ET open
  Exit     : 16:00 ET close
  Cost     : 0.5 pt RT default; sweep 0.25 / 0.5 / 1.0 / 2.0 pt

Runs the 13 pre-committed kill criteria on the BEST of {LONG, SHORT}.
Direction-lock criterion #13 requires the same direction to win in all
3 regime windows — sign-flip across regime = REJECT.

Usage:
  venv/Scripts/python.exe experiments/last_hour_month_end_ndx/last_hour_month_end_ndx_demo.py
"""

from __future__ import annotations

import os
import sys
from datetime import date

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))
sys.path.insert(0, os.path.join(_ROOT, "experiments", "structural_flow_audit"))

from data import fetch_ohlc  # noqa: E402
from structural_flow_audit import (  # noqa: E402
    gen_month_end_dates, compute_window_returns, compute_placebo_returns,
)


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

START_DATE = "2019-01-01"
END_DATE = "2026-05-26"
TZ_NAME = "US/Eastern"
WIN_START_H, WIN_START_M = 15, 0
WIN_END_H, WIN_END_M = 16, 0

NDX_REF_PRICE = 20000.0          # approximate, for bp conversion
COST_POINTS_DEFAULT = 0.5         # ~0.25 bp on $20k
COST_POINTS_STRESS = 1.0          # ~0.5 bp (criterion #10)
COST_POINTS_SWEEP = (0.25, 0.5, 1.0, 2.0)

EVENTS_PER_YEAR = 12

YEARS = range(2019, 2027)
# 17 structural-audit screen cells + this 2-direction test = 19 effective trials
N_SCREEN_TRIALS = 19

# Pre-committed kill criteria thresholds (FROZEN — set in thesis BEFORE running)
KC1_FULL_MEAN_NET = 1.5
KC2_W3_MEAN_NET = 1.0
KC4_ANN_SH = 0.30
KC5_WR = 0.50
KC6_MDD = 0.03
KC7_BOOT_LOWER_GT = 0.0
KC8_DIR_GAP = 0.30
KC9_PLACEBO_MAG = 1.0
KC10_COST_STRESS_NET = 0.0
KC11_DEFLATED_SH = 0.20


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def section(t: str) -> None:
    print(f"\n{'=' * 92}\n  {t}\n{'=' * 92}\n")


def label_regime(d: date) -> str:
    if d.year <= 2020:
        return "W1_2019_2020"
    if d.year <= 2022:
        return "W2_2021_2022"
    return "W3_2023_2026"


def annualized_sharpe_event(rets_bps: np.ndarray,
                            events_per_year: float = EVENTS_PER_YEAR) -> float:
    rets = rets_bps[np.isfinite(rets_bps)]
    if len(rets) < 2:
        return 0.0
    std = rets.std(ddof=1)
    if std == 0:
        return 0.0
    return float(rets.mean() / std * np.sqrt(events_per_year))


def equity_mdd(rets_frac: np.ndarray) -> float:
    if len(rets_frac) == 0:
        return 0.0
    eq = (1.0 + rets_frac).cumprod()
    rm = np.maximum.accumulate(eq)
    dd = (eq - rm) / rm
    return float(dd.min())


def bootstrap_mean_ci(rets: np.ndarray, n_iter: int = 5000, alpha: float = 0.05,
                     seed: int = 42) -> tuple[float, float, float]:
    if len(rets) < 2:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    n = len(rets)
    boot_means = np.empty(n_iter, dtype=np.float64)
    for i in range(n_iter):
        sample = rng.choice(rets, size=n, replace=True)
        boot_means[i] = sample.mean()
    return (
        float(np.quantile(boot_means, alpha / 2)),
        float(rets.mean()),
        float(np.quantile(boot_means, 1 - alpha / 2)),
    )


def deflated_sharpe(observed_sh: float, returns: np.ndarray, n_trials: int) -> float:
    from math import sqrt, log
    if len(returns) < 4 or n_trials <= 1:
        return observed_sh
    e_max = sqrt(2.0 * log(n_trials)) * (1.0 / sqrt(len(returns)))
    return float(observed_sh - e_max)


def cost_bps_from_points(cost_pt: float, ref_price: float = NDX_REF_PRICE) -> float:
    return cost_pt / ref_price * 1e4


# -----------------------------------------------------------------------------
# Data
# -----------------------------------------------------------------------------

def load_ndx_m5() -> pd.DataFrame:
    df = fetch_ohlc("NDX100", "M5", START_DATE, END_DATE)
    df = df[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


# -----------------------------------------------------------------------------
# Per-direction metrics block
# -----------------------------------------------------------------------------

def direction_metrics(long_bps: np.ndarray, kept_dates: list,
                      direction: str, cost_bps: float) -> dict:
    """direction in {'long','short'}; returns full metrics block."""
    raw = long_bps if direction == "long" else -long_bps
    net = raw - cost_bps
    n = len(net)
    if n < 2:
        return {"n": n, "direction": direction}
    mean = float(net.mean())
    std = float(net.std(ddof=1))
    sh_trade = mean / std if std > 0 else 0.0
    sh_ann = annualized_sharpe_event(net)
    wr = float((net > 0).mean())
    rets_frac = net / 1e4
    mdd = equity_mdd(rets_frac)
    gw = float(net[net > 0].sum())
    gl = float(-net[net <= 0].sum())
    pf = gw / gl if gl > 0 else float("inf")

    labels = np.array([label_regime(d) for d in kept_dates])
    regimes = {}
    for w in ["W1_2019_2020", "W2_2021_2022", "W3_2023_2026"]:
        m = labels == w
        if m.sum() < 2:
            regimes[w] = {"n": int(m.sum()), "mean": float("nan"), "sh_ann": float("nan")}
            continue
        sub = net[m]
        regimes[w] = {
            "n": int(m.sum()),
            "mean": float(sub.mean()),
            "sh_ann": annualized_sharpe_event(sub),
        }

    return {
        "n": n, "direction": direction, "mean": mean, "std": std,
        "sh_trade": sh_trade, "sh_ann": sh_ann, "wr": wr, "pf": pf, "mdd": mdd,
        "regimes": regimes, "net": net, "raw": raw,
    }


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> int:
    section("Loading NDX100 M5")
    bars = load_ndx_m5()
    print(f"  bars: {len(bars):,}  range {bars.index[0].date()} -> {bars.index[-1].date()}")

    event_dates = gen_month_end_dates(YEARS)
    print(f"  calendar events: {len(event_dates)} (last biz day of every month)")

    section("Per-event LONG returns (15:00-16:00 ET) — gross")
    long_bps, kept = compute_window_returns(
        bars, event_dates, TZ_NAME,
        WIN_START_H, WIN_START_M, WIN_END_H, WIN_END_M,
    )
    print(f"  kept: {len(kept)} events")
    cost_default_bps = cost_bps_from_points(COST_POINTS_DEFAULT)
    print(f"  cost: {COST_POINTS_DEFAULT}pt = {cost_default_bps:.2f} bps RT")

    # ----------------------------------------------------------------------
    # Both directions
    # ----------------------------------------------------------------------
    section("BOTH directions side-by-side (lesson #54)")
    L = direction_metrics(long_bps, kept, "long", cost_default_bps)
    S = direction_metrics(long_bps, kept, "short", cost_default_bps)
    print(f"  {'metric':<22s} {'LONG':>10s} {'SHORT':>10s}")
    print(f"  {'n':<22s} {L['n']:>10d} {S['n']:>10d}")
    print(f"  {'mean net (bps)':<22s} {L['mean']:>+10.2f} {S['mean']:>+10.2f}")
    print(f"  {'trade-Sharpe':<22s} {L['sh_trade']:>+10.3f} {S['sh_trade']:>+10.3f}")
    print(f"  {'ann-Sharpe':<22s} {L['sh_ann']:>+10.3f} {S['sh_ann']:>+10.3f}")
    print(f"  {'WR':<22s} {L['wr']*100:>9.1f}% {S['wr']*100:>9.1f}%")
    print(f"  {'PF':<22s} {L['pf']:>10.2f} {S['pf']:>10.2f}")
    print(f"  {'MDD':<22s} {L['mdd']*100:>+9.2f}% {S['mdd']*100:>+9.2f}%")

    # Best direction
    best = L if L["sh_ann"] >= S["sh_ann"] else S
    worst = S if best is L else L
    print(f"\n  Best direction: **{best['direction'].upper()}** (ann-Sh {best['sh_ann']:+.2f})")
    print(f"  Worst direction: {worst['direction'].upper()} (ann-Sh {worst['sh_ann']:+.2f})")
    dir_gap = best["sh_trade"] - worst["sh_trade"]
    print(f"  Direction-gap (best - worst, trade-Sh): {dir_gap:+.3f}")

    # ----------------------------------------------------------------------
    # Best direction — full metrics & regime
    # ----------------------------------------------------------------------
    section(f"Best-direction ({best['direction'].upper()}) regime breakdown")
    print(f"  {'window':<16s} {'n':>3s} {'mean (bps)':>11s} {'sh_ann':>8s}")
    for w in ["W1_2019_2020", "W2_2021_2022", "W3_2023_2026"]:
        r = best["regimes"][w]
        if r.get("mean") is None or (isinstance(r.get("mean"), float) and np.isnan(r["mean"])):
            print(f"  {w:<16s} {r['n']:>3d}    INSUFFICIENT")
            continue
        print(f"  {w:<16s} {r['n']:>3d} {r['mean']:>+10.2f} {r['sh_ann']:>+7.2f}")

    section(f"Worst-direction ({worst['direction'].upper()}) regime breakdown — for direction-lock check")
    print(f"  {'window':<16s} {'n':>3s} {'mean (bps)':>11s} {'sh_ann':>8s}")
    for w in ["W1_2019_2020", "W2_2021_2022", "W3_2023_2026"]:
        r = worst["regimes"][w]
        if r.get("mean") is None or (isinstance(r.get("mean"), float) and np.isnan(r["mean"])):
            print(f"  {w:<16s} {r['n']:>3d}    INSUFFICIENT")
            continue
        print(f"  {w:<16s} {r['n']:>3d} {r['mean']:>+10.2f} {r['sh_ann']:>+7.2f}")

    # ----------------------------------------------------------------------
    # Criterion #13: direction-lock check
    # ----------------------------------------------------------------------
    section("Criterion #13 — direction lock across regimes")
    best_dir = best["direction"]
    direction_lock = True
    for w in ["W1_2019_2020", "W2_2021_2022", "W3_2023_2026"]:
        L_w = L["regimes"][w].get("mean", float("nan"))
        S_w = S["regimes"][w].get("mean", float("nan"))
        if np.isnan(L_w) or np.isnan(S_w):
            direction_lock = False
            print(f"  {w}: INSUFFICIENT_N -> direction-lock FAIL")
            continue
        # Best direction's regime-mean must be net-positive
        w_winner = "long" if L_w >= S_w else "short"
        if w_winner != best_dir:
            direction_lock = False
            print(f"  {w}: full-sample best={best_dir.upper()} BUT regime winner is {w_winner.upper()} -> FAIL")
        else:
            print(f"  {w}: regime winner {w_winner.upper()} == full-sample best -> OK")
    print(f"\n  Direction-lock: {'PASS' if direction_lock else 'FAIL'}")

    # ----------------------------------------------------------------------
    # Bootstrap CI on best direction
    # ----------------------------------------------------------------------
    section("Bootstrap 95% CI (best direction, full sample)")
    boot_lo, boot_pt, boot_hi = bootstrap_mean_ci(best["net"])
    print(f"  point: {boot_pt:+.2f} bps    95% CI [{boot_lo:+.2f}, {boot_hi:+.2f}] bps")

    # ----------------------------------------------------------------------
    # Placebo on best direction
    # ----------------------------------------------------------------------
    section("Placebo non-event same-weekday days (best direction)")
    event_set = set(kept)
    weekdays = {d.weekday() for d in kept}
    plc_long_bps = compute_placebo_returns(
        bars, event_set, TZ_NAME, weekdays,
        WIN_START_H, WIN_START_M, WIN_END_H, WIN_END_M,
        max_samples=1500,
    )
    plc_raw = plc_long_bps if best_dir == "long" else -plc_long_bps
    plc_mean = float(plc_raw.mean()) if len(plc_raw) > 0 else float("nan")
    print(f"  n placebo: {len(plc_raw)}")
    print(f"  best-direction placebo mean (gross): {plc_mean:+.2f} bps")

    # ----------------------------------------------------------------------
    # Cost sweep on best direction
    # ----------------------------------------------------------------------
    section(f"Cost-sensitivity sweep (best direction = {best_dir.upper()})")
    print(f"  {'cost_pt':<8s} {'cost_bp':<8s} {'mean (bps)':>11s} {'ann-Sh':>8s}")
    cost_stress_net = None
    for cp in COST_POINTS_SWEEP:
        cbps = cost_bps_from_points(cp)
        net_var = (long_bps if best_dir == "long" else -long_bps) - cbps
        m = float(net_var.mean())
        s = float(net_var.std(ddof=1))
        sh = m / s * np.sqrt(EVENTS_PER_YEAR) if s > 0 else 0.0
        marker = ("  (default)" if cp == COST_POINTS_DEFAULT else
                  "  (stress 2x)" if cp == COST_POINTS_STRESS else "")
        print(f"  {cp:<8.2f} {cbps:<8.2f} {m:>+10.2f} {sh:>+7.2f}{marker}")
        if cp == COST_POINTS_STRESS:
            cost_stress_net = m

    # ----------------------------------------------------------------------
    # Walk-forward halves on best direction
    # ----------------------------------------------------------------------
    section("Walk-forward halves (best direction)")
    n_total = len(best["net"])
    midpoint = n_total // 2
    h1 = best["net"][:midpoint]
    h2 = best["net"][midpoint:]
    h1_mean = float(h1.mean()) if len(h1) >= 2 else float("nan")
    h2_mean = float(h2.mean()) if len(h2) >= 2 else float("nan")
    h1_sh = float(h1.mean() / h1.std(ddof=1) * np.sqrt(EVENTS_PER_YEAR)) if len(h1) >= 2 and h1.std(ddof=1) > 0 else 0.0
    h2_sh = float(h2.mean() / h2.std(ddof=1) * np.sqrt(EVENTS_PER_YEAR)) if len(h2) >= 2 and h2.std(ddof=1) > 0 else 0.0
    print(f"  H1 ({len(h1)} events, {kept[0]} -> {kept[midpoint - 1]}): "
          f"mean {h1_mean:+.2f} bps  sh_ann {h1_sh:+.2f}")
    print(f"  H2 ({len(h2)} events, {kept[midpoint]} -> {kept[-1]}): "
          f"mean {h2_mean:+.2f} bps  sh_ann {h2_sh:+.2f}")

    # ----------------------------------------------------------------------
    # Deflated Sharpe
    # ----------------------------------------------------------------------
    section(f"Deflated Sharpe (n_trials={N_SCREEN_TRIALS} — 17 screen + 2-direction)")
    dsh = deflated_sharpe(best["sh_ann"], best["net"], n_trials=N_SCREEN_TRIALS)
    print(f"  observed ann-Sh: {best['sh_ann']:+.3f}")
    print(f"  deflated ann-Sh: {dsh:+.3f}")

    # ----------------------------------------------------------------------
    # Kill criteria
    # ----------------------------------------------------------------------
    section("Phase 2 pre-committed kill criteria (13)")
    w1 = best["regimes"]["W1_2019_2020"].get("mean", float("nan"))
    w2 = best["regimes"]["W2_2021_2022"].get("mean", float("nan"))
    w3 = best["regimes"]["W3_2023_2026"].get("mean", float("nan"))
    all_regs_pos = all((not np.isnan(x)) and x > 0 for x in (w1, w2, w3))

    criteria = [
        ("1. Best-dir full mean net >= +1.5 bp", best["mean"] >= KC1_FULL_MEAN_NET,
            f"{best['mean']:+.2f} bp  (dir={best_dir.upper()})"),
        ("2. Best-dir W3 mean net >= +1.0 bp",
            (not np.isnan(w3)) and w3 >= KC2_W3_MEAN_NET,
            f"W3={w3:+.2f} bp"),
        ("3. All 3 regimes net positive (best)", all_regs_pos,
            f"W1={w1:+.2f} W2={w2:+.2f} W3={w3:+.2f}"),
        ("4. Annualized Sharpe >= +0.30", best["sh_ann"] >= KC4_ANN_SH,
            f"sh_ann={best['sh_ann']:+.2f}"),
        ("5. WR >= 50%", best["wr"] >= KC5_WR,
            f"WR={best['wr']*100:.1f}%"),
        ("6. MDD <= -3%", abs(best["mdd"]) <= KC6_MDD,
            f"mdd={best['mdd']*100:+.2f}%"),
        ("7. Bootstrap 95% CI lower > 0", boot_lo > KC7_BOOT_LOWER_GT,
            f"[{boot_lo:+.2f}, {boot_hi:+.2f}]"),
        ("8. Direction-gap >= +0.30", dir_gap >= KC8_DIR_GAP,
            f"{dir_gap:+.2f}"),
        ("9. Placebo |mean| < 1 bp", abs(plc_mean) < KC9_PLACEBO_MAG,
            f"{plc_mean:+.2f} bp"),
        ("10. Cost-stress 2x net > 0",
            cost_stress_net is not None and cost_stress_net > KC10_COST_STRESS_NET,
            f"{cost_stress_net:+.2f} bp" if cost_stress_net else "n/a"),
        ("11. Deflated Sharpe >= +0.20", dsh >= KC11_DEFLATED_SH,
            f"{dsh:+.2f}"),
        ("12. WF halves both net > 0",
            (h1_mean > 0) and (h2_mean > 0),
            f"H1={h1_mean:+.2f} H2={h2_mean:+.2f}"),
        ("13. Direction-lock across regimes", direction_lock,
            "all 3 regimes winner = full-sample winner" if direction_lock else "regime sign-flip"),
    ]
    n_pass = 0
    for name, ok, msg in criteria:
        tag = "PASS" if ok else "FAIL"
        print(f"  [{tag}] {name:<44s}  {msg}")
        if ok:
            n_pass += 1
    print(f"\n  Result: {n_pass}/13  ->  {'PASS' if n_pass == 13 else 'REJECT'}")

    # ----------------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------------
    section("Summary")
    print(f"  last_hour_month_end_ndx: NDX100 M5, 15-16 ET, last biz day of every month")
    print(f"  best direction: {best_dir.upper()}  (LONG sh {L['sh_ann']:+.2f} / SHORT sh {S['sh_ann']:+.2f})")
    print(f"  n={best['n']}  mean_net={best['mean']:+.2f}bp  ann_sh={best['sh_ann']:+.2f}  mdd={best['mdd']*100:+.2f}%")
    print(f"  boot CI [{boot_lo:+.2f}, {boot_hi:+.2f}]  deflated_sh {dsh:+.2f}")
    print(f"  W1 {w1:+.2f}  W2 {w2:+.2f}  W3 {w3:+.2f}")
    print(f"  direction-lock: {'YES' if direction_lock else 'NO'}")
    print(f"  Phase 2 verdict: {n_pass}/13 -> {'PASS' if n_pass == 13 else 'REJECT'}")

    if best_dir == "long":
        print(f"\n  NOTE: best direction is LONG. User constraint was 'SHORT-only favored'.")
        print(f"  If PASS, candidate adds another LONG-direction leg to book (book is already net-long).")
    else:
        print(f"\n  NOTE: best direction is SHORT — matches user constraint.")
        print(f"  If PASS, candidate fills the SHORT-only slot the structural-flow pipeline targeted.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
