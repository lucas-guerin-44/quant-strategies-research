#!/usr/bin/env python3
"""
FX carry-trade demo -- mechanically-independent complement to XS-mom.

Pure pandas/numpy simulation (no Backtester).  Long high-yield currencies,
short low-yield ones, monthly-rebalanced, vol-targeted.  Reports standalone
risk/return plus correlation of daily and monthly returns against the
existing XS-mom strategy (imported from ``examples/xs_momentum_validation``).

Run AFTER ``scripts/fred_fetch.py``.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
EXPERIMENTS = os.path.dirname(HERE)
ROOT = os.path.dirname(EXPERIMENTS)
ENGINE = os.path.abspath(os.path.join(ROOT, "..", "backtesting-engine-2.0"))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
sys.path.insert(0, ENGINE)
sys.path.insert(0, os.path.join(EXPERIMENTS, "xs_momentum"))  # sibling for xs_momentum_validation

from data import fetch_ohlc  # noqa: E402
from xs_momentum_validation import (  # noqa: E402
    load_data as xs_load_data,
    run_xs_momentum,
    UNIVERSE as XS_UNIVERSE,
    COSTS_BY_SYMBOL as XS_COSTS,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FX_PAIRS = [
    "AUDNZD", "NZDCAD", "GBPNZD", "AUDCAD", "CADJPY", "NZDJPY",
    "EURGBP", "EURNOK", "USDZAR", "EURUSD", "GBPUSD",
]
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "NOK", "ZAR"]

TIMEFRAME = "D1"
START_DATE = "2015-01-01"
END_DATE = "2026-04-18"

RATES_DIR = os.path.join(ROOT, "ohlc_data", "rates")

# Signal threshold on carry differential (percent).
SIGNAL_THRESHOLD_PCT = 0.5

# Rebalance cadence (trading days) and sizing.
REBAL_BARS = 21                 # monthly
VOL_LOOKBACK_BARS = 60
VOL_TARGET_ANN = 0.15           # 15% per position
BARS_PER_YEAR = 252
GROSS_CAP = 2.0

# Costs in bps per unit of weight traded (per side).  4 bps commission +
# 2 bps slippage = 6 bps per unit of |delta weight|.
ROUNDTRIP_BPS = 6.0


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'=' * 78}\n  {title}\n{'=' * 78}\n")


def load_fx(symbol: str) -> pd.DataFrame | None:
    try:
        raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    except Exception as e:
        print(f"  {symbol:<8s} LOAD FAILED ({e})")
        return None
    if raw.empty:
        print(f"  {symbol:<8s} no bars")
        return None
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    # OHLC cleanup: high/low must bound O, C.
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    return df


def load_rate(ccy: str) -> pd.Series | None:
    path = os.path.join(RATES_DIR, f"{ccy}_rate.csv")
    if not os.path.exists(path):
        print(f"  {ccy:<3s}  no rate file at {path}")
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    s = df.set_index("date")["rate_pct"].sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s


def parse_pair(pair: str) -> tuple[str, str]:
    """FX pair convention: base = first 3 chars, quote = last 3."""
    return pair[:3], pair[3:]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section("Loading FX data")
    fx_frames: dict[str, pd.DataFrame] = {}
    for p in FX_PAIRS:
        df = load_fx(p)
        if df is None or len(df) < 300:
            if df is not None:
                print(f"  {p:<8s} skipped ({len(df)} bars)")
            continue
        fx_frames[p] = df
        print(f"  {p:<8s} {len(df):>5,} bars  "
              f"{df.index[0].date()} -> {df.index[-1].date()}")
    print(f"\n  {len(fx_frames)}/{len(FX_PAIRS)} pairs loaded")

    section("Loading interest-rate series")
    rates_raw: dict[str, pd.Series] = {}
    for c in CURRENCIES:
        s = load_rate(c)
        if s is None or s.empty:
            continue
        rates_raw[c] = s
        print(f"  {c:<3s}  {len(s):>5,} rows  "
              f"{s.index[0].date()} -> {s.index[-1].date()}  "
              f"last={s.iloc[-1]:.4f}%")
    missing_ccy = [c for c in CURRENCIES if c not in rates_raw]
    if missing_ccy:
        print(f"\n  WARNING: missing rate series for {missing_ccy} -- "
              f"any pair requiring these will be skipped from sizing.")

    # ------------------------------------------------------------------
    # Common daily index (business days) and aligned price/rate panels.
    # ------------------------------------------------------------------
    panel_start = pd.Timestamp(START_DATE, tz="UTC")
    panel_end = pd.Timestamp(END_DATE, tz="UTC")
    # Use pd.bdate_range then localize to UTC to match FX index.
    bidx_naive = pd.bdate_range(
        start=pd.Timestamp(START_DATE), end=pd.Timestamp(END_DATE)
    )
    bidx = bidx_naive.tz_localize("UTC")

    closes = pd.DataFrame(index=bidx, columns=list(fx_frames.keys()), dtype=float)
    for p, df in fx_frames.items():
        s = df["close"].reindex(bidx, method=None).ffill()
        closes[p] = s

    # Build per-currency rate panel: forward-fill monthly-series to daily
    # on the same business-day index.  Rates have naive timestamps, so
    # reindex to the naive bidx then attach UTC.
    rates = pd.DataFrame(index=bidx, columns=list(rates_raw.keys()), dtype=float)
    for c, s in rates_raw.items():
        # Align naive date to bidx_naive.
        r = s.reindex(bidx_naive, method="ffill")
        r.index = bidx
        rates[c] = r

    # After ffill there may still be a head of NaNs before first observation
    # (shouldn't happen -- all series start <= 2015-01-01 -- but guard).
    rates = rates.ffill()

    # ------------------------------------------------------------------
    # Signal per pair per day: +1 if carry > 0.5%, -1 if < -0.5%, else 0.
    # carry_pct = rate_base - rate_quote.
    # ------------------------------------------------------------------
    section("Signal construction")
    pair_signals: dict[str, pd.Series] = {}
    pair_carry: dict[str, pd.Series] = {}
    skipped_pairs: list[str] = []
    for p in closes.columns:
        base, quote = parse_pair(p)
        if base not in rates.columns or quote not in rates.columns:
            skipped_pairs.append(p)
            continue
        carry = rates[base] - rates[quote]
        pair_carry[p] = carry
        sig = pd.Series(0, index=bidx, dtype=int)
        sig[carry > SIGNAL_THRESHOLD_PCT] = 1
        sig[carry < -SIGNAL_THRESHOLD_PCT] = -1
        pair_signals[p] = sig

    if skipped_pairs:
        print(f"  Skipped pairs (missing a rate series): {skipped_pairs}")
    active_pairs = list(pair_signals.keys())
    print(f"  Active pairs: {len(active_pairs)}")

    # --- Sanity spot-check: print carry and signal at 3 representative dates
    # for 3 pairs with known directionality expectations.
    print("\n  Sanity spot-checks (expected long = +, short = -):")
    check_dates = [
        pd.Timestamp("2016-06-30", tz="UTC"),
        pd.Timestamp("2020-06-30", tz="UTC"),
        pd.Timestamp("2024-06-28", tz="UTC"),
    ]
    # NZDJPY ~ "AUDJPY-like": NZD usually > JPY -> long.
    # USDZAR: ZAR usually >> USD -> carry(base-quote) negative -> short
    #         (shorting USD vs ZAR = buying ZAR, the high-yielder).
    # AUDNZD: depends on regime.
    checks = ["NZDJPY", "USDZAR", "AUDNZD"]
    header = f"    {'date':<12s} " + " ".join(f"{p:>12s}" for p in checks if p in active_pairs)
    print(header)
    for d in check_dates:
        # Use nearest business-day on or before d.
        pos = bidx.get_indexer([d], method="pad")[0]
        if pos < 0:
            continue
        dstr = bidx[pos].strftime("%Y-%m-%d")
        parts = [f"    {dstr:<12s}"]
        for p in checks:
            if p not in active_pairs:
                continue
            c = pair_carry[p].iloc[pos]
            s = pair_signals[p].iloc[pos]
            parts.append(f"{c:+6.2f}% s={s:+d}")
        print(" ".join(parts))

    # ------------------------------------------------------------------
    # Daily returns on the close, per pair.
    # ------------------------------------------------------------------
    rets = closes[active_pairs].pct_change().fillna(0.0)

    # Rolling realized vol (annualised).
    daily_vol = rets.rolling(VOL_LOOKBACK_BARS, min_periods=VOL_LOOKBACK_BARS // 2).std(ddof=1)
    ann_vol = daily_vol * np.sqrt(BARS_PER_YEAR)

    # ------------------------------------------------------------------
    # P&L simulation, rebalancing every REBAL_BARS.
    # ------------------------------------------------------------------
    n_bars = len(bidx)
    weights = np.zeros(len(active_pairs))
    equity = np.empty(n_bars)
    equity[0] = 1.0  # unit equity; interpret as fractional return curve.
    daily_returns = np.zeros(n_bars)
    pair_pnl = np.zeros(len(active_pairs))
    turnover_events: list[float] = []
    n_rebals = 0

    # Signal coverage: first date where all active pairs have a finite rate
    # AND enough price history for vol estimate.
    first_valid = VOL_LOOKBACK_BARS  # need this many bars for vol
    # First rebalance at the first REBAL_BARS-multiple >= first_valid.
    first_rebal = first_valid
    rets_arr = rets.to_numpy()
    annvol_arr = ann_vol.to_numpy()
    sig_df = pd.DataFrame({p: pair_signals[p] for p in active_pairs}).to_numpy()
    rebal_dates: list[pd.Timestamp] = []

    for t in range(n_bars):
        if t > 0:
            r = rets_arr[t]
            r = np.where(np.isfinite(r), r, 0.0)
            port_ret = float(np.dot(weights, r))
            equity[t] = equity[t - 1] * (1.0 + port_ret)
            daily_returns[t] = port_ret
            pair_pnl += weights * r  # contribution tracked in "return units"

        is_rebal = (
            t >= first_rebal and (t - first_rebal) % REBAL_BARS == 0
        )
        if not is_rebal:
            continue

        sig_t = sig_df[t].astype(float)  # -1 / 0 / +1
        vol_t = annvol_arr[t]

        # Pairs with a live signal AND a valid vol estimate.
        live = (sig_t != 0) & np.isfinite(vol_t) & (vol_t > 1e-6)
        if not live.any():
            # Flatten if previously live but now no signal.
            new_weights = np.zeros_like(weights)
        else:
            # Equal-risk, vol-targeted: w_i = sign_i * (vol_target / realized_vol_i) / N_live.
            n_live = int(live.sum())
            new_weights = np.zeros_like(weights)
            base_w = np.where(live, sig_t * (VOL_TARGET_ANN / np.where(vol_t > 0, vol_t, np.nan)) / n_live, 0.0)
            base_w = np.where(np.isfinite(base_w), base_w, 0.0)

            # Cap total gross exposure at GROSS_CAP.
            gross = float(np.sum(np.abs(base_w)))
            if gross > GROSS_CAP and gross > 0:
                base_w = base_w * (GROSS_CAP / gross)
            new_weights = base_w

        dw = new_weights - weights
        turnover = float(np.sum(np.abs(dw)))
        turnover_events.append(turnover)

        cost = turnover * (ROUNDTRIP_BPS * 1e-4)
        equity[t] *= (1.0 - cost)
        daily_returns[t] -= cost

        weights = new_weights
        n_rebals += 1
        rebal_dates.append(bidx[t])

    # ------------------------------------------------------------------
    # Standalone metrics.
    # ------------------------------------------------------------------
    section("Carry standalone performance")
    total_ret = float(equity[-1] / equity[0] - 1.0)
    sharpe = annualized_sharpe(daily_returns)
    mdd = max_drawdown(equity)
    years = (bidx[-1] - bidx[0]).days / 365.25
    cagr = (equity[-1] / equity[0]) ** (1.0 / max(years, 1e-9)) - 1.0
    calmar = (cagr / abs(mdd)) if mdd != 0 else 0.0

    print(f"  Period          : {bidx[0].date()} -> {bidx[-1].date()}  ({years:.2f}y)")
    print(f"  Total return    : {total_ret * 100:+.2f}%")
    print(f"  CAGR            : {cagr * 100:+.2f}%")
    print(f"  Sharpe (252)    : {sharpe:.4f}")
    print(f"  Max DD          : {mdd * 100:+.2f}%")
    print(f"  Calmar          : {calmar:.3f}")
    print(f"  Rebalances      : {n_rebals}")
    if turnover_events:
        print(f"  Avg turnover    : {np.mean(turnover_events):.4f}  "
              f"(sum |dw| per rebal)")

    # ------------------------------------------------------------------
    # Per-pair P&L contribution, signal coverage.
    # ------------------------------------------------------------------
    section("Per-pair P&L contribution")
    contribs = sorted(
        [(p, pair_pnl[i]) for i, p in enumerate(active_pairs)],
        key=lambda x: -x[1],
    )
    print(f"  {'Pair':<8s} {'Contribution':>14s}")
    print("  " + "-" * 25)
    for p, c in contribs:
        print(f"  {p:<8s} {c * 100:>+13.2f}%")

    section("Signal coverage (fraction of days non-zero)")
    # Coverage starts only from first_rebal, since before that we hold flat.
    frac_rows = []
    for p in active_pairs:
        s = pair_signals[p].iloc[first_rebal:]
        frac = float((s != 0).mean())
        frac_rows.append((p, frac))
    frac_rows.sort(key=lambda x: -x[1])
    print(f"  {'Pair':<8s} {'Frac non-zero':>14s}")
    print("  " + "-" * 25)
    for p, f in frac_rows:
        print(f"  {p:<8s} {f * 100:>13.2f}%")

    # ------------------------------------------------------------------
    # Correlation with XS-mom.
    # ------------------------------------------------------------------
    section("Correlation with XS-momentum strategy")
    print("  Loading XS-mom universe for cross-strategy comparison...")
    xs_frames: dict[str, pd.DataFrame] = {}
    for sym in XS_UNIVERSE:
        df = xs_load_data(sym, START_DATE, END_DATE)
        if df is None or len(df) < 400:
            continue
        xs_frames[sym] = df
    print(f"    Loaded {len(xs_frames)} XS-mom instruments.")
    print("  Running XS-mom (lookback=189, skip=42, rebal=63, top_k=5, bottom_k=0)...")
    xs_res = run_xs_momentum(
        xs_frames,
        start_date=START_DATE,
        end_date=END_DATE,
        lookback_bars=189,
        skip_bars=42,
        rebalance_bars=63,
        top_k=5,
        bottom_k=0,
        starting_cash=100_000.0,
        costs_bps=XS_COSTS,
    )
    xs_idx = xs_res["index"]
    xs_ret = pd.Series(xs_res["daily_returns"], index=xs_idx, name="xs_mom")
    carry_ret = pd.Series(daily_returns, index=bidx, name="carry")

    # Align on the intersection.
    aligned = pd.concat([carry_ret, xs_ret], axis=1, join="inner").dropna()
    # Restrict to where BOTH strategies have live P&L.  Drop leading zeros
    # from each before the first non-zero.
    def _trim(s: pd.Series) -> pd.Series:
        nz = np.flatnonzero(s.to_numpy())
        return s.iloc[nz[0]:] if nz.size else s

    carry_live = _trim(aligned["carry"])
    xs_live = _trim(aligned["xs_mom"])
    live_start = max(carry_live.index[0], xs_live.index[0])
    both = aligned.loc[live_start:]
    print(f"  Overlap window  : {both.index[0].date()} -> {both.index[-1].date()}  "
          f"({len(both)} bars)")

    if len(both) < 30:
        print("  WARNING: very short overlap; correlation unreliable.")
    corr_daily = float(both["carry"].corr(both["xs_mom"]))

    # Monthly returns: compound daily returns within month, then correlate.
    monthly = (1.0 + both).resample("ME").prod() - 1.0
    corr_monthly = float(monthly["carry"].corr(monthly["xs_mom"]))

    print(f"  Corr (daily)    : {corr_daily:+.4f}")
    print(f"  Corr (monthly)  : {corr_monthly:+.4f}")

    # ------------------------------------------------------------------
    # Final summary block.
    # ------------------------------------------------------------------
    print()
    print("CARRY STRATEGY SUMMARY")
    print("======================")
    print(f"Return:           {total_ret * 100:+.2f}%")
    print(f"Sharpe:           {sharpe:.4f}")
    print(f"Max DD:           {mdd * 100:+.2f}%")
    print(f"Calmar:           {calmar:.3f}")
    print()
    print("Correlation with XS-mom:")
    print(f"  Daily returns:    {corr_daily:+.2f}")
    print(f"  Monthly returns:  {corr_monthly:+.2f}")
    print()
    print("Diversification verdict:")
    best_abs = max(abs(corr_daily), abs(corr_monthly))
    if best_abs < 0.3:
        verdict = "corr < 0.3  -> strong complement, add to blend"
    elif best_abs < 0.6:
        verdict = "corr 0.3-0.6 -> weak complement, limited value"
    else:
        verdict = "corr > 0.6  -> redundant, skip"
    print(f"  {verdict}")

    # Flag whether the standalone Sharpe target is met.
    print()
    print(f"Standalone Sharpe target (>0.4): "
          f"{'MET' if sharpe > 0.4 else 'MISSED'}  (actual {sharpe:.2f})")
    print(f"Correlation target (<0.3):       "
          f"{'MET' if best_abs < 0.3 else 'MISSED'}  (max |rho| {best_abs:.2f})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
