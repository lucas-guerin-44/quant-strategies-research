#!/usr/bin/env python3
"""
Softs TSMOM ensemble -- EIGHTCAP-DEPLOYABLE SUB-BASKET re-validation.

Context
-------
`softs_ensemble` was VALIDATED (Sh 0.85 / holdout 1.44) on a 6-name basket
(COCOA, COFFEE, COTTON, CORN, SOYBEAN, LIVE_CATTLE) using Yahoo continuous-
future history, but tombstoned VALIDATED_NO_DEPLOY because Eightcap's own D1
feed was too short to re-validate.

Phase-0 swap probe (scripts/softs_swap_probe.py, 2026-05-29) changed the
picture: Eightcap *does* carry softs CFDs, but the lesson-#59 CFD-swap ceiling
splits the basket:
  - COCOA  long-financing ~ -0.14%/yr  -> survives
  - COFFEE long-financing ~ +0.13%/yr  -> survives (slight credit)
  - COTTON ~ -16.9%/yr | CORN ~ -17.2%/yr | WHEAT ~ -11.2%/yr -> PEAD-redux, dead
  - SOYBEAN, LIVE_CATTLE (the two highest-alpha validated names) -> not offered

So the Eightcap-deployable form collapses to a COCOA + COFFEE pair. This script
re-validates that 2-name sub-basket with the *real* swap cost in the model, the
3-window regime split, the direction null-check, a cost-sensitivity sweep, and a
correlation check against the live book's instruments (the deploy question is
"does a thin commodity leg still clear the +0.30 deploy bar AND diversify the
US-equity/XAU-heavy book?").

Thesis: experiments/softs_ensemble/softs_ensemble.md
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_EXPERIMENTS, 'gold_trend'))

from gold_trend_demo import (  # noqa: E402
    LOOKBACKS, VOL_LOOKBACK, VOL_TARGET_ANN, BARS_PER_YEAR,
    annualized_sharpe, max_drawdown, load_series,
    multi_horizon_signal, atr_series, simulate_tsmom_pyramid,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Eightcap-deployable sub-basket (offered AND swap-survivable). Research runs on
# the long Yahoo continuous-future series (COCOA_YF/COFFEE_YF); the live deploy
# instrument is the Eightcap CFD (COCOA/COFFEE) whose swap is modelled below.
UNIVERSE = ["COCOA_YF", "COFFEE_YF"]

# Live-book instruments to check diversification against (daily directional
# overlap proxy; the book legs are intraday but daily-return corr bounds the
# shared directional exposure).
BOOK_PROXIES = ["XAUUSD", "NDX100", "GER40", "USDJPY"]

# Real Eightcap long-side annual financing (fraction of notional/yr), from the
# 2026-05-29 swap probe. Negative = cost to a long; positive = credit.
SWAP_ANN_LONG = {"COCOA_YF": -0.0014, "COFFEE_YF": +0.0013}

COST_BPS_PER_SIDE = 5.0
START = "2015-01-01"
END = "2026-04-18"

DEPLOY_SHARPE_BAR = 0.30          # CLAUDE.md Phase-2 post-cost deploy bar
ALPHA_BAR = 0.10                  # blend must beat its own B&H basket by this
NULL_GAP_BAR = 0.30               # long - inverse-signal-long must exceed this
MDD_BAR = 0.35
CORR_BOOK_BAR = 0.30              # max |corr| vs any book leg for a clean diversifier


def section(t: str) -> None:
    print(f"\n{'=' * 84}\n  {t}\n{'=' * 84}\n")


def metrics(r: pd.Series) -> dict:
    rn = r.dropna()
    if len(rn) < 5:
        return {"years": 0, "total": 0.0, "cagr": 0.0, "sharpe": 0.0, "mdd": 0.0}
    eq = (1.0 + rn).cumprod().to_numpy()
    years = (rn.index[-1] - rn.index[0]).days / 365.25
    total = float(eq[-1] - 1.0)
    cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
    return {"years": years, "total": total, "cagr": cagr,
            "sharpe": annualized_sharpe(rn.to_numpy()), "mdd": max_drawdown(eq)}


def report_block(label: str, r: pd.Series) -> None:
    m = metrics(r)
    if m["years"] == 0:
        print(f"  {label:<26s} (no data)")
        return
    print(f"  {label:<26s} ret {m['total'] * 100:>+8.2f}%  CAGR {m['cagr'] * 100:>+7.2f}%  "
          f"Sharpe {m['sharpe']:>+6.2f}  MDD {m['mdd'] * 100:>+7.2f}%")


def run_instrument(sym: str, cost_bps: float = COST_BPS_PER_SIDE,
                   invert: bool = False, apply_swap: bool = True) -> dict | None:
    """MH-LO + pyramid on one softs CFD, with optional swap overlay / signal invert."""
    df = load_series(sym)
    if df is None or len(df) < max(LOOKBACKS) + 100:
        return None
    df = df.loc[START:END]
    close, high, low = df["close"], df["high"], df["low"]
    ret = close.pct_change().fillna(0.0)
    rv = ret.rolling(VOL_LOOKBACK, min_periods=VOL_LOOKBACK // 2).std(ddof=1) * np.sqrt(BARS_PER_YEAR)
    rv = rv.shift(1)
    sig = multi_horizon_signal(close, LOOKBACKS)
    if invert:
        sig = -sig                       # direction null: long-only on the DOWN-trend
    atr = atr_series(high, low, close)
    strat_ret, stats = simulate_tsmom_pyramid(
        close, sig, rv, atr, f"{sym}-MH-LO-P{'-INV' if invert else ''}",
        long_only=True, cost_bps_per_side=cost_bps,
    )
    if apply_swap:
        # Daily swap P&L = position-weight * annual_rate / 365 (w is long fraction).
        swap = pd.Series(stats["w"] * (SWAP_ANN_LONG.get(sym, 0.0) / 365.0), index=strat_ret.index)
        strat_ret = (strat_ret + swap).rename(strat_ret.name)
    return {"symbol": sym, "strat_ret": strat_ret,
            "bh_ret": ret.rename(f"{sym}-BH"), "stats": stats}


def blend(results: dict, key: str = "strat_ret") -> pd.Series:
    df = pd.concat([results[s][key].rename(s) for s in UNIVERSE], axis=1, join="inner").dropna()
    return df.mean(axis=1).rename("cocoa+coffee")


def main() -> int:
    # ----- Load + per-instrument (swap on vs off) ------------------------
    section("Per-instrument MH-LO + pyramid (Eightcap sub-basket, swap ON)")
    res = {}
    res_noswap = {}
    for sym in UNIVERSE:
        r = run_instrument(sym, apply_swap=True)
        r0 = run_instrument(sym, apply_swap=False)
        if r is None:
            print(f"  {sym}: LOAD FAILED -- abort")
            return 1
        res[sym], res_noswap[sym] = r, r0

    df0 = load_series(UNIVERSE[0]).loc[START:END]
    print(f"  data window: {df0.index[0].date()} -> {df0.index[-1].date()}  "
          f"({len(df0)} D1 bars)\n")
    print(f"  {'sym':<10s} {'Sh(noswap)':>11s} {'Sh(swap)':>10s} {'CAGR':>8s} {'MDD':>8s} "
          f"{'B&H-Sh':>7s} {'alpha':>7s} {'trades':>7s}")
    for sym in UNIVERSE:
        m = metrics(res[sym]["strat_ret"])
        m0 = metrics(res_noswap[sym]["strat_ret"])
        bh = metrics(res[sym]["bh_ret"])
        print(f"  {sym:<10s} {m0['sharpe']:>+11.2f} {m['sharpe']:>+10.2f} "
              f"{m['cagr'] * 100:>+7.2f}% {m['mdd'] * 100:>+7.2f}% {bh['sharpe']:>+7.2f} "
              f"{m['sharpe'] - bh['sharpe']:>+7.2f} {res[sym]['stats']['trades']:>7d}")

    # ----- 2-name correlation + EW blend ---------------------------------
    section("Cocoa+Coffee correlation & equal-weight blend (swap ON)")
    df_strat = pd.concat([res[s]["strat_ret"].rename(s) for s in UNIVERSE],
                         axis=1, join="inner").dropna()
    pair_corr = float(df_strat.corr().iloc[0, 1])
    print(f"  within-pair daily corr: {pair_corr:+.3f}\n")
    blend_strat = blend(res)
    blend_bh = blend(res, "bh_ret")
    for sym in UNIVERSE:
        report_block(f"{sym}-MH-LO-P", df_strat[sym])
    report_block("EW blend (strategy)", blend_strat)
    report_block("EW blend (B&H basket)", blend_bh)
    bm, bbh = metrics(blend_strat), metrics(blend_bh)
    alpha = bm["sharpe"] - bbh["sharpe"]
    single_avg = np.mean([metrics(df_strat[s])["sharpe"] for s in UNIVERSE])
    print(f"\n  alpha vs B&H basket : {alpha:+.2f} Sharpe")
    print(f"  diversification lift: blend {bm['sharpe']:+.2f} - avg single {single_avg:+.2f} "
          f"= {bm['sharpe'] - single_avg:+.2f}")

    # ----- Regime breakdown ----------------------------------------------
    section("Regime sub-periods (blend strategy, swap ON)")
    windows = [
        ("2015-2017", "2015-01-01", "2017-12-31"),
        ("2018-2019", "2018-01-01", "2019-12-31"),
        ("2020-2021", "2020-01-01", "2021-12-31"),
        ("2022", "2022-01-01", "2022-12-31"),
        ("2023-2026 holdout", "2023-01-01", "2026-12-31"),
    ]
    print(f"  {'window':<22s} {'ret':>10s}  {'CAGR':>8s}  {'Sharpe':>7s}  {'MDD':>8s}")
    regime_rets = []
    for wl, s, e in windows:
        sub = blend_strat.loc[s:e]
        if len(sub) < 50:
            continue
        regime_rets.append((wl, metrics(sub)["total"], metrics(sub)["sharpe"]))
        report_block(wl, sub)
    n_pos = sum(1 for _, _, sh in regime_rets if sh > 0)
    tot = sum(abs(t) for _, t, _ in regime_rets)
    max_share = max(abs(t) for _, t, _ in regime_rets) / tot if tot > 0 else 0.0
    print(f"\n  regimes positive: {n_pos}/{len(regime_rets)}   "
          f"max regime share of abs return: {max_share * 100:.1f}% "
          f"({'PASS' if max_share < 0.60 else 'FAIL'})")

    # ----- Direction null-check ------------------------------------------
    section("Direction null-check (inverse signal: long-only on DOWN-trend)")
    res_inv = {s: run_instrument(s, invert=True, apply_swap=True) for s in UNIVERSE}
    blend_inv = blend(res_inv)
    im = metrics(blend_inv)
    null_gap = bm["sharpe"] - im["sharpe"]
    report_block("blend NORMAL (long-trend)", blend_strat)
    report_block("blend INVERSE (long-downtrend)", blend_inv)
    print(f"\n  null-gap (normal - inverse): {null_gap:+.2f}  "
          f"({'PASS' if null_gap > NULL_GAP_BAR else 'FAIL'} -- need > {NULL_GAP_BAR})")

    # ----- Cost sensitivity ----------------------------------------------
    section("Cost sensitivity (txn bps/side x swap on/off)")
    print(f"  {'txn bps':>8s} {'swap ON Sh':>11s} {'swap OFF Sh':>12s}")
    for cb in (3.0, 5.0, 8.0, 10.0):
        on = {s: run_instrument(s, cost_bps=cb, apply_swap=True) for s in UNIVERSE}
        off = {s: run_instrument(s, cost_bps=cb, apply_swap=False) for s in UNIVERSE}
        print(f"  {cb:>8.1f} {metrics(blend(on))['sharpe']:>+11.2f} "
              f"{metrics(blend(off))['sharpe']:>+12.2f}")

    # ----- Correlation vs live book --------------------------------------
    section("Diversification vs live book (daily-return corr)")
    print(f"  blend daily returns vs each book-leg underlying:")
    max_abs_corr = 0.0
    for sym in BOOK_PROXIES:
        bdf = load_series(sym)
        if bdf is None:
            print(f"    {sym:<10s} (load failed)")
            continue
        # Normalize both indices to calendar date: Yahoo stamps D1 at 00:00 UTC,
        # the lake stamps it at 23:00 (broker-tz artifact), so a raw inner-join
        # matches almost nothing. Floor to date before joining.
        bret = bdf["close"].pct_change()
        bret.index = bret.index.normalize()
        bs = blend_strat.copy()
        bs.index = bs.index.normalize()
        joined = pd.concat([bs, bret.rename(sym)], axis=1, join="inner").dropna()
        joined = joined.loc[START:END]
        if len(joined) < 50:
            print(f"    {sym:<10s} (insufficient overlap)")
            continue
        c = float(joined.corr().iloc[0, 1])
        max_abs_corr = max(max_abs_corr, abs(c))
        print(f"    {sym:<10s} corr {c:>+6.3f}   ({len(joined)} common days)")
    print(f"\n  max |corr| vs book: {max_abs_corr:.3f}  "
          f"({'PASS' if max_abs_corr < CORR_BOOK_BAR else 'FAIL'} -- want < {CORR_BOOK_BAR})")

    # ----- Scorecard -----------------------------------------------------
    section("Deploy scorecard (Eightcap cocoa+coffee sub-basket)")
    n_trades = sum(res[s]["stats"]["trades"] for s in UNIVERSE)

    def v(c: bool) -> str: return "PASS" if c else "FAIL"
    checks = [
        (f"Blend Sharpe > {DEPLOY_SHARPE_BAR} (deploy bar)", bm["sharpe"] > DEPLOY_SHARPE_BAR, f"{bm['sharpe']:+.2f}"),
        (f"Alpha vs B&H >= {ALPHA_BAR}", alpha >= ALPHA_BAR, f"{alpha:+.2f}"),
        (f"Null-gap > {NULL_GAP_BAR}", null_gap > NULL_GAP_BAR, f"{null_gap:+.2f}"),
        (f"MDD < {MDD_BAR:.0%}", abs(bm["mdd"]) < MDD_BAR, f"{bm['mdd'] * 100:+.1f}%"),
        ("Holdout 2023-26 Sharpe > 0", metrics(blend_strat.loc['2023-01-01':])["sharpe"] > 0,
         f"{metrics(blend_strat.loc['2023-01-01':])['sharpe']:+.2f}"),
        (f"Max |corr| vs book < {CORR_BOOK_BAR}", max_abs_corr < CORR_BOOK_BAR, f"{max_abs_corr:.3f}"),
        ("Total trades >= 100", n_trades >= 100, f"{n_trades}"),
    ]
    passed = 0
    for label, ok, val in checks:
        print(f"  {label:<40s} {v(ok):>5s}  ({val})")
        passed += ok
    section("Summary")
    print(f"  cocoa+coffee blend: Sharpe {bm['sharpe']:+.2f}  CAGR {bm['cagr'] * 100:+.2f}%  "
          f"MDD {bm['mdd'] * 100:+.2f}%  ({passed}/{len(checks)} checks PASS)")
    print(f"  (validated 6-name basket was Sh 0.85 / holdout 1.44 -- this is the thinner, "
          f"swap-survivable Eightcap-deployable cut)")
    # Binding kills override the raw pass-count: a high full-sample Sharpe carried
    # by one regime, or weak directional content, is REJECT regardless of count.
    binding_fail = (max_share >= 0.60) or (null_gap <= NULL_GAP_BAR) or (bm["sharpe"] <= DEPLOY_SHARPE_BAR)
    if binding_fail:
        reasons = []
        if max_share >= 0.60:
            reasons.append(f"one-window-wonder ({max_share * 100:.0f}% in one regime)")
        if null_gap <= NULL_GAP_BAR:
            reasons.append(f"weak null-gap ({null_gap:+.2f})")
        if bm["sharpe"] <= DEPLOY_SHARPE_BAR:
            reasons.append(f"Sharpe below deploy bar ({bm['sharpe']:+.2f})")
        verdict = f"REJECT for Eightcap deploy -- binding: {', '.join(reasons)}"
    elif passed >= 6:
        verdict = "PROCEED to Phase 3"
    else:
        verdict = "MARGINAL -- thin but directionally intact"
    print(f"\n  VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
