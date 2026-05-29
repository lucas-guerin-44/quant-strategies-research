#!/usr/bin/env python3
"""
BTC weekend / DOW effect -- Phase 2 demo.

Thesis: experiments/btc_weekend/btc_weekend.md

Signal: weekend_drift = (Mon_open - prior_Fri_close) / prior_Fri_close.
Trade: enter at Mon open, exit at close of bar (Mon + HOLD_DAYS - 1).
Run continuation and fade variants alongside as a fade-gap test
(per gap_continuation lesson #1 + CLAUDE.md rule 6).

Phases run in one A-to-Z pass:
  Phase 2 - baseline at honest 10 bps/side; kill criteria check
  Phase 4 - regime breakdown across 4 windows
  Phase 5 - parameter sensitivity (drift threshold, hold period, cost)
  Phase 6 - walk-forward (5 rolling 3y-IS/2y-OOS splits, per lesson #29)
  Holdout-decay diagnostic (W1 vs W4 Sharpe)
"""

from __future__ import annotations

import os
import sys
from typing import Callable

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))

from data import fetch_ohlc


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SYMBOL = "BTCUSD"
TIMEFRAME = "D1"
START_DATE = "2018-01-01"
END_DATE = "2026-04-18"

# Baseline parameters (locked before running)
BASE_MIN_DRIFT_PCT = 1.0      # |weekend_drift| filter
BASE_HOLD_DAYS = 1            # exit at close of (Mon + HOLD-1)
BASE_COST_BPS = 10.0          # honest BTC CFD spread
BARS_PER_YEAR = 52            # weekly cadence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f"\n{'=' * 84}\n  {t}\n{'=' * 84}\n")


def load_btc(start: str = START_DATE, end: str = END_DATE) -> pd.DataFrame:
    raw = fetch_ohlc(SYMBOL, TIMEFRAME, start, end)
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df["dow"] = df.index.day_name()
    return df


def annualized_sharpe(r: np.ndarray, bars_per_year: float = BARS_PER_YEAR) -> float:
    r = r[np.isfinite(r)]
    if r.size == 0:
        return 0.0
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(bars_per_year))


def max_drawdown(e: np.ndarray) -> float:
    rm = np.maximum.accumulate(e)
    dd = (e - rm) / np.where(rm > 0, rm, 1.0)
    return float(dd.min()) if dd.size else 0.0


# ---------------------------------------------------------------------------
# Core: build (Fri_close, Mon_open, hold_close) triplets
# ---------------------------------------------------------------------------

def build_weekly_trades(df: pd.DataFrame, hold_days: int) -> pd.DataFrame:
    """For each Monday in df, find:
      prev_fri_close: close of the most recent Friday strictly before this Monday
      mon_open      : open of the Monday bar
      exit_close    : close of the bar at integer-index (mon_idx + hold_days - 1)
    Returns one row per usable Monday.
    """
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    dow = df["dow"].to_numpy()
    open_arr = df["open"].to_numpy(dtype=np.float64)
    close_arr = df["close"].to_numpy(dtype=np.float64)
    n = len(df)

    rows = []
    for i in range(n):
        if dow[i] != "Monday":
            continue
        # Find prior Friday close (scan back up to 7 bars)
        prev_fri_close = np.nan
        for j in range(i - 1, max(i - 8, -1), -1):
            if dow[j] == "Friday":
                prev_fri_close = close_arr[j]
                break
        if not np.isfinite(prev_fri_close):
            continue
        exit_i = i + hold_days - 1
        if exit_i >= n:
            continue
        mon_open = open_arr[i]
        exit_close = close_arr[exit_i]
        if not (np.isfinite(mon_open) and np.isfinite(exit_close)):
            continue
        rows.append({
            "monday_ts": df.index[i],
            "prev_fri_close": prev_fri_close,
            "mon_open": mon_open,
            "exit_close": exit_close,
            "weekend_drift_pct": (mon_open / prev_fri_close - 1.0) * 100.0,
            "intra_pct": (exit_close / mon_open - 1.0) * 100.0,
        })
    return pd.DataFrame(rows)


def simulate_direction(
    trades: pd.DataFrame,
    direction: str,
    min_drift_pct: float,
    cost_bps_per_side: float,
) -> tuple[pd.Series, dict]:
    """Run continuation ('cont') or fade direction on the trade table.
    Returns (per-trade-net-return Series indexed by monday_ts, stats dict).
    """
    if trades.empty:
        return pd.Series(dtype=np.float64), {"trades": 0}

    drift = trades["weekend_drift_pct"].to_numpy()
    intra = trades["intra_pct"].to_numpy()
    fired = np.abs(drift) >= min_drift_pct
    if direction == "cont":
        side = np.sign(drift)
    elif direction == "fade":
        side = -np.sign(drift)
    else:
        raise ValueError(direction)

    # Per-trade gross return = side * intra_pct / 100
    gross = np.where(fired, side * intra / 100.0, 0.0)
    # Round-trip cost: enter + exit = 2 * cost_bps_per_side * 1e-4
    rt_cost = 2.0 * cost_bps_per_side * 1e-4
    net = np.where(fired, gross - rt_cost, 0.0)
    n_trades = int(fired.sum())

    s = pd.Series(net, index=trades["monday_ts"].to_numpy(), name=direction)
    stats = {
        "trades": n_trades,
        "fired_frac": float(fired.mean()),
        "wr": float(np.mean(net[fired] > 0)) if n_trades else 0.0,
    }
    return s, stats


def report_block(label: str, r: pd.Series) -> dict:
    """Compute return / Sharpe / MDD on weekly trade returns. Skip zero-bar weeks."""
    r_clean = r[r != 0.0]
    if len(r_clean) < 2:
        return {"trades": 0, "sharpe": 0.0, "mdd": 0.0, "total": 0.0,
                "cagr": 0.0, "wr": 0.0}
    eq = (1.0 + r_clean).cumprod().to_numpy()
    sh = annualized_sharpe(r_clean.to_numpy())
    mdd = max_drawdown(eq)
    total = float(eq[-1] - 1.0)
    # bars-per-year for CAGR is fired-trades-per-year
    years = max(1e-9, (r.index[-1] - r.index[0]).days / 365.25)
    cagr = (1.0 + total) ** (1.0 / years) - 1.0
    wr = float((r_clean > 0).mean())
    print(f"  {label:<32s} trades {len(r_clean):>4d}  ret {total * 100:>+8.2f}%  "
          f"CAGR {cagr * 100:>+6.2f}%  Sh {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  "
          f"WR {wr * 100:>5.1f}%")
    return {"trades": len(r_clean), "sharpe": sh, "mdd": mdd, "total": total,
            "cagr": cagr, "wr": wr}


def kill_check(label: str, stats: dict, fade_gap: float, cost_zero_sh: float) -> bool:
    """Phase 2 kill-criteria check."""
    sh = stats['sharpe']
    mdd = stats['mdd']
    n = stats['trades']

    def v(c: bool) -> str: return "PASS" if c else "FAIL"

    p2_sh = sh > 0.30
    p2_mdd = abs(mdd) < 0.20
    p2_tr = n >= 200
    p2_gap = fade_gap > 0.50
    p2_costzero = cost_zero_sh > 0.30

    print(f"\n  Phase 2 kill criteria ({label}):")
    print(f"    Sharpe > +0.30 (10 bps)   : {v(p2_sh)}  ({sh:+.2f})")
    print(f"    MDD < 20%                 : {v(p2_mdd)}  ({mdd * 100:+.2f}%)")
    print(f"    Trades >= 200             : {v(p2_tr)}  ({n})")
    print(f"    Fade-gap > +0.50          : {v(p2_gap)}  ({fade_gap:+.2f})")
    print(f"    Cost-zero Sharpe > +0.30  : {v(p2_costzero)}  ({cost_zero_sh:+.2f})")
    overall = p2_sh and p2_mdd and p2_tr and p2_gap and p2_costzero
    print(f"    OVERALL                   : {v(overall)}")
    return overall


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section(f"Loading {SYMBOL}")
    df = load_btc()
    print(f"  {SYMBOL:<8s} {len(df):>5,} bars  "
          f"{df.index[0].date()} -> {df.index[-1].date()}")

    section("Phase 2 -- baseline (10 bps/side, drift>=1%, hold=1d)")
    trades = build_weekly_trades(df, BASE_HOLD_DAYS)
    print(f"  Mondays available: {len(trades)}")
    print(f"  Mean |weekend_drift|: {trades['weekend_drift_pct'].abs().mean():.2f}%")
    print(f"  Median |weekend_drift|: {trades['weekend_drift_pct'].abs().median():.2f}%")
    print(f"  Mondays with |drift| >= 1%: "
          f"{(trades['weekend_drift_pct'].abs() >= 1.0).sum()}")
    print()

    cont_ret, cont_stats = simulate_direction(
        trades, "cont", BASE_MIN_DRIFT_PCT, BASE_COST_BPS,
    )
    fade_ret, fade_stats = simulate_direction(
        trades, "fade", BASE_MIN_DRIFT_PCT, BASE_COST_BPS,
    )
    cont_m = report_block("continuation (long if drift>0)", cont_ret)
    fade_m = report_block("fade (long if drift<0)         ", fade_ret)

    # Cost-zero diagnostic
    cont_ret_cz, _ = simulate_direction(trades, "cont", BASE_MIN_DRIFT_PCT, 0.0)
    fade_ret_cz, _ = simulate_direction(trades, "fade", BASE_MIN_DRIFT_PCT, 0.0)
    cz_cont = annualized_sharpe(cont_ret_cz[cont_ret_cz != 0].to_numpy())
    cz_fade = annualized_sharpe(fade_ret_cz[fade_ret_cz != 0].to_numpy())
    print(f"\n  Cost-zero Sharpe (diagnostic):")
    print(f"    continuation @ 0 bps : {cz_cont:+.3f}")
    print(f"    fade        @ 0 bps : {cz_fade:+.3f}")

    best_dir = "cont" if cont_m['sharpe'] >= fade_m['sharpe'] else "fade"
    best_m = cont_m if best_dir == "cont" else fade_m
    best_cz = cz_cont if best_dir == "cont" else cz_fade
    fade_gap = abs(cont_m['sharpe'] - fade_m['sharpe'])

    print(f"\n  Best direction        : {best_dir}")
    print(f"  Fade gap (|cont-fade|): {fade_gap:+.3f}")
    kill_check(best_dir, best_m, fade_gap, best_cz)

    # ----- Phase 4 -- regime breakdown ----------------------------------
    section("Phase 4 -- regime breakdown (4 non-overlapping windows)")
    WINDOWS = [
        ("W1 2018-2019 (early retail crypto)   ", "2018-01-01", "2019-12-31"),
        ("W2 2020-2021 (parabola + COVID)     ", "2020-01-01", "2021-12-31"),
        ("W3 2022-2023 (FTX collapse + bear)  ", "2022-01-01", "2023-12-31"),
        ("W4 2024-2026 (ETF era / institut.)  ", "2024-01-01", "2026-03-31"),
    ]
    window_rows = {"cont": [], "fade": []}
    for direction in ("cont", "fade"):
        print(f"\n  -- direction = {direction} --")
        for wname, ws, we in WINDOWS:
            sub_df = df.loc[ws:we]
            sub_tr = build_weekly_trades(sub_df, BASE_HOLD_DAYS)
            r, st = simulate_direction(sub_tr, direction, BASE_MIN_DRIFT_PCT,
                                       BASE_COST_BPS)
            m = report_block(wname, r)
            window_rows[direction].append({"name": wname.strip(), **m})

    # Holdout-decay diagnostic (W1 vs W4) for the best direction
    bd = best_dir
    w1_sh = window_rows[bd][0]['sharpe']
    w4_sh = window_rows[bd][3]['sharpe']
    decay = w1_sh - w4_sh
    print(f"\n  Holdout-decay diagnostic ({bd}): W1 Sh {w1_sh:+.2f}, "
          f"W4 Sh {w4_sh:+.2f}, decay {decay:+.2f}")
    decay_pass = decay <= 0.5
    print(f"    Decay < +0.5             : {'PASS' if decay_pass else 'FAIL'}  "
          f"({decay:+.2f})")

    # ----- Phase 5 -- parameter sensitivity ----------------------------
    section("Phase 5 -- parameter sensitivity (best direction = " + bd + ")")

    # Sweep 1: drift threshold
    print("  [Sweep 1] |weekend_drift| threshold")
    print(f"  {'thr':>5s} {'trades':>7s} {'Sharpe':>8s} {'MDD':>8s} {'CAGR':>8s}")
    sw1 = []
    for thr in (0.0, 0.5, 1.0, 2.0, 3.0, 5.0):
        r, _ = simulate_direction(trades, bd, thr, BASE_COST_BPS)
        m = {"sharpe": 0.0, "mdd": 0.0, "cagr": 0.0, "trades": 0}
        nz = r[r != 0]
        if len(nz) >= 2:
            eq = (1.0 + nz).cumprod().to_numpy()
            m['sharpe'] = annualized_sharpe(nz.to_numpy())
            m['mdd'] = max_drawdown(eq)
            total = float(eq[-1] - 1.0)
            years = max(1e-9, (r.index[-1] - r.index[0]).days / 365.25)
            m['cagr'] = (1.0 + total) ** (1.0 / years) - 1.0
            m['trades'] = len(nz)
        mark = " <<" if abs(thr - BASE_MIN_DRIFT_PCT) < 1e-6 else ""
        print(f"  {thr:>5.1f}% {m['trades']:>7d} {m['sharpe']:>+7.3f} "
              f"{m['mdd'] * 100:>+7.2f}% {m['cagr'] * 100:>+7.2f}%{mark}")
        sw1.append(m['sharpe'])

    # Sweep 2: hold period
    print("\n  [Sweep 2] hold period")
    print(f"  {'hold':>5s} {'trades':>7s} {'Sharpe':>8s} {'MDD':>8s} {'CAGR':>8s}")
    sw2 = []
    for h in (1, 2, 3, 5):
        sub_tr = build_weekly_trades(df, h)
        r, _ = simulate_direction(sub_tr, bd, BASE_MIN_DRIFT_PCT, BASE_COST_BPS)
        m = {"sharpe": 0.0, "mdd": 0.0, "cagr": 0.0, "trades": 0}
        nz = r[r != 0]
        if len(nz) >= 2:
            eq = (1.0 + nz).cumprod().to_numpy()
            m['sharpe'] = annualized_sharpe(nz.to_numpy())
            m['mdd'] = max_drawdown(eq)
            total = float(eq[-1] - 1.0)
            years = max(1e-9, (r.index[-1] - r.index[0]).days / 365.25)
            m['cagr'] = (1.0 + total) ** (1.0 / years) - 1.0
            m['trades'] = len(nz)
        mark = " <<" if h == BASE_HOLD_DAYS else ""
        print(f"  {h:>4d}d {m['trades']:>7d} {m['sharpe']:>+7.3f} "
              f"{m['mdd'] * 100:>+7.2f}% {m['cagr'] * 100:>+7.2f}%{mark}")
        sw2.append(m['sharpe'])

    # Sweep 3: cost
    print("\n  [Sweep 3] cost (bps/side)")
    print(f"  {'cost':>5s} {'trades':>7s} {'Sharpe':>8s} {'MDD':>8s}")
    sw3 = []
    for c in (0.0, 5.0, 10.0, 15.0, 20.0, 30.0):
        r, _ = simulate_direction(trades, bd, BASE_MIN_DRIFT_PCT, c)
        nz = r[r != 0]
        if len(nz) >= 2:
            sh = annualized_sharpe(nz.to_numpy())
            mdd = max_drawdown((1.0 + nz).cumprod().to_numpy())
            n = len(nz)
        else:
            sh = mdd = 0.0
            n = 0
        mark = " <<" if abs(c - BASE_COST_BPS) < 1e-6 else ""
        print(f"  {c:>5.1f}  {n:>7d} {sh:>+7.3f} {mdd * 100:>+7.2f}%{mark}")
        sw3.append(sh)

    # ----- Phase 6 -- walk-forward (5 rolling 3y-IS/2y-OOS splits) -----
    section("Phase 6 -- walk-forward (5 rolling splits, best direction)")
    splits = [
        ("S1", "2018-01-01", "2020-12-31", "2021-01-01", "2022-12-31"),
        ("S2", "2019-01-01", "2021-12-31", "2022-01-01", "2023-12-31"),
        ("S3", "2020-01-01", "2022-12-31", "2023-01-01", "2024-12-31"),
        ("S4", "2021-01-01", "2023-12-31", "2024-01-01", "2025-12-31"),
        ("S5", "2022-01-01", "2024-12-31", "2025-01-01", "2026-03-31"),
    ]
    print(f"  {'split':<6s} {'IS window':<24s} {'OOS window':<24s} "
          f"{'IS Sh':>7s} {'OOS Sh':>7s} {'degrad':>7s}")
    print("  " + "-" * 88)
    wf_rows = []
    for label, is_s, is_e, oos_s, oos_e in splits:
        is_tr = build_weekly_trades(df.loc[is_s:is_e], BASE_HOLD_DAYS)
        oos_tr = build_weekly_trades(df.loc[oos_s:oos_e], BASE_HOLD_DAYS)
        is_r, _ = simulate_direction(is_tr, bd, BASE_MIN_DRIFT_PCT, BASE_COST_BPS)
        oos_r, _ = simulate_direction(oos_tr, bd, BASE_MIN_DRIFT_PCT, BASE_COST_BPS)
        is_nz = is_r[is_r != 0]
        oos_nz = oos_r[oos_r != 0]
        is_sh = annualized_sharpe(is_nz.to_numpy()) if len(is_nz) >= 2 else 0.0
        oos_sh = annualized_sharpe(oos_nz.to_numpy()) if len(oos_nz) >= 2 else 0.0
        degrad = is_sh - oos_sh
        wf_rows.append({"split": label, "is_sh": is_sh, "oos_sh": oos_sh,
                        "degrad": degrad})
        print(f"  {label:<6s} {is_s + '..' + is_e:<24s} {oos_s + '..' + oos_e:<24s} "
              f"{is_sh:>+7.2f} {oos_sh:>+7.2f} {degrad:>+7.3f}")

    degrads = [r['degrad'] for r in wf_rows]
    oos_shs = [r['oos_sh'] for r in wf_rows]
    mean_deg = float(np.mean(degrads))
    median_deg = float(np.median(degrads))
    splits_deg_pass = sum(1 for d in degrads if d < 0.5)
    splits_oos_pos = sum(1 for s in oos_shs if s > 0)
    n = len(wf_rows)
    print(f"\n  Mean degradation     : {mean_deg:+.3f}  "
          f"({'PASS' if mean_deg < 0.5 else 'FAIL'} -- need < 0.5)")
    print(f"  Median degradation   : {median_deg:+.3f}")
    print(f"  Splits w/ deg < 0.5  : {splits_deg_pass}/{n}  "
          f"({'PASS' if splits_deg_pass >= 3 else 'FAIL'} -- need >= 3)")
    print(f"  Splits w/ OOS Sh > 0 : {splits_oos_pos}/{n}  "
          f"({'PASS' if splits_oos_pos >= 3 else 'FAIL'} -- need >= 3)")

    wf_pass = (mean_deg < 0.5 and splits_deg_pass >= 3 and splits_oos_pos >= 3)
    print(f"\n  WALK-FORWARD OVERALL: {'PASS' if wf_pass else 'FAIL'}")

    # ----- Summary verdict ---------------------------------------------
    section("VERDICT SUMMARY")
    print(f"  Best direction              : {bd}")
    print(f"  Best Sharpe (10 bps)        : {best_m['sharpe']:+.2f}")
    print(f"  Fade gap                    : {fade_gap:+.2f}")
    print(f"  Cost-zero Sharpe (best dir) : {best_cz:+.2f}")
    print(f"  Holdout decay (W1-W4)       : {decay:+.2f}")
    print(f"  Walk-forward mean deg       : {mean_deg:+.3f}")
    print(f"  Walk-forward OOS positive   : {splits_oos_pos}/{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
