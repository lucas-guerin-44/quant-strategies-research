#!/usr/bin/env python3
"""
Equity pairs trading -- Phase 2 minimum-viable demo.

10 hand-picked mega-cap cointegrated pairs, dollar-neutral long/short with
rolling OLS hedge ratio and z-score-based mean-reversion signal.

Thesis: experiments/equity_pairs/equity_pairs.md
Universe: KO/PEP, XOM/CVX, JPM/BAC, V/MA, HD/LOW, UNH/CI, PG/CL,
          WMT/TGT, LMT/RTX, GS/MS.
Period: 2015-01-01 to 2026-04-18, daily bars, split+dividend adjusted.

Signal:
  beta[t]   = Cov(log A, log B) / Var(log B) over trailing 60 bars
  spread[t] = log A[t] - beta[t] * log B[t]
  z[t]      = (spread[t] - rolling_mean(spread, 60)) / rolling_std(spread, 60)
  Entry: |z| > 2.0; Exit: |z| < 0.5; Stop: |z| > 3.5; Time-stop: 20 bars.

Sizing: 0.30x equity gross per active pair (0.15 long leg + 0.15 short leg).
Max gross exposure 3.0x (all 10 pairs simultaneously active -- rare).

Costs: 12 bps roundtrip per pair + 30 bps/yr borrow on short leg
       (prorated by holding bars).
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

PAIRS: list[tuple[str, str]] = [
    ("KO",  "PEP"),
    ("XOM", "CVX"),
    ("JPM", "BAC"),
    ("V",   "MA"),
    ("HD",  "LOW"),
    ("UNH", "CI"),
    ("PG",  "CL"),
    ("WMT", "TGT"),
    ("LMT", "RTX"),
    ("GS",  "MS"),
]
TICKERS = sorted({s for p in PAIRS for s in p})

START_DATE = "2015-01-01"
END_DATE = "2026-04-18"
TIMEFRAME = "D1"

# Signal params.
BETA_WINDOW = 60       # rolling hedge ratio window
Z_WINDOW = 60          # rolling z-score window
ENTRY_Z = 2.0
EXIT_Z = 0.5
STOP_Z = 3.5
MAX_HOLD = 20

# Sizing.
PER_PAIR_GROSS = 0.30   # 0.15 long + 0.15 short per active pair
BARS_PER_YEAR = 252

# Costs.
ROUNDTRIP_BPS = 12.0    # commission + slippage, both legs, entry + exit
BORROW_BPS_PER_YEAR = 30.0   # annual borrow cost on short leg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f"\n{'=' * 80}\n  {t}\n{'=' * 80}\n")


def load_ticker(sym: str) -> pd.DataFrame | None:
    try:
        raw = fetch_ohlc(sym, TIMEFRAME, START_DATE, END_DATE)
    except Exception as e:
        print(f"  {sym:<5s} LOAD FAILED ({e})")
        return None
    if raw is None or raw.empty:
        print(f"  {sym:<5s} no bars")
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
# Core: simulate one pair
# ---------------------------------------------------------------------------

def simulate_pair(
    a_close: pd.Series, b_close: pd.Series, pair_label: str, verbose: bool = False
) -> tuple[pd.Series, dict]:
    """Return (daily_pair_return_series, stats_dict) for one pair."""
    # Align on inner intersection (both must have a close).
    df = pd.concat([a_close.rename("a"), b_close.rename("b")], axis=1).dropna()
    idx = df.index
    a = df["a"].to_numpy()
    b = df["b"].to_numpy()
    la = np.log(a)
    lb = np.log(b)

    # Rolling OLS beta of la on lb: beta_t = Cov(la, lb) / Var(lb) over window.
    n = len(idx)
    beta = np.full(n, np.nan)
    spread = np.full(n, np.nan)
    for t in range(BETA_WINDOW, n):
        la_w = la[t - BETA_WINDOW:t]
        lb_w = lb[t - BETA_WINDOW:t]
        var_b = lb_w.var(ddof=1)
        if var_b > 1e-12:
            cov = np.cov(la_w, lb_w, ddof=1)[0, 1]
            b_hat = cov / var_b
        else:
            b_hat = np.nan
        beta[t] = b_hat
        if np.isfinite(b_hat):
            spread[t] = la[t] - b_hat * lb[t]

    # Rolling mean + std on spread, 60 bars.
    spread_s = pd.Series(spread, index=idx)
    mu = spread_s.rolling(Z_WINDOW, min_periods=Z_WINDOW // 2).mean()
    sd = spread_s.rolling(Z_WINDOW, min_periods=Z_WINDOW // 2).std(ddof=1)
    z = (spread_s - mu) / sd

    a_ret = pd.Series(a, index=idx).pct_change().fillna(0.0).to_numpy()
    b_ret = pd.Series(b, index=idx).pct_change().fillna(0.0).to_numpy()
    z_arr = z.to_numpy()
    beta_arr = beta

    # State machine: 0 flat, +1 long pair (long A, short B), -1 short pair.
    state = 0
    entry_beta = np.nan
    entry_bar = -1

    daily_ret = np.zeros(n)
    trade_log: list[dict] = []
    current_trade: dict | None = None

    for t in range(1, n):
        # Apply P&L first at new weight (weight from t-1 state, b-hedge at entry).
        if state != 0:
            # pair_return = sign * (a_ret_t - entry_beta * b_ret_t)
            spread_ret = a_ret[t] - entry_beta * b_ret[t]
            # Scale to equity: 0.15 long leg + 0.15 short leg => half of gross.
            gross_per_leg = PER_PAIR_GROSS / 2.0
            contrib = state * gross_per_leg * spread_ret
            # Daily borrow drag on short leg (0.15x * annual_rate / 252).
            borrow = gross_per_leg * (BORROW_BPS_PER_YEAR * 1e-4) / BARS_PER_YEAR
            contrib -= borrow
            daily_ret[t] = contrib

        # Then evaluate transitions using today's z.
        zt = z_arr[t]
        if not np.isfinite(zt):
            continue

        if state == 0:
            if zt < -ENTRY_Z and np.isfinite(beta_arr[t]) and beta_arr[t] > 0:
                state = +1
                entry_beta = beta_arr[t]
                entry_bar = t
                entry_cost = (ROUNDTRIP_BPS * 0.5) * 1e-4 * PER_PAIR_GROSS
                daily_ret[t] -= entry_cost
                current_trade = {
                    "entry_date": idx[t], "side": +1, "entry_z": zt,
                    "entry_beta": entry_beta, "entry_spread": spread[t],
                }
            elif zt > ENTRY_Z and np.isfinite(beta_arr[t]) and beta_arr[t] > 0:
                state = -1
                entry_beta = beta_arr[t]
                entry_bar = t
                entry_cost = (ROUNDTRIP_BPS * 0.5) * 1e-4 * PER_PAIR_GROSS
                daily_ret[t] -= entry_cost
                current_trade = {
                    "entry_date": idx[t], "side": -1, "entry_z": zt,
                    "entry_beta": entry_beta, "entry_spread": spread[t],
                }
        else:
            held = t - entry_bar
            exit_reason = None
            if abs(zt) < EXIT_Z:
                exit_reason = "mean_reversion"
            elif abs(zt) > STOP_Z:
                exit_reason = "stop_loss"
            elif held >= MAX_HOLD:
                exit_reason = "time_stop"
            # Also flip if z crosses zero into the opposite extreme (unlikely but safe)
            elif (state == +1 and zt > +ENTRY_Z) or (state == -1 and zt < -ENTRY_Z):
                exit_reason = "flip_stop"
            if exit_reason is not None:
                exit_cost = (ROUNDTRIP_BPS * 0.5) * 1e-4 * PER_PAIR_GROSS
                daily_ret[t] -= exit_cost
                if current_trade is not None:
                    current_trade.update({
                        "exit_date": idx[t], "exit_z": zt,
                        "exit_spread": spread[t], "bars_held": held,
                        "reason": exit_reason,
                    })
                    trade_log.append(current_trade)
                    current_trade = None
                state = 0
                entry_beta = np.nan
                entry_bar = -1

    pair_ret = pd.Series(daily_ret, index=idx, name=pair_label)

    stats = {
        "pair": pair_label,
        "n_trades": len(trade_log),
        "n_bars": n,
        "z_coverage": float(np.isfinite(z_arr).mean()),
        "pct_in_trade": float(np.mean([(t["bars_held"] or 0) for t in trade_log]) * len(trade_log) / n) if trade_log else 0.0,
        "trades": trade_log,
    }
    if verbose and trade_log:
        stop_count = sum(1 for t in trade_log if t.get("reason") == "stop_loss")
        time_count = sum(1 for t in trade_log if t.get("reason") == "time_stop")
        mr_count = sum(1 for t in trade_log if t.get("reason") == "mean_reversion")
        print(f"    {pair_label:<10s} trades={len(trade_log):>3d}  MR={mr_count:>3d}  "
              f"time={time_count:>3d}  stop={stop_count:>3d}")
    return pair_ret, stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section("Loading tickers")
    frames: dict[str, pd.Series] = {}
    for sym in TICKERS:
        df = load_ticker(sym)
        if df is None or len(df) < 300:
            continue
        frames[sym] = df["close"]
        print(f"  {sym:<5s} {len(df):>5,} bars  "
              f"{df.index[0].date()} -> {df.index[-1].date()}  "
              f"last={df['close'].iloc[-1]:.2f}")

    missing = [s for s in TICKERS if s not in frames]
    if missing:
        print(f"\n  MISSING: {missing}")
        return 1

    # Common business-day index across all tickers.
    common = None
    for s, series in frames.items():
        common = series.index if common is None else common.intersection(series.index)
    common = common.sort_values()
    print(f"\n  Common index: {len(common):,} bars  "
          f"{common[0].date()} -> {common[-1].date()}")

    # ------------------------------------------------------------------
    # Simulate each pair.
    # ------------------------------------------------------------------
    section("Simulating pairs")
    print(f"  {'pair':<10s} {'trades':>6s}  {'MR':>4s} {'time':>4s} {'stop':>4s}")
    pair_returns: dict[str, pd.Series] = {}
    all_stats: list[dict] = []
    for a, b in PAIRS:
        label = f"{a}/{b}"
        a_s = frames[a].reindex(common)
        b_s = frames[b].reindex(common)
        ret, stats = simulate_pair(a_s, b_s, label, verbose=True)
        pair_returns[label] = ret
        all_stats.append(stats)

    # ------------------------------------------------------------------
    # Portfolio aggregation -- sum of per-pair return contributions.
    # ------------------------------------------------------------------
    section("Portfolio performance")
    port_ret = pd.concat(pair_returns.values(), axis=1).sum(axis=1)
    port_ret.name = "portfolio"
    port_eq = (1.0 + port_ret).cumprod()

    report_block("Full period", port_ret)

    total_trades = sum(s["n_trades"] for s in all_stats)
    print(f"\n  Total trades across pairs : {total_trades:,}")
    print(f"  Avg trades per pair       : {total_trades / len(PAIRS):.1f}")

    # Per-pair contribution ranking.
    section("Per-pair contribution")
    print(f"  {'pair':<10s} {'total_ret':>10s} {'sharpe':>8s} {'MDD':>8s} "
          f"{'trades':>7s} {'win%':>6s}")
    contribs = []
    for s in all_stats:
        pr = pair_returns[s["pair"]]
        total_p = float((1.0 + pr).prod() - 1.0)
        sharpe_p = annualized_sharpe(pr.to_numpy())
        eq_p = (1.0 + pr).cumprod().to_numpy()
        mdd_p = max_drawdown(eq_p) if len(eq_p) else 0.0
        # Win-rate on trades (pair-level): count closed trades with positive total contrib.
        tlog = s["trades"]
        wins = 0
        for tr in tlog:
            if "exit_date" in tr and "entry_date" in tr:
                seg = pr.loc[tr["entry_date"]:tr["exit_date"]]
                if (1.0 + seg).prod() > 1.0:
                    wins += 1
        win_rate = (wins / len(tlog)) if tlog else 0.0
        contribs.append((s["pair"], total_p, sharpe_p, mdd_p, s["n_trades"], win_rate))

    for p, tot, shrp, mdd, ntr, wr in sorted(contribs, key=lambda x: -x[1]):
        print(f"  {p:<10s} {tot * 100:>+9.2f}% {shrp:>+7.2f} {mdd * 100:>+7.2f}% "
              f"{ntr:>7d} {wr * 100:>5.1f}%")

    # Single-pair dominance check.
    total_ret = float(sum(c[1] for c in contribs))
    if total_ret != 0:
        max_share = max(abs(c[1]) / abs(total_ret) for c in contribs)
    else:
        max_share = 0.0

    # ------------------------------------------------------------------
    # Regime sub-periods.
    # ------------------------------------------------------------------
    section("Regime sub-periods")
    windows = [
        ("2015-2017",         "2015-01-01", "2017-12-31"),
        ("2018-2019",         "2018-01-01", "2019-12-31"),
        ("2020 (COVID)",      "2020-01-01", "2020-12-31"),
        ("2021-2022",         "2021-01-01", "2022-12-31"),
        ("2023-2026 (holdout)","2023-01-01", "2026-12-31"),
    ]
    print(f"  {'window':<22s} "
          f"{'ret':>10s}  {'CAGR':>8s}  {'Sharpe':>7s}  "
          f"{'MDD':>8s}  {'Calmar':>7s}  {'worst-day':>10s}")
    for label, s, e in windows:
        sub = port_ret.loc[s:e]
        report_block(label, sub)

    # ------------------------------------------------------------------
    # Kill-criteria check from thesis (Phase 2).
    # ------------------------------------------------------------------
    section("Phase 2 kill-criteria check")
    full_sharpe = annualized_sharpe(port_ret.to_numpy())
    full_mdd = max_drawdown(port_eq.to_numpy())
    full_ret = float(port_eq.iloc[-1] - 1.0)
    worst_day = float(port_ret.min())
    single_pair_share = max_share

    def verdict(cond: bool) -> str:
        return "PASS" if cond else "FAIL"

    print(f"  Sharpe > 0.30              : {verdict(full_sharpe > 0.30)}  (actual {full_sharpe:+.2f})")
    print(f"  Max DD < 15%               : {verdict(abs(full_mdd) < 0.15)}  (actual {full_mdd * 100:+.2f}%)")
    print(f"  Total trades >= 100        : {verdict(total_trades >= 100)}  (actual {total_trades})")
    print(f"  No pair > 40% of P&L       : {verdict(single_pair_share < 0.40)}  (actual {single_pair_share * 100:.1f}%)")
    print(f"  Full return                : {full_ret * 100:+.2f}%  (target CAGR ~10%)")
    print(f"  Worst single day           : {worst_day * 100:+.2f}%")

    # ------------------------------------------------------------------
    # Summary.
    # ------------------------------------------------------------------
    section("Summary")
    years = (port_ret.index[-1] - port_ret.index[0]).days / 365.25
    cagr = (1 + full_ret) ** (1 / max(years, 1e-9)) - 1
    print(f"  Period             : {port_ret.index[0].date()} -> {port_ret.index[-1].date()}  ({years:.1f}y)")
    print(f"  Total return       : {full_ret * 100:+.2f}%")
    print(f"  CAGR               : {cagr * 100:+.2f}%")
    print(f"  Sharpe (252)       : {full_sharpe:+.2f}")
    print(f"  Max DD             : {full_mdd * 100:+.2f}%")
    print(f"  # Pair-trades      : {total_trades}")
    print(f"  Top pair share     : {single_pair_share * 100:.1f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
