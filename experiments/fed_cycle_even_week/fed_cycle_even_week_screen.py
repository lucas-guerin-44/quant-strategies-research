#!/usr/bin/env python3
"""
Fed-cycle even-week equity drift — Phase 0/1 screen.

Cieslak, Morse & Vissing-Jorgensen (2019, J. Finance): over 1994-2016 the entire US
equity premium was earned in the EVEN weeks of the FOMC cycle (weeks 0/2/4/6 counting
from each FOMC announcement); odd weeks ~flat. Mechanism: Fed information cycle +
liquidity provision biweekly.

Test (mostly OUT-OF-SAMPLE to the paper, 2019-2026): LONG NDX100/SPX100 on even-week
days, cash on odd-week days. Built-in null = even-vs-odd mean. Per lesson #73 (single-
instrument long-bias), the binding gates are (a) even-week Sh > Buy&Hold Sh AND
(b) even-week mean > odd-week mean by a meaningful margin.

cycle day t = trading days since most recent FOMC announcement (t=0 = announcement day)
week = t // 5 ; even_week = (week % 2 == 0)   [standard simplified CMV replication]
"""
from __future__ import annotations

import os
import sys
from datetime import date

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))
sys.path.insert(0, _ROOT)  # repo root, for `import data`

from data import fetch_ohlc  # noqa: E402

FOMC_CAL = os.path.join(_ROOT, "experiments", "_live", "macro_drift", "fomc_calendar.csv")
SYMBOLS = ["NDX100", "SPX500"]
SWAP_BPS_PER_DAY = 1.5   # ~financing on a long index CFD held overnight (even-week days)
START, END = "2019-01-01", "2026-05-26"


def section(t): print(f"\n{'='*92}\n  {t}\n{'='*92}\n")


def regime(y):
    if y <= 2020: return "W1"
    if y <= 2022: return "W2"
    return "W3H"


def sharpe(r):
    r = r[np.isfinite(r)]
    if len(r) < 2 or r.std(ddof=1) == 0: return 0.0
    return float(r.mean()/r.std(ddof=1)*np.sqrt(252))


def daily_close(sym):
    df = fetch_ohlc(sym, "M5", START, END)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df.index = df.index.tz_convert("US/Eastern")
    g = df.groupby(df.index.normalize())["close"].last()
    g.index = [d.date() for d in g.index]
    return g


def fomc_dates():
    c = pd.read_csv(FOMC_CAL)
    return sorted(date.fromisoformat(str(x)[:10]) for x in c["date"])


def cycle_even_flags(trading_days, fomc):
    """For each trading day return (even_week_bool). t = trading-days since last FOMC."""
    fomc = sorted(fomc)
    flags = []
    for i, d in enumerate(trading_days):
        # most recent FOMC on/before d
        prior = [f for f in fomc if f <= d]
        if not prior:
            flags.append(None); continue
        last = prior[-1]
        # t = number of trading days from `last` to d (count positions in trading_days)
        # find index of `last` (or the trading day on/after last)
        t = sum(1 for x in trading_days[:i+1] if x > last)  # trading days strictly after last, up to d
        # t=0 means d is the announcement day itself
        week = t // 5
        flags.append(week % 2 == 0)
    return flags


def main():
    section("FED-CYCLE EVEN-WEEK EQUITY DRIFT — Phase 0/1 screen")
    fomc = [f for f in fomc_dates() if f >= date(2018, 6, 1)]
    print(f"  FOMC announcements loaded: {len(fomc)}  ({fomc[0]} -> {fomc[-1]})")

    for sym in SYMBOLS:
        g = daily_close(sym)
        tdays = list(g.index)
        ret = g.pct_change().to_numpy() * 1e4  # daily close-to-close bps
        even = cycle_even_flags(tdays, fomc)
        yrs = np.array([d.year for d in tdays])
        ev = np.array([bool(e) if e is not None else False for e in even])
        valid = np.array([e is not None for e in even]) & np.isfinite(ret)
        ev &= valid

        even_ret = ret[ev]
        odd_ret = ret[valid & ~ev]
        # strategy: even-week LONG (minus swap), 0 on odd days
        strat = np.where(ev, ret - SWAP_BPS_PER_DAY, 0.0)[valid]
        bh = ret[valid]

        section(f"{sym}")
        print(f"  even-week days n={ev.sum():>4d}  mean {even_ret.mean():>+6.2f}bp   Sh(active) {sharpe(even_ret):>+5.2f}")
        print(f"  odd-week  days n={(valid & ~ev).sum():>4d}  mean {odd_ret.mean():>+6.2f}bp   Sh(active) {sharpe(odd_ret):>+5.2f}")
        print(f"  even-odd mean gap: {even_ret.mean()-odd_ret.mean():+.2f}bp")
        print(f"  STRATEGY even-week LONG (−{SWAP_BPS_PER_DAY}bp swap, cash odd): ann-Sh {sharpe(strat):>+5.2f}  | Buy&Hold ann-Sh {sharpe(bh):>+5.2f}")
        print(f"  -> lesson-#73 gate: strategy Sh > B&H Sh ? {'PASS' if sharpe(strat) > sharpe(bh) else 'FAIL'}"
              f"  ({sharpe(strat):+.2f} vs {sharpe(bh):+.2f})")
        # annualized returns
        strat_ann = strat.mean()/1e4*252*100
        bh_ann = bh.mean()/1e4*252*100
        print(f"  ann return: strategy {strat_ann:+.1f}%/yr (≈half exposure)  vs  B&H {bh_ann:+.1f}%/yr")

        print(f"\n  {'rg':<5s} {'evenN':>6s} {'even_mean':>10s} {'odd_mean':>9s} {'gap':>7s} {'stratSh':>8s} {'bhSh':>6s}")
        for rg in ("W1", "W2", "W3H"):
            m = (yrs == yrs) & np.array([regime(y) == rg for y in yrs]) & valid
            if m.sum() < 10: continue
            e_m = ret[m & ev]; o_m = ret[m & ~ev]
            st = np.where(ev[m], ret[m]-SWAP_BPS_PER_DAY, 0.0)
            print(f"  {rg:<5s} {int((m&ev).sum()):>6d} {e_m.mean():>+9.2f} {o_m.mean():>+8.2f} {e_m.mean()-o_m.mean():>+6.2f} {sharpe(st):>+7.2f} {sharpe(ret[m]):>+5.2f}")

    section("READ")
    print("  Promote only if: even-odd gap clearly >0 in 2019-2026 AND even-week strategy Sh > B&H Sh")
    print("  (lesson #73) AND holdout W3H even-odd gap > 0. Beta-timing, not alpha — diversification")
    print("  value vs the index-heavy book is the separate question even if it passes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
