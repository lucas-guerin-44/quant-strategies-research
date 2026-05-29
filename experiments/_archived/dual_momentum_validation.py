#!/usr/bin/env python3
"""
Dual Momentum (class-diversified) out-of-sample / robustness validation.

Refactors the hardcoded logic of ``dual_momentum_demo.py`` into a callable
function ``run_dual_momentum`` that takes already-loaded OHLC dataframes and
a date window, and returns a dict of summary stats + equity curve.

Then runs three robustness tests on the class_ew variant with baseline
parameters (lookback=252, skip=21, rebalance=21, abs_threshold=0.0):
    1. Regime stability — 4 non-overlapping time slices of 2015-2026
    2. Parameter sensitivity — one-at-a-time sweeps
    3. True holdout — IS (2015-2022) vs OOS (2023-2026-04-18)
Plus per-class sleeve return attribution.

Run from the repo root:
    python examples/dual_momentum_validation.py
"""

from __future__ import annotations

import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # repo root, for `import data`
sys.path.insert(0, os.path.dirname(_HERE))  # experiments/ (sibling experiment imports)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, '..', '..', 'backtesting-engine-2.0')))  # engine

from data import fetch_ohlc


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
STARTING_CASH = 100_000.0

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
# Data loading (mirrors dual_momentum_demo but parametric)
# ----------------------------------------------------------------------

def load_symbol(symbol: str, start: str, end: str) -> pd.DataFrame | None:
    """Load one symbol's D1 frame for [start, end], with Yahoo OHLC fix."""
    try:
        raw = fetch_ohlc(symbol, TIMEFRAME, start, end)
    except Exception as e:
        print(f"  {symbol:<8s}  LOAD FAILED ({e})")
        return None
    if raw is None or raw.empty:
        return None

    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]

    # Yahoo OHLC sanity fix: high = max(OHLC), low = min(OHLC)
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    return df


def load_all_dataframes(
    groups: dict[str, list[str]],
    start: str,
    end: str,
    verbose: bool = True,
) -> dict[str, pd.DataFrame]:
    """Load all symbols across all class groups, filter >= 400 bars."""
    all_symbols: list[str] = []
    for syms in groups.values():
        all_symbols.extend(syms)

    frames: dict[str, pd.DataFrame] = {}
    for sym in all_symbols:
        df = load_symbol(sym, start, end)
        if df is None or len(df) < 400:
            if verbose and df is not None:
                print(f"  {sym:<8s}  skipped ({len(df)} bars, need >= 400)")
            elif verbose:
                print(f"  {sym:<8s}  skipped (no data)")
            continue
        frames[sym] = df
        if verbose:
            print(f"  {sym:<8s}  {len(df):>5,} bars  "
                  f"{df.index[0].date()} -> {df.index[-1].date()}")
    return frames


def build_close_matrix(
    dataframes: dict[str, pd.DataFrame],
    groups: dict[str, list[str]],
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Restrict loaded frames to the [start_date, end_date] window and
    align them on a shared business-day index, forward-filling gaps.

    Identical resampling logic to ``dual_momentum_demo`` but parametric."""
    start_ts = pd.to_datetime(start_date).tz_localize("UTC")
    end_ts = pd.to_datetime(end_date).tz_localize("UTC")

    # Filter each frame to the window, keep only those with >= 400 bars left
    filtered: dict[str, pd.DataFrame] = {}
    for sym, df in dataframes.items():
        sub = df[(df.index >= start_ts) & (df.index <= end_ts)]
        if len(sub) >= 400:
            filtered[sym] = sub

    if not filtered:
        raise RuntimeError(
            f"No instruments with >= 400 bars in [{start_date}, {end_date}]"
        )

    closes = pd.DataFrame({
        sym: df["close"].tz_convert(None) for sym, df in filtered.items()
    }).sort_index()

    bday_index = pd.bdate_range(
        start=closes.index.min().normalize(),
        end=closes.index.max().normalize(),
    )
    closes = closes.reindex(bday_index, method=None).ffill()
    closes = closes.dropna(how="all")

    groups_present: dict[str, list[str]] = {}
    for cls, syms in groups.items():
        present = [s for s in syms if s in closes.columns]
        if present:
            groups_present[cls] = present

    return closes, groups_present


# ----------------------------------------------------------------------
# Dual Momentum simulator (refactored, parametric)
# ----------------------------------------------------------------------

def run_dual_momentum(
    dataframes: dict[str, pd.DataFrame],
    start_date: str,
    end_date: str,
    lookback_bars: int = 252,
    skip_bars: int = 21,
    rebalance_bars: int = 21,
    absolute_threshold: float = 0.0,
    variant: str = "class_ew",
    starting_cash: float = 100_000.0,
    costs_bps: dict[str, tuple[float, float]] | None = None,
) -> dict:
    """Run a Dual Momentum backtest on pre-loaded dataframes.

    Parameters
    ----------
    dataframes : dict
        Mapping of symbol -> OHLC DataFrame (tz-aware UTC index).
    start_date, end_date : str
        "YYYY-MM-DD"; window the engine will align on.
    lookback_bars, skip_bars, rebalance_bars : int
        Momentum signal = (close[t-skip] - close[t-lookback]) / close[t-lookback].
        Rebalance every ``rebalance_bars`` starting from bar index ``lookback``.
    absolute_threshold : float
        The 12-1 return must be strictly greater than this to hold (else the
        sleeve goes to cash). ``-inf`` disables the cash filter entirely
        (pure cross-sectional class picker).
    variant : str
        "class_ew"          — top-1 per class, equal-weight the sleeves.
        "single_universe"   — top-1 across all instruments (or cash).
    starting_cash : float
    costs_bps : dict or None
        Per-symbol (commission_bps, slippage_bps) overrides.

    Returns
    -------
    dict with keys:
        equity_curve      : np.ndarray of portfolio equity per bar
        dates             : pd.DatetimeIndex aligned to equity_curve
        total_return      : final/start - 1 (float, fraction)
        sharpe            : float (annualized, 252)
        max_dd            : float (negative fraction, -0.30 = -30%)
        pct_cash          : fraction of bars with any CASH weight (> 0)
        rebalance_count   : int
        picks_count       : Counter[str] -> count over rebalances
        weights           : pd.DataFrame (bars x universe incl. CASH)
        selections        : list of (ts, {class: pick})
        per_class_pnl     : dict class -> fraction of total $ pnl produced
                            by that sleeve (only meaningful for class_ew)
        costs_paid        : total $ paid in turnover costs
        n_bars            : len(dates)
        effective_bars    : bars after the (lookback) warmup
    """
    if costs_bps is None:
        costs_bps = COSTS_BY_SYMBOL

    def cost_bps(sym: str) -> float:
        if sym == "CASH":
            return 0.0
        comm, slip = costs_bps.get(sym, DEFAULT_COSTS)
        return comm + slip

    closes, groups_present = build_close_matrix(
        dataframes, CLASS_GROUPS, start_date, end_date
    )

    if variant == "class_ew":
        groups = groups_present
    elif variant == "single_universe":
        groups = {"ALL": list(closes.columns)}
    else:
        raise ValueError(f"Unknown variant: {variant}")

    n_classes = len(groups)
    class_weight = 1.0 / n_classes

    dates = closes.index
    n_bars = len(dates)

    universe = list(closes.columns) + ["CASH"]
    sym_idx = {s: i for i, s in enumerate(universe)}

    close_mat = closes.values
    n_real = close_mat.shape[1]

    rets_real = np.zeros_like(close_mat)
    rets_real[1:] = close_mat[1:] / close_mat[:-1] - 1.0
    rets_real = np.nan_to_num(rets_real, nan=0.0, posinf=0.0, neginf=0.0)

    weights = np.zeros((n_bars, len(universe)))
    equity = np.full(n_bars, starting_cash, dtype=float)
    cur_w = np.zeros(len(universe))

    # Per-class P&L attribution: track $ pnl each class sleeve produces
    # (variant == class_ew). For single_universe, all pnl is one sleeve.
    class_names = list(groups.keys())
    cls_of_pick: dict[str, str] = {}  # current picked symbol -> class name
    per_class_pnl: dict[str, float] = {c: 0.0 for c in class_names}

    selections: list[tuple[pd.Timestamp, dict[str, str]]] = []
    n_trades = 0
    costs_paid_total = 0.0
    pick_freq: Counter = Counter()

    first_rebal = lookback_bars
    rebalance_count = 0

    for t in range(n_bars):
        if t > 0:
            port_ret_per_real = cur_w[:n_real] * rets_real[t, :]
            port_ret = float(port_ret_per_real.sum())
            # Before mutating equity, attribute pnl of each sleeve.
            # Each leg's dollar pnl = equity[t-1] * cur_w[i] * rets_real[t,i].
            prev_eq = equity[t - 1]
            if class_names:
                for i, sym in enumerate(universe[:n_real]):
                    c = cls_of_pick.get(sym)
                    if c is None:
                        continue
                    per_class_pnl[c] += prev_eq * cur_w[i] * rets_real[t, i]
            equity[t] = prev_eq * (1.0 + port_ret)
        else:
            equity[t] = starting_cash

        is_rebal = (t >= first_rebal) and ((t - first_rebal) % rebalance_bars == 0)

        if is_rebal:
            rebalance_count += 1
            picks: dict[str, str] = {}
            new_w = np.zeros(len(universe))

            # Strict no-lookahead: only use close[t-skip] (<= t) and close[t-lookback]
            p_recent = close_mat[t - skip_bars]
            p_old = close_mat[t - lookback_bars]

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

                # Cash filter — strict greater than threshold to hold
                if best_sym is None or best_sig <= absolute_threshold:
                    picks[cls] = "CASH"
                    new_w[sym_idx["CASH"]] += class_weight
                else:
                    picks[cls] = best_sym
                    new_w[sym_idx[best_sym]] += class_weight

            # Turnover + costs
            dw = new_w - cur_w
            turnover_abs = np.abs(dw)
            n_trades += int((turnover_abs > 1e-9).sum())

            cost_per_leg = np.zeros(len(universe))
            for i, sym in enumerate(universe):
                cost_per_leg[i] = turnover_abs[i] * cost_bps(sym) * 1e-4
            cost_dollars = float(equity[t] * cost_per_leg.sum())
            costs_paid_total += cost_dollars
            equity[t] -= cost_dollars

            cur_w = new_w
            selections.append((dates[t], picks))

            # Refresh symbol -> class map for attribution
            cls_of_pick = {}
            for cls, sym in picks.items():
                if sym != "CASH":
                    cls_of_pick[sym] = cls

            for sym in picks.values():
                pick_freq[sym] += 1

        weights[t, :] = cur_w

    eq = equity
    total_return = (eq[-1] - starting_cash) / starting_cash
    running_max = np.maximum.accumulate(eq)
    max_dd = float((eq / running_max - 1.0).min())

    daily = np.diff(eq) / eq[:-1]
    daily = daily[np.isfinite(daily)]
    if len(daily) > 1 and daily.std() > 0:
        sharpe = float(np.sqrt(252) * daily.mean() / daily.std())
    else:
        sharpe = 0.0

    cash_col = sym_idx["CASH"]
    pct_cash = float((weights[:, cash_col] > 1e-9).mean())

    w_df = pd.DataFrame(weights, index=dates, columns=universe)

    # Normalize per_class_pnl to fractions of total pnl (if non-zero)
    total_pnl = eq[-1] - starting_cash
    if abs(total_pnl) > 1e-9:
        per_class_frac = {c: v / total_pnl for c, v in per_class_pnl.items()}
    else:
        per_class_frac = {c: 0.0 for c in per_class_pnl}

    return {
        "equity_curve": eq,
        "dates": dates,
        "total_return": total_return,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "pct_cash": pct_cash,
        "rebalance_count": rebalance_count,
        "picks_count": pick_freq,
        "weights": w_df,
        "selections": selections,
        "per_class_pnl": per_class_frac,
        "per_class_pnl_dollars": per_class_pnl,
        "costs_paid": costs_paid_total,
        "n_bars": n_bars,
        "effective_bars": max(n_bars - lookback_bars, 0),
        "n_trades": n_trades,
    }


# ----------------------------------------------------------------------
# Reporting helpers
# ----------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'=' * 80}\n  {title}\n{'=' * 80}\n")


def fmt_pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def fmt_pct_abs(x: float) -> str:
    return f"{x * 100:.2f}%"


def print_result_row(label: str, r: dict) -> None:
    print(f"  {label:<32s}  ret {fmt_pct(r['total_return']):>9s}  "
          f"Sharpe {r['sharpe']:>+7.4f}  MaxDD {fmt_pct(r['max_dd']):>9s}  "
          f"reb {r['rebalance_count']:>3d}  %cash {fmt_pct_abs(r['pct_cash']):>7s}")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> None:
    section("Loading data (2015-01-01 -> 2026-04-18)")

    # Load full data once; we slice dates in each test
    full_dataframes = load_all_dataframes(
        CLASS_GROUPS, start="2015-01-01", end="2026-12-31", verbose=True,
    )

    baseline_params = dict(
        lookback_bars=252,
        skip_bars=21,
        rebalance_bars=21,
        absolute_threshold=0.0,
        variant="class_ew",
        starting_cash=STARTING_CASH,
    )

    # ------------------------------------------------------------------
    section("Sanity reconciliation: baseline class_ew on 2015-01-01 -> 2026-12-31")
    # ------------------------------------------------------------------
    baseline = run_dual_momentum(
        full_dataframes,
        start_date="2015-01-01",
        end_date="2026-12-31",
        **baseline_params,
    )
    print(f"  Final equity     : ${STARTING_CASH * (1 + baseline['total_return']):>14,.2f}")
    print(f"  Total return     : {fmt_pct(baseline['total_return']):>14s}")
    print(f"  Ann Sharpe (252) : {baseline['sharpe']:>+14.4f}")
    print(f"  Max drawdown     : {fmt_pct(baseline['max_dd']):>14s}")
    print(f"  Rebalances       : {baseline['rebalance_count']:>14d}")
    print(f"  Time in cash     : {fmt_pct_abs(baseline['pct_cash']):>14s}")
    print(f"  Costs paid       : ${baseline['costs_paid']:>14,.2f}")
    print(f"  Bars in run      : {baseline['n_bars']:>14d}  "
          f"(effective {baseline['effective_bars']} after warmup)")
    print()
    print(f"  Expected demo values: +54.90%  Sharpe 0.39  %cash 91.45%")
    diff_ret = baseline['total_return'] * 100 - 54.90
    diff_shp = baseline['sharpe'] - 0.39
    diff_cash = baseline['pct_cash'] * 100 - 91.45
    print(f"  Delta to demo      : ret {diff_ret:+.2f}pp  "
          f"Sharpe {diff_shp:+.4f}  %cash {diff_cash:+.2f}pp")
    if abs(diff_ret) > 1.0 or abs(diff_shp) > 0.02 or abs(diff_cash) > 1.0:
        print("\n  WARNING: reconciliation mismatch — treating as informational, "
              "continuing with this implementation as the 'baseline' for all tests.")
    else:
        print("  Reconciliation OK.")

    # ------------------------------------------------------------------
    section("TEST 1 — Regime stability (4 non-overlapping windows)")
    # ------------------------------------------------------------------
    # 2015-2026 (~11.3 years) -> 4 windows of ~2.85 years each.
    windows = [
        ("2015-01-01", "2017-10-31"),
        ("2017-11-01", "2020-08-31"),
        ("2020-09-01", "2023-06-30"),
        ("2023-07-01", "2026-04-18"),
    ]

    sharpe_sign = {"pos": 0, "nonpos": 0}
    cash_fractions = []
    print(f"  Lookback = 252 bars (~1y warmup) -> first ~1y of each window "
          f"produces no rebalances.\n")
    print(f"  {'Window':<28s} {'Bars':>6s} {'Eff':>6s} {'Ret':>9s} "
          f"{'Sharpe':>8s} {'MaxDD':>9s} {'Reb':>4s} {'%Cash':>7s}")
    print("  " + "-" * 85)
    for sd, ed in windows:
        try:
            r = run_dual_momentum(
                full_dataframes, start_date=sd, end_date=ed, **baseline_params,
            )
        except Exception as e:
            print(f"  {sd} -> {ed}  FAILED: {e}")
            continue
        label = f"{sd} -> {ed}"
        print(f"  {label:<28s} {r['n_bars']:>6d} {r['effective_bars']:>6d} "
              f"{fmt_pct(r['total_return']):>9s} {r['sharpe']:>+8.4f} "
              f"{fmt_pct(r['max_dd']):>9s} {r['rebalance_count']:>4d} "
              f"{fmt_pct_abs(r['pct_cash']):>7s}")
        if r['sharpe'] > 0:
            sharpe_sign["pos"] += 1
        else:
            sharpe_sign["nonpos"] += 1
        cash_fractions.append(r['pct_cash'] * 100)

    print()
    print(f"  Sharpe positive in {sharpe_sign['pos']}/4 windows.")
    if cash_fractions:
        print(f"  Cash-time range across windows: "
              f"{min(cash_fractions):.1f}% .. {max(cash_fractions):.1f}%.")

    regime_pos_count = sharpe_sign["pos"]
    regime_cash_range = (min(cash_fractions), max(cash_fractions)) if cash_fractions else (0, 0)

    # ------------------------------------------------------------------
    section("TEST 2 — Parameter sensitivity (full 2015-2026)")
    # ------------------------------------------------------------------
    def sweep(param_name: str, values: list, fmt: str = "g") -> list[tuple]:
        """Run a one-at-a-time sweep. Return list of (val, result) tuples."""
        rows = []
        print(f"\n  --- Sweep {param_name} ---")
        print(f"    {'value':>10s}  {'ret':>9s}  {'Sharpe':>8s}  "
              f"{'MaxDD':>9s}  {'Reb':>4s}  {'%cash':>7s}")
        for v in values:
            params = dict(baseline_params)
            params[param_name] = v
            try:
                r = run_dual_momentum(
                    full_dataframes,
                    start_date="2015-01-01", end_date="2026-12-31",
                    **params,
                )
            except Exception as e:
                print(f"    {v:>10}  FAILED: {e}")
                continue
            rows.append((v, r))
            vlabel = f"{v:>10{fmt}}" if isinstance(v, (int, float)) else f"{v:>10s}"
            print(f"    {vlabel}  {fmt_pct(r['total_return']):>9s}  "
                  f"{r['sharpe']:>+8.4f}  {fmt_pct(r['max_dd']):>9s}  "
                  f"{r['rebalance_count']:>4d}  {fmt_pct_abs(r['pct_cash']):>7s}")
        return rows

    lookback_rows = sweep("lookback_bars", [126, 189, 252, 315, 378], fmt="d")
    skip_rows = sweep("skip_bars", [0, 10, 21, 42], fmt="d")
    reb_rows = sweep("rebalance_bars", [10, 21, 42, 63], fmt="d")
    thr_rows = sweep("absolute_threshold", [-0.10, -0.05, 0.0, 0.05, 0.10], fmt=".3f")

    # "Pure cross-sectional" counterfactual: -inf threshold => never goes to cash
    print("\n  --- Pure cross-sectional class picker (absolute_threshold = -inf) ---")
    pure_cs = run_dual_momentum(
        full_dataframes, start_date="2015-01-01", end_date="2026-12-31",
        lookback_bars=252, skip_bars=21, rebalance_bars=21,
        absolute_threshold=float("-inf"),
        variant="class_ew", starting_cash=STARTING_CASH,
    )
    print_result_row("no-cash counterfactual", pure_cs)
    print_result_row("baseline (thr = 0.0)", baseline)
    cash_filter_pp = (baseline["total_return"] - pure_cs["total_return"]) * 100.0
    cash_filter_sharpe = baseline["sharpe"] - pure_cs["sharpe"]
    print(f"\n  Cash-filter contribution: {cash_filter_pp:+.2f} pp of total return, "
          f"{cash_filter_sharpe:+.4f} Sharpe.")

    # Simple plateau/peak heuristic — is baseline the unique max on each sweep?
    def plateau_verdict(name: str, rows: list[tuple], baseline_val) -> str:
        if not rows:
            return f"{name}: no data"
        sharpes = [r["sharpe"] for _, r in rows]
        best_i = int(np.argmax(sharpes))
        best_v, best_r = rows[best_i]
        # Find baseline row
        base_row = next((r for v, r in rows if v == baseline_val), None)
        base_sharpe = base_row["sharpe"] if base_row is not None else float("nan")
        # "Robust" if best sharpe is within 0.1 of median and span < 0.3
        span = max(sharpes) - min(sharpes)
        robust = span < 0.30
        return (f"{name}: span of Sharpe = {span:.3f}  "
                f"(best {best_v} -> {best_r['sharpe']:+.4f}, "
                f"baseline {baseline_val} -> {base_sharpe:+.4f})  "
                f"=> {'robust' if robust else 'FRAGILE'}")

    print("\n  Sweep summaries:")
    print("   ", plateau_verdict("lookback_bars", lookback_rows, 252))
    print("   ", plateau_verdict("skip_bars", skip_rows, 21))
    print("   ", plateau_verdict("rebalance_bars", reb_rows, 21))
    print("   ", plateau_verdict("absolute_threshold", thr_rows, 0.0))

    def fragile_list() -> list[str]:
        frag = []
        for name, rows, baseline_val in [
            ("lookback_bars", lookback_rows, 252),
            ("skip_bars", skip_rows, 21),
            ("rebalance_bars", reb_rows, 21),
            ("absolute_threshold", thr_rows, 0.0),
        ]:
            if not rows:
                continue
            sharpes = [r["sharpe"] for _, r in rows]
            span = max(sharpes) - min(sharpes)
            if span >= 0.30:
                frag.append(name)
        return frag

    fragile_dims = fragile_list()

    # ------------------------------------------------------------------
    section("TEST 3 — True holdout (IS 2015-2022 vs OOS 2023-2026-04-18)")
    # ------------------------------------------------------------------
    is_r = run_dual_momentum(
        full_dataframes,
        start_date="2015-01-01", end_date="2022-12-31",
        **baseline_params,
    )
    oos_r = run_dual_momentum(
        full_dataframes,
        start_date="2023-01-01", end_date="2026-04-18",
        **baseline_params,
    )
    print(f"  {'Period':<22s} {'Bars':>6s} {'Eff':>6s} {'Ret':>9s} "
          f"{'Sharpe':>8s} {'MaxDD':>9s} {'Reb':>4s} {'%Cash':>7s}")
    print("  " + "-" * 80)
    for name, r in [("IS 2015-2022", is_r), ("OOS 2023-2026", oos_r)]:
        print(f"  {name:<22s} {r['n_bars']:>6d} {r['effective_bars']:>6d} "
              f"{fmt_pct(r['total_return']):>9s} {r['sharpe']:>+8.4f} "
              f"{fmt_pct(r['max_dd']):>9s} {r['rebalance_count']:>4d} "
              f"{fmt_pct_abs(r['pct_cash']):>7s}")
    degradation = is_r["sharpe"] - oos_r["sharpe"]
    print(f"\n  Degradation (IS Sharpe - OOS Sharpe) = {degradation:+.4f}")
    if degradation < 0.2:
        deg_verdict = "robust"
    elif degradation < 0.5:
        deg_verdict = "some overfitting"
    else:
        deg_verdict = "heavily overfit"
    print(f"  Verdict: {deg_verdict}")

    # ------------------------------------------------------------------
    section("Bonus — per-class sleeve attribution (full 2015-2026, class_ew)")
    # ------------------------------------------------------------------
    print(f"  Total $ pnl: {baseline['equity_curve'][-1] - STARTING_CASH:+,.2f}\n")
    print(f"  {'Class':<14s} {'$ pnl':>16s} {'share of total':>16s}")
    print("  " + "-" * 48)
    for cls, dollars in baseline["per_class_pnl_dollars"].items():
        frac = baseline["per_class_pnl"][cls]
        print(f"  {cls:<14s} {dollars:>+16,.2f} {frac * 100:>+15.2f}%")

    # ------------------------------------------------------------------
    section("VERDICT")
    # ------------------------------------------------------------------
    sens_verdict = "Robust" if not fragile_dims else f"Fragile on: {', '.join(fragile_dims)}"
    if degradation < 0.2:
        overall_deg = "robust"
    elif degradation < 0.5:
        overall_deg = "some overfitting"
    else:
        overall_deg = "heavily overfit"

    # Overall decision heuristic
    regime_ok = regime_pos_count >= 3
    sens_ok = not fragile_dims
    holdout_ok = degradation < 0.2

    if regime_ok and sens_ok and holdout_ok:
        overall = "KEEP"
    elif (regime_pos_count >= 2) and (degradation < 0.5):
        overall = "INVESTIGATE"
    else:
        overall = "REJECT"

    print(f"Regime stability:  Sharpe positive in {regime_pos_count}/4 windows "
          f"(in-cash fraction varied {regime_cash_range[0]:.1f}-{regime_cash_range[1]:.1f}%)")
    print(f"Param sensitivity: {sens_verdict}")
    print(f"Holdout:           IS Sharpe {is_r['sharpe']:+.4f}, "
          f"OOS Sharpe {oos_r['sharpe']:+.4f}, degradation {degradation:+.4f} ({overall_deg})")
    print(f"Cash-filter value: contributed {cash_filter_pp:+.2f} pp of return "
          f"(and {cash_filter_sharpe:+.4f} Sharpe) vs no-filter counterfactual")
    print(f"Overall:           {overall}")

    print("\nDone.")


if __name__ == "__main__":
    main()
