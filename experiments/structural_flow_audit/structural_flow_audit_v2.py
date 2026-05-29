#!/usr/bin/env python3
"""
Structural-flow calendar audit — v2 (2026-05-28).

Re-run of the Phase-0 structural-flow screen (lesson #-20: quarterly re-run with
widened universe) with two changes vs v1 (structural_flow_audit.py, kept intact
as the historical record):

  1. COST_FLOOR_BPS corrected. v1 had a ~10x scaling error (XAU 7bp vs ~0.7-2bp
     realised; indices 4-5bp vs ~0.5-1.5bp for the 1pt-RT default). The bug made
     v1 STRICTER than intended (no false positives), so v2 may PROMOTE cells that
     v1 buried. Corrected floors below are realistic Eightcap Raw-account all-in
     RT (spread + commission), consistent with lesson #32 (XAU ~2bp all-in) and
     the repo's "1 point RT per index CFD" default.

  2. Widened universe. v1 was US-venue-centric. v2 adds:
       - FRA40 / UK100 to equity grids (Euronext/LSE).
       - EU triple-witch close + EU quarter-end last-2h on GER40/FRA40/UK100
         (Eurex & Euronext run their own 3rd-Friday expiry auctions; the QEXS
         finding was XAU/US-only, EU venues never screened for quarter-end).
       - MSCI semi-annual rebalance (last biz day May & Nov) across index venues
         — global index-tracker forced flow concentrated in the closing auction.

Reuses every helper from v1 by import (DRY); only config + grid definitions differ.

Usage:
  venv/Scripts/python.exe experiments/structural_flow_audit/structural_flow_audit_v2.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import structural_flow_audit as sfa  # noqa: E402
from structural_flow_audit import (  # noqa: E402
    section, load_m5, evaluate_grid, last_business_day,
    gen_jpm_collar_dates, gen_month_end_dates, gen_vix_soq_dates,
    gen_opex_day_after_dates, gen_triple_witch_dates,
    YEARS,
)

# -----------------------------------------------------------------------------
# Corrected cost floors (Eightcap Raw, all-in RT bps). Patched onto the v1 module
# so evaluate_grid (which reads sfa.COST_FLOOR_BPS as a module global) uses them.
# -----------------------------------------------------------------------------
CORRECTED_COST_FLOOR_BPS = {
    # indices: ~1pt RT default, expressed in bps at typical price levels, with a
    # small markup for realistic Raw spread+commission.
    "SPX500": 1.5, "NDX100": 0.8, "GER40": 0.8, "FRA40": 1.5, "UK100": 1.5,
    # FX majors: Raw ~0.1pip spread + ~0.6bp commission.
    "EURUSD": 0.8, "USDJPY": 1.0, "GBPUSD": 1.2,
    # XAU all-in per lesson #32.
    "XAUUSD": 2.0,
}
sfa.COST_FLOOR_BPS = CORRECTED_COST_FLOOR_BPS


# -----------------------------------------------------------------------------
# New calendar generator
# -----------------------------------------------------------------------------

def gen_msci_rebal_dates(years: range) -> list[date]:
    """MSCI semi-annual index review effective at close: last biz day of May & Nov.

    (MSCI also runs quarterly Feb/Aug reviews but the May/Nov semi-annuals are the
    large ones with the biggest tracker-rebalance flow.)
    """
    out = []
    for y in years:
        for m in (5, 11):
            out.append(last_business_day(y, m))
    return out


# -----------------------------------------------------------------------------
# Flexible grid format: each entry is
#   (event_label, gen_fn, [(instrument, tz_name, (sh, sm, eh, em)), ...])
# so EU instruments can carry their own local close windows in the same grid.
# -----------------------------------------------------------------------------

ET = "US/Eastern"
BERLIN = "Europe/Berlin"
LONDON = "Europe/London"


def build_grids_v2():
    # US equity close last hour 15-16 ET; EU close last hour 16:30-17:30 CET
    # (Xetra/Euronext continuous close ~17:30) and 15:30-16:30 London (LSE 16:30 close).
    return [
        # ---- v1 cells, re-scored with corrected costs ----
        ("jpm_collar_close", gen_jpm_collar_dates, [
            ("SPX500", ET, (15, 0, 16, 0)), ("NDX100", ET, (15, 0, 16, 0))]),
        ("month_end_wmr_fix", gen_month_end_dates, [
            ("EURUSD", LONDON, (15, 45, 16, 15)),
            ("USDJPY", LONDON, (15, 45, 16, 15)),
            ("GBPUSD", LONDON, (15, 45, 16, 15))]),
        ("vix_soq_settle", gen_vix_soq_dates, [
            ("SPX500", ET, (8, 30, 9, 30))]),
        ("opex_day_after_am", gen_opex_day_after_dates, [
            ("SPX500", ET, (9, 30, 12, 0)), ("NDX100", ET, (9, 30, 12, 0))]),
        ("triple_witch_close_us", gen_triple_witch_dates, [
            ("SPX500", ET, (15, 0, 16, 0)), ("NDX100", ET, (15, 0, 16, 0))]),
        ("month_end_usd_funding", gen_month_end_dates, [
            ("EURUSD", ET, (14, 0, 15, 0)), ("USDJPY", ET, (14, 0, 15, 0)),
            ("GBPUSD", ET, (14, 0, 15, 0))]),
        ("quarter_end_last_2h_us", gen_jpm_collar_dates, [
            ("SPX500", ET, (14, 0, 16, 0)), ("NDX100", ET, (14, 0, 16, 0)),
            ("XAUUSD", ET, (14, 0, 16, 0)), ("EURUSD", ET, (14, 0, 16, 0))]),

        # ---- v2 widened cells ----
        ("triple_witch_close_eu", gen_triple_witch_dates, [
            ("GER40", BERLIN, (16, 30, 17, 30)),
            ("FRA40", BERLIN, (16, 30, 17, 30)),
            ("UK100", LONDON, (15, 30, 16, 30))]),
        ("quarter_end_last_2h_eu", gen_jpm_collar_dates, [
            ("GER40", BERLIN, (15, 30, 17, 30)),
            ("FRA40", BERLIN, (15, 30, 17, 30)),
            ("UK100", LONDON, (14, 30, 16, 30))]),
        ("msci_semiannual_rebal", gen_msci_rebal_dates, [
            ("SPX500", ET, (15, 0, 16, 0)), ("NDX100", ET, (15, 0, 16, 0)),
            ("GER40", BERLIN, (16, 30, 17, 30)),
            ("FRA40", BERLIN, (16, 30, 17, 30)),
            ("UK100", LONDON, (15, 30, 16, 30))]),
    ]


def main() -> int:
    section("Structural-flow calendar audit v2 (corrected costs + widened universe)")
    print(f"  Period   : {sfa.START_DATE} -> {sfa.END_DATE}")
    print(f"  Cost flrs: {CORRECTED_COST_FLOOR_BPS}")

    grids = build_grids_v2()
    all_instruments = sorted({inst for _, _, cells in grids for inst, _, _ in cells})

    section("Loading instruments")
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
    for event_label, gen_fn, cells in grids:
        event_dates = gen_fn(YEARS)
        print(f"\n  [{event_label}] n_events_cal={len(event_dates)}")
        for inst, tz_name, win in cells:
            if inst not in bars_map:
                print(f"    {inst:<8s} SKIPPED (no data)")
                continue
            row = evaluate_grid(
                event_label, inst, bars_map[inst], event_dates, tz_name,
                win[0], win[1], win[2], win[3])
            if row is None:
                continue
            row["tz"] = tz_name
            row["window"] = f"{win[0]:02d}:{win[1]:02d}-{win[2]:02d}:{win[3]:02d}"
            print(f"    {inst:<8s} {tz_name:<13s} {row['window']}  n_ev={row['n_events']:>3d}  "
                  f"ev={row['event_mean_bps']:>+6.2f}  pl={row['placebo_mean_bps']:>+6.2f}  "
                  f"gap={row['null_gap_bps']:>+7.2f}bp  t={row['t_stat']:>+5.2f}  "
                  f"room={row['cost_headroom_bps']:>+6.2f}bp  [{row['tier']}]")
            rows.append(row)

    if not rows:
        print("\n  No rows. Check data loading.")
        return 1

    df = pd.DataFrame(rows)
    order = {"STRONG": 0, "MEDIUM": 1, "WEAK": 2, "REJECT": 3, "INSUFFICIENT_N": 4}
    df_sorted = df.sort_values(
        ["tier", "score"],
        key=lambda c: c.map(order) if c.name == "tier" else -c,
        ascending=[True, True], na_position="last")

    section("Ranked output (all cells)")
    print(df_sorted[["event", "instrument", "window", "n_events", "event_mean_bps",
                     "null_gap_bps", "t_stat", "cost_headroom_bps", "tier"]]
          .to_string(index=False, float_format=lambda x: f"{x:+.2f}"))

    section("Survivors (STRONG + MEDIUM)")
    surv = df_sorted[df_sorted["tier"].isin(["STRONG", "MEDIUM"])]
    if len(surv) == 0:
        print("  No STRONG or MEDIUM cells.")
    else:
        print(surv[["event", "instrument", "window", "n_events", "null_gap_bps",
                    "t_stat", "cost_headroom_bps", "tier"]]
              .to_string(index=False, float_format=lambda x: f"{x:+.2f}"))

    section("Summary")
    tc = df_sorted["tier"].value_counts()
    for tier in ["STRONG", "MEDIUM", "WEAK", "REJECT", "INSUFFICIENT_N"]:
        print(f"  {tier:<16s}: {int(tc.get(tier, 0))}")

    out_csv = os.path.join(_HERE, "structural_flow_audit_v2_results.csv")
    df_sorted.to_csv(out_csv, index=False)
    print(f"\n  Results -> {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
