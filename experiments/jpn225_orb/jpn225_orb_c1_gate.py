#!/usr/bin/env python3
"""
Nikkei (JPN225) cash-open ORB — Phase-0b C1 gate ONLY (lesson #72).

ORB is 0-for-6 outside DAX. The lesson-#72 binding rule: for any ORB instrument-port,
run the in-session-vs-off-session C1 control BEFORE writing a full simulator. If
(open-anchored zero-cost Sh) − (off-session-anchored zero-cost Sh) < +0.40, REJECT.

Rationale to even try JPN225: TSE Itayose is a literal single-venue opening auction AND
the Nikkei tape is retail-momentum-heavy — the two properties that make DAX the lone ORB
survivor (ASX had the venue but commodity-heavy tape; FTSE neither).

TSE cash open 09:00 JST = 00:00 UTC. Uses GAP-AWARE FILLS (lesson #81): if the breakout
bar opens past the OR level, fill at the open, not the level.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))
sys.path.insert(0, _ROOT)  # repo root, for `import data`

from data import fetch_ohlc  # noqa: E402

SYMBOL = "JPN225"
START, END = "2019-01-01", "2026-05-26"
OR_MIN = 30          # opening-range length
SESSION_HOURS = 6    # trade window length after the anchor


def section(t): print(f"\n{'='*84}\n  {t}\n{'='*84}\n")


def regime(y):
    if y <= 2020: return "W1"
    if y <= 2022: return "W2"
    return "W3H"


def load():
    df = fetch_ohlc(SYMBOL, "M5", START, END)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def orb_returns(df, anchor_h):
    """ORB anchored at anchor_h:00 UTC, OR_MIN opening range, trade SESSION_HOURS.
    Returns (continuation net-of-nothing bps array, years_array). Gap-aware fill."""
    sod = df.index.hour*60 + df.index.minute
    lo = anchor_h*60
    hi = lo + SESSION_HOURS*60
    win = df[(sod >= lo) & (sod < hi)].copy()
    win["d"] = win.index.normalize()
    cont, yrs = [], []
    n_gap = 0
    for d, sub in win.groupby("d"):
        m = sub.index.hour*60 + sub.index.minute - lo  # minutes since anchor
        o = sub["open"].to_numpy(); h = sub["high"].to_numpy()
        l = sub["low"].to_numpy(); c = sub["close"].to_numpy()
        or_mask = m < OR_MIN
        if or_mask.sum() < 2 or (~or_mask).sum() < 4:
            continue
        or_hi = h[or_mask].max(); or_lo = l[or_mask].min()
        post = np.flatnonzero(~or_mask)
        ph, pl, po, pc = h[post], l[post], o[post], c[post]
        up = np.flatnonzero(ph > or_hi)
        dn = np.flatnonzero(pl < or_lo)
        iu = up[0] if len(up) else 10**9
        idn = dn[0] if len(dn) else 10**9
        if iu == 10**9 and idn == 10**9:
            continue
        eod = pc[-1]
        if iu < idn:   # up-break → LONG continuation
            ob = po[iu]; entry = ob if ob > or_hi else or_hi
            if ob > or_hi: n_gap += 1
            cont.append((eod-entry)/entry*1e4)
        else:          # down-break → SHORT continuation
            ob = po[idn]; entry = ob if ob < or_lo else or_lo
            if ob < or_lo: n_gap += 1
            cont.append((entry-eod)/entry*1e4)
        yrs.append(d.year)
    return np.array(cont), np.array(yrs), n_gap


def annsh(x, n_per_yr=252):
    x = x[np.isfinite(x)]
    if len(x) < 2 or x.std(ddof=1) == 0: return 0.0
    return float(x.mean()/x.std(ddof=1)*np.sqrt(n_per_yr))


def main():
    section("JPN225 cash-open ORB — Phase-0b C1 gate (lesson #72)")
    df = load()
    print(f"  {SYMBOL} M5: {len(df):,} bars {df.index[0].date()} -> {df.index[-1].date()}")
    print(f"  OR={OR_MIN}min, trade window {SESSION_HOURS}h, gap-aware fills (lesson #81)")

    cont_in, yr_in, gap_in = orb_returns(df, 0)    # real TSE open 00:00 UTC
    cont_off, yr_off, gap_off = orb_returns(df, 6)  # off-session control 06:00 UTC

    # best direction each (continuation vs fade), zero-cost
    sh_in_c, sh_in_f = annsh(cont_in), annsh(-cont_in)
    sh_off_c, sh_off_f = annsh(cont_off), annsh(-cont_off)
    best_in = max(sh_in_c, sh_in_f); best_off = max(sh_off_c, sh_off_f)
    bestdir_in = "CONT" if sh_in_c >= sh_in_f else "FADE"

    section("In-session (00:00 UTC TSE open) vs off-session (06:00 UTC) — zero-cost")
    print(f"  in-session : n={len(cont_in)}  CONT Sh {sh_in_c:+.2f}  FADE Sh {sh_in_f:+.2f}  (gap-through {gap_in/max(1,len(cont_in))*100:.0f}%)")
    print(f"  off-session: n={len(cont_off)}  CONT Sh {sh_off_c:+.2f}  FADE Sh {sh_off_f:+.2f}")
    delta = best_in - best_off
    print(f"\n  best-dir in-session {best_in:+.2f} ({bestdir_in})  −  best-dir off-session {best_off:+.2f}  =  C1 delta {delta:+.2f}")
    print(f"  C1 GATE (lesson #72, need >=+0.40): {'PASS' if delta >= 0.40 else 'FAIL'}")

    # dir-gap (in-session continuation vs fade)
    dirgap = sh_in_c - sh_in_f
    section("In-session direction null + regime (zero-cost best dir)")
    print(f"  dir-gap (CONT − FADE): {dirgap:+.2f}")
    bt = cont_in if bestdir_in == "CONT" else -cont_in
    print(f"  {'rg':<5s} {'n':>4s} {'mean_bp':>9s} {'Sh':>6s}")
    for rg in ("W1", "W2", "W3H"):
        x = bt[np.array([regime(y) == rg for y in yr_in])]
        print(f"  {rg:<5s} {len(x):>4d} {x.mean() if len(x) else 0:>+8.2f} {annsh(x):>+5.2f}")

    # ---- can we DO anything with the all-session momentum? cost-applied reality ----
    section("Cost-applied economics — does the generic momentum net anything? (lesson #26)")
    print(f"  in-session per-trade mean (zero-cost): {bt.mean():+.2f}bp  std {bt.std(ddof=1):.1f}bp")
    for cb in (0.0, 1.3, 2.6, 5.0):  # 1.3bp≈5pt Raw; 2.6bp≈2x; 5bp pessimistic
        net = bt - cb
        print(f"    cost {cb:>4.1f}bp  net mean {net.mean():>+6.2f}bp  ann-Sh {annsh(net):>+5.2f}"
              f"  {'(default ~5pt)' if cb==1.3 else ''}")
    # off-session too (is the all-session signal cost-survivable anywhere?)
    off_bt = cont_off if sh_off_c >= sh_off_f else -cont_off
    print(f"  off-session net @1.3bp: ann-Sh {annsh(off_bt-1.3):+.2f}  (all-session momentum, not window-specific)")

    section("VERDICT")
    if delta >= 0.40 and best_in > 0.30 and abs(dirgap) >= 0.30:
        print("  PASS C1 gate -> proceed to full ORB Phase 2 (gap-aware, cost-applied, kill criteria).")
    else:
        print("  REJECT at C1 gate -> ORB is not TSE-open-specific on JPN225; do NOT build full sim.")
        print("  Confirms ORB 0-for-7 outside DAX (lesson #72 cheap falsifier doing its job).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
