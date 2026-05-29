#!/usr/bin/env python3
"""
Triple-witch closing-hour SHORT — Phase-0+ deep dive on the one MEDIUM cell from
structural_flow_audit_v2 (2026-05-28).

Screen finding: SPX500 15:00-16:00 ET on 3rd-Fri-of-Mar/Jun/Sep/Dec drifts
-16.1 bp/event (t=-2.26, n=29), corroborated UK100 -15.2 bp (t=-2.10).

GATING QUESTION (MEDIUM-tier rule = "refine direction/regime before thesis lock"):
does the SHORT survive the W4 2023-2026 regime, or did 0DTE flip it like the rest
of the OPEX-pin family (lessons #-5 / #-11 / #43)? If W4 is sign-flipped or dead,
tombstone as a 5th OPEX-family REJECT. If W4 holds the SHORT, promote to a full
Phase-2 thesis (sparse-event, ~4/yr, QEXS-style).

Candidate mechanism (directional, NOT pin-MR): in a secular bull tape dealers hold
long-stock hedges against the ITM calls they're short; at the triple-witch settle
they unwind those hedges = net selling into the close = price down. This is the
MIRROR of pin-fade (MR toward strike), so OPEX-family tombstone does not auto-apply.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from structural_flow_audit import (  # noqa: E402
    load_m5, compute_window_returns, gen_triple_witch_dates, section, YEARS,
)

# closing-hour windows per venue
CELLS = [
    ("SPX500", "US/Eastern",     (15, 0, 16, 0)),
    ("NDX100", "US/Eastern",     (15, 0, 16, 0)),
    ("UK100",  "Europe/London",  (15, 30, 16, 30)),
    ("GER40",  "Europe/Berlin",  (16, 30, 17, 30)),
    ("FRA40",  "Europe/Berlin",  (16, 30, 17, 30)),
]

# realistic all-in RT cost (bps) for a SHORT entry/exit at the close
COST_BPS = {"SPX500": 1.5, "NDX100": 0.8, "UK100": 1.5, "GER40": 0.8, "FRA40": 1.5}


def regime(year: int) -> str:
    if year <= 2020: return "W1"   # 2019-2020 pre/COVID
    if year <= 2022: return "W2"   # 2021-2022 vol
    return "W3H"                    # 2023-2026 holdout (the binding window)


def metrics(rets_bps: np.ndarray, cost_bps: float) -> dict:
    """rets_bps are LONG window returns; we evaluate the SHORT (sign-flip)."""
    short = -rets_bps - cost_bps  # SHORT net per-event, in bps
    short_dec = short / 1e4
    n = len(short_dec)
    if n == 0:
        return {"n": 0}
    mean = float(short_dec.mean())
    std = float(short_dec.std(ddof=1)) if n > 1 else 0.0
    sh = (mean / std * np.sqrt(4.0)) if std > 0 else 0.0  # ~4 triple-witch/yr
    t = (mean / (std / np.sqrt(n))) if std > 0 else 0.0
    wr = float((short_dec > 0).mean())
    return {"n": n, "mean_bps": mean * 1e4, "sh": sh, "t": t, "wr": wr}


def main() -> int:
    section("Triple-witch closing-hour SHORT — Phase-0+ deep dive")
    tw_dates = gen_triple_witch_dates(YEARS)
    print(f"  triple-witch dates: {len(tw_dates)}  ({tw_dates[0]} -> {tw_dates[-1]})")

    for sym, tz, win in CELLS:
        bars = load_m5(sym)
        if bars is None:
            print(f"\n  {sym}: NO DATA"); continue
        cost = COST_BPS[sym]
        ev_rets, kept = compute_window_returns(bars, tw_dates, tz, *win)
        if len(ev_rets) == 0:
            print(f"\n  {sym}: no windows matched"); continue
        years = np.array([d.year for d in kept])

        section(f"{sym}  SHORT close {win[0]:02d}:{win[1]:02d}-{win[2]:02d}:{win[3]:02d} {tz}  (cost {cost}bp)")
        full = metrics(ev_rets, cost)
        print(f"  FULL      n={full['n']:>3d}  short_mean {full['mean_bps']:>+7.2f}bp  "
              f"t {full['t']:>+5.2f}  Sh {full['sh']:>+5.2f}  WR {full['wr']*100:4.1f}%")
        # also report the LONG (continuation) net for the direction-null read
        long_net = (ev_rets - cost) / 1e4
        long_sh = (long_net.mean() / long_net.std(ddof=1) * np.sqrt(4.0)) if long_net.std(ddof=1) > 0 else 0.0
        print(f"  (LONG net mean {long_net.mean()*1e4:+.2f}bp  Sh {long_sh:+.2f}  -> dir-gap SHORT-LONG Sh {full['sh']-long_sh:+.2f})")

        print(f"\n  {'regime':<6s} {'n':>3s} {'short_mean':>11s} {'t':>6s} {'Sh':>6s} {'WR':>6s}")
        for rg in ("W1", "W2", "W3H"):
            mask = np.array([regime(y) == rg for y in years])
            if mask.sum() == 0:
                continue
            m = metrics(ev_rets[mask], cost)
            flag = ""
            if rg == "W3H":
                if m["mean_bps"] > 0 and m["t"] < -0 and m["sh"] > 0.3: flag = "  <<< holdout SHORT holds"
                elif m["mean_bps"] <= 0: flag = "  <<< holdout SIGN-FLIP (OPEX-family death)"
            print(f"  {rg:<6s} {m['n']:>3d} {m['mean_bps']:>+10.2f}bp {m['t']:>+5.2f} {m['sh']:>+5.2f} {m['wr']*100:5.1f}%{flag}")

    section("READ")
    print("  Promote to Phase-2 thesis ONLY if SPX500 (or UK100) holdout-W3H SHORT mean>0")
    print("  with |t| meaningful. Holdout sign-flip => 5th OPEX-family REJECT, tombstone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
