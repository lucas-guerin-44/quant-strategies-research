#!/usr/bin/env python3
"""
ORB_DAX × Market Sentiment Overlay — Layer 1 Phase 2 demo.

Thesis: experiments/orb_dax_sentiment/orb_dax_sentiment.md

Base strategy: GER40 M5 T+180 LONG-only opening-range breakout (the deployed
`orb_dax` config). We re-simulate it inline (numpy inner loop) and expose per-
trade (entry_date, entry_bar_idx, exit_bar_idx, pnl_net). On top of those
trades we build a daily sentiment composite from VIX / VIX3M / SPX500 / GER40
D1 trend / EURUSD / HYG (all D1, all point-in-time on t-1 close — strictly
observable before the Xetra open) and run 6 overlay variants + null check.

Run: ``venv/Scripts/python.exe experiments/orb_dax_sentiment/sentiment_demo.py``
"""

from __future__ import annotations

import os
import sys
from datetime import time as dtime

import numpy as np
import pandas as pd

# Windows cp1252 default kills unicode. Force utf-8 stdout.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))

from data import fetch_ohlc  # noqa: E402


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SYMBOL = "GER40"
TIMEFRAME = "M5"
START_DATE = "2019-01-01"
END_DATE = "2026-04-18"

OR_MINUTES = 30
ENTRY_CUTOFF_MIN = 180
TOD_EXIT_MIN = 180
EXIT_MIN_BEFORE_CLOSE = 5
COST_POINTS_ROUND_TRIP = 1.0

RTH_OPEN = dtime(9, 0)
RTH_CLOSE = dtime(17, 30)
SESSION_TZ = "Europe/Berlin"

_rth_minutes = (RTH_CLOSE.hour * 60 + RTH_CLOSE.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)
BARS_PER_DAY = _rth_minutes // 5
DAYS_PER_YEAR = 252
BARS_PER_YEAR = BARS_PER_DAY * DAYS_PER_YEAR

# Sentiment composite config.
SENTIMENT_INPUTS = ["VIX", "VIX3M", "SPX500", "GER40", "EURUSD", "HYG"]
ZSCORE_WIN = 252         # expanding then 252-day trailing
QUINTILE_MIN_HISTORY = 252  # need 1y of composite before forming quintile cuts
QUINTILE_N = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f"\n{'=' * 78}\n  {t}\n{'=' * 78}")


def load_m5(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, "M5", START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f"No M5 bars for {symbol}.")
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df.index = df.index.tz_convert(SESSION_TZ)
    times = df.index.time
    df = df.loc[(times >= RTH_OPEN) & (times < RTH_CLOSE)]
    df = df.loc[df.index.dayofweek < 5]
    return df


def load_d1(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, "D1", "2017-01-01", END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f"No D1 bars for {symbol}.")
    df = raw[["timestamp", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df = df.rename(columns={"close": symbol})
    return df[[symbol]]


def max_drawdown(eq: np.ndarray) -> float:
    rm = np.maximum.accumulate(eq)
    dd = (eq - rm) / rm
    return float(dd.min()) if len(dd) else 0.0


def annualized_sharpe_bar(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if r.size == 0:
        return 0.0
    s = r.std(ddof=1)
    if s == 0 or not np.isfinite(s):
        return 0.0
    return float(r.mean() / s * np.sqrt(BARS_PER_YEAR))


# ---------------------------------------------------------------------------
# ORB long-only T+180 simulator — numpy inner loop
# ---------------------------------------------------------------------------

def simulate_orb_long_t180(
    bars: pd.DataFrame,
    cost_points: float = COST_POINTS_ROUND_TRIP,
) -> tuple[np.ndarray, list[dict]]:
    idx = bars.index
    n_bars = len(bars)
    open_arr = bars["open"].to_numpy(dtype=np.float64)
    high_arr = bars["high"].to_numpy(dtype=np.float64)
    low_arr = bars["low"].to_numpy(dtype=np.float64)
    close_arr = bars["close"].to_numpy(dtype=np.float64)

    rth_open_min = RTH_OPEN.hour * 60 + RTH_OPEN.minute
    rth_close_min = RTH_CLOSE.hour * 60 + RTH_CLOSE.minute
    hours = np.asarray(idx.hour, dtype=np.int32)
    minutes = np.asarray(idx.minute, dtype=np.int32)
    minute_of_day = hours * 60 + minutes - rth_open_min

    dates_obj = np.asarray(idx.date)
    change = np.empty(n_bars, dtype=bool)
    change[0] = True
    change[1:] = dates_obj[1:] != dates_obj[:-1]
    day_starts = np.flatnonzero(change)
    day_ends = np.empty_like(day_starts)
    day_ends[:-1] = day_starts[1:]
    day_ends[-1] = n_bars

    ret_arr = np.zeros(n_bars, dtype=np.float64)
    trades: list[dict] = []

    rth_minutes = rth_close_min - rth_open_min
    exit_cutoff = rth_minutes - EXIT_MIN_BEFORE_CLOSE
    or_end = OR_MINUTES
    entry_cutoff = ENTRY_CUTOFF_MIN
    min_day_bars = (OR_MINUTES // 5) + 4

    for d_i in range(len(day_starts)):
        s = int(day_starts[d_i])
        e = int(day_ends[d_i])
        n = e - s
        if n < min_day_bars:
            continue

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

        post_or = np.flatnonzero(day_mod >= or_end)
        if post_or.size == 0:
            continue
        first_post = int(post_or[0])

        position = 0
        entry_px = 0.0
        entry_bar_idx = -1
        stop_px = 0.0
        long_taken = False

        for i in range(first_post, n):
            mod = int(day_mod[i])
            is_last = (i == n - 1)

            if position != 0 and i > entry_bar_idx:
                prev_close = day_close[i - 1]
                cur_close = day_close[i]
                ret_arr[s + i] = position * (cur_close - prev_close) / prev_close

            if position != 0:
                bar_low = day_low[i]
                tod_forced = (i - entry_bar_idx) * 5 >= TOD_EXIT_MIN
                hit_stop = bar_low <= stop_px
                forced_close = (mod >= exit_cutoff) or is_last or tod_forced
                if hit_stop or forced_close:
                    if hit_stop:
                        exit_px = stop_px
                        reason = "stop"
                    elif tod_forced:
                        exit_px = float(day_close[i])
                        reason = "tod"
                    else:
                        exit_px = float(day_close[i])
                        reason = "eod"
                    cost_ret = cost_points / entry_px
                    ret_arr[s + i] -= cost_ret
                    pnl_net = (exit_px - entry_px) / entry_px - cost_ret
                    trades.append({
                        "entry_date": dates_obj[s + entry_bar_idx],
                        "entry_bar_idx": s + entry_bar_idx,
                        "exit_bar_idx": s + i,
                        "entry_px": entry_px,
                        "exit_px": exit_px,
                        "pnl_net": pnl_net,
                        "reason": reason,
                    })
                    position = 0
                    entry_bar_idx = -1
                if position != 0:
                    continue

            # Entry logic — LONG-only, max 1 entry per day, before entry-cutoff.
            if not long_taken and mod < entry_cutoff and i + 1 < n:
                if day_close[i] > or_high:
                    position = 1
                    entry_px = float(day_open[i + 1])
                    if not np.isfinite(entry_px) or entry_px <= 0:
                        position = 0
                        continue
                    stop_px = or_low
                    entry_bar_idx = i + 1
                    long_taken = True

    return ret_arr, trades


# ---------------------------------------------------------------------------
# Sentiment composite — expanding-window z-scoring, no look-ahead
# ---------------------------------------------------------------------------

def build_composite() -> pd.DataFrame:
    """Returns a DataFrame indexed by date (Berlin trading day) with column
    `composite` representing the day's sentiment reading available at Xetra
    open (i.e., computed strictly from t-1 closes)."""
    series = {}
    for sym in SENTIMENT_INPUTS:
        series[sym] = load_d1(sym)
    df = pd.concat(series.values(), axis=1)
    df.index = df.index.tz_convert(SESSION_TZ).normalize()
    df = df.sort_index().ffill()

    vix = df["VIX"]
    vix3m = df["VIX3M"]
    spx = df["SPX500"]
    ger = df["GER40"]
    eur = df["EURUSD"]
    hyg = df["HYG"]

    # Raw features (sign so larger = MORE risk-ON).
    f_vix_z = -(vix - vix.rolling(60, min_periods=20).mean()) / vix.rolling(60, min_periods=20).std(ddof=1)
    f_vix_chg = -(vix / vix.shift(1) - 1.0)
    f_term = -(vix / vix3m - 1.0)
    f_spx_overnight = spx / spx.shift(1) - 1.0
    ma50 = ger.rolling(50, min_periods=20).mean()
    ma200 = ger.rolling(200, min_periods=100).mean()
    above50 = (ger > ma50).astype(float)
    above200 = (ger > ma200).astype(float)
    f_dax_trend = (above50 + above200) - 1.0  # -1 / 0 / +1
    f_eur_chg = eur / eur.shift(5) - 1.0
    f_hyg_chg = hyg / hyg.shift(5) - 1.0

    feats = pd.DataFrame({
        "vix_z": f_vix_z,
        "vix_chg": f_vix_chg,
        "term": f_term,
        "spx_overnight": f_spx_overnight,
        "dax_trend": f_dax_trend,
        "eur_chg": f_eur_chg,
        "hyg_chg": f_hyg_chg,
    }).dropna()

    # Z-score each feature on a 252-day trailing window (rolling, min 60 obs).
    zfeats = pd.DataFrame(index=feats.index, columns=feats.columns, dtype=float)
    for col in feats.columns:
        s = feats[col]
        mu = s.rolling(ZSCORE_WIN, min_periods=60).mean()
        sd = s.rolling(ZSCORE_WIN, min_periods=60).std(ddof=1)
        zfeats[col] = (s - mu) / sd

    composite = zfeats.mean(axis=1).rename("composite")

    # Crucial: shift by 1 day. The composite computed from D1 closes ending on
    # date X is available at the start of trading day X+1 (Xetra open the next
    # business day after the D1 close completes). Index by the *trading day it
    # applies to*.
    composite = composite.shift(1).dropna()

    out = composite.to_frame()
    out.index = out.index.date  # plain python date for easy join with trades
    return out


# ---------------------------------------------------------------------------
# Overlay application
# ---------------------------------------------------------------------------

def expanding_quintile_break(composite: pd.Series, q_lo: float, q_hi: float) -> pd.DataFrame:
    """For each date in composite, compute the quintile-lower and quintile-upper
    breakpoints using ONLY composite history strictly before that date.

    Returns DataFrame with 'lo' and 'hi' columns aligned to composite.index.
    """
    vals = composite.to_numpy(dtype=np.float64)
    n = len(vals)
    lo = np.full(n, np.nan)
    hi = np.full(n, np.nan)
    for i in range(QUINTILE_MIN_HISTORY, n):
        hist = vals[:i]
        lo[i] = np.nanquantile(hist, q_lo)
        hi[i] = np.nanquantile(hist, q_hi)
    return pd.DataFrame({"lo": lo, "hi": hi}, index=composite.index)


def apply_overlay(
    ret_arr: np.ndarray,
    trades: list[dict],
    composite_by_date: dict,
    breaks: pd.DataFrame,
    mode: str,
) -> tuple[np.ndarray, int, int, int]:
    """Returns modified ret_arr, n_kept, n_scaled, n_skipped."""
    new_ret = ret_arr.copy()
    n_kept = 0
    n_scaled = 0
    n_skipped = 0
    breaks_idx = {d: (lo, hi) for d, lo, hi in zip(breaks.index, breaks["lo"], breaks["hi"])}

    for tr in trades:
        d = tr["entry_date"]
        comp = composite_by_date.get(d, np.nan)
        # Look up breaks aligned to the trade date; if not present (early days), keep trade unmodified.
        b = breaks_idx.get(pd.Timestamp(d).date(), None)
        if b is None:
            # try with timestamp variants
            b = breaks_idx.get(d, None)
        if b is None or not np.isfinite(comp) or not np.isfinite(b[0]) or not np.isfinite(b[1]):
            n_kept += 1
            continue
        lo, hi = b
        i0, i1 = tr["entry_bar_idx"], tr["exit_bar_idx"]
        scale = 1.0
        skip = False

        if mode == "baseline":
            pass
        elif mode == "gate_q1":
            skip = comp <= lo
        elif mode == "gate_neg":
            skip = comp < 0
        elif mode == "size_q5":
            if comp >= hi:
                scale = 2.0
        elif mode == "combo":
            if comp <= lo:
                skip = True
            elif comp >= hi:
                scale = 2.0
        elif mode == "inv_gate":  # gate top quintile (null)
            skip = comp >= hi
        elif mode == "inv_size":  # 2x bottom quintile (null)
            if comp <= lo:
                scale = 2.0
        else:
            raise ValueError(f"unknown mode: {mode}")

        if skip:
            new_ret[i0:i1 + 1] = 0.0
            n_skipped += 1
        elif scale != 1.0:
            new_ret[i0:i1 + 1] *= scale
            n_scaled += 1
            n_kept += 1
        else:
            n_kept += 1
    return new_ret, n_kept, n_scaled, n_skipped


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_run(label: str, ret_arr: np.ndarray, trades_in: int, n_kept: int, n_scaled: int, n_skipped: int) -> dict:
    eq = np.cumprod(1.0 + ret_arr)
    sh = annualized_sharpe_bar(ret_arr)
    mdd = max_drawdown(eq)
    total_ret = float(eq[-1] - 1.0) if len(eq) else 0.0
    years = len(ret_arr) / BARS_PER_YEAR
    cagr = (1.0 + total_ret) ** (1.0 / years) - 1.0 if years > 0 and total_ret > -1 else float("nan")
    print(
        f"  {label:<18}  Sh {sh:+.3f}   MDD {mdd*100:+.2f}%   "
        f"TotRet {total_ret*100:+.1f}%   CAGR {cagr*100:+.2f}%   "
        f"trades(in/kept/scaled/skip): {trades_in}/{n_kept}/{n_scaled}/{n_skipped}"
    )
    return {"label": label, "sharpe": sh, "mdd": mdd, "total_ret": total_ret, "cagr": cagr,
            "n_kept": n_kept, "n_scaled": n_scaled, "n_skipped": n_skipped}


def regime_breakdown(label: str, ret_arr: np.ndarray, bars: pd.DataFrame) -> None:
    idx = bars.index
    years = idx.year.values
    windows = [("2019-2020", (years >= 2019) & (years <= 2020)),
               ("2021-2022", (years >= 2021) & (years <= 2022)),
               ("2023-2026", years >= 2023)]
    print(f"  Regime breakdown — {label}")
    for name, mask in windows:
        if not mask.any():
            continue
        r = ret_arr[mask]
        sh = annualized_sharpe_bar(r)
        eq = np.cumprod(1.0 + r)
        mdd = max_drawdown(eq)
        print(f"    {name}:  Sh {sh:+.3f}   MDD {mdd*100:+.2f}%   bars {mask.sum()}")


def cost_sensitivity(bars: pd.DataFrame, composite_by_date: dict, breaks: pd.DataFrame, mode: str) -> None:
    print(f"  Cost sensitivity — {mode}")
    for cost in (0.5, 1.0, 1.5, 2.0):
        ret_arr, trades = simulate_orb_long_t180(bars, cost_points=cost)
        new_ret, nk, ns, nx = apply_overlay(ret_arr, trades, composite_by_date, breaks, mode)
        sh = annualized_sharpe_bar(new_ret)
        print(f"    {cost:.1f}pt RT:  Sh {sh:+.3f}   kept/scaled/skipped {nk}/{ns}/{nx}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    section("Loading GER40 M5 (Xetra RTH)")
    bars = load_m5(SYMBOL)
    print(f"  {len(bars):,} M5 bars  |  {bars.index.min()} -> {bars.index.max()}")

    section("Building sentiment composite from D1 inputs")
    comp_df = build_composite()
    print(f"  {len(comp_df)} daily composite values  |  "
          f"{comp_df.index.min()} -> {comp_df.index.max()}")
    print(f"  composite stats: mean={comp_df['composite'].mean():+.3f}  "
          f"std={comp_df['composite'].std():.3f}  "
          f"min={comp_df['composite'].min():+.2f}  max={comp_df['composite'].max():+.2f}")

    composite = comp_df["composite"]
    composite_by_date = dict(zip(comp_df.index, comp_df["composite"].values))
    breaks = expanding_quintile_break(composite, 0.2, 0.8)
    n_valid_breaks = breaks.dropna().shape[0]
    print(f"  quintile-break series: {n_valid_breaks} valid days (after {QUINTILE_MIN_HISTORY}-day warmup)")

    section("Baseline ORB_DAX T+180 LONG-only — reconfirm deployed numbers")
    ret_arr, trades = simulate_orb_long_t180(bars, cost_points=COST_POINTS_ROUND_TRIP)
    print(f"  {len(trades)} trades over {len(bars) / BARS_PER_DAY / DAYS_PER_YEAR:.2f} years")
    _ = report_run("baseline", ret_arr, len(trades), len(trades), 0, 0)

    section("Per-quintile baseline edge — does composite carry information?")
    breaks_idx = {d: (lo, hi) for d, lo, hi in zip(breaks.index, breaks["lo"], breaks["hi"])}
    by_quintile: dict[int, list[float]] = {q: [] for q in range(QUINTILE_N)}
    no_comp = 0
    for tr in trades:
        d = tr["entry_date"]
        comp = composite_by_date.get(d, np.nan)
        b = breaks_idx.get(d, None)
        if b is None or not np.isfinite(comp) or not np.isfinite(b[0]):
            no_comp += 1
            continue
        lo, hi = b
        # 5-quantile via expanding break — we computed q20/q80; map to {bot/mid/top} buckets first.
        if comp <= lo:
            q = 0
        elif comp >= hi:
            q = 4
        else:
            q = 2
        by_quintile[q].append(tr["pnl_net"])
    print(f"  trades without composite (warmup): {no_comp}")
    for q in sorted(by_quintile):
        arr = np.array(by_quintile[q], dtype=np.float64)
        if arr.size == 0:
            continue
        mu = arr.mean() * 100
        wr = (arr > 0).mean() * 100
        label = {0: "bot Q1 (risk-off)", 2: "mid Q2-Q4", 4: "top Q5 (risk-on)"}[q]
        print(f"    {label:<22}  n={arr.size:>4}   avg PnL {mu:+.4f}%   WR {wr:.1f}%   "
              f"sum {arr.sum()*100:+.2f}%")

    section("Overlay variants")
    rows = []
    for mode in ["baseline", "gate_q1", "gate_neg", "size_q5", "combo", "inv_gate", "inv_size"]:
        new_ret, nk, ns, nx = apply_overlay(ret_arr, trades, composite_by_date, breaks, mode)
        rows.append(report_run(mode, new_ret, len(trades), nk, ns, nx))

    # Identify best-performing non-null variant.
    non_null = [r for r in rows if r["label"] not in ("baseline", "inv_gate", "inv_size")]
    best = max(non_null, key=lambda r: r["sharpe"])
    baseline_sh = next(r["sharpe"] for r in rows if r["label"] == "baseline")
    inv_gate_sh = next(r["sharpe"] for r in rows if r["label"] == "inv_gate")
    inv_size_sh = next(r["sharpe"] for r in rows if r["label"] == "inv_size")

    section("Kill-criteria check — pre-committed (G-Q1 variant)")
    g_q1 = next(r for r in rows if r["label"] == "gate_q1")
    delta_sh = g_q1["sharpe"] - baseline_sh
    inv_gap = g_q1["sharpe"] - inv_gate_sh
    checks = [
        ("Sharpe lift ≥ +0.10", delta_sh >= 0.10, f"{delta_sh:+.3f}"),
        ("MDD not worse by >1pp", g_q1["mdd"] >= (-abs(rows[0]["mdd"]) - 0.01),
         f"baseline {rows[0]['mdd']*100:+.2f}% vs G-Q1 {g_q1['mdd']*100:+.2f}%"),
        ("Trade count ≥ 200", g_q1["n_kept"] >= 200, f"{g_q1['n_kept']} kept"),
        ("Null check: G-Q1 Sh − Inv-G-Q1 Sh ≥ +0.20", inv_gap >= 0.20, f"gap {inv_gap:+.3f}"),
    ]
    for name, ok, detail in checks:
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {name}   ({detail})")

    section(f"Regime breakdown — baseline vs best variant ({best['label']})")
    baseline_ret, _ = simulate_orb_long_t180(bars, cost_points=COST_POINTS_ROUND_TRIP)
    regime_breakdown("baseline", baseline_ret, bars)
    best_ret, _, _, _ = apply_overlay(ret_arr, trades, composite_by_date, breaks, best["label"])
    regime_breakdown(best["label"], best_ret, bars)

    section(f"Cost sensitivity — best variant ({best['label']})")
    cost_sensitivity(bars, composite_by_date, breaks, best["label"])

    section("Summary")
    print(f"  Baseline (deployed):  Sh {baseline_sh:+.3f}")
    print(f"  Best overlay variant: {best['label']}  Sh {best['sharpe']:+.3f}  (delta {best['sharpe']-baseline_sh:+.3f})")
    print(f"  Null (Inv-G-Q1):      Sh {inv_gate_sh:+.3f}  (gap vs G-Q1: {inv_gap:+.3f})")
    print(f"  Null (Inv-S-Q5):      Sh {inv_size_sh:+.3f}")


if __name__ == "__main__":
    main()
