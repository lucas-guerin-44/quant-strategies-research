#!/usr/bin/env python3
"""
Quick validate/invalidate probe — USDCAD LONG (= SHORT CAD) at month-end 14-15 ET.

This is NOT a Phase 2 thesis lock — just a magnitude check to see if USDCAD's
USD-funding-squeeze signature is materially larger than EUR/GBP's (which were
sub-threshold for retail deploy at +0.85 bp/event net).

Decision rule (set before running):
  Decisive PASS (worth thesis lock + Phase 2): gross gap > 4 bp, t > 2.0
  Worth refining:                              gross gap 2.5-4 bp, t 1.5-2.0
  REJECT extension:                            gross gap < 2.5 bp OR same magnitude as EUR

If magnitude is comparable to EUR (~2.2 bp), the entire USD-funding-squeeze
family on retail FX is mechanically sub-threshold and the family tombstones
at the source level.
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

# Pull DATALAKE_URL from .env before importing fetch_ohlc (engine config reads env at import)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_ROOT, ".env"))

from data import fetch_ohlc  # noqa: E402
from structural_flow_audit import (  # noqa: E402
    gen_month_end_dates, compute_window_returns, compute_placebo_returns,
)

START_DATE = "2019-01-01"
END_DATE = "2026-05-26"
TZ_NAME = "US/Eastern"
WIN_START_H, WIN_START_M = 14, 0
WIN_END_H, WIN_END_M = 15, 0
COST_BPS_USDCAD = 2.0   # Eightcap typical
YEARS = range(2019, 2027)


def section(t: str) -> None:
    print(f"\n{'=' * 92}\n  {t}\n{'=' * 92}\n")


def label_regime(d: date) -> str:
    if d.year <= 2020:
        return "W1_2019_2020"
    if d.year <= 2022:
        return "W2_2021_2022"
    return "W3_2023_2026"


def main() -> int:
    section("USDCAD LONG (= SHORT CAD) at month-end 14-15 ET — Phase 0+ probe")
    print("  Fetching USDCAD M5 via authenticated datalake call...")
    import requests
    datalake_url = os.getenv("DATALAKE_URL", "").rstrip("/")
    api_key = os.getenv("DATALAKE_API_KEY", "")
    if not datalake_url or not api_key:
        print("  FATAL: DATALAKE_URL / DATALAKE_API_KEY missing from .env")
        return 1
    all_rows = []
    cursor = None
    while True:
        params = {
            "instrument": "USDCAD", "timeframe": "M5",
            "start": f"{START_DATE}T00:00:00", "end": f"{END_DATE}T23:59:59",
            "limit": 10000,
        }
        if cursor:
            params["cursor"] = cursor
        r = requests.get(f"{datalake_url}/query", params=params,
                         headers={"X-API-Key": api_key}, timeout=120)
        r.raise_for_status()
        payload = r.json()
        rows = payload.get("data", []) if isinstance(payload, dict) else payload
        all_rows.extend(rows)
        pag = payload.get("pagination", {}) if isinstance(payload, dict) else {}
        if not pag.get("has_more") or not pag.get("next_cursor"):
            break
        cursor = pag["next_cursor"]
    if not all_rows:
        print("  USDCAD bars: empty. Need to fetch via mt5_fetch first.")
        return 1
    bars = pd.DataFrame(all_rows)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars[["timestamp", "open", "high", "low", "close"]]
    bars = bars.set_index("timestamp").sort_index()
    bars = bars[~bars.index.duplicated(keep="first")]
    print(f"  USDCAD bars: {len(bars):,}  range {bars.index[0].date()} -> {bars.index[-1].date()}")

    event_dates = gen_month_end_dates(YEARS)
    print(f"  calendar events: {len(event_dates)} (last biz day of every month)")

    # ----------------------------------------------------------------------
    # Compute LONG returns on USDCAD = SHORT CAD direction
    # ----------------------------------------------------------------------
    section("Per-event USDCAD LONG returns (= SHORT CAD)")
    long_bps, kept = compute_window_returns(
        bars, event_dates, TZ_NAME,
        WIN_START_H, WIN_START_M, WIN_END_H, WIN_END_M,
    )
    n = len(kept)
    if n < 5:
        print(f"  INSUFFICIENT_N: only {n} events fired. Probably broker-data depth issue.")
        return 1
    if n < 20:
        print(f"  WARNING: only {n} events fired. Stats are direction-only at this n.")

    long_net = long_bps - COST_BPS_USDCAD

    gross_mean = float(long_bps.mean())
    gross_std = float(long_bps.std(ddof=1))
    gross_t = gross_mean / (gross_std / np.sqrt(n)) if gross_std > 0 else 0.0
    net_mean = float(long_net.mean())

    print(f"  n           : {n}")
    print(f"  USDCAD LONG gross mean: {gross_mean:+.2f} bps")
    print(f"  USDCAD LONG net mean (cost {COST_BPS_USDCAD}bp): {net_mean:+.2f} bps")
    print(f"  std         : {gross_std:.2f} bps")
    print(f"  t-stat      : {gross_t:+.2f}")
    print(f"  WR (gross+) : {(long_bps > 0).mean() * 100:.1f}%")

    # ----------------------------------------------------------------------
    # Regime breakdown
    # ----------------------------------------------------------------------
    section("Regime breakdown")
    labels = np.array([label_regime(d) for d in kept])
    print(f"  {'window':<16s} {'n':>3s} {'gross mean':>11s} {'net mean':>10s} {'t':>6s}")
    for w in ["W1_2019_2020", "W2_2021_2022", "W3_2023_2026"]:
        mask = labels == w
        if mask.sum() < 2:
            print(f"  {w:<16s} INSUFFICIENT_N (n={mask.sum()})")
            continue
        sub_g = long_bps[mask]
        sub_n = long_net[mask]
        m_g = float(sub_g.mean())
        m_n = float(sub_n.mean())
        t_s = m_g / (sub_g.std(ddof=1) / np.sqrt(mask.sum())) if sub_g.std(ddof=1) > 0 else 0.0
        print(f"  {w:<16s} {int(mask.sum()):>3d} {m_g:>+10.2f} {m_n:>+9.2f} {t_s:>+5.2f}")

    # ----------------------------------------------------------------------
    # Placebo: same window on non-event same-weekday days
    # ----------------------------------------------------------------------
    section("Placebo (non-event same-weekday days)")
    event_set = set(kept)
    weekdays = {d.weekday() for d in kept}
    placebo_long = compute_placebo_returns(
        bars, event_set, TZ_NAME, weekdays,
        WIN_START_H, WIN_START_M, WIN_END_H, WIN_END_M,
        max_samples=1500,
    )
    placebo_mean = float(placebo_long.mean()) if len(placebo_long) > 0 else float("nan")
    null_gap = gross_mean - placebo_mean
    print(f"  USDCAD placebo LONG gross mean: {placebo_mean:+.2f} bps (n={len(placebo_long)})")
    print(f"  null-gap event - placebo: {null_gap:+.2f} bps")

    # ----------------------------------------------------------------------
    # Comparison vs EUR/GBP (from the prior REJECT)
    # ----------------------------------------------------------------------
    section("Comparison vs EUR/GBP basket prior")
    print("  Prior REJECT (month_end_usd_short basket):")
    print(f"    EUR: gross -2.68 / null-gap -2.20 / t -1.77 / cost 1.5bp / net SHORT +1.18bp")
    print(f"    GBP: gross -1.97 / null-gap -2.34 / t -1.45 / cost 2.0bp / net SHORT -0.03bp")
    print(f"    Basket: net +0.85 bp/event -- REJECT 7/13 at retail cost")
    print()
    print("  USDCAD probe:")
    print(f"    Gross LONG: {gross_mean:+.2f} bps  (vs EUR -2.68 = LONG+2.68 on negate)")
    print(f"    Null-gap  : {null_gap:+.2f} bps  (vs EUR -2.20)")
    print(f"    Net LONG  : {net_mean:+.2f} bps  (vs EUR-SHORT net +1.18, GBP-SHORT net -0.03)")
    print(f"    t-stat    : {gross_t:+.2f}  (vs EUR -1.77, GBP -1.45)")

    # ----------------------------------------------------------------------
    # Verdict
    # ----------------------------------------------------------------------
    section("Probe verdict")
    abs_gross = abs(gross_mean)
    abs_t = abs(gross_t)
    if abs_gross >= 4.0 and abs_t >= 2.0:
        verdict = "DECISIVE PASS"
        action = "Worth full thesis lock + Phase 2 13-criterion test"
    elif abs_gross >= 2.5 and abs_t >= 1.5:
        verdict = "WORTH REFINING"
        action = "Magnitude in screen-WEAK band; thesis + Phase 2 worth attempting"
    elif abs_gross >= 2.0:
        verdict = "MARGINAL (EUR-like)"
        action = "Same magnitude as EUR — likely sub-threshold for retail at 3x cost-floor rule"
    else:
        verdict = "REJECT extension"
        action = "Mechanism does not extend at deploy-grade magnitude on USDCAD"

    print(f"  Gross magnitude: {abs_gross:.2f} bps")
    print(f"  |t-stat|       : {abs_t:.2f}")
    print(f"  -> {verdict}")
    print(f"  -> {action}")
    if abs_gross >= 2.5 and gross_mean < 0:
        print()
        print("  NOTE: gross is NEGATIVE meaning USDCAD goes DOWN at month-end 14-15 ET.")
        print("  Direction is opposite the hypothesis: month-end is LONG-CAD (= SHORT USD on USDCAD).")
        print("  Mechanism story (USD-funding squeeze) would predict UP on USDCAD. Re-think prior.")
    elif abs_gross >= 2.5 and gross_mean > 0:
        print()
        print("  USDCAD goes UP at month-end -- consistent with USD-funding squeeze mechanism.")
        print("  Direction confirms the LONG-USD basket prior.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
