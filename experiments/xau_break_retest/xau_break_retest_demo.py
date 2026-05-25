#!/usr/bin/env python3
"""XAUUSD M5 — Break of Structure + Retest continuation (NY cash-open session).

Thesis: experiments/xau_break_retest/xau_break_retest.md

Rules:
  Session window     = 13:00 -> 16:00 UTC (~09:00-12:00 ET, NY cash open + 2.5h).
  Entry cutoff       = 15:00 UTC (no new entries after this; manage open).
  For each in-session M5 bar b:
    swing_high = max(high[b-LOOKBACK : b]); swing_low = min(low[...])
    If flat and bar closes > swing_high AND no break-yet today: arm UP break.
    If flat and bar closes < swing_low  AND no break-yet today: arm DOWN break.
  Within RETEST_WINDOW bars of the break, look for retest:
    UP retest: bar low touches within RETEST_TOL_ATR * ATR above swing_high
               AND bar close stays above swing_high (no invalidation).
               -> ENTER LONG at bar close.
    DOWN retest: symmetric.
  Stop: swing_high - STOP_ATR_MULT * ATR for LONG (mirror for SHORT).
  Exit (first of): stop hit, TIME_EXIT_MIN, session-end (16:00 UTC), or
                   close back through level (invalidation pre-entry).
  Max 1 round-trip per direction per day.

Null check: 'fade' direction inverts each entry (short the UP retest, long the
DOWN retest), reporting fade-gap = baseline_Sharpe - fade_Sharpe.

Cost: in XAU points per round-trip (Eightcap raw ~0.1-0.2 pt RT; sweep
0.1/0.2/0.4/0.8 pt).

Run:
  venv\\Scripts\\python.exe experiments\\xau_break_retest\\xau_break_retest_demo.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, "..", "backtesting-engine-2.0")))

DATA_PATH = os.path.join(_ROOT, "ohlc_data", "XAUUSD_M5.csv")

# ---------------------------------------------------------------------------
# Config (5 free parameters — see thesis §"Signal math")
# ---------------------------------------------------------------------------

SWING_LOOKBACK_BARS = 20
RETEST_WINDOW_BARS = 4
RETEST_TOL_ATR = 0.30
STOP_ATR_MULT = 1.20
SESSION_START_UTC = 13
SESSION_END_UTC = 16
ENTRY_CUTOFF_UTC = 15

ATR_PERIOD = 14
TIME_EXIT_MIN = 60   # 12 M5 bars
TIME_EXIT_BARS = TIME_EXIT_MIN // 5

# Cost model: XAU points per round-trip.
COST_POINTS_DEFAULT = 0.20    # Eightcap raw realistic ~0.16 spread + commission
COST_POINTS_SWEEP = (0.1, 0.2, 0.4, 0.8)

# Annualization (Sharpe). Per-trade returns; we'll annualize by trades-per-year.
DAYS_PER_YEAR = 252

# Pre-committed kill criteria (from thesis)
KC_SHARPE_FULL = 0.30
KC_SHARPE_HOLDOUT = 0.0
KC_MDD = 0.25
KC_TRADES = 200
KC_WR = 0.35
KC_PF = 1.10
KC_FADE_GAP = 0.30
KC_COST_STRESS_PT = 0.4   # 2x default 0.2pt
KC_DEFLATED_SH = 0.20
N_VARIANTS_PRECOMMITTED = 6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f"\n{'=' * 92}\n  {t}\n{'=' * 92}\n")


def label_regime(year: int) -> str:
    if year <= 2020:
        return "W1 2019-2020"
    if year <= 2022:
        return "W2 2021-2022"
    return "W3 2023-2026 (holdout)"


def annualized_sharpe(r: np.ndarray, trades_per_year: float) -> float:
    r = r[np.isfinite(r)]
    if r.size < 2:
        return 0.0
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(trades_per_year))


def max_drawdown(eq: np.ndarray) -> float:
    if len(eq) == 0:
        return 0.0
    rm = np.maximum.accumulate(eq)
    dd = (eq - rm) / rm
    return float(dd.min())


def deflated_sharpe(observed_sh: float, returns: np.ndarray, n_trials: int) -> float:
    """Bailey & Lopez de Prado (2014) deflated Sharpe.

    Approximation: SR* = expected_max_SR_under_null adjusted for skew/kurtosis.
    Returns the deflated Sharpe value (haircut applied to observed).
    """
    r = returns[np.isfinite(returns)]
    n = r.size
    if n < 30 or n_trials < 2:
        return observed_sh
    # Skew/kurtosis correction
    from math import sqrt, log, pi
    g3 = float(pd.Series(r).skew())
    g4 = float(pd.Series(r).kurt())  # excess kurt
    # SR variance approx
    sr_std = sqrt((1 - g3 * observed_sh + (g4 / 4.0) * observed_sh ** 2) / max(n - 1, 1))
    # Expected max SR under N independent trials of N(0, sr_std^2)
    em = 0.5772 + log(n_trials)    # Euler-Mascheroni for log-n approx
    e_max = sr_std * sqrt(2 * log(max(n_trials, 2)))
    return float(observed_sh - e_max)


# ---------------------------------------------------------------------------
# Data load
# ---------------------------------------------------------------------------

def load_m5() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df = df[~df["timestamp"].duplicated(keep="first")].reset_index(drop=True)
    # Restrict to NY-session window. Pre-filter to session_start - lookback*5min margin
    # so swing/ATR contexts at session-start have history.
    df["hour"] = df["timestamp"].dt.hour
    df["minute"] = df["timestamp"].dt.minute
    df["date"] = df["timestamp"].dt.date
    df["dow"] = df["timestamp"].dt.dayofweek
    return df


# ---------------------------------------------------------------------------
# Simulator (numpy inner loop)
# ---------------------------------------------------------------------------

def simulate_break_retest(
    df: pd.DataFrame,
    swing_lookback: int = SWING_LOOKBACK_BARS,
    retest_window: int = RETEST_WINDOW_BARS,
    retest_tol_atr: float = RETEST_TOL_ATR,
    stop_atr_mult: float = STOP_ATR_MULT,
    session_start_utc: int = SESSION_START_UTC,
    session_end_utc: int = SESSION_END_UTC,
    entry_cutoff_utc: int = ENTRY_CUTOFF_UTC,
    time_exit_bars: int = TIME_EXIT_BARS,
    cost_points: float = COST_POINTS_DEFAULT,
    direction_filter: str = "both",   # 'both' | 'long' | 'short'
    fade: bool = False,
) -> tuple[np.ndarray, list[dict]]:
    """Returns per-trade NET return array + trade-detail list.

    Per-trade return: signed_PnL_in_points / entry_price - cost/entry_price.
    """
    # Materialize numpy arrays once before the outer loop. CLAUDE.md PRIORITIZE
    # NUMPY ALWAYS — pandas .loc inside an outer loop is forbidden.
    ts = df["timestamp"].to_numpy()
    hour = df["hour"].to_numpy(dtype=np.int32)
    o = df["open"].to_numpy(dtype=np.float64)
    h = df["high"].to_numpy(dtype=np.float64)
    l = df["low"].to_numpy(dtype=np.float64)
    c = df["close"].to_numpy(dtype=np.float64)
    dows = df["dow"].to_numpy(dtype=np.int32)
    # date as ordinal int64 for fast group detection
    dates = df["timestamp"].dt.normalize().to_numpy()

    # Precompute ATR (M5, 14-period Wilder's-ish: use SMA of TR for simplicity)
    n = len(df)
    tr = np.zeros(n, dtype=np.float64)
    tr[0] = h[0] - l[0]
    prev_c = c[:-1]
    cur_h = h[1:]
    cur_l = l[1:]
    tr[1:] = np.maximum.reduce([cur_h - cur_l, np.abs(cur_h - prev_c), np.abs(cur_l - prev_c)])
    # SMA ATR (simple, fine for stop-distance estimation on M5)
    atr = pd.Series(tr).rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean().to_numpy()

    # Day boundaries
    change = np.empty(n, dtype=bool)
    change[0] = True
    change[1:] = dates[1:] != dates[:-1]
    day_starts = np.flatnonzero(change)
    day_ends = np.empty_like(day_starts)
    day_ends[:-1] = day_starts[1:]
    day_ends[-1] = n

    trades: list[dict] = []
    rets: list[float] = []

    for d_i in range(len(day_starts)):
        s = int(day_starts[d_i])
        e = int(day_ends[d_i])
        if dows[s] >= 5:  # weekend defensive
            continue

        # Per-day: identify in-session bars (session_start_utc <= hour < session_end_utc)
        day_h = hour[s:e]
        day_in = np.flatnonzero((day_h >= session_start_utc) & (day_h < session_end_utc))
        if day_in.size < swing_lookback + 2:
            continue
        # entry_cutoff: hour < entry_cutoff_utc
        day_entry_mask = day_h < entry_cutoff_utc

        # Walk in-session bars
        # State per day: up/down break flags + retest counters
        up_break_armed = False
        down_break_armed = False
        up_break_swing = 0.0
        down_break_swing = 0.0
        up_break_atr = 0.0
        down_break_atr = 0.0
        up_break_idx = -1  # local index (within day) of break bar
        down_break_idx = -1
        long_taken = False
        short_taken = False

        for local_i in day_in:
            g = s + int(local_i)  # global index
            cur_atr = atr[g - 1] if g - 1 >= 0 else np.nan
            if not np.isfinite(cur_atr) or cur_atr <= 0:
                continue
            # Need at least swing_lookback prior bars (across day boundaries OK for swing context)
            if g < swing_lookback:
                continue

            window_hi = float(h[g - swing_lookback:g].max())
            window_lo = float(l[g - swing_lookback:g].min())
            cur_close = c[g]
            cur_high = h[g]
            cur_low = l[g]
            in_entry_window = day_entry_mask[local_i]

            # ---- Detect break (only first one per direction per day) ----
            if not up_break_armed and not long_taken and cur_close > window_hi and in_entry_window:
                up_break_armed = True
                up_break_swing = window_hi
                up_break_atr = cur_atr
                up_break_idx = int(local_i)
            if not down_break_armed and not short_taken and cur_close < window_lo and in_entry_window:
                down_break_armed = True
                down_break_swing = window_lo
                down_break_atr = cur_atr
                down_break_idx = int(local_i)

            # ---- Look for retest within RETEST_WINDOW bars after break ----
            entered = False
            if up_break_armed and not long_taken:
                bars_since = int(local_i) - up_break_idx
                if 1 <= bars_since <= retest_window:
                    # UP retest: bar low touches near level AND close stays above
                    if cur_low <= up_break_swing + retest_tol_atr * up_break_atr:
                        if cur_close > up_break_swing:
                            # Valid retest — ENTER
                            entry_dir = -1 if fade else +1
                            if direction_filter == "short" and entry_dir == +1:
                                pass  # filter blocks the long-retest-continuation
                            elif direction_filter == "long" and entry_dir == -1:
                                pass
                            else:
                                _enter_and_exit(
                                    trades, rets, g, entry_dir, "up_retest",
                                    h, l, c, o, dates, dows, ts,
                                    swing_level=up_break_swing,
                                    atr_at_entry=up_break_atr,
                                    stop_atr_mult=stop_atr_mult,
                                    time_exit_bars=time_exit_bars,
                                    session_end_utc=session_end_utc,
                                    hour=hour,
                                    cost_points=cost_points,
                                    day_end_g=e,
                                )
                                long_taken = True
                                entered = True
                        else:
                            # Closed back through — invalidate up break
                            up_break_armed = False
                elif bars_since > retest_window:
                    up_break_armed = False  # retest window expired

            if down_break_armed and not short_taken and not entered:
                bars_since = int(local_i) - down_break_idx
                if 1 <= bars_since <= retest_window:
                    if cur_high >= down_break_swing - retest_tol_atr * down_break_atr:
                        if cur_close < down_break_swing:
                            entry_dir = +1 if fade else -1
                            if direction_filter == "long" and entry_dir == -1:
                                pass
                            elif direction_filter == "short" and entry_dir == +1:
                                pass
                            else:
                                _enter_and_exit(
                                    trades, rets, g, entry_dir, "down_retest",
                                    h, l, c, o, dates, dows, ts,
                                    swing_level=down_break_swing,
                                    atr_at_entry=down_break_atr,
                                    stop_atr_mult=stop_atr_mult,
                                    time_exit_bars=time_exit_bars,
                                    session_end_utc=session_end_utc,
                                    hour=hour,
                                    cost_points=cost_points,
                                    day_end_g=e,
                                )
                                short_taken = True
                        else:
                            down_break_armed = False
                elif bars_since > retest_window:
                    down_break_armed = False

    return np.asarray(rets, dtype=np.float64), trades


def _enter_and_exit(
    trades_list, rets_list,
    entry_g: int, direction: int, entry_reason: str,
    h, l, c, o, dates, dows, ts,
    swing_level: float, atr_at_entry: float,
    stop_atr_mult: float, time_exit_bars: int,
    session_end_utc: int, hour, cost_points: float, day_end_g: int,
) -> None:
    """Resolve a trade from entry_g onward. Direction = +1 long, -1 short.
    Entry at close of entry_g bar; exit on first of (stop, time, session_end).
    Updates trades_list and rets_list in place.
    """
    entry_px = float(c[entry_g])
    if direction == +1:
        stop_px = swing_level - stop_atr_mult * atr_at_entry
    else:
        stop_px = swing_level + stop_atr_mult * atr_at_entry

    # Walk forward within the SAME day (don't carry overnight). The session_end_utc
    # constraint + day_end_g sandwich enforces this.
    max_bar = min(entry_g + time_exit_bars + 1, day_end_g)
    exit_px = entry_px
    exit_reason = "session_end"

    for j in range(entry_g + 1, max_bar):
        # Session-end check
        if hour[j] >= session_end_utc:
            exit_px = float(c[j - 1]) if j - 1 > entry_g else float(c[entry_g])
            # Actually: take the close of the last in-session bar (j-1 if j is first out)
            exit_px = float(c[j - 1]) if hour[j - 1] < session_end_utc else float(c[entry_g])
            exit_reason = "session_end"
            break
        # Stop check (bar low/high)
        bar_low = l[j]
        bar_high = h[j]
        if direction == +1 and bar_low <= stop_px:
            exit_px = stop_px
            exit_reason = "stop"
            break
        if direction == -1 and bar_high >= stop_px:
            exit_px = stop_px
            exit_reason = "stop"
            break
        # Time exit?
        if j - entry_g >= time_exit_bars:
            exit_px = float(c[j])
            exit_reason = "time"
            break
    else:
        # Loop completed without break — exit at last bar
        exit_px = float(c[max_bar - 1]) if max_bar > entry_g + 1 else float(c[entry_g])
        exit_reason = "time_or_session"

    gross_points = direction * (exit_px - entry_px)
    net_points = gross_points - cost_points
    net_ret = net_points / entry_px  # fractional

    rets_list.append(net_ret)
    trades_list.append({
        "entry_ts": ts[entry_g],
        "entry_px": entry_px,
        "exit_px": exit_px,
        "direction": direction,
        "entry_reason": entry_reason,
        "exit_reason": exit_reason,
        "gross_points": gross_points,
        "net_points": net_points,
        "net_ret": net_ret,
        "swing_level": swing_level,
        "stop_px": stop_px,
        "atr": atr_at_entry,
        "year": pd.Timestamp(ts[entry_g]).year,
        "regime": label_regime(pd.Timestamp(ts[entry_g]).year),
        "dow": int(dows[entry_g]),
    })


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_run(label: str, rets: np.ndarray, trades: list[dict]) -> dict:
    if rets.size == 0:
        print(f"  [{label}]: empty (0 trades)")
        return {"sharpe": 0.0, "mdd": 0.0, "n": 0, "wr": 0.0, "pf": 0.0,
                "mean": 0.0, "tpy": 0.0, "total_pts": 0.0}
    eq = (1.0 + rets).cumprod()
    n = len(rets)
    # Years span = first → last trade time
    first_year = trades[0]["entry_ts"]
    last_year = trades[-1]["entry_ts"]
    years = max((pd.Timestamp(last_year) - pd.Timestamp(first_year)).days / 365.25, 1e-9)
    tpy = n / years
    sh = annualized_sharpe(rets, trades_per_year=tpy)
    mdd = max_drawdown(eq)
    wins = rets[rets > 0]
    losses = rets[rets <= 0]
    wr = len(wins) / n if n else 0.0
    gw = float(wins.sum()) if len(wins) else 0.0
    gl = float(-losses.sum()) if len(losses) else 0.0
    pf = gw / gl if gl > 0 else float("inf")
    total_pts = float(np.sum([t["net_points"] for t in trades]))
    total_ret = float(eq[-1] - 1.0)
    cagr = (1 + total_ret) ** (1 / years) - 1 if years > 0 else 0.0

    print(f"  [{label}]")
    print(f"    period      : {pd.Timestamp(first_year).date()} -> {pd.Timestamp(last_year).date()} ({years:.1f}y)")
    print(f"    trades      : {n}  ({tpy:.0f}/yr)")
    print(f"    Sharpe      : {sh:+.2f}")
    print(f"    Max DD      : {mdd * 100:+.2f}%")
    print(f"    total ret   : {total_ret * 100:+.2f}%")
    print(f"    CAGR        : {cagr * 100:+.2f}%")
    print(f"    WR          : {wr * 100:.1f}%")
    print(f"    PF          : {pf:.2f}")
    print(f"    mean/trade  : {rets.mean() * 100:+.4f}%  ({rets.mean() * 10000:+.2f} bp)")
    print(f"    total points: {total_pts:+.1f}")
    return {"sharpe": sh, "mdd": mdd, "n": n, "wr": wr, "pf": pf,
            "mean": float(rets.mean()), "tpy": tpy, "total_pts": total_pts,
            "cagr": cagr}


def regime_breakdown(rets: np.ndarray, trades: list[dict]) -> dict:
    if rets.size == 0:
        return {}
    out = {}
    by_regime: dict = {}
    for r, t in zip(rets, trades):
        by_regime.setdefault(t["regime"], []).append(r)
    for w in ("W1 2019-2020", "W2 2021-2022", "W3 2023-2026 (holdout)"):
        arr = np.asarray(by_regime.get(w, []), dtype=np.float64)
        if arr.size < 20:
            print(f"  {w:<26s} (n={arr.size} insufficient)")
            continue
        eq = (1 + arr).cumprod()
        # tpy approx: regime years
        n = arr.size
        # extract first/last ts for this regime
        ts = [pd.Timestamp(t["entry_ts"]) for t in trades if t["regime"] == w]
        years = max((ts[-1] - ts[0]).days / 365.25, 1e-9)
        tpy = n / years
        sh = annualized_sharpe(arr, trades_per_year=tpy)
        mdd = max_drawdown(eq)
        mean = arr.mean()
        wins = arr[arr > 0]
        wr = len(wins) / n if n else 0.0
        print(f"  {w:<26s} n={n:>4d}  Sh {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  "
              f"WR {wr * 100:>4.1f}%  mean {mean * 10000:>+6.2f}bp")
        out[w] = {"sharpe": sh, "mdd": mdd, "n": n, "wr": wr, "mean": mean}
    return out


def cost_sweep(df: pd.DataFrame, label: str, **kwargs) -> None:
    print(f"  [{label} — cost sweep]")
    for cp in COST_POINTS_SWEEP:
        rets, trades = simulate_break_retest(df, cost_points=cp, **kwargs)
        if rets.size == 0:
            print(f"    cost={cp:.2f}pt  (no trades)")
            continue
        first = pd.Timestamp(trades[0]["entry_ts"])
        last = pd.Timestamp(trades[-1]["entry_ts"])
        years = max((last - first).days / 365.25, 1e-9)
        tpy = len(rets) / years
        sh = annualized_sharpe(rets, trades_per_year=tpy)
        eq = (1 + rets).cumprod()
        mdd = max_drawdown(eq)
        cagr = (eq[-1]) ** (1 / years) - 1
        flag = " (deploy)" if cp == COST_POINTS_DEFAULT else (" (stress)" if cp == KC_COST_STRESS_PT else "")
        print(f"    cost={cp:.2f}pt  Sh {sh:>+6.2f}  CAGR {cagr * 100:>+6.2f}%  "
              f"MDD {mdd * 100:>+7.2f}%  n={len(rets)}{flag}")


def kill_criteria_check(label: str, stats: dict, regime: dict, fade_gap: float,
                        cost_stress_sh: float, deflated_sh: float) -> bool:
    sh = stats.get("sharpe", 0.0)
    mdd = stats.get("mdd", -1.0)
    n = stats.get("n", 0)
    wr = stats.get("wr", 0.0)
    pf = stats.get("pf", 0.0)
    ho = regime.get("W3 2023-2026 (holdout)", {})
    ho_sh = ho.get("sharpe", 0.0)

    print(f"  [{label}]")
    wr_pf_joint_fail = (wr < KC_WR) and (pf < KC_PF)
    checks = [
        (f"FULL Sharpe > {KC_SHARPE_FULL:.2f}", sh > KC_SHARPE_FULL, f"{sh:+.2f}"),
        (f"MDD         < {KC_MDD * 100:.0f}%", abs(mdd) < KC_MDD, f"{mdd * 100:+.2f}%"),
        (f"Trades     >= {KC_TRADES}", n >= KC_TRADES, f"{n}"),
        (f"WR>{KC_WR*100:.0f}% OR PF>{KC_PF:.2f}", not wr_pf_joint_fail,
         f"WR {wr * 100:.1f}% PF {pf:.2f}"),
        (f"Fade-gap   > {KC_FADE_GAP:.2f}", fade_gap > KC_FADE_GAP, f"{fade_gap:+.2f}"),
        (f"Holdout Sh > {KC_SHARPE_HOLDOUT:.2f}", ho_sh > KC_SHARPE_HOLDOUT, f"{ho_sh:+.2f}"),
        (f"Cost-stress Sh@{KC_COST_STRESS_PT}pt > 0", cost_stress_sh > 0, f"{cost_stress_sh:+.2f}"),
        (f"Deflated Sh > {KC_DEFLATED_SH:.2f}", deflated_sh > KC_DEFLATED_SH, f"{deflated_sh:+.2f}"),
    ]
    all_pass = True
    for desc, ok, val in checks:
        print(f"    {desc:<32s} : {'PASS' if ok else 'FAIL'}  ({val})")
        if not ok:
            all_pass = False
    print(f"    -> {'PASS' if all_pass else 'FAIL'} on Phase 2 kill criteria")
    return all_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_variant(df, label, *, fade=False, cs_pt=KC_COST_STRESS_PT, **kw):
    """Run baseline + null + cost-stress + regime + cost-sweep for ONE variant."""
    section(f"Variant: {label}")
    rets, trades = simulate_break_retest(df, cost_points=COST_POINTS_DEFAULT, fade=False, **kw)
    stats = report_run(label, rets, trades)
    section(f"Regime breakdown — {label}")
    rb = regime_breakdown(rets, trades)
    section(f"Cost sweep — {label}")
    cost_sweep(df, label, **kw)

    section(f"Null check — {label} FADE")
    rets_f, trades_f = simulate_break_retest(df, cost_points=COST_POINTS_DEFAULT, fade=True, **kw)
    stats_f = report_run(label + " FADE", rets_f, trades_f)
    fade_gap = stats["sharpe"] - stats_f["sharpe"]
    print(f"\n  fade-gap (baseline - FADE): {fade_gap:+.2f}  (bar: > {KC_FADE_GAP:.2f})")

    section(f"Cost-stress @ {cs_pt}pt — {label}")
    rets_cs, trades_cs = simulate_break_retest(df, cost_points=cs_pt, fade=False, **kw)
    stats_cs = report_run(label + f" @{cs_pt}pt", rets_cs, trades_cs)

    # Deflated Sharpe (n_trials = pre-committed variant count)
    d_sh = deflated_sharpe(stats["sharpe"], rets, n_trials=N_VARIANTS_PRECOMMITTED)
    print(f"\n  Deflated Sharpe (n_trials={N_VARIANTS_PRECOMMITTED}): {d_sh:+.2f}  (bar: > {KC_DEFLATED_SH:.2f})")

    section(f"Phase 2 kill criteria — {label}")
    passed = kill_criteria_check(label, stats, rb, fade_gap, stats_cs["sharpe"], d_sh)

    return {
        "label": label,
        "stats": stats,
        "regime": rb,
        "fade_gap": fade_gap,
        "cost_stress_sh": stats_cs["sharpe"],
        "deflated_sh": d_sh,
        "passed": passed,
    }


def main() -> int:
    section("Loading XAUUSD M5 (2018-2026, UTC)")
    df = load_m5()
    print(f"  bars   : {len(df):,}")
    print(f"  range  : {df['timestamp'].min()} -> {df['timestamp'].max()}")
    in_session = df[(df["hour"] >= SESSION_START_UTC) & (df["hour"] < SESSION_END_UTC)]
    print(f"  in-session (13-16 UTC): {len(in_session):,} bars across "
          f"{in_session['date'].nunique()} days")

    results = []

    # 1. Baseline
    results.append(run_variant(df, "baseline"))

    # 2. Long-only
    results.append(run_variant(df, "long-only", direction_filter="long"))

    # 3. Short-only
    results.append(run_variant(df, "short-only", direction_filter="short"))

    # 4. Tight retest tol
    results.append(run_variant(df, "tight-retest (tol=0.15)", retest_tol_atr=0.15))

    # 5. Wide retest tol
    results.append(run_variant(df, "wide-retest (tol=0.50)", retest_tol_atr=0.50))

    # 6. Strict swing (longer lookback)
    results.append(run_variant(df, "strict-swing (lookback=40)", swing_lookback=40))

    # ----- Summary -----
    section("Phase 2 summary — all variants")
    print(f"  {'variant':<28s} {'Sh':>7s} {'Sh HO':>7s} {'MDD':>8s} {'n':>5s} "
          f"{'WR%':>5s} {'PF':>5s} {'f-gap':>7s} {'Sh@CS':>7s} {'dSh':>7s} verdict")
    print("  " + "-" * 110)
    for r in results:
        s = r["stats"]
        ho = r["regime"].get("W3 2023-2026 (holdout)", {})
        print(f"  {r['label']:<28s} {s.get('sharpe', 0):>+6.2f} "
              f"{ho.get('sharpe', 0):>+6.2f} "
              f"{s.get('mdd', 0) * 100:>+7.2f}% "
              f"{s.get('n', 0):>5d} "
              f"{s.get('wr', 0) * 100:>4.1f}% "
              f"{s.get('pf', 0):>4.2f} "
              f"{r['fade_gap']:>+6.2f} "
              f"{r['cost_stress_sh']:>+6.2f} "
              f"{r['deflated_sh']:>+6.2f} "
              f"{'PASS' if r['passed'] else 'FAIL'}")

    # Deploy candidate
    print("\n  Deploy candidate:")
    passers = [r for r in results if r["passed"]]
    if passers:
        best = max(passers, key=lambda r: r["stats"].get("sharpe", 0))
        print(f"    {best['label']} (Sharpe {best['stats']['sharpe']:+.2f}, "
              f"HO {best['regime'].get('W3 2023-2026 (holdout)', {}).get('sharpe', 0):+.2f})")
    else:
        print("    NONE pass all kill criteria. Report verdict accordingly.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
