#!/usr/bin/env python3
"""
NDX100 intraday mean-reversion on M5 — Phase 2 demo.

Thesis: experiments/ndx_mean_reversion/ndx_mean_reversion.md

Rules:
  Compute within-day rolling z-score of close over last WINDOW_BARS bars.
  Flat only, within entry cutoff:
    z >= +Z_ENTRY -> short at next bar open (fade up-stretch)
    z <= -Z_ENTRY -> long  at next bar open (fade down-stretch)
  Exit (first of):
    |z| <= Z_EXIT                                  -> TP (mean reversion success)
    |z| * sign(position-against-direction) >= Z_STOP -> STOP
    bars_since_entry * 5 min >= T_EXIT_MIN         -> TIME
    minute_of_day >= (session_minutes - EXIT_MIN_BEFORE_CLOSE) -> EOD

Cost: COST_POINTS_ROUND_TRIP index points per round-trip, applied as
return drag = cost / entry_price on the exit bar.
"""

from __future__ import annotations

import os
import sys
from datetime import time as dtime

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))

from data import fetch_ohlc  # noqa: E402


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SYMBOL = os.environ.get("NDX_MR_SYMBOL", "NDX100")
TIMEFRAME = "M5"
START_DATE = "2019-01-01"
END_DATE = "2026-04-18"

WINDOW_BARS = 20
Z_ENTRY = 2.0
Z_EXIT = 0.5
Z_STOP = 3.0
T_EXIT_MIN = 60
ENTRY_CUTOFF_MIN = 300
EXIT_MIN_BEFORE_CLOSE = 5
COST_POINTS_ROUND_TRIP = 1.0

RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)
SESSION_TZ = "US/Eastern"
_rth_minutes = (RTH_CLOSE.hour * 60 + RTH_CLOSE.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)
BARS_PER_DAY = _rth_minutes // 5
DAYS_PER_YEAR = 252
BARS_PER_YEAR = BARS_PER_DAY * DAYS_PER_YEAR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f"\n{'=' * 80}\n  {t}\n{'=' * 80}\n")


def load_m5(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(
            f"No bars for {symbol} {TIMEFRAME}. Fetch with:\n"
            f"  python scripts/mt5_fetch.py --symbols {symbol} --timeframes M5 "
            f"--from {START_DATE}"
        )
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df.index = df.index.tz_convert(SESSION_TZ)
    times = df.index.time
    mask = (times >= RTH_OPEN) & (times < RTH_CLOSE)
    df = df.loc[mask]
    df = df.loc[df.index.dayofweek < 5]
    return df


def max_drawdown(eq: np.ndarray) -> float:
    rm = np.maximum.accumulate(eq)
    dd = (eq - rm) / rm
    return float(dd.min()) if len(dd) else 0.0


def annualized_sharpe(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if r.size == 0:
        return 0.0
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(BARS_PER_YEAR))


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

def simulate_zscore_fade(
    bars: pd.DataFrame,
    window_bars: int = WINDOW_BARS,
    z_entry: float = Z_ENTRY,
    z_exit: float = Z_EXIT,
    z_stop: float | None = Z_STOP,
    t_exit_min: int | None = T_EXIT_MIN,
    entry_cutoff_min: int = ENTRY_CUTOFF_MIN,
    exit_min_before_close: int = EXIT_MIN_BEFORE_CLOSE,
    cost_points: float = COST_POINTS_ROUND_TRIP,
    momentum: bool = False,       # null check: enter WITH stretch instead of against
    trend_filter: pd.Series | None = None,  # daily: +1 long-only, -1 short-only, 0 both
) -> tuple[pd.Series, list[dict]]:
    """
    Returns
    -------
    bar_ret : pd.Series
        Bar-by-bar strategy return (net of costs), indexed by bar timestamp.
    trades : list[dict]
        One entry per completed round-trip.
    """
    bars = bars.copy()
    bars["date"] = bars.index.date
    bars["minute_of_day"] = (bars.index.hour * 60 + bars.index.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)

    ret = pd.Series(0.0, index=bars.index)
    trades: list[dict] = []

    for day, day_bars in bars.groupby("date", sort=True):
        if len(day_bars) < window_bars + 4:
            continue

        closes = day_bars["close"].to_numpy(dtype=float)
        highs = day_bars["high"].to_numpy(dtype=float)
        lows = day_bars["low"].to_numpy(dtype=float)
        opens = day_bars["open"].to_numpy(dtype=float)
        mod = day_bars["minute_of_day"].to_numpy(dtype=int)
        idx_list = list(day_bars.index)
        n = len(idx_list)

        rth_minutes = _rth_minutes
        exit_cutoff = rth_minutes - exit_min_before_close

        # Within-day rolling z-score. Start from index >= window_bars.
        mean_arr = np.full(n, np.nan)
        std_arr = np.full(n, np.nan)
        z_arr = np.full(n, np.nan)
        if n >= window_bars:
            for i in range(window_bars - 1, n):
                window = closes[i - window_bars + 1 : i + 1]
                mean_arr[i] = window.mean()
                std_arr[i] = window.std(ddof=1)
                if std_arr[i] > 0:
                    z_arr[i] = (closes[i] - mean_arr[i]) / std_arr[i]

        bias = 0
        if trend_filter is not None:
            try:
                bias = int(trend_filter.loc[day])
            except (KeyError, ValueError):
                bias = 0

        position = 0
        entry_px = np.nan
        entry_ts = None
        entry_bar_idx = -1
        stop_z = np.nan          # z value at which to stop
        entry_z = np.nan
        t_exit_bars = None if t_exit_min is None else t_exit_min // 5

        for i in range(n):
            ts = idx_list[i]
            is_last_bar = (i == n - 1)

            # Mark-to-market if positioned.
            if position != 0 and i > 0:
                prev_close = closes[i - 1]
                cur_close = closes[i]
                ret.iloc[ret.index.get_loc(ts)] = position * (cur_close - prev_close) / prev_close

            # Exit check (before entry).
            if position != 0:
                cur_z = z_arr[i] if np.isfinite(z_arr[i]) else entry_z
                # TP: z returned near zero.
                hit_tp = abs(cur_z) <= z_exit
                # Stop: z moved further against us (for fade-short, z kept rising past z_stop;
                # for fade-long, z kept falling past -z_stop).
                hit_stop = False
                if z_stop is not None and np.isfinite(cur_z):
                    if not momentum:
                        # Fade short (position=-1 when entry_z>0): stop if z >= z_stop.
                        # Fade long  (position=+1 when entry_z<0): stop if z <= -z_stop.
                        if position == -1 and cur_z >= z_stop:
                            hit_stop = True
                        if position == 1 and cur_z <= -z_stop:
                            hit_stop = True
                    else:
                        # Momentum variant: position is +1 when entry_z>0 (long with up-stretch),
                        # so stop fires on reversion toward mean (z collapses past a threshold).
                        # Symmetric stop at the opposite z_stop.
                        if position == 1 and cur_z <= -z_stop:
                            hit_stop = True
                        if position == -1 and cur_z >= z_stop:
                            hit_stop = True

                tod_forced = (t_exit_bars is not None and entry_bar_idx >= 0
                              and (i - entry_bar_idx) >= t_exit_bars)
                forced_close = mod[i] >= exit_cutoff or is_last_bar or tod_forced

                if hit_tp or hit_stop or forced_close:
                    exit_px = closes[i]
                    if hit_tp:
                        exit_reason = "tp"
                    elif hit_stop:
                        exit_reason = "stop"
                    elif tod_forced:
                        exit_reason = "tod"
                    else:
                        exit_reason = "eod"

                    # Rebook this bar's return using exit price.
                    if i > 0:
                        prev_close = closes[i - 1]
                        ret.iloc[ret.index.get_loc(ts)] = position * (exit_px - prev_close) / prev_close
                    else:
                        ret.iloc[ret.index.get_loc(ts)] = position * (exit_px - entry_px) / entry_px
                    cost_ret = cost_points / entry_px
                    ret.iloc[ret.index.get_loc(ts)] = ret.iloc[ret.index.get_loc(ts)] - cost_ret
                    trades.append({
                        "date": day,
                        "direction": "LONG" if position == 1 else "SHORT",
                        "entry_ts": entry_ts,
                        "exit_ts": ts,
                        "entry_px": entry_px,
                        "exit_px": exit_px,
                        "entry_z": entry_z,
                        "exit_z": cur_z if np.isfinite(cur_z) else entry_z,
                        "pnl_pct": position * (exit_px - entry_px) / entry_px - cost_ret,
                        "reason": exit_reason,
                    })
                    position = 0
                    entry_px = np.nan
                    entry_bar_idx = -1
                    continue

            # Entry: only if flat, z defined, within cutoff, have next bar.
            if position == 0 and i + 1 < n and mod[i] < entry_cutoff_min:
                z = z_arr[i]
                if not np.isfinite(z):
                    continue
                if abs(z) < z_entry:
                    continue
                # Direction resolution.
                if not momentum:
                    # Fade: up-stretch -> short; down-stretch -> long.
                    want_dir = -1 if z > 0 else 1
                else:
                    # Momentum: up-stretch -> long; down-stretch -> short.
                    want_dir = 1 if z > 0 else -1

                # Bias gate.
                if bias > 0 and want_dir < 0:
                    continue
                if bias < 0 and want_dir > 0:
                    continue

                position = want_dir
                entry_px = opens[i + 1]
                entry_ts = idx_list[i + 1]
                entry_bar_idx = i + 1
                entry_z = z

        # Safety end-of-day close.
        if position != 0:
            last_ts = idx_list[-1]
            last_close = closes[-1]
            cost_ret = cost_points / entry_px
            trades.append({
                "date": day,
                "direction": "LONG" if position == 1 else "SHORT",
                "entry_ts": entry_ts,
                "exit_ts": last_ts,
                "entry_px": entry_px,
                "exit_px": last_close,
                "entry_z": entry_z,
                "exit_z": z_arr[-1] if np.isfinite(z_arr[-1]) else entry_z,
                "pnl_pct": position * (last_close - entry_px) / entry_px - cost_ret,
                "reason": "eod-safety",
            })

    bar_ret = ret.fillna(0.0)
    bar_ret.name = "ndx_mr_ret"
    return bar_ret, trades


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_run(label: str, bar_ret: pd.Series, trades: list[dict]) -> None:
    eq = (1.0 + bar_ret).cumprod()
    years = (bar_ret.index[-1] - bar_ret.index[0]).days / 365.25
    total = float(eq.iloc[-1] - 1.0)
    cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
    sh = annualized_sharpe(bar_ret.to_numpy())
    mdd = max_drawdown(eq.to_numpy())
    n_trades = len(trades)
    trades_per_week = n_trades / (years * 52) if years > 0 else 0.0
    wins = [t for t in trades if t["pnl_pct"] > 0]
    win_rate = len(wins) / n_trades if n_trades else 0.0
    gw = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gl = -sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0)
    pf = gw / gl if gl > 0 else float("inf")
    avg_win = np.mean([t["pnl_pct"] for t in wins]) if wins else 0.0
    losses = [t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0]
    avg_loss = np.mean(losses) if losses else 0.0
    reason_counts: dict[str, int] = {}
    for t in trades:
        reason_counts[t["reason"]] = reason_counts.get(t["reason"], 0) + 1

    print(f"  [{label}]")
    print(f"    period      : {bar_ret.index[0].date()} -> {bar_ret.index[-1].date()} ({years:.1f}y)")
    print(f"    total ret   : {total * 100:+.2f}%")
    print(f"    CAGR        : {cagr * 100:+.2f}%")
    print(f"    Sharpe      : {sh:+.2f}")
    print(f"    Max DD      : {mdd * 100:+.2f}%")
    print(f"    trades      : {n_trades}  ({trades_per_week:.2f}/week)")
    print(f"    win rate    : {win_rate * 100:.1f}%")
    print(f"    profit fac. : {pf:.2f}")
    print(f"    avg win     : {avg_win * 100:+.3f}%   avg loss: {avg_loss * 100:+.3f}%")
    print(f"    exit mix    : {reason_counts}")


def kill_criteria_check(label: str, bar_ret: pd.Series, trades: list[dict]) -> None:
    sh = annualized_sharpe(bar_ret.to_numpy())
    eq = (1.0 + bar_ret).cumprod()
    mdd = max_drawdown(eq.to_numpy())
    n_trades = len(trades)
    wins = [t for t in trades if t["pnl_pct"] > 0]
    wr = len(wins) / n_trades if n_trades else 0.0
    gw = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gl = -sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0)
    pf = gw / gl if gl > 0 else float("inf")

    def v(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    print(f"  [{label}]")
    print(f"    Sharpe > 0.30       : {v(sh > 0.30)}  ({sh:+.2f})")
    print(f"    Max DD < 25%        : {v(abs(mdd) < 0.25)}  ({mdd * 100:+.2f}%)")
    print(f"    Trades >= 200       : {v(n_trades >= 200)}  ({n_trades})")
    print(f"    WR>=50 or PF>=1.1   : {v(wr >= 0.50 or pf >= 1.1)}  "
          f"(WR {wr * 100:.1f}%, PF {pf:.2f})")


def regime_breakdown(bar_ret: pd.Series, trades: list[dict]) -> None:
    windows = [
        ("2019-2020 pre/COVID", "2019-01-01", "2020-12-31"),
        ("2021-2022 vol",       "2021-01-01", "2022-12-31"),
        ("2023-2026 holdout",   "2023-01-01", "2026-12-31"),
    ]
    for label, s, e in windows:
        sub_ret = bar_ret.loc[s:e]
        sub_trades = [t for t in trades if s <= str(t["date"]) <= e]
        if len(sub_ret) < 200:
            print(f"  {label:<22s} (insufficient bars)")
            continue
        eq = (1.0 + sub_ret).cumprod()
        years = (sub_ret.index[-1] - sub_ret.index[0]).days / 365.25
        cagr = float(eq.iloc[-1]) ** (1 / max(years, 1e-9)) - 1
        sh = annualized_sharpe(sub_ret.to_numpy())
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in sub_trades if t["pnl_pct"] > 0) / max(len(sub_trades), 1)
        print(f"  {label:<22s} CAGR {cagr * 100:>+7.2f}%  Sharpe {sh:>+6.2f}  "
              f"MDD {mdd * 100:>+7.2f}%  trades {len(sub_trades):>4d}  WR {wr*100:>4.1f}%")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section(f"Loading {SYMBOL} {TIMEFRAME}")
    try:
        bars = load_m5(SYMBOL)
    except RuntimeError as e:
        print(f"  {e}")
        return 1
    print(f"  bars     : {len(bars):,}")
    print(f"  range    : {bars.index[0]} -> {bars.index[-1]}")
    print(f"  session  : {bars.index.time.min()} -> {bars.index.time.max()} ({SESSION_TZ})")
    print(f"  days     : {len(set(bars.index.date))}")

    section("Baseline (window=20, z_entry=2.0, z_exit=0.5, z_stop=3.0, T=60min, cost=1pt)")
    bar_ret, trades = simulate_zscore_fade(bars)
    report_run("baseline", bar_ret, trades)

    section("Phase 2 kill-criteria")
    kill_criteria_check("baseline", bar_ret, trades)

    section("Regime breakdown (baseline)")
    regime_breakdown(bar_ret, trades)

    section("Null check — momentum variant (should LOSE if MR is the real edge)")
    r_mom, t_mom = simulate_zscore_fade(bars, momentum=True)
    report_run("momentum", r_mom, t_mom)
    sh_fade = annualized_sharpe(bar_ret.to_numpy())
    sh_mom = annualized_sharpe(r_mom.to_numpy())
    print(f"\n  Fade Sharpe     : {sh_fade:+.2f}")
    print(f"  Momentum Sharpe : {sh_mom:+.2f}")
    print(f"  **Fade-gap**    : {sh_fade - sh_mom:+.2f}   "
          f"(need >= +0.30 for real directional signal)")

    section("Variant sweep — z_entry")
    for z in (1.5, 2.0, 2.5, 3.0):
        r_v, t_v = simulate_zscore_fade(bars, z_entry=z)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in t_v if t["pnl_pct"] > 0) / max(len(t_v), 1)
        gw = sum(t["pnl_pct"] for t in t_v if t["pnl_pct"] > 0)
        gl = -sum(t["pnl_pct"] for t in t_v if t["pnl_pct"] < 0)
        pf = gw / gl if gl > 0 else float("inf")
        print(f"  z_entry={z:>3.1f}  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  "
              f"trades {len(t_v):>4d}  WR {wr*100:>4.1f}%  PF {pf:>4.2f}")

    section("Variant sweep — window_bars")
    for w in (10, 20, 40, 60):
        r_v, t_v = simulate_zscore_fade(bars, window_bars=w)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in t_v if t["pnl_pct"] > 0) / max(len(t_v), 1)
        print(f"  window={w:>3d}  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  "
              f"trades {len(t_v):>4d}  WR {wr*100:>4.1f}%")

    section("Variant sweep — T_exit (time stop)")
    for t_min in (15, 30, 60, 120, None):
        label = f"{t_min}min" if t_min is not None else "EOD-only"
        r_v, t_v = simulate_zscore_fade(bars, t_exit_min=t_min)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in t_v if t["pnl_pct"] > 0) / max(len(t_v), 1)
        print(f"  T={label:<9s}  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  "
              f"trades {len(t_v):>4d}  WR {wr*100:>4.1f}%")

    section("Variant sweep — z_stop")
    for zs in (2.5, 3.0, 3.5, 4.0, None):
        label = f"{zs:.1f}" if zs is not None else "none"
        r_v, t_v = simulate_zscore_fade(bars, z_stop=zs)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in t_v if t["pnl_pct"] > 0) / max(len(t_v), 1)
        print(f"  z_stop={label:<5s}  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  "
              f"trades {len(t_v):>4d}  WR {wr*100:>4.1f}%")

    section("Variant sweep — cost sensitivity (points RT)")
    for cost in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0):
        r_v, t_v = simulate_zscore_fade(bars, cost_points=cost)
        sh = annualized_sharpe(r_v.to_numpy())
        print(f"  cost={cost:>3.1f}pt  Sharpe {sh:>+6.2f}  trades {len(t_v):>4d}")

    section("Summary")
    sh = annualized_sharpe(bar_ret.to_numpy())
    eq = (1.0 + bar_ret).cumprod()
    years = (bar_ret.index[-1] - bar_ret.index[0]).days / 365.25
    total = float(eq.iloc[-1] - 1.0)
    cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
    print(f"  baseline : CAGR {cagr * 100:+.2f}%  Sharpe {sh:+.2f}  "
          f"MDD {max_drawdown(eq.to_numpy()) * 100:+.2f}%  "
          f"trades {len(trades)} ({len(trades) / max(years * 52, 1e-9):.2f}/week)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
