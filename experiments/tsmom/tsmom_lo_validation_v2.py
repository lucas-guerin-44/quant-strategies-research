#!/usr/bin/env python3
"""TSMOM long-only robustness validation - V2 (post-bugfix).

Context
-------
The original ``tsmom_lo_validation.py`` reported baseline full-period stats
of +40.71% / Sharpe 0.3627 / -11.30% DD / 0 trades. The ZERO trade count
was the tell: ``TimeSeriesMomentumStrategy.manage_position`` returned early
when ``self._current_signal == 0``, so in long-only mode positions never
closed on a signal-flip-to-neutral. The "winner" numbers were really just
a never-rebalancing basket.

The fix (now in ``strategies/tsmom.py``): ``manage_position`` closes the
trade whenever ``self._current_signal != trade.side`` - i.e. a flip OR a
flat-out neutral (0) signal, which matters in long-only mode where the
strategy can only be +1 or 0.

This V2 script re-runs the exact same three tests (regime stability,
parameter sensitivity, true holdout) against the fixed strategy and makes
the comparison to the old (buggy) numbers explicit in the final verdict.
"""

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

from backtesting.allocation import EqualWeightAllocator
from backtesting.portfolio_backtest import PortfolioBacktester, RiskLimits
from backtesting.statistics import compute_sharpe
from tsmom_strategy import TimeSeriesMomentumStrategy

from tsmom_demo import (
    UNIVERSE,
    COSTS_BY_SYMBOL,
    DEFAULT_COSTS,
    STARTING_CASH,
    load_data,
)


# ---------------------------------------------------------------------------
# Baseline configuration (locked) - identical to tsmom_variants_demo long-only
# ---------------------------------------------------------------------------

BASE_PARAMS = dict(
    lookback_bars=252,
    skip_bars=21,
    rebalance_bars=21,
    vol_lookback=60,
    vol_target_annual=0.15,
    long_only=True,
    min_abs_return=0.0,
    size_cap_fraction=1.0,
)

# Full period: 2015-01-01 -> 2026-04-18 (today at task-authoring time)
FULL_START = pd.Timestamp("2015-01-01", tz="UTC")
FULL_END = pd.Timestamp("2026-04-18", tz="UTC")

# ~1 year of trading days for signal warmup (lookback_bars = 252)
WARMUP_BARS = 260  # a touch over 252 to be safe

# Old (buggy) baseline numbers - hard-coded for the final comparison block.
OLD_BUGGY_BASELINE = {
    "return_pct": 40.71,
    "sharpe": 0.3627,
    "max_dd_pct": 11.30,
    "trades": 0,
}

# Equal-weight portfolio risk limits (identical to tsmom_demo)
LIMITS = RiskLimits(
    max_gross_exposure=1.2,
    max_net_exposure=1.0,
    max_single_asset=0.20,
    max_open_positions=len(UNIVERSE),
)


def section(title: str) -> None:
    print(f"\n{'=' * 80}\n  {title}\n{'=' * 80}\n")


def costs_dict(symbols):
    return {
        sym: {
            "commission_bps": COSTS_BY_SYMBOL.get(sym, DEFAULT_COSTS)[0],
            "slippage_bps": COSTS_BY_SYMBOL.get(sym, DEFAULT_COSTS)[1],
        }
        for sym in symbols
    }


def slice_with_warmup(
    df: pd.DataFrame,
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
    warmup_bars: int = WARMUP_BARS,
):
    """Return a slice covering (test_start - warmup_bars) .. test_end,
    plus the integer index inside the slice where the test window begins.
    """
    upto_end = df.loc[df.index <= test_end]
    if upto_end.empty:
        return None, 0

    before_test = upto_end.loc[upto_end.index < test_start]
    test_bars = upto_end.loc[upto_end.index >= test_start]
    if test_bars.empty:
        return None, 0

    warmup_available = min(warmup_bars, len(before_test))
    warmup_slice = before_test.tail(warmup_available) if warmup_available else before_test.iloc[0:0]
    window = pd.concat([warmup_slice, test_bars])
    test_start_idx = len(warmup_slice)
    return window, test_start_idx


def window_stats(
    equity_curve: np.ndarray,
    test_start_idx: int,
    trades: list,
    timestamps,
    test_start: pd.Timestamp,
):
    """Compute return / Sharpe / max DD / trade count on the test portion."""
    eq = np.asarray(equity_curve, dtype=np.float64)
    n = len(eq)
    if test_start_idx >= n:
        return None

    test_eq = eq[test_start_idx:]
    if len(test_eq) < 2 or test_eq[0] <= 0:
        return None

    rebased = test_eq * (STARTING_CASH / test_eq[0])

    peak = np.maximum.accumulate(rebased)
    dd = np.where(peak > 0, (peak - rebased) / peak, 0.0)
    max_dd = float(dd.max())

    total_ret = (rebased[-1] - STARTING_CASH) / STARTING_CASH * 100
    sharpe = compute_sharpe(rebased)

    test_trades = 0
    for tr in trades:
        entry_ts = getattr(tr.entry_bar, "timestamp", None)
        if entry_ts is not None and entry_ts >= test_start:
            test_trades += 1

    return {
        "return_pct": total_ret,
        "sharpe": sharpe,
        "max_dd_pct": max_dd * 100,
        "trades": test_trades,
    }


def run_equal_weight_portfolio(
    dataframes: dict,
    params: dict,
    symbols: list,
):
    """Run the equal-weight multi-asset TSMOM portfolio.  Returns (result, bt)."""
    strats = {sym: TimeSeriesMomentumStrategy(**params) for sym in symbols}
    pbt = PortfolioBacktester(
        dataframes=dataframes,
        strategies=strats,
        allocator=EqualWeightAllocator(),
        starting_cash=STARTING_CASH,
        commission_bps=DEFAULT_COSTS[0],
        slippage_bps=DEFAULT_COSTS[1],
        rebalance_frequency=21,
        vol_lookback=500,
        risk_limits=LIMITS,
        costs_by_symbol=costs_dict(symbols),
    )
    return pbt.run(), pbt


def portfolio_stats(result, max_dd: float):
    """Compute full-period stats from a portfolio backtest result."""
    eq = result.equity_curve
    if len(eq) < 2 or eq[0] <= 0:
        return {"return_pct": 0.0, "sharpe": 0.0, "max_dd_pct": 0.0, "trades": 0}
    ret = (eq[-1] - eq[0]) / eq[0] * 100
    sharpe = compute_sharpe(eq)
    return {
        "return_pct": ret,
        "sharpe": sharpe,
        "max_dd_pct": max_dd * 100,
        "trades": len(result.trades),
    }


# ---------------------------------------------------------------------------
# Test 1: Regime stability
# ---------------------------------------------------------------------------

def test_regime_stability(full_frames: dict, symbols: list):
    section("Test 1 - Regime stability (4 non-overlapping windows)")

    print("Approach: prepend ~260 bars (~1 year) of prior history to each")
    print("test window so the 252-bar lookback is armed at window start.")
    print("Stats are computed on the TEST PORTION of the equity curve only")
    print("(rebased to starting_cash at test_start), not on the warmup.\n")

    boundaries = [
        pd.Timestamp("2015-01-01", tz="UTC"),
        pd.Timestamp("2017-10-01", tz="UTC"),
        pd.Timestamp("2020-07-01", tz="UTC"),
        pd.Timestamp("2023-04-01", tz="UTC"),
        pd.Timestamp("2026-04-18", tz="UTC"),
    ]

    header = f"  {'Window':<24s} {'Return':>10s} {'Sharpe':>8s} {'Max DD':>9s} {'Trades':>7s}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    window_results = []
    for k in range(4):
        test_start = boundaries[k]
        test_end = boundaries[k + 1]

        sliced: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            sl, _idx = slice_with_warmup(full_frames[sym], test_start, test_end)
            if sl is None or len(sl) < 50:
                continue
            sliced[sym] = sl

        if len(sliced) < 3:
            print(f"  {test_start.date()}..{test_end.date()}  (insufficient data)")
            continue

        active_syms = sorted(sliced.keys())
        strats = {sym: TimeSeriesMomentumStrategy(**BASE_PARAMS) for sym in active_syms}
        pbt = PortfolioBacktester(
            dataframes=sliced,
            strategies=strats,
            allocator=EqualWeightAllocator(),
            starting_cash=STARTING_CASH,
            commission_bps=DEFAULT_COSTS[0],
            slippage_bps=DEFAULT_COSTS[1],
            rebalance_frequency=21,
            vol_lookback=500,
            risk_limits=LIMITS,
            costs_by_symbol=costs_dict(active_syms),
        )
        result = pbt.run()

        ts = result.timestamps
        test_start_idx = 0
        for i, t in enumerate(ts):
            if t >= test_start:
                test_start_idx = i
                break

        stats = window_stats(
            result.equity_curve, test_start_idx, result.trades, ts, test_start,
        )
        if stats is None:
            print(f"  {test_start.date()}..{test_end.date()}  (equity degenerate)")
            continue

        window_results.append({
            "start": test_start.date(),
            "end": test_end.date(),
            **stats,
        })

        label = f"{test_start.date()}..{test_end.date()}"
        print(f"  {label:<24s} {stats['return_pct']:>+9.2f}% "
              f"{stats['sharpe']:>8.4f} {stats['max_dd_pct']:>8.2f}% "
              f"{stats['trades']:>7d}")

    pos = sum(1 for w in window_results if w["sharpe"] > 0)
    total = len(window_results)
    verdict = (f"Sharpe positive in {pos}/{total} windows "
               f"({'stable' if pos == total else 'regime-dependent' if pos <= total // 2 else 'mixed'})")
    print(f"\n  {verdict}")

    return window_results, verdict, pos, total


# ---------------------------------------------------------------------------
# Test 2: Parameter sensitivity
# ---------------------------------------------------------------------------

def test_param_sensitivity(full_frames: dict, symbols: list):
    section("Test 2 - Parameter sensitivity (one-at-a-time sweeps)")

    sweeps = [
        ("lookback_bars", [126, 189, 252, 315, 378]),
        ("skip_bars", [0, 10, 21, 42]),
        ("rebalance_bars", [10, 21, 42, 63]),
        ("vol_target_annual", [0.10, 0.15, 0.20, 0.25]),
    ]

    all_results: dict[str, list] = {}

    for param_name, values in sweeps:
        print(f"  Sweep: {param_name}  (baseline = {BASE_PARAMS[param_name]})")
        print(f"  {'value':>10s} {'Return':>10s} {'Sharpe':>8s} {'Max DD':>9s} {'Trades':>7s}")
        print("  " + "-" * 50)

        results = []
        for v in values:
            params = dict(BASE_PARAMS)
            params[param_name] = v
            result, pbt = run_equal_weight_portfolio(full_frames, params, symbols)
            stats = portfolio_stats(result, pbt.max_drawdown)
            results.append({"value": v, **stats})
            marker = "  *baseline" if v == BASE_PARAMS[param_name] else ""
            print(f"  {str(v):>10s} {stats['return_pct']:>+9.2f}% "
                  f"{stats['sharpe']:>8.4f} {stats['max_dd_pct']:>8.2f}% "
                  f"{stats['trades']:>7d}{marker}")
        all_results[param_name] = results

        sharpes = [r["sharpe"] for r in results]
        spread = max(sharpes) - min(sharpes)
        all_pos = all(s > 0 for s in sharpes)
        print(f"  -> Sharpe range: [{min(sharpes):+.4f}, {max(sharpes):+.4f}]  "
              f"spread {spread:.4f}  all_positive={all_pos}\n")

    robust_count = 0
    fragile_dims: list[str] = []
    total_params = len(sweeps)
    for name, _ in sweeps:
        sharpes = [r["sharpe"] for r in all_results[name]]
        if all(s > 0 for s in sharpes) and (max(sharpes) - min(sharpes)) < 0.5:
            robust_count += 1
        else:
            fragile_dims.append(name)

    if robust_count == total_params:
        verdict = f"Robust across all {total_params} param sweeps"
    elif robust_count >= total_params // 2:
        verdict = f"Mostly robust ({robust_count}/{total_params} sweeps)"
    else:
        verdict = f"Fragile ({robust_count}/{total_params} sweeps robust)"
    print(f"  {verdict}")

    return all_results, verdict, fragile_dims


# ---------------------------------------------------------------------------
# Test 3: True holdout
# ---------------------------------------------------------------------------

def test_holdout(full_frames: dict, symbols: list):
    section("Test 3 - True holdout (IS 2015-2022, OOS 2023-2026-04-18)")

    is_end = pd.Timestamp("2022-12-31", tz="UTC")
    oos_start = pd.Timestamp("2023-01-01", tz="UTC")

    is_frames: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = full_frames[sym]
        is_slice = df.loc[(df.index >= FULL_START) & (df.index <= is_end)]
        if len(is_slice) > 50:
            is_frames[sym] = is_slice

    is_syms = sorted(is_frames.keys())
    is_result, is_bt = run_equal_weight_portfolio(is_frames, BASE_PARAMS, is_syms)
    is_stats = portfolio_stats(is_result, is_bt.max_drawdown)

    oos_frames: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        sl, _idx = slice_with_warmup(full_frames[sym], oos_start, FULL_END)
        if sl is not None and len(sl) > 50:
            oos_frames[sym] = sl

    oos_syms = sorted(oos_frames.keys())
    strats = {sym: TimeSeriesMomentumStrategy(**BASE_PARAMS) for sym in oos_syms}
    oos_pbt = PortfolioBacktester(
        dataframes=oos_frames,
        strategies=strats,
        allocator=EqualWeightAllocator(),
        starting_cash=STARTING_CASH,
        commission_bps=DEFAULT_COSTS[0],
        slippage_bps=DEFAULT_COSTS[1],
        rebalance_frequency=21,
        vol_lookback=500,
        risk_limits=LIMITS,
        costs_by_symbol=costs_dict(oos_syms),
    )
    oos_result = oos_pbt.run()

    ts = oos_result.timestamps
    oos_test_idx = 0
    for i, t in enumerate(ts):
        if t >= oos_start:
            oos_test_idx = i
            break

    oos_stats = window_stats(
        oos_result.equity_curve, oos_test_idx, oos_result.trades, ts, oos_start,
    )

    print(f"  {'Period':<22s} {'Return':>10s} {'Sharpe':>8s} {'Max DD':>9s} {'Trades':>7s}")
    print("  " + "-" * 60)
    print(f"  {'IS (2015-01..2022-12)':<22s} {is_stats['return_pct']:>+9.2f}% "
          f"{is_stats['sharpe']:>8.4f} {is_stats['max_dd_pct']:>8.2f}% "
          f"{is_stats['trades']:>7d}")
    print(f"  {'OOS (2023-01..today)':<22s} {oos_stats['return_pct']:>+9.2f}% "
          f"{oos_stats['sharpe']:>8.4f} {oos_stats['max_dd_pct']:>8.2f}% "
          f"{oos_stats['trades']:>7d}")

    degradation = is_stats["sharpe"] - oos_stats["sharpe"]
    if degradation < 0.2:
        verdict_tag = "robust"
    elif degradation < 0.5:
        verdict_tag = "some overfitting"
    else:
        verdict_tag = "heavily overfit"
    print(f"\n  Degradation (IS Sharpe - OOS Sharpe): {degradation:+.4f}  ({verdict_tag})")

    return is_stats, oos_stats, degradation, verdict_tag


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    section("TSMOM long-only validation V2 (POST-BUGFIX) - loading data")
    full_frames: dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        df = load_data(sym)
        if df is None or len(df) < 400:
            if df is not None:
                print(f"  {sym:<8s}  skipped ({len(df)} bars - need >= 400)")
            continue
        df = df.loc[(df.index >= FULL_START) & (df.index <= FULL_END)]
        if len(df) < 400:
            print(f"  {sym:<8s}  skipped (only {len(df)} bars in validation period)")
            continue
        full_frames[sym] = df
        print(f"  {sym:<8s}  {len(df):>5,} bars  "
              f"{df.index[0].date()} -> {df.index[-1].date()}")

    if len(full_frames) < 3:
        print("Need at least 3 instruments with enough history.")
        sys.exit(1)

    symbols = sorted(full_frames.keys())
    print(f"\n  {len(symbols)} instruments loaded")

    # ---- Reference full-period baseline ---------------------------------
    section("Reference: full-period baseline (equal-weight, 2015-2026, FIXED strategy)")
    full_result, full_bt = run_equal_weight_portfolio(full_frames, BASE_PARAMS, symbols)
    full_stats = portfolio_stats(full_result, full_bt.max_drawdown)
    print(f"  Return: {full_stats['return_pct']:+.2f}%   "
          f"Sharpe: {full_stats['sharpe']:.4f}   "
          f"Max DD: {full_stats['max_dd_pct']:.2f}%   "
          f"Trades: {full_stats['trades']}")

    # ---- SANITY CHECK: trade count must be > 0 --------------------------
    if full_stats["trades"] == 0:
        print("\n  ****  SANITY CHECK FAILED  ****")
        print("  Trade count is still 0 after the fix. Either the fix did not")
        print("  land in strategies/tsmom.py, or there is another blocking bug.")
        print("  STOPPING - no further tests will run.")
        sys.exit(2)
    else:
        print(f"\n  SANITY CHECK OK: {full_stats['trades']} trades recorded "
              f"(was 0 in the buggy run).")

    # ---- Tests ----------------------------------------------------------
    window_results, regime_verdict, regime_pos, regime_total = test_regime_stability(
        full_frames, symbols,
    )
    sensitivity_results, param_verdict, fragile_dims = test_param_sensitivity(
        full_frames, symbols,
    )
    is_stats, oos_stats, degradation, holdout_tag = test_holdout(full_frames, symbols)

    # ---- Final verdict --------------------------------------------------
    section("VERDICT")

    old = OLD_BUGGY_BASELINE
    print(f"Old (buggy) baseline:   Return {old['return_pct']:+.2f}%  "
          f"Sharpe {old['sharpe']:.4f}  DD -{old['max_dd_pct']:.2f}%  "
          f"Trades {old['trades']}")
    print(f"Fixed baseline:         Return {full_stats['return_pct']:+.2f}%  "
          f"Sharpe {full_stats['sharpe']:.4f}  DD -{full_stats['max_dd_pct']:.2f}%  "
          f"Trades {full_stats['trades']}")

    # Classify the delta
    ret_f = full_stats["return_pct"]
    shp_f = full_stats["sharpe"]
    if shp_f < 0.10 or ret_f < 5.0:
        delta_tag = ("ARTEFACT - the old +40.71%/Sharpe 0.36 was spurious. "
                     "Once the strategy actually closes positions, the edge collapses.")
    elif shp_f >= 0.30 or ret_f >= 20.0:
        delta_tag = ("REAL EDGE - fixed baseline is roughly in line with the old numbers, "
                     "so the edge was not an artefact of the no-exit bug.")
    else:
        delta_tag = ("PARTIAL EDGE - fixed baseline shows a degraded but non-trivial "
                     "signal; the old numbers were inflated but not pure noise.")
    print(f"Delta:                  {delta_tag}")

    print()
    print(f"Regime stability:       Sharpe positive in {regime_pos}/{regime_total} windows")
    if fragile_dims:
        print(f"Param sensitivity:      {param_verdict} "
              f"(fragile on: {', '.join(fragile_dims)})")
    else:
        print(f"Param sensitivity:      {param_verdict}")
    print(f"Holdout:                IS Sharpe {is_stats['sharpe']:.2f}, "
          f"OOS Sharpe {oos_stats['sharpe']:.2f}, "
          f"degradation {degradation:+.2f}")

    regime_ok = window_results and (regime_pos >= 3)
    param_ok = param_verdict.startswith("Robust") or param_verdict.startswith("Mostly")
    holdout_ok = degradation < 0.5
    edge_ok = shp_f >= 0.10 and ret_f >= 5.0

    if edge_ok and regime_ok and param_ok and holdout_ok and degradation < 0.2:
        overall = "KEEP"
    elif edge_ok and regime_ok and param_ok and holdout_ok:
        overall = "KEEP (with mild OOS degradation)"
    elif edge_ok and (regime_ok + param_ok + holdout_ok) >= 2:
        overall = "INVESTIGATE"
    else:
        overall = "REJECT"

    print(f"Overall:                {overall}")
    print("\nDone.")


if __name__ == "__main__":
    main()
