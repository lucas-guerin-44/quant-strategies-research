#!/usr/bin/env python3
"""
Pre-jobless-claims drift screen on NDX100 — macro 3-axis track (2026-05-28).

The macro-event-drift family (event_calendar: FOMC/CPI/RS/NFP) drifts LONG on NDX
in the 24h pre-window. Lesson #-13: the book is NOT auto-expandable; an event only
inherits the drift if it aligns on (a) mid-month/mid-cycle, (b) non-Friday,
(c) first-read information. PPI and PCE both REJECTED as confirming-reads.

Jobless claims (initial) is the highest-FREQUENCY first-read labor series:
  - released every Thursday 08:30 ET  -> axis (b) non-Friday PASS, (c) first-read PASS
  - weekly, not monthly                -> axis (a) mid-month N/A (FAILS the framework)
Honest prior = REJECT (no anticipation-accumulation flow builds into a weekly print),
but it has a FREE exact calendar (every Thursday) and huge n, so it's the one macro
candidate testable with zero date-fabrication risk. Putting a number on it either
confirms the 3-axis framework or surfaces a surprise.

Runs BOTH directions per lesson #54. Phase-0 read only (not a thesis lock).
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))
sys.path.insert(0, _ROOT)  # repo root, for `import data`

from data import fetch_ohlc  # noqa: E402

START, END = "2019-01-01", "2026-05-26"
SYMBOL = "NDX100"
RELEASE_HOUR_ET, RELEASE_MIN_ET = 8, 30
WINDOW_HOURS = 24
EXIT_BUFFER_MIN = 30
COST_BPS = 0.8  # NDX ~1pt RT


def section(t): print(f"\n{'='*92}\n  {t}\n{'='*92}\n")


def regime(y):
    if y <= 2020: return "W1"
    if y <= 2022: return "W2"
    return "W3H"


def all_thursdays(start: date, end: date) -> list[date]:
    out, d = [], start
    while d.weekday() != 3:  # Thursday
        d += timedelta(days=1)
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out


def load_bars():
    df = fetch_ohlc(SYMBOL, "M5", START, END)
    df = df[["timestamp", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df["timestamp"].values.astype("datetime64[ns]"), df["close"].to_numpy(np.float64)


def closest(ts, close, target_utc, tol_min=10):
    target = np.datetime64(target_utc.tz_convert("UTC").tz_localize(None))
    i = np.searchsorted(ts, target)
    cands = [c for c in (i-1, i) if 0 <= c < len(ts)]
    best, bd = None, pd.Timedelta(days=10)
    for c in cands:
        dlt = abs(pd.Timestamp(ts[c]) - pd.Timestamp(target))
        if dlt < bd: bd, best = dlt, c
    if best is None or bd > pd.Timedelta(minutes=tol_min): return None
    return float(close[best])


def event_returns(ts, close, dates, direction):
    sign = 1.0 if direction == "long" else -1.0
    rows = []
    for d in dates:
        # release at 08:30 ET -> UTC via ET offset (use fixed -5/-4 handled by tz-aware)
        rel = pd.Timestamp(f"{d} {RELEASE_HOUR_ET:02d}:{RELEASE_MIN_ET:02d}", tz="US/Eastern").tz_convert("UTC")
        entry = closest(ts, close, rel - pd.Timedelta(hours=WINDOW_HOURS))
        exit_ = closest(ts, close, rel - pd.Timedelta(minutes=EXIT_BUFFER_MIN))
        if entry is None or exit_ is None: continue
        gross = sign * (exit_ - entry) / entry * 100.0
        rows.append({"year": d.year, "regime": regime(d.year), "net": gross - COST_BPS/100.0})
    return pd.DataFrame(rows)


def metr(tr):
    if tr.empty: return {"n": 0, "mean": 0, "sh": 0, "t": 0, "wr": 0}
    net = tr["net"].to_numpy()/100.0
    n = len(net); mean = net.mean(); std = net.std(ddof=1) if n > 1 else 0
    sh = mean/std*np.sqrt(52) if std > 0 else 0  # ~52 Thursdays/yr
    t = mean/(std/np.sqrt(n)) if std > 0 else 0
    return {"n": n, "mean": mean*100, "sh": sh, "t": t, "wr": float((net > 0).mean())}


def main():
    section("PRE-JOBLESS-CLAIMS DRIFT on NDX100 — Phase-0 screen (both directions)")
    ts, close = load_bars()
    print(f"  NDX100 M5: {len(ts):,} bars {pd.Timestamp(ts[0]).date()} -> {pd.Timestamp(ts[-1]).date()}")
    thu = [d for d in all_thursdays(date(2019,1,3), date(2026,5,21))]
    print(f"  Thursdays: {len(thu)}  | window {WINDOW_HOURS}h pre-08:30ET, {EXIT_BUFFER_MIN}min buffer, cost {COST_BPS}bp")

    lo = event_returns(ts, close, thu, "long")
    sh = event_returns(ts, close, thu, "short")
    ml, ms = metr(lo), metr(sh)
    section("BASELINE")
    print(f"  LONG   n={ml['n']:>4d}  mean {ml['mean']:+.4f}%  t {ml['t']:+.2f}  Sh {ml['sh']:+.2f}  WR {ml['wr']*100:.1f}%")
    print(f"  SHORT  n={ms['n']:>4d}  mean {ms['mean']:+.4f}%  t {ms['t']:+.2f}  Sh {ms['sh']:+.2f}  WR {ms['wr']*100:.1f}%")
    best = "long" if ml["mean"] > ms["mean"] else "short"
    gap = abs(ml["sh"] - ms["sh"])
    print(f"  -> best {best.upper()}  dir-null-gap Sh {gap:+.2f} (need >=0.30)")

    bt = lo if best == "long" else sh
    section(f"REGIME ({best.upper()})")
    print(f"  {'rg':<5s} {'n':>4s} {'mean':>10s} {'t':>6s} {'Sh':>6s}")
    for rg in ("W1", "W2", "W3H"):
        m = metr(bt[bt["regime"] == rg])
        print(f"  {rg:<5s} {m['n']:>4d} {m['mean']:>+9.4f}% {m['t']:>+5.2f} {m['sh']:>+5.2f}")

    # PLACEBO: same 24h window anchored to non-Thursday weekdays (Mon-Wed). If the
    # holdout LONG drift survives only on Thursdays, it's claims-specific; if the
    # placebo drifts equally, it's just 2023-26 NDX bull-beta in a long overnight window.
    thu_set = set(thu)
    placebo_days = []
    d = date(2019, 1, 2)
    while d <= date(2026, 5, 21):
        if d.weekday() in (0, 1, 2) and d not in thu_set:  # Mon/Tue/Wed
            placebo_days.append(d)
        d += timedelta(days=1)
    pl = event_returns(ts, close, placebo_days, best)
    section(f"PLACEBO ({best.upper()}) — non-Thursday Mon/Tue/Wed, same 24h pre-08:30ET window")
    print(f"  {'rg':<5s} {'n':>4s} {'mean':>10s} {'t':>6s} {'Sh':>6s}")
    for rg in ("W1", "W2", "W3H"):
        m = metr(pl[pl["regime"] == rg])
        print(f"  {rg:<5s} {m['n']:>4d} {m['mean']:>+9.4f}% {m['t']:>+5.2f} {m['sh']:>+5.2f}")
    pm_full = metr(pl); bt_w3 = metr(bt[bt["regime"] == "W3H"]); pl_w3 = metr(pl[pl["regime"] == "W3H"])
    claims_specific_w3 = bt_w3["mean"] - pl_w3["mean"]
    print(f"\n  Thu-W3H mean {bt_w3['mean']:+.4f}%  vs  placebo-W3H mean {pl_w3['mean']:+.4f}%  -> claims-specific gap {claims_specific_w3:+.4f}%")

    section("READ")
    confound = abs(claims_specific_w3) < 0.05  # holdout edge is mostly bull-beta if gap is tiny
    if confound:
        verdict = "REJECT (bull-beta confound — placebo matches the Thursday drift)"
    elif gap < 0.30 or metr(bt)["sh"] < 0.30 or bt_w3["mean"] <= 0:
        verdict = "REJECT"
    else:
        verdict = "INVESTIGATE (claims-specific holdout drift survives placebo)"
    print(f"  Phase-0 verdict: {verdict}")
    print(f"  (3-axis prior was REJECT: weekly low-info first-read, no anticipation-accumulation flow.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
