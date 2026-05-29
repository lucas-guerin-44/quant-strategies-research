#!/usr/bin/env python3
"""
EU Close-Auction Overshoot Fade — paired FRA40 (Euronext) + GER40 (Xetra) test.

Thesis: experiments/eu_close_auction_fade/eu_close_auction_fade.md

Mechanism:
  Both Euronext and Xetra close at 17:30 local via single-price call auction.
  When the auction print materially differs from the pre-auction continuous
  CFD price, the gap reflects a one-sided liquidity-demand shock at the print
  that should partially revert in the first 15-30 min of post-close CFD.

Rules (per instrument):
  pre_avg   = mean(close) over bars [17:00, 17:30) local
  print_px  = close of bar timestamped 17:30 local (auction settled)
  gap       = (print_px - pre_avg) / pre_avg
  atr_proxy = rolling 20-day mean of |gap|
  if |gap| >= ATR_THRESHOLD * atr_proxy:
    position = -sign(gap)  # FADE (primary); MOMENTUM is null check
    entry    = open of bar at 17:35 local
    exit     = close of bar at (17:35 + HOLD_BARS*5min) local
    cost applied as COST_PT / entry_px

Bug-audit (lesson #77):
  entry_bar_index = print_bar_index + 1  ⇒ no same-bar look-ahead.
  ATR uses ONLY past values.
  Tripwire: |Sh| > 0.80 ⇒ audit before verdict.

Cost model:
  FRA40: 1.5pt RT (level ~8400 = ~1.8bp)
  GER40: 1.0pt RT (level ~18000 = ~0.6bp)
"""

from __future__ import annotations

import os
import sys

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

INSTRUMENTS = [
    {"symbol": "FRA40", "tz": "Europe/Paris",  "cost_pt": 1.5},
    {"symbol": "GER40", "tz": "Europe/Berlin", "cost_pt": 1.0},
]

TIMEFRAME = "M5"
START_DATE = "2019-01-01"
END_DATE = "2026-04-18"

# Pre-auction window: bars from 17:00 (inclusive) to 17:30 (exclusive) local.
PRE_WINDOW_START_HOUR = 17
PRE_WINDOW_START_MIN = 0
PRINT_BAR_HOUR = 17
PRINT_BAR_MIN = 30      # bar timestamped 17:30 captures the call-auction print
ENTRY_BAR_HOUR = 17
ENTRY_BAR_MIN = 35      # first purely post-print bar

HOLD_BARS = 4           # 20 min hold by default
ATR_THRESHOLD = 0.20
MODE = "fade"           # 'fade' (primary) or 'momentum' (null)

ATR_LOOKBACK_DAYS = 20
# Bars/day for Sharpe annualization: use the standard EU-cash-session length
# (the bars we actually trade live on each day are a small subset, but the
# annualizer is over the available session; matches the orb_demo convention
# of using session-length-derived BARS_PER_DAY).
EU_SESSION_HOURS = 9      # 09:00-17:30 local ≈ 8.5h, round up to 9
BARS_PER_DAY = (EU_SESSION_HOURS * 60) // 5  # 108
DAYS_PER_YEAR = 252
BARS_PER_YEAR = BARS_PER_DAY * DAYS_PER_YEAR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f"\n{'=' * 80}\n  {t}\n{'=' * 80}\n")


def load_m5(symbol: str, tz: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f"No bars for {symbol} {TIMEFRAME}")
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    # Drop weekends (UTC dayofweek — weekends never differ across CET/CEST).
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

def simulate_auction_fade(
    bars: pd.DataFrame,
    tz: str,
    hold_bars: int = HOLD_BARS,
    atr_threshold: float = ATR_THRESHOLD,
    cost_points: float = 1.5,
    mode: str = "fade",
    direction: str = "both",
    atr_lookback_days: int = ATR_LOOKBACK_DAYS,
) -> tuple[pd.Series, list[dict]]:
    """Post-close-auction overshoot fade/momentum simulator (numpy inner loop).

    Per day in local time:
      - find bars in [17:00, 17:30) local → pre_avg
      - bar at 17:30 local → print_px (auction settled close)
      - bar at 17:35 local → entry
      - bar at 17:35 + hold_bars*5min local → exit
      - gap = (print_px - pre_avg) / pre_avg
      - if |gap| >= ATR_THRESHOLD * atr_proxy:
          fade → position = -sign(gap)
          momentum (null) → position = +sign(gap)
    """
    n_bars = len(bars)
    if n_bars == 0:
        return pd.Series(dtype=float, name="ret"), []

    open_arr = bars["open"].to_numpy(dtype=np.float64)
    close_arr = bars["close"].to_numpy(dtype=np.float64)
    idx_utc = bars.index
    idx_local = idx_utc.tz_convert(tz)

    local_hours = np.asarray(idx_local.hour, dtype=np.int32)
    local_minutes = np.asarray(idx_local.minute, dtype=np.int32)
    local_dates = np.asarray(idx_local.date)
    local_mod = local_hours * 60 + local_minutes  # minute-of-day local

    # Day boundaries by local-date (handles DST cleanly — local date is what
    # matters for "is this the same trading session").
    change = np.empty(n_bars, dtype=bool)
    change[0] = True
    change[1:] = local_dates[1:] != local_dates[:-1]
    day_starts = np.flatnonzero(change)
    day_ends = np.empty_like(day_starts)
    day_ends[:-1] = day_starts[1:]
    day_ends[-1] = n_bars

    PRE_START_MIN = PRE_WINDOW_START_HOUR * 60 + PRE_WINDOW_START_MIN  # 17*60
    PRINT_MIN = PRINT_BAR_HOUR * 60 + PRINT_BAR_MIN                    # 17*60+30
    ENTRY_MIN = ENTRY_BAR_HOUR * 60 + ENTRY_BAR_MIN                    # 17*60+35

    ret_arr = np.zeros(n_bars, dtype=np.float64)
    trades: list[dict] = []

    long_ok = direction in ("both", "long")
    short_ok = direction in ("both", "short")
    is_fade = (mode == "fade")

    gap_buffer: list[float] = []  # rolling daily |gap| for ATR proxy

    for d_i in range(len(day_starts)):
        s = int(day_starts[d_i])
        e = int(day_ends[d_i])
        day_mod = local_mod[s:e]
        day_close = close_arr[s:e]
        day_open = open_arr[s:e]
        dn = e - s

        # Find pre-window bars (local 17:00 ≤ mod < 17:30).
        pre_mask = (day_mod >= PRE_START_MIN) & (day_mod < PRINT_MIN)
        if pre_mask.sum() < 3:  # need at least 3 pre-bars for stable mean
            continue
        pre_avg = float(np.mean(day_close[pre_mask]))

        # Find print bar (local == 17:30).
        print_arr = np.flatnonzero(day_mod == PRINT_MIN)
        if print_arr.size == 0:
            continue
        print_i = int(print_arr[0])

        # Find entry bar (local == 17:35).
        entry_arr = np.flatnonzero(day_mod == ENTRY_MIN)
        if entry_arr.size == 0:
            continue
        entry_i = int(entry_arr[0])

        # Sanity: entry must be strictly after print.
        if entry_i <= print_i:
            continue

        # Exit: entry + hold_bars (cap at last bar of day).
        exit_i = entry_i + hold_bars
        if exit_i >= dn:
            continue  # not enough post-entry bars in the day

        # Signal.
        print_px = float(day_close[print_i])
        if print_px <= 0 or pre_avg <= 0:
            continue
        gap = (print_px - pre_avg) / pre_avg

        # Rolling ATR proxy — past-only.
        atr_proxy = float(np.mean(gap_buffer)) if gap_buffer else 0.0
        gap_buffer.append(abs(gap))
        if len(gap_buffer) > atr_lookback_days:
            gap_buffer.pop(0)
        threshold = atr_threshold * atr_proxy

        if abs(gap) < threshold:
            continue

        # Direction.
        if is_fade:
            pos = -1 if gap > 0 else 1  # FADE
        else:
            pos = 1 if gap > 0 else -1  # MOMENTUM

        if pos == 1 and not long_ok:
            continue
        if pos == -1 and not short_ok:
            continue

        entry_px = float(day_open[entry_i])
        if entry_px <= 0:
            continue
        cost_ret = cost_points / entry_px

        # Bar-by-bar MTM returns.
        prev = entry_px
        exit_px = float(day_close[exit_i])
        for j in range(entry_i, exit_i + 1):
            if j == exit_i:
                bar_ret = pos * (exit_px - prev) / prev - cost_ret
            else:
                bar_ret = pos * (day_close[j] - prev) / prev
            ret_arr[s + j] += bar_ret
            prev = day_close[j]

        gross_ret = pos * (exit_px - entry_px) / entry_px - cost_ret
        trades.append({
            "date": local_dates[s],
            "direction": "LONG" if pos == 1 else "SHORT",
            "gap": gap,
            "atr_proxy": atr_proxy,
            "threshold": threshold,
            "entry_px": entry_px,
            "exit_px": exit_px,
            "pnl_pct": gross_ret,
        })

    bar_ret = pd.Series(ret_arr, index=idx_utc, name="ret")
    return bar_ret, trades


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_run(label: str, bar_ret: pd.Series, trades: list[dict]) -> dict:
    if len(bar_ret) == 0 or np.all(bar_ret.to_numpy() == 0):
        print(f"  [{label}]  no trades")
        return {"sharpe": 0.0, "n_trades": 0}
    r_arr = bar_ret.to_numpy()
    eq = (1.0 + bar_ret).cumprod()
    years = max((bar_ret.index[-1] - bar_ret.index[0]).days / 365.25, 1e-9)
    total = float(eq.iloc[-1] - 1.0)
    cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
    sh = annualized_sharpe(r_arr)
    mdd = max_drawdown(eq.to_numpy())
    n_trades = len(trades)
    trades_per_year = n_trades / years if years > 0 else 0.0
    wins = [t for t in trades if t["pnl_pct"] > 0]
    win_rate = len(wins) / n_trades if n_trades else 0.0
    gw = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gl = -sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0)
    pf = gw / gl if gl > 0 else float("inf")

    print(f"  [{label}]")
    print(f"    period   : {bar_ret.index[0].date()} -> {bar_ret.index[-1].date()} ({years:.1f}y)")
    print(f"    total    : {total * 100:+.2f}%")
    print(f"    CAGR     : {cagr * 100:+.2f}%")
    print(f"    Sharpe   : {sh:+.2f}")
    print(f"    MDD      : {mdd * 100:+.2f}%")
    print(f"    trades   : {n_trades}  ({trades_per_year:.1f}/yr)")
    print(f"    WR       : {win_rate * 100:.1f}%")
    print(f"    PF       : {pf:.2f}")
    return {
        "sharpe": sh, "mdd": mdd, "n_trades": n_trades,
        "win_rate": win_rate, "pf": pf,
    }


def kill_criteria_check(label: str, bar_ret: pd.Series, trades: list[dict],
                        sh_floor: float = 0.30, mdd_floor: float = 0.25,
                        trade_floor: int = 200, wr_floor: float = 0.40,
                        pf_floor: float = 1.1) -> None:
    r_arr = bar_ret.to_numpy()
    if np.all(r_arr == 0):
        print(f"  [{label}]  no trades — all FAIL")
        return
    sh = annualized_sharpe(r_arr)
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
    print(f"    Sharpe > {sh_floor:.2f}       : {v(sh > sh_floor)}  ({sh:+.2f})")
    print(f"    MDD < {mdd_floor * 100:.0f}%        : {v(abs(mdd) < mdd_floor)}  ({mdd * 100:+.2f}%)")
    print(f"    Trades >= {trade_floor}      : {v(n_trades >= trade_floor)}  ({n_trades})")
    print(f"    WR >= {wr_floor * 100:.0f}% AND PF >= {pf_floor:.1f} : "
          f"{v(win_rate >= wr_floor and pf >= pf_floor)}  "
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
        if len(sub_trades) < 5:
            print(f"  {label:<22s}  (insufficient trades: {len(sub_trades)})")
            continue
        eq = (1.0 + sub_ret).cumprod()
        years = max((sub_ret.index[-1] - sub_ret.index[0]).days / 365.25, 1e-9)
        cagr = (float(eq.iloc[-1])) ** (1 / max(years, 1e-9)) - 1
        sh = annualized_sharpe(sub_ret.to_numpy())
        mdd = max_drawdown(eq.to_numpy())
        print(f"  {label:<22s}  CAGR {cagr * 100:>+7.2f}%  Sharpe {sh:>+6.2f}  "
              f"MDD {mdd * 100:>+7.2f}%  trades {len(sub_trades):>4d}")


# ---------------------------------------------------------------------------
# Main per-instrument runner
# ---------------------------------------------------------------------------

def run_instrument(inst: dict) -> dict:
    symbol = inst["symbol"]
    tz = inst["tz"]
    cost_pt = inst["cost_pt"]

    section(f"Loading {symbol} {TIMEFRAME} (tz={tz}, cost={cost_pt}pt RT)")
    bars = load_m5(symbol, tz)
    n_days = len(set(bars.index.date))
    print(f"  bars     : {len(bars):,}")
    print(f"  range    : {bars.index[0]} -> {bars.index[-1]}")
    print(f"  days     : {n_days}")

    # ----- Baseline (FADE) -----
    section(f"{symbol} Baseline (FADE, HOLD=20min, ATR=0.20, cost={cost_pt}pt)")
    bar_ret, trades = simulate_auction_fade(bars, tz, cost_points=cost_pt, mode="fade")
    report_run(f"{symbol}-baseline-fade", bar_ret, trades)

    section(f"{symbol} Phase 2 kill-criteria")
    kill_criteria_check(f"{symbol}-baseline-fade", bar_ret, trades)

    section(f"{symbol} Regime breakdown (baseline-fade)")
    regime_breakdown(bar_ret, trades)

    # Cost-zero check.
    bar_ret_zc, _ = simulate_auction_fade(bars, tz, cost_points=0.0, mode="fade")
    sh_zc = annualized_sharpe(bar_ret_zc.to_numpy())
    print(f"\n  Cost-zero Sharpe: {sh_zc:+.2f}  (must be > 0 for signal-present)")

    # ----- Null check: MOMENTUM (opposite direction) -----
    section(f"{symbol} Null check: MOMENTUM (opposite direction)")
    bar_ret_mom, trades_mom = simulate_auction_fade(bars, tz, cost_points=cost_pt, mode="momentum")
    report_run(f"{symbol}-null-momentum", bar_ret_mom, trades_mom)
    sh_fade = annualized_sharpe(bar_ret.to_numpy())
    sh_mom = annualized_sharpe(bar_ret_mom.to_numpy())
    dir_gap = sh_fade - sh_mom
    print(f"\n  dir-gap (FADE - MOMENTUM) Sharpe: {dir_gap:+.2f}")
    print(f"    (must be >= +0.30 for directional content)")

    # ----- LONG / SHORT split -----
    section(f"{symbol} Long/short asymmetry (fade)")
    for d in ("long", "short"):
        r_v, t_v = simulate_auction_fade(bars, tz, cost_points=cost_pt, direction=d)
        if len(t_v) == 0:
            print(f"  dir={d:<5s}  no trades")
            continue
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        wr = sum(1 for t in t_v if t["pnl_pct"] > 0) / max(len(t_v), 1)
        print(f"  dir={d:<5s}  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  "
              f"trades {len(t_v):>4d}  WR {wr*100:>4.1f}%")

    # ----- ATR threshold sweep -----
    section(f"{symbol} ATR threshold sweep (FADE, HOLD=20min, cost={cost_pt}pt)")
    for thr in (0.0, 0.10, 0.20, 0.50, 1.00):
        r_v, t_v = simulate_auction_fade(bars, tz, cost_points=cost_pt, atr_threshold=thr)
        if len(t_v) == 0:
            print(f"  thr={thr:>4.2f}  no trades")
            continue
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        print(f"  thr={thr:>4.2f}  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  "
              f"trades {len(t_v):>4d}")

    # ----- HOLD window sweep -----
    section(f"{symbol} Hold window sweep (FADE, ATR=0.20, cost={cost_pt}pt)")
    for hold in (2, 4, 8, 12):
        r_v, t_v = simulate_auction_fade(bars, tz, cost_points=cost_pt, hold_bars=hold)
        if len(t_v) == 0:
            print(f"  hold={hold*5:>3d}min  no trades")
            continue
        sh = annualized_sharpe(r_v.to_numpy())
        eq = (1.0 + r_v).cumprod()
        mdd = max_drawdown(eq.to_numpy())
        print(f"  hold={hold*5:>3d}min  Sharpe {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  "
              f"trades {len(t_v):>4d}")

    # ----- Cost sensitivity -----
    section(f"{symbol} Cost sensitivity (FADE, HOLD=20min, ATR=0.20)")
    for c in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0):
        r_v, t_v = simulate_auction_fade(bars, tz, cost_points=c)
        if len(t_v) == 0:
            print(f"  cost={c:>3.1f}pt  no trades")
            continue
        sh = annualized_sharpe(r_v.to_numpy())
        print(f"  cost={c:>3.1f}pt  Sharpe {sh:>+6.2f}  trades {len(t_v):>4d}")

    # ----- Walk-forward (3 rolling splits) -----
    section(f"{symbol} Walk-forward (FADE baseline, 3 rolling splits)")
    wf_splits = [
        ("S1: IS 2019-01 / OOS 2023-07", "2019-01-01", "2023-06-30", "2023-07-01", "2026-04-18"),
        ("S2: IS 2019-07 / OOS 2024-01", "2019-07-01", "2024-01-31", "2024-02-01", "2026-04-18"),
        ("S3: IS 2020-01 / OOS 2024-07", "2020-01-01", "2024-07-31", "2024-08-01", "2026-04-18"),
    ]
    oos_sharpes = []
    for label, is_s, is_e, oos_s, oos_e in wf_splits:
        is_bars = bars.loc[is_s:is_e]
        oos_bars = bars.loc[oos_s:oos_e]
        r_is, t_is = simulate_auction_fade(is_bars, tz, cost_points=cost_pt)
        r_oos, t_oos = simulate_auction_fade(oos_bars, tz, cost_points=cost_pt)
        sh_is = annualized_sharpe(r_is.to_numpy())
        sh_oos = annualized_sharpe(r_oos.to_numpy())
        oos_sharpes.append(sh_oos)
        print(f"  {label:<40s}  IS Sh {sh_is:>+6.2f}  OOS Sh {sh_oos:>+6.2f}  "
              f"trades IS={len(t_is):>4d} OOS={len(t_oos):>4d}")
    mean_oos = float(np.mean(oos_sharpes)) if oos_sharpes else 0.0
    min_oos = float(min(oos_sharpes)) if oos_sharpes else 0.0
    print(f"\n  WF OOS mean: {mean_oos:+.2f}  (need > +0.30)")
    print(f"  WF OOS min:  {min_oos:+.2f}  (need > 0)")

    return {
        "symbol": symbol,
        "sharpe": sh_fade,
        "sharpe_momentum": sh_mom,
        "dir_gap": dir_gap,
        "cost_zero_sharpe": sh_zc,
        "n_trades": len(trades),
        "wf_oos_mean": mean_oos,
        "wf_oos_min": min_oos,
        "trades": trades,
        "bar_ret": bar_ret,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    results = {}
    for inst in INSTRUMENTS:
        results[inst["symbol"]] = run_instrument(inst)

    # Cross-venue agreement.
    section("Cross-venue agreement (paired-experiment gate)")
    syms = list(results.keys())
    for sym in syms:
        r = results[sym]
        sgn = "POS" if r["sharpe"] > 0 else ("NEG" if r["sharpe"] < 0 else "ZERO")
        print(f"  {sym:>6s}  baseline Sh {r['sharpe']:>+6.2f} ({sgn})  "
              f"dir-gap {r['dir_gap']:>+5.2f}  cost-zero {r['cost_zero_sharpe']:>+5.2f}  "
              f"WF OOS mean {r['wf_oos_mean']:>+5.2f}")
    if len(syms) == 2:
        a, b = results[syms[0]], results[syms[1]]
        same_sign = (a["sharpe"] > 0) == (b["sharpe"] > 0)
        print(f"\n  Same-sign across venues: {'YES' if same_sign else 'NO'}")
        both_pass = a["sharpe"] > 0.30 and b["sharpe"] > 0.30
        print(f"  Both venues pass Sh > +0.30: {'YES' if both_pass else 'NO'}")
        print(f"  Verdict gate: "
              f"{'PASS-paired' if both_pass and same_sign else 'REJECT-or-VENUE-SPECIFIC'}")

    # Tripwire (lesson #77).
    section("Bug-audit tripwire (lesson #77)")
    for sym in syms:
        r = results[sym]
        tripped = abs(r["sharpe"]) > 0.80
        msg = "AUDIT-REQUIRED" if tripped else "ok"
        print(f"  {sym:>6s}  |Sh| = {abs(r['sharpe']):.2f}  vs prior-midpoint 0.30  -> {msg}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
