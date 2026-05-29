#!/usr/bin/env python3
"""
Mega-cap earnings-cluster INDEX drift — NDX100, Phase 0/1 screen.

Distinct from the rejected single-stock earnings family (earnings_fade / earnings_continuation_mag7
/ opex_pin_singlestock): this tests INDEX-LEVEL (NDX100) structural effects around the Mag7
earnings fortnight, where the mechanism is aggregate vol-crush + de-risking/re-risking, not a
single-name PEAD bet.

Three sub-tests (both directions per lesson #54; placebo per lesson #82b):
  A. Reaction-day drift  : NDX RTH return on each Mag7 trade_date (aggregate + per-name)
  B. Post-NVDA relief    : NDX cumulative return over the 3 sessions after NVDA reaction-day
                           (NVDA reports last + is the biggest NDX-mover → uncertainty resolved)
  C. Post-cluster relief : NDX return in the 5 sessions after the LAST Mag7 report each quarter

Calendar: experiments/earnings_fade/data/earnings_calendar.csv (all 7 Mag7 names, 2019-2026).
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

MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]
CAL = os.path.join(_ROOT, "experiments", "earnings_fade", "data", "earnings_calendar.csv")
TZ = "US/Eastern"
RTH = (9, 30, 16, 0)
COST_BPS = 0.8
START, END = "2019-01-01", "2026-05-26"


def section(t): print(f"\n{'='*92}\n  {t}\n{'='*92}\n")


def regime(y):
    if y <= 2020: return "W1"
    if y <= 2022: return "W2"
    return "W3H"


def metr(bps, ann):
    x = bps[np.isfinite(bps)]; n = len(x)
    if n < 2: return {"n": n, "mean": 0, "t": 0, "sh": 0, "wr": 0}
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    return {"n": n, "mean": mu, "t": mu/(sd/np.sqrt(n)) if sd else 0,
            "sh": mu/sd*np.sqrt(ann) if sd else 0, "wr": float((x > 0).mean())}


def main():
    section("MEGA-CAP EARNINGS INDEX DRIFT — NDX100, Phase 0/1 screen")
    ndx = fetch_ohlc("NDX100", "M5", START, END)
    ndx["timestamp"] = pd.to_datetime(ndx["timestamp"], utc=True)
    ndx = ndx.set_index("timestamp").sort_index()
    ndx.index = ndx.index.tz_convert(TZ)
    sod = ndx.index.hour*60 + ndx.index.minute
    ndx = ndx[(sod >= RTH[0]*60+RTH[1]) & (sod < RTH[2]*60+RTH[3])]
    ndx["d"] = ndx.index.normalize()
    daily = ndx.groupby("d").agg(open=("open", "first"), close=("close", "last"))
    daily = daily[ndx.groupby("d").size() >= 30]   # full sessions only
    didx = list(daily.index.date)
    dopen = daily["open"].to_numpy(); dclose = daily["close"].to_numpy()
    pos = {d: i for i, d in enumerate(didx)}
    print(f"  NDX100 full RTH sessions: {len(didx)}  ({didx[0]} -> {didx[-1]})")

    cal = pd.read_csv(CAL)
    cal = cal[cal["ticker"].isin(MAG7)].copy()
    cal["trade_date"] = pd.to_datetime(cal["trade_date"]).dt.date
    cal = cal[(cal["trade_date"] >= pd.Timestamp(START).date()) & (cal["trade_date"] <= pd.Timestamp(END).date())]
    print(f"  Mag7 earnings reaction-days 2019+: {len(cal)}")

    def day_ret(d):  # RTH open->close return in bps
        i = pos.get(d)
        return (dclose[i]-dopen[i])/dopen[i]*1e4 if i is not None else np.nan

    def fwd_ret(d, k):  # close[d] -> close[d+k]
        i = pos.get(d)
        if i is None or i+k >= len(didx): return np.nan
        return (dclose[i+k]-dclose[i])/dclose[i]*1e4

    # ---- A. reaction-day drift ----
    section("A. Reaction-day NDX drift (open->close on Mag7 trade_date)")
    rows = [(r.ticker, r.trade_date, day_ret(r.trade_date)) for r in cal.itertuples()]
    agg = np.array([x[2] for x in rows]); agg = agg[np.isfinite(agg)]
    ml = metr(agg - COST_BPS, 28); ms = metr(-agg - COST_BPS, 28)
    print(f"  LONG  n={ml['n']:>3d} mean {ml['mean']:+.2f}bp t {ml['t']:+.2f} Sh {ml['sh']:+.2f} WR {ml['wr']*100:.1f}%")
    print(f"  SHORT n={ms['n']:>3d} mean {ms['mean']:+.2f}bp t {ms['t']:+.2f} Sh {ms['sh']:+.2f}")
    print(f"  per-name LONG mean(bp):")
    for t in MAG7:
        v = np.array([x[2] for x in rows if x[0] == t]); v = v[np.isfinite(v)]
        m = metr(v - COST_BPS, 4)
        print(f"    {t:<6s} n={m['n']:>2d} mean {m['mean']:>+7.2f} t {m['t']:>+5.2f}")
    # placebo: all-sessions mean (is the reaction-day drift > baseline?)
    allret = (dclose-dopen)/dopen*1e4
    print(f"  placebo all-session mean {float(allret.mean()):+.2f}bp  -> event-specific gap {float(agg.mean())-float(allret.mean()):+.2f}bp")

    # ---- B. post-NVDA relief ----
    section("B. Post-NVDA relief (NDX cum return over next 3 sessions after NVDA reaction-day)")
    nvda = sorted(cal[cal["ticker"] == "NVDA"]["trade_date"])
    for k in (1, 2, 3):
        v = np.array([fwd_ret(d, k) for d in nvda]); v = v[np.isfinite(v)]
        ml = metr(v - COST_BPS, 4); ms = metr(-v - COST_BPS, 4)
        print(f"  +{k}d  LONG n={ml['n']:>2d} mean {ml['mean']:>+7.2f}bp Sh {ml['sh']:>+5.2f} | SHORT mean {ms['mean']:>+7.2f} Sh {ms['sh']:>+5.2f}  dir-gap {abs(ml['sh']-ms['sh']):+.2f}")

    # ---- C. post-cluster relief ----
    section("C. Post-cluster relief (NDX from day-after-last-Mag7-report, +5 sessions)")
    cal["yq"] = pd.to_datetime(cal["trade_date"]).dt.to_period("Q")
    last_by_q = cal.groupby("yq")["trade_date"].max()
    for k in (1, 3, 5):
        v = np.array([fwd_ret(d, k) for d in last_by_q]); v = v[np.isfinite(v)]
        ml = metr(v - COST_BPS, 4); ms = metr(-v - COST_BPS, 4)
        print(f"  +{k}d  LONG n={ml['n']:>2d} mean {ml['mean']:>+7.2f}bp Sh {ml['sh']:>+5.2f} | SHORT mean {ms['mean']:>+7.2f} Sh {ms['sh']:>+5.2f}  dir-gap {abs(ml['sh']-ms['sh']):+.2f}")

    section("READ")
    print("  Promote a sub-test only if: best-dir Sh>=0.30 AND dir-gap>=0.30 AND event-specific")
    print("  gap vs baseline meaningful (A) / holdout-positive. Single-stock earnings family is")
    print("  already tombstoned; this only survives if the INDEX-aggregate effect is distinct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
