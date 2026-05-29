#!/usr/bin/env python3
"""
Treasury trend (rates-only TSMOM on TLT / IEF) -- Phase 2 demo.

Thesis: experiments/treasury_trend/treasury_trend.md

Signal: 252-day total-return sign per ETF.
  r_12m > 0  -> long ETF, vol-targeted (10% ann)
  r_12m <= 0 -> flat in BIL (T-bill cash return)
Rebalance monthly (21 bars).
Costs: 6 bps roundtrip (3 per side).

Runs three variants:
  1. TLT-only
  2. IEF-only
  3. 50/50 TLT+IEF blend, monthly-rebalanced

Plus a "buy-and-hold TLT" reference and a "BIL-only" (cash) reference to
sanity-check the filter is adding value vs the static alternatives.
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
sys.path.insert(0, os.path.join(_EXPERIMENTS, 'xs_momentum'))  # for XS-mom correlation import

from data import fetch_ohlc


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

START_DATE = "2015-01-01"
END_DATE = "2026-04-18"
TIMEFRAME = "D1"

LOOKBACK_BARS = 252         # 12M TSMOM (single-horizon variant)
MULTI_LOOKBACKS = (21, 63, 252)  # 1M + 3M + 12M per Moskowitz/Ooi/Pedersen (2012)
REBAL_BARS = 21             # monthly
VOL_LOOKBACK = 60
VOL_TARGET_ANN = 0.10       # 10% ann when long (conservative for bonds)
GROSS_CAP = 1.0
COST_BPS_PER_SIDE = 3.0     # ETF: 1bp commission + 2bp spread
BARS_PER_YEAR = 252


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
    df = raw[["timestamp", "close"]].copy()
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
# Core simulator for a single ETF with BIL-when-flat
# ---------------------------------------------------------------------------

def simulate_tsmom(etf_close: pd.Series, bil_close: pd.Series, label: str,
                   lookbacks: tuple[int, ...] = (LOOKBACK_BARS,)
                   ) -> tuple[pd.Series, dict]:
    """Simulate TSMOM on (etf, bil-when-flat).

    ``lookbacks`` is a tuple of bar-lookbacks whose signals are averaged
    (signal in {0, 1/N, 2/N, ..., 1}). Single-horizon by default;
    pass e.g. (21, 63, 252) for multi-horizon per Moskowitz/Ooi/Pedersen.
    """
    df = pd.concat([etf_close.rename("etf"), bil_close.rename("bil")], axis=1).dropna()
    idx = df.index
    etf = df["etf"]
    bil = df["bil"]

    etf_ret = etf.pct_change().fillna(0.0)
    bil_ret = bil.pct_change().fillna(0.0)

    # One return series per lookback -> one binary signal per lookback.
    # Final signal is the average in [0, 1].
    sub_signals = []
    for lb in lookbacks:
        r_lb = etf.pct_change(lb)
        sub_signals.append((r_lb > 0).astype(float))
    combined_signal = pd.concat(sub_signals, axis=1).mean(axis=1)  # mean of 0/1 -> in [0, 1]

    realized_vol = etf_ret.rolling(VOL_LOOKBACK, min_periods=VOL_LOOKBACK // 2).std(ddof=1) * np.sqrt(BARS_PER_YEAR)
    realized_vol = realized_vol.shift(1)  # no look-ahead

    max_lb = max(lookbacks)
    first_rebal = max_lb
    n = len(idx)
    w_etf = np.zeros(n)
    w_bil = np.zeros(n)
    cur_scale = 0.0
    last_scale = 0.0
    trades = 0

    for t in range(n):
        if t < first_rebal:
            w_etf[t] = 0.0
            w_bil[t] = 1.0
            continue
        is_rebal = (t - first_rebal) % REBAL_BARS == 0
        if is_rebal:
            sig = combined_signal.iloc[t - 1]  # t-1 signal -> no look-ahead
            rv = realized_vol.iloc[t - 1]
            if np.isfinite(sig) and np.isfinite(rv) and rv > 1e-6:
                vol_scale = min(VOL_TARGET_ANN / rv, GROSS_CAP)
                cur_scale = float(sig) * vol_scale
            else:
                cur_scale = 0.0
            if abs(cur_scale - last_scale) > 1e-6 or (t == first_rebal and cur_scale > 0):
                trades += 1
            last_scale = cur_scale
        w_etf[t] = cur_scale
        w_bil[t] = 1.0 - cur_scale

    gross_ret = w_etf * etf_ret.to_numpy() + w_bil * bil_ret.to_numpy()
    dw = np.abs(np.diff(w_etf, prepend=w_etf[0]))
    dw[0] = 0.0
    costs = dw * (COST_BPS_PER_SIDE * 1e-4)
    net_ret = pd.Series(gross_ret - costs, index=idx, name=label)

    stats = {
        "label": label,
        "lookbacks": lookbacks,
        "trades": trades,
        "frac_long": float(np.mean(w_etf > 0)),
        "frac_full_long": float(np.mean(np.isclose(w_etf, w_etf[w_etf > 0].max() if (w_etf > 0).any() else 0.0, rtol=1e-3))),
        "avg_scale_when_long": float(w_etf[w_etf > 0].mean() if (w_etf > 0).any() else 0.0),
        # Arrays needed for downstream permutation tests.
        "w_etf": w_etf.copy(),
        "etf_ret": etf_ret.to_numpy().copy(),
        "bil_ret": bil_ret.to_numpy().copy(),
        "costs": costs.copy(),
    }
    return net_ret, stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section("Loading Treasury ETFs")
    tlt = load_series("TLT")
    ief = load_series("IEF")
    bil = load_series("BIL")
    if any(x is None for x in (tlt, ief, bil)):
        print("Missing ETF data; abort.")
        return 1
    for name, df in (("TLT", tlt), ("IEF", ief), ("BIL", bil)):
        print(f"  {name:<4s} {len(df):>5,} bars  "
              f"{df.index[0].date()} -> {df.index[-1].date()}  "
              f"last={df['close'].iloc[-1]:.2f}")

    common = tlt.index.intersection(ief.index).intersection(bil.index).sort_values()
    tlt_c = tlt["close"].reindex(common)
    ief_c = ief["close"].reindex(common)
    bil_c = bil["close"].reindex(common)
    print(f"\n  Common index: {len(common):,} bars  {common[0].date()} -> {common[-1].date()}")

    # ------------------------------------------------------------------
    # Variants.
    # ------------------------------------------------------------------
    section("Strategy variants")
    tlt_ret, tlt_stats = simulate_tsmom(tlt_c, bil_c, "TLT-trend")
    ief_ret, ief_stats = simulate_tsmom(ief_c, bil_c, "IEF-trend")
    ief_mh_ret, ief_mh_stats = simulate_tsmom(
        ief_c, bil_c, "IEF-trend-MH", lookbacks=MULTI_LOOKBACKS,
    )
    blend_ret = 0.5 * tlt_ret + 0.5 * ief_ret
    blend_ret.name = "50/50-blend"

    # References for comparison.
    tlt_bh = tlt_c.pct_change().fillna(0.0).rename("TLT-buyhold")
    bil_bh = bil_c.pct_change().fillna(0.0).rename("BIL-buyhold")

    print(f"  {'variant':<22s} {'lookbacks':<20s} {'trades':>7s} {'frac-long':>11s} {'avg-scale':>11s}")
    for s in (tlt_stats, ief_stats, ief_mh_stats):
        lbs = str(s['lookbacks'])
        print(f"  {s['label']:<22s} {lbs:<20s} {s['trades']:>7d} "
              f"{s['frac_long'] * 100:>10.1f}% {s['avg_scale_when_long']:>11.3f}")

    section("Performance summary (full period)")
    print(f"  {'variant':<22s} {'ret':>10s}  {'CAGR':>8s}  {'Sharpe':>7s}  "
          f"{'MDD':>8s}  {'Calmar':>7s}  {'worst-day':>10s}")
    report_block("TLT-trend (12M)", tlt_ret)
    report_block("IEF-trend (12M)", ief_ret)
    report_block("IEF-trend MH", ief_mh_ret)
    report_block("50/50 blend", blend_ret)
    report_block("TLT buy & hold", tlt_bh)
    report_block("BIL (cash)", bil_bh)

    # ------------------------------------------------------------------
    # Critical test: 2022 bond crash drill-down.
    # ------------------------------------------------------------------
    section("2022 drill-down (bond crash year)")
    print(f"  {'variant':<22s} {'ret':>10s}  {'MDD':>8s}  {'worst-day':>10s}")
    for label, r in (("TLT-trend (12M)", tlt_ret), ("IEF-trend (12M)", ief_ret),
                     ("IEF-trend MH", ief_mh_ret), ("50/50 blend", blend_ret),
                     ("TLT buy & hold", tlt_bh), ("BIL (cash)", bil_bh)):
        sub = r.loc["2022-01-01":"2022-12-31"]
        if len(sub) > 10:
            sub_eq = (1.0 + sub).cumprod()
            print(f"  {label:<22s} {sub_eq.iloc[-1] / sub_eq.iloc[0] - 1:>+9.2%}  "
                  f"{max_drawdown(sub_eq.to_numpy()):>+7.2%}  "
                  f"{sub.min():>+9.2%}")

    # ------------------------------------------------------------------
    # Regime breakdown.
    # ------------------------------------------------------------------
    section("Regime sub-periods (IEF-MH, preferred variant)")
    windows = [
        ("2015-2017",         "2015-01-01", "2017-12-31"),
        ("2018-2019",         "2018-01-01", "2019-12-31"),
        ("2020-2021",         "2020-01-01", "2021-12-31"),
        ("2022",              "2022-01-01", "2022-12-31"),
        ("2023-2026 holdout", "2023-01-01", "2026-12-31"),
    ]
    print(f"  {'window':<22s} {'ret':>10s}  {'CAGR':>8s}  {'Sharpe':>7s}  "
          f"{'MDD':>8s}  {'Calmar':>7s}  {'worst-day':>10s}")
    for label, s, e in windows:
        sub = ief_mh_ret.loc[s:e]
        report_block(label, sub)

    # ------------------------------------------------------------------
    # Kill-criteria check.
    # ------------------------------------------------------------------
    section("Phase 2 kill-criteria check")
    def check(label: str, rets: pd.Series, n_trades: int) -> None:
        eq = (1.0 + rets).cumprod()
        sh = annualized_sharpe(rets.to_numpy())
        mdd = max_drawdown(eq.to_numpy())
        sub_2022 = rets.loc["2022-01-01":"2022-12-31"]
        sub_2022_eq = (1.0 + sub_2022).cumprod()
        loss22 = float(sub_2022_eq.iloc[-1] / sub_2022_eq.iloc[0] - 1.0)
        def v(c: bool) -> str: return "PASS" if c else "FAIL"
        print(f"  [{label}]")
        print(f"    Sharpe > 0.30           : {v(sh > 0.30)}  (actual {sh:+.2f})")
        print(f"    Max DD < 15%            : {v(abs(mdd) < 0.15)}  (actual {mdd * 100:+.2f}%)")
        print(f"    2022 loss > -12%        : {v(loss22 > -0.12)}  (actual {loss22 * 100:+.2f}%)")
        print(f"    Trades >= 50            : {v(n_trades >= 50)}  (actual {n_trades})")
    check("IEF-trend (12M)", ief_ret, ief_stats['trades'])
    check("IEF-trend MH",    ief_mh_ret, ief_mh_stats['trades'])
    check("50/50 blend",     blend_ret, tlt_stats['trades'] + ief_stats['trades'])
    # Summary scalars for the end-of-run block (use IEF-MH).
    blend_eq = (1.0 + ief_mh_ret).cumprod()
    full_sharpe = annualized_sharpe(ief_mh_ret.to_numpy())
    full_mdd = max_drawdown(blend_eq.to_numpy())
    blend_2022 = ief_mh_ret.loc["2022-01-01":"2022-12-31"]
    blend_2022_eq = (1.0 + blend_2022).cumprod()
    loss_2022 = float(blend_2022_eq.iloc[-1] / blend_2022_eq.iloc[0] - 1.0)

    # ------------------------------------------------------------------
    # Correlation vs XS-mom.
    # ------------------------------------------------------------------
    section("Correlation vs XS-mom (the real diversification question)")
    print("  Loading XS-mom universe for cross-strategy comparison...")
    try:
        from xs_momentum_validation import (  # noqa: E402
            load_data as xs_load_data,
            run_xs_momentum,
            UNIVERSE as XS_UNIVERSE,
            COSTS_BY_SYMBOL as XS_COSTS,
        )
        xs_frames: dict[str, pd.DataFrame] = {}
        for sym in XS_UNIVERSE:
            df = xs_load_data(sym, START_DATE, END_DATE)
            if df is None or len(df) < 400:
                continue
            xs_frames[sym] = df
        print(f"    Loaded {len(xs_frames)} XS-mom instruments.")
        xs_res = run_xs_momentum(
            xs_frames,
            start_date=START_DATE, end_date=END_DATE,
            lookback_bars=189, skip_bars=42, rebalance_bars=63,
            top_k=5, bottom_k=0, starting_cash=100_000.0,
            costs_bps=XS_COSTS,
        )
        xs_idx = xs_res["index"]
        xs_ret = pd.Series(xs_res["daily_returns"], index=xs_idx, name="xs_mom")

        for label, r in (("TLT-trend (12M)", tlt_ret), ("IEF-trend (12M)", ief_ret),
                         ("IEF-trend MH", ief_mh_ret), ("50/50 blend", blend_ret)):
            aligned = pd.concat([r.rename("tt"), xs_ret], axis=1, join="inner").dropna()
            if len(aligned) < 60:
                print(f"  {label:<22s} too little overlap ({len(aligned)})")
                continue
            corr_daily = float(aligned["tt"].corr(aligned["xs_mom"]))
            monthly = (1.0 + aligned).resample("ME").prod() - 1.0
            corr_monthly = float(monthly["tt"].corr(monthly["xs_mom"]))
            print(f"  {label:<22s} corr(daily)={corr_daily:+.3f}  corr(monthly)={corr_monthly:+.3f}")
    except Exception as e:
        print(f"  Could not run XS-mom correlation: {e}")

    # ------------------------------------------------------------------
    # Summary.
    # ------------------------------------------------------------------
    section("Summary")
    years = (ief_mh_ret.index[-1] - ief_mh_ret.index[0]).days / 365.25
    total = float(blend_eq.iloc[-1] - 1.0)
    cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
    print(f"  IEF-MH             : CAGR {cagr * 100:+.2f}%  Sharpe {full_sharpe:+.2f}  "
          f"MDD {full_mdd * 100:+.2f}%  trades {ief_mh_stats['trades']}")
    print(f"  Period             : {ief_mh_ret.index[0].date()} -> {ief_mh_ret.index[-1].date()}")
    print(f"  2022 perf          : {loss_2022 * 100:+.2f}%  (TLT b&h 2022: -29%)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
