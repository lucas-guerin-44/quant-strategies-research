#!/usr/bin/env python3
"""
Blended portfolio demo: TSMOM long-only + XS-mom long-only (IS-optimal).

Runs each validated strategy independently on the same 24-instrument universe,
same period, same $100K starting capital, then blends the resulting equity
curves post-hoc at several fixed weightings (50/50, 60/40, 40/60, risk-parity
by inverse realized vol).

For each configuration we report:
  - Total return, annualized Sharpe (252 bpy), max drawdown, Calmar ratio
  - Pearson correlation of daily returns between the two strategies
  - Rolling 252-day Sharpe summary (min/max/% time > 0) for individual
    strategies and the 50/50 blend

This helps decide whether diversification is genuine (blend Sharpe > both)
or whether the two momentum strategies are essentially the same bet.

No lookahead is introduced by the blend: each component is computed from its
own no-lookahead equity path; we only combine the resulting dollar curves.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)  # research repo root
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))  # engine
sys.path.insert(0, _HERE)  # this strategy's directory
sys.path.insert(0, os.path.join(_EXPERIMENTS, 'tsmom'))      # for TimeSeriesMomentumStrategy
sys.path.insert(0, os.path.join(_EXPERIMENTS, 'xs_momentum'))  # for XS-mom validation helpers

from backtesting.allocation import EqualWeightAllocator
from backtesting.portfolio_backtest import PortfolioBacktester, RiskLimits
from tsmom_strategy import TimeSeriesMomentumStrategy

from tsmom_demo import UNIVERSE as TSMOM_UNIVERSE, COSTS_BY_SYMBOL as TSMOM_COSTS
from xs_momentum_validation import (
    BARS_PER_YEAR,
    COSTS_BY_SYMBOL as XSMOM_COSTS,
    load_data,
    run_xs_momentum,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

START_DATE = "2015-01-01"
END_DATE = "2026-04-18"
STARTING_CASH = 100_000.0
DEFAULT_COSTS = (4.0, 2.0)  # matches both demos' fallback

# TSMOM long-only baseline params (validated: +44.19% / 0.39 / -15.53% DD).
TSMOM_PARAMS = dict(
    lookback_bars=252,
    skip_bars=21,
    rebalance_bars=21,
    vol_lookback=60,
    vol_target_annual=0.15,
    long_only=True,
    min_abs_return=0.0,
    size_cap_fraction=1.0,
)

# XS-mom IS-optimal params (validated: +259.75% / 0.92 / -23.12% DD).
XSMOM_PARAMS = dict(
    lookback_bars=189,
    skip_bars=42,
    rebalance_bars=63,
    top_k=5,
    bottom_k=0,
)


def section(title: str) -> None:
    print(f"\n{'=' * 80}\n  {title}\n{'=' * 80}\n")


# ---------------------------------------------------------------------------
# Metrics (pct-return based, matching xs_momentum_validation.py convention)
# ---------------------------------------------------------------------------

def pct_returns(equity: np.ndarray) -> np.ndarray:
    """Simple daily returns from an equity array. Leading bar -> 0."""
    eq = np.asarray(equity, dtype=float)
    rets = np.zeros_like(eq)
    if len(eq) < 2:
        return rets
    prev = eq[:-1]
    valid = prev > 1e-8
    diff = np.diff(eq)
    rets[1:][valid] = diff[valid] / prev[valid]
    return rets


def total_return(equity: np.ndarray) -> float:
    if len(equity) < 2 or equity[0] <= 0:
        return 0.0
    return float(equity[-1] / equity[0] - 1.0)


def ann_sharpe(daily_returns: np.ndarray) -> float:
    """Annualized Sharpe; trims leading zero-return bars (pre-rebalance)."""
    r = np.asarray(daily_returns, dtype=float)
    nz = np.flatnonzero(r)
    if nz.size == 0:
        return 0.0
    r = r[nz[0]:]
    sd = r.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(r.mean() / sd * np.sqrt(BARS_PER_YEAR))


def max_drawdown(equity: np.ndarray) -> float:
    eq = np.asarray(equity, dtype=float)
    running_max = np.maximum.accumulate(eq)
    dd = (eq - running_max) / running_max
    return float(dd.min())


def annualized_return(equity: np.ndarray, n_bars: int) -> float:
    if n_bars <= 1 or equity[0] <= 0:
        return 0.0
    years = n_bars / BARS_PER_YEAR
    if years <= 0:
        return 0.0
    return float((equity[-1] / equity[0]) ** (1.0 / years) - 1.0)


def calmar(equity: np.ndarray, n_bars: int) -> float:
    mdd = max_drawdown(equity)
    if mdd >= 0:
        return float("inf")
    ann_ret = annualized_return(equity, n_bars)
    return float(ann_ret / abs(mdd))


def rolling_sharpe(daily_returns: np.ndarray, window: int = 252) -> np.ndarray:
    """Rolling annualized Sharpe over ``window`` bars. NaN where insufficient."""
    r = np.asarray(daily_returns, dtype=float)
    out = np.full(r.shape, np.nan)
    if len(r) < window:
        return out
    s = pd.Series(r)
    mean = s.rolling(window).mean()
    std = s.rolling(window).std(ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = (mean / std) * np.sqrt(BARS_PER_YEAR)
    return rs.to_numpy()


# ---------------------------------------------------------------------------
# Component runners
# ---------------------------------------------------------------------------

def run_tsmom(dataframes: dict[str, pd.DataFrame]) -> tuple[np.ndarray, pd.DatetimeIndex]:
    """TSMOM long-only via the event-driven PortfolioBacktester harness
    (matches examples/tsmom_demo.py: equal-weight, per-symbol costs, same
    RiskLimits)."""
    symbols = sorted(dataframes.keys())

    costs_bps = {
        sym: {
            "commission_bps": TSMOM_COSTS.get(sym, DEFAULT_COSTS)[0],
            "slippage_bps":   TSMOM_COSTS.get(sym, DEFAULT_COSTS)[1],
        }
        for sym in symbols
    }

    limits = RiskLimits(
        max_gross_exposure=1.2,
        max_net_exposure=1.0,
        max_single_asset=0.20,
        max_open_positions=len(symbols),
    )

    strats = {sym: TimeSeriesMomentumStrategy(**TSMOM_PARAMS) for sym in symbols}
    pbt = PortfolioBacktester(
        dataframes=dataframes,
        strategies=strats,
        allocator=EqualWeightAllocator(),
        starting_cash=STARTING_CASH,
        commission_bps=DEFAULT_COSTS[0],
        slippage_bps=DEFAULT_COSTS[1],
        rebalance_frequency=21,
        vol_lookback=500,
        risk_limits=limits,
        costs_by_symbol=costs_bps,
    )
    result = pbt.run()
    eq = np.asarray(result.equity_curve, dtype=float)
    idx = pd.DatetimeIndex(result.timestamps)
    # Ensure timezone-aware UTC for clean alignment with the XS-mom B-day index.
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    return eq, idx


def run_xsmom(dataframes: dict[str, pd.DataFrame]) -> tuple[np.ndarray, pd.DatetimeIndex]:
    """XS-mom long-only at IS-optimal params, via the validated pandas/numpy
    simulator (same per-symbol costs)."""
    res = run_xs_momentum(
        dataframes,
        start_date=START_DATE,
        end_date=END_DATE,
        starting_cash=STARTING_CASH,
        costs_bps=XSMOM_COSTS,
        **XSMOM_PARAMS,
    )
    eq = np.asarray(res["equity_curve"], dtype=float)
    idx = pd.DatetimeIndex(res["index"])
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    return eq, idx


# ---------------------------------------------------------------------------
# Alignment + blending
# ---------------------------------------------------------------------------

def align_curves(
    tsmom_eq: np.ndarray, tsmom_idx: pd.DatetimeIndex,
    xsmom_eq: np.ndarray, xsmom_idx: pd.DatetimeIndex,
) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    """Union indices, forward-fill, trim to overlap, re-normalize to $100K."""
    s_ts = pd.Series(tsmom_eq, index=tsmom_idx)
    s_xs = pd.Series(xsmom_eq, index=xsmom_idx)

    common = s_ts.index.union(s_xs.index).sort_values()
    s_ts = s_ts.reindex(common).ffill()
    s_xs = s_xs.reindex(common).ffill()

    # Trim leading bars where either curve is still NaN (before strategy start).
    first_valid = max(s_ts.first_valid_index(), s_xs.first_valid_index())
    s_ts = s_ts.loc[first_valid:]
    s_xs = s_xs.loc[first_valid:]

    # Re-normalize both so they start at $100K on the first aligned date.
    ts_norm = s_ts.to_numpy() / s_ts.iloc[0] * STARTING_CASH
    xs_norm = s_xs.to_numpy() / s_xs.iloc[0] * STARTING_CASH
    return s_ts.index, ts_norm, xs_norm


def blend(weights: tuple[float, float],
          tsmom_eq: np.ndarray, xsmom_eq: np.ndarray) -> np.ndarray:
    w_t, w_x = weights
    return w_t * tsmom_eq + w_x * xsmom_eq


def inverse_vol_weights(ts_rets: np.ndarray, xs_rets: np.ndarray) -> tuple[float, float]:
    """Risk-parity-lite: weight by 1/stdev(daily returns), normalized.
    Single fixed weighting (no dynamic rebalancing) to keep it honest."""
    # Trim leading zeros (pre-signal bars) from each before measuring vol so
    # we don't artificially deflate the stdev.
    def trimmed_std(r: np.ndarray) -> float:
        nz = np.flatnonzero(r)
        if nz.size == 0:
            return 0.0
        return float(np.std(r[nz[0]:], ddof=1))

    v_t = trimmed_std(ts_rets)
    v_x = trimmed_std(xs_rets)
    if v_t <= 0 or v_x <= 0:
        return 0.5, 0.5
    inv_t = 1.0 / v_t
    inv_x = 1.0 / v_x
    s = inv_t + inv_x
    return inv_t / s, inv_x / s


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def summarize(name: str, equity: np.ndarray) -> dict:
    n = len(equity)
    ret = total_return(equity)
    rets = pct_returns(equity)
    sh = ann_sharpe(rets)
    mdd = max_drawdown(equity)
    cal = calmar(equity, n)
    return {
        "name": name,
        "return": ret,
        "sharpe": sh,
        "max_dd": mdd,
        "calmar": cal,
        "daily_returns": rets,
        "equity": equity,
    }


def rolling_summary(name: str, daily_returns: np.ndarray) -> dict:
    rs = rolling_sharpe(daily_returns, window=252)
    valid = rs[np.isfinite(rs)]
    if valid.size == 0:
        return {"name": name, "min": float("nan"), "max": float("nan"), "pct_pos": float("nan")}
    return {
        "name": name,
        "min": float(valid.min()),
        "max": float(valid.max()),
        "pct_pos": float((valid > 0).mean() * 100.0),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    section("Loading data (shared 24-instrument universe)")

    # Use TSMOM universe as source of truth (identical to XS-mom's).
    assert TSMOM_UNIVERSE == list(TSMOM_UNIVERSE), "universe sanity"

    dataframes: dict[str, pd.DataFrame] = {}
    for sym in TSMOM_UNIVERSE:
        df = load_data(sym, START_DATE, END_DATE)
        if df is None or len(df) < 400:
            if df is not None:
                print(f"  {sym:<8s}  skipped ({len(df)} bars -- need >= 400)")
            continue
        dataframes[sym] = df
        print(f"  {sym:<8s}  {len(df):>5,} bars  "
              f"{df.index[0].date()} -> {df.index[-1].date()}")
    print(f"\n  {len(dataframes)} instruments loaded")

    # ------------------------------------------------------------------
    section("Running TSMOM long-only (event-driven PortfolioBacktester)")
    # ------------------------------------------------------------------
    tsmom_eq_raw, tsmom_idx_raw = run_tsmom(dataframes)
    ret_t = total_return(tsmom_eq_raw) * 100
    print(f"  Bars: {len(tsmom_eq_raw)}   "
          f"Period: {tsmom_idx_raw[0].date()} -> {tsmom_idx_raw[-1].date()}")
    print(f"  Raw TSMOM total return: {ret_t:+.2f}%")

    # ------------------------------------------------------------------
    section("Running XS-mom long-only (IS-optimal, pandas simulator)")
    # ------------------------------------------------------------------
    xsmom_eq_raw, xsmom_idx_raw = run_xsmom(dataframes)
    ret_x = total_return(xsmom_eq_raw) * 100
    print(f"  Bars: {len(xsmom_eq_raw)}   "
          f"Period: {xsmom_idx_raw[0].date()} -> {xsmom_idx_raw[-1].date()}")
    print(f"  Raw XS-mom total return: {ret_x:+.2f}%")

    # ------------------------------------------------------------------
    section("Aligning equity curves onto a common daily index")
    # ------------------------------------------------------------------
    common_idx, ts_eq, xs_eq = align_curves(
        tsmom_eq_raw, tsmom_idx_raw, xsmom_eq_raw, xsmom_idx_raw,
    )
    print(f"  Aligned bars: {len(common_idx)}   "
          f"Period: {common_idx[0].date()} -> {common_idx[-1].date()}")
    print(f"  TSMOM renormalized start: ${ts_eq[0]:,.2f} -> ${ts_eq[-1]:,.2f}")
    print(f"  XSMOM renormalized start: ${xs_eq[0]:,.2f} -> ${xs_eq[-1]:,.2f}")

    # ------------------------------------------------------------------
    section("Computing blends")
    # ------------------------------------------------------------------

    ts_rets = pct_returns(ts_eq)
    xs_rets = pct_returns(xs_eq)

    # Correlation of daily returns (trim leading zero window common to both).
    nz = max(np.flatnonzero(ts_rets)[0] if np.any(ts_rets) else 0,
             np.flatnonzero(xs_rets)[0] if np.any(xs_rets) else 0)
    corr = float(np.corrcoef(ts_rets[nz:], xs_rets[nz:])[0, 1]) if len(ts_rets) > nz + 2 else float("nan")

    # Risk-parity-lite weights.
    rp_w = inverse_vol_weights(ts_rets, xs_rets)

    blends = {
        "TSMOM LO":       ts_eq,
        "XS-mom (IS)":    xs_eq,
        "50/50 blend":    blend((0.5, 0.5), ts_eq, xs_eq),
        "60/40 (TSMOM)":  blend((0.6, 0.4), ts_eq, xs_eq),
        "40/60 (XS-mom)": blend((0.4, 0.6), ts_eq, xs_eq),
        "Risk-parity":    blend(rp_w, ts_eq, xs_eq),
    }

    print(f"  Realized-vol weights (risk-parity-lite): "
          f"TSMOM={rp_w[0]:.3f}, XS-mom={rp_w[1]:.3f}")
    print(f"  Pearson corr(daily returns, TSMOM vs XS-mom): {corr:+.3f}")
    if corr < 0.3:
        corr_verdict = "genuine diversification"
    elif corr > 0.6:
        corr_verdict = "essentially the same bet (blending gains minimal)"
    else:
        corr_verdict = "moderate overlap (some diversification benefit)"
    print(f"  Interpretation: {corr_verdict}")

    # ------------------------------------------------------------------
    section("Rolling 1-year Sharpe (252-day window)")
    # ------------------------------------------------------------------
    roll_targets = [
        ("TSMOM LO",    pct_returns(ts_eq)),
        ("XS-mom (IS)", pct_returns(xs_eq)),
        ("50/50 blend", pct_returns(blends["50/50 blend"])),
    ]
    print(f"  {'Strategy':<14s} {'min':>8s} {'max':>8s} {'% > 0':>8s}")
    print("  " + "-" * 44)
    for name, rr in roll_targets:
        rs = rolling_summary(name, rr)
        print(f"  {rs['name']:<14s} {rs['min']:>+8.3f} {rs['max']:>+8.3f} "
              f"{rs['pct_pos']:>7.1f}%")

    # ------------------------------------------------------------------
    section("Final comparison table")
    # ------------------------------------------------------------------

    rows = [summarize(name, eq) for name, eq in blends.items()]

    print(f"  {'Strategy':<16s} {'Return':>9s} {'Sharpe':>8s} "
          f"{'Max DD':>9s} {'Calmar':>8s} {'Corr':>9s}")
    print("  " + "-" * 70)
    for r in rows:
        if r["name"] == "TSMOM LO":
            corr_col = "(base)"
        elif r["name"] == "XS-mom (IS)":
            corr_col = f"{corr:+.3f}"
        else:
            corr_col = "-"
        print(f"  {r['name']:<16s} "
              f"{r['return']*100:>+8.2f}% "
              f"{r['sharpe']:>+8.3f} "
              f"{r['max_dd']*100:>+8.2f}% "
              f"{r['calmar']:>+8.3f} "
              f"{corr_col:>9s}")

    # ------------------------------------------------------------------
    section("Interpretation")
    # ------------------------------------------------------------------

    ts_row = next(r for r in rows if r["name"] == "TSMOM LO")
    xs_row = next(r for r in rows if r["name"] == "XS-mom (IS)")
    blend_rows = [r for r in rows if r["name"] not in ("TSMOM LO", "XS-mom (IS)")]

    max_ind_sharpe = max(ts_row["sharpe"], xs_row["sharpe"])
    best_blend_by_sharpe = max(blend_rows, key=lambda r: r["sharpe"])
    best_by_calmar = max(rows, key=lambda r: r["calmar"])

    if best_blend_by_sharpe["sharpe"] > max_ind_sharpe + 1e-6:
        sharpe_verdict = (
            f"Diversification is WORKING: the {best_blend_by_sharpe['name']} "
            f"blend (Sharpe {best_blend_by_sharpe['sharpe']:.3f}) beats the "
            f"better of the two standalone strategies "
            f"(max individual Sharpe {max_ind_sharpe:.3f})."
        )
    elif corr > 0.6:
        sharpe_verdict = (
            f"The strategies are too correlated (rho={corr:+.2f}) for blending "
            f"to lift Sharpe meaningfully; blends just interpolate between the "
            f"two component Sharpes."
        )
    else:
        sharpe_verdict = (
            f"Blending does not raise Sharpe above the better standalone "
            f"strategy (max individual {max_ind_sharpe:.3f} vs best blend "
            f"{best_blend_by_sharpe['sharpe']:.3f}); the return/vol tradeoff is "
            f"dominated by one component."
        )

    print(sharpe_verdict)
    print()
    print(f"Best by Calmar (return per unit drawdown): "
          f"{best_by_calmar['name']} "
          f"(return {best_by_calmar['return']*100:+.2f}%, "
          f"DD {best_by_calmar['max_dd']*100:+.2f}%, "
          f"Calmar {best_by_calmar['calmar']:.3f}). "
          f"For a real retail portfolio this matters more than Sharpe -- "
          f"drawdown is what makes people quit the system, and a higher "
          f"return/DD ratio means fewer candidates for abandoning at the worst "
          f"possible moment.")

    print("\nDone.")


if __name__ == "__main__":
    main()
