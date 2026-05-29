#!/usr/bin/env python3
"""
Bollinger-Band Reversion on index CFDs (M5) -- Phase 2 demo.

Thesis: experiments/bb_reversion/bb_reversion.md

Rules:
  Rolling 20-bar SMA + 2σ bands on M5 closes.
  On close > upper band: SHORT at next bar open (fade upper extreme).
  On close < lower band: LONG at next bar open (fade lower extreme).
  Stop: entry ± STOP_ATR_MULT × ATR(14).
  Target: rolling midline at time of entry.
  Exits: stop, target, or EOD cutoff, whichever first.
  Max 1 round-trip per direction per day. Flat overnight.

Instrument + session via env vars (same pattern as experiments/orb/orb_demo.py):

    ORB_SYMBOL=UK100 ORB_SESSION=UK python experiments/bb_reversion/bb_reversion_demo.py
    ORB_SYMBOL=NDX100 ORB_SESSION=US python experiments/bb_reversion/bb_reversion_demo.py
    ORB_SYMBOL=GER40 ORB_SESSION=EU python experiments/bb_reversion/bb_reversion_demo.py
    ...

Also runs a "trend" variant (long on upper break, short on lower break — the
mechanical opposite) as a fade-test: if trend variant Sharpe is close to
baseline, signal has no directional content.

Cost model: 1 index point per round-trip (pessimistic retail CFD).
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


# =============================================================================
# Config
# =============================================================================

SYMBOL = os.environ.get("ORB_SYMBOL", "UK100")
TIMEFRAME = "M5"
START_DATE = "2019-01-01"
END_DATE = "2026-04-18"

BB_PERIOD = 20            # 20 M5 bars = 100 min rolling window
BB_SIGMA = 2.0
ATR_PERIOD = 14
STOP_ATR_MULT = 1.5       # stop = entry ± 1.5 × ATR(14)

ENTRY_CUTOFF_MIN_FROM_OPEN = 60    # skip first hour (BB warm-up + opening noise)
EXIT_MIN_BEFORE_CLOSE = 15         # flatten 15 min before session close

COST_POINTS_ROUND_TRIP = 1.0

SESSIONS = {
    "US": (dtime(9, 30), dtime(16, 0), "US/Eastern"),
    "EU": (dtime(9, 0), dtime(17, 30), "Europe/Berlin"),
    "UK": (dtime(8, 0), dtime(16, 30), "Europe/London"),
}
SESSION_KEY = os.environ.get("ORB_SESSION", "UK").upper()
if SESSION_KEY not in SESSIONS:
    raise RuntimeError(f"Unknown ORB_SESSION={SESSION_KEY!r}; options: {list(SESSIONS)}")
RTH_OPEN, RTH_CLOSE, SESSION_TZ = SESSIONS[SESSION_KEY]

_rth_minutes = (RTH_CLOSE.hour * 60 + RTH_CLOSE.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)
BARS_PER_DAY = _rth_minutes // 5
BARS_PER_YEAR = BARS_PER_DAY * 252


# =============================================================================
# Helpers
# =============================================================================

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


def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Wilder-style ATR — classic rolling mean of true range."""
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift(1)).abs()
    lc = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


# =============================================================================
# Simulator
# =============================================================================

def simulate_bb_reversion(
    bars: pd.DataFrame,
    bb_period: int = BB_PERIOD,
    bb_sigma: float = BB_SIGMA,
    stop_atr_mult: float = STOP_ATR_MULT,
    cost_points: float = COST_POINTS_ROUND_TRIP,
    trend_mode: bool = False,       # if True, long on upper break, short on lower — FADE TEST
) -> tuple[pd.Series, list[dict]]:
    """Bar-level BB-reversion simulator."""
    bars = bars.copy()
    bars["date"] = bars.index.date
    bars["mod_min"] = (bars.index.hour * 60 + bars.index.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)

    # Rolling stats on close.
    mean = bars["close"].rolling(bb_period, min_periods=bb_period).mean()
    sigma = bars["close"].rolling(bb_period, min_periods=bb_period).std(ddof=1)
    upper = mean + bb_sigma * sigma
    lower = mean - bb_sigma * sigma

    atr = compute_atr(bars, ATR_PERIOD)

    bars["mean"] = mean
    bars["upper"] = upper
    bars["lower"] = lower
    bars["atr"] = atr

    ret = pd.Series(0.0, index=bars.index)
    trades: list[dict] = []

    rth_minutes = (RTH_CLOSE.hour * 60 + RTH_CLOSE.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)
    exit_cutoff_min = rth_minutes - EXIT_MIN_BEFORE_CLOSE

    for day, day_bars in bars.groupby("date", sort=True):
        if len(day_bars) < bb_period + 5:
            continue

        position = 0
        entry_px = np.nan
        entry_ts = None
        stop_px = np.nan
        target_px = np.nan
        long_taken = False
        short_taken = False

        idx_list = list(day_bars.index)
        n = len(idx_list)

        for i, ts in enumerate(idx_list):
            bar = day_bars.loc[ts]
            mod = int(bar["mod_min"])
            is_last_bar = (i == n - 1)

            # Mark-to-market if positioned.
            if position != 0 and i > 0:
                prev_ts = idx_list[i - 1]
                prev_close = float(day_bars.loc[prev_ts, "close"])
                cur_close = float(bar["close"])
                ret.loc[ts] = position * (cur_close - prev_close) / prev_close

            # ---- Exit checks ----
            if position != 0:
                hit_stop = (position == 1 and bar["low"] <= stop_px) or \
                           (position == -1 and bar["high"] >= stop_px)
                hit_target = False
                if np.isfinite(target_px):
                    hit_target = (position == 1 and bar["high"] >= target_px) or \
                                 (position == -1 and bar["low"] <= target_px)
                forced_close = mod >= exit_cutoff_min or is_last_bar

                if hit_stop or hit_target or forced_close:
                    if hit_stop:
                        exit_px = stop_px
                        exit_reason = "stop"
                    elif hit_target:
                        exit_px = target_px
                        exit_reason = "target"
                    else:
                        exit_px = float(bar["close"])
                        exit_reason = "eod"

                    if i > 0:
                        prev_close = float(day_bars.loc[idx_list[i - 1], "close"])
                        ret.loc[ts] = position * (exit_px - prev_close) / prev_close
                    else:
                        ret.loc[ts] = position * (exit_px - entry_px) / entry_px
                    cost_ret = cost_points / entry_px
                    ret.loc[ts] = ret.loc[ts] - cost_ret

                    trades.append({
                        "date": day,
                        "direction": "LONG" if position == 1 else "SHORT",
                        "entry_ts": entry_ts,
                        "exit_ts": ts,
                        "entry_px": entry_px,
                        "exit_px": exit_px,
                        "pnl_pct": position * (exit_px - entry_px) / entry_px - cost_ret,
                        "reason": exit_reason,
                    })
                    position = 0
                    entry_px = np.nan
                    stop_px = np.nan
                    target_px = np.nan
                    continue

            # ---- Entry checks ----
            if position != 0:
                continue
            if mod < ENTRY_CUTOFF_MIN_FROM_OPEN:
                continue
            if mod >= exit_cutoff_min:
                continue
            if i + 1 >= n:
                continue

            # Need fully-formed BB + ATR values.
            bar_mean = float(bar["mean"]) if np.isfinite(bar["mean"]) else np.nan
            bar_upper = float(bar["upper"]) if np.isfinite(bar["upper"]) else np.nan
            bar_lower = float(bar["lower"]) if np.isfinite(bar["lower"]) else np.nan
            bar_atr = float(bar["atr"]) if np.isfinite(bar["atr"]) else np.nan
            if not (np.isfinite(bar_mean) and np.isfinite(bar_upper)
                    and np.isfinite(bar_lower) and np.isfinite(bar_atr) and bar_atr > 0):
                continue

            cur_close = float(bar["close"])
            next_bar = day_bars.loc[idx_list[i + 1]]
            next_open = float(next_bar["open"])

            upper_break = cur_close > bar_upper
            lower_break = cur_close < bar_lower

            # Baseline: fade the extreme (mean reversion).
            # Trend mode: chase the extreme (for fade-test null comparison).
            if upper_break and not short_taken:
                direction = +1 if trend_mode else -1
                if direction == -1:
                    entry_px = next_open
                    stop_px = entry_px + stop_atr_mult * bar_atr
                    target_px = bar_mean
                    short_taken = True
                else:
                    entry_px = next_open
                    stop_px = entry_px - stop_atr_mult * bar_atr
                    target_px = bar_mean + 2.0 * (bar_mean - bar_lower)  # stretch target opposite
                    long_taken = True  # trend-mode uses long_taken for upper-break trades
                position = direction
                entry_ts = idx_list[i + 1]

            elif lower_break and not long_taken:
                direction = -1 if trend_mode else +1
                if direction == +1:
                    entry_px = next_open
                    stop_px = entry_px - stop_atr_mult * bar_atr
                    target_px = bar_mean
                    long_taken = True
                else:
                    entry_px = next_open
                    stop_px = entry_px + stop_atr_mult * bar_atr
                    target_px = bar_mean - 2.0 * (bar_upper - bar_mean)
                    short_taken = True
                position = direction
                entry_ts = idx_list[i + 1]

    bar_ret = ret.fillna(0.0)
    bar_ret.name = "bb_ret"
    return bar_ret, trades


# =============================================================================
# Reporting
# =============================================================================

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
    gross_win = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gross_loss = -sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0)
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    avg_win = np.mean([t["pnl_pct"] for t in wins]) if wins else 0.0
    losses = [t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0]
    avg_loss = np.mean(losses) if losses else 0.0

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


def kill_criteria_check(label: str, bar_ret: pd.Series, trades: list[dict]) -> None:
    sh = annualized_sharpe(bar_ret.to_numpy())
    eq = (1.0 + bar_ret).cumprod()
    mdd = max_drawdown(eq.to_numpy())
    n_trades = len(trades)
    wins = [t for t in trades if t["pnl_pct"] > 0]
    win_rate = len(wins) / n_trades if n_trades else 0.0
    gw = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gl = -sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0)
    pf = gw / gl if gl > 0 else float("inf")

    def v(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    print(f"  [{label}]")
    print(f"    Sharpe > 0.30       : {v(sh > 0.30)}  ({sh:+.2f})")
    print(f"    Max DD < 25%        : {v(abs(mdd) < 0.25)}  ({mdd * 100:+.2f}%)")
    print(f"    Trades >= 200       : {v(n_trades >= 200)}  ({n_trades})")
    print(f"    WR>=35 or PF>=1.15  : {v(win_rate >= 0.35 or pf >= 1.15)}  "
          f"(WR {win_rate * 100:.1f}%, PF {pf:.2f})")


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
        print(f"  {label:<22s} CAGR {cagr * 100:>+7.2f}%  Sharpe {sh:>+6.2f}  "
              f"MDD {mdd * 100:>+7.2f}%  trades {len(sub_trades):>4d}")


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    section(f"Loading {SYMBOL} M5 ({SESSION_KEY} session)")
    try:
        bars = load_m5(SYMBOL)
    except RuntimeError as e:
        print(f"  {e}")
        return 1
    print(f"  bars: {len(bars):,}")
    print(f"  range: {bars.index[0]} -> {bars.index[-1]}")
    print(f"  BB period {BB_PERIOD}, sigma {BB_SIGMA}, ATR period {ATR_PERIOD}, "
          f"stop {STOP_ATR_MULT}×ATR, cost {COST_POINTS_ROUND_TRIP}pt")

    section("Baseline: fade extremes (mean reversion)")
    bar_ret, trades = simulate_bb_reversion(bars)
    report_run("baseline", bar_ret, trades)

    section("Phase 2 kill-criteria")
    kill_criteria_check("baseline", bar_ret, trades)

    section("Regime breakdown")
    regime_breakdown(bar_ret, trades)

    section("Fade-test: trend variant (chase extremes instead of fade)")
    r_trend, t_trend = simulate_bb_reversion(bars, trend_mode=True)
    report_run("trend (fade-test)", r_trend, t_trend)
    sh_base = annualized_sharpe(bar_ret.to_numpy())
    sh_trend = annualized_sharpe(r_trend.to_numpy())
    gap = sh_base - sh_trend
    print(f"\n  >> Sharpe-gap (baseline - trend): {gap:+.2f}")
    if gap > 0.3:
        print("  >> REAL mean-reversion signal.")
    elif gap < -0.3:
        print("  >> Trend dominates — this is actually a breakout strategy, not mean reversion.")
    else:
        print("  >> Weak / ambiguous — signal has little directional content.")

    section("Parameter robustness (±BB sigma)")
    for s in (1.5, 2.0, 2.5):
        r_v, t_v = simulate_bb_reversion(bars, bb_sigma=s)
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        print(f"  sigma={s:.1f}  Sharpe {sh:+.2f}  MDD {mdd * 100:+.2f}%  trades {len(t_v)}")

    section("Cost sensitivity")
    for cost in (0.5, 1.0, 2.0):
        r_v, t_v = simulate_bb_reversion(bars, cost_points=cost)
        sh = annualized_sharpe(r_v.to_numpy())
        print(f"  cost={cost:.1f}pt  Sharpe {sh:+.2f}  trades {len(t_v)}")

    section("Summary")
    years = (bar_ret.index[-1] - bar_ret.index[0]).days / 365.25
    eq = (1.0 + bar_ret).cumprod()
    total = float(eq.iloc[-1] - 1.0)
    cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
    print(f"  {SYMBOL} BB-reversion baseline: "
          f"CAGR {cagr * 100:+.2f}%  Sharpe {annualized_sharpe(bar_ret.to_numpy()):+.2f}  "
          f"MDD {max_drawdown(eq.to_numpy()) * 100:+.2f}%  "
          f"trades {len(trades)} ({len(trades) / max(years * 52, 1e-9):.2f}/week)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
