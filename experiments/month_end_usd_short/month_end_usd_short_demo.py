#!/usr/bin/env python3
"""
Phase 2 simulator — Month-end USD-funding SHORT basket (EUR + GBP).

Thesis: experiments/month_end_usd_short/month_end_usd_short.md

Rules:
  Universe : EURUSD M5 + GBPUSD M5
  Trigger  : last business day of every month
  Window   : 14:00 -> 15:00 ET local (DST-aware via pytz)
  Direction: SHORT both legs (= LONG USD basket)
  Entry    : 14:00 ET open
  Exit     : 15:00 ET close
  Cost     : 1.5 bp RT EUR, 2.0 bp RT GBP; sweep 1x / 2x / 3x

Runs all 13 pre-committed kill criteria + bootstrap CI + cost-stress
+ walk-forward halves + direction null + placebo + deflated Sharpe
+ EUR/GBP co-direction check (W3 mechanism falsification).

Usage:
  venv/Scripts/python.exe experiments/month_end_usd_short/month_end_usd_short_demo.py
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
WIN_START_H, WIN_START_M = 14, 0
WIN_END_H, WIN_END_M = 15, 0

# Per-leg cost (bps RT). Eightcap typicals.
COST_BPS_EUR = 1.5
COST_BPS_GBP = 2.0
COST_STRESS_MULT = 2.0  # criterion #10

EVENTS_PER_YEAR = 12

YEARS = range(2019, 2027)
N_SCREEN_CELLS = 17  # for deflated-Sharpe selection-bias adjustment

# Pre-committed kill criteria thresholds (FROZEN — set in thesis BEFORE running)
KC1_FULL_MEAN_NET = 1.5    # bps/event (basket)
KC2_W3_MEAN_NET = 1.0
KC4_ANN_SH = 0.30
KC5_WR = 0.53
KC6_MDD = 0.03             # 3% on event-equity curve
KC7_BOOT_LOWER_GT = 0.0
KC8_DIR_GAP = 0.30
KC9_PLACEBO_MAG = 1.0      # |placebo SHORT mean| < 1 bp
KC10_COST_STRESS_NET = 0.0
KC11_DEFLATED_SH = 0.20
KC12_WF_BOTH_POS = True
KC13_LEG_W3_BOTH_POS = True  # EUR and GBP both net-positive in W3


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


def per_event_metrics(rets: np.ndarray) -> dict:
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
# Data
# -----------------------------------------------------------------------------

def load_m5(symbol: str) -> pd.DataFrame:
    df = fetch_ohlc(symbol, "M5", START_DATE, END_DATE)
    df = df[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> int:
    section("Loading EURUSD + GBPUSD M5")
    eur = load_m5("EURUSD")
    gbp = load_m5("GBPUSD")
    print(f"  EUR bars: {len(eur):,}  range {eur.index[0].date()} -> {eur.index[-1].date()}")
    print(f"  GBP bars: {len(gbp):,}  range {gbp.index[0].date()} -> {gbp.index[-1].date()}")

    event_dates = gen_month_end_dates(YEARS)
    print(f"  calendar events: {len(event_dates)} (last biz day of every month)")

    # ----------------------------------------------------------------------
    # Per-leg LONG returns -> SHORT (negate) -> cost-net
    # ----------------------------------------------------------------------
    section("Per-leg LONG returns (14:00-15:00 ET) -> SHORT direction")
    eur_long_bps, eur_kept = compute_window_returns(
        eur, event_dates, TZ_NAME,
        WIN_START_H, WIN_START_M, WIN_END_H, WIN_END_M,
    )
    gbp_long_bps, gbp_kept = compute_window_returns(
        gbp, event_dates, TZ_NAME,
        WIN_START_H, WIN_START_M, WIN_END_H, WIN_END_M,
    )
    print(f"  EUR kept: {len(eur_kept)} events  (range {eur_kept[0]} -> {eur_kept[-1]})")
    print(f"  GBP kept: {len(gbp_kept)} events  (range {gbp_kept[0]} -> {gbp_kept[-1]})")

    eur_short_gross = -eur_long_bps
    gbp_short_gross = -gbp_long_bps
    eur_short_net = eur_short_gross - COST_BPS_EUR
    gbp_short_net = gbp_short_gross - COST_BPS_GBP

    print(f"\n  EUR SHORT net mean: {eur_short_net.mean():+.2f} bps  std {eur_short_net.std(ddof=1):.2f}")
    print(f"  GBP SHORT net mean: {gbp_short_net.mean():+.2f} bps  std {gbp_short_net.std(ddof=1):.2f}")

    # ----------------------------------------------------------------------
    # Basket construction: average of available legs per event
    # ----------------------------------------------------------------------
    section("Basket: average of available legs per event")
    eur_dict = dict(zip(eur_kept, eur_short_net))
    gbp_dict = dict(zip(gbp_kept, gbp_short_net))
    all_dates = sorted(set(eur_kept) | set(gbp_kept))

    basket_rows = []
    for d in all_dates:
        legs = []
        if d in eur_dict:
            legs.append(eur_dict[d])
        if d in gbp_dict:
            legs.append(gbp_dict[d])
        if not legs:
            continue
        basket_rows.append({"date": d, "ret_bps": float(np.mean(legs)),
                            "n_legs": len(legs),
                            "eur": eur_dict.get(d, float("nan")),
                            "gbp": gbp_dict.get(d, float("nan"))})
    bdf = pd.DataFrame(basket_rows)
    print(f"  basket events: {len(bdf)}")
    print(f"  events with both legs: {(bdf['n_legs'] == 2).sum()}")
    print(f"  events with EUR only:  {(bdf['n_legs'] == 1).sum()}  (pre-2022-11 era)")

    basket_net = bdf["ret_bps"].to_numpy(dtype=np.float64)

    # ----------------------------------------------------------------------
    # Headline metrics
    # ----------------------------------------------------------------------
    section("Headline basket metrics (SHORT, cost-net)")
    bm = per_event_metrics(basket_net)
    sh_ann = annualized_sharpe_event(basket_net)
    rets_frac = basket_net / 1e4
    mdd = equity_mdd(rets_frac)
    gw = float(basket_net[basket_net > 0].sum())
    gl = float(-basket_net[basket_net <= 0].sum())
    pf = gw / gl if gl > 0 else float("inf")
    print(f"  n        : {bm['n']}")
    print(f"  mean net : {bm['mean']:+.2f} bps/event")
    print(f"  std      : {bm['std']:.2f} bps")
    print(f"  trade Sh : {bm['sh_trade']:+.3f}")
    print(f"  ann Sh   : {sh_ann:+.3f}  (events_per_year={EVENTS_PER_YEAR})")
    print(f"  WR       : {bm['wr'] * 100:.1f}%  PF: {pf:.2f}")
    print(f"  MDD      : {mdd * 100:+.2f}%")

    # ----------------------------------------------------------------------
    # Regime breakdown
    # ----------------------------------------------------------------------
    section("Regime breakdown (basket, cost-net)")
    bdf["regime"] = bdf["date"].map(label_regime)
    regime_res = {}
    print(f"  {'window':<16s} {'n':>3s} {'mean':>10s} {'t':>6s} {'sh_ann':>7s} {'wr':>6s}  n_legs_mix")
    for w in ["W1_2019_2020", "W2_2021_2022", "W3_2023_2026"]:
        sub_df = bdf[bdf["regime"] == w]
        if len(sub_df) < 2:
            print(f"  {w:<16s} INSUFFICIENT_N (n={len(sub_df)})")
            regime_res[w] = None
            continue
        sub = sub_df["ret_bps"].to_numpy()
        sub_m = per_event_metrics(sub)
        sub_t = sub_m["mean"] / (sub_m["std"] / np.sqrt(len(sub))) if sub_m["std"] > 0 else 0.0
        sub_sh_ann = sub_m["mean"] / sub_m["std"] * np.sqrt(EVENTS_PER_YEAR) if sub_m["std"] > 0 else 0.0
        legs_mix = f"{int((sub_df['n_legs'] == 2).sum())}both / {int((sub_df['n_legs'] == 1).sum())}EUR-only"
        regime_res[w] = {"mean": sub_m["mean"], "t": sub_t, "sh_ann": sub_sh_ann,
                         "n": int(len(sub_df)), "wr": sub_m["wr"]}
        print(f"  {w:<16s} {int(len(sub_df)):>3d} {sub_m['mean']:>+9.2f} "
              f"{sub_t:>+5.2f} {sub_sh_ann:>+6.2f} {sub_m['wr']*100:>5.1f}%  {legs_mix}")

    # ----------------------------------------------------------------------
    # Per-leg W3 metrics for criterion #13 (mechanism falsification)
    # ----------------------------------------------------------------------
    section("Per-leg W3 holdout breakdown (criterion #13 — mechanism falsification)")
    eur_w3_mask = np.array([label_regime(d) == "W3_2023_2026" for d in eur_kept])
    gbp_w3_mask = np.array([label_regime(d) == "W3_2023_2026" for d in gbp_kept])
    eur_w3_net = eur_short_net[eur_w3_mask]
    gbp_w3_net = gbp_short_net[gbp_w3_mask]
    eur_w3_mean = float(eur_w3_net.mean()) if len(eur_w3_net) >= 2 else float("nan")
    gbp_w3_mean = float(gbp_w3_net.mean()) if len(gbp_w3_net) >= 2 else float("nan")
    print(f"  EUR W3 SHORT net mean: {eur_w3_mean:+.2f} bps  (n={len(eur_w3_net)})")
    print(f"  GBP W3 SHORT net mean: {gbp_w3_mean:+.2f} bps  (n={len(gbp_w3_net)})")
    legs_codir = (eur_w3_mean > 0) and (gbp_w3_mean > 0)
    print(f"  Both legs net-positive in W3? {'YES (PASS)' if legs_codir else 'NO (FAIL — venue-specificity tombstone)'}")

    # ----------------------------------------------------------------------
    # Bootstrap CI
    # ----------------------------------------------------------------------
    section("Bootstrap 95% CI on full-sample basket mean")
    boot_lo, boot_pt, boot_hi = bootstrap_mean_ci(basket_net)
    print(f"  point: {boot_pt:+.2f} bps    95% CI [{boot_lo:+.2f}, {boot_hi:+.2f}] bps")

    # ----------------------------------------------------------------------
    # Direction null
    # ----------------------------------------------------------------------
    section("Direction null check (zero-cost LONG vs SHORT, basket)")
    # Combine zero-cost legs to a basket
    eur_long_gross_dict = dict(zip(eur_kept, eur_long_bps))
    gbp_long_gross_dict = dict(zip(gbp_kept, gbp_long_bps))
    basket_long_gross = []
    for d in all_dates:
        legs = []
        if d in eur_long_gross_dict:
            legs.append(eur_long_gross_dict[d])
        if d in gbp_long_gross_dict:
            legs.append(gbp_long_gross_dict[d])
        if legs:
            basket_long_gross.append(np.mean(legs))
    basket_long_gross = np.asarray(basket_long_gross)
    basket_short_gross = -basket_long_gross
    long_sh = basket_long_gross.mean() / basket_long_gross.std(ddof=1) if basket_long_gross.std(ddof=1) > 0 else 0.0
    short_sh = -long_sh
    dir_gap = short_sh - long_sh
    print(f"  LONG  zero-cost trade-Sh : {long_sh:+.3f}")
    print(f"  SHORT zero-cost trade-Sh : {short_sh:+.3f}")
    print(f"  direction-gap            : {dir_gap:+.3f}")

    # ----------------------------------------------------------------------
    # Placebo — non-event same-weekday days, basket SHORT
    # ----------------------------------------------------------------------
    section("Placebo non-event same-weekday days (basket SHORT)")
    event_set = set(all_dates)
    weekdays = {d.weekday() for d in all_dates}
    eur_plc_long = compute_placebo_returns(
        eur, event_set, TZ_NAME, weekdays,
        WIN_START_H, WIN_START_M, WIN_END_H, WIN_END_M,
        max_samples=1500,
    )
    gbp_plc_long = compute_placebo_returns(
        gbp, event_set, TZ_NAME, weekdays,
        WIN_START_H, WIN_START_M, WIN_END_H, WIN_END_M,
        max_samples=1500,
    )
    eur_plc_short = -eur_plc_long
    gbp_plc_short = -gbp_plc_long
    plc_mean = (eur_plc_short.mean() + gbp_plc_short.mean()) / 2.0 \
               if len(eur_plc_short) > 0 and len(gbp_plc_short) > 0 \
               else (eur_plc_short.mean() if len(eur_plc_short) else gbp_plc_short.mean())
    print(f"  EUR placebo SHORT mean (gross): {eur_plc_short.mean():+.2f} bps  (n={len(eur_plc_short)})")
    print(f"  GBP placebo SHORT mean (gross): {gbp_plc_short.mean():+.2f} bps  (n={len(gbp_plc_short)})")
    print(f"  basket placebo SHORT mean     : {plc_mean:+.2f} bps")

    # ----------------------------------------------------------------------
    # Cost sweep
    # ----------------------------------------------------------------------
    section("Cost-sensitivity sweep (basket; per-leg costs scaled)")
    print(f"  {'mult':<6s} {'EUR bp':<7s} {'GBP bp':<7s} {'basket mean':>13s} {'ann Sh':>8s}")
    cost_stress_net = None
    for mult in (0.5, 1.0, 1.5, 2.0, 3.0):
        eur_n = -eur_long_bps - COST_BPS_EUR * mult
        gbp_n = -gbp_long_bps - COST_BPS_GBP * mult
        eur_d2 = dict(zip(eur_kept, eur_n))
        gbp_d2 = dict(zip(gbp_kept, gbp_n))
        b_vals = []
        for d in all_dates:
            legs = []
            if d in eur_d2:
                legs.append(eur_d2[d])
            if d in gbp_d2:
                legs.append(gbp_d2[d])
            if legs:
                b_vals.append(np.mean(legs))
        b_arr = np.asarray(b_vals)
        m = float(b_arr.mean())
        s = float(b_arr.std(ddof=1))
        sh = m / s * np.sqrt(EVENTS_PER_YEAR) if s > 0 else 0.0
        marker = ("  (default)" if mult == 1.0 else
                  "  (stress 2x)" if abs(mult - COST_STRESS_MULT) < 1e-6 else "")
        print(f"  {mult:<6.1f} {COST_BPS_EUR*mult:<7.2f} {COST_BPS_GBP*mult:<7.2f} "
              f"{m:>+12.2f} {sh:>+7.2f}{marker}")
        if abs(mult - COST_STRESS_MULT) < 1e-6:
            cost_stress_net = m

    # ----------------------------------------------------------------------
    # Walk-forward halves
    # ----------------------------------------------------------------------
    section("Walk-forward halves (chronological split)")
    n = len(basket_net)
    midpoint = n // 2
    h1 = basket_net[:midpoint]
    h2 = basket_net[midpoint:]
    h1_mean = float(h1.mean()) if len(h1) >= 2 else float("nan")
    h2_mean = float(h2.mean()) if len(h2) >= 2 else float("nan")
    h1_sh = float(h1.mean() / h1.std(ddof=1) * np.sqrt(EVENTS_PER_YEAR)) if len(h1) >= 2 and h1.std(ddof=1) > 0 else 0.0
    h2_sh = float(h2.mean() / h2.std(ddof=1) * np.sqrt(EVENTS_PER_YEAR)) if len(h2) >= 2 and h2.std(ddof=1) > 0 else 0.0
    print(f"  H1 ({len(h1)} events, {bdf['date'].iloc[0]} -> {bdf['date'].iloc[midpoint - 1]}): "
          f"mean_net {h1_mean:+.2f} bps  sh_ann {h1_sh:+.2f}")
    print(f"  H2 ({len(h2)} events, {bdf['date'].iloc[midpoint]} -> {bdf['date'].iloc[-1]}): "
          f"mean_net {h2_mean:+.2f} bps  sh_ann {h2_sh:+.2f}")

    # ----------------------------------------------------------------------
    # Deflated Sharpe
    # ----------------------------------------------------------------------
    section(f"Deflated Sharpe (n_trials={N_SCREEN_CELLS} screen cells)")
    dsh = deflated_sharpe(sh_ann, basket_net, n_trials=N_SCREEN_CELLS)
    print(f"  observed ann Sh : {sh_ann:+.3f}")
    print(f"  deflated ann Sh : {dsh:+.3f}")

    # ----------------------------------------------------------------------
    # Kill criteria
    # ----------------------------------------------------------------------
    section("Phase 2 pre-committed kill criteria (13)")
    w1 = regime_res.get("W1_2019_2020")
    w2 = regime_res.get("W2_2021_2022")
    w3 = regime_res.get("W3_2023_2026")
    all_regs_pos = all(r is not None and r["mean"] > 0 for r in (w1, w2, w3))

    criteria = [
        ("1. Full mean net >= +1.5 bp/event", bm["mean"] >= KC1_FULL_MEAN_NET,
            f"{bm['mean']:+.2f} bp"),
        ("2. W3 mean net >= +1.0 bp/event",
            w3 is not None and w3["mean"] >= KC2_W3_MEAN_NET,
            f"W3={w3['mean']:+.2f} bp" if w3 else "n/a"),
        ("3. All 3 regimes net positive", all_regs_pos,
            f"W1={w1['mean']:+.2f} W2={w2['mean']:+.2f} W3={w3['mean']:+.2f}"
                if all(r is not None for r in (w1, w2, w3)) else "missing"),
        ("4. Annualized Sharpe >= +0.30", sh_ann >= KC4_ANN_SH,
            f"sh_ann={sh_ann:+.2f}"),
        ("5. WR >= 53%", bm["wr"] >= KC5_WR,
            f"WR={bm['wr']*100:.1f}%"),
        ("6. MDD <= -3%", abs(mdd) <= KC6_MDD,
            f"mdd={mdd*100:+.2f}%"),
        ("7. Bootstrap 95% CI lower > 0", boot_lo > KC7_BOOT_LOWER_GT,
            f"[{boot_lo:+.2f}, {boot_hi:+.2f}]"),
        ("8. Direction-gap > +0.30", dir_gap > KC8_DIR_GAP,
            f"{dir_gap:+.2f}"),
        ("9. Placebo basket |mean| < 1 bp", abs(plc_mean) < KC9_PLACEBO_MAG,
            f"{plc_mean:+.2f} bp"),
        ("10. Cost-stress 2x mean net > 0",
            cost_stress_net is not None and cost_stress_net > KC10_COST_STRESS_NET,
            f"{cost_stress_net:+.2f} bp" if cost_stress_net else "n/a"),
        ("11. Deflated Sharpe >= +0.20", dsh >= KC11_DEFLATED_SH,
            f"{dsh:+.2f}"),
        ("12. WF halves both net > 0",
            (h1_mean > 0) and (h2_mean > 0),
            f"H1={h1_mean:+.2f} H2={h2_mean:+.2f}"),
        ("13. EUR + GBP both net+ in W3", legs_codir,
            f"EUR={eur_w3_mean:+.2f} GBP={gbp_w3_mean:+.2f}"),
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
    print(f"  month_end_usd_short: SHORT EUR + SHORT GBP basket, 14-15 ET, last biz day of every month")
    print(f"  n={bm['n']}  mean_net={bm['mean']:+.2f}bp  ann_sh={sh_ann:+.2f}  mdd={mdd*100:+.2f}%")
    print(f"  boot CI [{boot_lo:+.2f}, {boot_hi:+.2f}]  deflated_sh {dsh:+.2f}")
    print(f"  W1 {w1['mean'] if w1 else 'n/a':+.2f}  W2 {w2['mean'] if w2 else 'n/a':+.2f}  W3 {w3['mean'] if w3 else 'n/a':+.2f}")
    print(f"  EUR W3 {eur_w3_mean:+.2f}  GBP W3 {gbp_w3_mean:+.2f}  co-direction: {'YES' if legs_codir else 'NO'}")
    print(f"  Phase 2 verdict: {n_pass}/13 -> {'PASS' if n_pass == 13 else 'REJECT'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
