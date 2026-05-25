#!/usr/bin/env python3
"""TSMOM variants comparison.

Runs three Time-Series Momentum configurations side by side on the same
24-instrument universe as :mod:`examples.tsmom_demo`:

  * Baseline    - long/short, no regime filter (TimeSeriesMomentumStrategy)
  * Long-only   - long/flat, no regime filter   (TimeSeriesMomentumStrategy)
  * Filtered    - long/short, 200-EMA regime filter (TrendFilteredTSMOMStrategy)

For each variant we run:
  1. Per-asset single backtests.
  2. A multi-asset portfolio backtest with EqualWeightAllocator and
     RiskParityAllocator.

At the end we print a one-line-per-variant comparison block (EqualWeight
portfolio) against the known baseline numbers from tsmom_demo.
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

from backtesting.allocation import EqualWeightAllocator, RiskParityAllocator
from backtesting.backtest import Backtester
from backtesting.portfolio_backtest import PortfolioBacktester, RiskLimits
from backtesting.statistics import compute_sharpe
from tsmom_strategy import TimeSeriesMomentumStrategy
from tsmom_filtered_strategy import TrendFilteredTSMOMStrategy

# Reuse the universe, costs, and data loader from tsmom_demo to guarantee
# apples-to-apples comparison with the published baseline numbers.
from tsmom_demo import (
    UNIVERSE,
    COSTS_BY_SYMBOL,
    DEFAULT_COSTS,
    STARTING_CASH,
    load_data,
    bnh_return,
)


# Variant definitions: (display_name, strategy_class, extra_kwargs)
VARIANTS = [
    ("Baseline",  TimeSeriesMomentumStrategy,  {"long_only": False}),
    ("Long-only", TimeSeriesMomentumStrategy,  {"long_only": True}),
    ("Filtered",  TrendFilteredTSMOMStrategy,  {"long_only": False,
                                                "trend_filter_period": 200}),
]


BASE_PARAMS = dict(
    lookback_bars=252,
    skip_bars=21,
    rebalance_bars=21,
    vol_lookback=60,
    vol_target_annual=0.15,
    min_abs_return=0.0,
    size_cap_fraction=1.0,
)


def section(title: str) -> None:
    print(f"\n{'=' * 80}\n  {title}\n{'=' * 80}\n")


def make_strategy(cls, extra_kwargs):
    """Build a strategy with BASE_PARAMS + variant-specific kwargs."""
    params = dict(BASE_PARAMS)
    params.update(extra_kwargs)
    return cls(**params)


def run_variant_per_asset(variant_name, cls, extra_kwargs, dataframes, symbols):
    """Run single-asset backtests for one variant. Returns list of metric dicts."""
    print(f"{'Instrument':<10s} {'Bars':>6s} {'TSMOM Ret':>10s} {'B&H Ret':>10s} "
          f"{'Max DD':>8s} {'Sharpe':>8s} {'Trades':>7s} {'Win %':>7s}")
    print("-" * 80)

    metrics = []
    for sym in symbols:
        df = dataframes[sym]
        strat = make_strategy(cls, extra_kwargs)
        comm, slip = COSTS_BY_SYMBOL.get(sym, DEFAULT_COSTS)

        bt = Backtester(
            df, strat,
            starting_cash=STARTING_CASH,
            commission_bps=comm,
            slippage_bps=slip,
            symbol=sym,
            max_leverage=2.0,
        )
        eq, trades = bt.run()

        ret = (eq[-1] - STARTING_CASH) / STARTING_CASH * 100
        sharpe = compute_sharpe(eq)
        dd = bt.max_drawdown * 100
        wins = sum(1 for t in trades if t.pnl and t.pnl > 0)
        win_rate = wins / len(trades) * 100 if trades else 0.0
        bnh = bnh_return(df)

        metrics.append({
            "symbol": sym, "return": ret, "bnh": bnh, "dd": dd,
            "sharpe": sharpe, "trades": len(trades), "win_rate": win_rate,
        })

        print(f"{sym:<10s} {len(df):>6,} {ret:>+9.2f}% {bnh:>+9.2f}% "
              f"{dd:>7.2f}% {sharpe:>8.4f} {len(trades):>7d} {win_rate:>6.1f}%")

    mean_ret = np.mean([m["return"] for m in metrics])
    mean_sharpe = np.mean([m["sharpe"] for m in metrics])
    winners = sum(1 for m in metrics if m["return"] > 0)
    bnh_beat = sum(1 for m in metrics if m["return"] > m["bnh"])
    print("-" * 80)
    print(f"  [{variant_name}]  Mean return: {mean_ret:+.2f}%   "
          f"Mean Sharpe: {mean_sharpe:.4f}   Winners: {winners}/{len(metrics)}   "
          f"Beats B&H: {bnh_beat}/{len(metrics)}")
    return metrics


def run_variant_portfolio(variant_name, cls, extra_kwargs, dataframes, symbols):
    """Run portfolio backtests (EW + RP) for one variant. Returns dict of metrics."""
    costs_bps = {
        sym: {"commission_bps": COSTS_BY_SYMBOL.get(sym, DEFAULT_COSTS)[0],
              "slippage_bps":   COSTS_BY_SYMBOL.get(sym, DEFAULT_COSTS)[1]}
        for sym in symbols
    }

    limits = RiskLimits(
        max_gross_exposure=1.2,
        max_net_exposure=1.0,
        max_single_asset=0.20,
        max_open_positions=len(symbols),
    )

    results = {}
    for alloc_name, allocator in [
        ("Equal Weight", EqualWeightAllocator()),
        ("Risk Parity", RiskParityAllocator(min_lookback=60, max_weight=0.20)),
    ]:
        strats = {sym: make_strategy(cls, extra_kwargs) for sym in symbols}
        pbt = PortfolioBacktester(
            dataframes=dataframes,
            strategies=strats,
            allocator=allocator,
            starting_cash=STARTING_CASH,
            commission_bps=DEFAULT_COSTS[0],
            slippage_bps=DEFAULT_COSTS[1],
            rebalance_frequency=21,
            vol_lookback=500,
            risk_limits=limits,
            costs_by_symbol=costs_bps,
        )
        result = pbt.run()
        ret = (result.equity_curve[-1] - STARTING_CASH) / STARTING_CASH * 100
        sharpe = compute_sharpe(result.equity_curve)
        dd = pbt.max_drawdown * 100
        results[alloc_name] = {
            "return": ret, "sharpe": sharpe, "dd": dd,
            "trades": len(result.trades),
        }
        print(f"  [{variant_name}] {alloc_name:<14s} Return: {ret:>+8.2f}%   "
              f"Max DD: {dd:>6.2f}%   Sharpe: {sharpe:>7.4f}   "
              f"Trades: {len(result.trades)}")
    return results


def main() -> None:
    section("Loading data")
    dataframes: dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        df = load_data(sym)
        if df is None or len(df) < 400:
            if df is not None:
                print(f"  {sym:<8s}  skipped ({len(df)} bars - need >= 400)")
            continue
        dataframes[sym] = df
        print(f"  {sym:<8s}  {len(df):>5,} bars  "
              f"{df.index[0].date()} -> {df.index[-1].date()}")

    if len(dataframes) < 3:
        print("Need at least 3 instruments with enough history. "
              "Populate ohlc_data/ first.")
        sys.exit(1)

    symbols = sorted(dataframes.keys())
    print(f"\n  {len(symbols)} instruments loaded")

    # --- Per-asset runs for each variant -------------------------------
    per_asset_by_variant: dict[str, list] = {}
    for variant_name, cls, extra in VARIANTS:
        section(f"Per-asset TSMOM - {variant_name}")
        per_asset_by_variant[variant_name] = run_variant_per_asset(
            variant_name, cls, extra, dataframes, symbols
        )

    # --- Portfolio runs for each variant -------------------------------
    portfolio_by_variant: dict[str, dict] = {}
    for variant_name, cls, extra in VARIANTS:
        section(f"Multi-asset TSMOM portfolio - {variant_name}")
        portfolio_by_variant[variant_name] = run_variant_portfolio(
            variant_name, cls, extra, dataframes, symbols
        )

    # Equal-weight buy-and-hold benchmark (same across variants)
    bnh_rets = [bnh_return(dataframes[s]) for s in symbols]
    print(f"\n  B&H (EW) benchmark Return: {np.mean(bnh_rets):+.2f}%   "
          f"(equal-weight average of single-asset buy-and-hold)")

    # --- Comparison block ---------------------------------------------
    section("Variant comparison (Equal-Weight portfolio)")

    print(f"  {'Variant':<12s} {'Portfolio Ret':>14s} {'Sharpe':>8s} "
          f"{'Max DD':>8s} {'Winners (vs B&H)':>18s}")
    print("  " + "-" * 70)

    # Include the published baseline reference as the first row.
    print(f"  {'Baseline*':<12s} {'+5.87%':>14s} {'0.09':>8s} "
          f"{'18.78%':>8s} {'4/24':>18s}")

    for variant_name, _, _ in VARIANTS:
        port = portfolio_by_variant[variant_name]["Equal Weight"]
        metrics = per_asset_by_variant[variant_name]
        bnh_beat = sum(1 for m in metrics if m["return"] > m["bnh"])
        total = len(metrics)
        print(f"  {variant_name:<12s} "
              f"{port['return']:>+13.2f}% "
              f"{port['sharpe']:>8.4f} "
              f"{port['dd']:>7.2f}% "
              f"{bnh_beat:>13d}/{total:<4d}")
    print("\n  *Baseline row is the reference line from tsmom_demo.py.")

    # Risk-Parity block (useful signal too)
    print(f"\n  {'Variant':<12s} {'RP Ret':>10s} {'RP Sharpe':>10s} {'RP Max DD':>10s}")
    print("  " + "-" * 50)
    for variant_name, _, _ in VARIANTS:
        rp = portfolio_by_variant[variant_name]["Risk Parity"]
        print(f"  {variant_name:<12s} "
              f"{rp['return']:>+9.2f}% "
              f"{rp['sharpe']:>10.4f} "
              f"{rp['dd']:>9.2f}%")

    # --- Instrument-level deltas (where variants diverge dramatically) --
    section("Instruments with largest variant divergence (single-asset returns)")

    base_by_sym = {m["symbol"]: m for m in per_asset_by_variant["Baseline"]}
    lo_by_sym   = {m["symbol"]: m for m in per_asset_by_variant["Long-only"]}
    fi_by_sym   = {m["symbol"]: m for m in per_asset_by_variant["Filtered"]}

    rows = []
    for sym in symbols:
        b = base_by_sym[sym]["return"]
        lo = lo_by_sym[sym]["return"]
        fi = fi_by_sym[sym]["return"]
        best = max(b, lo, fi)
        worst = min(b, lo, fi)
        rows.append((sym, b, lo, fi, best - worst))
    rows.sort(key=lambda r: r[4], reverse=True)

    print(f"  {'Symbol':<10s} {'Baseline':>10s} {'Long-only':>11s} "
          f"{'Filtered':>10s} {'Spread':>10s}")
    print("  " + "-" * 58)
    for sym, b, lo, fi, spread in rows[:8]:
        print(f"  {sym:<10s} {b:>+9.2f}% {lo:>+10.2f}% "
              f"{fi:>+9.2f}% {spread:>9.2f}%")

    print("\nDone.")


if __name__ == "__main__":
    main()
