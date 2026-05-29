#!/usr/bin/env python3
"""
Phase 0/1 screen — Leveraged-ETF end-of-day rebalance SHORT (continuation into the close).

Mechanism (Cheng & Madhavan 2009): leveraged & inverse ETFs must rebalance daily to keep
constant leverage; the rebalance is MECHANICALLY same-direction as the day's move and executed
near the close (~last 30-60 min). Aggregate demand is convex in the day's return. On big DOWN
days the rebalance amplifies selling into the close => last-30-min CONTINUATION down => SHORT.
The book wants the SHORT leg specifically: it fires on risk-off days => hedge convexity for a
long-heavy book.

This is a SCREEN, not a thesis lock. It answers: conditioned on a large intraday DOWN move
(open->15:30 ET), does the 15:30->16:00 ET window continue down (SHORT-profitable) above the
unconditional baseline, survive 1.5 bp cost, and survive the W3 (2023-26) holdout?

Decision gate to promote to a Phase 2 thesis lock (set BEFORE running):
  - best down-day threshold: SHORT close-window net mean >= +3 bp AND
  - dir-gap (continuation - fade zero-cost Sh) > +0.40 AND
  - W3 holdout SHORT net mean > 0 (the EOD US-index space is 0DTE-decay-prone; holdout is binding)
If any fail -> REJECT at screen (do not write a Phase 2 simulator).

Usage:
  PYTHONIOENCODING=utf-8 venv/Scripts/python.exe experiments/letf_eod_rebalance/letf_eod_rebalance_screen.py
"""
from __future__ import annotations

import os
import sys
from datetime import date
from math import sqrt

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))
sys.path.insert(0, os.path.join(_ROOT, "experiments", "structural_flow_audit"))

from structural_flow_audit import load_m5  # noqa: E402

# config
TZ = "US/Eastern"
OPEN_HM = (9, 30)
DECISION_HM = (15, 30)   # end of "early" window / start of close window
CLOSE_HM = (16, 0)
INSTRUMENTS = {"SPX500": 1.5, "NDX100": 0.8}  # default cost bps RT
DOWN_THRESHOLDS = [-0.003, -0.005, -0.0075, -0.010, -0.015]  # early-move cutoffs (fractional)
TRADING_DAYS_YR = 252
COST_BPS_TRADING_PER_DAY = None  # n/a (one trade per qualifying day)


def section(t): print(f"\n{'='*92}\n  {t}\n{'='*92}\n")


def regime(d: date) -> str:
    if d.year <= 2020: return "W1_2019_2020"
    if d.year <= 2022: return "W2_2021_2022"
    return "W3_2023_2026"


def ann_sh(x, per_year):
    x = x[np.isfinite(x)]
    if len(x) < 2 or x.std(ddof=1) == 0: return 0.0
    return float(x.mean() / x.std(ddof=1) * sqrt(per_year))


def build_daily(sym):
    """Return DataFrame indexed by session date with early_ret, close_ret (both fractional)."""
    bars = load_m5(sym)
    if bars is None:
        return None
    bl = bars.copy()
    bl.index = bl.index.tz_convert(TZ)
    sod = bl.index.hour * 60 + bl.index.minute
    o_mod = OPEN_HM[0]*60 + OPEN_HM[1]
    d_mod = DECISION_HM[0]*60 + DECISION_HM[1]
    c_mod = CLOSE_HM[0]*60 + CLOSE_HM[1]
    dates = bl.index.normalize()

    rows = []
    for ld, sub in bl.groupby(dates):
        s = sub.index.hour*60 + sub.index.minute
        early = sub[(s >= o_mod) & (s < d_mod)]
        closew = sub[(s >= d_mod) & (s < c_mod)]
        if len(early) < 5 or len(closew) < 2:
            continue
        o0 = float(early["open"].iloc[0])
        p_dec = float(early["close"].iloc[-1])   # ~15:30 level
        c1 = float(closew["close"].iloc[-1])
        if o0 <= 0 or p_dec <= 0:
            continue
        early_ret = (p_dec - o0) / o0
        close_ret = (c1 - p_dec) / p_dec
        rows.append((ld.date(), early_ret, close_ret))
    df = pd.DataFrame(rows, columns=["date", "early_ret", "close_ret"]).set_index("date")
    return df


def screen_instrument(sym):
    cost = INSTRUMENTS[sym]
    df = build_daily(sym)
    if df is None or len(df) < 200:
        print(f"  {sym}: insufficient data"); return
    n_days = len(df)
    print(f"\n  --- {sym}  n_days={n_days}  ({df.index[0]} -> {df.index[-1]})  cost={cost}bp ---")

    # unconditional baseline: SHORT the close window every day
    uncond_short_net = (-df["close_ret"].values * 1e4) - cost
    print(f"  unconditional SHORT close-window net mean {uncond_short_net.mean():+.2f}bp  "
          f"sh {ann_sh(uncond_short_net, TRADING_DAYS_YR):+.2f}  n={n_days}")

    print(f"\n  {'thr':>7s} {'n':>4s} {'shortNet':>9s} {'shSh':>6s} {'contZc':>7s} {'fadeZc':>7s} "
          f"{'dirGap':>7s} {'W1':>7s} {'W2':>7s} {'W3':>7s}")
    for thr in DOWN_THRESHOLDS:
        mask = df["early_ret"].values <= thr
        n = int(mask.sum())
        if n < 10:
            print(f"  {thr*100:>+6.2f}% {n:>4d}  INSUF"); continue
        cr = df["close_ret"].values[mask]                  # fractional close-window return on down days
        short_zc = (-cr) * 1e4                             # SHORT continuation, zero cost
        fade_zc = (cr) * 1e4                               # fade (long the close) zero cost
        short_net = short_zc - cost
        dir_gap = ann_sh(short_zc, TRADING_DAYS_YR) - ann_sh(fade_zc, TRADING_DAYS_YR)
        labs = np.array([regime(d) for d in df.index[mask]])
        wmeans = {}
        for w in ("W1_2019_2020", "W2_2021_2022", "W3_2023_2026"):
            sub = short_net[labs == w]
            wmeans[w] = float(sub.mean()) if len(sub) >= 2 else float("nan")
        print(f"  {thr*100:>+6.2f}% {n:>4d} {short_net.mean():>+8.2f} "
              f"{ann_sh(short_net, TRADING_DAYS_YR):>+5.2f} {short_zc.mean():>+6.2f} {fade_zc.mean():>+6.2f} "
              f"{dir_gap:>+6.2f} {wmeans['W1_2019_2020']:>+6.2f} {wmeans['W2_2021_2022']:>+6.2f} "
              f"{wmeans['W3_2023_2026']:>+6.2f}")


def main() -> int:
    section("LEVERAGED-ETF EOD REBALANCE SHORT — Phase 0/1 screen")
    print(f"  early window {OPEN_HM[0]:02d}:{OPEN_HM[1]:02d}->{DECISION_HM[0]:02d}:{DECISION_HM[1]:02d} ET  "
          f"close window {DECISION_HM[0]:02d}:{DECISION_HM[1]:02d}->{CLOSE_HM[0]:02d}:{CLOSE_HM[1]:02d} ET")
    print(f"  SHORT close window conditioned on early-move <= threshold (continuation hypothesis)")
    print(f"  Promote gate: best-thr short net >= +3bp AND dir-gap > +0.40 AND W3 short net > 0")
    for sym in INSTRUMENTS:
        screen_instrument(sym)
    section("Read: promote to Phase 2 thesis lock only if a threshold clears ALL three gate conditions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
