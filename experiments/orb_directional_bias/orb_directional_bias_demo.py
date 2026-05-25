#!/usr/bin/env python3
"""
ORB Directional-Bias Predictor on GER40 M5.

Thesis: experiments/orb_directional_bias/orb_directional_bias.md

Build daily predictor series from prior-day-available info:
  - gap        : today_open / prior_close - 1
  - pcir       : prior_close-in-range = (pc - pl) / (ph - pl)
  - spx        : SPX500 overnight return (prior 22:00 Berlin -> today 09:00 Berlin)
  - mom5       : 5-day prior-close momentum

Each predictor produces a bias in {+1, 0, -1}. Run parent ORB rules
with three filter modes:
  filter_long   : LONG-only on bias>=0 days  (skip down-bias days)
  filter_short  : SHORT-only on bias<=0 days (skip up-bias days)
  combined      : LONG on +1, SHORT on -1, SKIP on 0  (revival path)

Plus the diagnostic: hit-rate of first-break-direction vs predictor sign.
Cost model: 1pt RT (parent default).
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

from utils import fetch_ohlc  # noqa: E402


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

START_DATE = "2019-01-01"
END_DATE = "2026-04-18"
SESSION_TZ = "Europe/Berlin"
RTH_OPEN = dtime(9, 0)
RTH_CLOSE = dtime(17, 30)

OR_MINUTES = 30
ENTRY_CUTOFF_MIN = 180
TOD_EXIT_MIN = 180
EXIT_MIN_BEFORE_CLOSE = 5
COST_POINTS_ROUND_TRIP = 1.0

_rth_minutes = (RTH_CLOSE.hour * 60 + RTH_CLOSE.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)
BARS_PER_DAY = _rth_minutes // 5
DAYS_PER_YEAR = 252
BARS_PER_YEAR = BARS_PER_DAY * DAYS_PER_YEAR


def section(t: str) -> None:
    print(f"\n{'=' * 80}\n  {t}\n{'=' * 80}\n")


def load_m5_berlin(symbol: str) -> pd.DataFrame:
    """Load M5 bars and normalize to Europe/Berlin (Xetra session if filtered)."""
    raw = fetch_ohlc(symbol, "M5", START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f"No bars for {symbol} M5")
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df.index = df.index.tz_convert(SESSION_TZ)
    return df


def filter_rth(df: pd.DataFrame) -> pd.DataFrame:
    times = df.index.time
    mask = (times >= RTH_OPEN) & (times < RTH_CLOSE)
    out = df.loc[mask]
    return out.loc[out.index.dayofweek < 5]


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
# Predictors
# ---------------------------------------------------------------------------

def build_daily_ohlc(bars_rth: pd.DataFrame) -> pd.DataFrame:
    """Per-day OHLC over the RTH session, indexed by date."""
    by_day = bars_rth.groupby(bars_rth.index.date)
    daily = pd.DataFrame({
        "open":  by_day["open"].first(),
        "high":  by_day["high"].max(),
        "low":   by_day["low"].min(),
        "close": by_day["close"].last(),
    })
    daily.index = pd.to_datetime(daily.index).date
    return daily


def build_bias_gap(daily: pd.DataFrame, thresh: float) -> pd.Series:
    """+1 if today_open > prior_close*(1+thresh); -1 if below; else 0."""
    pc = pd.Series(daily["close"].shift(1).values, index=daily.index)
    op = daily["open"]
    gap = op / pc - 1.0
    bias = pd.Series(0, index=daily.index, dtype=int)
    bias[gap > thresh] = 1
    bias[gap < -thresh] = -1
    bias[gap.isna()] = 0
    return bias


def build_bias_pcir(daily: pd.DataFrame, hi_q: float = 0.75, lo_q: float = 0.25) -> pd.Series:
    """+1 if prior close in top quartile of prior range, -1 if bottom, else 0."""
    ph = daily["high"].shift(1)
    pl = daily["low"].shift(1)
    pc = daily["close"].shift(1)
    rng = (ph - pl).replace(0, np.nan)
    pcir = (pc - pl) / rng
    bias = pd.Series(0, index=daily.index, dtype=int)
    bias[pcir > hi_q] = 1
    bias[pcir < lo_q] = -1
    bias[pcir.isna()] = 0
    return bias


def build_bias_spx(daily_ger: pd.DataFrame, spx_m5: pd.DataFrame, thresh: float) -> pd.Series:
    """
    SPX overnight = SPX close at today 09:00 Berlin / SPX close at prior 22:00 Berlin - 1.

    Snap to the nearest available SPX M5 bar within +/-30min of each anchor.
    """
    bias = pd.Series(0, index=daily_ger.index, dtype=int)
    if spx_m5 is None or spx_m5.empty:
        return bias

    # Build a fast lookup: timestamp -> close. Then snap.
    spx_close = spx_m5["close"]
    spx_idx = spx_m5.index

    def snap_close(target: pd.Timestamp) -> float:
        # Binary-search the nearest index entry within +/-30min.
        pos = spx_idx.searchsorted(target)
        candidates: list[int] = []
        if pos > 0:
            candidates.append(pos - 1)
        if pos < len(spx_idx):
            candidates.append(pos)
        best = float("nan")
        best_delta = pd.Timedelta(minutes=30)
        for c in candidates:
            d = abs(spx_idx[c] - target)
            if d <= best_delta:
                best = float(spx_close.iloc[c])
                best_delta = d
        return best

    dates = list(daily_ger.index)
    for i, d in enumerate(dates):
        if i == 0:
            continue
        today_open_ts = pd.Timestamp(d).tz_localize(SESSION_TZ).replace(hour=9, minute=0)
        prior_close_ts = pd.Timestamp(dates[i - 1]).tz_localize(SESSION_TZ).replace(hour=22, minute=0)
        s_today = snap_close(today_open_ts)
        s_prior = snap_close(prior_close_ts)
        if not (np.isfinite(s_today) and np.isfinite(s_prior)) or s_prior == 0:
            continue
        r = s_today / s_prior - 1.0
        if r > thresh:
            bias.iloc[i] = 1
        elif r < -thresh:
            bias.iloc[i] = -1
    return bias


def build_bias_mom5(daily: pd.DataFrame, thresh: float = 0.0) -> pd.Series:
    """+1 if prior_close > close 5d ago by thresh; -1 if below; else 0."""
    pc = daily["close"].shift(1)
    c5 = daily["close"].shift(6)
    mom = pc / c5 - 1.0
    bias = pd.Series(0, index=daily.index, dtype=int)
    bias[mom > thresh] = 1
    bias[mom < -thresh] = -1
    bias[mom.isna()] = 0
    return bias


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

def simulate_orb_directional(
    bars: pd.DataFrame,
    bias_by_date: dict,
    mode: str = "combined",   # 'combined' / 'filter_long' / 'filter_short' / 'symmetric' / 'invert'
    or_minutes: int = OR_MINUTES,
    entry_cutoff_min: int = ENTRY_CUTOFF_MIN,
    tod_exit_minutes: int = TOD_EXIT_MIN,
    exit_min_before_close: int = EXIT_MIN_BEFORE_CLOSE,
    cost_points: float = COST_POINTS_ROUND_TRIP,
) -> tuple[pd.Series, list[dict], dict]:
    """
    Parent ORB rules + per-day directional bias filter.

    mode semantics (bias in {+1, 0, -1}):
      combined     : +1 -> LONG only, -1 -> SHORT only, 0 -> skip day
      filter_long  : take LONG if bias>=0 (skip down-bias days for longs);
                     SHORTS NEVER (LONG-only with bias filter)
      filter_short : take SHORT if bias<=0; LONGS NEVER (SHORT-only with bias filter)
      symmetric    : bias ignored — symmetric ORB for comparison
      invert       : combined but with bias sign flipped (null check)

    Also computes a first-break-direction observable per day for hit-rate stats.
    """
    idx = bars.index
    n_bars = len(bars)
    if n_bars == 0:
        return pd.Series(dtype=float), [], {"break_records": []}

    open_arr = bars["open"].to_numpy(dtype=np.float64)
    high_arr = bars["high"].to_numpy(dtype=np.float64)
    low_arr = bars["low"].to_numpy(dtype=np.float64)
    close_arr = bars["close"].to_numpy(dtype=np.float64)

    rth_open_min = RTH_OPEN.hour * 60 + RTH_OPEN.minute
    rth_close_min = RTH_CLOSE.hour * 60 + RTH_CLOSE.minute
    hours = np.asarray(idx.hour, dtype=np.int32)
    minutes = np.asarray(idx.minute, dtype=np.int32)
    minute_of_day = hours * 60 + minutes - rth_open_min

    dates = np.asarray(idx.date)
    change = np.empty(n_bars, dtype=bool)
    change[0] = True
    change[1:] = dates[1:] != dates[:-1]
    day_starts = np.flatnonzero(change)
    day_ends = np.empty_like(day_starts)
    day_ends[:-1] = day_starts[1:]
    day_ends[-1] = n_bars

    ret_arr = np.zeros(n_bars, dtype=np.float64)
    trades: list[dict] = []
    break_records: list[dict] = []  # for hit-rate diagnostic

    rth_minutes = rth_close_min - rth_open_min
    exit_cutoff = rth_minutes - exit_min_before_close
    or_end = or_minutes

    for d_i in range(len(day_starts)):
        s = int(day_starts[d_i])
        e = int(day_ends[d_i])
        n = e - s
        if n < (or_end // 5) + 4:
            continue

        d = dates[s]
        raw_bias = int(bias_by_date.get(d, 0))
        if mode == "invert":
            raw_bias = -raw_bias

        # Resolve direction permissions per mode.
        if mode == "combined" or mode == "invert":
            if raw_bias == 0:
                continue  # skip neutral days
            long_ok = (raw_bias == 1)
            short_ok = (raw_bias == -1)
        elif mode == "filter_long":
            long_ok = (raw_bias >= 0)
            short_ok = False
        elif mode == "filter_short":
            long_ok = False
            short_ok = (raw_bias <= 0)
        elif mode == "symmetric":
            long_ok = True
            short_ok = True
        else:
            raise ValueError(f"unknown mode {mode!r}")

        day_open = open_arr[s:e]
        day_high = high_arr[s:e]
        day_low = low_arr[s:e]
        day_close = close_arr[s:e]
        day_mod = minute_of_day[s:e]

        or_mask = day_mod < or_end
        if not or_mask.any():
            continue
        or_high = float(day_high[or_mask].max())
        or_low = float(day_low[or_mask].min())
        if not (np.isfinite(or_high) and np.isfinite(or_low)) or or_high <= or_low:
            continue
        or_width = or_high - or_low

        # First-break observable (independent of trade execution).
        first_break = 0  # +1 up, -1 down, 0 none
        post_or_idx = np.flatnonzero(day_mod >= or_end)
        for j in post_or_idx:
            c = day_close[j]
            if c > or_high:
                first_break = 1
                break
            if c < or_low:
                first_break = -1
                break
        break_records.append({"date": d, "bias": int(bias_by_date.get(d, 0)), "first_break": first_break})

        if not (long_ok or short_ok):
            continue

        # Walk forward for entries/exits.
        position = 0
        entry_px = 0.0
        entry_bar_i = -1
        stop_px = 0.0
        long_taken = False
        short_taken = False

        first_post = int(post_or_idx[0]) if post_or_idx.size else n
        for i in range(first_post, n):
            mod_i = int(day_mod[i])
            is_last = (i == n - 1)

            if position != 0 and i > first_post:
                prev_close = day_close[i - 1]
                cur_close = day_close[i]
                ret_arr[s + i] = position * (cur_close - prev_close) / prev_close

            if position != 0:
                bar_h = day_high[i]
                bar_l = day_low[i]
                if position == 1:
                    hit_stop = bar_l <= stop_px
                else:
                    hit_stop = bar_h >= stop_px
                tod_forced = entry_bar_i >= 0 and (i - entry_bar_i) * 5 >= tod_exit_minutes
                forced_close = (mod_i >= exit_cutoff) or is_last or tod_forced
                if hit_stop or forced_close:
                    if hit_stop:
                        exit_px = stop_px
                        exit_reason = "stop"
                    elif tod_forced:
                        exit_px = float(day_close[i])
                        exit_reason = "tod"
                    else:
                        exit_px = float(day_close[i])
                        exit_reason = "eod"
                    if i > first_post:
                        prev_close = day_close[i - 1]
                        ret_arr[s + i] = position * (exit_px - prev_close) / prev_close
                    else:
                        ret_arr[s + i] = position * (exit_px - entry_px) / entry_px
                    cost_ret = cost_points / entry_px
                    ret_arr[s + i] -= cost_ret
                    trades.append({
                        "date": d,
                        "direction": "LONG" if position == 1 else "SHORT",
                        "entry_px": float(entry_px),
                        "exit_px": float(exit_px),
                        "pnl_pct": position * (exit_px - entry_px) / entry_px - cost_ret,
                        "reason": exit_reason,
                        "bias": int(bias_by_date.get(d, 0)),
                    })
                    position = 0
                    entry_px = 0.0
                    stop_px = 0.0
                    entry_bar_i = -1
                    continue

            if position == 0 and mod_i < entry_cutoff_min and i + 1 < n:
                cur_close = day_close[i]
                up_break = cur_close > or_high
                down_break = cur_close < or_low
                next_open = float(day_open[i + 1])

                if not long_taken and up_break and long_ok:
                    position = 1
                    entry_px = next_open
                    stop_px = entry_px - or_width
                    entry_bar_i = i + 1
                    long_taken = True
                elif not short_taken and down_break and short_ok:
                    position = -1
                    entry_px = next_open
                    stop_px = entry_px + or_width
                    entry_bar_i = i + 1
                    short_taken = True

    bar_ret = pd.Series(ret_arr, index=idx, name="orb_dir_ret")
    diag = {"break_records": break_records}
    return bar_ret, trades, diag


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_run(label: str, bar_ret: pd.Series, trades: list[dict]) -> dict:
    eq = (1.0 + bar_ret).cumprod()
    years = (bar_ret.index[-1] - bar_ret.index[0]).days / 365.25
    sh = annualized_sharpe(bar_ret.to_numpy())
    mdd = max_drawdown(eq.to_numpy())
    n_trades = len(trades)
    trades_per_week = n_trades / (years * 52) if years > 0 else 0.0
    wins = [t for t in trades if t["pnl_pct"] > 0]
    wr = len(wins) / n_trades if n_trades else 0.0
    gw = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gl = -sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0)
    pf = gw / gl if gl > 0 else float("inf")
    print(f"  {label:<28s}  Sh {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  trades {n_trades:>4d} "
          f"({trades_per_week:>4.2f}/wk)  WR {wr*100:>4.1f}%  PF {pf:>4.2f}")
    return {"sharpe": sh, "mdd": mdd, "trades": n_trades, "wr": wr, "pf": pf}


def hit_rate(diag: dict) -> tuple[float, int, float, int, float]:
    """Return (predictor_hit_rate, n_signalled, baseline_up_rate, n_total, lift)."""
    recs = diag["break_records"]
    n_total = sum(1 for r in recs if r["first_break"] != 0)
    n_up = sum(1 for r in recs if r["first_break"] == 1)
    base_up = n_up / n_total if n_total else 0.0
    n_sig = sum(1 for r in recs if r["bias"] != 0 and r["first_break"] != 0)
    hit = sum(1 for r in recs if r["bias"] != 0 and r["first_break"] == r["bias"])
    rate = hit / n_sig if n_sig else 0.0
    base = (base_up if any(r["bias"] == 1 for r in recs) else 0.5)
    return rate, n_sig, base_up, n_total, rate - 0.5


def regime_split(bar_ret: pd.Series, trades: list[dict]) -> None:
    windows = [
        ("2019-2020", "2019-01-01", "2020-12-31"),
        ("2021-2022", "2021-01-01", "2022-12-31"),
        ("2023-2026", "2023-01-01", "2026-12-31"),
    ]
    for label, s, e in windows:
        sub_ret = bar_ret.loc[s:e]
        sub_trades = [t for t in trades if s <= str(t["date"]) <= e]
        if len(sub_ret) < 100:
            print(f"    {label}: insufficient")
            continue
        sh = annualized_sharpe(sub_ret.to_numpy())
        eq = (1.0 + sub_ret).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        print(f"    {label}  Sh {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  trades {len(sub_trades):>4d}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section("Loading GER40 M5 (Berlin RTH) + SPX500 M5 (for SPX-overnight predictor)")
    ger_raw = load_m5_berlin("GER40")
    ger = filter_rth(ger_raw)
    print(f"  GER40 RTH bars : {len(ger):,}  range {ger.index[0]} -> {ger.index[-1]}")

    try:
        spx_raw = load_m5_berlin("SPX500")
        print(f"  SPX500 M5 bars : {len(spx_raw):,}  range {spx_raw.index[0]} -> {spx_raw.index[-1]}")
    except RuntimeError as ex:
        print(f"  SPX500 unavailable -> spx-overnight predictor will be skipped: {ex}")
        spx_raw = None

    daily = build_daily_ohlc(ger)
    print(f"  GER40 daily rows: {len(daily)}")

    # ----- Build predictors -----
    section("Building daily predictor bias series")
    predictors: dict[str, pd.Series] = {}
    for th in (0.0, 0.0010, 0.0025):
        predictors[f"gap_{th:.4f}"] = build_bias_gap(daily, th)
    predictors["pcir_75/25"] = build_bias_pcir(daily, 0.75, 0.25)
    predictors["pcir_60/40"] = build_bias_pcir(daily, 0.60, 0.40)
    if spx_raw is not None:
        for th in (0.0, 0.0010, 0.0025):
            predictors[f"spx_{th:.4f}"] = build_bias_spx(daily, spx_raw, th)
    predictors["mom5_0"] = build_bias_mom5(daily, 0.0)

    for name, ser in predictors.items():
        n_pos = int((ser == 1).sum())
        n_neg = int((ser == -1).sum())
        n_zero = int((ser == 0).sum())
        print(f"  {name:<18s}  +1: {n_pos:>4d}   -1: {n_neg:>4d}   0: {n_zero:>4d}  "
              f"(active {n_pos + n_neg}/{len(ser)})")

    # ----- Symmetric / baseline reference -----
    section("Reference: parent symmetric ORB (no bias)")
    none_bias = {d: 0 for d in daily.index}
    bar_sym, trades_sym, diag_sym = simulate_orb_directional(ger, none_bias, mode="symmetric")
    res_sym = report_run("symmetric (no bias)", bar_sym, trades_sym)
    # Unconditional up-break rate
    recs = diag_sym["break_records"]
    n_total = sum(1 for r in recs if r["first_break"] != 0)
    n_up = sum(1 for r in recs if r["first_break"] == 1)
    print(f"  unconditional first-break-up rate: {n_up}/{n_total} = {n_up/max(n_total,1)*100:.1f}%")

    # ----- Hit-rate diagnostic for each predictor -----
    section("Hit-rate diagnostic — does predictor sign match first-break direction?")
    print(f"  {'predictor':<18s}  {'n_signalled':>12s}  {'hit_rate':>10s}  {'vs 50%':>8s}  {'baseline_up%':>14s}")
    hit_table: dict[str, tuple] = {}
    for name, ser in predictors.items():
        bias_map = {d: int(v) for d, v in ser.items()}
        _, _, diag = simulate_orb_directional(ger, bias_map, mode="symmetric")
        rate, n_sig, base_up, n_total, lift = hit_rate(diag)
        hit_table[name] = (rate, n_sig, lift)
        print(f"  {name:<18s}  {n_sig:>12d}  {rate*100:>9.1f}%  {lift*100:>+7.2f}  {base_up*100:>13.1f}%")

    # ----- Combined-mode (revival path) -----
    section("Combined-mode: take LONG on +1, SHORT on -1, SKIP on 0")
    combined_results: dict[str, dict] = {}
    for name, ser in predictors.items():
        bias_map = {d: int(v) for d, v in ser.items()}
        r, t, _ = simulate_orb_directional(ger, bias_map, mode="combined")
        res = report_run(f"combined::{name}", r, t)
        combined_results[name] = {**res, "ret": r, "trades": t}

    # ----- Filter-mode (long-only with bias filter) -----
    section("Filter-mode (LONG-only, skip down-bias days)")
    filter_long_results: dict[str, dict] = {}
    for name, ser in predictors.items():
        bias_map = {d: int(v) for d, v in ser.items()}
        r, t, _ = simulate_orb_directional(ger, bias_map, mode="filter_long")
        res = report_run(f"filter_long::{name}", r, t)
        filter_long_results[name] = {**res, "ret": r, "trades": t}

    # ----- Revival-mode (short-only with bias filter) -----
    section("Revival-mode (SHORT-only, skip up-bias days)")
    revival_results: dict[str, dict] = {}
    for name, ser in predictors.items():
        bias_map = {d: int(v) for d, v in ser.items()}
        r, t, _ = simulate_orb_directional(ger, bias_map, mode="filter_short")
        res = report_run(f"filter_short::{name}", r, t)
        revival_results[name] = {**res, "ret": r, "trades": t}

    # ----- Null check: invert each predictor in combined mode -----
    section("Null check — invert each predictor (combined mode); expect Sharpe degradation")
    for name, ser in predictors.items():
        bias_map = {d: int(v) for d, v in ser.items()}
        r, t, _ = simulate_orb_directional(ger, bias_map, mode="invert")
        base_sh = combined_results[name]["sharpe"]
        sh = annualized_sharpe(r.to_numpy())
        gap = base_sh - sh
        print(f"  combined::{name:<14s}  fade {sh:>+6.2f}  base {base_sh:>+6.2f}  gap {gap:>+6.2f}  "
              f"{'PASS' if gap >= 0.30 else 'FAIL'}")

    # ----- Regime breakdown for top candidates -----
    section("Regime breakdown — top combined-mode candidates")
    ranked = sorted(combined_results.items(), key=lambda kv: kv[1]["sharpe"], reverse=True)[:5]
    for name, res in ranked:
        print(f"\n  combined::{name}  full Sh {res['sharpe']:+.2f}  trades {len(res['trades'])}")
        regime_split(res["ret"], res["trades"])

    section("Regime breakdown — top filter_long candidates")
    ranked = sorted(filter_long_results.items(), key=lambda kv: kv[1]["sharpe"], reverse=True)[:5]
    for name, res in ranked:
        print(f"\n  filter_long::{name}  full Sh {res['sharpe']:+.2f}  trades {len(res['trades'])}")
        regime_split(res["ret"], res["trades"])

    section("Regime breakdown — top revival (short-only) candidates")
    ranked = sorted(revival_results.items(), key=lambda kv: kv[1]["sharpe"], reverse=True)[:5]
    for name, res in ranked:
        print(f"\n  filter_short::{name}  full Sh {res['sharpe']:+.2f}  trades {len(res['trades'])}")
        regime_split(res["ret"], res["trades"])

    # ----- Cost sensitivity on best survivor -----
    section("Cost sensitivity — best combined-mode survivor")
    best_name, best_res = max(combined_results.items(), key=lambda kv: kv[1]["sharpe"])
    print(f"  best combined-mode: {best_name}  Sh {best_res['sharpe']:+.2f}")
    best_ser = predictors[best_name]
    bias_map = {d: int(v) for d, v in best_ser.items()}
    for c in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0):
        r, t, _ = simulate_orb_directional(ger, bias_map, mode="combined", cost_points=c)
        sh = annualized_sharpe(r.to_numpy())
        print(f"    cost={c:>3.1f}pt  Sh {sh:>+6.2f}  trades {len(t):>4d}")

    # ----- Final summary -----
    section("Summary")
    parent_long_only_sh = 0.76   # research baseline from orb.md
    parent_short_only_sh = 0.01
    parent_symmetric_sh = 0.58

    print(f"  Parent baselines (from orb.md):")
    print(f"    LONG-only symmetric ORB    Sh {parent_long_only_sh:+.2f}")
    print(f"    SHORT-only symmetric ORB   Sh {parent_short_only_sh:+.2f}")
    print(f"    Symmetric both-directions  Sh {parent_symmetric_sh:+.2f}")
    print()

    print(f"  Top combined-mode (Sharpe lift over LONG-only +0.76 = REVIVAL value):")
    ranked = sorted(combined_results.items(), key=lambda kv: kv[1]["sharpe"], reverse=True)[:5]
    for name, res in ranked:
        lift = res["sharpe"] - parent_long_only_sh
        print(f"    {name:<18s}  Sh {res['sharpe']:>+6.2f}  vs +0.76  ->  lift {lift:>+6.2f}  trades {len(res['trades'])}")

    print()
    print(f"  Top filter_long (Sharpe lift over LONG-only +0.76 = FILTER value):")
    ranked = sorted(filter_long_results.items(), key=lambda kv: kv[1]["sharpe"], reverse=True)[:5]
    for name, res in ranked:
        lift = res["sharpe"] - parent_long_only_sh
        print(f"    {name:<18s}  Sh {res['sharpe']:>+6.2f}  vs +0.76  ->  lift {lift:>+6.2f}  trades {len(res['trades'])}")

    print()
    print(f"  Top revival short-only (vs SHORT-only baseline +0.01):")
    ranked = sorted(revival_results.items(), key=lambda kv: kv[1]["sharpe"], reverse=True)[:5]
    for name, res in ranked:
        lift = res["sharpe"] - parent_short_only_sh
        print(f"    {name:<18s}  Sh {res['sharpe']:>+6.2f}  vs +0.01  ->  lift {lift:>+6.2f}  trades {len(res['trades'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
