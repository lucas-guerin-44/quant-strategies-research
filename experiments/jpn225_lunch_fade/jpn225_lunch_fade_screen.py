#!/usr/bin/env python3
"""
JPN225 lunch-fade — Phase 0/1 screen (lunch_fade transplant to the TSE cash lunch).

Why this is the mechanism-justified transplant (not a generic idea):
  Deployed `lunch_fade` works on NDX because during the US lunch the cash-vs-futures
  basis-arb HFT inventory mean-reverts (lessons #8/#27). Every failed lunch-fade
  transplant (fdax / fx / single_stock) died because the venue has NO cash lunch halt
  → no liquidity vacuum. The Tokyo Stock Exchange is the ONE major index with a formal
  cash lunch halt (11:30-12:30 JST = 02:30-03:30 UTC) while Nikkei futures (which the
  JPN225 CFD tracks) trade through it → the exact cash/futures-basis-vacuum setup.

TSE cash day (JST=UTC+9, no DST):
  morning  09:00-11:30 JST = 00:00-02:30 UTC   (150 min)
  LUNCH    11:30-12:30 JST = 02:30-03:30 UTC    (cash halted; CFD continuous)
  afternoon 12:30-15:00 JST = 03:30-06:00 UTC   (150 min)

Reuses simulate_lunch_fade by monkey-patching lunch_fade_demo's session globals.
Per lesson #72 (BINDING): runs the in-session-vs-off-session C1 control BEFORE trusting
the result — if lunch-window fade minus off-session fade < +0.40 zero-cost Sharpe, the
edge is not lunch-specific → REJECT before any Phase 2.
"""
from __future__ import annotations

import os
import sys
from datetime import time as dtime

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))
sys.path.insert(0, os.path.join(_ROOT, "experiments", "_live", "lunch_fade"))

import lunch_fade_demo as lf  # noqa: E402


def section(t): print(f"\n{'='*84}\n  {t}\n{'='*84}\n")


def configure(open_h, close_h):
    """Patch lunch_fade_demo session globals for an arbitrary UTC window."""
    lf.SYMBOL = "JPN225"
    lf.SESSION_TZ = "UTC"
    lf.RTH_OPEN = dtime(open_h, 0)
    lf.RTH_CLOSE = dtime(close_h, 0)
    lf.RTH_MINUTES = (close_h - open_h) * 60
    lf.BARS_PER_DAY = lf.RTH_MINUTES // 5
    lf.BARS_PER_YEAR = lf.BARS_PER_DAY * lf.DAYS_PER_YEAR
    lf.COST_POINTS_ROUND_TRIP = 5.0   # JPN225 ~39000 → 5pt RT ≈ 1.3 bp (Eightcap)


def sh(r):
    return lf.annualized_sharpe(r.to_numpy())


def main():
    section("JPN225 LUNCH-FADE — Phase 0/1 (lunch_fade transplant to TSE cash lunch)")

    # ---- Phase 0b C1 control FIRST (lesson #72): lunch window vs off-session ----
    # Cash day 00:00-06:00 UTC: morning 0-150min, fade through lunch, exit afternoon.
    configure(0, 6)
    bars_cash = lf.load_m5("JPN225")
    print(f"  TSE-cash window 00:00-06:00 UTC: {len(bars_cash):,} bars, "
          f"{bars_cash.index[0].date()} -> {bars_cash.index[-1].date()}, days={len(set(bars_cash.index.date))}")
    # zero-cost fade, morning=150 (02:30 UTC cash-morning close), exit 270 (04:30 UTC, into afternoon)
    r_lunch, t_lunch = lf.simulate_lunch_fade(bars_cash, morning_end_min=150, afternoon_end_min=270, cost_points=0.0)
    sh_lunch_zc = sh(r_lunch)

    # off-session control: 06:00-12:00 UTC (Tokyo-afternoon→Europe; NO cash lunch halt)
    configure(6, 12)
    bars_off = lf.load_m5("JPN225")
    r_off, t_off = lf.simulate_lunch_fade(bars_off, morning_end_min=150, afternoon_end_min=270, cost_points=0.0)
    sh_off_zc = sh(r_off)

    section("Phase 0b C1 control (zero-cost) — BINDING (lesson #72)")
    print(f"  lunch-window fade (00-06 UTC, fade through 02:30-03:30 cash halt): zero-cost Sh {sh_lunch_zc:+.2f}  trades {len(t_lunch)}")
    print(f"  off-session  fade (06-12 UTC, no cash lunch):                      zero-cost Sh {sh_off_zc:+.2f}  trades {len(t_off)}")
    delta = sh_lunch_zc - sh_off_zc
    print(f"  C1 delta (lunch - off-session): {delta:+.2f}   {'PASS (>=+0.40)' if delta >= 0.40 else 'FAIL (<+0.40) -> mechanism not lunch-specific'}")
    if delta < 0.40:
        print("\n  REJECT before Phase 2 — the fade is not specific to the cash-lunch window.")
        print("  (lesson #72: in-session-vs-off-session control is the cheap pre-Phase-2 falsifier.)")
        # still print the lunch-window detail for the record
    # ---- full lunch-window detail (cost-applied) ----
    configure(0, 6)
    section("Lunch-window fade — baseline (morning=150, exit=270, cost=5pt≈1.3bp)")
    r, t = lf.simulate_lunch_fade(bars_cash, morning_end_min=150, afternoon_end_min=270)
    lf.report_run("JPN225 lunch-fade", r, t)

    section("Phase 2 kill-criteria")
    lf.kill_criteria_check("JPN225 lunch-fade", r, t)

    section("Regime breakdown")
    lf.regime_breakdown(r, t)

    section("Null-check — continuation direction")
    r_c, t_c = lf.simulate_lunch_fade(bars_cash, morning_end_min=150, afternoon_end_min=270, direction="cont")
    gap = sh(r) - sh(r_c)
    print(f"  fade Sh {sh(r):+.2f}  cont Sh {sh(r_c):+.2f}  dir-gap {gap:+.2f}  "
          f"{'PASS' if gap >= 0.30 else ('INVERTED' if gap <= -0.30 else 'FAIL <0.30')}")

    section("Exit-window sweep (afternoon_end_min)")
    for ae in (210, 240, 270, 300, 330, 360):  # 03:30 reopen, +30/+60/... into afternoon
        rv, tv = lf.simulate_lunch_fade(bars_cash, morning_end_min=150, afternoon_end_min=ae)
        print(f"  exit={ae}min ({ae//60:02d}:{ae%60:02d} UTC)  Sh {sh(rv):+.2f}  trades {len(tv)}")

    section("Threshold sweep (MIN_MOVE_ATR)")
    for thr in (0.0, 0.25, 0.5, 0.75, 1.0):
        rv, tv = lf.simulate_lunch_fade(bars_cash, morning_end_min=150, afternoon_end_min=270, min_move_atr=thr)
        print(f"  thr={thr:.2f}  Sh {sh(rv):+.2f}  trades {len(tv)}")

    section("READ")
    print(f"  C1 control delta {delta:+.2f} (binding); baseline fade Sh {sh(r):+.2f}; dir-gap {gap:+.2f}")
    verdict = "INVESTIGATE" if (delta >= 0.40 and sh(r) > 0.30 and gap >= 0.30) else "REJECT"
    print(f"  Phase-0/1 verdict: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
