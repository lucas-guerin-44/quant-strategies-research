#!/usr/bin/env python3
"""
FX short-term mean-reversion strategy (z-score based).

Standalone pandas/numpy simulation: bar-by-bar state machine per pair
(flat / long / short). Intended as a mechanically-independent complement to the
existing XS-momentum strategy (long-horizon, cross-sectional, trend-following).

Universe: 11 FX crosses, D1 bars, 2015-01-01 to 2026-04-18.

Signal:
  ma  = MA_n(close), sd = SD_n(close), z = (close - ma) / sd
  Entry: z < -entry_z (long)  or  z > +entry_z (short)  when flat
  Exit : |z| < 0.25  OR  bars_held >= 10  OR  z moves +1.5 sigma against entry

Position:
  vol-target 15% annualized using 60-day realized vol.
  one position per pair, notional capped at equity_per_slot (1x),
  gross portfolio exposure capped at 1.5x equity.

Costs: 6 bps entry + 6 bps exit.
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

from data import fetch_ohlc
from examples.xs_momentum_validation import run_xs_momentum, load_data as xs_load_data


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

UNIVERSE = [
    "AUDNZD", "NZDCAD", "GBPNZD", "AUDCAD", "CADJPY", "NZDJPY",
    "EURGBP", "EURNOK", "USDZAR", "EURUSD", "GBPUSD",
]

TIMEFRAME = "D1"
FULL_START = "2015-01-01"
FULL_END = "2026-04-18"
STARTING_CASH = 100_000.0

# Baseline strategy params
BASE_MA_WINDOW = 20
BASE_ENTRY_Z = 1.5
EXIT_Z = 0.25
STOP_Z_DELTA = 1.5   # stop triggers when z moves 1.5 sigma further against entry
MAX_HOLD = 10
VOL_TARGET = 0.15
VOL_WINDOW = 60
MAX_NOTIONAL_MULT = 1.0
MAX_GROSS_EXPOSURE = 1.5
COST_BPS_ROUNDTRIP = 12.0  # 6 bps entry + 6 bps exit -> applied on turnover
COST_BPS_PER_SIDE = 6.0

BARS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# Data loader
# ---------------------------------------------------------------------------

def load_fx_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame | None:
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
    nonzero = np.flatnonzero(daily_returns)
    if nonzero.size == 0:
        return 0.0
    start = nonzero[0]
    r = daily_returns[start:]
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(BARS_PER_YEAR))


def cagr(equity: np.ndarray, n_bars: int, bars_per_year: int = BARS_PER_YEAR) -> float:
    if equity[0] <= 0 or equity[-1] <= 0 or n_bars <= 1:
        return 0.0
    years = n_bars / bars_per_year
    return float((equity[-1] / equity[0]) ** (1.0 / years) - 1.0)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def run_mean_reversion(
    dataframes: dict[str, pd.DataFrame],
    start_date: str,
    end_date: str,
    ma_window: int = BASE_MA_WINDOW,
    entry_z: float = BASE_ENTRY_Z,
    exit_z: float = EXIT_Z,
    stop_z_delta: float = STOP_Z_DELTA,
    max_hold: int = MAX_HOLD,
    vol_target: float = VOL_TARGET,
    vol_window: int = VOL_WINDOW,
    max_notional_mult: float = MAX_NOTIONAL_MULT,
    max_gross_exposure: float = MAX_GROSS_EXPOSURE,
    cost_bps_per_side: float = COST_BPS_PER_SIDE,
    starting_cash: float = STARTING_CASH,
) -> dict:
    """Bar-by-bar mean-reversion sim with per-pair state machine.

    Signals and vol are computed on close[t]. Entries/exits are executed at
    close[t] (no lookahead since we use t's close to compute z, and the
    decision happens at the bar boundary). PnL accrues via close-to-close
    returns on the *next* bar given the position notional locked in at t.

    Returns a dict with aggregate metrics and per-pair stats.
    """
    start_ts = pd.Timestamp(start_date, tz="UTC")
    end_ts = pd.Timestamp(end_date, tz="UTC")

    # --- Align on a common business-day index, slice to window first.
    sliced: dict[str, pd.DataFrame] = {}
    for sym, df in dataframes.items():
        sub = df.loc[(df.index >= start_ts) & (df.index <= end_ts)]
        if not sub.empty:
            sliced[sym] = sub

    if not sliced:
        raise ValueError("No data in window.")

    panel_start = max(min(d.index[0] for d in sliced.values()), start_ts)
    panel_end = min(max(d.index[-1] for d in sliced.values()), end_ts)
    bidx = pd.date_range(start=panel_start, end=panel_end, freq="B", tz="UTC")

    symbols = sorted(sliced.keys())
    closes = pd.DataFrame(index=bidx, columns=symbols, dtype=float)
    for sym, df in sliced.items():
        s = df["close"].reindex(bidx, method=None)
        s = s.ffill()
        closes[sym] = s

    # Forward-filled NaNs at the head are still NaN until the first real obs.
    # Rolling stats will return NaN until there's enough history.
    n_bars = len(closes)
    n_syms = len(symbols)

    # --- Precompute rolling stats and returns.
    ma = closes.rolling(ma_window, min_periods=ma_window).mean()
    sd = closes.rolling(ma_window, min_periods=ma_window).std(ddof=1)
    z = (closes - ma) / sd

    simple_rets = closes.pct_change().fillna(0.0)
    vol_ann = simple_rets.rolling(vol_window, min_periods=vol_window).std(ddof=1) * np.sqrt(BARS_PER_YEAR)

    closes_arr = closes.to_numpy()
    z_arr = z.to_numpy()
    rets_arr = simple_rets.to_numpy()
    vol_arr = vol_ann.to_numpy()

    # --- State per pair: 0=flat, 1=long, -1=short
    state = np.zeros(n_syms, dtype=np.int8)
    entry_z_vals = np.zeros(n_syms)   # z at entry, for stop logic
    notional = np.zeros(n_syms)       # $ notional (signed)
    bars_held = np.zeros(n_syms, dtype=np.int32)

    equity = np.empty(n_bars)
    equity[0] = starting_cash
    daily_returns = np.zeros(n_bars)

    equity_per_slot_static = starting_cash / n_syms
    cost_frac = cost_bps_per_side * 1e-4

    # Per-pair bookkeeping
    pair_pnl = {s: 0.0 for s in symbols}
    pair_trades = {s: 0 for s in symbols}
    pair_wins = {s: 0 for s in symbols}
    pair_hold_bars = {s: [] for s in symbols}
    # Open trade tracking: entry_equity_snapshot not needed; we track trade PnL
    # by summing the daily $ PnL contributions from entry to exit.
    open_trade_pnl = np.zeros(n_syms)
    open_trade_hold = np.zeros(n_syms, dtype=np.int32)

    total_trades = 0
    total_wins = 0
    all_hold_bars: list[int] = []

    for t in range(n_bars):
        if t > 0:
            # Apply PnL from positions held at t-1 over the bar t-1 -> t.
            port_pnl_dollars = 0.0
            for i in range(n_syms):
                if state[i] != 0 and np.isfinite(rets_arr[t, i]):
                    pnl_i = notional[i] * rets_arr[t, i]
                    port_pnl_dollars += pnl_i
                    open_trade_pnl[i] += pnl_i
                    open_trade_hold[i] += 1
                    bars_held[i] += 1
            equity[t] = equity[t - 1] + port_pnl_dollars
            daily_returns[t] = port_pnl_dollars / equity[t - 1] if equity[t - 1] > 0 else 0.0
        # If not t==0 we keep equity[t] from above.

        if equity[t] <= 0:
            # Blown up. Zero out and move on.
            equity[t] = max(equity[t], 1e-6)

        # --- Now, at bar t's close, run the state machine: exits then entries.
        equity_per_slot = equity[t] / n_syms
        cost_dollars_total = 0.0

        # Exits
        for i in range(n_syms):
            if state[i] == 0:
                continue
            zi = z_arr[t, i]
            if not np.isfinite(zi):
                # Flatten on bad data to avoid stuck state.
                exit_reason = "nan"
            elif state[i] == 1 and zi < (entry_z_vals[i] - stop_z_delta):
                exit_reason = "stop"
            elif state[i] == -1 and zi > (entry_z_vals[i] + stop_z_delta):
                exit_reason = "stop"
            elif abs(zi) < exit_z:
                exit_reason = "revert"
            elif bars_held[i] >= max_hold:
                exit_reason = "time"
            else:
                exit_reason = None

            if exit_reason is not None:
                # Apply exit cost on the gross notional.
                cost_i = abs(notional[i]) * cost_frac
                cost_dollars_total += cost_i
                # Book the trade.
                realized = open_trade_pnl[i] - cost_i
                # Note: entry cost was already deducted at entry time.
                sym = symbols[i]
                pair_pnl[sym] += realized
                pair_trades[sym] += 1
                total_trades += 1
                hold = int(open_trade_hold[i])
                pair_hold_bars[sym].append(hold)
                all_hold_bars.append(hold)
                # Win if realized > 0 (after both costs)
                if realized > 0:
                    pair_wins[sym] += 1
                    total_wins += 1
                # Clear state
                state[i] = 0
                entry_z_vals[i] = 0.0
                notional[i] = 0.0
                bars_held[i] = 0
                open_trade_pnl[i] = 0.0
                open_trade_hold[i] = 0

        # Entries -- only if currently flat, enough rolling history, and gross
        # exposure budget allows the new position.
        current_gross = float(np.sum(np.abs(notional)))
        for i in range(n_syms):
            if state[i] != 0:
                continue
            zi = z_arr[t, i]
            vi = vol_arr[t, i]
            if not (np.isfinite(zi) and np.isfinite(vi)) or vi <= 0:
                continue

            if zi < -entry_z:
                side = 1
            elif zi > entry_z:
                side = -1
            else:
                continue

            # Vol-target sizing
            raw_notional = equity_per_slot * (vol_target / vi)
            capped = min(raw_notional, equity_per_slot * max_notional_mult)
            if capped <= 0:
                continue

            # Gross exposure cap
            gross_cap_dollars = equity[t] * max_gross_exposure
            room = gross_cap_dollars - current_gross
            if room <= 0:
                continue
            final_notional = min(capped, room)
            if final_notional <= 0:
                continue

            # Open position
            state[i] = side
            entry_z_vals[i] = zi
            notional[i] = side * final_notional
            bars_held[i] = 0
            open_trade_pnl[i] = 0.0
            open_trade_hold[i] = 0
            current_gross += final_notional

            # Entry cost
            cost_dollars_total += final_notional * cost_frac

        # Apply total costs (both exit and entry) incurred at this bar.
        if cost_dollars_total > 0:
            equity[t] -= cost_dollars_total
            # Adjust today's return to reflect costs.
            if t > 0 and equity[t - 1] > 0:
                daily_returns[t] -= cost_dollars_total / equity[t - 1]
            if equity[t] <= 0:
                equity[t] = max(equity[t], 1e-6)

    total_return = float(equity[-1] / equity[0] - 1.0)
    sharpe = annualized_sharpe(daily_returns)
    mdd = max_drawdown(equity)
    cagr_val = cagr(equity, n_bars)
    calmar = (cagr_val / abs(mdd)) if mdd < 0 else 0.0
    win_rate = total_wins / total_trades if total_trades > 0 else 0.0
    avg_hold = float(np.mean(all_hold_bars)) if all_hold_bars else 0.0

    per_pair = []
    for s in symbols:
        n = pair_trades[s]
        wr = pair_wins[s] / n if n > 0 else 0.0
        avg_h = float(np.mean(pair_hold_bars[s])) if pair_hold_bars[s] else 0.0
        per_pair.append({
            "symbol": s,
            "pnl": pair_pnl[s],
            "trades": n,
            "win_rate": wr,
            "avg_hold": avg_h,
        })

    return {
        "equity_curve": equity,
        "index": bidx,
        "daily_returns": daily_returns,
        "total_return": total_return,
        "cagr": cagr_val,
        "sharpe": sharpe,
        "max_dd": mdd,
        "calmar": calmar,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "avg_hold": avg_hold,
        "per_pair": per_pair,
    }


# ---------------------------------------------------------------------------
# Correlation vs XS-momentum
# ---------------------------------------------------------------------------

XS_UNIVERSE = [
    "AUDNZD", "NZDCAD", "GBPNZD", "AUDCAD", "CADJPY", "NZDJPY",
    "EURGBP", "EURNOK", "USDZAR",
    "COCOA", "COFFEE", "SUGAR", "COTTON",
    "EWZ", "FXI", "EWJ",
    "XAUUSD", "USOUSD", "SPX500", "NDX100", "GER40", "BTCUSD",
    "EURUSD", "GBPUSD",
]

XS_COSTS_BY_SYMBOL = {
    "BTCUSD": (10.0, 5.0),
    "XAUUSD": (5.0, 3.0), "USOUSD": (5.0, 3.0),
    "SPX500": (3.0, 1.0), "NDX100": (3.0, 1.0), "GER40": (3.0, 2.0),
    "EURUSD": (2.0, 1.0), "GBPUSD": (2.0, 1.0),
    "COCOA": (8.0, 5.0), "COFFEE": (8.0, 5.0),
    "SUGAR": (8.0, 5.0), "COTTON": (8.0, 5.0),
    "EWZ": (5.0, 3.0), "FXI": (5.0, 3.0), "EWJ": (5.0, 3.0),
}


def compute_correlations(mr_result: dict, xs_result: dict) -> tuple[float, float]:
    mr_rets = pd.Series(mr_result["daily_returns"], index=mr_result["index"], name="mr")
    xs_rets = pd.Series(xs_result["daily_returns"], index=xs_result["index"], name="xs")

    # Align on common dates
    joined = pd.concat([mr_rets, xs_rets], axis=1, join="inner").dropna()
    # Strip leading zeros (before first trade on either side) to reduce noise
    mask = (joined["mr"].cumsum() != 0) | (joined["xs"].cumsum() != 0)
    joined = joined.loc[mask]

    if len(joined) < 20:
        return float("nan"), float("nan")

    daily_corr = float(joined["mr"].corr(joined["xs"]))

    # Monthly correlation: compound to monthly returns
    monthly = (1.0 + joined).resample("ME").prod() - 1.0
    monthly = monthly.dropna()
    if len(monthly) >= 3:
        monthly_corr = float(monthly["mr"].corr(monthly["xs"]))
    else:
        monthly_corr = float("nan")

    return daily_corr, monthly_corr


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    section("Loading FX data")
    fx_data: dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        df = load_fx_data(sym, FULL_START, FULL_END)
        if df is None or len(df) < 200:
            if df is not None:
                print(f"  {sym:<8s}  skipped ({len(df)} bars)")
            continue
        fx_data[sym] = df
        print(f"  {sym:<8s}  {len(df):>5,} bars  "
              f"{df.index[0].date()} -> {df.index[-1].date()}")
    print(f"\n  {len(fx_data)} FX pairs loaded")

    # ------------------------------------------------------------------
    section("Running mean-reversion baseline (ma=20, entry_z=1.5)")
    # ------------------------------------------------------------------

    baseline = run_mean_reversion(
        fx_data,
        start_date=FULL_START,
        end_date=FULL_END,
        ma_window=BASE_MA_WINDOW,
        entry_z=BASE_ENTRY_Z,
    )

    print(f"  Total return   : {baseline['total_return'] * 100:+.2f}%")
    print(f"  CAGR           : {baseline['cagr'] * 100:+.2f}%")
    print(f"  Sharpe         : {baseline['sharpe']:.4f}")
    print(f"  Max DD         : {baseline['max_dd'] * 100:+.2f}%")
    print(f"  Calmar         : {baseline['calmar']:.3f}")
    print(f"  Total trades   : {baseline['total_trades']}")
    print(f"  Win rate       : {baseline['win_rate'] * 100:.1f}%")
    print(f"  Avg hold (bars): {baseline['avg_hold']:.1f}")

    # ------------------------------------------------------------------
    section("Per-pair stats (sorted by P&L contribution)")
    # ------------------------------------------------------------------

    pp = sorted(baseline["per_pair"], key=lambda r: r["pnl"], reverse=True)
    print(f"  {'Symbol':<8s} {'P&L $':>12s} {'Trades':>8s} {'Win%':>7s} {'AvgHold':>8s}")
    print("  " + "-" * 50)
    for r in pp:
        print(f"  {r['symbol']:<8s} {r['pnl']:>+12.2f} {r['trades']:>8d} "
              f"{r['win_rate'] * 100:>6.1f}% {r['avg_hold']:>7.1f}")

    # ------------------------------------------------------------------
    section("Running XS-momentum for correlation benchmark")
    # ------------------------------------------------------------------

    xs_data: dict[str, pd.DataFrame] = {}
    for sym in XS_UNIVERSE:
        df = xs_load_data(sym, FULL_START, FULL_END)
        if df is None or len(df) < 400:
            continue
        xs_data[sym] = df
    print(f"  XS universe loaded: {len(xs_data)} instruments")

    xs_result = run_xs_momentum(
        xs_data,
        start_date=FULL_START,
        end_date=FULL_END,
        lookback_bars=189,
        skip_bars=42,
        rebalance_bars=63,
        top_k=5,
        bottom_k=0,
        starting_cash=STARTING_CASH,
        costs_bps=XS_COSTS_BY_SYMBOL,
    )
    print(f"  XS-mom total return: {xs_result['total_return'] * 100:+.2f}%")
    print(f"  XS-mom Sharpe      : {xs_result['sharpe']:.4f}")

    daily_corr, monthly_corr = compute_correlations(baseline, xs_result)
    print(f"\n  Correlation (daily returns)   : {daily_corr:+.3f}")
    print(f"  Correlation (monthly returns) : {monthly_corr:+.3f}")

    # ------------------------------------------------------------------
    section("MEAN REVERSION SUMMARY")
    # ------------------------------------------------------------------
    print("MEAN REVERSION SUMMARY")
    print("======================")
    print(f"Return:           {baseline['total_return'] * 100:+.2f}%")
    print(f"Sharpe:           {baseline['sharpe']:.4f}")
    print(f"Max DD:           {baseline['max_dd'] * 100:+.2f}%")
    print(f"Calmar:           {baseline['calmar']:.3f}")
    print(f"Trades:           {baseline['total_trades']}")
    print(f"Win rate:         {baseline['win_rate'] * 100:.1f}%")
    print(f"Avg hold:         {baseline['avg_hold']:.1f} bars")
    print("")
    print("Correlation with XS-mom:")
    print(f"  Daily returns:    {daily_corr:+.2f}")
    print(f"  Monthly returns:  {monthly_corr:+.2f}")
    print("")

    abs_daily_corr = abs(daily_corr) if np.isfinite(daily_corr) else 1.0
    if baseline["sharpe"] <= 0:
        verdict = "REJECT"
        reason = "Sharpe <= 0"
    elif abs_daily_corr < 0.3 and baseline["sharpe"] > 0.4:
        verdict = "KEEP"
        reason = "corr < 0.3 AND Sharpe > 0.4 (strong complement)"
    elif abs_daily_corr < 0.3 and baseline["sharpe"] > 0:
        verdict = "MAYBE"
        reason = "corr < 0.3 AND 0 < Sharpe <= 0.4 (weak but uncorrelated)"
    else:
        verdict = "REJECT"
        reason = "correlation too high or Sharpe not positive enough"
    print(f"Verdict: {verdict}")
    print(f"  ({reason})")

    # ------------------------------------------------------------------
    section("Sensitivity grid: entry_z x ma_window")
    # ------------------------------------------------------------------
    entry_zs = [1.0, 1.5, 2.0, 2.5]
    ma_windows = [10, 20, 40]
    grid: list[dict] = []

    print(f"  {'entry_z':>8s} {'ma':>4s} {'Return %':>10s} {'Sharpe':>8s} "
          f"{'MaxDD %':>10s} {'Trades':>7s} {'CorrD':>7s}")
    print("  " + "-" * 65)
    best_sharpe = -1e9
    best_cfg = None
    for ez in entry_zs:
        for mw in ma_windows:
            r = run_mean_reversion(
                fx_data,
                start_date=FULL_START,
                end_date=FULL_END,
                ma_window=mw,
                entry_z=ez,
            )
            dc, mc = compute_correlations(r, xs_result)
            row = {
                "entry_z": ez,
                "ma_window": mw,
                "return": r["total_return"],
                "sharpe": r["sharpe"],
                "mdd": r["max_dd"],
                "trades": r["total_trades"],
                "daily_corr": dc,
                "monthly_corr": mc,
            }
            grid.append(row)
            marker = ""
            if ez == BASE_ENTRY_Z and mw == BASE_MA_WINDOW:
                marker = "  <- baseline"
            print(f"  {ez:>8.1f} {mw:>4d} {r['total_return'] * 100:>+9.2f}% "
                  f"{r['sharpe']:>+8.3f} {r['max_dd'] * 100:>+9.2f}% "
                  f"{r['total_trades']:>7d} {dc:>+7.2f}{marker}")
            if r["sharpe"] > best_sharpe:
                best_sharpe = r["sharpe"]
                best_cfg = row

    # ------------------------------------------------------------------
    section("Sensitivity verdict")
    # ------------------------------------------------------------------
    print(f"Baseline (entry_z={BASE_ENTRY_Z}, ma={BASE_MA_WINDOW}) Sharpe: "
          f"{baseline['sharpe']:.4f}")
    if best_cfg is not None:
        print(f"Best cell in grid: entry_z={best_cfg['entry_z']}, "
              f"ma={best_cfg['ma_window']} -> Sharpe {best_cfg['sharpe']:.4f}, "
              f"corr(daily)={best_cfg['daily_corr']:+.2f}")

    # Flag "rescue" if baseline bad but some grid cell is strongly positive.
    if baseline["sharpe"] <= 0 and best_cfg is not None and best_cfg["sharpe"] > 0.4 \
            and abs(best_cfg["daily_corr"]) < 0.3:
        print("\n  NOTE: Baseline Sharpe is non-positive, but a nearby config")
        print(f"  (entry_z={best_cfg['entry_z']}, ma={best_cfg['ma_window']}) "
              f"has Sharpe {best_cfg['sharpe']:.3f} and daily corr "
              f"{best_cfg['daily_corr']:+.2f} -- worth investigating further")
        print("  with proper IS/OOS split before accepting. (Do NOT cherry-pick.)")

    print("\nDone.")


if __name__ == "__main__":
    main()
