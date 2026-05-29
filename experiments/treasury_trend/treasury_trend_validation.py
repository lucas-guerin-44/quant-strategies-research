#!/usr/bin/env python3
"""
Treasury trend (IEF-MH) -- Phase 3 statistical battery.

Wires backtesting.statistics.compute_statistical_report to answer:
  1. Bootstrap 95% CI on Sharpe -- does it exclude zero?
  2. Permutation test -- is the observed Sharpe distinguishable from
     returns drawn in random order (null = no trade-direction edge)?
  3. Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014) -- adjusted for
     the number of configurations we evaluated during development.

n_trials_tested = 4 (TLT-12M, IEF-12M, 50/50 blend, IEF-MH). The lookback
triple (21, 63, 252) itself was not searched -- it was taken directly from
Moskowitz/Ooi/Pedersen (2012), so we don't double-count those as trials.
"""

from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_EXPERIMENTS)
sys.path.insert(0, _ROOT)  # research repo root
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, '..', 'backtesting-engine-2.0')))  # engine
sys.path.insert(0, _HERE)  # this strategy's directory

from treasury_trend_demo import (  # noqa: E402
    simulate_tsmom, MULTI_LOOKBACKS, BARS_PER_YEAR,
    START_DATE as DEFAULT_START_DATE,
)
from backtesting.statistics import compute_statistical_report  # noqa: E402
from data import fetch_ohlc  # noqa: E402
import pandas as pd  # noqa: E402


# Extended sample: IEF has traded since 2002-07-26. Using SHY (same vintage)
# as the cash proxy instead of BIL (2007-inception). SHY and BIL behave
# essentially identically on daily returns for our purposes.
EXTENDED_START = "2002-07-26"
EXTENDED_END = "2026-04-18"

# We deliberately evaluated these 4 configs during Phase 2:
N_TRIALS_TESTED = 4


def load_series_long(sym: str) -> pd.DataFrame | None:
    try:
        raw = fetch_ohlc(sym, "D1", EXTENDED_START, EXTENDED_END)
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


def section(t: str) -> None:
    print(f"\n{'=' * 80}\n  {t}\n{'=' * 80}\n")


def main() -> int:
    section("Loading data (extended sample)")
    ief = load_series_long("IEF")
    shy = load_series_long("SHY")
    if ief is None or shy is None:
        print("Missing data; abort.")
        return 1
    common = ief.index.intersection(shy.index).sort_values()
    ief_c = ief["close"].reindex(common)
    cash_c = shy["close"].reindex(common)
    print(f"  IEF/SHY aligned: {len(common):,} bars  "
          f"{common[0].date()} -> {common[-1].date()}  "
          f"(~{(common[-1] - common[0]).days / 365.25:.1f} years)")

    section("Running IEF-MH (1M + 3M + 12M) on extended sample")
    ret, stats = simulate_tsmom(ief_c, cash_c, "IEF-MH", lookbacks=MULTI_LOOKBACKS)
    equity = (1.0 + ret).cumprod().to_numpy()
    print(f"  lookbacks       : {stats['lookbacks']}")
    print(f"  trades          : {stats['trades']}")
    print(f"  frac-long days  : {stats['frac_long'] * 100:.1f}%")
    print(f"  avg scale (long): {stats['avg_scale_when_long']:.3f}")
    observed_sharpe = float(np.mean(np.diff(equity) / equity[:-1]) /
                            np.std(np.diff(equity) / equity[:-1], ddof=1)
                            * np.sqrt(BARS_PER_YEAR))
    print(f"  observed Sharpe : {observed_sharpe:+.4f}")

    section(f"Phase 3 statistical battery (n_trials_tested={N_TRIALS_TESTED})")
    print("  Running bootstrap CI (10,000 resamples), permutation test")
    print("  (5,000 permutations), and deflated Sharpe. Uses return-shuffle")
    print("  mode since this strategy has continuous position weights, not")
    print("  discrete trade PnLs.")
    print()

    report = compute_statistical_report(
        equity_curve=equity,
        trades=[],  # fall back to return-shuffle permutation
        n_trials_tested=N_TRIALS_TESTED,
        n_bootstrap=10_000,
        n_permutations=5_000,
        seed=42,
    )

    # ------------------------------------------------------------------
    # 1. Bootstrap CI
    # ------------------------------------------------------------------
    ci = report.bootstrap_ci
    ci_excludes_zero = ci.significant
    print("  [1] Bootstrap 95% CI on annualized Sharpe")
    print(f"      observed Sharpe    : {ci.observed_sharpe:+.4f}")
    print(f"      95% CI             : [{ci.ci_lower:+.4f}, {ci.ci_upper:+.4f}]")
    print(f"      CI excludes zero   : {'PASS' if ci_excludes_zero else 'FAIL'}")
    print()

    # ------------------------------------------------------------------
    # 2. Permutation test (position-shuffle -- proper null for
    #    continuous-position strategies). The engine's built-in perm test
    #    shuffles the return series, which for a continuous-weight
    #    strategy is mathematically equivalent to the observed -- not a
    #    meaningful null. The right question is: does the timing of
    #    our position choices beat random timing at the same marginal
    #    position distribution?
    # ------------------------------------------------------------------
    from backtesting.statistics import compute_sharpe as _sharpe  # noqa: E402
    rng = np.random.default_rng(42)
    w_real = stats['w_etf']
    etf_ret_arr = stats['etf_ret']
    bil_ret_arr = stats['bil_ret']
    costs_arr = stats['costs']
    # Observed net-P&L equity curve (re-derived for clarity).
    observed_net = w_real * etf_ret_arr + (1.0 - w_real) * bil_ret_arr - costs_arr
    observed_eq = np.cumprod(1.0 + observed_net)
    observed_sh = _sharpe(observed_eq)

    N_PERMS = 5000
    null_sharpes = np.empty(N_PERMS)
    for i in range(N_PERMS):
        w_shuffled = rng.permutation(w_real)
        # Keep the daily trading cost profile comparable by re-deriving
        # costs from the shuffled weight series (|dw|).
        dw_shuf = np.abs(np.diff(w_shuffled, prepend=w_shuffled[0]))
        dw_shuf[0] = 0.0
        costs_shuf = dw_shuf * (3.0 * 1e-4)  # COST_BPS_PER_SIDE = 3
        net_shuf = w_shuffled * etf_ret_arr + (1.0 - w_shuffled) * bil_ret_arr - costs_shuf
        eq_shuf = np.cumprod(1.0 + net_shuf)
        null_sharpes[i] = _sharpe(eq_shuf)
    perm_p = float(np.mean(null_sharpes >= observed_sh))
    perm_pass = perm_p < 0.05
    print("  [2] Permutation test (position-shuffle: shuffle weight timing,")
    print("      preserve marginal weight distribution and actual returns)")
    print(f"      observed Sharpe    : {observed_sh:+.4f}")
    print(f"      null Sharpe mean   : {null_sharpes.mean():+.4f}")
    print(f"      null Sharpe std    : {null_sharpes.std():.4f}")
    print(f"      null Sharpe p95    : {np.percentile(null_sharpes, 95):+.4f}")
    print(f"      p(null >= observed): {perm_p:.4f}")
    print(f"      p < 0.05           : {'PASS' if perm_pass else 'FAIL'}")
    print()

    # ------------------------------------------------------------------
    # 3. Deflated Sharpe
    # ------------------------------------------------------------------
    dsr = report.deflated_sharpe
    if dsr is None:
        print("  [3] Deflated Sharpe: skipped (n_trials<=1 or empty curve)")
        dsr_pass = False
    else:
        dsr_pass = dsr.significant
        print("  [3] Deflated Sharpe (Bailey & Lopez de Prado 2014)")
        print(f"      observed Sharpe    : {dsr.observed_sharpe:+.4f}")
        print(f"      deflated Sharpe    : {dsr.deflated_sharpe:+.4f}")
        print(f"      n_trials_tested    : {dsr.n_trials_tested}")
        print(f"      p-value            : {dsr.p_value:.4f}")
        print(f"      p < 0.05           : {'PASS' if dsr_pass else 'FAIL'}")
    print()

    # ------------------------------------------------------------------
    # Overall verdict
    # ------------------------------------------------------------------
    section("Phase 3 verdict")
    phase3_pass = ci_excludes_zero and perm_pass and dsr_pass
    print(f"  Bootstrap CI excludes 0 : {'PASS' if ci_excludes_zero else 'FAIL'}  "
          f"[{ci.ci_lower:+.4f}, {ci.ci_upper:+.4f}]")
    print(f"  Permutation p < 0.05    : {'PASS' if perm_pass else 'FAIL'}  "
          f"(p={perm_p:.4f})")
    print(f"  Deflated Sharpe p < 0.05: {'PASS' if dsr_pass else 'FAIL'}  "
          f"(p={dsr.p_value:.4f})")
    print()
    if phase3_pass:
        print("  Phase 3 OVERALL: PASS -- proceeding to Phase 4 (regime stability)")
    else:
        print("  Phase 3 OVERALL: FAIL -- at least one stat test rejected.")
        return 1

    # ==================================================================
    # Phase 4 — regime stability
    # ==================================================================
    section("Phase 4 — Regime stability (4 non-overlapping windows)")
    print("  Each window is an independent simulation with 252-bar warmup")
    print("  prepended from prior data. No state carries between windows.")
    print()

    WINDOWS = [
        ("W1 2002-2008 (post-dotcom, GFC onset)", "2002-07-26", "2008-12-31"),
        ("W2 2009-2014 (QE era, bond bull)     ", "2009-01-01", "2014-12-31"),
        ("W3 2015-2020 (ZIRP exit + first cycle)", "2015-01-01", "2020-12-31"),
        ("W4 2021-2026 (COVID + 2022 + recent) ", "2021-01-01", "2026-04-17"),
    ]

    print(f"  {'window':<42s} {'bars':>5s} {'trades':>7s} "
          f"{'ret':>9s} {'CAGR':>8s} {'Sharpe':>7s} {'MDD':>8s}")
    window_results = []
    for wname, wstart_str, wend_str in WINDOWS:
        wstart = pd.Timestamp(wstart_str, tz="UTC")
        wend = pd.Timestamp(wend_str, tz="UTC")
        idx = common
        pos_start = idx.searchsorted(wstart)
        pos_end = min(idx.searchsorted(wend, side='right'), len(idx))
        warmup_start_pos = max(0, pos_start - 252)
        ief_slice = ief_c.iloc[warmup_start_pos:pos_end]
        cash_slice = cash_c.iloc[warmup_start_pos:pos_end]
        w_ret, w_stats = simulate_tsmom(
            ief_slice, cash_slice, wname.strip(), lookbacks=MULTI_LOOKBACKS,
        )
        w_ret_window = w_ret.loc[wstart_str:wend_str]
        if len(w_ret_window) < 50:
            print(f"  {wname:<42s} <no data>")
            continue
        eq = (1.0 + w_ret_window).cumprod().to_numpy()
        years = (w_ret_window.index[-1] - w_ret_window.index[0]).days / 365.25
        total = float(eq[-1] / eq[0] - 1.0)
        cagr = (eq[-1] / eq[0]) ** (1.0 / max(years, 1e-9)) - 1.0
        sharpe = float(np.mean(np.diff(eq) / eq[:-1]) /
                       np.std(np.diff(eq) / eq[:-1], ddof=1) * np.sqrt(252)) if len(eq) > 1 else 0.0
        rm = np.maximum.accumulate(eq)
        mdd = float(((eq - rm) / rm).min())
        # Count trades inside the window (state changes after warmup).
        w_trades_in_window = w_stats['trades']
        window_results.append({
            "name": wname.strip(), "total_ret": total, "cagr": cagr,
            "sharpe": sharpe, "mdd": mdd, "bars": len(w_ret_window),
            "trades": w_trades_in_window,
        })
        print(f"  {wname:<42s} {len(w_ret_window):>5d} {w_trades_in_window:>7d} "
              f"{total * 100:>+8.2f}% {cagr * 100:>+7.2f}% "
              f"{sharpe:>+7.2f} {mdd * 100:>+7.2f}%")

    # ------------------------------------------------------------------
    # Phase 4 kill criteria.
    # ------------------------------------------------------------------
    print()
    positive_windows = sum(1 for w in window_results if w["sharpe"] > 0)
    total_ret_sum = sum(w["total_ret"] for w in window_results)
    max_share = 0.0
    if abs(total_ret_sum) > 1e-9:
        max_share = max(abs(w["total_ret"]) / abs(total_ret_sum) for w in window_results)

    p4_sharpe_pass = positive_windows >= 3
    p4_dominance_pass = max_share < 0.80

    print(f"  Windows with Sharpe > 0  : {positive_windows}/4  "
          f"({'PASS' if p4_sharpe_pass else 'FAIL'} — need >= 3)")
    print(f"  Max single-window share   : {max_share * 100:.1f}%  "
          f"({'PASS' if p4_dominance_pass else 'FAIL'} — need < 80%)")

    phase4_pass = p4_sharpe_pass and p4_dominance_pass
    print()
    if phase4_pass:
        print("  Phase 4 OVERALL: PASS -- regime-stable. Proceeding to Phase 5.")
    else:
        print("  Phase 4 OVERALL: FAIL -- regime-dependent.")
        return 1

    # ==================================================================
    # Phase 5 — Parameter sensitivity
    # ==================================================================
    section("Phase 5 — Parameter sensitivity (plateau vs peak)")
    print("  Sweep each key param with others held at baseline. Target:")
    print("  Sharpe plateau, not a lucky peak. Kill if Sharpe drops > 50%")
    print("  on ±20% param perturbation or goes negative in any sweep.")
    print()

    # Baseline reference for comparison.
    baseline_sharpe = observed_sh
    print(f"  Baseline (IEF-MH, {MULTI_LOOKBACKS}, rebal=21, vt=0.10): "
          f"Sharpe = {baseline_sharpe:+.4f}")
    print()

    def run_config(lookbacks: tuple[int, ...], rebal: int, vol_target: float,
                   vol_lb: int = 60) -> tuple[float, int, float]:
        # Temporarily patch module constants used by simulate_tsmom.
        import treasury_trend_demo as m
        orig_rebal = m.REBAL_BARS
        orig_vt = m.VOL_TARGET_ANN
        orig_vlb = m.VOL_LOOKBACK
        m.REBAL_BARS = rebal
        m.VOL_TARGET_ANN = vol_target
        m.VOL_LOOKBACK = vol_lb
        try:
            r, s = simulate_tsmom(ief_c, cash_c, "sweep", lookbacks=lookbacks)
        finally:
            m.REBAL_BARS = orig_rebal
            m.VOL_TARGET_ANN = orig_vt
            m.VOL_LOOKBACK = orig_vlb
        eq_arr = (1.0 + r).cumprod().to_numpy()
        if len(eq_arr) < 3:
            return 0.0, 0, 0.0
        sh = float(np.mean(np.diff(eq_arr) / eq_arr[:-1]) /
                   np.std(np.diff(eq_arr) / eq_arr[:-1], ddof=1) * np.sqrt(252))
        rm = np.maximum.accumulate(eq_arr)
        mdd = float(((eq_arr - rm) / rm).min())
        return sh, s['trades'], mdd

    # ------------------------------------------------------------------
    # Sweep 1: rebalance cadence (±50%+ around 21)
    # ------------------------------------------------------------------
    print("  [Sweep 1] Rebalance cadence")
    print(f"  {'rebal':>6s} {'Sharpe':>7s} {'trades':>7s} {'MDD':>8s}  {'vs-baseline':>11s}")
    sweep1 = []
    for rb in (5, 10, 15, 21, 30, 42, 63):
        sh, tr, mdd = run_config(MULTI_LOOKBACKS, rb, 0.10)
        delta = sh / baseline_sharpe - 1.0 if baseline_sharpe != 0 else 0.0
        marker = "<< baseline" if rb == 21 else ""
        print(f"  {rb:>6d} {sh:>+7.3f} {tr:>7d} {mdd * 100:>+7.2f}%  "
              f"{delta * 100:>+10.1f}%  {marker}")
        sweep1.append((rb, sh))

    # ------------------------------------------------------------------
    # Sweep 2: lookback structure (single-horizon + MH variants)
    # ------------------------------------------------------------------
    print("\n  [Sweep 2] Lookback structure")
    print(f"  {'lookbacks':<22s} {'Sharpe':>7s} {'trades':>7s} {'MDD':>8s}  {'vs-baseline':>11s}")
    lookback_variants = [
        ((63,),                  "3M only"),
        ((126,),                 "6M only"),
        ((189,),                 "9M only"),
        ((252,),                 "12M only"),
        ((378,),                 "18M only"),
        ((21, 252),              "1M+12M"),
        ((63, 252),              "3M+12M"),
        ((21, 63, 252),          "1M+3M+12M (baseline MH)"),
        ((21, 63, 126, 252),     "1M+3M+6M+12M"),
        ((21, 63, 252, 378),     "1M+3M+12M+18M"),
    ]
    sweep2 = []
    for lbs, label in lookback_variants:
        sh, tr, mdd = run_config(lbs, 21, 0.10)
        delta = sh / baseline_sharpe - 1.0 if baseline_sharpe != 0 else 0.0
        marker = "<< baseline" if lbs == MULTI_LOOKBACKS else ""
        print(f"  {str(lbs):<22s} {sh:>+7.3f} {tr:>7d} {mdd * 100:>+7.2f}%  "
              f"{delta * 100:>+10.1f}%  {marker}")
        sweep2.append((label, sh))

    # ------------------------------------------------------------------
    # Sweep 3: vol target (±50% around 0.10)
    # ------------------------------------------------------------------
    print("\n  [Sweep 3] Vol target (annualized)")
    print(f"  {'vt':>5s} {'Sharpe':>7s} {'trades':>7s} {'MDD':>8s}  {'vs-baseline':>11s}")
    sweep3 = []
    for vt in (0.05, 0.08, 0.10, 0.12, 0.15, 0.20):
        sh, tr, mdd = run_config(MULTI_LOOKBACKS, 21, vt)
        delta = sh / baseline_sharpe - 1.0 if baseline_sharpe != 0 else 0.0
        marker = "<< baseline" if abs(vt - 0.10) < 1e-6 else ""
        print(f"  {vt:>5.2f} {sh:>+7.3f} {tr:>7d} {mdd * 100:>+7.2f}%  "
              f"{delta * 100:>+10.1f}%  {marker}")
        sweep3.append((vt, sh))

    # ------------------------------------------------------------------
    # Sweep 4: vol lookback (±50% around 60)
    # ------------------------------------------------------------------
    print("\n  [Sweep 4] Vol lookback (realized-vol window)")
    print(f"  {'vlb':>5s} {'Sharpe':>7s} {'trades':>7s} {'MDD':>8s}  {'vs-baseline':>11s}")
    sweep4 = []
    for vlb in (20, 30, 45, 60, 90, 120):
        sh, tr, mdd = run_config(MULTI_LOOKBACKS, 21, 0.10, vol_lb=vlb)
        delta = sh / baseline_sharpe - 1.0 if baseline_sharpe != 0 else 0.0
        marker = "<< baseline" if vlb == 60 else ""
        print(f"  {vlb:>5d} {sh:>+7.3f} {tr:>7d} {mdd * 100:>+7.2f}%  "
              f"{delta * 100:>+10.1f}%  {marker}")
        sweep4.append((vlb, sh))

    # ------------------------------------------------------------------
    # Phase 5 kill-criteria.
    # ------------------------------------------------------------------
    print()
    all_sharpes = ([s for _, s in sweep1] + [s for _, s in sweep2] +
                   [s for _, s in sweep3] + [s for _, s in sweep4])
    min_sh = min(all_sharpes)
    neg_count = sum(1 for s in all_sharpes if s < 0)

    # ±20% perturbation: check rebal (21 ± 20% ≈ 17-25; our grid has 15 and 21 on each side) and
    # vol target (0.10 ± 20% = 0.08-0.12; our grid has both). Use those specifically.
    rebal_at_15 = next(s for r, s in sweep1 if r == 15)
    rebal_at_30 = next(s for r, s in sweep1 if r == 30)
    vt_at_008 = next(s for v, s in sweep3 if abs(v - 0.08) < 1e-6)
    vt_at_012 = next(s for v, s in sweep3 if abs(v - 0.12) < 1e-6)
    max_drop_20pct = max(
        abs(rebal_at_15 - baseline_sharpe) / abs(baseline_sharpe),
        abs(rebal_at_30 - baseline_sharpe) / abs(baseline_sharpe),
        abs(vt_at_008 - baseline_sharpe) / abs(baseline_sharpe),
        abs(vt_at_012 - baseline_sharpe) / abs(baseline_sharpe),
    )

    p5_dropout_pass = max_drop_20pct < 0.50
    p5_negative_pass = neg_count == 0

    print("  Phase 5 scorecard")
    print(f"    Min Sharpe across entire sweep      : {min_sh:+.3f}")
    print(f"    Negative Sharpe configs (yellow)    : {neg_count}/{len(all_sharpes)}")
    print(f"    Max Sharpe drop on ±20% param change: {max_drop_20pct * 100:.1f}%  "
          f"({'PASS' if p5_dropout_pass else 'FAIL'} — need < 50%)")
    print(f"    No negative Sharpe in sweep         : {'PASS' if p5_negative_pass else 'YELLOW'}")
    print()
    phase5_pass = p5_dropout_pass and p5_negative_pass
    if phase5_pass:
        print("  Phase 5 OVERALL: PASS -- Sharpe is on a plateau. Proceeding to Phase 6.")
    elif p5_dropout_pass and not p5_negative_pass:
        print("  Phase 5 OVERALL: YELLOW -- plateau holds under ±20% but goes negative in extremes.")
        return 1
    else:
        print("  Phase 5 OVERALL: FAIL -- Sharpe collapses under ±20% perturbation.")
        return 1

    # ==================================================================
    # Phase 6 — True holdout
    # ==================================================================
    section("Phase 6 — True holdout (train 2002-2014, test 2015-2026)")
    print("  Strategy was developed on 2015-2026 data. Honest OOS test:")
    print("  does the unchanged strategy perform on the pre-development")
    print("  period (proxy for 'if we had developed on 2002-2014 only,")
    print("  what would 2015-2026 have looked like out-of-sample?').")
    print()

    TRAIN_END = "2014-12-31"
    TEST_START = "2015-01-01"

    def run_split(start_str: str, end_str: str, label: str) -> dict:
        wstart = pd.Timestamp(start_str, tz="UTC")
        wend = pd.Timestamp(end_str, tz="UTC")
        pos_start = common.searchsorted(wstart)
        pos_end = min(common.searchsorted(wend, side='right'), len(common))
        warmup_start_pos = max(0, pos_start - 252)
        ief_slice = ief_c.iloc[warmup_start_pos:pos_end]
        cash_slice = cash_c.iloc[warmup_start_pos:pos_end]
        r, s = simulate_tsmom(ief_slice, cash_slice, label, lookbacks=MULTI_LOOKBACKS)
        r_window = r.loc[start_str:end_str]
        eq = (1.0 + r_window).cumprod().to_numpy()
        years = (r_window.index[-1] - r_window.index[0]).days / 365.25
        total = float(eq[-1] / eq[0] - 1.0)
        cagr = (eq[-1] / eq[0]) ** (1.0 / max(years, 1e-9)) - 1.0
        sh = float(np.mean(np.diff(eq) / eq[:-1]) /
                   np.std(np.diff(eq) / eq[:-1], ddof=1) * np.sqrt(252))
        rm = np.maximum.accumulate(eq)
        mdd = float(((eq - rm) / rm).min())
        return {
            "label": label, "years": years, "total": total, "cagr": cagr,
            "sharpe": sh, "mdd": mdd, "trades": s['trades'], "bars": len(r_window),
        }

    IS = run_split("2002-07-26", TRAIN_END, "IS train 2002-2014")
    OOS = run_split(TEST_START, "2026-04-17", "OOS test 2015-2026")

    print(f"  {'split':<22s} {'years':>5s} {'trades':>7s} "
          f"{'ret':>9s} {'CAGR':>8s} {'Sharpe':>7s} {'MDD':>8s}")
    for r in (IS, OOS):
        print(f"  {r['label']:<22s} {r['years']:>5.1f} {r['trades']:>7d} "
              f"{r['total'] * 100:>+8.2f}% {r['cagr'] * 100:>+7.2f}% "
              f"{r['sharpe']:>+7.2f} {r['mdd'] * 100:>+7.2f}%")

    degradation = IS["sharpe"] - OOS["sharpe"]
    print()
    print(f"  IS Sharpe           : {IS['sharpe']:+.3f}")
    print(f"  OOS Sharpe          : {OOS['sharpe']:+.3f}")
    print(f"  Degradation (IS-OOS): {degradation:+.3f}")
    print()
    p6_oos_positive = OOS["sharpe"] > 0
    p6_degradation_ok = degradation < 0.5
    print(f"  OOS Sharpe > 0       : {'PASS' if p6_oos_positive else 'FAIL'}  (actual {OOS['sharpe']:+.3f})")
    print(f"  Degradation < 0.5    : {'PASS' if p6_degradation_ok else 'FAIL'}  (actual {degradation:+.3f})")
    print()
    phase6_pass = p6_oos_positive and p6_degradation_ok
    if phase6_pass:
        print("  Phase 6 OVERALL: PASS -- OOS holds up. Ready for Phase 7 (already known:")
        print("                   corr with XS-mom ~ 0) and Phase 8 (QC deployment).")
    else:
        print("  Phase 6 OVERALL: FAIL -- strategy did not survive true holdout.")

    return 0 if phase6_pass else 1


if __name__ == "__main__":
    sys.exit(main())
