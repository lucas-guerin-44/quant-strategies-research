#!/usr/bin/env python3
"""
NR7 volatility-contraction breakout — GER40 M5, Phase 0/1 screen.

Thesis (Crabel volatility-contraction): the day after a narrowest-range-in-7-days (NR7)
session, price expands and breaks the NR7 day's range. orb_dax proves DAX/Xetra has
genuine opening-impulse momentum (lesson #18) that CAC/FTSE lack; a vol-contraction→
expansion breakout may tap the SAME venue property from a different trigger.

Rule:
  daily RTH bars (09:00-17:30 Berlin) from M5
  NR7 day i  : range_i == min(range over trailing 7 sessions)
  next day i+1: first M5 bar that breaks NR7_high (up) or NR7_low (down) sets the
               breakout; enter at the broken level, exit at i+1 RTH close
  continuation = trade in break direction ; fade = opposite (null-check, lesson #54)

Reports continuation vs fade, regime split, cost sweep. Risk: generic intraday breakout
is arbed on US indices (lesson #24); DAX is the exception where breakouts work — this
screen tests whether NR7 specifically adds anything over the deployed open-range version.
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

SYMBOL = "GER40"
TZ = "Europe/Berlin"
RTH = (9, 0, 17, 30)
COST_BPS = 0.8
START, END = "2019-01-01", "2026-05-26"


def section(t): print(f"\n{'='*92}\n  {t}\n{'='*92}\n")


def regime(y):
    if y <= 2020: return "W1"
    if y <= 2022: return "W2"
    return "W3H"


def metr(bps, ann=120.0):  # NR7 fires often; ann placeholder ~ trades/yr
    x = bps[np.isfinite(bps)]
    n = len(x)
    if n < 2: return {"n": n, "mean": 0, "t": 0, "sh": 0, "wr": 0}
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    return {"n": n, "mean": mu, "t": mu/(sd/np.sqrt(n)) if sd else 0,
            "sh": mu/sd*np.sqrt(ann) if sd else 0, "wr": float((x > 0).mean())}


def main():
    section("NR7 BREAKOUT — GER40 M5, Phase 0/1 screen")
    df = fetch_ohlc(SYMBOL, "M5", START, END)
    df = df[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df.index = df.index.tz_convert(TZ)
    sod = df.index.hour*60 + df.index.minute
    df = df[(sod >= RTH[0]*60+RTH[1]) & (sod < RTH[2]*60+RTH[3])]
    df["d"] = df.index.normalize()
    print(f"  {SYMBOL} RTH M5 bars: {len(df):,}")

    # per-day OHLC + keep M5 groups
    days, dopen, dhigh, dlow, dclose = [], [], [], [], []
    groups = {}
    for d, sub in df.groupby("d"):
        if len(sub) < 10:  # half-days
            continue
        days.append(d.date())
        dopen.append(sub["open"].iloc[0]); dhigh.append(sub["high"].max())
        dlow.append(sub["low"].min()); dclose.append(sub["close"].iloc[-1])
        groups[d.date()] = sub[["open", "high", "low", "close"]].to_numpy()
    days = np.array(days)
    dhigh = np.array(dhigh); dlow = np.array(dlow)
    rng = dhigh - dlow
    print(f"  trading days: {len(days)}")

    cont, fade = [], []  # net bps
    cont_yr = []
    n_gap_through = 0
    for i in range(7, len(days) - 1):
        if rng[i] != rng[i-6:i+1].min():
            continue  # not NR7
        nr_hi, nr_lo = dhigh[i], dlow[i]
        nxt = groups[days[i+1]]
        o, h, l, c = nxt[:, 0], nxt[:, 1], nxt[:, 2], nxt[:, 3]
        # first breakout
        up = np.where(h > nr_hi)[0]
        dn = np.where(l < nr_lo)[0]
        iu = up[0] if len(up) else 10**9
        idn = dn[0] if len(dn) else 10**9
        if iu == 10**9 and idn == 10**9:
            continue  # no breakout (inside day)
        eod = c[-1]
        # GAP-AWARE FILL (lesson #81 fix): if the breakout bar already opened past the
        # level, a stop order fills at the OPEN, not at the level — booking the level
        # would be phantom gap profit. Fill at max(open, level) for longs / min for shorts.
        if iu < idn:      # up-break first → LONG continuation
            obar = o[iu]
            entry = obar if obar > nr_hi else nr_hi
            if obar > nr_hi: n_gap_through += 1
            cont_ret = (eod - entry)/entry*1e4
        else:             # down-break first → SHORT continuation
            obar = o[idn]
            entry = obar if obar < nr_lo else nr_lo
            if obar < nr_lo: n_gap_through += 1
            cont_ret = (entry - eod)/entry*1e4
        cont.append(cont_ret - COST_BPS)
        fade.append(-cont_ret - COST_BPS)
        cont_yr.append(days[i+1].year)
    print(f"  NR7 breakout events: {len(cont)}  | gap-through fills (open past level): {n_gap_through} ({n_gap_through/max(1,len(cont))*100:.0f}%)")

    cont = np.array(cont); fade = np.array(fade); yrs = np.array(cont_yr)
    section("Continuation vs Fade (cost-net)")
    mc, mf = metr(cont), metr(fade)
    print(f"  CONTINUATION n={mc['n']:>4d}  mean {mc['mean']:>+6.2f}bp  t {mc['t']:>+5.2f}  Sh {mc['sh']:>+5.2f}  WR {mc['wr']*100:.1f}%")
    print(f"  FADE         n={mf['n']:>4d}  mean {mf['mean']:>+6.2f}bp  t {mf['t']:>+5.2f}  Sh {mf['sh']:>+5.2f}")
    best = "CONTINUATION" if mc["mean"] > mf["mean"] else "FADE"
    gap = abs(mc["sh"] - mf["sh"])
    print(f"  -> best {best}  dir-gap Sh {gap:+.2f}")

    bt = cont if best == "CONTINUATION" else fade
    section(f"Regime ({best})")
    print(f"  {'rg':<5s} {'n':>4s} {'mean':>8s} {'t':>6s} {'sh':>6s}")
    for rg in ("W1", "W2", "W3H"):
        m = metr(bt[np.array([regime(y) == rg for y in yrs])])
        print(f"  {rg:<5s} {m['n']:>4d} {m['mean']:>+7.2f} {m['t']:>+5.2f} {m['sh']:>+5.2f}")

    section("Cost sweep (best dir)")
    base = (cont if best == "CONTINUATION" else fade) + COST_BPS  # gross
    for cb in (0.0, 0.8, 1.6, 3.0):
        m = metr(base - cb)
        print(f"  cost {cb:>4.1f}bp  mean {m['mean']:+.2f}  Sh {m['sh']:+.2f}")

    section("READ")
    v = "REJECT" if (gap < 0.30 or metr(bt)["sh"] < 0.30 or metr(bt[np.array([regime(y)=='W3H' for y in yrs])])['mean'] <= 0) else "INVESTIGATE"
    print(f"  verdict: {v}  (need best-dir Sh>=0.30, dir-gap>=0.30, holdout>0, cost-survivable)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
