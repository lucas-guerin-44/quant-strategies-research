#!/usr/bin/env python3
"""
Gold trend following (XAUUSD TSMOM) -- Phase 2 demo (iteration 2).

Thesis: experiments/gold_trend/gold_trend.md

Iteration 2 changes vs v1:
  * Multi-horizon signal: average of sign(r_1M), sign(r_3M), sign(r_12M).
    Signal now takes values in {-1, -2/3, -1/3, 0, 1/3, 2/3, 1}. Natural
    sizing-via-signal-strength is already baked in.
  * Optional Turtle-style pyramid: enter at 1/K of full vol-target, add 1/K
    after each +ATR_MULT * ATR(14) favorable move, cap at full target.
    Exit everything on signal flip or flat. Keeps total risk budget constant.

Variants:
  1. MH-LO                 -- multi-horizon long-only, no pyramid
  2. MH-LO-Pyramid         -- MH-LO with sizing-in
  3. MH-LS                 -- multi-horizon long/short, no pyramid
  4. MH-LS-Pyramid         -- MH-LS with sizing-in
  5. Buy & hold XAUUSD     -- passive reference
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
sys.path.insert(0, _HERE)

from data import fetch_ohlc


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SYMBOL = "XAUUSD"
TIMEFRAME = "D1"
START_DATE = "2015-01-01"
END_DATE = "2026-04-18"

LOOKBACKS = (21, 63, 252)   # 1M, 3M, 12M -- multi-horizon MOP (2012)
REBAL_BARS = 21
VOL_LOOKBACK = 60
VOL_TARGET_ANN = 0.15
GROSS_CAP = 1.0
COST_BPS_PER_SIDE = 5.0
BARS_PER_YEAR = 252

# Pyramid params
PYRAMID_STEPS = 3          # K: enter at 1/K, add 1/K per favorable +ATR move
PYRAMID_ATR_MULT = 1.0     # add a step per +1 ATR(14) favorable move since last step
ATR_LOOKBACK = 14


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f"\n{'=' * 80}\n  {t}\n{'=' * 80}\n")


def load_series(sym: str) -> pd.DataFrame | None:
    try:
        raw = fetch_ohlc(sym, TIMEFRAME, START_DATE, END_DATE)
    except Exception as e:
        print(f"  {sym}: LOAD FAILED ({e})")
        return None
    if raw is None or raw.empty:
        return None
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def max_drawdown(e: np.ndarray) -> float:
    rm = np.maximum.accumulate(e)
    dd = (e - rm) / rm
    return float(dd.min())


def annualized_sharpe(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    nz = np.flatnonzero(r)
    if nz.size == 0:
        return 0.0
    r = r[nz[0]:]
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(BARS_PER_YEAR))


def report_block(label: str, rets: pd.Series) -> None:
    if len(rets) < 5:
        print(f"  {label:<22s} (no data)")
        return
    r = rets.to_numpy()
    eq = (1.0 + rets).cumprod().to_numpy()
    years = (rets.index[-1] - rets.index[0]).days / 365.25
    total = eq[-1] / eq[0] - 1.0
    cagr = (eq[-1] / eq[0]) ** (1.0 / max(years, 1e-9)) - 1.0
    shrp = annualized_sharpe(r)
    mdd = max_drawdown(eq)
    calmar = cagr / abs(mdd) if mdd != 0 else 0.0
    worst_day = float(np.min(r))
    print(
        f"  {label:<22s} "
        f"ret {total * 100:>+8.2f}%  "
        f"CAGR {cagr * 100:>+7.2f}%  "
        f"Sharpe {shrp:>+6.2f}  "
        f"MDD {mdd * 100:>+7.2f}%  "
        f"Calmar {calmar:>+6.2f}  "
        f"worst-day {worst_day * 100:>+7.2f}%"
    )


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def multi_horizon_signal(close: pd.Series, lookbacks: tuple[int, ...]) -> pd.Series:
    """Mean of sign(past-return over lb) across all lookbacks. In [-1, 1]."""
    subs = [np.sign(close.pct_change(lb)).fillna(0.0) for lb in lookbacks]
    return pd.concat(subs, axis=1).mean(axis=1)


def atr_series(high: pd.Series, low: pd.Series, close: pd.Series, n: int = ATR_LOOKBACK) -> pd.Series:
    """Simple mean of true range over n bars."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=max(2, n // 2)).mean()


# ---------------------------------------------------------------------------
# Simulators
# ---------------------------------------------------------------------------

def simulate_tsmom(
    close: pd.Series,
    signal: pd.Series,
    realized_vol: pd.Series,
    label: str,
    long_only: bool,
    cost_bps_per_side: float = COST_BPS_PER_SIDE,
) -> tuple[pd.Series, dict]:
    """Classic vol-targeted TSMOM on a single instrument. No pyramid.

    target_weight = signal * min(VOL_TARGET_ANN / realized_vol, GROSS_CAP)
    Rebalance every REBAL_BARS.
    """
    idx = close.index
    ret = close.pct_change().fillna(0.0)
    sig = signal.clip(lower=0.0) if long_only else signal

    first_rebal = max(LOOKBACKS)
    n = len(idx)
    w = np.zeros(n)
    cur = 0.0
    last = 0.0
    trades = 0

    for t in range(n):
        if t < first_rebal:
            continue
        is_rebal = (t - first_rebal) % REBAL_BARS == 0
        if is_rebal:
            s = sig.iloc[t - 1]
            rv = realized_vol.iloc[t - 1]
            if np.isfinite(s) and np.isfinite(rv) and rv > 1e-6:
                vol_scale = min(VOL_TARGET_ANN / rv, GROSS_CAP)
                cur = float(s) * vol_scale
            else:
                cur = 0.0
            if abs(cur - last) > 1e-6:
                trades += 1
            last = cur
        w[t] = cur

    gross = w * ret.to_numpy()
    dw = np.abs(np.diff(w, prepend=0.0))
    costs = dw * (cost_bps_per_side * 1e-4)
    net = pd.Series(gross - costs, index=idx, name=label)
    stats = _summarize_weights(label, w, trades)
    stats.update({"w": w.copy(), "ret": ret.to_numpy().copy(), "costs": costs.copy(),
                  "cost_bps_per_side": cost_bps_per_side})
    return net, stats


def simulate_tsmom_pyramid(
    close: pd.Series,
    signal: pd.Series,
    realized_vol: pd.Series,
    atr: pd.Series,
    label: str,
    long_only: bool,
    steps: int = PYRAMID_STEPS,
    atr_mult: float = PYRAMID_ATR_MULT,
    max_units: int | None = None,
    cost_bps_per_side: float = COST_BPS_PER_SIDE,
) -> tuple[pd.Series, dict]:
    """Turtle-style pyramid on top of multi-horizon TSMOM.

    Unit size = 1/steps * full_vol_target. Cap at max_units units.
    If ``max_units == steps`` (default), cap = full_vol_target (path control only).
    If ``max_units > steps``, the pyramid LEVERS ABOVE vol-target on proven trends
    (e.g. steps=3, max_units=5 -> caps at 5/3 = 1.67x vol-target).

      * On signal turning directional with no position: enter at 1 unit.
      * On each subsequent rebalance, if signal still agrees AND price has moved
        favorably by >= atr_mult * ATR since the last increment, add 1 unit.
        Cap at max_units.
      * On signal going flat or flipping: close fully (pyramid re-starts from 0
        on any re-entry).

    NOTE: uses sign of the multi-horizon signal to pick direction, not its
    magnitude. Sizing-via-signal-strength and pyramid sizing are mutually
    exclusive in this variant.
    """
    if max_units is None:
        max_units = steps
    idx = close.index
    ret = close.pct_change().fillna(0.0)
    c_arr = close.to_numpy()
    atr_arr = atr.to_numpy()
    sig = signal.clip(lower=0.0) if long_only else signal

    first_rebal = max(LOOKBACKS)
    n = len(idx)
    w = np.zeros(n)
    cur = 0.0
    last = 0.0
    trades = 0
    cur_side = 0             # +1, -1, or 0
    units = 0                # current number of pyramid units in [0, steps]
    full_target = 0.0        # weight magnitude if all units filled
    last_inc_price = np.nan
    last_inc_atr = np.nan

    for t in range(n):
        if t < first_rebal:
            continue
        is_rebal = (t - first_rebal) % REBAL_BARS == 0
        if is_rebal:
            s = sig.iloc[t - 1]
            rv = realized_vol.iloc[t - 1]
            side_new = int(np.sign(s)) if np.isfinite(s) else 0

            # Determine full-size target magnitude for this rebalance.
            if np.isfinite(rv) and rv > 1e-6:
                vol_scale = min(VOL_TARGET_ANN / rv, GROSS_CAP)
            else:
                vol_scale = 0.0

            price_t = c_arr[t - 1]
            atr_t = atr_arr[t - 1]

            if side_new == 0 or vol_scale <= 0.0:
                # Flat or no size -> close everything.
                cur = 0.0
                cur_side = 0
                units = 0
                full_target = 0.0
                last_inc_price = np.nan
                last_inc_atr = np.nan
            elif side_new != cur_side:
                # New direction (or first entry). Reset pyramid, enter 1 unit.
                cur_side = side_new
                full_target = vol_scale  # positive magnitude
                units = 1
                cur = cur_side * full_target * (units / steps)
                last_inc_price = price_t
                last_inc_atr = atr_t
            else:
                # Same direction, position already open. Refresh full_target to
                # current vol_scale (vol-target drift), then try to pyramid up.
                full_target = vol_scale
                if units < max_units and np.isfinite(last_inc_price) and np.isfinite(last_inc_atr) and last_inc_atr > 0:
                    favorable = cur_side * (price_t - last_inc_price)
                    if favorable >= atr_mult * last_inc_atr:
                        units += 1
                        last_inc_price = price_t
                        last_inc_atr = atr_t
                cur = cur_side * full_target * (units / steps)

            if abs(cur - last) > 1e-6:
                trades += 1
            last = cur
        w[t] = cur

    gross = w * ret.to_numpy()
    dw = np.abs(np.diff(w, prepend=0.0))
    costs = dw * (cost_bps_per_side * 1e-4)
    net = pd.Series(gross - costs, index=idx, name=label)
    stats = _summarize_weights(label, w, trades)
    stats.update({"w": w.copy(), "ret": ret.to_numpy().copy(), "costs": costs.copy(),
                  "cost_bps_per_side": cost_bps_per_side})
    return net, stats


def _summarize_weights(label: str, w: np.ndarray, trades: int) -> dict:
    return {
        "label": label,
        "trades": trades,
        "frac_long": float(np.mean(w > 0)),
        "frac_short": float(np.mean(w < 0)),
        "frac_flat": float(np.mean(np.isclose(w, 0.0))),
        "avg_gross_exposure": float(np.mean(np.abs(w))),
        "max_gross_exposure": float(np.max(np.abs(w))),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section(f"Loading {SYMBOL}")
    df = load_series(SYMBOL)
    if df is None:
        print(f"Missing {SYMBOL} data; abort.")
        return 1
    print(f"  {SYMBOL:<8s} {len(df):>5,} bars  "
          f"{df.index[0].date()} -> {df.index[-1].date()}  "
          f"last={df['close'].iloc[-1]:.2f}")

    close = df["close"]
    high = df["high"]
    low = df["low"]
    ret = close.pct_change().fillna(0.0)
    realized_vol = ret.rolling(VOL_LOOKBACK, min_periods=VOL_LOOKBACK // 2).std(ddof=1) * np.sqrt(BARS_PER_YEAR)
    realized_vol = realized_vol.shift(1)
    signal = multi_horizon_signal(close, LOOKBACKS)
    atr = atr_series(high, low, close)

    section("Strategy variants")
    mh_lo_ret, mh_lo_stats = simulate_tsmom(close, signal, realized_vol, "MH-LO", long_only=True)
    mh_ls_ret, mh_ls_stats = simulate_tsmom(close, signal, realized_vol, "MH-LS", long_only=False)
    mh_lo_p_ret, mh_lo_p_stats = simulate_tsmom_pyramid(
        close, signal, realized_vol, atr, "MH-LO-P", long_only=True,
    )
    mh_ls_p_ret, mh_ls_p_stats = simulate_tsmom_pyramid(
        close, signal, realized_vol, atr, "MH-LS-P", long_only=False,
    )
    # Direction null check (CLAUDE.md convention): same mechanism, flipped signal.
    # If the inverted signal also makes money, the result is just gold beta,
    # not a directional edge.
    null_lo_ret, null_lo_stats = simulate_tsmom(close, -signal, realized_vol, "NULL-LO", long_only=True)
    null_ls_ret, null_ls_stats = simulate_tsmom(close, -signal, realized_vol, "NULL-LS", long_only=False)
    bh_ret = ret.rename("XAU-buyhold")

    print(f"  {'variant':<22s} {'trades':>7s} {'frac-long':>11s} {'frac-short':>12s} "
          f"{'frac-flat':>11s} {'avg-|w|':>9s} {'max-|w|':>9s}")
    for s in (mh_lo_stats, mh_lo_p_stats, mh_ls_stats, mh_ls_p_stats, null_lo_stats, null_ls_stats):
        print(f"  {s['label']:<22s} {s['trades']:>7d} "
              f"{s['frac_long'] * 100:>10.1f}% {s['frac_short'] * 100:>11.1f}% "
              f"{s['frac_flat'] * 100:>10.1f}% {s['avg_gross_exposure']:>9.3f} "
              f"{s['max_gross_exposure']:>9.3f}")

    section("Performance summary (full period)")
    print(f"  {'variant':<22s} {'ret':>10s}  {'CAGR':>8s}  {'Sharpe':>7s}  "
          f"{'MDD':>8s}  {'Calmar':>7s}  {'worst-day':>10s}")
    report_block("MH long-only",        mh_lo_ret)
    report_block("MH long-only + pyra", mh_lo_p_ret)
    report_block("MH long/short",       mh_ls_ret)
    report_block("MH long/short + pyra", mh_ls_p_ret)
    report_block("NULL long-only (-sig)", null_lo_ret)
    report_block("NULL long/short (-sig)", null_ls_ret)
    report_block("XAU buy & hold",      bh_ret)

    # ----- Pyramid sensitivity sweep (on MH-LO, best variant) ------------
    section("Pyramid sweep: steps x atr_mult x max_units (MH long-only)")
    print(f"  {'config':<32s} {'trades':>7s} {'avg-|w|':>8s} {'max-|w|':>8s}  "
          f"{'CAGR':>8s}  {'Sharpe':>7s}  {'MDD':>8s}")
    sweep_configs = [
        # (steps, atr_mult, max_units)  -- label auto-derived
        (3, 1.0, 3),   # baseline (path-only, 1x cap)
        (3, 0.5, 3),   # add faster
        (3, 2.0, 3),   # require more proof
        (5, 1.0, 5),   # finer path, 1x cap
        (3, 1.0, 4),   # lever to 1.33x on proven trend
        (3, 1.0, 5),   # lever to 1.67x
        (3, 1.0, 6),   # lever to 2.0x
        (3, 0.5, 6),   # fast pyramid, 2x cap
        (3, 2.0, 6),   # slow pyramid, 2x cap
    ]
    for steps, amul, maxu in sweep_configs:
        cap_mult = maxu / steps
        lbl = f"K={steps} atr={amul:.1f} cap={cap_mult:.2f}x"
        sr, ss = simulate_tsmom_pyramid(
            close, signal, realized_vol, atr, lbl,
            long_only=True, steps=steps, atr_mult=amul, max_units=maxu,
        )
        eq = (1.0 + sr).cumprod()
        years = (sr.index[-1] - sr.index[0]).days / 365.25
        cagr = (float(eq.iloc[-1])) ** (1 / max(years, 1e-9)) - 1
        sh = annualized_sharpe(sr.to_numpy())
        mdd = max_drawdown(eq.to_numpy())
        print(f"  {lbl:<32s} {ss['trades']:>7d} "
              f"{ss['avg_gross_exposure']:>8.3f} {ss['max_gross_exposure']:>8.3f}  "
              f"{cagr * 100:>+7.2f}%  {sh:>+6.2f}  {mdd * 100:>+7.2f}%")

    # ----- Regime breakdown ---------------------------------------------
    section("Regime sub-periods (per variant)")
    windows = [
        ("2015-2017",         "2015-01-01", "2017-12-31"),
        ("2018-2019",         "2018-01-01", "2019-12-31"),
        ("2020-2021",         "2020-01-01", "2021-12-31"),
        ("2022",              "2022-01-01", "2022-12-31"),
        ("2023-2026 holdout", "2023-01-01", "2026-12-31"),
    ]
    for lbl, r in (("MH long-only", mh_lo_ret),
                   ("MH long-only + pyra", mh_lo_p_ret),
                   ("MH long/short", mh_ls_ret),
                   ("MH long/short + pyra", mh_ls_p_ret),
                   ("NULL long-only (-sig)", null_lo_ret),
                   ("NULL long/short (-sig)", null_ls_ret)):
        print(f"\n  -- {lbl} --")
        for wl, s, e in windows:
            report_block(wl, r.loc[s:e])

    # ----- Phase 2 kill-criteria check ----------------------------------
    section("Phase 2 kill-criteria check")
    def check(label: str, rets: pd.Series, n_trades: int) -> None:
        eq = (1.0 + rets).cumprod()
        sh = annualized_sharpe(rets.to_numpy())
        mdd = max_drawdown(eq.to_numpy())
        total = float(eq.iloc[-1] - 1.0)
        def v(c: bool) -> str: return "PASS" if c else "FAIL"
        print(f"  [{label}]")
        print(f"    Sharpe > 0.30           : {v(sh > 0.30)}  (actual {sh:+.2f})")
        print(f"    Max DD < 30%            : {v(abs(mdd) < 0.30)}  (actual {mdd * 100:+.2f}%)")
        print(f"    Trades >= 50            : {v(n_trades >= 50)}  (actual {n_trades})")
        print(f"    Total return > 0        : {v(total > 0)}  (actual {total * 100:+.2f}%)")
    check("MH long-only",          mh_lo_ret,   mh_lo_stats['trades'])
    check("MH long-only + pyramid", mh_lo_p_ret, mh_lo_p_stats['trades'])
    check("MH long/short",         mh_ls_ret,   mh_ls_stats['trades'])
    check("MH long/short + pyramid", mh_ls_p_ret, mh_ls_p_stats['trades'])

    # ----- Direction null check + B&H dominance check -----------------------
    section("Direction null check + B&H dominance")
    bh_sh = annualized_sharpe(bh_ret.to_numpy())
    def fade_gap(label: str, sig_ret: pd.Series, null_ret: pd.Series) -> None:
        sh_sig = annualized_sharpe(sig_ret.to_numpy())
        sh_null = annualized_sharpe(null_ret.to_numpy())
        gap = sh_sig - sh_null
        beats_bh = sh_sig > bh_sh
        def v(c: bool) -> str: return "PASS" if c else "FAIL"
        print(f"  [{label}]")
        print(f"    Sharpe vs -signal null  : sig {sh_sig:+.2f} vs null {sh_null:+.2f} -> gap {gap:+.2f}  ({v(gap > 0.30)})")
        print(f"    Beats XAU buy-and-hold  : {v(beats_bh)}  (sig {sh_sig:+.2f} vs B&H {bh_sh:+.2f})")
    fade_gap("MH long-only",   mh_lo_ret, null_lo_ret)
    fade_gap("MH long/short",  mh_ls_ret, null_ls_ret)

    # ----- Summary ------------------------------------------------------
    section("Summary")
    for lbl, r, s in (("MH long-only",           mh_lo_ret,   mh_lo_stats),
                      ("MH long-only + pyra",    mh_lo_p_ret, mh_lo_p_stats),
                      ("MH long/short",          mh_ls_ret,   mh_ls_stats),
                      ("MH long/short + pyra",   mh_ls_p_ret, mh_ls_p_stats),
                      ("NULL long-only (-sig)",  null_lo_ret, null_lo_stats),
                      ("NULL long/short (-sig)", null_ls_ret, null_ls_stats)):
        eq = (1.0 + r).cumprod()
        years = (r.index[-1] - r.index[0]).days / 365.25
        total = float(eq.iloc[-1] - 1.0)
        cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
        sh = annualized_sharpe(r.to_numpy())
        mdd = max_drawdown(eq.to_numpy())
        print(f"  {lbl:<24s} CAGR {cagr * 100:+.2f}%  Sharpe {sh:+.2f}  "
              f"MDD {mdd * 100:+.2f}%  trades {s['trades']}")
    bh_eq = (1.0 + bh_ret).cumprod()
    years = (bh_ret.index[-1] - bh_ret.index[0]).days / 365.25
    bh_total = float(bh_eq.iloc[-1] - 1.0)
    bh_cagr = (1 + bh_total) ** (1 / max(years, 1e-9)) - 1
    print(f"  {'XAU buy & hold':<24s} CAGR {bh_cagr * 100:+.2f}%  "
          f"Sharpe {annualized_sharpe(bh_ret.to_numpy()):+.2f}  "
          f"MDD {max_drawdown(bh_eq.to_numpy()) * 100:+.2f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
