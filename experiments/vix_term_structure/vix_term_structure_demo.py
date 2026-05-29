#!/usr/bin/env python3
"""
VIX term-structure roll (short-vol VRP) — Phase 2 minimum-viable demo.

Thesis: VX futures are in contango most of the time; shorting them (or
holding an inverse-VXX ETP like SVXY) harvests the variance risk premium.
When the curve flips to backwardation, the roll reverses and the strategy
must flatten.

Signal: ts_ratio = VIX / VIX3M.
  ts_ratio < 0.95 -> long SVXY (short-vol exposure)
  ts_ratio > 1.00 -> flat
  otherwise       -> hold previous position (hysteresis band)

Traded instrument: SVXY (daily). Note SVXY re-leveraged from -1x to -0.5x on
2018-02-27 after XIV blow-up. We run on the raw SVXY price series so the
Feb-2018 Volmageddon event is naturally in-sample — the contango filter
either catches it or it doesn't.

Position sizing: vol-target 15% annualized using 60-day realized vol on
SVXY, gross capped at 1.0x equity.

Costs: 10 bps commission + 5 bps slippage per side, charged on |delta w|.

Execution: signal uses ts_ratio at close of day t-1, position applied to
day-t return. Realistic — no look-ahead.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)  # research repo root
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))  # engine
sys.path.insert(0, _HERE)  # this strategy's directory

from data import fetch_ohlc


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TIMEFRAME = "D1"
START_DATE = "2015-01-01"
END_DATE = "2026-04-18"

# Signal bounds (hysteresis band).
CONTANGO_ENTRY = 0.95   # below this -> go long SVXY
BACKWARDATION_EXIT = 0.98  # above this -> flat (tightened from 1.00 after Phase-2 baseline)

# Sizing.
VOL_TARGET_ANN = 0.15
VOL_LOOKBACK = 60
GROSS_CAP = 1.0
BARS_PER_YEAR = 252
REBAL_BARS = 5   # weekly vol-target refresh; state-change flips are still instant

# Costs on |delta weight|.
COST_BPS_PER_SIDE = 15.0   # 10 bps commission + 5 bps slippage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'=' * 80}\n  {title}\n{'=' * 80}\n")


def load_series(symbol: str) -> pd.DataFrame | None:
    try:
        raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    except Exception as e:
        print(f"  {symbol:<8s} LOAD FAILED ({e})")
        return None
    if raw is None or raw.empty:
        print(f"  {symbol:<8s} no bars")
        return None
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def max_drawdown(equity: np.ndarray) -> float:
    running_max = np.maximum.accumulate(equity)
    dd = (equity - running_max) / running_max
    return float(dd.min())


def annualized_sharpe(daily_returns: np.ndarray) -> float:
    r = daily_returns[np.isfinite(daily_returns)]
    nz = np.flatnonzero(r)
    if nz.size == 0:
        return 0.0
    r = r[nz[0]:]
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(BARS_PER_YEAR))


def report_block(label: str, rets: pd.Series, equity: pd.Series) -> None:
    r = rets.to_numpy()
    e = equity.to_numpy()
    if len(r) == 0 or len(e) == 0:
        print(f"  {label:<20s} (empty)")
        return
    years = (rets.index[-1] - rets.index[0]).days / 365.25
    total = e[-1] / e[0] - 1.0
    cagr = (e[-1] / e[0]) ** (1.0 / max(years, 1e-9)) - 1.0
    shrp = annualized_sharpe(r)
    mdd = max_drawdown(e)
    calmar = cagr / abs(mdd) if mdd != 0 else 0.0
    worst_day = float(np.min(r))
    # Worst 5-day rolling return.
    if len(r) >= 5:
        rolling5 = pd.Series(r).rolling(5).apply(lambda x: np.prod(1 + x) - 1.0, raw=True)
        worst_week = float(rolling5.min())
    else:
        worst_week = float('nan')
    print(
        f"  {label:<20s} "
        f"ret {total * 100:>+8.2f}%  "
        f"CAGR {cagr * 100:>+7.2f}%  "
        f"Sharpe {shrp:>+6.2f}  "
        f"MDD {mdd * 100:>+7.2f}%  "
        f"Calmar {calmar:>+6.2f}  "
        f"worst-day {worst_day * 100:>+7.2f}%  "
        f"worst-5d {worst_week * 100:>+7.2f}%"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section("Loading data")
    vix = load_series("VIX")
    vix3m = load_series("VIX3M")
    svxy = load_series("SVXY")
    if vix is None or vix3m is None or svxy is None:
        print("FATAL: missing one or more series.")
        return 1
    for name, df in (("VIX", vix), ("VIX3M", vix3m), ("SVXY", svxy)):
        print(f"  {name:<6s} {len(df):>5,} bars  "
              f"{df.index[0].date()} -> {df.index[-1].date()}")

    # Align on common business-day index (intersection).
    idx = vix.index.intersection(vix3m.index).intersection(svxy.index)
    idx = idx.sort_values()
    print(f"\n  Common index: {len(idx):,} bars  "
          f"{idx[0].date()} -> {idx[-1].date()}")

    vix_c = vix["close"].reindex(idx)
    vix3m_c = vix3m["close"].reindex(idx)
    svxy_c = svxy["close"].reindex(idx)

    # Drop any residual NaNs (e.g. partial days).
    panel = pd.DataFrame({"vix": vix_c, "vix3m": vix3m_c, "svxy": svxy_c}).dropna()
    idx = panel.index
    vix_c = panel["vix"]
    vix3m_c = panel["vix3m"]
    svxy_c = panel["svxy"]
    print(f"  After dropna: {len(idx):,} bars")

    # ------------------------------------------------------------------
    # Signal: ts_ratio = VIX / VIX3M with hysteresis state machine.
    # target position in {0, 1} (long SVXY or flat).
    # ------------------------------------------------------------------
    section("Signal construction")
    ts_ratio = (vix_c / vix3m_c).astype(float)
    target = pd.Series(0, index=idx, dtype=int)
    state = 0
    for t in range(len(idx)):
        r = ts_ratio.iloc[t]
        if not np.isfinite(r):
            target.iloc[t] = state
            continue
        if r < CONTANGO_ENTRY:
            state = 1
        elif r > BACKWARDATION_EXIT:
            state = 0
        # else: hold prior state (hysteresis)
        target.iloc[t] = state

    frac_long = float((target == 1).mean())
    frac_flat = float((target == 0).mean())
    print(f"  Fraction days targeting long : {frac_long * 100:.2f}%")
    print(f"  Fraction days targeting flat : {frac_flat * 100:.2f}%")
    # Breakdown of ts_ratio distribution.
    print(f"  ts_ratio quantiles (all days): "
          f"p05={ts_ratio.quantile(0.05):.3f}  "
          f"p25={ts_ratio.quantile(0.25):.3f}  "
          f"p50={ts_ratio.quantile(0.50):.3f}  "
          f"p75={ts_ratio.quantile(0.75):.3f}  "
          f"p95={ts_ratio.quantile(0.95):.3f}")

    # ------------------------------------------------------------------
    # Position sizing: vol-target from 60-day realized vol of SVXY.
    # Lagged one bar (use t-1 vol to size t position).
    # ------------------------------------------------------------------
    svxy_ret = svxy_c.pct_change().fillna(0.0)
    realized_vol = svxy_ret.rolling(VOL_LOOKBACK, min_periods=VOL_LOOKBACK // 2).std(ddof=1) * np.sqrt(BARS_PER_YEAR)
    realized_vol = realized_vol.shift(1)  # no look-ahead

    # ------------------------------------------------------------------
    # Build daily weight series with t-1 signal and t-1 vol.
    #
    # Rebalance policy: hold weight constant between scheduled rebalances
    # (every REBAL_BARS bars) UNLESS the target state flips, in which case
    # act immediately. This keeps the Feb-2018 filter reaction time but
    # cuts the daily vol-target sizing churn.
    # ------------------------------------------------------------------
    target_lag = target.shift(1).fillna(0).astype(int)
    scale = (VOL_TARGET_ANN / realized_vol).clip(upper=GROSS_CAP).fillna(0.0)
    scale = scale.where(np.isfinite(scale), 0.0)
    desired_weight = (target_lag.astype(float) * scale)

    weight = pd.Series(0.0, index=idx)
    cur_w = 0.0
    prev_target = 0
    bars_since = REBAL_BARS  # force rebalance on first bar
    for t in range(len(idx)):
        tgt = int(target_lag.iloc[t])
        desired = float(desired_weight.iloc[t])
        if not np.isfinite(desired):
            desired = 0.0
        state_changed = (tgt != prev_target)
        if state_changed or bars_since >= REBAL_BARS:
            cur_w = desired
            bars_since = 0
        else:
            bars_since += 1
        weight.iloc[t] = cur_w
        prev_target = tgt
    weight = weight.rename("weight")

    # ------------------------------------------------------------------
    # P&L: r_t = weight_t * svxy_ret_t - cost_t
    # cost_t = |weight_t - weight_{t-1}| * cost_per_side
    # ------------------------------------------------------------------
    dweight = weight.diff().abs().fillna(weight.abs())  # first non-zero also counts as a trade
    cost_per_side = COST_BPS_PER_SIDE * 1e-4
    costs = dweight * cost_per_side

    gross_ret = weight * svxy_ret
    net_ret = (gross_ret - costs).astype(float)

    equity = (1.0 + net_ret).cumprod()
    equity.iloc[0] = 1.0  # ensure clean start

    # ------------------------------------------------------------------
    # Overall metrics.
    # ------------------------------------------------------------------
    section("Overall performance (2015 -> 2026)")
    report_block("Full period", net_ret, equity)

    n_trades = int((dweight > 1e-8).sum())
    print(f"\n  Trades (|dw|>0)   : {n_trades:,}")
    print(f"  Avg gross weight  : {weight.abs().mean():.3f}  "
          f"(when long: {weight[weight > 0].mean() if (weight > 0).any() else 0.0:.3f})")
    print(f"  Turnover sum      : {dweight.sum():.2f}  "
          f"(cost drag total: {costs.sum() * 100:.2f}%)")

    # ------------------------------------------------------------------
    # Regime sub-periods.
    # ------------------------------------------------------------------
    section("Regime sub-periods")
    windows = [
        ("2015-2017 (calm)",  "2015-01-01", "2017-12-31"),
        ("2018 (Volmaggdn)",  "2018-01-01", "2018-12-31"),
        ("2019-2021",         "2019-01-01", "2021-12-31"),
        ("2022-2023 (bear)",  "2022-01-01", "2023-12-31"),
        ("2024-2026 (recent)","2024-01-01", "2026-12-31"),
    ]
    print(f"  {'window':<22s} "
          f"{'ret':>10s}  {'CAGR':>8s}  {'Sharpe':>7s}  "
          f"{'MDD':>8s}  {'Calmar':>7s}  {'worst-day':>10s}  {'worst-5d':>10s}")
    for label, s, e in windows:
        sub = net_ret.loc[s:e]
        if len(sub) < 10:
            print(f"  {label:<22s} (no data)")
            continue
        sub_eq = (1.0 + sub).cumprod()
        report_block(label, sub, sub_eq)

    # ------------------------------------------------------------------
    # Phase 2 kill-criteria check (from vix_term_structure.md).
    # ------------------------------------------------------------------
    section("Phase 2 kill-criteria check")
    full_sharpe = annualized_sharpe(net_ret.to_numpy())
    full_mdd = max_drawdown(equity.to_numpy())
    worst_day = float(net_ret.min())

    def verdict(cond: bool, pass_str: str = "PASS", fail_str: str = "FAIL") -> str:
        return pass_str if cond else fail_str

    print(f"  Sharpe > 0.30              : {verdict(full_sharpe > 0.30)}  (actual {full_sharpe:+.2f})")
    print(f"  Max DD < 40%               : {verdict(abs(full_mdd) < 0.40)}  (actual {full_mdd * 100:+.2f}%)")
    print(f"  No single-day loss > 15%   : {verdict(worst_day > -0.15)}  (actual {worst_day * 100:+.2f}%)")
    print(f"  Trades >= 50               : {verdict(n_trades >= 50)}  (actual {n_trades})")

    # ------------------------------------------------------------------
    # Drill-down: Feb 2018 specifically (the Volmageddon window).
    # ------------------------------------------------------------------
    section("Feb 2018 drill-down (was the filter fast enough?)")
    feb_idx = (idx >= "2018-01-15") & (idx <= "2018-02-15")
    feb_dates = idx[feb_idx]
    if len(feb_dates) > 0:
        print(f"  {'date':<12s} {'VIX':>7s} {'VIX3M':>7s} {'ratio':>7s} "
              f"{'target':>7s} {'weight':>7s} {'svxy':>9s} {'day_ret':>9s}")
        for d in feb_dates:
            print(f"  {d.date().isoformat():<12s} "
                  f"{vix_c.loc[d]:>7.2f} "
                  f"{vix3m_c.loc[d]:>7.2f} "
                  f"{ts_ratio.loc[d]:>7.3f} "
                  f"{target.loc[d]:>7d} "
                  f"{weight.loc[d]:>7.3f} "
                  f"{svxy_c.loc[d]:>9.2f} "
                  f"{net_ret.loc[d] * 100:>+8.2f}%")
    else:
        print("  (no data in range)")

    section("Summary")
    print(f"  Full-period Sharpe : {full_sharpe:+.2f}")
    print(f"  Full-period MDD    : {full_mdd * 100:+.2f}%")
    print(f"  Worst single day   : {worst_day * 100:+.2f}%")
    print(f"  # regime changes   : {int((target.diff().abs() > 0).sum())}")
    print()
    print("  Next: if Phase 2 passes, wire compute_statistical_report (Phase 3),")
    print("  then regime-split check (Phase 4 — but our kill-criteria above cover")
    print("  the worst period already). Param sweep on thresholds is Phase 5.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
