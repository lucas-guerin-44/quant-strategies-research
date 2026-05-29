#!/usr/bin/env python3
"""
ETH/BTC ratio mean-reversion — Phase 2 demo.

Thesis: experiments/eth_btc_ratio_mr/eth_btc_ratio_mr.md

Daily-close-to-close two-sided spread MR on ETHUSD / BTCUSD CFDs.
Window: 2022-09-15 (Ethereum Merge) → 2026-03-31 (joint coverage end).

PRE-COMMITTED parameters (NOT swept against in-sample Sharpe):
  LOOKBACK     = 90 days
  ENTRY_Z      = 2.0  (|z| ≥ 2.0 enters)
  EXIT_Z       = 0.5  (|z| ≤ 0.5 exits)
  MAX_HOLD     = 30 days
  COST_BPS_RT  = 10 bps (5bp per leg × 2 legs)

Run: ``venv/Scripts/python.exe experiments/eth_btc_ratio_mr/eth_btc_ratio_mr_demo.py``
"""

from __future__ import annotations

import os
import sys
from datetime import date

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))

from data import fetch_ohlc  # noqa: E402


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

START_DATE = "2022-09-15"   # Ethereum Merge
END_DATE = "2026-03-31"     # joint coverage end (BTC latest)

LOOKBACK = 90
ENTRY_Z = 2.0
EXIT_Z = 0.5
MAX_HOLD = 30
COST_BPS_RT = 10.0           # 5bp per leg × 2 legs = 10bp total round-trip

DAYS_PER_YEAR = 365          # crypto 24/7 — annualize per calendar year


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f"\n{'=' * 84}\n  {t}\n{'=' * 84}")


def load_d1_close(symbol: str) -> pd.Series:
    raw = fetch_ohlc(symbol, "D1", "2017-01-01", "2026-05-01")
    if raw is None or raw.empty:
        raise RuntimeError(f"No D1 bars for {symbol}.")
    df = raw[["timestamp", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.normalize()
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df["close"].astype(float).rename(symbol)


def annualized_sharpe(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if r.size == 0:
        return 0.0
    s = r.std(ddof=1)
    if s == 0 or not np.isfinite(s):
        return 0.0
    return float(r.mean() / s * np.sqrt(DAYS_PER_YEAR))


def max_drawdown(eq: np.ndarray) -> float:
    if len(eq) == 0:
        return 0.0
    rm = np.maximum.accumulate(eq)
    dd = (eq - rm) / rm
    return float(dd.min())


# ---------------------------------------------------------------------------
# Simulator — numpy inner loop, state-machine per spread position
# ---------------------------------------------------------------------------

def simulate(
    eth: np.ndarray,
    btc: np.ndarray,
    z: np.ndarray,
    *,
    entry_z: float = ENTRY_Z,
    exit_z: float = EXIT_Z,
    max_hold: int | None = MAX_HOLD,
    cost_bps_rt: float = COST_BPS_RT,
    mode: str = "mr",       # "mr" = mean-revert; "mom" = momentum (null)
    legs: str = "both",     # "both" / "cheap_only" / "rich_only"
) -> tuple[np.ndarray, list[dict]]:
    """Daily close-to-close pair simulation.

    Position convention: position = +1 means LONG ETH / SHORT BTC; position = -1 means
    SHORT ETH / LONG BTC. PnL per bar = position * (eth_ret - btc_ret).

    Entry signal (mode="mr"):
      z <= -entry_z and (legs in {both, cheap_only}) → position = +1
      z >= +entry_z and (legs in {both, rich_only})  → position = -1

    Entry signal (mode="mom"):
      z <= -entry_z and (legs in {both, cheap_only}) → position = -1 (trade WITH the deviation)
      z >= +entry_z and (legs in {both, rich_only})  → position = +1

    Exit: |z| <= exit_z, or held >= max_hold days.

    Returns:
      ret_arr — per-day PnL series, same length as input arrays
      trades  — list of dicts with entry/exit dates, holding days, side, raw + net pnl
    """
    n = len(eth)
    eth_ret = np.zeros(n, dtype=np.float64)
    eth_ret[1:] = eth[1:] / eth[:-1] - 1.0
    btc_ret = np.zeros(n, dtype=np.float64)
    btc_ret[1:] = btc[1:] / btc[:-1] - 1.0

    pnl = np.zeros(n, dtype=np.float64)
    position = 0
    entry_idx = -1
    cost_rt = cost_bps_rt / 1e4

    trades: list[dict] = []

    for i in range(n):
        # Accrue PnL on existing position.
        if position != 0 and i > entry_idx:
            pnl[i] = position * (eth_ret[i] - btc_ret[i])

        # Exit check.
        if position != 0:
            held = i - entry_idx
            exit_cond = abs(z[i]) <= exit_z or (max_hold is not None and held >= max_hold)
            if exit_cond:
                # Charge cost on exit bar (RT covers both entry + exit cost together).
                pnl[i] -= cost_rt
                # Record trade.
                trades.append({
                    "entry_idx": entry_idx,
                    "exit_idx": i,
                    "held_days": held,
                    "side": position,
                    "entry_z": float(z[entry_idx]),
                    "exit_z": float(z[i]),
                    "pnl_net": float(pnl[entry_idx + 1: i + 1].sum()),
                    "exit_reason": "z_cross" if abs(z[i]) <= exit_z else "time_stop",
                })
                position = 0
                entry_idx = -1

        # Entry check (only if flat).
        if position == 0 and np.isfinite(z[i]):
            want_long = (z[i] <= -entry_z) and (legs in ("both", "cheap_only"))
            want_short = (z[i] >= entry_z) and (legs in ("both", "rich_only"))
            if mode == "mr":
                if want_long:
                    position = +1
                    entry_idx = i
                elif want_short:
                    position = -1
                    entry_idx = i
            elif mode == "mom":
                if want_long:
                    position = -1     # opposite of MR
                    entry_idx = i
                elif want_short:
                    position = +1     # opposite of MR
                    entry_idx = i

    return pnl, trades


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report(label: str, pnl: np.ndarray, trades: list[dict]) -> dict:
    eq = np.cumprod(1.0 + pnl)
    sh = annualized_sharpe(pnl)
    mdd = max_drawdown(eq)
    total_ret = float(eq[-1] - 1.0) if len(eq) else 0.0
    years = len(pnl) / DAYS_PER_YEAR
    cagr = (1.0 + total_ret) ** (1.0 / years) - 1.0 if years > 0 and total_ret > -1 else float("nan")
    n_tr = len(trades)
    held = [t["held_days"] for t in trades] if trades else []
    long_n = sum(1 for t in trades if t["side"] == +1)
    short_n = sum(1 for t in trades if t["side"] == -1)
    print(
        f"  {label:<26}  Sh {sh:+.3f}  MDD {mdd*100:+.2f}%  TotRet {total_ret*100:+.1f}%  "
        f"CAGR {cagr*100:+.2f}%  trades {n_tr} (L{long_n}/S{short_n})  "
        f"hold med {np.median(held) if held else 0:.0f}d / p90 {np.percentile(held, 90) if held else 0:.0f}d"
    )
    return {"label": label, "sharpe": sh, "mdd": mdd, "total_ret": total_ret, "cagr": cagr,
            "n_trades": n_tr, "long_n": long_n, "short_n": short_n,
            "held_med": float(np.median(held)) if held else 0.0,
            "held_p90": float(np.percentile(held, 90)) if held else 0.0}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    section("Loading ETHUSD + BTCUSD D1, joining on date")
    eth_s = load_d1_close("ETHUSD")
    btc_s = load_d1_close("BTCUSD")
    df = pd.concat([eth_s, btc_s], axis=1).dropna()
    df = df.loc[START_DATE:END_DATE]
    print(f"  joint coverage: {len(df)} days  |  {df.index.min().date()} → {df.index.max().date()}")
    if len(df) < 365:
        print(f"  WARNING: joint coverage < 1 year — results will be noisy")

    eth = df["ETHUSD"].to_numpy(dtype=np.float64)
    btc = df["BTCUSD"].to_numpy(dtype=np.float64)
    ratio = eth / btc
    log_ratio = np.log(ratio)
    print(f"  ratio range [{ratio.min():.5f}, {ratio.max():.5f}]  mean {ratio.mean():.5f}  std {ratio.std():.5f}")

    # Rolling z-score with strictly-historical window (no look-ahead).
    s = pd.Series(log_ratio, index=df.index)
    mu = s.rolling(LOOKBACK, min_periods=LOOKBACK).mean().shift(1)
    sd = s.rolling(LOOKBACK, min_periods=LOOKBACK).std(ddof=1).shift(1)
    z = ((s - mu) / sd).to_numpy(dtype=np.float64)
    n_valid_z = int(np.isfinite(z).sum())
    print(f"  z-series: {n_valid_z} valid days after {LOOKBACK}d warmup + 1d shift")
    print(f"  z stats: mean {np.nanmean(z):+.3f}  std {np.nanstd(z):.3f}  "
          f"min {np.nanmin(z):+.2f}  max {np.nanmax(z):+.2f}")
    n_above = int((z >= ENTRY_Z).sum())
    n_below = int((z <= -ENTRY_Z).sum())
    print(f"  |z|≥{ENTRY_Z} bars: {n_above + n_below} ({n_below} cheap-side, {n_above} rich-side)")

    section("Population-count sanity (lesson #37 — count before running variants)")
    # Approximate setup count: a "setup" is a fresh crossing from |z|<ENTRY_Z into |z|≥ENTRY_Z.
    abs_z = np.abs(z)
    is_extreme = abs_z >= ENTRY_Z
    crossings = np.zeros_like(is_extreme, dtype=bool)
    crossings[1:] = is_extreme[1:] & ~is_extreme[:-1]
    n_crossings = int(crossings.sum())
    print(f"  fresh entries (|z| crossings into ≥{ENTRY_Z}): ~{n_crossings}")
    if n_crossings < 15:
        print(f"  WARNING: <15 fresh entries on {len(df)/365:.2f}y; trade-count floor in pre-commit is 30 — likely FAIL")

    section("Baseline + variants")
    rows = []
    base_pnl, base_trades = simulate(eth, btc, z, mode="mr", legs="both")
    rows.append(report("baseline (MR both legs)", base_pnl, base_trades))

    cheap_pnl, cheap_trades = simulate(eth, btc, z, mode="mr", legs="cheap_only")
    rows.append(report("cheap-only (LONG ETH)", cheap_pnl, cheap_trades))

    rich_pnl, rich_trades = simulate(eth, btc, z, mode="mr", legs="rich_only")
    rows.append(report("rich-only (SHORT ETH)", rich_pnl, rich_trades))

    mom_pnl, mom_trades = simulate(eth, btc, z, mode="mom", legs="both")
    rows.append(report("momentum-null (both)", mom_pnl, mom_trades))

    nots_pnl, nots_trades = simulate(eth, btc, z, mode="mr", legs="both", max_hold=None)
    rows.append(report("no-time-stop", nots_pnl, nots_trades))

    z15_pnl, z15_trades = simulate(eth, btc, z, mode="mr", legs="both", entry_z=1.5)
    rows.append(report("z≥1.5 entry", z15_pnl, z15_trades))

    z25_pnl, z25_trades = simulate(eth, btc, z, mode="mr", legs="both", entry_z=2.5)
    rows.append(report("z≥2.5 entry", z25_pnl, z25_trades))

    baseline = rows[0]
    cheap = rows[1]
    rich = rows[2]
    mom_null = rows[3]

    section("Pre-committed kill-criteria check (baseline)")
    null_gap = baseline["sharpe"] - mom_null["sharpe"]
    held_med = baseline["held_med"]
    checks = [
        ("Full-window Sharpe ≥ +0.50", baseline["sharpe"] >= 0.50, f"{baseline['sharpe']:+.3f}"),
        ("Trade count ≥ 30", baseline["n_trades"] >= 30, f"{baseline['n_trades']} trades"),
        ("MDD ≤ 20%", baseline["mdd"] >= -0.20, f"{baseline['mdd']*100:+.2f}%"),
        ("Momentum-null gap ≥ +0.30", null_gap >= 0.30, f"gap {null_gap:+.3f} (base {baseline['sharpe']:+.3f} − mom {mom_null['sharpe']:+.3f})"),
        ("Cheap-leg Sh ≥ 0", cheap["sharpe"] >= 0.0, f"{cheap['sharpe']:+.3f}"),
        ("Rich-leg Sh ≥ 0", rich["sharpe"] >= 0.0, f"{rich['sharpe']:+.3f}"),
        ("Half-life sane (5 ≤ med hold ≤ 20)", 5 <= held_med <= 20, f"med hold {held_med:.1f}d"),
    ]
    for name, ok, detail in checks:
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {name}   ({detail})")

    section("Sub-window stability")
    # Split mid-window: 2022-09 → 2024-06 (first half) vs 2024-07 → 2026-03 (second half).
    midpoint = pd.Timestamp("2024-07-01", tz="UTC")
    dates = df.index
    mask_h1 = dates < midpoint
    mask_h2 = dates >= midpoint
    sh_h1 = annualized_sharpe(base_pnl[mask_h1])
    sh_h2 = annualized_sharpe(base_pnl[mask_h2])
    eq_h1 = np.cumprod(1.0 + base_pnl[mask_h1])
    eq_h2 = np.cumprod(1.0 + base_pnl[mask_h2])
    print(f"  H1 2022-09→2024-06: Sh {sh_h1:+.3f}  MDD {max_drawdown(eq_h1)*100:+.2f}%  n_days {int(mask_h1.sum())}")
    print(f"  H2 2024-07→2026-03: Sh {sh_h2:+.3f}  MDD {max_drawdown(eq_h2)*100:+.2f}%  n_days {int(mask_h2.sum())}")
    h_both_ok = sh_h1 >= 0.20 and sh_h2 >= 0.20
    print(f"  [{'PASS' if h_both_ok else 'FAIL'}] Both sub-windows Sh ≥ +0.20")

    section("Cost sensitivity (baseline)")
    for cost in (5.0, 10.0, 20.0, 40.0):
        c_pnl, _ = simulate(eth, btc, z, mode="mr", legs="both", cost_bps_rt=cost)
        sh_c = annualized_sharpe(c_pnl)
        print(f"  {cost:5.1f}bp RT:  Sh {sh_c:+.3f}")
    cost20_pnl, _ = simulate(eth, btc, z, mode="mr", legs="both", cost_bps_rt=20.0)
    sh_20 = annualized_sharpe(cost20_pnl)
    print(f"  [{'PASS' if sh_20 >= 0.20 else 'FAIL'}] 20bp Sharpe ≥ +0.20")

    section("Trade-level summary (baseline)")
    if base_trades:
        held = np.array([t["held_days"] for t in base_trades])
        pnls = np.array([t["pnl_net"] for t in base_trades])
        wr = float((pnls > 0).mean())
        print(f"  n={len(base_trades)}  WR {wr*100:.1f}%  "
              f"avg pnl {pnls.mean()*100:+.3f}%  median {np.median(pnls)*100:+.3f}%  "
              f"hold mean {held.mean():.1f}d  p10/p50/p90 {np.percentile(held,10):.0f}/{np.median(held):.0f}/{np.percentile(held,90):.0f}d")
        reason_counts: dict[str, int] = {}
        for t in base_trades:
            reason_counts[t["exit_reason"]] = reason_counts.get(t["exit_reason"], 0) + 1
        print(f"  exit reasons: {reason_counts}")
        # Best / worst.
        ord_idx = np.argsort(pnls)
        print(f"  worst 3 trades (pnl%, held_d, side, entry_z → exit_z):")
        for k in ord_idx[:3]:
            t = base_trades[int(k)]
            print(f"    {t['pnl_net']*100:+.2f}%   {t['held_days']:>3}d   side {t['side']:+d}   "
                  f"z {t['entry_z']:+.2f} → {t['exit_z']:+.2f}   ({t['exit_reason']})")
        print(f"  best 3 trades:")
        for k in ord_idx[-3:][::-1]:
            t = base_trades[int(k)]
            print(f"    {t['pnl_net']*100:+.2f}%   {t['held_days']:>3}d   side {t['side']:+d}   "
                  f"z {t['entry_z']:+.2f} → {t['exit_z']:+.2f}   ({t['exit_reason']})")

    section("Summary")
    overall_pass = all(ok for _, ok, _ in checks) and h_both_ok and sh_20 >= 0.20
    print(f"  Baseline Sh {baseline['sharpe']:+.3f}  MDD {baseline['mdd']*100:+.2f}%  trades {baseline['n_trades']}")
    print(f"  Momentum-null gap {null_gap:+.3f}   Cheap leg {cheap['sharpe']:+.3f}   Rich leg {rich['sharpe']:+.3f}")
    print(f"  Sub-windows: H1 {sh_h1:+.3f}  H2 {sh_h2:+.3f}")
    print(f"  Cost-stress: 20bp Sh {sh_20:+.3f}")
    print(f"  OVERALL: {'PASS — deploy candidate' if overall_pass else 'FAIL — see kill-criteria above'}")


if __name__ == "__main__":
    main()
