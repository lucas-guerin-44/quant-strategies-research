#!/usr/bin/env python3
"""
Gary Antonacci Dual Momentum demo (pandas/numpy simulation).

This is a standalone script — it does NOT use the event-driven Backtester.
It simulates Antonacci's Dual Momentum across a 24-instrument retail
universe, 2015-2026.

Dual Momentum combines:
    1. RELATIVE momentum: within each asset class, rank by trailing 12-1
       month return (close[t-21] - close[t-252]) / close[t-252].
    2. ABSOLUTE momentum: the selected asset's 12-1 return must be positive;
       otherwise the class sleeve goes to cash (0% return until next rebal).

Two variants are produced:
    - Class-diversified: top-1 per asset class (FX / Commodities / Equities
      / Crypto), equal-weight the four sleeves.
    - Single-universe:   top-1 across ALL 24 instruments (100% in one asset
      or 100% cash).

Benchmark: equal-weight buy-and-hold across the same loaded universe.

Run from the repo root:
    python examples/dual_momentum_demo.py
"""

from __future__ import annotations

import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))  # research repo root
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, '..', '..', 'backtesting-engine-2.0')))  # engine

from utils import fetch_ohlc


# ----------------------------------------------------------------------
# Universe
# ----------------------------------------------------------------------

FX_CROSSES = [
    "AUDNZD", "NZDCAD", "GBPNZD", "AUDCAD", "CADJPY", "NZDJPY",
    "EURGBP", "EURNOK", "USDZAR", "EURUSD", "GBPUSD",
]
COMMODITIES = ["COCOA", "COFFEE", "SUGAR", "COTTON", "XAUUSD", "USOUSD"]
EQUITIES = ["EWZ", "FXI", "EWJ", "SPX500", "NDX100", "GER40"]
CRYPTO = ["BTCUSD"]

CLASS_GROUPS = {
    "FX":          FX_CROSSES,
    "Commodities": COMMODITIES,
    "Equities":    EQUITIES,
    "Crypto":      CRYPTO,
}

TIMEFRAME = "D1"
START_DATE = "2015-01-01"
END_DATE = "2026-12-31"
STARTING_CASH = 100_000.0

# Momentum parameters
LOOKBACK = 252      # ~12 months
SKIP = 21           # skip the most recent month (12-1 momentum)
REBALANCE_BARS = 21  # monthly rebalance

# Per-symbol costs (bps) — same schedule as tsmom_demo.py
COSTS_BY_SYMBOL = {
    "BTCUSD": (10.0, 5.0),
    "XAUUSD": (5.0, 3.0), "USOUSD": (5.0, 3.0),
    "SPX500": (3.0, 1.0), "NDX100": (3.0, 1.0), "GER40": (3.0, 2.0),
    "EURUSD": (2.0, 1.0), "GBPUSD": (2.0, 1.0),
    "COCOA":  (8.0, 5.0), "COFFEE": (8.0, 5.0),
    "SUGAR":  (8.0, 5.0), "COTTON": (8.0, 5.0),
    "EWZ":    (5.0, 3.0), "FXI":    (5.0, 3.0), "EWJ": (5.0, 3.0),
}
DEFAULT_COSTS = (4.0, 2.0)


# ----------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------

def load_symbol(symbol: str) -> pd.DataFrame | None:
    """Load one instrument's D1 close series.

    Applies the Yahoo OHLC sanity fix (min/max across OHLC) defensively
    even though we only use close — keeps the pipeline consistent with
    the rest of the repo.
    """
    try:
        raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    except Exception as e:
        print(f"  {symbol:<8s}  LOAD FAILED ({e})")
        return None
    if raw is None or raw.empty:
        return None

    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]

    # Yahoo floating-point OHLC fix
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    return df


def build_close_matrix(
    groups: dict[str, list[str]],
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Load all instruments, filter to >= 400 bars, align on business-day index.

    Returns
    -------
    closes : DataFrame
        Business-day index, columns = symbols with sufficient history.
        Gaps forward-filled so rebalance lookups never hit NaN after warmup.
    groups_present : dict[str, list[str]]
        Same structure as ``groups`` but only containing symbols that
        survived the 400-bar filter.
    """
    all_symbols: list[str] = []
    for syms in groups.values():
        all_symbols.extend(syms)

    frames: dict[str, pd.DataFrame] = {}
    for sym in all_symbols:
        df = load_symbol(sym)
        if df is None or len(df) < 400:
            if df is not None:
                print(f"  {sym:<8s}  skipped ({len(df)} bars, need >= 400)")
            else:
                print(f"  {sym:<8s}  skipped (no data)")
            continue
        frames[sym] = df
        print(f"  {sym:<8s}  {len(df):>5,} bars  "
              f"{df.index[0].date()} -> {df.index[-1].date()}")

    if not frames:
        raise SystemExit("No instruments loaded — populate ohlc_data/ first.")

    # Union index of all timestamps, then resample to business days.
    # fetch_ohlc returns tz-aware UTC timestamps; strip tz for BDay index.
    closes = pd.DataFrame({
        sym: df["close"].tz_convert(None) for sym, df in frames.items()
    })
    closes = closes.sort_index()

    bday_index = pd.bdate_range(
        start=closes.index.min().normalize(),
        end=closes.index.max().normalize(),
    )
    closes = closes.reindex(bday_index, method=None).ffill()

    # Drop the warm-up rows where any column is still NaN so every rebalance
    # after position LOOKBACK has real data for every (surviving) instrument.
    closes = closes.dropna(how="all")

    groups_present: dict[str, list[str]] = {}
    for cls, syms in groups.items():
        present = [s for s in syms if s in closes.columns]
        if present:
            groups_present[cls] = present

    return closes, groups_present


# ----------------------------------------------------------------------
# Dual Momentum engine
# ----------------------------------------------------------------------

def dual_momentum_backtest(
    closes: pd.DataFrame,
    groups: dict[str, list[str]] | None,
    lookback: int = LOOKBACK,
    skip: int = SKIP,
    rebalance: int = REBALANCE_BARS,
    starting_cash: float = STARTING_CASH,
) -> dict:
    """Run a Dual Momentum backtest on the close matrix.

    Parameters
    ----------
    closes : DataFrame
        Business-day index, columns = instrument closes.
    groups : dict or None
        ``{class_name: [symbols...]}``. If None, the whole universe is
        treated as a single group (single-universe variant).
    lookback : int
        Bars ago for the start of the momentum window (default 252 ~= 12m).
    skip : int
        Bars to skip at the end of the window (default 21 ~= 1m).
    rebalance : int
        Bars between rebalances (default 21).
    starting_cash : float
        Starting equity.

    Returns
    -------
    dict with keys:
        equity        : pd.Series of portfolio equity, indexed by date.
        weights       : pd.DataFrame of weights at each bar (incl. "CASH").
        selections    : list of (date, {class: symbol_or_'CASH'}) per rebal.
        n_trades      : int total leg-switches (|dw| > 0) across rebalances.
        costs_paid    : float total dollars paid in commission+slippage.
    """
    if groups is None:
        groups = {"ALL": list(closes.columns)}

    # Cost lookup: bps per symbol
    def cost_bps(sym: str) -> float:
        if sym == "CASH":
            return 0.0
        comm, slip = COSTS_BY_SYMBOL.get(sym, DEFAULT_COSTS)
        return comm + slip

    n_classes = len(groups)
    class_weight = 1.0 / n_classes  # 25% each for 4 classes

    dates = closes.index
    n_bars = len(dates)

    # Asset universe including synthetic CASH leg (earns 0%)
    universe = list(closes.columns) + ["CASH"]
    sym_idx = {s: i for i, s in enumerate(universe)}

    # Close matrix as numpy for speed; CASH price held constant at 1.0
    close_mat = closes.values  # shape (n_bars, n_syms)
    n_real = close_mat.shape[1]

    # daily simple returns for each real instrument; CASH return = 0
    rets_real = np.zeros_like(close_mat)
    rets_real[1:] = close_mat[1:] / close_mat[:-1] - 1.0
    rets_real = np.nan_to_num(rets_real, nan=0.0, posinf=0.0, neginf=0.0)

    # weights vector (per bar) — store history for reporting
    weights = np.zeros((n_bars, len(universe)))
    equity = np.full(n_bars, starting_cash, dtype=float)

    cur_w = np.zeros(len(universe))
    selections: list[tuple[pd.Timestamp, dict[str, str]]] = []
    n_trades = 0
    costs_paid_total = 0.0

    # first rebalance cannot happen before we have (lookback) bars of history
    first_rebal = lookback

    for t in range(n_bars):
        # 1) apply today's returns to current weights — equity evolves
        if t > 0:
            port_ret = float(np.dot(cur_w[:n_real], rets_real[t, :]))
            equity[t] = equity[t - 1] * (1.0 + port_ret)
        else:
            equity[t] = starting_cash

        # 2) check for rebalance
        is_rebal = (t >= first_rebal) and ((t - first_rebal) % rebalance == 0)

        if is_rebal:
            # Pick per-class top
            picks: dict[str, str] = {}
            new_w = np.zeros(len(universe))

            # price at end of month and one year ago (skip most recent month)
            # signal = (close[t - skip] - close[t - lookback]) / close[t - lookback]
            p_recent = close_mat[t - skip]
            p_old = close_mat[t - lookback]

            for cls, syms in groups.items():
                best_sym: str | None = None
                best_sig = -np.inf
                for s in syms:
                    j = sym_idx[s]
                    p0 = p_old[j]
                    p1 = p_recent[j]
                    if not np.isfinite(p0) or not np.isfinite(p1) or p0 <= 0:
                        continue
                    sig = (p1 - p0) / p0
                    if sig > best_sig:
                        best_sig = sig
                        best_sym = s

                if best_sym is None or best_sig <= 0.0:
                    picks[cls] = "CASH"
                    new_w[sym_idx["CASH"]] += class_weight
                else:
                    picks[cls] = best_sym
                    new_w[sym_idx[best_sym]] += class_weight

            # Turnover and costs
            dw = new_w - cur_w
            turnover_abs = np.abs(dw)
            # Count trade legs where we actually moved capital
            n_trades += int((turnover_abs > 1e-9).sum())

            # Cost in $ = equity * |dw_i| * bps_i / 10_000
            cost_per_leg = np.zeros(len(universe))
            for i, sym in enumerate(universe):
                cost_per_leg[i] = turnover_abs[i] * cost_bps(sym) * 1e-4
            cost_dollars = float(equity[t] * cost_per_leg.sum())
            costs_paid_total += cost_dollars
            equity[t] -= cost_dollars

            cur_w = new_w
            selections.append((dates[t], picks))

        weights[t, :] = cur_w

    w_df = pd.DataFrame(weights, index=dates, columns=universe)
    eq_s = pd.Series(equity, index=dates, name="equity")

    return {
        "equity": eq_s,
        "weights": w_df,
        "selections": selections,
        "n_trades": n_trades,
        "costs_paid": costs_paid_total,
    }


# ----------------------------------------------------------------------
# Benchmarks
# ----------------------------------------------------------------------

def equal_weight_buy_and_hold(closes: pd.DataFrame, starting_cash: float) -> pd.Series:
    """Equal-weight, rebalanced-once, hold-forever benchmark.

    Each instrument receives 1/N of starting capital at its first valid
    close; the portfolio is the sum of those sleeves thereafter. Forward-
    filled closes mean an instrument that stops updating simply flat-lines.
    """
    n = closes.shape[1]
    w = 1.0 / n
    # Normalize each column to its first valid price, then sum with weight w.
    firsts = closes.bfill().iloc[0]  # guaranteed after dropna(how='all')
    normed = closes.div(firsts).ffill()
    port = normed.sum(axis=1) * w * starting_cash
    return port.rename("equity")


# ----------------------------------------------------------------------
# Performance stats
# ----------------------------------------------------------------------

def compute_stats(
    eq: pd.Series,
    starting_cash: float,
    weights: pd.DataFrame | None = None,
    n_trades: int | None = None,
) -> dict:
    """Compute summary stats for an equity curve."""
    eq = eq.dropna()
    total_ret = (eq.iloc[-1] - starting_cash) / starting_cash * 100.0

    # Max drawdown
    running_max = eq.cummax()
    dd = (eq / running_max - 1.0)
    max_dd = dd.min() * 100.0

    # Sharpe (daily returns, annualized)
    daily = eq.pct_change().dropna()
    if daily.std() > 0 and len(daily) > 1:
        sharpe = float(np.sqrt(252) * daily.mean() / daily.std())
    else:
        sharpe = 0.0

    # Years covered (business-day based)
    years = max(len(eq) / 252.0, 1e-9)

    result = {
        "total_return_pct": total_ret,
        "max_drawdown_pct": max_dd,
        "sharpe": sharpe,
        "years": years,
        "final_equity": float(eq.iloc[-1]),
    }

    if n_trades is not None:
        result["trades_per_year"] = n_trades / years
        result["n_trades"] = n_trades

    if weights is not None and "CASH" in weights.columns:
        # Fraction of bars where any cash weight is held (> 0)
        cash_bars = (weights["CASH"] > 1e-9).sum()
        result["pct_time_in_cash"] = cash_bars / len(weights) * 100.0

    return result


def picks_frequency(
    selections: list[tuple[pd.Timestamp, dict[str, str]]],
) -> Counter:
    """Count how often each instrument (or CASH) is chosen across rebalances."""
    c: Counter = Counter()
    for _, picks in selections:
        for sym in picks.values():
            c[sym] += 1
    return c


# ----------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'=' * 80}\n  {title}\n{'=' * 80}\n")


def print_variant(name: str, result: dict, closes: pd.DataFrame) -> None:
    stats = compute_stats(
        result["equity"], STARTING_CASH,
        weights=result["weights"], n_trades=result["n_trades"],
    )
    freq = picks_frequency(result["selections"])

    print(f"--- {name} ---")
    print(f"  Final equity         : ${stats['final_equity']:>14,.2f}")
    print(f"  Total return         : {stats['total_return_pct']:>+14.2f}%")
    print(f"  Max drawdown         : {stats['max_drawdown_pct']:>+14.2f}%")
    print(f"  Ann. Sharpe (252)    : {stats['sharpe']:>14.4f}")
    print(f"  Rebalance legs       : {stats['n_trades']:>14d}")
    print(f"  Trades per year      : {stats['trades_per_year']:>14.2f}")
    print(f"  Time with cash held  : {stats['pct_time_in_cash']:>14.2f}%")
    print(f"  Costs paid (cum $)   : ${result['costs_paid']:>14,.2f}")
    print(f"  Years covered        : {stats['years']:>14.2f}")

    print(f"\n  Top 10 most-picked instruments:")
    for sym, n in freq.most_common(10):
        print(f"    {sym:<10s} {n:>4d} rebalances")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> None:
    section("Loading data (>= 400 bars from 2015-01-01)")
    closes, groups_present = build_close_matrix(CLASS_GROUPS)

    print(f"\n  Loaded {closes.shape[1]} instruments across "
          f"{len(groups_present)} asset classes")
    for cls, syms in groups_present.items():
        print(f"    {cls:<12s} ({len(syms):>2d}): {', '.join(syms)}")
    print(f"  Aligned index: {closes.index.min().date()} -> "
          f"{closes.index.max().date()}  ({len(closes):,} business days)")

    # ------------------------------------------------------------------
    section("Class-diversified Dual Momentum (top-1 per class, EW sleeves)")
    # ------------------------------------------------------------------
    class_result = dual_momentum_backtest(closes, groups_present)
    print_variant("Class-diversified", class_result, closes)

    # ------------------------------------------------------------------
    section("Single-universe Dual Momentum (top-1 across all instruments)")
    # ------------------------------------------------------------------
    single_result = dual_momentum_backtest(closes, groups=None)
    print_variant("Single-universe", single_result, closes)

    # ------------------------------------------------------------------
    section("Benchmark: equal-weight buy-and-hold")
    # ------------------------------------------------------------------
    bnh_eq = equal_weight_buy_and_hold(closes, STARTING_CASH)
    bnh_stats = compute_stats(bnh_eq, STARTING_CASH)
    print(f"  Final equity         : ${bnh_stats['final_equity']:>14,.2f}")
    print(f"  Total return         : {bnh_stats['total_return_pct']:>+14.2f}%")
    print(f"  Max drawdown         : {bnh_stats['max_drawdown_pct']:>+14.2f}%")
    print(f"  Ann. Sharpe (252)    : {bnh_stats['sharpe']:>14.4f}")
    print(f"  Years covered        : {bnh_stats['years']:>14.2f}")

    # ------------------------------------------------------------------
    section("Side-by-side summary vs. TSMOM baseline")
    # ------------------------------------------------------------------
    cs = compute_stats(class_result["equity"], STARTING_CASH,
                       weights=class_result["weights"],
                       n_trades=class_result["n_trades"])
    ss = compute_stats(single_result["equity"], STARTING_CASH,
                       weights=single_result["weights"],
                       n_trades=single_result["n_trades"])

    header = f"{'Strategy':<28s} {'Return':>10s} {'MaxDD':>10s} {'Sharpe':>8s} {'Trd/yr':>8s} {'%Cash':>8s}"
    print(header)
    print("-" * len(header))
    print(f"{'TSMOM baseline (ref)':<28s} "
          f"{'+5.87%':>10s} {'n/a':>10s} {'0.0900':>8s} {'n/a':>8s} {'n/a':>8s}")
    print(f"{'Dual Momentum (class EW)':<28s} "
          f"{cs['total_return_pct']:>+9.2f}% {cs['max_drawdown_pct']:>+9.2f}% "
          f"{cs['sharpe']:>8.4f} {cs['trades_per_year']:>8.2f} "
          f"{cs['pct_time_in_cash']:>7.2f}%")
    print(f"{'Dual Momentum (single-uni)':<28s} "
          f"{ss['total_return_pct']:>+9.2f}% {ss['max_drawdown_pct']:>+9.2f}% "
          f"{ss['sharpe']:>8.4f} {ss['trades_per_year']:>8.2f} "
          f"{ss['pct_time_in_cash']:>7.2f}%")
    print(f"{'Equal-weight B&H':<28s} "
          f"{bnh_stats['total_return_pct']:>+9.2f}% {bnh_stats['max_drawdown_pct']:>+9.2f}% "
          f"{bnh_stats['sharpe']:>8.4f} {'—':>8s} {'—':>8s}")

    print("\nDone.")


if __name__ == "__main__":
    main()
