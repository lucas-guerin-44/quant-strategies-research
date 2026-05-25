#!/usr/bin/env python3
"""pre_natgas_eia Phase 2 simulator + validation pipeline.

First commodity-specific extension of the macro-event family. Tests 24h
pre-EIA-Weekly-Natural-Gas-Storage-Report drift on XNGUSD M5,
2023-01-03 to 2026-05-22 (data limit on the Eightcap broker).

Per lesson #54, runs BOTH directions (LONG / SHORT) in parallel.
Per lesson #55, uses mechanism-aware kill criteria (PF > 1.3 + Sh > +0.30
+ MDD < 25%) instead of LONG-bias WR > 55%.

Pre-committed kill criteria (applied to BEST direction):
  - Per-trade mean > +0.15% at 30 bp RT (NG-CFD-realistic default)
  - W4 (2024-2026) per-trade mean > +0.10%
  - PF > 1.3
  - Sharpe (x sqrt(52)) > +0.30
  - MDD < 25%
  - Events >= 50
  - Direction null-gap |LONG - SHORT| >= +0.30
  - Walk-forward OOS mean Sh >= +0.30, min OOS Sh >= 0
  - Placebo non-EIA Thursdays at 10:30 ET: |mean| < 0.05% or |t| < 1.5
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_ROOT / "experiments" / "macro_drift"))
from _profile_fomc_drift import et_to_utc  # type: ignore

# ---------- config ----------

CAL_PATH = _HERE / "eia_ng_calendar.csv"
M5_PATH = _ROOT / "ohlc_data" / "XNGUSD_M5.csv"

# NG CFD has much wider spread than index CFDs.
# Default 30bp RT; sweep 10/30/50/100 instead of 0/2/5/10/20.
COST_BPS_DEFAULT = 30.0
WINDOW_HOURS = 24
EXIT_BUFFER_MIN = 30

WINDOW_HOURS_SWEEP = (6, 12, 18, 24, 48)
EXIT_BUFFER_SWEEP = (5, 15, 30, 60)
COST_SWEEP_BPS = (10, 30, 50, 100)

# Data starts 2023-01-03 so only W3 (2023) and W4 (2024-2026) are populated.
def label_regime(year: int) -> str:
    if year <= 2023: return "W3"
    return "W4"


# ---------- data loading ----------

def load_calendar(historical_only: bool = True) -> pd.DataFrame:
    df = pd.read_csv(CAL_PATH)
    df["date"] = pd.to_datetime(df["date"])
    if historical_only:
        df = df[df["is_historical"] == "yes"].copy()
    rows = []
    for _, r in df.iterrows():
        h, m = map(int, r["announce_time_et"].split(":"))
        et_dt = r["date"] + pd.Timedelta(hours=h, minutes=m)
        utc_dt = et_to_utc(et_dt)
        rows.append({"date": r["date"], "year": r["date"].year,
                      "regime": label_regime(r["date"].year),
                      "announce_utc": utc_dt})
    return pd.DataFrame(rows)


def load_m5(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
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
        rows.append({"date": ev["date"], "year": ev["year"], "regime": ev["regime"],
                      "entry_px": entry_px, "exit_px": exit_px,
                      "gross_pct": gross, "net_pct": net})
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
    sh_annual = sh_per_trade * np.sqrt(52.0)   # ~52 EIA NG events/yr
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
    print(f"    Sharpe    : {m['sh']:+.2f}  (ann x sqrt(52))")
    print(f"    MDD       : {m['mdd']*100:+.2f}%")
    print(f"    CAGR      : {m['cagr']*100:+.2f}%  (total {m['total']*100:+.2f}%)")
    print(f"    WR        : {m['wr']*100:.1f}%   PF {m['pf']:.2f}")


def regime_table(trades: pd.DataFrame) -> None:
    print(f'  {"regime":<8s} {"n":>4s}  {"mean":>9s} {"std":>7s} {"t":>6s}  {"WR":>6s} {"Sh":>7s}')
    for w in ("W3", "W4"):
        sub = trades[trades["regime"] == w]
        m = event_metrics(sub)
        if m["n"] < 3:
            print(f"  {w:<8s} {m['n']:>4d}  (sparse)"); continue
        marker = ""
        if w == "W4":
            if m["mean"] > 0.15: marker = "  <<< W4 PASS"
            elif m["mean"] > 0.10: marker = "  <<< W4 MARGINAL"
            elif m["mean"] < 0: marker = "  <<< W4 FAIL"
        print(f"  {w:<8s} {m['n']:>4d}  {m['mean']:>+8.3f}% {m['std']:>6.3f}% {m['t']:>+5.2f}  {m['wr']*100:>5.1f}% {m['sh']:>+6.2f}{marker}")


def kill_check(label: str, trades: pd.DataFrame) -> dict:
    m = event_metrics(trades)
    if m["n"] == 0:
        print(f"  [{label}] NO TRADES -- KILL"); return {}
    w4 = trades[trades["regime"] == "W4"]
    w4m = event_metrics(w4) if len(w4) >= 3 else {"mean": 0.0}
    checks = {
        "mean > +0.15%      ": m["mean"] > 0.15,
        "W4_mean > +0.10%   ": w4m.get("mean", 0) > 0.10,
        "PF   > 1.3         ": m["pf"] > 1.3,
        "Sh   > +0.30       ": m["sh"] > 0.30,
        "MDD  < 25%         ": abs(m["mdd"]) < 0.25,
        "events >= 50       ": m["n"] >= 50,
    }
    print(f"  [{label}]   n={m['n']}  mean {m['mean']:+.3f}%  Sh {m['sh']:+.2f}  MDD {m['mdd']*100:+.2f}%  WR {m['wr']*100:.1f}%")
    for c, ok in checks.items():
        print(f"    {c} : {'PASS' if ok else 'FAIL'}")
    return checks


# ---------- placebo ----------

def placebo_check(df: pd.DataFrame, cal: pd.DataFrame, direction: str,
                   cost_bps: float = COST_BPS_DEFAULT, seed: int = 42) -> dict:
    """Same 24h pre-10:30-ET window, on random non-EIA Thursdays."""
    eia_dates = set(cal["date"].dt.date)
    start = df["timestamp"].min().date()
    end = df["timestamp"].max().date()
    # All Thursdays in data window not in eia_dates
    rng = np.random.default_rng(seed)
    pool = []
    d = start
    while d <= end:
        if d.weekday() == 3 and d not in eia_dates:
            pool.append(d)
        d = d + pd.Timedelta(days=1).to_pytimedelta()
    # Pool of non-EIA Thursdays will be small (holiday-shifted Thursdays only ~8).
    # Augment with all weekdays that don't fall on EIA-shifted dates, matching
    # the weekday distribution of eia_dates.
    eia_weekdays = pd.Series([d.weekday() for d in eia_dates]).value_counts()
    candidates = {wd: [] for wd in eia_weekdays.index}
    d = start
    while d <= end:
        if d.weekday() in candidates and d not in eia_dates:
            candidates[d.weekday()].append(d)
        d = d + pd.Timedelta(days=1).to_pytimedelta()
    sample = []
    for wd, n_wd in eia_weekdays.items():
        pool_wd = candidates[wd]
        if not pool_wd:
            continue
        idx = rng.choice(len(pool_wd), size=min(n_wd, len(pool_wd)), replace=False)
        sample.extend([pool_wd[i] for i in idx])
    sample = sorted(sample)
    fake_rows = []
    for d in sample:
        et_dt = pd.Timestamp(d) + pd.Timedelta(hours=10, minutes=30)
        utc_dt = et_to_utc(et_dt)
        fake_rows.append({"date": pd.Timestamp(d), "year": d.year,
                           "regime": label_regime(d.year),
                           "announce_utc": utc_dt})
    fake_cal = pd.DataFrame(fake_rows)
    trades = compute_event_returns(df, fake_cal, cost_bps=cost_bps, direction=direction)
    m = event_metrics(trades)
    print(f"  placebo non-EIA weekdays ({direction:<5s})  n={m['n']}  mean {m['mean']:+.3f}%  t {m['t']:+.2f}  Sh {m['sh']:+.2f}  WR {m['wr']*100:.1f}%")
    return m


# ---------- walk-forward ----------

def walk_forward(df: pd.DataFrame, cal: pd.DataFrame, direction: str,
                  cost_bps: float = COST_BPS_DEFAULT) -> list[dict]:
    # Narrower splits given 2023-2026 data window.
    splits = [
        (pd.Timestamp("2023-01-01"), pd.Timestamp("2024-01-01"), pd.Timestamp("2026-12-31")),
        (pd.Timestamp("2023-01-01"), pd.Timestamp("2024-07-01"), pd.Timestamp("2026-12-31")),
        (pd.Timestamp("2023-01-01"), pd.Timestamp("2025-01-01"), pd.Timestamp("2026-12-31")),
    ]
    results = []
    for is_start, oos_start, oos_end in splits:
        is_cal  = cal[(cal["date"] >= is_start) & (cal["date"] < oos_start)]
        oos_cal = cal[(cal["date"] >= oos_start) & (cal["date"] < oos_end)]
        is_t  = compute_event_returns(df, is_cal,  cost_bps=cost_bps, direction=direction)
        oos_t = compute_event_returns(df, oos_cal, cost_bps=cost_bps, direction=direction)
        is_m, oos_m = event_metrics(is_t), event_metrics(oos_t)
        results.append({
            "split": f"IS {is_start.date()}->{oos_start.date()} / OOS {oos_start.date()}-{oos_end.date()}",
            "is_n": is_m["n"], "is_sh": is_m["sh"], "is_mean": is_m["mean"],
            "oos_n": oos_m["n"], "oos_sh": oos_m["sh"], "oos_mean": oos_m["mean"],
        })
    return results


# ---------- main ----------

def main() -> None:
    section("PRE-EIA-NG DRIFT (XNGUSD) -- Phase 2  (direction TBD per #54, mech-aware KCs per #55)")
    print(f"Calendar: {CAL_PATH}")
    print(f"M5 data:  {M5_PATH}")
    print(f"Window:   {WINDOW_HOURS}h entry / {EXIT_BUFFER_MIN}min exit buffer")
    print(f"Cost:     {COST_BPS_DEFAULT} bp RT default (NG-CFD-realistic)")

    cal = load_calendar(historical_only=True)
    df = load_m5(M5_PATH)
    print(f"\nLoaded {len(cal)} historical EIA NG events ({cal['date'].min().date()} -> {cal['date'].max().date()})")
    print(f"Loaded {len(df)} XNGUSD M5 bars ({df['timestamp'].min().date()} -> {df['timestamp'].max().date()})")

    # Both directions, baseline
    section("BASELINE -- 24h, both directions, 30bp RT")
    base_long  = compute_event_returns(df, cal, direction="long")
    base_short = compute_event_returns(df, cal, direction="short")
    report("LONG ", base_long)
    print()
    report("SHORT", base_short)

    m_long  = event_metrics(base_long)
    m_short = event_metrics(base_short)
    gap_long = m_long["mean"] - m_short["mean"]
    print(f"\n  direction null-gap (LONG-SHORT mean): {gap_long:+.3f}%")
    if abs(gap_long) >= 0.30:
        best_dir = "long" if m_long["mean"] > m_short["mean"] else "short"
        print(f"  null-gap PASS (>= 0.30) -- best direction: {best_dir.upper()}")
    else:
        best_dir = "long" if m_long["mean"] > m_short["mean"] else "short"
        print(f"  null-gap FAIL (|gap| < 0.30) -- mechanism lacks directional content")

    best_trades = base_long if best_dir == "long" else base_short
    best_m = event_metrics(best_trades)

    section(f"REGIME BREAKDOWN -- best direction = {best_dir.upper()}")
    regime_table(best_trades)

    section(f"PLACEBO -- non-EIA matched-weekday at 10:30 ET ({best_dir.upper()})")
    placebo = placebo_check(df, cal, direction=best_dir)
    placebo_opp = placebo_check(df, cal, direction=("short" if best_dir == "long" else "long"))

    section(f"WALK-FORWARD (3 IS/OOS splits, {best_dir.upper()})")
    wf = walk_forward(df, cal, direction=best_dir)
    print(f"  {'split':<60s} {'IS n':>5s} {'IS Sh':>7s} {'IS mean':>9s}   {'OOS n':>5s} {'OOS Sh':>7s} {'OOS mean':>9s}")
    for r in wf:
        print(f"  {r['split']:<60s} {r['is_n']:>5d} {r['is_sh']:>+7.2f} {r['is_mean']:>+8.3f}%   {r['oos_n']:>5d} {r['oos_sh']:>+7.2f} {r['oos_mean']:>+8.3f}%")
    wf_oos = [r["oos_sh"] for r in wf if r["oos_n"] >= 3]
    wf_mean = float(np.mean(wf_oos)) if wf_oos else float("nan")
    wf_min  = float(np.min(wf_oos))  if wf_oos else float("nan")
    print(f"\n  walk-forward OOS Sh: mean {wf_mean:+.2f}  min {wf_min:+.2f}")

    section(f"COST SENSITIVITY ({best_dir.upper()})")
    print(f"  {'cost(bp)':>8s} {'n':>4s} {'mean':>9s} {'Sh':>7s}")
    for c in COST_SWEEP_BPS:
        t = compute_event_returns(df, cal, cost_bps=c, direction=best_dir)
        m = event_metrics(t)
        print(f"  {c:>8d} {m['n']:>4d} {m['mean']:>+8.3f}% {m['sh']:>+7.2f}")

    section(f"WINDOW SWEEP (30bp RT, {best_dir.upper()})")
    print(f"  {'window_h':>8s} {'buffer_min':>10s} {'n':>4s} {'mean':>9s} {'Sh':>7s}")
    for wh in WINDOW_HOURS_SWEEP:
        for eb in EXIT_BUFFER_SWEEP:
            t = compute_event_returns(df, cal, window_hours=wh, exit_buffer_min=eb, direction=best_dir)
            m = event_metrics(t)
            print(f"  {wh:>8d} {eb:>10d} {m['n']:>4d} {m['mean']:>+8.3f}% {m['sh']:>+7.2f}")

    section(f"KILL-CHECK SUMMARY (best direction = {best_dir.upper()}, 24h, 30bp)")
    checks = kill_check("baseline_best", best_trades)
    null_ok = abs(gap_long) >= 0.30
    plc_ok  = abs(placebo["mean"]) < 0.05 or abs(placebo["t"]) < 1.5
    wf_ok   = (len(wf_oos) >= 2) and (wf_mean >= 0.30) and (wf_min >= 0.0)
    all_basic = all(checks.values()) if checks else False
    print(f"\n  direction null-gap >= +0.30:  {'PASS' if null_ok else 'FAIL'} ({gap_long:+.3f})")
    print(f"  placebo benign            :  {'PASS' if plc_ok else 'FAIL'} (mean {placebo['mean']:+.3f}%, t {placebo['t']:+.2f})")
    print(f"  walk-forward OOS pass     :  {'PASS' if wf_ok else 'FAIL'} (mean {wf_mean:+.2f} min {wf_min:+.2f})")

    section("FINAL VERDICT")
    if all_basic and null_ok and plc_ok and wf_ok:
        print(f"  PASS -- pre-EIA-NG {best_dir.upper()} on XNGUSD validated; proceed to Phase 7 EA build")
    elif (best_m["mean"] > 0.10) and null_ok and not all_basic:
        print(f"  MARGINAL -- mechanism present ({best_dir.upper()}) but not deploy-grade")
    else:
        print("  REJECT -- tombstone; mechanism does not survive pre-commits")
    print()


if __name__ == "__main__":
    main()
