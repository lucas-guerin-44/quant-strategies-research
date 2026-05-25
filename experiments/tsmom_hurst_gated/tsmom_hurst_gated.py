#!/usr/bin/env python3
"""
TSMOM long-only 12-1 with Hurst-regime entry gate.

Reimplements the baseline tsmom strategy in pure numpy (no engine dependency)
so that the gated and ungated variants share identical signal/sizing/cost
machinery. Adds the H_t > 0.50 entry gate to the gated variant.

Pre-commits live in tsmom_hurst_gated.md. Runs three configurations:
  - UNGATED baseline (replicates tsmom KEEP_FOR_REFERENCE)
  - GATED   (long if 12-1 signal AND rolling 252d DFA Hurst > 0.50)
  - INVERTED gate null-check (long if 12-1 signal AND H < 0.50)

Reports full-sample and 2023-2026 W4-holdout Sharpe, MDD, trade count,
gated-vs-ungated correlation, and per-instrument lift table.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

# Reuse the DFA implementation from the diagnostic
sys.path.insert(0, os.path.join(_ROOT, "experiments", "regime_hurst_diagnostic"))
from regime_hurst_diagnostic import rolling_dfa_h


# ---------- pre-committed config ----------

UNIVERSE = [
    "AUDNZD", "NZDCAD", "GBPNZD", "AUDCAD", "CADJPY", "NZDJPY",
    "EURGBP", "EURNOK", "USDZAR",
    "COCOA", "COFFEE", "SUGAR", "COTTON",
    "EWZ", "FXI", "EWJ",
    "XAUUSD", "USOUSD", "SPX500", "NDX100", "GER40", "BTCUSD",
    "EURUSD", "GBPUSD",
]

START_DATE = pd.Timestamp("2015-01-01", tz="UTC")
END_DATE   = pd.Timestamp("2026-04-18", tz="UTC")
W4_SPLIT   = pd.Timestamp("2023-01-01", tz="UTC")

LOOKBACK_BARS    = 252      # 12-month return horizon
SKIP_BARS        = 21       # 1-month skip (classic 12-1)
REBAL_BARS       = 21       # monthly rebalance
VOL_LOOKBACK     = 60       # ~3 months for vol estimate
VOL_TARGET       = 0.15     # 15% annualised per position
SIZE_CAP         = 1.0      # max per-position weight
H_GATE_THRESH    = 0.50     # gated long if H_t > 0.50

# Per-asset round-trip costs (bps), matching baseline tsmom config
COSTS_BPS = {
    "BTCUSD": 15.0,
    "XAUUSD": 8.0, "USOUSD": 8.0,
    "SPX500": 4.0, "NDX100": 4.0, "GER40": 5.0,
    "EURUSD": 3.0, "GBPUSD": 3.0,
    "COCOA": 13.0, "COFFEE": 13.0, "SUGAR": 13.0, "COTTON": 13.0,
    "EWZ": 8.0, "FXI": 8.0, "EWJ": 8.0,
}
DEFAULT_COST_BPS = 6.0  # exotic FX crosses


# ---------- data loading ----------

def load_close(symbol: str) -> pd.Series:
    """Load D1 close series for one instrument, restricted to study window."""
    path = os.path.join(_ROOT, "ohlc_data", f"{symbol}_D1.csv")
    df = pd.read_csv(path, usecols=["timestamp", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    s = df["close"].astype(float)
    return s.loc[START_DATE - pd.Timedelta(days=400):END_DATE]


# ---------- single-instrument backtest (numpy) ----------

@dataclass
class InstrumentRun:
    symbol: str
    dates: np.ndarray         # rebal dates only
    weights: np.ndarray       # per-rebal target weight (0..size_cap)
    daily_returns: np.ndarray # per-day strategy return (post-cost)
    daily_dates: pd.DatetimeIndex
    trade_count: int


def backtest_instrument(symbol: str, gate_mode: str = "none") -> InstrumentRun:
    """
    Run long-only 12-1 TSMOM on one instrument, with optional Hurst gate.

    gate_mode:
      "none"     - no gate (baseline)
      "gated"    - long requires H_t > H_GATE_THRESH
      "inverted" - long requires H_t < H_GATE_THRESH (null-check)
    """
    close = load_close(symbol)
    if close.size < LOOKBACK_BARS + VOL_LOOKBACK + 30:
        # insufficient history
        return InstrumentRun(symbol, np.array([]), np.array([]),
                              np.zeros(0), pd.DatetimeIndex([]), 0)

    px = close.to_numpy(dtype=float)
    log_px = np.log(px)
    log_ret = np.diff(log_px, prepend=log_px[0])
    n = px.size

    # Rolling Hurst across the entire series (use the diagnostic's implementation)
    if gate_mode in ("gated", "inverted"):
        h_series = rolling_dfa_h(log_ret, window=252, scales=(10, 20, 50, 100))
    else:
        h_series = np.full(n, np.nan)

    # Per-day target weight series
    weights = np.zeros(n)
    rebal_idx = []
    rebal_w   = []

    earliest = LOOKBACK_BARS + SKIP_BARS + 1
    # Walk forward on a monthly rebal cadence
    for t in range(earliest, n):
        # rebal day check
        bars_since_last = (t - rebal_idx[-1]) if rebal_idx else REBAL_BARS
        if rebal_idx and bars_since_last < REBAL_BARS:
            continue

        # 12-1 momentum signal
        r12_1 = px[t - SKIP_BARS] / px[t - LOOKBACK_BARS - SKIP_BARS] - 1.0
        sig_long = 1.0 if r12_1 > 0 else 0.0

        # Hurst gate
        if gate_mode == "gated":
            h_t = h_series[t]
            gate = 1.0 if (np.isfinite(h_t) and h_t > H_GATE_THRESH) else 0.0
        elif gate_mode == "inverted":
            h_t = h_series[t]
            gate = 1.0 if (np.isfinite(h_t) and h_t < H_GATE_THRESH) else 0.0
        else:
            gate = 1.0

        # Vol-target sizing
        rv_window = log_ret[t - VOL_LOOKBACK:t]
        rv_ann = rv_window.std(ddof=0) * np.sqrt(252.0)
        if rv_ann <= 1e-8:
            target_w = 0.0
        else:
            target_w = min(SIZE_CAP, VOL_TARGET / rv_ann)
        target_w = target_w * sig_long * gate

        rebal_idx.append(t)
        rebal_w.append(target_w)

    # Forward-fill weights between rebals
    if not rebal_idx:
        return InstrumentRun(symbol, np.array([]), np.array([]),
                              np.zeros(n), close.index, 0)
    prev_w = 0.0
    rebal_set = dict(zip(rebal_idx, rebal_w))
    for t in range(n):
        if t in rebal_set:
            weights[t] = rebal_set[t]
            prev_w = weights[t]
        else:
            weights[t] = prev_w

    # Daily strategy returns: weight_{t-1} * arithmetic_return_t
    arith_ret = np.zeros(n)
    arith_ret[1:] = px[1:] / px[:-1] - 1.0
    strat_ret = np.zeros(n)
    strat_ret[1:] = weights[:-1] * arith_ret[1:]

    # Apply costs on weight changes (per-side ~ cost/2 bps; round-trip on |dw|)
    cost_bps = COSTS_BPS.get(symbol, DEFAULT_COST_BPS)
    cost_frac = cost_bps / 10000.0
    dw = np.diff(weights, prepend=0.0)
    cost_drag = np.abs(dw) * cost_frac
    strat_ret = strat_ret - cost_drag

    # Trade count = number of weight changes that cross zero or are large
    trade_count = int((np.abs(dw) > 0.01).sum())

    return InstrumentRun(
        symbol=symbol,
        dates=np.array(rebal_idx),
        weights=np.array(rebal_w),
        daily_returns=strat_ret,
        daily_dates=close.index,
        trade_count=trade_count,
    )


# ---------- portfolio aggregation ----------

@dataclass
class PortfolioResult:
    name: str
    daily_returns: pd.Series
    trade_count: int
    per_instrument_sharpe: dict[str, float]


def run_portfolio(gate_mode: str) -> PortfolioResult:
    """Equal-weight across the universe, ignoring instruments with no data."""
    runs: list[InstrumentRun] = []
    for sym in UNIVERSE:
        r = backtest_instrument(sym, gate_mode=gate_mode)
        if r.daily_returns.size > 0:
            runs.append(r)

    # Align all daily-return series on a common DatetimeIndex
    series = []
    for r in runs:
        s = pd.Series(r.daily_returns, index=r.daily_dates, name=r.symbol)
        series.append(s)
    df = pd.concat(series, axis=1).sort_index()
    df = df.loc[START_DATE:END_DATE].fillna(0.0)

    # Equal-weight portfolio: 1/N over instruments with data on that date
    n_active = (df != 0).any(axis=0).sum()
    port_ret = df.mean(axis=1)  # equal-weight; weights already sum to <= N
    port_ret = port_ret * (1.0 / 1.0)  # 1/N normalisation embedded via mean()

    # Wait — df.mean() divides by N every day even when some are zero.
    # That underweights vs an equal-weight allocator. Use sum / N_universe so
    # the strategy capital usage reflects the true cross-section size.
    port_ret = df.sum(axis=1) / len(UNIVERSE)

    per_inst_sharpe = {}
    for r in runs:
        s = pd.Series(r.daily_returns, index=r.daily_dates).loc[START_DATE:END_DATE]
        mu = s.mean()
        sd = s.std(ddof=0)
        per_inst_sharpe[r.symbol] = float(mu / sd * np.sqrt(252.0)) if sd > 0 else float("nan")

    total_trades = sum(r.trade_count for r in runs)
    return PortfolioResult(
        name=gate_mode,
        daily_returns=port_ret,
        trade_count=total_trades,
        per_instrument_sharpe=per_inst_sharpe,
    )


# ---------- reporting ----------

def sharpe(returns: pd.Series) -> float:
    r = returns.dropna()
    r = r[r != 0]
    if r.size < 30:
        return float("nan")
    mu = r.mean()
    sd = r.std(ddof=0)
    return float(mu / sd * np.sqrt(252.0)) if sd > 0 else float("nan")


def max_drawdown(returns: pd.Series) -> float:
    equity = (1.0 + returns.fillna(0.0)).cumprod()
    peak = equity.cummax()
    dd = (equity / peak - 1.0).min()
    return float(dd)


def annual_return(returns: pd.Series) -> float:
    r = returns.dropna()
    if r.size < 10:
        return float("nan")
    total = (1.0 + r).prod() - 1.0
    years = r.size / 252.0
    return float((1.0 + total) ** (1.0 / years) - 1.0) if years > 0 else float("nan")


def section(t: str) -> None:
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def report(result: PortfolioResult) -> dict:
    full = result.daily_returns
    pre  = full.loc[:W4_SPLIT - pd.Timedelta(days=1)]
    post = full.loc[W4_SPLIT:]

    out = dict(
        name=result.name,
        full_sh=sharpe(full),
        pre_sh=sharpe(pre),
        post_sh=sharpe(post),
        full_mdd=max_drawdown(full),
        full_cagr=annual_return(full),
        trades=result.trade_count,
    )
    return out


def print_summary(rows: list[dict]) -> None:
    head = "{:<12s}  {:>8s}  {:>8s}  {:>8s}  {:>8s}  {:>8s}  {:>8s}"
    print(head.format("config", "full Sh", "pre Sh", "W4 Sh", "MDD%", "CAGR%", "trades"))
    for r in rows:
        print(head.format(
            r["name"][:12],
            f"{r['full_sh']:+.2f}",
            f"{r['pre_sh']:+.2f}",
            f"{r['post_sh']:+.2f}",
            f"{r['full_mdd']*100:+.1f}",
            f"{r['full_cagr']*100:+.1f}",
            f"{r['trades']:d}",
        ))


def main() -> None:
    section("TSMOM HURST-GATED -- Phase 2")
    print(f"Universe: {len(UNIVERSE)} instruments, D1, {START_DATE.date()} -> {END_DATE.date()}")
    print(f"Signal:   12-1 long-only, monthly rebal, vol-target {VOL_TARGET}, cap {SIZE_CAP}")
    print(f"Gate:     H_t > {H_GATE_THRESH} on rolling 252d DFA Hurst")
    print(f"W4 split: {W4_SPLIT.date()}")
    print(f"Pre-commits: W4 lift >= +0.15, trades >= 200, corr_gated_vs_ungated <= 0.85, W4 Sh > 0, MDD > -25%")

    section("RUNNING three configurations")
    print("\n[1/3] UNGATED baseline ...")
    base = run_portfolio("none")
    print("[2/3] GATED (H > 0.50) ...")
    gated = run_portfolio("gated")
    print("[3/3] INVERTED gate null-check (H < 0.50) ...")
    inv = run_portfolio("inverted")

    section("PORTFOLIO HEADLINE")
    rows = [report(base), report(gated), report(inv)]
    print()
    print_summary(rows)

    section("CORRELATIONS")
    df = pd.concat([base.daily_returns.rename("ungated"),
                     gated.daily_returns.rename("gated"),
                     inv.daily_returns.rename("inverted")], axis=1).fillna(0.0)
    corr = df.corr()
    print()
    print(corr.round(3).to_string())

    section("PER-INSTRUMENT SHARPE (full sample)")
    head = "{:<8s}  {:>8s}  {:>8s}  {:>8s}  {:>8s}"
    print(head.format("instr", "ungated", "gated", "inverted", "lift"))
    for sym in UNIVERSE:
        u = base.per_instrument_sharpe.get(sym, float("nan"))
        g = gated.per_instrument_sharpe.get(sym, float("nan"))
        i = inv.per_instrument_sharpe.get(sym, float("nan"))
        lift = g - u if (np.isfinite(g) and np.isfinite(u)) else float("nan")
        print(head.format(sym,
                          f"{u:+.2f}" if np.isfinite(u) else "  nan ",
                          f"{g:+.2f}" if np.isfinite(g) else "  nan ",
                          f"{i:+.2f}" if np.isfinite(i) else "  nan ",
                          f"{lift:+.2f}" if np.isfinite(lift) else "  nan "))

    section("PRE-COMMITTED VERDICT")
    base_w4 = rows[0]["post_sh"]
    gated_w4 = rows[1]["post_sh"]
    inv_w4 = rows[2]["post_sh"]
    w4_lift = gated_w4 - base_w4
    corr_g_u = float(corr.loc["gated", "ungated"])
    trades = rows[1]["trades"]
    mdd_full = rows[1]["full_mdd"]

    def chk(cond: bool, label: str, val: str) -> str:
        return f"  [{'PASS' if cond else 'FAIL'}] {label}: {val}"

    c1 = w4_lift >= 0.15
    c2 = trades >= 200
    c3 = corr_g_u <= 0.85
    c4 = gated_w4 > 0
    c5 = mdd_full > -0.25
    c_null = not (np.isfinite(inv_w4) and inv_w4 > gated_w4 - 0.10)
    print()
    print(chk(c1, "W4 Sharpe lift >= +0.15", f"{w4_lift:+.2f}"))
    print(chk(c2, "Trades >= 200",            f"{trades:d}"))
    print(chk(c3, "corr(gated, ungated) <= 0.85", f"{corr_g_u:.3f}"))
    print(chk(c4, "W4 Sharpe > 0",            f"{gated_w4:+.2f}"))
    print(chk(c5, "Full-sample MDD > -25%",   f"{mdd_full*100:+.1f}%"))
    print(chk(c_null, "Null-check: inverted W4 not within 0.10 of gated", f"inv={inv_w4:+.2f} gated={gated_w4:+.2f}"))

    all_pass = all([c1, c2, c3, c4, c5, c_null])
    print()
    if all_pass:
        print("FINAL VERDICT: PASS -- proceed to Phase 3 (walk-forward + statistical validation)")
    elif c1 and c4 and c5 and (not c3) and corr_g_u < 0.90:
        print("FINAL VERDICT: MARGINAL -- gate works directionally but too close to baseline")
    else:
        print("FINAL VERDICT: REJECT -- Hurst-overlay family tombstoned (per pre-commit)")
    print()


if __name__ == "__main__":
    main()
