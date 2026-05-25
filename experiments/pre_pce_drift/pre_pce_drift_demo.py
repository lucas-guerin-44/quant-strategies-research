#!/usr/bin/env python3
"""pre_pce_drift Phase 2 simulator + validation pipeline.

Fourth extension of the macro_drift family. Tests 24h pre-PCE-release drift on
NDX100 M5, 2018-2026. PCE = Personal Consumption Expenditures Price Index
(BEA, 08:30 ET, last business day of month, ~12/yr). Direct corroboration
test of the lesson #56 canonical rule (scheduled US-macro events drift LONG
on NDX via institutional risk-premium accumulation).

Per lesson #54, runs BOTH directions (LONG / SHORT) in parallel.
Per lesson #55, uses mechanism-aware kill criteria (PF > 1.3 + Sh > +0.30
+ MDD < 25%) instead of LONG-bias WR > 55%.

Pre-committed kill criteria (applied to BEST direction):
  - Per-trade mean > +0.10% at 5 bp RT
  - W4 (2024-2026) per-trade mean > +0.05%
  - PF > 1.3
  - Sharpe (x sqrt(12)) > +0.30
  - MDD < 25%
  - Events >= 50
  - Direction null-gap |LONG - SHORT| >= +0.30
  - Walk-forward OOS mean Sh >= +0.30, min OOS Sh >= 0
  - Placebo non-PCE weekdays: |best dir mean| < 0.05% or t < 1.5
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_HERE))
# Reuse macro_drift's ET timezone helper
sys.path.insert(0, str(_ROOT / "experiments" / "macro_drift"))
from _profile_fomc_drift import et_to_utc  # type: ignore

# ---------- config ----------

CAL_PATH = _HERE / "pce_calendar.csv"
NDX_M5_PATH = _ROOT / "ohlc_data" / "NDX100_M5.csv"

COST_BPS_DEFAULT = 5.0
WINDOW_HOURS = 24
EXIT_BUFFER_MIN = 30

WINDOW_HOURS_SWEEP = (6, 12, 18, 24, 48)
EXIT_BUFFER_SWEEP = (5, 15, 30, 60)
COST_SWEEP_BPS = (0, 2, 5, 10, 20)


def label_regime(year: int) -> str:
    if year <= 2019: return "W1"
    if year <= 2021: return "W2"
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
    sh_annual = sh_per_trade * np.sqrt(12.0)
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
    print(f"    Sharpe    : {m['sh']:+.2f}  (ann x sqrt(12))")
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
            if m["mean"] > 0.10: marker = "  <<< W4 PASS"
            elif m["mean"] > 0.05: marker = "  <<< W4 MARGINAL"
            elif m["mean"] < 0: marker = "  <<< W4 FAIL"
        print(f"  {w:<8s} {m['n']:>4d}  {m['mean']:>+8.3f}% {m['std']:>6.3f}% {m['t']:>+5.2f}  {m['wr']*100:>5.1f}% {m['sh']:>+6.2f}{marker}")


def kill_check(label: str, trades: pd.DataFrame) -> dict:
    m = event_metrics(trades)
    if m["n"] == 0:
        print(f"  [{label}] NO TRADES -- KILL"); return {}
    w4 = trades[trades["regime"] == "W4"]
    w4m = event_metrics(w4) if len(w4) >= 3 else {"mean": 0.0}
    checks = {
        "mean > +0.10%      ": m["mean"] > 0.10,
        "W4_mean > +0.05%   ": w4m.get("mean", 0) > 0.05,
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
    """Same 24h pre-08:30-ET window, on random non-PCE weekdays (weekday-matched).

    PCE releases land mostly on Friday (~half) plus Thu/Mon end-of-month edges,
    so the placebo population is weekday-matched to avoid a day-of-week confound.
    Also -- because PCE clusters at month-end, a strong placebo would suggest
    month-end structural drift rather than PCE-specific signal; the placebo's
    role here is exactly to falsify that confound.
    """
    pce_dates = set(cal["date"].dt.date)
    start = df["timestamp"].min().date()
    end = df["timestamp"].max().date()
    pce_weekdays = [d.weekday() for d in pce_dates]
    weekday_counts = pd.Series(pce_weekdays).value_counts()
    all_candidates = {wd: [] for wd in weekday_counts.index}
    d = start
    while d <= end:
        if d.weekday() in all_candidates and d not in pce_dates:
            all_candidates[d.weekday()].append(d)
        d = d + pd.Timedelta(days=1).to_pytimedelta()
    rng = np.random.default_rng(seed)
    sample = []
    for wd, n_wd in weekday_counts.items():
        pool = all_candidates[wd]
        if not pool:
            continue
        idx = rng.choice(len(pool), size=min(n_wd, len(pool)), replace=False)
        sample.extend([pool[i] for i in idx])
    sample = sorted(sample)
    fake_rows = []
    for d in sample:
        et_dt = pd.Timestamp(d) + pd.Timedelta(hours=8, minutes=30)
        utc_dt = et_to_utc(et_dt)
        fake_rows.append({"date": pd.Timestamp(d), "year": d.year,
                           "regime": label_regime(d.year),
                           "announce_utc": utc_dt})
    fake_cal = pd.DataFrame(fake_rows)
    trades = compute_event_returns(df, fake_cal, cost_bps=cost_bps, direction=direction)
    m = event_metrics(trades)
    print(f"  placebo weekdays ({direction:<5s})  n={m['n']}  mean {m['mean']:+.3f}%  t {m['t']:+.2f}  Sh {m['sh']:+.2f}  WR {m['wr']*100:.1f}%")
    return m


# ---------- walk-forward ----------

def walk_forward(df: pd.DataFrame, cal: pd.DataFrame, direction: str,
                  cost_bps: float = COST_BPS_DEFAULT) -> list[dict]:
    splits = [
        (pd.Timestamp("2019-01-01"), pd.Timestamp("2022-01-01"), pd.Timestamp("2026-12-31")),
        (pd.Timestamp("2019-01-01"), pd.Timestamp("2023-01-01"), pd.Timestamp("2026-12-31")),
        (pd.Timestamp("2019-01-01"), pd.Timestamp("2024-01-01"), pd.Timestamp("2026-12-31")),
    ]
    results = []
    for is_start, oos_start, oos_end in splits:
        is_cal  = cal[(cal["date"] >= is_start) & (cal["date"] < oos_start)]
        oos_cal = cal[(cal["date"] >= oos_start) & (cal["date"] < oos_end)]
        is_t  = compute_event_returns(df, is_cal,  cost_bps=cost_bps, direction=direction)
        oos_t = compute_event_returns(df, oos_cal, cost_bps=cost_bps, direction=direction)
        is_m, oos_m = event_metrics(is_t), event_metrics(oos_t)
        results.append({
            "split": f"IS {is_start.year}->{oos_start.year} / OOS {oos_start.year}-{oos_end.year}",
            "is_n": is_m["n"], "is_sh": is_m["sh"], "is_mean": is_m["mean"],
            "oos_n": oos_m["n"], "oos_sh": oos_m["sh"], "oos_mean": oos_m["mean"],
        })
    return results


# ---------- friday-vs-non-friday subset (per red-flag #4) ----------

def friday_subset_diagnostic(trades: pd.DataFrame) -> None:
    if trades.empty:
        print("  (no trades for subset)")
        return
    trades = trades.copy()
    trades["dow"] = pd.to_datetime(trades["date"]).dt.dayofweek
    fri = trades[trades["dow"] == 4]
    non_fri = trades[trades["dow"] != 4]
    m_fri = event_metrics(fri)
    m_non = event_metrics(non_fri)
    print(f"  Friday     n={m_fri['n']:>3d}  mean {m_fri['mean']:+.3f}%  Sh {m_fri['sh']:+.2f}  WR {m_fri['wr']*100:.1f}%")
    print(f"  Non-Friday n={m_non['n']:>3d}  mean {m_non['mean']:+.3f}%  Sh {m_non['sh']:+.2f}  WR {m_non['wr']*100:.1f}%")
    delta = m_fri["mean"] - m_non["mean"]
    print(f"  delta (Fri - non-Fri) mean: {delta:+.3f}%  (large negative -> NFP-style Fri drag dilutes signal)")


# ---------- main ----------

def main() -> None:
    section("PRE-PCE DRIFT (NDX100) -- Phase 2  (direction TBD per #54, mech-aware KCs per #55)")
    print(f"Calendar: {CAL_PATH}")
    print(f"M5 data:  {NDX_M5_PATH}")
    print(f"Window:   {WINDOW_HOURS}h entry / {EXIT_BUFFER_MIN}min exit buffer")
    print(f"Cost:     {COST_BPS_DEFAULT} bp RT default")

    cal = load_calendar(historical_only=True)
    df = load_m5(NDX_M5_PATH)
    print(f"\nLoaded {len(cal)} historical PCE events ({cal['date'].min().date()} -> {cal['date'].max().date()})")
    print(f"Loaded {len(df)} NDX100 M5 bars ({df['timestamp'].min().date()} -> {df['timestamp'].max().date()})")

    section("BASELINE -- 24h, both directions, 5bp RT")
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

    section(f"FRIDAY-vs-NON-FRIDAY SUBSET ({best_dir.upper()}) -- per red-flag #4")
    friday_subset_diagnostic(best_trades)

    section(f"PLACEBO -- non-PCE weekdays at 08:30 ET ({best_dir.upper()})")
    placebo = placebo_check(df, cal, direction=best_dir)
    placebo_opp = placebo_check(df, cal, direction=("short" if best_dir == "long" else "long"))

    section(f"WALK-FORWARD (3 IS/OOS splits, {best_dir.upper()})")
    wf = walk_forward(df, cal, direction=best_dir)
    print(f"  {'split':<42s} {'IS n':>5s} {'IS Sh':>7s} {'IS mean':>9s}   {'OOS n':>5s} {'OOS Sh':>7s} {'OOS mean':>9s}")
    for r in wf:
        print(f"  {r['split']:<42s} {r['is_n']:>5d} {r['is_sh']:>+7.2f} {r['is_mean']:>+8.3f}%   {r['oos_n']:>5d} {r['oos_sh']:>+7.2f} {r['oos_mean']:>+8.3f}%")
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

    section(f"WINDOW SWEEP (5bp RT, {best_dir.upper()})")
    print(f"  {'window_h':>8s} {'buffer_min':>10s} {'n':>4s} {'mean':>9s} {'Sh':>7s}")
    for wh in WINDOW_HOURS_SWEEP:
        for eb in EXIT_BUFFER_SWEEP:
            t = compute_event_returns(df, cal, window_hours=wh, exit_buffer_min=eb, direction=best_dir)
            m = event_metrics(t)
            print(f"  {wh:>8d} {eb:>10d} {m['n']:>4d} {m['mean']:>+8.3f}% {m['sh']:>+7.2f}")

    section(f"KILL-CHECK SUMMARY (best direction = {best_dir.upper()}, 24h, 5bp)")
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
        print(f"  PASS -- pre-PCE {best_dir.upper()} on NDX100 validated; framework corroboration (lesson #56) confirmed")
    elif (best_m["mean"] > 0.05) and null_ok and not all_basic:
        print(f"  MARGINAL -- mechanism present ({best_dir.upper()}) but not deploy-grade")
    else:
        print("  REJECT -- tombstone; PCE does not survive pre-commits -- weakens CPI generalisation framing")
    print()


if __name__ == "__main__":
    main()
