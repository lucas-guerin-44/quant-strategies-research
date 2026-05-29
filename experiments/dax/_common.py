"""Shared helpers for DAX-focused strategy demos.

Hardcodes the Xetra cash session (09:00-17:30 Europe/Berlin) and provides
uniform load / reporting / regime-breakdown / kill-criteria so each
strategy demo only contains its own simulator.
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

TIMEFRAME = "M5"
START_DATE = "2019-01-01"
END_DATE = "2026-04-18"

RTH_OPEN = dtime(9, 0)
RTH_CLOSE = dtime(17, 30)
SESSION_TZ = "Europe/Berlin"

RTH_MINUTES = (RTH_CLOSE.hour * 60 + RTH_CLOSE.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)
BARS_PER_DAY = RTH_MINUTES // 5
DAYS_PER_YEAR = 252
BARS_PER_YEAR = BARS_PER_DAY * DAYS_PER_YEAR


def section(t: str) -> None:
    print(f"\n{'=' * 80}\n  {t}\n{'=' * 80}\n")


def _to_utc_indexed(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def load_dax_m5() -> pd.DataFrame:
    raw = fetch_ohlc("GER40", TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError("No bars for GER40")
    df = _to_utc_indexed(raw)
    df.index = df.index.tz_convert(SESSION_TZ)
    times = df.index.time
    mask = (times >= RTH_OPEN) & (times < RTH_CLOSE)
    df = df.loc[mask]
    df = df.loc[df.index.dayofweek < 5]
    return df


def load_spx_m5_et() -> pd.DataFrame:
    raw = fetch_ohlc("SPX500", TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError("No bars for SPX500")
    df = _to_utc_indexed(raw)
    df.index = df.index.tz_convert("US/Eastern")
    # Keep only NY RTH (09:30-16:00 ET).
    t = df.index.time
    df = df.loc[(t >= dtime(9, 30)) & (t < dtime(16, 0))]
    df = df.loc[df.index.dayofweek < 5]
    return df


def max_drawdown(eq: np.ndarray) -> float:
    rm = np.maximum.accumulate(eq)
    dd = (eq - rm) / rm
    return float(dd.min()) if len(dd) else 0.0


def annualized_sharpe(r: np.ndarray, bars_per_year: int = BARS_PER_YEAR) -> float:
    r = r[np.isfinite(r)]
    if r.size == 0:
        return 0.0
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(bars_per_year))


def report_run(label: str, bar_ret: pd.Series, trades: list[dict],
               bars_per_year: int = BARS_PER_YEAR) -> None:
    eq = (1.0 + bar_ret).cumprod()
    years = (bar_ret.index[-1] - bar_ret.index[0]).days / 365.25
    total = float(eq.iloc[-1] - 1.0)
    cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
    sh = annualized_sharpe(bar_ret.to_numpy(), bars_per_year)
    mdd = max_drawdown(eq.to_numpy())
    n = len(trades)
    tpw = n / (years * 52) if years > 0 else 0.0
    wins = [t for t in trades if t["pnl_pct"] > 0]
    wr = len(wins) / n if n else 0.0
    gw = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gl = -sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0)
    pf = gw / gl if gl > 0 else float("inf")
    avg_w = np.mean([t["pnl_pct"] for t in wins]) if wins else 0.0
    losses = [t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0]
    avg_l = np.mean(losses) if losses else 0.0
    print(f"  [{label}]")
    print(f"    period      : {bar_ret.index[0].date()} -> {bar_ret.index[-1].date()} ({years:.1f}y)")
    print(f"    total ret   : {total * 100:+.2f}%")
    print(f"    CAGR        : {cagr * 100:+.2f}%")
    print(f"    Sharpe      : {sh:+.2f}")
    print(f"    Max DD      : {mdd * 100:+.2f}%")
    print(f"    trades      : {n}  ({tpw:.2f}/week)")
    print(f"    win rate    : {wr * 100:.1f}%")
    print(f"    profit fac. : {pf:.2f}")
    print(f"    avg win     : {avg_w * 100:+.3f}%   avg loss: {avg_l * 100:+.3f}%")


def kill_criteria_check(label: str, bar_ret: pd.Series, trades: list[dict],
                        sharpe_min: float = 0.30, mdd_max: float = 0.25,
                        trade_min: int = 200, wr_min: float = 0.38, pf_min: float = 1.1,
                        bars_per_year: int = BARS_PER_YEAR) -> None:
    sh = annualized_sharpe(bar_ret.to_numpy(), bars_per_year)
    eq = (1.0 + bar_ret).cumprod()
    mdd = max_drawdown(eq.to_numpy())
    n = len(trades)
    wins = [t for t in trades if t["pnl_pct"] > 0]
    wr = len(wins) / n if n else 0.0
    gw = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gl = -sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0)
    pf = gw / gl if gl > 0 else float("inf")

    def v(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    print(f"  [{label}]")
    print(f"    Sharpe > {sharpe_min:.2f}         : {v(sh > sharpe_min)}  ({sh:+.2f})")
    print(f"    Max DD < {mdd_max * 100:.0f}%          : {v(abs(mdd) < mdd_max)}  ({mdd * 100:+.2f}%)")
    print(f"    Trades >= {trade_min:<4d}       : {v(n >= trade_min)}  ({n})")
    print(f"    WR>={wr_min * 100:.0f} or PF>={pf_min:.2f}  : {v(wr >= wr_min or pf >= pf_min)}  "
          f"(WR {wr * 100:.1f}%, PF {pf:.2f})")


def regime_breakdown(bar_ret: pd.Series, trades: list[dict],
                     bars_per_year: int = BARS_PER_YEAR) -> None:
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
        cagr = (float(eq.iloc[-1])) ** (1 / max(years, 1e-9)) - 1
        sh = annualized_sharpe(sub_ret.to_numpy(), bars_per_year)
        mdd = max_drawdown(eq.to_numpy())
        print(f"  {label:<22s} CAGR {cagr * 100:>+7.2f}%  Sharpe {sh:>+6.2f}  "
              f"MDD {mdd * 100:>+7.2f}%  trades {len(sub_trades):>4d}")


def compute_day_groups(idx: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (dates, day_starts, day_ends) given a sorted bar index."""
    dates = np.asarray(idx.date)
    n = len(idx)
    change = np.empty(n, dtype=bool)
    change[0] = True
    change[1:] = dates[1:] != dates[:-1]
    day_starts = np.flatnonzero(change)
    day_ends = np.empty_like(day_starts)
    day_ends[:-1] = day_starts[1:]
    day_ends[-1] = n
    return dates, day_starts, day_ends


def compute_minute_of_day(idx: pd.DatetimeIndex) -> np.ndarray:
    rth_open_min = RTH_OPEN.hour * 60 + RTH_OPEN.minute
    hours = np.asarray(idx.hour, dtype=np.int32)
    minutes = np.asarray(idx.minute, dtype=np.int32)
    return hours * 60 + minutes - rth_open_min
