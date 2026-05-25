#!/usr/bin/env python3
"""
Cross-Sectional Momentum (XS-mom) long-only validation harness.

Refactors the simulation logic from ``examples/xs_momentum_demo.py`` into a
callable function and runs three robustness tests:

  1) Regime stability    -- 4 non-overlapping time windows (no cross-window leakage).
  2) Parameter sensitivity -- one-at-a-time sweeps around the baseline.
  3) True holdout        -- IS 2015-2022 vs OOS 2023-2026.

A sanity reconciliation pass first runs the full 2015-2026 period with baseline
params and checks it matches the in-sample numbers from the existing demo
(+130.14%, Sharpe 0.61) within tolerance.
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

from utils import fetch_ohlc


# ---------------------------------------------------------------------------
# Universe and config (verbatim from xs_momentum_demo.py / tsmom_demo.py)
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
FULL_START = "2015-01-01"
FULL_END = "2026-04-18"
STARTING_CASH_DEFAULT = 100_000.0

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

BARS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# Data loading (apply Yahoo OHLC invariants on load)
# ---------------------------------------------------------------------------

def load_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    try:
        raw = fetch_ohlc(symbol, TIMEFRAME, start_date, end_date)
    except Exception as e:
        print(f"  {symbol:<8s}  LOAD FAILED ({e})")
        return None
    if raw.empty:
        return None
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    return df


def section(title: str) -> None:
    print(f"\n{'=' * 80}\n  {title}\n{'=' * 80}\n")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def max_drawdown(equity: np.ndarray) -> float:
    running_max = np.maximum.accumulate(equity)
    dd = (equity - running_max) / running_max
    return float(dd.min())


def annualized_sharpe(daily_returns: np.ndarray) -> float:
    # Exclude leading zeros before the first rebalance, matching xs_momentum_demo.py.
    nonzero = np.flatnonzero(daily_returns)
    if nonzero.size == 0:
        return 0.0
    start = nonzero[0]
    r = daily_returns[start:]
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(BARS_PER_YEAR))


# ---------------------------------------------------------------------------
# Refactored simulation: callable function matching the requested signature.
# ---------------------------------------------------------------------------

def run_xs_momentum(
    dataframes: dict[str, pd.DataFrame],
    start_date: str,
    end_date: str,
    lookback_bars: int = 252,
    skip_bars: int = 21,
    rebalance_bars: int = 21,
    top_k: int = 5,
    bottom_k: int = 0,  # 0 = long-only; >0 = long-short
    starting_cash: float = 100_000.0,
    costs_bps: dict[str, tuple[float, float]] | None = None,
) -> dict:
    """Run a cross-sectional momentum simulation on a window of data.

    The function slices each dataframe to ``[start_date, end_date]`` FIRST and
    builds the aligned business-day panel from that slice, so no data outside
    the window can leak into the signal (even via reindex / ffill).

    Returns
    -------
    dict
        {"equity_curve", "total_return", "sharpe", "max_dd", "turnover_mean",
         "rebalance_count", "index", "daily_returns"}.
    """
    if costs_bps is None:
        costs_bps = {}

    long_short = bottom_k > 0

    start_ts = pd.Timestamp(start_date, tz="UTC")
    end_ts = pd.Timestamp(end_date, tz="UTC")

    # --- Slice every dataframe to the window BEFORE reindexing/ffill.
    # This guarantees no information from outside [start, end] can enter the
    # aligned panel (ffill can only propagate forward within the slice).
    sliced: dict[str, pd.DataFrame] = {}
    for sym, df in dataframes.items():
        sub = df.loc[(df.index >= start_ts) & (df.index <= end_ts)]
        if not sub.empty:
            sliced[sym] = sub

    min_needed = top_k * (2 if long_short else 1)
    if len(sliced) < min_needed + 1:
        return {
            "equity_curve": np.array([starting_cash]),
            "total_return": 0.0,
            "sharpe": 0.0,
            "max_dd": 0.0,
            "turnover_mean": 0.0,
            "rebalance_count": 0,
            "index": pd.DatetimeIndex([start_ts]),
            "daily_returns": np.zeros(1),
        }

    symbols = sorted(sliced.keys())

    # Build a common business-day (B) index from the per-window slice.
    panel_start = min(d.index[0] for d in sliced.values())
    panel_start = max(panel_start, start_ts)
    panel_end = max(d.index[-1] for d in sliced.values())
    panel_end = min(panel_end, end_ts)
    bidx = pd.date_range(start=panel_start, end=panel_end, freq="B", tz="UTC")

    closes = pd.DataFrame(index=bidx, columns=symbols, dtype=float)
    for sym, df in sliced.items():
        s = df["close"].reindex(bidx, method=None)
        s = s.ffill()  # forward-fill inside the window only; no lookahead.
        closes[sym] = s

    n_bars = len(closes)
    idx = closes.index
    simple_rets = closes.pct_change().fillna(0.0)
    closes_arr = closes.to_numpy()

    cost_frac = np.array([
        (costs_bps.get(s, DEFAULT_COSTS)[0] + costs_bps.get(s, DEFAULT_COSTS)[1]) * 1e-4
        for s in symbols
    ])

    weights = np.zeros(len(symbols))
    equity = np.empty(n_bars)
    equity[0] = starting_cash
    daily_returns = np.zeros(n_bars)

    turnovers: list[float] = []
    n_rebalances = 0

    first_rebal_idx = lookback_bars

    for t in range(n_bars):
        if t > 0:
            r = simple_rets.iloc[t].to_numpy()
            port_ret = float(np.dot(weights, r))
            equity[t] = equity[t - 1] * (1.0 + port_ret)
            daily_returns[t] = port_ret

        is_rebal_day = (
            t >= first_rebal_idx
            and (t - first_rebal_idx) % rebalance_bars == 0
        )
        if not is_rebal_day:
            continue

        # Signal uses only closes with index <= t (no lookahead).
        past_close = closes_arr[t - skip_bars]
        old_close = closes_arr[t - lookback_bars]
        with np.errstate(divide="ignore", invalid="ignore"):
            signal = (past_close - old_close) / old_close

        valid = np.isfinite(signal) & np.isfinite(past_close) & np.isfinite(old_close)
        valid &= np.isfinite(closes_arr[t])

        need = top_k + (bottom_k if long_short else 0)
        if valid.sum() < need:
            continue

        valid_idx = np.where(valid)[0]
        sig_valid = signal[valid_idx]
        order = valid_idx[np.argsort(-sig_valid, kind="stable")]

        top = order[:top_k]
        if long_short:
            bottom = order[-bottom_k:]
        else:
            bottom = np.array([], dtype=int)

        new_weights = np.zeros(len(symbols))
        new_weights[top] = 1.0 / top_k
        if long_short:
            new_weights[bottom] = -1.0 / bottom_k

        dw = new_weights - weights
        turnover = float(np.sum(np.abs(dw)))
        turnovers.append(turnover)

        cost_drag = float(np.sum(np.abs(dw) * cost_frac))
        equity[t] *= (1.0 - cost_drag)
        daily_returns[t] -= cost_drag

        weights = new_weights
        n_rebalances += 1

    total_return = float(equity[-1] / equity[0] - 1.0)
    sharpe = annualized_sharpe(daily_returns)
    mdd = max_drawdown(equity)
    turnover_mean = float(np.mean(turnovers)) if turnovers else 0.0

    return {
        "equity_curve": equity,
        "total_return": total_return,
        "sharpe": sharpe,
        "max_dd": mdd,
        "turnover_mean": turnover_mean,
        "rebalance_count": n_rebalances,
        "index": idx,
        "daily_returns": daily_returns,
    }


# ---------------------------------------------------------------------------
# Main: load once, slice per window.
# ---------------------------------------------------------------------------

def main() -> None:
    section("Loading data (full span)")
    dataframes: dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        df = load_data(sym, FULL_START, FULL_END)
        if df is None or len(df) < 400:
            if df is not None:
                print(f"  {sym:<8s}  skipped ({len(df)} bars -- need >= 400)")
            continue
        dataframes[sym] = df
        print(f"  {sym:<8s}  {len(df):>5,} bars  "
              f"{df.index[0].date()} -> {df.index[-1].date()}")
    print(f"\n  {len(dataframes)} instruments loaded")

    # ------------------------------------------------------------------
    section("Sanity reconciliation: full 2015-2026 baseline")
    # ------------------------------------------------------------------
    print("  Running baseline (lookback=252, skip=21, rebal=21, top_k=5, bottom_k=0)")
    print(f"  Window: {FULL_START} -> {FULL_END}\n")

    base = run_xs_momentum(
        dataframes,
        start_date=FULL_START,
        end_date=FULL_END,
        lookback_bars=252,
        skip_bars=21,
        rebalance_bars=21,
        top_k=5,
        bottom_k=0,
        starting_cash=STARTING_CASH_DEFAULT,
        costs_bps=COSTS_BY_SYMBOL,
    )
    print(f"  Total return   : {base['total_return'] * 100:+.2f}%")
    print(f"  Sharpe         : {base['sharpe']:.4f}")
    print(f"  Max DD         : {base['max_dd'] * 100:+.2f}%")
    print(f"  Rebalances     : {base['rebalance_count']}")
    print(f"  Avg turnover   : {base['turnover_mean']:.4f}")

    EXPECTED_RET = 130.14
    EXPECTED_SHARPE = 0.61
    ret_diff = base["total_return"] * 100 - EXPECTED_RET
    sh_diff = base["sharpe"] - EXPECTED_SHARPE
    print(f"\n  Expected (demo): +{EXPECTED_RET:.2f}%, Sharpe {EXPECTED_SHARPE:.2f}")
    print(f"  Diff           : ret {ret_diff:+.2f}pp, Sharpe {sh_diff:+.3f}")

    # Demo ran to 2026-12-31 end; we run to 2026-04-18 OOS cutoff, so small
    # drift is expected. Flag only if gross mismatch.
    if abs(ret_diff) > 15.0 or abs(sh_diff) > 0.15:
        print("\n  WARNING: large deviation from demo; investigate before"
              " trusting validation results.")
    else:
        print("  OK: refactored function agrees with demo within tolerance.")

    # ------------------------------------------------------------------
    section("Test 1: Regime stability (4 non-overlapping windows)")
    # ------------------------------------------------------------------

    # Split 2015-01-01 -> 2026-04-18 into 4 roughly-equal windows (~2.83y each).
    windows = [
        ("2015-01-01", "2017-10-15"),
        ("2017-10-16", "2020-07-31"),
        ("2020-08-01", "2023-05-15"),
        ("2023-05-16", "2026-04-18"),
    ]

    print(f"  {'Window':<28s} {'Return %':>10s} {'Sharpe':>8s} "
          f"{'MaxDD %':>10s} {'Rebals':>7s}")
    print("  " + "-" * 70)
    win_results = []
    for ws, we in windows:
        r = run_xs_momentum(
            dataframes,
            start_date=ws,
            end_date=we,
            lookback_bars=252,
            skip_bars=21,
            rebalance_bars=21,
            top_k=5,
            bottom_k=0,
            starting_cash=STARTING_CASH_DEFAULT,
            costs_bps=COSTS_BY_SYMBOL,
        )
        win_results.append((ws, we, r))
        label = f"{ws} -> {we}"
        print(f"  {label:<28s} {r['total_return'] * 100:>+9.2f}% "
              f"{r['sharpe']:>+8.3f} {r['max_dd'] * 100:>+9.2f}% "
              f"{r['rebalance_count']:>7d}")

    print("\n  Note: window 1's 252-bar lookback means signals only start")
    print("  ~month 13 into the window (about mid-Jan 2016). By design.")

    n_pos_sharpe = sum(1 for _, _, r in win_results if r["sharpe"] > 0)
    print(f"\n  Windows with Sharpe > 0: {n_pos_sharpe}/4")

    # ------------------------------------------------------------------
    section("Test 2: Parameter sensitivity (full period, one-at-a-time)")
    # ------------------------------------------------------------------

    def sweep(name: str, key: str, values: list[int]) -> list[tuple[int, float, float]]:
        print(f"\n  Sweeping {name}:")
        print(f"  {'Value':>7s} {'Return %':>10s} {'Sharpe':>8s} {'MaxDD %':>10s}")
        print("  " + "-" * 40)
        results = []
        baseline = dict(
            lookback_bars=252, skip_bars=21, rebalance_bars=21,
            top_k=5, bottom_k=0,
        )
        for v in values:
            params = dict(baseline)
            params[key] = v
            r = run_xs_momentum(
                dataframes,
                start_date=FULL_START,
                end_date=FULL_END,
                starting_cash=STARTING_CASH_DEFAULT,
                costs_bps=COSTS_BY_SYMBOL,
                **params,
            )
            results.append((v, r["total_return"] * 100, r["sharpe"], r["max_dd"] * 100))
            marker = "  <- baseline" if v == baseline[key] else ""
            print(f"  {v:>7d} {r['total_return'] * 100:>+9.2f}% "
                  f"{r['sharpe']:>+8.3f} {r['max_dd'] * 100:>+9.2f}%{marker}")
        return results

    lb_res = sweep("lookback_bars", "lookback_bars", [126, 189, 252, 315, 378])
    sk_res = sweep("skip_bars", "skip_bars", [0, 10, 21, 42])
    rb_res = sweep("rebalance_bars", "rebalance_bars", [10, 21, 42, 63])
    tk_res = sweep("top_k", "top_k", [3, 5, 7, 10])

    def plateau_verdict(name: str, results: list, default_val: int) -> tuple[str, bool]:
        """Robust if default isn't the unique winner AND peer Sharpes are within 0.25."""
        sharpes = [r[2] for r in results]
        default_sharpe = next(r[2] for r in results if r[0] == default_val)
        max_sh = max(sharpes)
        # Robust: default is not strictly the peak by a big margin AND
        # at least 2 neighbors within 0.2 Sharpe of the default.
        neighbors_close = sum(
            1 for r in results
            if r[0] != default_val and abs(r[2] - default_sharpe) <= 0.2
        )
        is_robust = (default_sharpe <= max_sh) and neighbors_close >= 2
        # Additional guard: if default is the peak by >0.25 over every other, fragile.
        peak_gap = default_sharpe - max(r[2] for r in results if r[0] != default_val)
        if peak_gap > 0.25:
            is_robust = False
        return name, is_robust

    sensitivity = [
        plateau_verdict("lookback", lb_res, 252),
        plateau_verdict("skip", sk_res, 21),
        plateau_verdict("rebalance", rb_res, 21),
        plateau_verdict("top_k", tk_res, 5),
    ]

    # ------------------------------------------------------------------
    section("Test 3: True holdout (IS 2015-2022 vs OOS 2023-2026)")
    # ------------------------------------------------------------------

    is_window = ("2015-01-01", "2022-12-31")
    oos_window = ("2023-01-01", "2026-04-18")

    is_res = run_xs_momentum(
        dataframes,
        start_date=is_window[0], end_date=is_window[1],
        lookback_bars=252, skip_bars=21, rebalance_bars=21,
        top_k=5, bottom_k=0,
        starting_cash=STARTING_CASH_DEFAULT,
        costs_bps=COSTS_BY_SYMBOL,
    )
    oos_res = run_xs_momentum(
        dataframes,
        start_date=oos_window[0], end_date=oos_window[1],
        lookback_bars=252, skip_bars=21, rebalance_bars=21,
        top_k=5, bottom_k=0,
        starting_cash=STARTING_CASH_DEFAULT,
        costs_bps=COSTS_BY_SYMBOL,
    )

    print(f"  {'Period':<28s} {'Return %':>10s} {'Sharpe':>8s} {'MaxDD %':>10s}")
    print("  " + "-" * 60)
    print(f"  IS  {is_window[0]}->{is_window[1]}  "
          f"{is_res['total_return'] * 100:>+9.2f}% "
          f"{is_res['sharpe']:>+8.3f} {is_res['max_dd'] * 100:>+9.2f}%")
    print(f"  OOS {oos_window[0]}->{oos_window[1]}  "
          f"{oos_res['total_return'] * 100:>+9.2f}% "
          f"{oos_res['sharpe']:>+8.3f} {oos_res['max_dd'] * 100:>+9.2f}%")

    degradation = is_res["sharpe"] - oos_res["sharpe"]
    print(f"\n  Sharpe degradation (IS - OOS): {degradation:+.3f}")
    if degradation < 0.2:
        holdout_tag = "robust"
    elif degradation < 0.5:
        holdout_tag = "some overfitting"
    else:
        holdout_tag = "heavily overfit"
    print(f"  Tag: {holdout_tag}")

    # ------------------------------------------------------------------
    section("VERDICT")
    # ------------------------------------------------------------------

    # Decide param-sensitivity labels per parameter.
    param_tags = []
    for name, robust in sensitivity:
        param_tags.append(f"{name}={'robust' if robust else 'fragile'}")
    sensitivity_str = ", ".join(param_tags)
    all_params_robust = all(r for _, r in sensitivity)

    # Overall decision matrix.
    regime_ok = n_pos_sharpe >= 3
    holdout_ok = degradation < 0.2
    holdout_warn = 0.2 <= degradation < 0.5

    if regime_ok and all_params_robust and holdout_ok:
        overall = "KEEP"
    elif (not regime_ok and n_pos_sharpe <= 1) or degradation >= 0.5:
        overall = "REJECT"
    else:
        overall = "INVESTIGATE"

    print("VERDICT")
    print("=======")
    print(f"Regime stability:  Sharpe positive in {n_pos_sharpe}/4 windows")
    print(f"Param sensitivity: {sensitivity_str}")
    print(f"Holdout:           IS Sharpe {is_res['sharpe']:.2f}, "
          f"OOS Sharpe {oos_res['sharpe']:.2f}, degradation {degradation:+.2f} "
          f"({holdout_tag})")
    print(f"Overall:           {overall}")

    print("\nDone.")


if __name__ == "__main__":
    main()
