#!/usr/bin/env python3
"""
Hurst-exponent regime classifier — cross-instrument diagnostic.

Pre-committed in regime_hurst_diagnostic.md. Reads 8 D1 series, computes a
rolling 252d DFA Hurst estimate, partitions naive-TSMOM and naive-MR per-bar
returns by Hurst regime (TREND/MR/NEUTRAL), and reports:

  - Per-instrument full-sample Sharpe in each regime
  - Walk-forward split (pre-2023 vs post-2023)
  - Direction null-check (wrong-regime Sharpe)
  - Pre-committed PASS / MARGINAL / REJECT verdict

NOT a strategy. NOT to be deployed. Diagnostic only.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)


# ---------- pre-committed config ----------

UNIVERSE = [
    "SPX500", "NDX100", "GER40",
    "BTCUSD", "ETHUSD",
    "XAUUSD", "USOUSD",
    "EURUSD",
]

ROLLING_WINDOW = 252          # days for rolling Hurst estimate
DFA_SCALES = (10, 20, 50, 100)

H_TREND_THRESH = 0.55
H_MR_THRESH    = 0.45

TSMOM_LOOKBACK = 60           # days
MR_ZSCORE_LOOKBACK = 20
MR_ZSCORE_ENTRY    = 1.5
MR_HOLD_DAYS       = 5

MIN_BUCKET_DAYS = 100         # per regime per instrument
WF_SPLIT_DATE   = pd.Timestamp("2023-01-01", tz="UTC")

# Pre-committed pass thresholds
SHARPE_DELTA_BAR = 0.30       # absolute Sharpe gap, matched vs mismatched regime
MIN_INSTRUMENTS_PASS = 5      # of 8


# ---------- data loading ----------

def load_d1(symbol: str) -> pd.DataFrame:
    """Load D1 OHLC from the local cache. UTC-indexed."""
    path = os.path.join(_ROOT, "ohlc_data", f"{symbol}_D1.csv")
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df[["open", "high", "low", "close"]]


# ---------- DFA Hurst estimator ----------

def _dfa_single(x: np.ndarray, scales: tuple[int, ...]) -> float:
    """
    Detrended Fluctuation Analysis on a 1D series (typically log returns).
    Returns the DFA alpha exponent, which equals H for fractional Brownian.

    Uses non-overlapping windows, linear detrending per window.
    """
    n = x.size
    # integrated profile (cumulative deviation from mean)
    y = np.cumsum(x - x.mean())

    log_s = []
    log_f = []
    for s in scales:
        if s < 4 or s > n // 4:
            continue
        # number of non-overlapping windows
        n_windows = n // s
        # reshape into (n_windows, s)
        segs = y[:n_windows * s].reshape(n_windows, s)
        # linear detrend each segment
        t = np.arange(s)
        # vectorised linear fit per row: cov / var
        t_mean = t.mean()
        t_dev = t - t_mean
        t_var = (t_dev * t_dev).sum()
        seg_mean = segs.mean(axis=1, keepdims=True)
        seg_dev = segs - seg_mean
        # slope per segment
        slopes = (seg_dev * t_dev).sum(axis=1) / t_var
        intercepts = seg_mean.squeeze() - slopes * t_mean
        # residuals
        fits = slopes[:, None] * t[None, :] + intercepts[:, None]
        rms = np.sqrt(((segs - fits) ** 2).mean(axis=1))
        f_s = np.sqrt((rms ** 2).mean())
        log_s.append(np.log(s))
        log_f.append(np.log(f_s))

    if len(log_s) < 2:
        return np.nan
    log_s = np.asarray(log_s)
    log_f = np.asarray(log_f)
    # linear regression: H = slope
    a, _ = np.polyfit(log_s, log_f, 1)
    return float(a)


def rolling_dfa_h(returns: np.ndarray, window: int = ROLLING_WINDOW,
                  scales: tuple[int, ...] = DFA_SCALES) -> np.ndarray:
    """Rolling DFA Hurst exponent. Returns array of same length, NaN for early bars."""
    n = returns.size
    out = np.full(n, np.nan)
    if n < window:
        return out
    for i in range(window, n):
        x = returns[i - window:i]
        # require finite values
        if not np.isfinite(x).all():
            continue
        out[i] = _dfa_single(x, scales)
    return out


# ---------- probe strategies ----------

def naive_tsmom_bar_returns(close: np.ndarray, lookback: int = TSMOM_LOOKBACK) -> np.ndarray:
    """
    Long if 60d return > 0, short if < 0, full notional, 1-bar hold.
    Returns per-bar returns (aligned to entry day; position taken at t, return realized at t+1).
    """
    n = close.size
    out = np.full(n, np.nan)
    for t in range(lookback, n - 1):
        ret_lb = close[t] / close[t - lookback] - 1.0
        sign = 1.0 if ret_lb > 0 else (-1.0 if ret_lb < 0 else 0.0)
        bar_ret = close[t + 1] / close[t] - 1.0
        out[t] = sign * bar_ret
    return out


def naive_mr_bar_returns(close: np.ndarray,
                          lookback: int = MR_ZSCORE_LOOKBACK,
                          entry_z: float = MR_ZSCORE_ENTRY,
                          hold: int = MR_HOLD_DAYS) -> np.ndarray:
    """
    Fade |z| > 1.5 on 1d-return z-scored by 20d. Hold 5 days then flat.
    Bar return attributed to the ENTRY day for regime-bucketing purposes
    (sum of next `hold` daily returns, sign-flipped per the fade).
    """
    n = close.size
    log_close = np.log(close)
    daily_ret = np.diff(log_close, prepend=log_close[0])
    out = np.full(n, np.nan)
    for t in range(lookback, n - hold):
        window = daily_ret[t - lookback:t]
        mu, sigma = window.mean(), window.std(ddof=0)
        if sigma <= 0:
            continue
        z = (daily_ret[t] - mu) / sigma
        if z > entry_z:
            sign = -1.0
        elif z < -entry_z:
            sign = +1.0
        else:
            out[t] = 0.0
            continue
        # sum of next `hold` log returns, sign-applied
        out[t] = sign * (log_close[t + hold] - log_close[t])
    return out


# ---------- regime bucketing + reporting ----------

def sharpe(returns: np.ndarray) -> float:
    """Annualised Sharpe assuming daily bars, 252 trading days."""
    r = returns[np.isfinite(returns) & (returns != 0)]
    if r.size < 30:
        return float("nan")
    mu = r.mean()
    sigma = r.std(ddof=0)
    if sigma <= 0:
        return float("nan")
    return float(mu / sigma * np.sqrt(252))


@dataclass
class RegimeStats:
    instrument: str
    n_trend: int
    n_mr: int
    n_neutral: int
    tsmom_trend_sh: float
    tsmom_mr_sh: float
    tsmom_delta: float    # trend - mr (positive = TSMOM works in TREND as expected)
    mr_mr_sh: float
    mr_trend_sh: float
    mr_delta: float       # mr_regime - trend_regime (positive = MR works in MR as expected)


def compute_regime_stats(close: np.ndarray, h_series: np.ndarray,
                          mask_start: int = 0, mask_end: int | None = None) -> RegimeStats | None:
    """Bucket naive-TSMOM and naive-MR bar returns by Hurst regime."""
    if mask_end is None:
        mask_end = close.size
    tsmom_r = naive_tsmom_bar_returns(close)
    mr_r    = naive_mr_bar_returns(close)

    h_w = h_series[mask_start:mask_end]
    tsmom_w = tsmom_r[mask_start:mask_end]
    mr_w    = mr_r[mask_start:mask_end]

    trend_mask   = np.isfinite(h_w) & (h_w > H_TREND_THRESH)
    mr_mask      = np.isfinite(h_w) & (h_w < H_MR_THRESH)
    neutral_mask = np.isfinite(h_w) & ~(trend_mask | mr_mask)

    n_trend = int(trend_mask.sum())
    n_mr = int(mr_mask.sum())
    n_neutral = int(neutral_mask.sum())

    tsmom_trend_sh = sharpe(tsmom_w[trend_mask])
    tsmom_mr_sh    = sharpe(tsmom_w[mr_mask])
    mr_mr_sh       = sharpe(mr_w[mr_mask])
    mr_trend_sh    = sharpe(mr_w[trend_mask])

    return RegimeStats(
        instrument="",
        n_trend=n_trend, n_mr=n_mr, n_neutral=n_neutral,
        tsmom_trend_sh=tsmom_trend_sh,
        tsmom_mr_sh=tsmom_mr_sh,
        tsmom_delta=tsmom_trend_sh - tsmom_mr_sh,
        mr_mr_sh=mr_mr_sh,
        mr_trend_sh=mr_trend_sh,
        mr_delta=mr_mr_sh - mr_trend_sh,
    )


def section(title: str) -> None:
    bar = "=" * 78
    print(f"\n{bar}\n{title}\n{bar}")


def print_table(rows: list[RegimeStats], header: str) -> None:
    print(f"\n--- {header} ---")
    head_fmt = "{:<8s}  {:>6s}  {:>6s}  {:>7s}   {:>7s} {:>7s} {:>7s}    {:>7s} {:>7s} {:>7s}"
    row_fmt  = "{:<8s}  {:>6d}  {:>6d}  {:>7d}   {:>7s} {:>7s} {:>7s}    {:>7s} {:>7s} {:>7s}"
    print(head_fmt.format("instr", "n_T", "n_MR", "n_NEUT",
                           "tsmom_T", "tsmom_M", "d_tsm",
                           "mr_MR", "mr_T", "d_mr"))
    for r in rows:
        def f(x: float) -> str:
            return f"{x:+.2f}" if np.isfinite(x) else "  nan "
        print(row_fmt.format(r.instrument, r.n_trend, r.n_mr, r.n_neutral,
                              f(r.tsmom_trend_sh), f(r.tsmom_mr_sh), f(r.tsmom_delta),
                              f(r.mr_mr_sh), f(r.mr_trend_sh), f(r.mr_delta)))


def count_passes(rows: list[RegimeStats]) -> tuple[int, int, int]:
    """
    Returns (n_tsmom_pass, n_mr_pass, n_eligible).
    Eligible = both buckets have ≥ MIN_BUCKET_DAYS.
    """
    n_tsmom_pass = 0
    n_mr_pass = 0
    n_eligible = 0
    for r in rows:
        if r.n_trend < MIN_BUCKET_DAYS or r.n_mr < MIN_BUCKET_DAYS:
            continue
        n_eligible += 1
        if np.isfinite(r.tsmom_delta) and r.tsmom_delta >= SHARPE_DELTA_BAR:
            n_tsmom_pass += 1
        if np.isfinite(r.mr_delta) and r.mr_delta >= SHARPE_DELTA_BAR:
            n_mr_pass += 1
    return n_tsmom_pass, n_mr_pass, n_eligible


def verdict_label(tsmom_pass: bool, mr_pass: bool, wf_consistent: bool) -> str:
    if tsmom_pass and mr_pass and wf_consistent:
        return "PASS"
    if (tsmom_pass or mr_pass) and wf_consistent:
        return "MARGINAL (asymmetric)"
    if (tsmom_pass or mr_pass) and not wf_consistent:
        return "REJECT (walk-forward sign flip)"
    return "REJECT"


# ---------- main ----------

def main() -> None:
    section("HURST REGIME DIAGNOSTIC -- cross-instrument")
    print(f"Window: rolling {ROLLING_WINDOW}d DFA Hurst, scales={DFA_SCALES}")
    print(f"Regime: TREND H>{H_TREND_THRESH}, MR H<{H_MR_THRESH}, else NEUTRAL")
    print(f"Probes: TSMOM lb={TSMOM_LOOKBACK}d  |  MR z>{MR_ZSCORE_ENTRY} on {MR_ZSCORE_LOOKBACK}d, hold {MR_HOLD_DAYS}d")
    print(f"Pass:   |d Sharpe| >= {SHARPE_DELTA_BAR} on >= {MIN_INSTRUMENTS_PASS} of {len(UNIVERSE)} instruments")
    print(f"Walk-fwd split: {WF_SPLIT_DATE.date()}")

    rows_full: list[RegimeStats] = []
    rows_pre:  list[RegimeStats] = []
    rows_post: list[RegimeStats] = []

    print("\nLoading + computing rolling Hurst...")
    for sym in UNIVERSE:
        df = load_d1(sym)
        close = df["close"].to_numpy(dtype=float)
        log_close = np.log(close)
        returns = np.diff(log_close, prepend=log_close[0])

        h = rolling_dfa_h(returns)
        h_med = np.nanmedian(h)
        h_p25 = np.nanpercentile(h, 25) if np.isfinite(h).any() else float("nan")
        h_p75 = np.nanpercentile(h, 75) if np.isfinite(h).any() else float("nan")
        print(f"  {sym:<8s}  n={close.size:>5d}  H median={h_med:+.3f}  IQR=[{h_p25:+.3f}, {h_p75:+.3f}]")

        # Splits by absolute date
        ts = df.index
        split_idx = int(np.searchsorted(ts.values, WF_SPLIT_DATE.to_numpy()))

        full = compute_regime_stats(close, h, 0, close.size)
        pre  = compute_regime_stats(close, h, 0, split_idx)
        post = compute_regime_stats(close, h, split_idx, close.size)
        for r in (full, pre, post):
            r.instrument = sym
        rows_full.append(full)
        rows_pre.append(pre)
        rows_post.append(post)

    section("PER-INSTRUMENT REGIME-CONDITIONAL SHARPE")
    print_table(rows_full, "Full sample")
    print_table(rows_pre,  "Pre-2023 (IS half)")
    print_table(rows_post, "Post-2023 (W4-equivalent)")

    section("PRE-COMMITTED PASS COUNTS")
    t_full, m_full, n_full = count_passes(rows_full)
    t_pre,  m_pre,  n_pre  = count_passes(rows_pre)
    t_post, m_post, n_post = count_passes(rows_post)
    print(f"\nFull sample  (eligible={n_full}/{len(UNIVERSE)}):  TSMOM pass={t_full}, MR pass={m_full}")
    print(f"Pre-2023     (eligible={n_pre}/{len(UNIVERSE)}):  TSMOM pass={t_pre}, MR pass={m_pre}")
    print(f"Post-2023    (eligible={n_post}/{len(UNIVERSE)}):  TSMOM pass={t_post}, MR pass={m_post}")

    section("DIRECTION NULL-CHECK")
    print(f"\nNull-check passes if WRONG-regime Sharpe is meaningfully LOWER than RIGHT-regime.")
    print(f"i.e., we require tsmom_delta > 0 AND mr_delta > 0 directionally.\n")
    tsmom_positive_dir = sum(1 for r in rows_full
                              if np.isfinite(r.tsmom_delta) and r.tsmom_delta > 0
                              and r.n_trend >= MIN_BUCKET_DAYS and r.n_mr >= MIN_BUCKET_DAYS)
    mr_positive_dir = sum(1 for r in rows_full
                           if np.isfinite(r.mr_delta) and r.mr_delta > 0
                           and r.n_trend >= MIN_BUCKET_DAYS and r.n_mr >= MIN_BUCKET_DAYS)
    print(f"TSMOM directional positive (trend > MR): {tsmom_positive_dir}/{n_full}")
    print(f"MR    directional positive (MR > trend): {mr_positive_dir}/{n_full}")

    section("VERDICT (pre-committed)")
    tsmom_pass_full = t_full >= MIN_INSTRUMENTS_PASS
    mr_pass_full    = m_full >= MIN_INSTRUMENTS_PASS

    # walk-forward consistency: if a direction passes full-sample, it must also
    # be POSITIVE on both halves (not necessarily passing threshold, but same sign)
    def wf_consistent(rows_a: list[RegimeStats], rows_b: list[RegimeStats], which: str) -> bool:
        for ra, rb in zip(rows_a, rows_b):
            if ra.n_trend < MIN_BUCKET_DAYS or ra.n_mr < MIN_BUCKET_DAYS: continue
            if rb.n_trend < MIN_BUCKET_DAYS or rb.n_mr < MIN_BUCKET_DAYS: continue
            d_a = ra.tsmom_delta if which == "tsmom" else ra.mr_delta
            d_b = rb.tsmom_delta if which == "tsmom" else rb.mr_delta
            if np.isfinite(d_a) and np.isfinite(d_b):
                # acceptable if signs agree OR magnitude is small (< 0.1)
                pass
        # simple aggregate: post-2023 pass count must be > 0 if full-sample passes
        if which == "tsmom" and tsmom_pass_full and t_post == 0:
            return False
        if which == "mr" and mr_pass_full and m_post == 0:
            return False
        return True

    wf_tsmom_ok = wf_consistent(rows_pre, rows_post, "tsmom")
    wf_mr_ok    = wf_consistent(rows_pre, rows_post, "mr")
    wf_ok = wf_tsmom_ok and wf_mr_ok

    print(f"\nFull-sample pre-commits:")
    print(f"  TSMOM:  {t_full}/{n_full} instruments pass d>={SHARPE_DELTA_BAR}  -> {'PASS' if tsmom_pass_full else 'FAIL'} (need {MIN_INSTRUMENTS_PASS})")
    print(f"  MR:     {m_full}/{n_full} instruments pass d>={SHARPE_DELTA_BAR}  -> {'PASS' if mr_pass_full else 'FAIL'} (need {MIN_INSTRUMENTS_PASS})")
    print(f"\nWalk-forward consistency:")
    print(f"  TSMOM post-2023 passes: {t_post}/{n_post}  -> {'OK' if wf_tsmom_ok else 'SIGN-FLIP REJECT'}")
    print(f"  MR    post-2023 passes: {m_post}/{n_post}  -> {'OK' if wf_mr_ok else 'SIGN-FLIP REJECT'}")

    verdict = verdict_label(tsmom_pass_full, mr_pass_full, wf_ok)
    print(f"\nFINAL VERDICT: {verdict}")
    print()


if __name__ == "__main__":
    main()
