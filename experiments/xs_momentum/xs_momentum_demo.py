#!/usr/bin/env python3
"""
Cross-Sectional Momentum Rotation (Asness-Moskowitz-Pedersen 2013) demo.

At each rebalance (every 21 trading days), ranks every eligible instrument by
its 12-1 month past return (close[t-21] / close[t-252] - 1). The long-only
variant holds the top-K assets equal-weighted; the long-short variant also
shorts the bottom-K. Between rebalances, weights are held constant.

Unlike time-series momentum (which independently decides long/short per asset
and is vulnerable to V-recoveries whipsawing into shorts), cross-sectional
momentum re-allocates capital to whatever is currently trending hardest in
relative terms -- it never gets stuck short on a market that has already
turned.

This is a STANDALONE pandas/numpy simulation. It does NOT use the
event-driven Backtester in backtesting/. Lookahead is prevented by
construction: at rebalance date t we only index closes with label <= t.
"""

from __future__ import annotations

import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)  # research repo root
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))  # engine
sys.path.insert(0, _HERE)  # this strategy's directory

from utils import fetch_ohlc


# ---------------------------------------------------------------------------
# Universe and config -- duplicated verbatim from examples/tsmom_demo.py
# ---------------------------------------------------------------------------

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
STARTING_CASH = 100_000.0

# (commission_bps, slippage_bps) per asset
COSTS_BY_SYMBOL = {
    "BTCUSD": (10.0, 5.0),
    "XAUUSD": (5.0, 3.0), "USOUSD": (5.0, 3.0),
    "SPX500": (3.0, 1.0), "NDX100": (3.0, 1.0), "GER40": (3.0, 2.0),
    "EURUSD": (2.0, 1.0), "GBPUSD": (2.0, 1.0),
    "COCOA": (8.0, 5.0), "COFFEE": (8.0, 5.0),
    "SUGAR": (8.0, 5.0), "COTTON": (8.0, 5.0),
    "EWZ": (5.0, 3.0), "FXI": (5.0, 3.0), "EWJ": (5.0, 3.0),
}
DEFAULT_COSTS = (4.0, 2.0)

# Strategy hyperparameters
LOOKBACK_BARS = 252   # ~12 months
SKIP_BARS = 21        # skip most recent month (short-term reversal)
REBALANCE_BARS = 21   # rebalance monthly
TOP_K = 5             # number of longs (and shorts in LS variant)
BARS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data(symbol: str) -> pd.DataFrame | None:
    """Fetch OHLC, enforce OHLC invariants, return DatetimeIndex frame."""
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
    # Enforce OHLC invariants (Yahoo data has float rounding artifacts).
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    return df


def section(title: str) -> None:
    print(f"\n{'=' * 80}\n  {title}\n{'=' * 80}\n")


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def run_xs_momentum(
    closes: pd.DataFrame,
    costs: dict[str, tuple[float, float]],
    top_k: int,
    long_short: bool,
    rebalance_bars: int = REBALANCE_BARS,
    lookback_bars: int = LOOKBACK_BARS,
    skip_bars: int = SKIP_BARS,
) -> dict:
    """Run a cross-sectional momentum simulation on a closes panel.

    Parameters
    ----------
    closes : DataFrame
        Business-day indexed close panel, one column per symbol. Must be
        forward-filled already (NaN allowed only in the pre-listing burn-in
        at the top of each column).
    costs : dict[symbol, (comm_bps, slip_bps)]
    top_k : int
        Number of longs (and shorts if long_short=True).
    long_short : bool
    rebalance_bars : int
    lookback_bars : int
    skip_bars : int
        `signal(t) = close[t - skip] / close[t - lookback] - 1`.

    Returns
    -------
    dict with equity curve, daily returns, turnover history, etc.
    """
    symbols = list(closes.columns)
    n_bars = len(closes)
    idx = closes.index

    # Per-asset simple returns for PnL accounting. We use simple returns
    # (not log) because weights represent a fraction of equity and
    # portfolio_ret = sum(weight_i * simple_ret_i) is exact for one period.
    simple_rets = closes.pct_change().fillna(0.0)

    # Cost in fractional terms per unit of turnover, per symbol.
    cost_frac = np.array([
        (costs.get(s, DEFAULT_COSTS)[0] + costs.get(s, DEFAULT_COSTS)[1]) * 1e-4
        for s in symbols
    ])

    # State
    weights = np.zeros(len(symbols))
    equity = np.empty(n_bars)
    equity[0] = STARTING_CASH
    daily_returns = np.zeros(n_bars)

    turnovers: list[float] = []
    n_position_changes = 0
    long_counter: Counter[str] = Counter()
    short_counter: Counter[str] = Counter()
    n_rebalances = 0

    # First rebalance happens as soon as we have `lookback_bars` of history.
    # We rebalance at bar index t if (t - first_rebal_idx) % rebalance_bars == 0
    # and t >= lookback_bars.
    first_rebal_idx = lookback_bars

    closes_arr = closes.to_numpy()

    for t in range(n_bars):
        # Step 1: apply today's returns to existing weights (open-to-close).
        if t > 0:
            r = simple_rets.iloc[t].to_numpy()
            port_ret = float(np.dot(weights, r))
            equity[t] = equity[t - 1] * (1.0 + port_ret)
            daily_returns[t] = port_ret
        # Step 2: rebalance at close on scheduled days.
        is_rebal_day = (
            t >= first_rebal_idx
            and (t - first_rebal_idx) % rebalance_bars == 0
        )
        if not is_rebal_day:
            continue

        # Compute signal using ONLY information with index <= t.
        # close[t - skip_bars] and close[t - lookback_bars] are both <= t.
        past_close = closes_arr[t - skip_bars]       # ~1 month ago
        old_close = closes_arr[t - lookback_bars]    # ~12 months ago
        with np.errstate(divide="ignore", invalid="ignore"):
            signal = (past_close - old_close) / old_close

        # Mask out instruments without valid history at t-lookback or t-skip.
        valid = np.isfinite(signal) & np.isfinite(past_close) & np.isfinite(old_close)
        # Also require the asset to be "live" at t (close not NaN).
        valid &= np.isfinite(closes_arr[t])

        if valid.sum() < top_k * (2 if long_short else 1):
            continue

        valid_idx = np.where(valid)[0]
        sig_valid = signal[valid_idx]

        # Rank: descending by signal. argsort of -sig gives highest first.
        order = valid_idx[np.argsort(-sig_valid, kind="stable")]
        top = order[:top_k]
        bottom = order[-top_k:] if long_short else np.array([], dtype=int)

        new_weights = np.zeros(len(symbols))
        new_weights[top] = 1.0 / top_k
        if long_short:
            new_weights[bottom] = -1.0 / top_k

        # Turnover in weight space (gross change).
        dw = new_weights - weights
        turnover = float(np.sum(np.abs(dw)))
        turnovers.append(turnover)

        # Per-asset cost: |dw_i| * cost_frac_i, deducted from equity.
        cost_drag = float(np.sum(np.abs(dw) * cost_frac))
        equity[t] *= (1.0 - cost_drag)
        daily_returns[t] -= cost_drag

        # Track position changes (assets whose weight sign changed or went to/from 0).
        n_position_changes += int(np.sum(np.abs(dw) > 1e-12))

        # Diagnostic counters.
        for i in top:
            long_counter[symbols[i]] += 1
        for i in bottom:
            short_counter[symbols[i]] += 1

        weights = new_weights
        n_rebalances += 1

    return {
        "equity": equity,
        "daily_returns": daily_returns,
        "turnovers": turnovers,
        "n_position_changes": n_position_changes,
        "n_rebalances": n_rebalances,
        "long_counter": long_counter,
        "short_counter": short_counter,
        "index": idx,
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def max_drawdown(equity: np.ndarray) -> float:
    running_max = np.maximum.accumulate(equity)
    dd = (equity - running_max) / running_max
    return float(dd.min())


def annualized_sharpe(daily_returns: np.ndarray) -> float:
    # Exclude leading zeros before the first rebalance to avoid biasing std low.
    nonzero = np.flatnonzero(daily_returns)
    if nonzero.size == 0:
        return 0.0
    start = nonzero[0]
    r = daily_returns[start:]
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(BARS_PER_YEAR))


def years_elapsed(index: pd.DatetimeIndex, equity: np.ndarray) -> float:
    # From first non-zero equity-change bar to last bar.
    return (index[-1] - index[0]).days / 365.25


def report_variant(name: str, res: dict, years: float) -> None:
    eq = res["equity"]
    total_ret = (eq[-1] / eq[0] - 1.0) * 100.0
    dd = max_drawdown(eq) * 100.0
    sharpe = annualized_sharpe(res["daily_returns"])
    avg_turnover = float(np.mean(res["turnovers"])) if res["turnovers"] else 0.0
    trades_per_year = res["n_position_changes"] / years if years > 0 else 0.0

    print(f"  {name}")
    print(f"    Total return       : {total_ret:+.2f}%")
    print(f"    Max drawdown       : {dd:+.2f}%")
    print(f"    Annualized Sharpe  : {sharpe:.4f}")
    print(f"    Rebalances         : {res['n_rebalances']}")
    print(f"    Position changes   : {res['n_position_changes']}")
    print(f"    Trades per year    : {trades_per_year:.2f}")
    print(f"    Avg turnover / rbl : {avg_turnover:.4f}")
    print(f"    Final equity       : ${eq[-1]:,.2f}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    section("Loading data")
    dataframes: dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        df = load_data(sym)
        if df is None or len(df) < 400:
            if df is not None:
                print(f"  {sym:<8s}  skipped ({len(df)} bars -- need >= 400)")
            continue
        dataframes[sym] = df
        print(f"  {sym:<8s}  {len(df):>5,} bars  "
              f"{df.index[0].date()} -> {df.index[-1].date()}")

    if len(dataframes) < TOP_K * 2 + 1:
        print(f"Need at least {TOP_K * 2 + 1} instruments; "
              f"got {len(dataframes)}.")
        sys.exit(1)

    symbols = sorted(dataframes.keys())
    print(f"\n  {len(symbols)} instruments loaded")

    # ------------------------------------------------------------------
    section("Building aligned business-day close panel")
    # ------------------------------------------------------------------

    # Build a common business-day (B) index spanning the overlapping era.
    # We start at the latest "first valid close" across all symbols once at
    # least the first LOOKBACK_BARS bars of every surviving asset are
    # available. Assets without lookback history at t simply get NaN signal
    # and are excluded from that rebalance.
    start_ts = pd.Timestamp(START_DATE, tz="UTC")
    end_ts = max(df.index[-1] for df in dataframes.values())
    bidx = pd.date_range(start=start_ts, end=end_ts, freq="B", tz="UTC")

    closes = pd.DataFrame(index=bidx, columns=symbols, dtype=float)
    for sym, df in dataframes.items():
        # Align to business-day index and forward-fill gaps (weekends for
        # crypto, holidays for equities, etc.). Do NOT backfill -- we don't
        # want pre-listing prices.
        s = df["close"].reindex(bidx, method=None)
        s = s.ffill()
        closes[sym] = s
    print(f"  Business-day index: {len(bidx):,} bars "
          f"({bidx[0].date()} -> {bidx[-1].date()})")
    print(f"  Close panel shape : {closes.shape}")
    print(f"  NaN counts per sym (pre-listing burn-in only):")
    for sym in symbols:
        nan_ct = int(closes[sym].isna().sum())
        print(f"    {sym:<8s}  {nan_ct:>4d} NaN")

    # ------------------------------------------------------------------
    section("Running cross-sectional momentum (K=5)")
    # ------------------------------------------------------------------

    years = (bidx[-1] - bidx[0]).days / 365.25
    print(f"  Simulation span: {years:.2f} years")
    print(f"  Lookback {LOOKBACK_BARS} bars, skip {SKIP_BARS} bars, "
          f"rebalance every {REBALANCE_BARS} bars")
    print(f"  Signal at t: (close[t-{SKIP_BARS}] - close[t-{LOOKBACK_BARS}]) "
          f"/ close[t-{LOOKBACK_BARS}]   "
          f"(uses only closes with index <= t -> no lookahead)\n")

    lo = run_xs_momentum(
        closes, COSTS_BY_SYMBOL, top_k=TOP_K, long_short=False,
    )
    ls = run_xs_momentum(
        closes, COSTS_BY_SYMBOL, top_k=TOP_K, long_short=True,
    )

    report_variant("Long-only  (top-5)", lo, years)
    report_variant("Long-short (top-5 / bottom-5)", ls, years)

    # ------------------------------------------------------------------
    section("Equal-weight buy-and-hold benchmark (all 24)")
    # ------------------------------------------------------------------

    # EW B&H on the same aligned panel: weights = 1/N on all live assets
    # from day 0, reinvesting simple returns.
    simple_rets = closes.pct_change().fillna(0.0)
    # Only include assets once they're live (ffill exposes NaN in burn-in).
    live_mask = closes.notna().astype(float)
    # Re-normalize weights daily across live assets.
    live_count = live_mask.sum(axis=1).replace(0, np.nan)
    weights_ew = live_mask.div(live_count, axis=0).fillna(0.0)
    # Use yesterday's weights applied to today's returns.
    port_ret_ew = (weights_ew.shift(1).fillna(0.0) * simple_rets).sum(axis=1)
    eq_ew = STARTING_CASH * (1.0 + port_ret_ew).cumprod().to_numpy()

    bnh_ret = (eq_ew[-1] / eq_ew[0] - 1.0) * 100.0
    bnh_dd = max_drawdown(eq_ew) * 100.0
    bnh_sharpe = annualized_sharpe(port_ret_ew.to_numpy())
    print(f"  Total return       : {bnh_ret:+.2f}%")
    print(f"  Max drawdown       : {bnh_dd:+.2f}%")
    print(f"  Annualized Sharpe  : {bnh_sharpe:.4f}")
    print(f"  Final equity       : ${eq_ew[-1]:,.2f}")

    # ------------------------------------------------------------------
    section("Summary")
    # ------------------------------------------------------------------

    def quick(name: str, eq: np.ndarray, daily: np.ndarray) -> None:
        ret = (eq[-1] / eq[0] - 1.0) * 100.0
        dd = max_drawdown(eq) * 100.0
        sh = annualized_sharpe(daily)
        print(f"  {name:<28s}  Ret {ret:>+8.2f}%   "
              f"DD {dd:>+7.2f}%   Sharpe {sh:>+7.4f}")

    quick("XS-MOM long-only  (K=5)", lo["equity"], lo["daily_returns"])
    quick("XS-MOM long-short (K=5)", ls["equity"], ls["daily_returns"])
    quick("B&H equal-weight", eq_ew, port_ret_ew.to_numpy())

    # ------------------------------------------------------------------
    section("Diagnostic: most frequently selected instruments")
    # ------------------------------------------------------------------

    print("Long-short variant -- top-5 long bucket (most frequent picks):")
    for sym, n in ls["long_counter"].most_common(5):
        pct = n / ls["n_rebalances"] * 100.0
        print(f"  {sym:<8s}  picked {n:>3d} / {ls['n_rebalances']} rebalances ({pct:5.1f}%)")

    print("\nLong-short variant -- bottom-5 short bucket (most frequent picks):")
    for sym, n in ls["short_counter"].most_common(5):
        pct = n / ls["n_rebalances"] * 100.0
        print(f"  {sym:<8s}  picked {n:>3d} / {ls['n_rebalances']} rebalances ({pct:5.1f}%)")

    print("\nLong-only variant -- top-5 long bucket (most frequent picks):")
    for sym, n in lo["long_counter"].most_common(5):
        pct = n / lo["n_rebalances"] * 100.0
        print(f"  {sym:<8s}  picked {n:>3d} / {lo['n_rebalances']} rebalances ({pct:5.1f}%)")

    print("\nDone.")


if __name__ == "__main__":
    main()
