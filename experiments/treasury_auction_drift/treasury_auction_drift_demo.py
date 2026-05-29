#!/usr/bin/env python3
"""
US Treasury Auction → US-Index Post-Auction Drift.

Thesis: experiments/treasury_auction_drift/treasury_auction_drift.md

Mechanism:
  Treasury coupon auctions print at 13:00 ET (most) or 11:30 ET (20Y TIPS).
  The auction result re-prices the bond curve; equity-rate-duration channel
  transmits the signal to NDX/SPX over the following 30-90 min.

Phase 1 (calendar-only): test directional drift magnitude on auction days vs
  placebo (same time-of-day, non-auction Wed/Thu) per instrument & per tenor.
Phase 2 (outcome-conditioned, runs only if Phase 1 hits): condition direction
  on bid-to-cover z-score and/or stop-through proxy.

Bug-audit (lesson #77):
  Auction prints at T (13:00 or 11:30 ET); entry at bar T+5 ET ensures
  entry_bar_index strictly > print_bar_index. ATR-style filter uses past-only.
"""

from __future__ import annotations

import os
import sys
from datetime import time as dtime, timedelta

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
    {"symbol": "NDX100", "cost_pt": 0.5},   # NDX level ~22000 → 0.5pt ~0.23bp
    {"symbol": "SPX500", "cost_pt": 0.5},   # SPX level ~6000 → 0.5pt ~0.83bp
]
TIMEFRAME = "M5"
SESSION_TZ = "US/Eastern"
START_DATE = "2019-01-01"
END_DATE = "2026-04-30"

AUCTIONS_CSV = os.path.join(_HERE, "auctions.csv")

# RTH (for placebo selection and Sharpe annualization).
RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)
_rth_minutes = (RTH_CLOSE.hour*60+RTH_CLOSE.minute) - (RTH_OPEN.hour*60+RTH_OPEN.minute)
BARS_PER_DAY = _rth_minutes // 5   # 78
DAYS_PER_YEAR = 252
BARS_PER_YEAR = BARS_PER_DAY * DAYS_PER_YEAR

# Entry/exit window (in minutes-from-print).
ENTRY_OFFSET_MIN = 5    # entry at print_minute + 5 (next M5 bar after print)
DEFAULT_HOLD_BARS = 12  # 60 min hold


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    df = df.loc[df.index.dayofweek < 5]
    return df


def load_auctions() -> pd.DataFrame:
    df = pd.read_csv(AUCTIONS_CSV)
    df["auction_date"] = pd.to_datetime(df["auction_date"])
    df = df[df["security_type"].isin(["Note", "Bond"])].copy()
    # Parse closing_time_comp into a dtime; fall back to 13:00 ET (modal).
    def _parse_time(s):
        try:
            return pd.to_datetime(s, format="%I:%M %p").time()
        except Exception:
            return dtime(13, 0)
    df["close_time_et"] = df["closing_time_comp"].apply(_parse_time)
    df["bid_to_cover_ratio"] = pd.to_numeric(df["bid_to_cover_ratio"], errors="coerce")
    df["high_yield"] = pd.to_numeric(df["high_yield"], errors="coerce")
    # Tenor bucket (months).
    def _tenor_months(t):
        s = str(t)
        if "Year" in s:
            yrs = float(s.split("-Year")[0])
            if "Month" in s:
                # e.g. "9-Year 10-Month" → 9 + 10/12
                tail = s.split("Year")[1]
                months = float(tail.split("-Month")[0].strip())
                return yrs * 12 + months
            return yrs * 12
        return float("nan")
    df["tenor_months"] = df["security_term"].apply(_tenor_months)
    # Tenor bucket label.
    def _bucket(m):
        if m < 36: return "2y"
        if m < 60: return "3y"
        if m < 84: return "5y"
        if m < 108: return "7y"
        if m < 144: return "10y"
        if m < 240: return "20y"
        return "30y"
    df["tenor_bucket"] = df["tenor_months"].apply(_bucket)
    df = df.dropna(subset=["close_time_et"])
    df = df.sort_values("auction_date").reset_index(drop=True)
    return df


def annualized_sharpe(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if r.size == 0:
        return 0.0
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(BARS_PER_YEAR))


def max_drawdown(eq: np.ndarray) -> float:
    rm = np.maximum.accumulate(eq)
    dd = (eq - rm) / rm
    return float(dd.min()) if len(dd) else 0.0


# ---------------------------------------------------------------------------
# Core: per-event drift extraction
# ---------------------------------------------------------------------------

def extract_event_drifts(
    bars: pd.DataFrame,
    event_dates_times: list[tuple[pd.Timestamp, dtime]],
    hold_bars: int = DEFAULT_HOLD_BARS,
    entry_offset_min: int = ENTRY_OFFSET_MIN,
) -> pd.DataFrame:
    """For each (event_date, close_time_et), find the entry bar at
    close_time_et + entry_offset_min in US/Eastern, hold for hold_bars,
    return entry_px / exit_px / signed_pct_change.

    Returns DataFrame with columns: date, entry_ts, exit_ts, entry_px, exit_px,
    long_ret (signed LONG return = (exit-entry)/entry).
    """
    idx_utc = bars.index
    idx_et = idx_utc.tz_convert(SESSION_TZ)
    open_arr = bars["open"].to_numpy(np.float64)
    close_arr = bars["close"].to_numpy(np.float64)
    et_dates = np.asarray(idx_et.date)
    et_hours = np.asarray(idx_et.hour, dtype=np.int32)
    et_minutes = np.asarray(idx_et.minute, dtype=np.int32)
    et_mod = et_hours * 60 + et_minutes
    n = len(bars)

    rows = []
    for ev_date, ev_time in event_dates_times:
        d = ev_date.date()
        day_mask = (et_dates == d)
        if not day_mask.any():
            continue
        day_pos = np.flatnonzero(day_mask)
        s, e = int(day_pos[0]), int(day_pos[-1]) + 1

        entry_minute = ev_time.hour * 60 + ev_time.minute + entry_offset_min
        day_mod = et_mod[s:e]
        entry_arr = np.flatnonzero(day_mod >= entry_minute)
        if entry_arr.size == 0:
            continue
        entry_i_local = int(entry_arr[0])
        exit_i_local = entry_i_local + hold_bars
        if exit_i_local >= (e - s):
            continue

        entry_i = s + entry_i_local
        exit_i = s + exit_i_local
        entry_px = float(open_arr[entry_i])
        exit_px = float(close_arr[exit_i])
        if entry_px <= 0:
            continue
        long_ret = (exit_px - entry_px) / entry_px
        rows.append({
            "date": d,
            "entry_ts": idx_utc[entry_i],
            "exit_ts": idx_utc[exit_i],
            "entry_px": entry_px,
            "exit_px": exit_px,
            "long_ret": long_ret,
        })
    return pd.DataFrame(rows)


def build_placebo_dates(bars: pd.DataFrame, event_dates: set[pd.Timestamp],
                        close_time: dtime = dtime(13, 0)) -> list[tuple[pd.Timestamp, dtime]]:
    """All Wed/Thu trading days that are NOT in event_dates, at the same
    close_time. (Wed/Thu chosen because Treasury auctions are predominantly
    Wed/Thu — matching day-of-week reduces day-effect confound.)"""
    idx_et = bars.index.tz_convert(SESSION_TZ)
    unique_days = pd.DatetimeIndex(sorted(set(pd.Timestamp(d).normalize() for d in idx_et.date)))
    placebo = []
    for d in unique_days:
        if d.dayofweek not in (2, 3):
            continue
        if d in event_dates:
            continue
        placebo.append((d, close_time))
    return placebo


# ---------------------------------------------------------------------------
# Phase 1 reporting
# ---------------------------------------------------------------------------

def report_phase1(label: str, ev_df: pd.DataFrame, pl_df: pd.DataFrame,
                  cost_pt: float) -> dict:
    n_ev = len(ev_df)
    n_pl = len(pl_df)
    if n_ev == 0:
        print(f"  [{label}]  no event trades")
        return {}
    # Per-trade returns (LONG): event mean vs placebo mean.
    ev_mean = float(ev_df.long_ret.mean())
    ev_std = float(ev_df.long_ret.std(ddof=1))
    pl_mean = float(pl_df.long_ret.mean()) if n_pl > 0 else 0.0
    pl_std = float(pl_df.long_ret.std(ddof=1)) if n_pl > 0 else float("nan")

    # Welch's t-test (event vs placebo, two-sample, unequal variance).
    se_ev = ev_std / np.sqrt(n_ev)
    se_pl = (pl_std / np.sqrt(n_pl)) if n_pl > 0 else 0.0
    se_diff = np.sqrt(se_ev**2 + se_pl**2)
    t_diff = (ev_mean - pl_mean) / se_diff if se_diff > 0 else 0.0
    # One-sample t (event mean vs zero) for "is there directional content at all".
    t_ev0 = ev_mean / se_ev if se_ev > 0 else 0.0

    # bp magnitudes (LONG signed; absolute for "any-direction" magnitude).
    ev_mean_bp = ev_mean * 1e4
    ev_abs_mean_bp = float(np.abs(ev_df.long_ret).mean()) * 1e4
    pl_abs_mean_bp = float(np.abs(pl_df.long_ret).mean()) * 1e4 if n_pl > 0 else 0.0

    # Cost in bp (per-trade, using mean entry price).
    cost_bp = (cost_pt / float(ev_df.entry_px.mean())) * 1e4 if not ev_df.empty else 0.0

    # Net (post-cost) per-trade if we traded LONG every event.
    net_long_bp = ev_mean_bp - cost_bp
    net_short_bp = -ev_mean_bp - cost_bp

    print(f"  [{label}]")
    print(f"    events                : {n_ev}    placebo {n_pl}")
    print(f"    LONG gross mean       : {ev_mean_bp:+.2f} bp (placebo {pl_mean*1e4:+.2f} bp)")
    print(f"    t-stat (ev vs placebo): {t_diff:+.2f}    t-stat (ev vs 0): {t_ev0:+.2f}")
    print(f"    |event| mean magnitude: {ev_abs_mean_bp:.2f} bp  (placebo {pl_abs_mean_bp:.2f} bp)")
    print(f"    cost                  : {cost_bp:.2f} bp RT")
    print(f"    LONG net per-trade    : {net_long_bp:+.2f} bp   SHORT net: {net_short_bp:+.2f} bp")

    return {
        "n_ev": n_ev, "n_pl": n_pl,
        "ev_mean_bp": ev_mean_bp, "pl_mean_bp": pl_mean * 1e4,
        "ev_abs_mean_bp": ev_abs_mean_bp, "pl_abs_mean_bp": pl_abs_mean_bp,
        "t_diff": t_diff, "t_ev0": t_ev0,
        "cost_bp": cost_bp,
        "net_long_bp": net_long_bp, "net_short_bp": net_short_bp,
    }


def per_tenor_breakdown(label: str, ev_df: pd.DataFrame, auctions: pd.DataFrame,
                        cost_pt: float) -> None:
    # Join on date. Normalize types: ev_df.date is python date; auction_date is dt64.
    e = ev_df.copy()
    e["date"] = pd.to_datetime(e["date"])
    a = auctions[["auction_date", "tenor_bucket", "security_term",
                  "bid_to_cover_ratio"]].copy()
    a["auction_date"] = pd.to_datetime(a["auction_date"])
    df = e.merge(a, left_on="date", right_on="auction_date", how="left")
    print(f"  [{label}] per-tenor LONG-gross bp mean (events with that tenor):")
    for bucket in ["2y", "3y", "5y", "7y", "10y", "20y", "30y"]:
        sub = df[df.tenor_bucket == bucket]
        if len(sub) < 5:
            print(f"    {bucket:>4s}  n={len(sub):>3d}  (insufficient)")
            continue
        m = sub.long_ret.mean() * 1e4
        s = sub.long_ret.std(ddof=1) * 1e4
        n = len(sub)
        t = m / (s / np.sqrt(n)) if s > 0 else 0.0
        print(f"    {bucket:>4s}  n={n:>3d}  mean {m:+6.2f} bp  std {s:6.2f}  t {t:+5.2f}")


def regime_breakdown_returns(label: str, ev_df: pd.DataFrame) -> None:
    """Regime breakdown using per-event LONG returns (no day-of compounding —
    each auction is a discrete event)."""
    if ev_df.empty:
        return
    windows = [
        ("2019-2020 pre/COVID", "2019-01-01", "2020-12-31"),
        ("2021-2022 vol",       "2021-01-01", "2022-12-31"),
        ("2023-2026 holdout",   "2023-01-01", "2026-12-31"),
    ]
    print(f"  [{label}] LONG mean bp per regime:")
    df = ev_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    for lbl, s, e in windows:
        sub = df[(df.date >= s) & (df.date <= e)]
        if len(sub) < 5:
            print(f"    {lbl:<22s}  (insufficient: n={len(sub)})")
            continue
        m = sub.long_ret.mean() * 1e4
        std = sub.long_ret.std(ddof=1) * 1e4
        t = m / (std / np.sqrt(len(sub))) if std > 0 else 0.0
        print(f"    {lbl:<22s}  n={len(sub):>3d}  mean {m:+6.2f} bp  t {t:+5.2f}")


def hold_sweep(bars, auctions, instrument_cost_pt, label):
    print(f"\n  [{label}] hold-window sweep (LONG gross bp, then NET after cost):")
    for h in (3, 6, 12, 18, 24, 36):
        ev_dt = [(pd.Timestamp(r.auction_date), r.close_time_et) for r in auctions.itertuples()]
        ev_df = extract_event_drifts(bars, ev_dt, hold_bars=h)
        if ev_df.empty:
            print(f"    hold={h*5:>3d}min  no trades")
            continue
        m = ev_df.long_ret.mean() * 1e4
        cost_bp = (instrument_cost_pt / float(ev_df.entry_px.mean())) * 1e4
        net_long = m - cost_bp
        net_short = -m - cost_bp
        std = ev_df.long_ret.std(ddof=1) * 1e4
        t = m / (std / np.sqrt(len(ev_df))) if std > 0 else 0.0
        # Sharpe annualized treating each trade as one observation, ~108/yr.
        per_trade_sh_long = (net_long / 1e4) / (std / 1e4) if std > 0 else 0.0
        ann_sh_long = per_trade_sh_long * np.sqrt(108)
        print(f"    hold={h*5:>3d}min  n={len(ev_df):>3d}  gross {m:+6.2f} bp  t {t:+5.2f}  "
              f"net_LONG {net_long:+6.2f} bp  net_SHORT {net_short:+6.2f} bp  "
              f"ann_Sh_LONG {ann_sh_long:+5.2f}")


# ---------------------------------------------------------------------------
# Phase 2 (outcome-conditioned)
# ---------------------------------------------------------------------------

def phase2_outcome_conditioned(
    ev_df: pd.DataFrame, auctions: pd.DataFrame, cost_pt: float, label: str,
    btc_lookback: int = 12,
) -> dict:
    """Condition direction on bid-to-cover z-score:
        BTC > +z_thr  → strong auction → LONG
        BTC < -z_thr  → weak auction   → SHORT
    z-score is per-tenor rolling vs trailing btc_lookback auctions.
    """
    e = ev_df.copy()
    e["date"] = pd.to_datetime(e["date"])
    a = auctions[["auction_date", "tenor_bucket", "bid_to_cover_ratio"]].copy()
    a["auction_date"] = pd.to_datetime(a["auction_date"])
    df = e.merge(a, left_on="date", right_on="auction_date", how="left")
    df = df.dropna(subset=["bid_to_cover_ratio"]).copy()
    df = df.sort_values("date").reset_index(drop=True)

    # Per-tenor BTC z-score (past-only rolling).
    def _z_per_tenor(g):
        b = g.bid_to_cover_ratio.astype(float)
        # past-only rolling mean/std (exclude current; window = btc_lookback)
        rm = b.shift(1).rolling(btc_lookback, min_periods=4).mean()
        rs = b.shift(1).rolling(btc_lookback, min_periods=4).std()
        g["btc_z"] = (b - rm) / rs
        return g
    df = df.groupby("tenor_bucket", group_keys=False).apply(_z_per_tenor)

    results = {}
    for z_thr in (0.0, 0.5, 1.0):
        d2 = df.dropna(subset=["btc_z"]).copy()
        # Direction: LONG if btc_z > +z_thr (strong demand → yields drop → equities up)
        #            SHORT if btc_z < -z_thr (weak demand → yields rise → equities down)
        pos = np.where(d2.btc_z > z_thr, 1.0,
                       np.where(d2.btc_z < -z_thr, -1.0, 0.0))
        d2["pos"] = pos
        traded = d2[d2.pos != 0].copy()
        n = len(traded)
        if n < 30:
            results[z_thr] = {"n": n, "skip": "insufficient"}
            print(f"    z_thr={z_thr:.1f}  n={n}  (insufficient)")
            continue
        traded["signed_ret"] = traded.pos * traded.long_ret
        cost_per_trade = (cost_pt / traded.entry_px) * 1.0  # cost as fraction
        traded["net_ret"] = traded["signed_ret"] - cost_per_trade
        mean_bp = float(traded.signed_ret.mean()) * 1e4
        net_mean_bp = float(traded.net_ret.mean()) * 1e4
        std_bp = float(traded.signed_ret.std(ddof=1)) * 1e4
        per_trade_sh = (net_mean_bp / std_bp) if std_bp > 0 else 0.0
        ann_sh = per_trade_sh * np.sqrt(108)  # ~108 auctions/year
        wins = int((traded.net_ret > 0).sum())
        wr = wins / n
        gw = float(traded.net_ret[traded.net_ret > 0].sum())
        gl = -float(traded.net_ret[traded.net_ret < 0].sum())
        pf = gw / gl if gl > 0 else float("inf")
        print(f"    z_thr={z_thr:.1f}  n={n:>3d}  gross {mean_bp:+6.2f} bp  net {net_mean_bp:+6.2f} bp  "
              f"per-trade Sh {per_trade_sh:+.3f}  ann Sh {ann_sh:+.2f}  WR {wr*100:.1f}%  PF {pf:.2f}")
        results[z_thr] = {
            "n": n, "mean_bp": mean_bp, "net_mean_bp": net_mean_bp,
            "per_trade_sh": per_trade_sh, "ann_sh": ann_sh, "wr": wr, "pf": pf,
        }
    return results


# ---------------------------------------------------------------------------
# Main per-instrument
# ---------------------------------------------------------------------------

def run_instrument(inst: dict, auctions: pd.DataFrame) -> dict:
    symbol = inst["symbol"]
    cost_pt = inst["cost_pt"]

    section(f"Loading {symbol} {TIMEFRAME} (cost={cost_pt}pt RT)")
    bars = load_m5(symbol)
    n_days = len(set(bars.index.date))
    print(f"  bars     : {len(bars):,}")
    print(f"  range    : {bars.index[0]} -> {bars.index[-1]}")
    print(f"  days     : {n_days}")

    # Build event list.
    ev_dt = [(pd.Timestamp(r.auction_date), r.close_time_et) for r in auctions.itertuples()]
    event_dates = set(pd.Timestamp(r.auction_date) for r in auctions.itertuples())

    # ----- Phase 1: calendar-only test -----
    section(f"{symbol} Phase 1 — calendar drift (auction vs placebo)")
    ev_df = extract_event_drifts(bars, ev_dt, hold_bars=DEFAULT_HOLD_BARS)
    # Placebo at 13:00 ET (the modal auction time) on non-auction Wed/Thu.
    placebo_dt = build_placebo_dates(bars, event_dates, close_time=dtime(13, 0))
    pl_df = extract_event_drifts(bars, placebo_dt, hold_bars=DEFAULT_HOLD_BARS)
    p1 = report_phase1(f"{symbol}-phase1-60min", ev_df, pl_df, cost_pt)

    # ----- Per-tenor breakdown -----
    section(f"{symbol} Per-tenor breakdown")
    per_tenor_breakdown(symbol, ev_df, auctions, cost_pt)

    # ----- Regime breakdown (per-event mean) -----
    section(f"{symbol} Regime breakdown (LONG gross per regime)")
    regime_breakdown_returns(symbol, ev_df)

    # ----- Hold sweep -----
    section(f"{symbol} Hold-window sweep")
    hold_sweep(bars, auctions, cost_pt, symbol)

    # ----- Phase 2: outcome-conditioned (BTC z-score) -----
    section(f"{symbol} Phase 2 — outcome-conditioned (BTC z-score)")
    p2 = phase2_outcome_conditioned(ev_df, auctions, cost_pt, symbol)

    # Cost sensitivity on Phase 1 LONG.
    section(f"{symbol} Cost sensitivity (LONG every auction, 60min hold)")
    for c in (0.0, 0.25, 0.5, 1.0, 1.5):
        ev_df_tmp = ev_df.copy()
        cost_per_trade = (c / ev_df_tmp.entry_px) * 1.0
        net_ret = ev_df_tmp.long_ret - cost_per_trade
        m_bp = float(net_ret.mean()) * 1e4
        std_bp = float(net_ret.std(ddof=1)) * 1e4
        ann_sh = (m_bp / std_bp) * np.sqrt(108) if std_bp > 0 else 0.0
        print(f"  cost={c:>4.2f}pt  net mean {m_bp:+6.2f} bp  ann_Sh {ann_sh:+5.2f}")

    return {"symbol": symbol, "phase1": p1, "phase2": p2}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section("Treasury Auction Drift — Phase 1+2 (paired NDX/SPX)")
    auctions = load_auctions()
    print(f"  Auctions loaded: {len(auctions)}  ({auctions.auction_date.min().date()} -> {auctions.auction_date.max().date()})")
    print(f"  Per tenor: {auctions.tenor_bucket.value_counts().sort_index().to_dict()}")
    print(f"  Close times: {auctions.close_time_et.value_counts().to_dict()}")

    results = {}
    for inst in INSTRUMENTS:
        results[inst["symbol"]] = run_instrument(inst, auctions)

    section("Cross-instrument summary (Phase 1)")
    for sym, r in results.items():
        p = r.get("phase1", {})
        if not p:
            continue
        print(f"  {sym:>6s}  LONG gross {p['ev_mean_bp']:+6.2f} bp (placebo {p['pl_mean_bp']:+6.2f})  "
              f"t-diff {p['t_diff']:+5.2f}  t-ev0 {p['t_ev0']:+5.2f}  "
              f"cost {p['cost_bp']:.2f} bp  net_LONG {p['net_long_bp']:+6.2f}  net_SHORT {p['net_short_bp']:+6.2f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
