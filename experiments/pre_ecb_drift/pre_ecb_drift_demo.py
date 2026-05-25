#!/usr/bin/env python3
"""pre_ecb_drift Phase 2 simulator + validation pipeline.

European analog of macro_drift (FOMC, deployed NDX100 +1.04 Sh).
Tests 24h pre-ECB-announcement drift on GER40 M5, 2018-01-25 to 2026-04-30.

Pre-committed kill criteria (from pre_ecb_drift.md):
  - Per-trade mean > +0.10% (full sample, 5 bp RT)
  - W4 (2024-2026) per-trade mean > +0.05%
  - Win rate > 55%
  - MDD < 25%
  - Events >= 50
  - Direction null-gap (LONG - SHORT) >= +0.30
  - Walk-forward mean OOS Sh >= +0.30, min OOS Sh >= 0
  - Placebo non-ECB Thursdays: mean ~0, t < 1.5
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_HERE))

# ---------- config ----------

CAL_PATH = _HERE / "ecb_calendar.csv"
GER_M5_PATH = _ROOT / "ohlc_data" / "GER40_M5.csv"

# GER40 CFD: Eightcap typical spread 1-2pt on ~18000 = ~1-2 bp RT.
# Use 5 bp pessimistic per macro_drift cost-sensitivity convention.
COST_BPS_DEFAULT = 5.0

WINDOW_HOURS = 24
EXIT_BUFFER_MIN = 30

WINDOW_HOURS_SWEEP = (6, 12, 18, 24, 48)
EXIT_BUFFER_SWEEP = (5, 15, 30, 60)
COST_SWEEP_BPS = (0, 2, 5, 10, 20)

# Regime windows (mirrors macro_drift)
def label_regime(year: int) -> str:
    if year <= 2019:
        return "W1"
    if year <= 2021:
        return "W2"
    if year <= 2023:
        return "W3"
    return "W4"


# ---------- timezone ----------

def cet_is_dst(date: pd.Timestamp) -> bool:
    """EU DST: last Sunday March -> last Sunday October."""
    y = date.year
    # last Sunday of March
    march_31 = pd.Timestamp(f"{y}-03-31")
    march_lastsun = march_31 - pd.Timedelta(days=(march_31.dayofweek + 1) % 7)
    # last Sunday of October
    oct_31 = pd.Timestamp(f"{y}-10-31")
    oct_lastsun = oct_31 - pd.Timedelta(days=(oct_31.dayofweek + 1) % 7)
    return march_lastsun <= pd.Timestamp(date.year, date.month, date.day) < oct_lastsun


def cet_to_utc(local_dt: pd.Timestamp) -> pd.Timestamp:
    """Convert naive CET (Europe/Berlin) datetime to UTC."""
    offset_h = 2 if cet_is_dst(local_dt) else 1   # CEST = UTC+2, CET = UTC+1
    return (local_dt - pd.Timedelta(hours=offset_h)).tz_localize("UTC")


# ---------- data loading ----------

def load_calendar(historical_only: bool = True) -> pd.DataFrame:
    df = pd.read_csv(CAL_PATH)
    df["date"] = pd.to_datetime(df["date"])
    if historical_only:
        df = df[df["is_historical"] == "yes"].copy()
    rows = []
    for _, r in df.iterrows():
        h, m = map(int, r["announce_time_cet"].split(":"))
        cet_dt = r["date"] + pd.Timedelta(hours=h, minutes=m)
        utc_dt = cet_to_utc(cet_dt)
        rows.append({
            "date": r["date"],
            "year": r["date"].year,
            "regime": label_regime(r["date"].year),
            "announce_utc": utc_dt,
            "with_projections": r["with_projections"] == "yes",
        })
    return pd.DataFrame(rows)


def load_m5(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df = df[df["timestamp"] >= pd.Timestamp("2018-01-01", tz="UTC")].copy()
    return df


def closest_bar_close(df: pd.DataFrame, target_utc: pd.Timestamp,
                       tolerance_min: int = 30) -> float | None:
    delta = (df["timestamp"] - target_utc).abs()
    idx = delta.idxmin()
    if delta.iloc[idx] > pd.Timedelta(minutes=tolerance_min):
        return None
    return float(df.iloc[idx]["close"])


# ---------- core ----------

def compute_event_returns(df: pd.DataFrame, cal: pd.DataFrame,
                           window_hours: int = WINDOW_HOURS,
                           exit_buffer_min: int = EXIT_BUFFER_MIN,
                           cost_bps: float = COST_BPS_DEFAULT,
                           direction: str = "long") -> pd.DataFrame:
    """For each ECB event, compute pnl over [T-window, T-buffer]. direction in {long, short}."""
    sign = +1.0 if direction == "long" else -1.0
    rows = []
    for _, ev in cal.iterrows():
        announce = ev["announce_utc"]
        entry_t = announce - pd.Timedelta(hours=window_hours)
        exit_t  = announce - pd.Timedelta(minutes=exit_buffer_min)
        entry_px = closest_bar_close(df, entry_t)
        exit_px  = closest_bar_close(df, exit_t)
        if entry_px is None or exit_px is None:
            continue
        gross = sign * (exit_px - entry_px) / entry_px * 100.0
        net = gross - cost_bps / 100.0
        rows.append({
            "date": ev["date"],
            "year": ev["year"],
            "regime": ev["regime"],
            "with_projections": ev["with_projections"],
            "entry_px": entry_px,
            "exit_px": exit_px,
            "gross_pct": gross,
            "net_pct": net,
        })
    return pd.DataFrame(rows)


# ---------- stats ----------

def event_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"n": 0, "sh": 0.0, "mdd": 0.0, "cagr": 0.0, "wr": 0.0, "pf": 0.0,
                 "mean": 0.0, "std": 0.0, "t": 0.0, "total": 0.0}
    net = trades["net_pct"].to_numpy() / 100.0
    n = len(net)
    mean = float(net.mean())
    std = float(net.std(ddof=1)) if n > 1 else 0.0
    se = std / np.sqrt(n) if n > 0 else 0.0
    t = mean / se if se > 0 else 0.0
    wr = float((net > 0).mean())
    eq = (1.0 + net).cumprod()
    total = float(eq[-1] - 1.0)
    sh_per_trade = mean / std if std > 0 else 0.0
    sh_annual = sh_per_trade * np.sqrt(8.0)   # ~8 ECB events/yr
    rm = np.maximum.accumulate(eq)
    mdd = float(((eq - rm) / rm).min())
    dates = pd.to_datetime(trades["date"])
    years = max((dates.max() - dates.min()).days / 365.25, 1e-9)
    cagr = ((1.0 + total) ** (1.0 / years)) - 1.0 if total > -1 else -1.0
    wins = net[net > 0]; losses = net[net <= 0]
    gw = float(wins.sum()) if wins.size else 0.0
    gl = float(-losses.sum()) if losses.size else 0.0
    pf = gw / gl if gl > 0 else float("inf")
    return {"n": n, "sh": sh_annual, "mdd": mdd, "cagr": cagr, "wr": wr, "pf": pf,
             "mean": mean * 100, "std": std * 100, "t": t, "total": total}


def section(t: str) -> None:
    print(f'\n{"=" * 92}\n  {t}\n{"=" * 92}\n')


def report(label: str, trades: pd.DataFrame) -> None:
    m = event_metrics(trades)
    if m["n"] == 0:
        print(f"  [{label}] no trades"); return
    print(f"  [{label}]")
    print(f"    events    : {m['n']}")
    print(f"    mean_net  : {m['mean']:+.3f}%  std {m['std']:.3f}%  t {m['t']:+.2f}")
    print(f"    Sharpe    : {m['sh']:+.2f}  (ann x sqrt(8))")
    print(f"    MDD       : {m['mdd']*100:+.2f}%")
    print(f"    CAGR      : {m['cagr']*100:+.2f}%  (total {m['total']*100:+.2f}%)")
    print(f"    WR        : {m['wr']*100:.1f}%   PF {m['pf']:.2f}")


def regime_table(trades: pd.DataFrame) -> None:
    print(f'  {"regime":<8s} {"n":>4s}  {"mean":>9s} {"std":>7s} {"t":>6s}  {"WR":>6s} {"Sh":>7s}')
    for w in ("W1", "W2", "W3", "W4"):
        sub = trades[trades["regime"] == w]
        m = event_metrics(sub)
        if m["n"] < 3:
            print(f"  {w:<8s} {m['n']:>4d}  (sparse)"); continue
        marker = ""
        if w == "W4":
            if m["mean"] > 0.10: marker = "  <<< deploy-bar PASS"
            elif m["mean"] > 0.05: marker = "  <<< deploy-bar MARGINAL"
            elif m["mean"] < 0: marker = "  <<< deploy-bar FAIL"
        print(f"  {w:<8s} {m['n']:>4d}  {m['mean']:>+8.3f}% {m['std']:>6.3f}% {m['t']:>+5.2f}  {m['wr']*100:>5.1f}% {m['sh']:>+6.2f}{marker}")


def kill_check(label: str, trades: pd.DataFrame) -> dict:
    m = event_metrics(trades)
    if m["n"] == 0:
        print(f"  [{label}] NO TRADES -- KILL"); return {}
    w4 = trades[trades["regime"] == "W4"]
    w4m = event_metrics(w4) if len(w4) >= 3 else {"mean": 0.0}
    checks = {
        "mean > +0.10%       ": m["mean"] > 0.10,
        "W4_mean > +0.05%    ": w4m.get("mean", 0) > 0.05,
        "WR > 55%            ": m["wr"] > 0.55,
        "MDD < 25%           ": abs(m["mdd"]) < 0.25,
        "events >= 50        ": m["n"] >= 50,
    }
    print(f"  [{label}]   n={m['n']}  mean {m['mean']:+.3f}%  Sh {m['sh']:+.2f}  MDD {m['mdd']*100:+.2f}%  WR {m['wr']*100:.1f}%")
    for c, ok in checks.items():
        print(f"    {c} : {'PASS' if ok else 'FAIL'}")
    return checks


# ---------- placebo: non-ECB Thursdays ----------

def placebo_check(df: pd.DataFrame, cal: pd.DataFrame,
                   cost_bps: float = COST_BPS_DEFAULT, seed: int = 42,
                   n_samples: int | None = None) -> dict:
    """Same 24h window, anchored at 14:15 CET on random non-ECB Thursdays."""
    ecb_dates = set(cal["date"].dt.date)
    start = df["timestamp"].min().date()
    end = df["timestamp"].max().date()
    all_thu = []
    d = start
    while d <= end:
        if d.weekday() == 3 and d not in ecb_dates:  # Thursday=3
            all_thu.append(d)
        d = d + pd.Timedelta(days=1).to_pytimedelta()
    if n_samples is not None and len(all_thu) > n_samples:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(all_thu), size=n_samples, replace=False)
        all_thu = [all_thu[i] for i in sorted(idx)]
    # Build fake "cal" with announce_utc = 14:15 CET on each Thursday
    fake_rows = []
    for d in all_thu:
        cet_dt = pd.Timestamp(d) + pd.Timedelta(hours=14, minutes=15)
        utc_dt = cet_to_utc(cet_dt)
        fake_rows.append({"date": pd.Timestamp(d), "year": d.year,
                           "regime": label_regime(d.year),
                           "announce_utc": utc_dt, "with_projections": False})
    fake_cal = pd.DataFrame(fake_rows)
    placebo_trades = compute_event_returns(df, fake_cal, cost_bps=cost_bps, direction="long")
    m = event_metrics(placebo_trades)
    print(f"  placebo Thursdays  n={m['n']}  mean {m['mean']:+.3f}%  t {m['t']:+.2f}  Sh {m['sh']:+.2f}  WR {m['wr']*100:.1f}%")
    return m


# ---------- walk-forward ----------

def walk_forward(df: pd.DataFrame, cal: pd.DataFrame,
                  cost_bps: float = COST_BPS_DEFAULT) -> list[dict]:
    """Three IS/OOS splits mirroring macro_drift's protocol."""
    splits = [
        (pd.Timestamp("2018-01-01"), pd.Timestamp("2022-01-01"), pd.Timestamp("2026-12-31")),
        (pd.Timestamp("2018-01-01"), pd.Timestamp("2023-01-01"), pd.Timestamp("2026-12-31")),
        (pd.Timestamp("2018-01-01"), pd.Timestamp("2024-01-01"), pd.Timestamp("2026-12-31")),
    ]
    results = []
    for is_start, oos_start, oos_end in splits:
        is_cal  = cal[(cal["date"] >= is_start) & (cal["date"] < oos_start)]
        oos_cal = cal[(cal["date"] >= oos_start) & (cal["date"] < oos_end)]
        is_trades  = compute_event_returns(df, is_cal,  cost_bps=cost_bps, direction="long")
        oos_trades = compute_event_returns(df, oos_cal, cost_bps=cost_bps, direction="long")
        is_m  = event_metrics(is_trades)
        oos_m = event_metrics(oos_trades)
        results.append({
            "split": f"IS {is_start.year}->{oos_start.year} / OOS {oos_start.year}-{oos_end.year}",
            "is_n": is_m["n"], "is_sh": is_m["sh"], "is_mean": is_m["mean"],
            "oos_n": oos_m["n"], "oos_sh": oos_m["sh"], "oos_mean": oos_m["mean"],
        })
    return results


# ---------- main ----------

def main() -> None:
    section("PRE-ECB DRIFT (GER40) -- Phase 2")
    print(f"Calendar: {CAL_PATH}")
    print(f"M5 data:  {GER_M5_PATH}")
    print(f"Window:   {WINDOW_HOURS}h entry / {EXIT_BUFFER_MIN}min exit buffer")
    print(f"Cost:     {COST_BPS_DEFAULT} bp RT default")

    cal = load_calendar(historical_only=True)
    df = load_m5(GER_M5_PATH)
    print(f"\nLoaded {len(cal)} historical ECB events ({cal['date'].min().date()} -> {cal['date'].max().date()})")
    print(f"Loaded {len(df)} GER40 M5 bars ({df['timestamp'].min().date()} -> {df['timestamp'].max().date()})")

    # Baseline
    section("BASELINE -- 24h LONG, 5bp RT")
    base = compute_event_returns(df, cal, direction="long")
    report("baseline_long", base)
    print()
    regime_table(base)

    # Direction null-check
    section("DIRECTION NULL-CHECK (24h SHORT, same window)")
    null_short = compute_event_returns(df, cal, direction="short")
    report("null_short", null_short)
    m_long  = event_metrics(base)
    m_short = event_metrics(null_short)
    gap = m_long["mean"] - m_short["mean"]
    print(f"\n  direction null-gap (LONG-SHORT mean): {gap:+.3f}% per trade")
    if gap >= 0.30:
        print(f"  null-gap PASS (>=+0.30)")
    else:
        print(f"  null-gap FAIL (<+0.30) -- mechanism lacks directional content")

    # Placebo Thursdays
    section("PLACEBO -- non-ECB Thursdays (same 14:15 CET anchor)")
    placebo = placebo_check(df, cal, n_samples=len(cal))

    # Walk-forward
    section("WALK-FORWARD (3 IS/OOS splits)")
    wf = walk_forward(df, cal)
    print(f"  {'split':<42s} {'IS n':>5s} {'IS Sh':>7s} {'IS mean':>9s}   {'OOS n':>5s} {'OOS Sh':>7s} {'OOS mean':>9s}")
    for r in wf:
        print(f"  {r['split']:<42s} {r['is_n']:>5d} {r['is_sh']:>+7.2f} {r['is_mean']:>+8.3f}%   {r['oos_n']:>5d} {r['oos_sh']:>+7.2f} {r['oos_mean']:>+8.3f}%")
    wf_oos = [r["oos_sh"] for r in wf if r["oos_n"] >= 3]
    if wf_oos:
        wf_mean = float(np.mean(wf_oos))
        wf_min  = float(np.min(wf_oos))
        print(f"\n  walk-forward OOS Sh: mean {wf_mean:+.2f}  min {wf_min:+.2f}")
        print(f"  WF mean >= +0.30:  {'PASS' if wf_mean >= 0.30 else 'FAIL'}")
        print(f"  WF min  >= 0:      {'PASS' if wf_min  >= 0    else 'FAIL'}")

    # Cost sensitivity
    section("COST SENSITIVITY")
    print(f"  {'cost(bp)':>8s} {'n':>4s} {'mean':>9s} {'Sh':>7s}")
    for c in COST_SWEEP_BPS:
        t = compute_event_returns(df, cal, cost_bps=c, direction="long")
        m = event_metrics(t)
        print(f"  {c:>8d} {m['n']:>4d} {m['mean']:>+8.3f}% {m['sh']:>+7.2f}")

    # Window sweep
    section("WINDOW SWEEP (5bp RT)")
    print(f"  {'window_h':>8s} {'buffer_min':>10s} {'n':>4s} {'mean':>9s} {'Sh':>7s}")
    for wh in WINDOW_HOURS_SWEEP:
        for eb in EXIT_BUFFER_SWEEP:
            t = compute_event_returns(df, cal, window_hours=wh, exit_buffer_min=eb, direction="long")
            m = event_metrics(t)
            print(f"  {wh:>8d} {eb:>10d} {m['n']:>4d} {m['mean']:>+8.3f}% {m['sh']:>+7.2f}")

    # Headline kill-check
    section("KILL-CHECK SUMMARY (baseline 24h LONG, 5bp)")
    checks = kill_check("baseline", base)
    # Aggregate verdict
    all_basic = all(checks.values()) if checks else False
    null_ok = gap >= 0.30
    plc_ok = placebo["mean"] < 0.05 or placebo["t"] < 1.5
    wf_ok = (len(wf_oos) >= 2) and (np.mean(wf_oos) >= 0.30) and (np.min(wf_oos) >= 0.0)
    print(f"\n  direction null-gap >= +0.30:  {'PASS' if null_ok else 'FAIL'} ({gap:+.3f})")
    print(f"  placebo benign            :  {'PASS' if plc_ok else 'FAIL'} (mean {placebo['mean']:+.3f}%, t {placebo['t']:+.2f})")
    print(f"  walk-forward OOS pass     :  {'PASS' if wf_ok else 'FAIL'}")

    section("FINAL VERDICT")
    if all_basic and null_ok and plc_ok and wf_ok:
        print("  PASS -- pre-ECB drift on GER40 validated; proceed to Phase 7 EA build")
    elif (m_long['mean'] > 0.05) and null_ok and not all_basic:
        print("  MARGINAL -- mechanism present but not deploy-grade (one or more pre-commits failed)")
    else:
        print("  REJECT -- tombstone; mechanism does not survive pre-commits")
    print()


if __name__ == "__main__":
    main()
