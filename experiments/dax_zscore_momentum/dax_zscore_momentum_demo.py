#!/usr/bin/env python3
"""
GER40 intraday z-score momentum on M5 — Phase 2 demo.

Thesis: experiments/dax_zscore_momentum/dax_zscore_momentum.md

Rules (momentum — opposite of NDX MR):
  z >= +Z_ENTRY -> LONG  at next bar open (ride up-stretch)
  z <= -Z_ENTRY -> SHORT at next bar open (ride down-stretch)

  Exit (first of):
    |z| >= Z_PROFIT       -> TP   (further stretch)
    |z| <= Z_STOP         -> STOP (reverted to mean)
    t_in_trade >= T_EXIT  -> TIME
    session near close    -> EOD

Session: Europe/Berlin 09:00-17:30. Cost: 1pt round-trip (CFD).
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

SYMBOL = os.environ.get("DAX_MOM_SYMBOL", "GER40")
TIMEFRAME = "M5"
START_DATE = "2019-01-01"
END_DATE = "2026-04-18"

WINDOW_BARS = 20
Z_ENTRY = 2.0
Z_PROFIT = 3.0
Z_STOP = 0.5
T_EXIT_MIN = 180
ENTRY_CUTOFF_MIN = 300
EXIT_MIN_BEFORE_CLOSE = 5
COST_POINTS_ROUND_TRIP = 1.0

RTH_OPEN = dtime(9, 0)
RTH_CLOSE = dtime(17, 30)
SESSION_TZ = "Europe/Berlin"
_rth_minutes = (RTH_CLOSE.hour * 60 + RTH_CLOSE.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)
BARS_PER_DAY = _rth_minutes // 5
DAYS_PER_YEAR = 252
BARS_PER_YEAR = BARS_PER_DAY * DAYS_PER_YEAR


def section(t: str) -> None:
    print(f"\n{'=' * 80}\n  {t}\n{'=' * 80}\n")


def load_m5(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f"No bars for {symbol} {TIMEFRAME}")
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


def simulate_zscore_momentum(
    bars: pd.DataFrame,
    window_bars: int = WINDOW_BARS,
    z_entry: float = Z_ENTRY,
    z_profit: float | None = Z_PROFIT,
    z_stop: float = Z_STOP,
    t_exit_min: int | None = T_EXIT_MIN,
    entry_cutoff_min: int = ENTRY_CUTOFF_MIN,
    exit_min_before_close: int = EXIT_MIN_BEFORE_CLOSE,
    cost_points: float = COST_POINTS_ROUND_TRIP,
    reverse: bool = False,   # null: enter AGAINST stretch (reversion direction)
) -> tuple[pd.Series, list[dict]]:
    bars = bars.copy()
    bars["date"] = bars.index.date
    bars["minute_of_day"] = (bars.index.hour * 60 + bars.index.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)

    ret = pd.Series(0.0, index=bars.index)
    trades: list[dict] = []

    for day, day_bars in bars.groupby("date", sort=True):
        if len(day_bars) < window_bars + 4:
            continue

        closes = day_bars["close"].to_numpy(dtype=float)
        opens = day_bars["open"].to_numpy(dtype=float)
        mod = day_bars["minute_of_day"].to_numpy(dtype=int)
        idx_list = list(day_bars.index)
        n = len(idx_list)
        exit_cutoff = _rth_minutes - exit_min_before_close

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

        position = 0
        entry_px = np.nan
        entry_ts = None
        entry_bar_idx = -1
        entry_z = np.nan
        t_exit_bars = None if t_exit_min is None else t_exit_min // 5

        for i in range(n):
            ts = idx_list[i]
            is_last_bar = (i == n - 1)

            if position != 0 and i > 0:
                prev_close = closes[i - 1]
                cur_close = closes[i]
                ret.iloc[ret.index.get_loc(ts)] = position * (cur_close - prev_close) / prev_close

            if position != 0:
                cur_z = z_arr[i] if np.isfinite(z_arr[i]) else entry_z

                # TP = further stretch in our favor.
                # For momentum (reverse=False): LONG entered on z>+Z_ENTRY, TP when z >= Z_PROFIT.
                #                               SHORT entered on z<-Z_ENTRY, TP when z <= -Z_PROFIT.
                # For reverse (reversion): LONG entered on z<-Z_ENTRY, TP when z >= +Z_PROFIT (reverted).
                #                          SHORT entered on z>+Z_ENTRY, TP when z <= -Z_PROFIT (reverted).
                hit_tp = False
                hit_stop = False
                if np.isfinite(cur_z):
                    if not reverse:
                        # Momentum: TP on stretch continuation, stop on mean reversion
                        # LONG at z>+Z_ENTRY: TP when z>=+Z_PROFIT; stop when z<=+z_stop
                        # SHORT at z<-Z_ENTRY: TP when z<=-Z_PROFIT; stop when z>=-z_stop
                        if position == 1 and z_profit is not None and cur_z >= z_profit:
                            hit_tp = True
                        if position == -1 and z_profit is not None and cur_z <= -z_profit:
                            hit_tp = True
                        if position == 1 and cur_z <= z_stop:
                            hit_stop = True
                        if position == -1 and cur_z >= -z_stop:
                            hit_stop = True
                    else:
                        # Reversion (null-check): TP on mean reversion, stop on stretch continuation
                        # LONG at z<-Z_ENTRY: TP when z>=-z_stop (reverted); stop when z<=-Z_PROFIT (stretched further)
                        # SHORT at z>+Z_ENTRY: TP when z<=+z_stop (reverted); stop when z>=+Z_PROFIT (stretched further)
                        if position == 1 and cur_z >= -z_stop:
                            hit_tp = True
                        if position == -1 and cur_z <= z_stop:
                            hit_tp = True
                        if position == 1 and z_profit is not None and cur_z <= -z_profit:
                            hit_stop = True
                        if position == -1 and z_profit is not None and cur_z >= z_profit:
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

            if position == 0 and i + 1 < n and mod[i] < entry_cutoff_min:
                z = z_arr[i]
                if not np.isfinite(z):
                    continue
                if abs(z) < z_entry:
                    continue
                if not reverse:
                    want_dir = 1 if z > 0 else -1  # momentum
                else:
                    want_dir = -1 if z > 0 else 1  # reversion
                position = want_dir
                entry_px = opens[i + 1]
                entry_ts = idx_list[i + 1]
                entry_bar_idx = i + 1
                entry_z = z

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
    bar_ret.name = "dax_mom_ret"
    return bar_ret, trades


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
    print(f"    Sharpe > 0.30  : {v(sh > 0.30)}  ({sh:+.2f})")
    print(f"    Max DD < 25%   : {v(abs(mdd) < 0.25)}  ({mdd * 100:+.2f}%)")
    print(f"    Trades >= 150  : {v(n_trades >= 150)}  ({n_trades})")
    print(f"    PF >= 1.05     : {v(pf >= 1.05)}  ({pf:.2f})  [WR {wr * 100:.1f}%]")


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

    section("Baseline (window=20, z_entry=2.0, z_profit=3.0, z_stop=0.5, T=180min, cost=1pt)")
    bar_ret, trades = simulate_zscore_momentum(bars)
    report_run("baseline", bar_ret, trades)

    section("Phase 2 kill-criteria")
    kill_criteria_check("baseline", bar_ret, trades)

    section("Regime breakdown (baseline)")
    regime_breakdown(bar_ret, trades)

    section("Null check — reversion variant (should LOSE if momentum is real)")
    r_rev, t_rev = simulate_zscore_momentum(bars, reverse=True)
    report_run("reversion", r_rev, t_rev)
    sh_mom = annualized_sharpe(bar_ret.to_numpy())
    sh_rev = annualized_sharpe(r_rev.to_numpy())
    print(f"\n  Momentum Sharpe : {sh_mom:+.2f}")
    print(f"  Reversion Sharpe: {sh_rev:+.2f}")
    print(f"  **Fade-gap**    : {sh_mom - sh_rev:+.2f}   (need >= +0.30)")

    section("Variant sweep — z_entry")
    for z in (1.5, 2.0, 2.5, 3.0):
        r_v, t_v = simulate_zscore_momentum(bars, z_entry=z)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in t_v if t["pnl_pct"] > 0) / max(len(t_v), 1)
        gw = sum(t["pnl_pct"] for t in t_v if t["pnl_pct"] > 0)
        gl = -sum(t["pnl_pct"] for t in t_v if t["pnl_pct"] < 0)
        pf = gw / gl if gl > 0 else float("inf")
        print(f"  z_entry={z:>3.1f}  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  "
              f"trades {len(t_v):>4d}  WR {wr*100:>4.1f}%  PF {pf:>4.2f}")

    section("Variant sweep — T_exit")
    for t_min in (60, 120, 180, 240, None):
        label = f"{t_min}min" if t_min is not None else "EOD-only"
        r_v, t_v = simulate_zscore_momentum(bars, t_exit_min=t_min)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in t_v if t["pnl_pct"] > 0) / max(len(t_v), 1)
        print(f"  T={label:<9s}  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  "
              f"trades {len(t_v):>4d}  WR {wr*100:>4.1f}%")

    section("Variant sweep — z_profit (TP threshold)")
    for zp in (2.5, 3.0, 3.5, 4.0, None):
        label = f"{zp:.1f}" if zp is not None else "none"
        r_v, t_v = simulate_zscore_momentum(bars, z_profit=zp)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in t_v if t["pnl_pct"] > 0) / max(len(t_v), 1)
        print(f"  z_profit={label:<5s}  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  "
              f"trades {len(t_v):>4d}  WR {wr*100:>4.1f}%")

    section("Variant sweep — window_bars")
    for w in (10, 20, 40, 60):
        r_v, t_v = simulate_zscore_momentum(bars, window_bars=w)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in t_v if t["pnl_pct"] > 0) / max(len(t_v), 1)
        print(f"  window={w:>3d}  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  "
              f"trades {len(t_v):>4d}  WR {wr*100:>4.1f}%")

    section("Variant sweep — entry_cutoff (truncate late-session entries)")
    # DAX RTH is 510 min total. 180 = pre-lunch, 300 = pre-US-open, 420 = pre-close
    for cutoff in (180, 240, 300, 390, 480):
        r_v, t_v = simulate_zscore_momentum(bars, entry_cutoff_min=cutoff)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in t_v if t["pnl_pct"] > 0) / max(len(t_v), 1)
        print(f"  cutoff={cutoff:>3d}min  Sharpe {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  "
              f"trades {len(t_v):>4d}  WR {wr*100:>4.1f}%")

    section("Variant sweep — cost sensitivity (points RT)")
    for cost in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0):
        r_v, t_v = simulate_zscore_momentum(bars, cost_points=cost)
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
