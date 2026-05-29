#!/usr/bin/env python3
"""
Phase 2 simulator — VIX settlement (SOQ) pre-open SHORT.

Thesis: experiments/vix_soq_short/vix_soq_short.md

Primary  : SPX500 (VIX settles off SPX options ⇒ SPX is the mechanism-correct vessel)
Trigger  : Wednesday before the 3rd Friday of each month (VIX-expiration Wednesday)  ~12/yr
Window   : 08:30 -> 09:30 ET (the hour BEFORE the 09:30 SOQ print)
Direction: SHORT (enter window-start open, exit window-end close; fixed window, no stops)

12 pre-committed kill criteria (FROZEN in the thesis before this run) + bootstrap CI +
cost-stress + WF halves + direction null + placebo + deflated Sharpe + same-complex
corroboration (NDX100, non-load-bearing) + recent-event trade audit.

Usage:
  PYTHONIOENCODING=utf-8 venv/Scripts/python.exe experiments/vix_soq_short/vix_soq_short_demo.py
"""
from __future__ import annotations

import os
import sys
from datetime import date
from math import log, sqrt

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))
sys.path.insert(0, os.path.join(_ROOT, "experiments", "structural_flow_audit"))

from structural_flow_audit import (  # noqa: E402
    load_m5, compute_window_returns, compute_placebo_returns, gen_vix_soq_dates,
)

# ----------------------------------------------------------------------------- config
PRIMARY = "SPX500"
CELLS = {  # instrument -> (tz, (sh,sm,eh,em), default_cost_bps)
    "SPX500": ("US/Eastern", (8, 30, 9, 30), 1.5),
    "NDX100": ("US/Eastern", (8, 30, 9, 30), 0.8),  # same-complex SANITY ONLY (NDX has own VXN)
}
EVENTS_PER_YEAR = 12
YEARS = range(2019, 2027)
N_SCREEN_CELLS = 28          # v2 screen breadth (deflation)
COST_STRESS_MULT = 2.0

# FROZEN kill-criteria thresholds (see thesis)
KC1_FULL_MEAN = 3.0
KC2_W3_MEAN = 2.0
KC4_ANN_SH = 0.30
KC5_PF = 1.3
KC6_MDD = 0.10
KC7_BOOT_LOWER = 0.0
KC8_DIR_GAP = 0.30
KC9_PLACEBO_MEAN = 3.0
KC10_STRESS_NET = 0.0
KC11_DEFLATED = 0.0
KC12_WF_BOTH_POS = True


def section(t): print(f"\n{'='*92}\n  {t}\n{'='*92}\n")


def regime(d: date) -> str:
    if d.year <= 2020: return "W1_2019_2020"
    if d.year <= 2022: return "W2_2021_2022"
    return "W3_2023_2026"


def ann_sh(x):
    x = x[np.isfinite(x)]
    if len(x) < 2 or x.std(ddof=1) == 0: return 0.0
    return float(x.mean() / x.std(ddof=1) * sqrt(EVENTS_PER_YEAR))


def mdd_frac(rf):
    if len(rf) == 0: return 0.0
    eq = (1.0 + rf).cumprod(); rm = np.maximum.accumulate(eq)
    return float(((eq - rm) / rm).min())


def profit_factor(x):
    gw = float(x[x > 0].sum()); gl = float(-x[x <= 0].sum())
    return gw / gl if gl > 0 else float("inf")


def boot_ci(x, n_iter=5000, seed=42):
    if len(x) < 2: return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    bm = np.array([rng.choice(x, size=len(x), replace=True).mean() for _ in range(n_iter)])
    return float(np.quantile(bm, 0.025)), float(np.quantile(bm, 0.975))


def deflated(observed_sh, n, n_trials):
    if n < 4 or n_trials <= 1: return observed_sh
    e_max = sqrt(2.0 * log(n_trials)) / sqrt(n)
    return float(observed_sh - e_max)


def short_returns(sym):
    """Returns (short_gross_bps, short_net_bps, kept_dates, long_gross_bps, cost_bps, tz, win)."""
    tz, win, cost = CELLS[sym]
    bars = load_m5(sym)
    if bars is None:
        return None
    long_bps, kept = compute_window_returns(bars, gen_vix_soq_dates(YEARS), tz, *win)
    short_gross = -long_bps
    return short_gross, short_gross - cost, kept, long_bps, cost, tz, win


def main() -> int:
    section("VIX SOQ PRE-OPEN SHORT — Phase 2")
    print(f"  primary={PRIMARY}  events/yr={EVENTS_PER_YEAR}  screen-cells(deflation)={N_SCREEN_CELLS}")

    res = short_returns(PRIMARY)
    if res is None:
        print("  PRIMARY data missing"); return 1
    sgross, snet, kept, lgross, cost, tz, win = res
    n = len(snet)
    print(f"  {PRIMARY} {tz} {win[0]:02d}:{win[1]:02d}-{win[2]:02d}:{win[3]:02d}  "
          f"n={n}  cost={cost}bp  ({kept[0]} -> {kept[-1]})")

    # headline
    section("Headline (SHORT, cost-net)")
    mean_net = float(snet.mean()); std_net = float(snet.std(ddof=1))
    sh = ann_sh(snet); pf = profit_factor(snet); mdd = mdd_frac(snet / 1e4)
    wr = float((snet > 0).mean())
    print(f"  mean_net {mean_net:+.2f}bp  std {std_net:.2f}bp  ann_sh {sh:+.2f}  PF {pf:.2f}  WR {wr*100:.1f}%  MDD {mdd*100:+.2f}%")

    # regime
    section("Regime breakdown (SHORT cost-net)")
    labels = np.array([regime(d) for d in kept])
    rr = {}
    print(f"  {'window':<16s} {'n':>3s} {'mean':>9s} {'t':>6s} {'sh':>6s} {'PF':>5s}")
    for w in ("W1_2019_2020", "W2_2021_2022", "W3_2023_2026"):
        m = labels == w
        if m.sum() < 2: print(f"  {w:<16s} INSUF (n={int(m.sum())})"); rr[w] = None; continue
        sub = snet[m]; mu = float(sub.mean()); sd = float(sub.std(ddof=1))
        t = mu / (sd / sqrt(len(sub))) if sd > 0 else 0.0
        rr[w] = {"mean": mu, "t": t, "sh": ann_sh(sub), "pf": profit_factor(sub), "n": int(m.sum())}
        print(f"  {w:<16s} {int(m.sum()):>3d} {mu:>+8.2f} {t:>+5.2f} {ann_sh(sub):>+5.2f} {profit_factor(sub):>4.2f}")

    # bootstrap
    section("Bootstrap 95% CI on full-sample mean")
    blo, bhi = boot_ci(snet)
    print(f"  point {mean_net:+.2f}bp  95% CI [{blo:+.2f}, {bhi:+.2f}]")

    # direction null
    section("Direction null (zero-cost LONG vs SHORT)")
    long_sh = ann_sh(lgross); short_sh = ann_sh(sgross); dir_gap = short_sh - long_sh
    print(f"  LONG zc sh {long_sh:+.2f}  SHORT zc sh {short_sh:+.2f}  dir-gap {dir_gap:+.2f}")

    # placebo
    section("Placebo non-VIX-SOQ same-weekday pre-open windows (SHORT)")
    weekdays = {d.weekday() for d in kept}
    pl_long = compute_placebo_returns(load_m5(PRIMARY), set(kept), tz, weekdays, *win, max_samples=1500)
    pl_short = -pl_long
    print(f"  placebo n={len(pl_short)} weekdays={sorted(weekdays)}  placebo SHORT mean(gross) {pl_short.mean():+.2f}bp"
          f"  vs event {sgross.mean():+.2f}bp  gap {sgross.mean()-pl_short.mean():+.2f}bp")

    # cost sweep
    section("Cost sweep (SHORT)")
    stress_net = None
    print(f"  {'cost_bp':>8s} {'mean':>9s} {'sh':>6s} {'PF':>5s}")
    for cb in (0.0, cost*0.5, cost, cost*COST_STRESS_MULT, cost*4):
        net = sgross - cb
        marker = "  (default)" if abs(cb-cost) < 1e-9 else ("  (2x stress)" if abs(cb-cost*COST_STRESS_MULT) < 1e-9 else "")
        print(f"  {cb:>8.2f} {net.mean():>+8.2f} {ann_sh(net):>+5.2f} {profit_factor(net):>4.2f}{marker}")
        if abs(cb-cost*COST_STRESS_MULT) < 1e-9: stress_net = float(net.mean())

    # walk-forward halves
    section("Walk-forward halves")
    mid = n // 2
    h1, h2 = snet[:mid], snet[mid:]
    h1m, h2m = float(h1.mean()), float(h2.mean())
    print(f"  H1 ({len(h1)}, {kept[0]}->{kept[mid-1]}) mean {h1m:+.2f}bp sh {ann_sh(h1):+.2f}")
    print(f"  H2 ({len(h2)}, {kept[mid]}->{kept[-1]}) mean {h2m:+.2f}bp sh {ann_sh(h2):+.2f}")

    # deflated
    section(f"Deflated Sharpe (n_trials={N_SCREEN_CELLS})")
    dsh = deflated(sh, n, N_SCREEN_CELLS)
    print(f"  observed {sh:+.3f}  deflated {dsh:+.3f}")

    # same-complex corroboration (NDX100 — NOT load-bearing, VIX is SPX-specific)
    section("Same-complex corroboration (SHORT cost-net) — NDX100 is SANITY only")
    print(f"  {'sym':<8s} {'n':>3s} {'mean':>9s} {'sh':>6s} {'W3_mean':>9s} {'W3_sh':>6s}")
    cross = {}
    for sym in CELLS:
        r = short_returns(sym)
        if r is None: print(f"  {sym:<8s} NO DATA"); continue
        sg, sn, kp, lg, cb, _, _ = r
        lab = np.array([regime(d) for d in kp]); w3 = sn[lab == "W3_2023_2026"]
        w3m = float(w3.mean()) if len(w3) >= 2 else float("nan")
        w3sh = ann_sh(w3) if len(w3) >= 2 else float("nan")
        cross[sym] = {"mean": float(sn.mean()), "sh": ann_sh(sn), "w3m": w3m}
        print(f"  {sym:<8s} {len(sn):>3d} {sn.mean():>+8.2f} {ann_sh(sn):>+5.2f} {w3m:>+8.2f} {w3sh:>+5.2f}")

    # recent-event trade audit (bug-immune mechanism, but show the trades)
    section("Recent-event trade audit (last 8 VIX-SOQ SHORTs, SPX500)")
    bars = load_m5(PRIMARY); bl = bars.copy(); bl.index = bl.index.tz_convert(tz)
    for d in kept[-8:]:
        sub = bl[bl.index.normalize().date == d]
        sod = sub.index.hour*60 + sub.index.minute
        s0 = win[0]*60+win[1]; s1 = win[2]*60+win[3]
        w = sub[(sod >= s0) & (sod < s1)]
        if len(w) < 2: print(f"  {d}: <2 bars"); continue
        eo, ec = float(w['open'].iloc[0]), float(w['close'].iloc[-1])
        print(f"  {d}  enter@open {eo:.2f}  exit@close {ec:.2f}  SHORT ret {(eo-ec)/eo*1e4:+.1f}bp")

    # ---- kill criteria ----
    section("Phase 2 pre-committed kill criteria (12)")
    w1, w2, w3 = rr.get("W1_2019_2020"), rr.get("W2_2021_2022"), rr.get("W3_2023_2026")
    all_pos = all(r is not None and r["mean"] > 0 for r in (w1, w2, w3))
    crit = [
        ("1. Full mean net >= +3 bp", mean_net >= KC1_FULL_MEAN, f"{mean_net:+.2f}bp"),
        ("2. W3 mean net >= +2 bp", w3 is not None and w3["mean"] >= KC2_W3_MEAN, f"{w3['mean']:+.2f}bp" if w3 else "n/a"),
        ("3. All 3 regimes net positive", all_pos,
            f"{w1['mean'] if w1 else 0:+.1f}/{w2['mean'] if w2 else 0:+.1f}/{w3['mean'] if w3 else 0:+.1f}"),
        ("4. Ann Sharpe >= +0.30", sh >= KC4_ANN_SH, f"{sh:+.2f}"),
        ("5. PF >= 1.3 (SHORT, lesson #55)", pf >= KC5_PF, f"{pf:.2f}"),
        ("6. MDD <= -10%", abs(mdd) <= KC6_MDD, f"{mdd*100:+.2f}%"),
        ("7. Bootstrap CI lower > 0", blo > KC7_BOOT_LOWER, f"[{blo:+.2f},{bhi:+.2f}]"),
        ("8. Direction-gap > +0.30", dir_gap > KC8_DIR_GAP, f"{dir_gap:+.2f}"),
        ("9. Placebo SHORT mean < +3 bp", float(pl_short.mean()) < KC9_PLACEBO_MEAN, f"{pl_short.mean():+.2f}bp"),
        ("10. Cost-stress 2x net > 0", stress_net is not None and stress_net > KC10_STRESS_NET, f"{stress_net:+.2f}bp" if stress_net is not None else "n/a"),
        ("11. Deflated Sharpe >= 0.0", dsh >= KC11_DEFLATED, f"{dsh:+.2f}"),
        ("12. WF halves both net > 0", (h1m > 0) and (h2m > 0), f"H1={h1m:+.1f} H2={h2m:+.1f}"),
    ]
    npass = 0
    for name, ok, msg in crit:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:<40s} {msg}")
        npass += int(ok)
    verdict = "PASS" if npass == 12 else ("MARGINAL" if npass >= 8 else "REJECT")
    print(f"\n  Result: {npass}/12  ->  {verdict}")

    section("Summary")
    print(f"  vix_soq_short  primary={PRIMARY}  n={n}  mean_net {mean_net:+.2f}bp  ann_sh {sh:+.2f}")
    print(f"  deflated_sh {dsh:+.2f}  boot[{blo:+.2f},{bhi:+.2f}]  dir-gap {dir_gap:+.2f}")
    print(f"  regimes W1 {w1['mean'] if w1 else 'n/a'}  W2 {w2['mean'] if w2 else 'n/a'}  W3 {w3['mean'] if w3 else 'n/a'}")
    print(f"  NDX100 same-complex W3 mean: {cross.get('NDX100', {}).get('w3m', float('nan')):+.1f} (sanity only)")
    print(f"  VERDICT: {npass}/12 -> {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
