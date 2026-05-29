#!/usr/bin/env python3
"""
Time-Series Momentum (TSMOM) demo across the retail-friendly universe.

Runs MOP (2012) time-series momentum on:
  - Exotic FX crosses (AUDNZD, NZDCAD, GBPNZD, AUDCAD, CADJPY, NZDJPY,
    EURGBP, EURNOK, USDZAR)
  - Soft commodities (COCOA, COFFEE, SUGAR, COTTON)
  - Country ETF CFDs (EWZ, FXI, EWJ)
  - Existing deep-history instruments (XAUUSD, USOUSD, SPX500, NDX100,
    GER40, BTCUSD, EURUSD, GBPUSD)

For each instrument:
  1. Loads OHLC from the local CSV cache (populated by scripts/mt5_fetch.py
     or scripts/yahoo_fetch.py).
  2. Runs a single-asset TSMOM backtest (vol-targeted 15% per position,
     12-1 momentum signal, monthly rebalance).
  3. Reports return, drawdown, Sharpe, trade count, and buy-and-hold
     comparison.

Then aggregates into an equal-weight multi-asset portfolio (the classic
"managed futures" retail proxy) and reports portfolio-level stats.
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
from data import fetch_ohlc


UNIVERSE = [
    # Exotic FX crosses (MT5)
    "AUDNZD", "NZDCAD", "GBPNZD", "AUDCAD", "CADJPY", "NZDJPY",
    "EURGBP", "EURNOK", "USDZAR",
    # Soft commodities (Yahoo futures front-month)
    "COCOA", "COFFEE", "SUGAR", "COTTON",
    # Country ETF CFDs (Yahoo)
    "EWZ", "FXI", "EWJ",
    # Existing deep-history
    "XAUUSD", "USOUSD", "SPX500", "NDX100", "GER40", "BTCUSD",
    "EURUSD", "GBPUSD",
]

TIMEFRAME = "D1"
START_DATE = "2015-01-01"
END_DATE = "2026-12-31"
STARTING_CASH = 100_000

# Per-asset costs (bps). Reflect CFD reality for each asset class.
COSTS_BY_SYMBOL = {
    "BTCUSD": (10.0, 5.0),
    "XAUUSD": (5.0, 3.0), "USOUSD": (5.0, 3.0),
    "SPX500": (3.0, 1.0), "NDX100": (3.0, 1.0), "GER40": (3.0, 2.0),
    "EURUSD": (2.0, 1.0), "GBPUSD": (2.0, 1.0),
    # Softs (Yahoo futures — wider real-world spreads via CFD)
    "COCOA": (8.0, 5.0), "COFFEE": (8.0, 5.0),
    "SUGAR": (8.0, 5.0), "COTTON": (8.0, 5.0),
    # Country ETFs
    "EWZ": (5.0, 3.0), "FXI": (5.0, 3.0), "EWJ": (5.0, 3.0),
}
DEFAULT_COSTS = (4.0, 2.0)  # Exotic FX crosses and anything unlisted


def load_data(symbol: str) -> pd.DataFrame | None:
    """Fetch OHLC and return a DatetimeIndex frame, or None on failure."""
    try:
        raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    except Exception as e:
        print(f"  {symbol:<8s}  LOAD FAILED ({e})")
        return None
    if raw.empty:
        return None
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]

    # Yahoo futures data occasionally has sub-tick OHLC inconsistencies
    # (e.g. high slightly below open/close from feed rounding). Enforce
    # the OHLC invariants so the engine's validator accepts the data.
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    return df


def bnh_return(df: pd.DataFrame) -> float:
    c = df["close"]
    return (c.iloc[-1] - c.iloc[0]) / c.iloc[0] * 100


def section(title: str) -> None:
    print(f"\n{'=' * 80}\n  {title}\n{'=' * 80}\n")


def main() -> None:
    section("Loading data")
    dataframes: dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        df = load_data(sym)
        if df is None or len(df) < 400:
            if df is not None:
                print(f"  {sym:<8s}  skipped ({len(df)} bars — need >= 400)")
            continue
        dataframes[sym] = df
        print(f"  {sym:<8s}  {len(df):>5,} bars  {df.index[0].date()} -> {df.index[-1].date()}")

    if len(dataframes) < 3:
        print("Need at least 3 instruments with enough history. Populate ohlc_data/ first.")
        sys.exit(1)

    symbols = sorted(dataframes.keys())
    print(f"\n  {len(symbols)} instruments loaded")

    # ------------------------------------------------------------------
    section("Per-asset TSMOM (12-1 momentum, monthly rebalance, 15% vol target)")
    # ------------------------------------------------------------------

    base_params = dict(
        lookback_bars=252,
        skip_bars=21,
        rebalance_bars=21,
        vol_lookback=60,
        vol_target_annual=0.15,
        long_only=False,
        min_abs_return=0.0,
        size_cap_fraction=1.0,
    )

    print(f"{'Instrument':<10s} {'Bars':>6s} {'TSMOM Ret':>10s} {'B&H Ret':>10s} "
          f"{'Max DD':>8s} {'Sharpe':>8s} {'Trades':>7s} {'Win %':>7s}")
    print("-" * 80)

    per_asset_metrics = []
    for sym in symbols:
        df = dataframes[sym]
        strat = TimeSeriesMomentumStrategy(**base_params)
        comm, slip = COSTS_BY_SYMBOL.get(sym, DEFAULT_COSTS)

        bt = Backtester(
            df, strat,
            starting_cash=STARTING_CASH,
            commission_bps=comm,
            slippage_bps=slip,
            symbol=sym,
            max_leverage=2.0,  # allow some vol-target headroom for low-vol instruments
        )
        eq, trades = bt.run()

        ret = (eq[-1] - STARTING_CASH) / STARTING_CASH * 100
        sharpe = compute_sharpe(eq)
        dd = bt.max_drawdown * 100
        wins = sum(1 for t in trades if t.pnl and t.pnl > 0)
        win_rate = wins / len(trades) * 100 if trades else 0.0
        bnh = bnh_return(df)

        per_asset_metrics.append({
            "symbol": sym, "return": ret, "bnh": bnh, "dd": dd,
            "sharpe": sharpe, "trades": len(trades), "win_rate": win_rate,
        })

        print(f"{sym:<10s} {len(df):>6,} {ret:>+9.2f}% {bnh:>+9.2f}% "
              f"{dd:>7.2f}% {sharpe:>8.4f} {len(trades):>7d} {win_rate:>6.1f}%")

    # Summary across assets
    mean_ret = np.mean([m["return"] for m in per_asset_metrics])
    mean_sharpe = np.mean([m["sharpe"] for m in per_asset_metrics])
    winners = sum(1 for m in per_asset_metrics if m["return"] > 0)
    bnh_beat = sum(1 for m in per_asset_metrics if m["return"] > m["bnh"])
    print("-" * 80)
    print(f"  Mean return: {mean_ret:+.2f}%   Mean Sharpe: {mean_sharpe:.4f}   "
          f"Winners: {winners}/{len(per_asset_metrics)}   Beats B&H: {bnh_beat}/{len(per_asset_metrics)}")

    # ------------------------------------------------------------------
    section("Multi-asset TSMOM portfolio (equal-weight + risk-parity)")
    # ------------------------------------------------------------------

    # Use full per-symbol cost schedule for the portfolio pass
    costs_bps = {sym: {"commission_bps": COSTS_BY_SYMBOL.get(sym, DEFAULT_COSTS)[0],
                      "slippage_bps":   COSTS_BY_SYMBOL.get(sym, DEFAULT_COSTS)[1]}
                 for sym in symbols}

    limits = RiskLimits(
        max_gross_exposure=1.2,   # Room for vol-targeting above 1x in low-vol names
        max_net_exposure=1.0,
        max_single_asset=0.20,    # No single asset > 20% of equity
        max_open_positions=len(symbols),
    )

    portfolio_results: dict[str, np.ndarray] = {}
    for alloc_name, allocator in [
        ("Equal Weight", EqualWeightAllocator()),
        ("Risk Parity", RiskParityAllocator(min_lookback=60, max_weight=0.20)),
    ]:
        strats = {sym: TimeSeriesMomentumStrategy(**base_params) for sym in symbols}
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
        portfolio_results[alloc_name] = result.equity_curve

        ret = (result.equity_curve[-1] - STARTING_CASH) / STARTING_CASH * 100
        sharpe = compute_sharpe(result.equity_curve)
        dd = pbt.max_drawdown * 100
        print(f"{alloc_name:<14s} Return: {ret:>+8.2f}%   Max DD: {dd:>6.2f}%   "
              f"Sharpe: {sharpe:>7.4f}   Trades: {len(result.trades)}")

    # Equal-weight buy-and-hold benchmark
    bnh_rets = [bnh_return(dataframes[s]) for s in symbols]
    print(f"{'B&H (EW)':<14s} Return: {np.mean(bnh_rets):>+8.2f}%   "
          f"(equal-weight average of single-asset buy-and-hold)")

    # ------------------------------------------------------------------
    section("Top and bottom performers (single-asset)")
    # ------------------------------------------------------------------

    sorted_assets = sorted(per_asset_metrics, key=lambda m: m["sharpe"], reverse=True)
    print("Top 5 by Sharpe:")
    for m in sorted_assets[:5]:
        print(f"  {m['symbol']:<10s} Sharpe {m['sharpe']:+.4f}   "
              f"Ret {m['return']:+.2f}%   DD {m['dd']:.2f}%   Trades {m['trades']}")
    print("\nBottom 5 by Sharpe:")
    for m in sorted_assets[-5:]:
        print(f"  {m['symbol']:<10s} Sharpe {m['sharpe']:+.4f}   "
              f"Ret {m['return']:+.2f}%   DD {m['dd']:.2f}%   Trades {m['trades']}")

    print("\nDone.")


if __name__ == "__main__":
    main()
