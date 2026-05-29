#!/usr/bin/env python3
"""
BTC volatility breakout (Crabel-style, D1) -- Phase 2 demo.

Thesis: experiments/btc_volbreak/btc_volbreak.md

Signal: vol_expansion = TR_t / ATR_yest(20) > VOL_MULT (default 1.5)
        AND |today_return_pct| > MIN_RETURN_PCT (default 1.0%)
Trade : enter at C_t, exit at C_{t+HOLD_DAYS}, direction = sign(today_ret).
Run continuation and fade variants alongside as a fade-gap test.

Phases run A-to-Z:
  Phase 2 - baseline at honest 10 bps/side + kill criteria
  Phase 4 - regime breakdown (4 windows)
  Phase 5 - parameter sensitivity (vol-mult, hold, cost)
  Phase 6 - walk-forward (5 rolling 3y-IS / 2y-OOS, per lesson #29)
  Holdout-decay diagnostic (W4 absolute floor + W1-W4 difference)
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

from data import fetch_ohlc


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SYMBOL = "BTCUSD"
TIMEFRAME = "D1"
START_DATE = "2018-01-01"
END_DATE = "2026-04-18"

BASE_ATR_LOOKBACK = 20
BASE_VOL_MULT = 1.5
BASE_MIN_RETURN_PCT = 1.0
BASE_HOLD_DAYS = 3
BASE_COST_BPS = 10.0
BARS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f"\n{'=' * 84}\n  {t}\n{'=' * 84}\n")


def load_btc(start: str = START_DATE, end: str = END_DATE) -> pd.DataFrame:
    raw = fetch_ohlc(SYMBOL, TIMEFRAME, start, end)
    df = raw[["timestamp", "open", "high", "low", "close"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def annualized_sharpe(r: np.ndarray, bars_per_year: float = BARS_PER_YEAR) -> float:
    r = r[np.isfinite(r)]
    if r.size == 0:
        return 0.0
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(bars_per_year))


def max_drawdown(e: np.ndarray) -> float:
    rm = np.maximum.accumulate(e)
    dd = (e - rm) / np.where(rm > 0, rm, 1.0)
    return float(dd.min()) if dd.size else 0.0


# ---------------------------------------------------------------------------
# Core: identify vol-expansion days + run trades
# ---------------------------------------------------------------------------

def build_signals(
    df: pd.DataFrame,
    atr_lookback: int,
    vol_mult: float,
    min_return_pct: float,
) -> pd.DataFrame:
    """Return a frame with per-day signal columns (vectorized, numpy core)."""
    close = df["close"].to_numpy(dtype=np.float64)
    high = df["high"].to_numpy(dtype=np.float64)
    low = df["low"].to_numpy(dtype=np.float64)
    n = len(df)

    # Daily True Range
    prev_close = np.concatenate(([np.nan], close[:-1]))
    tr_a = high - low
    tr_b = np.abs(high - prev_close)
    tr_c = np.abs(low - prev_close)
    tr = np.nanmax(np.stack([tr_a, tr_b, tr_c]), axis=0)

    # Rolling mean ATR over t-atr_lookback..t-1 (uses only data BEFORE t)
    atr = np.full(n, np.nan)
    if n > atr_lookback:
        cumsum = np.concatenate(([0.0], np.nancumsum(tr)))
        for t in range(atr_lookback, n):
            atr[t] = (cumsum[t] - cumsum[t - atr_lookback]) / atr_lookback

    # Daily return (close-to-close)
    ret_pct = np.full(n, np.nan)
    ret_pct[1:] = (close[1:] - close[:-1]) / close[:-1] * 100.0

    # Signals: today's TR > VOL_MULT * yesterday's ATR; |return| > min
    # Note: atr[t] uses t-atr_lookback..t-1 → yesterday-anchored.
    expansion = (tr / np.where(atr > 0, atr, np.nan)) > vol_mult
    direction_ok = np.abs(ret_pct) > min_return_pct
    fired = expansion & direction_ok & np.isfinite(ret_pct) & np.isfinite(atr)

    out = pd.DataFrame({
        "close": close,
        "tr": tr,
        "atr": atr,
        "tr_over_atr": tr / np.where(atr > 0, atr, np.nan),
        "ret_pct": ret_pct,
        "fired": fired,
        "side_cont": np.where(fired, np.sign(ret_pct), 0.0),
    }, index=df.index)
    return out


def simulate(
    sig: pd.DataFrame,
    direction: str,
    hold_days: int,
    cost_bps_per_side: float,
) -> tuple[pd.Series, dict]:
    """Run continuation ('cont') or fade direction.

    Trade: enter at C_t for each fired day, exit at C_{t+hold}. Returns are
    measured per-trade and stamped at entry day. If a new fire happens while
    a prior trade is still open, the prior trade exits at the new entry day
    (no overlapping positions).
    """
    close = sig["close"].to_numpy(dtype=np.float64)
    fired = sig["fired"].to_numpy(dtype=bool)
    side_cont_arr = sig["side_cont"].to_numpy(dtype=np.float64)
    n = len(sig)

    trades_idx = np.where(fired)[0]
    rt_cost = 2.0 * cost_bps_per_side * 1e-4

    trade_dates = []
    trade_returns = []
    last_exit = -1

    for ent in trades_idx:
        if ent <= last_exit:
            # overlap suppression: ignore signals while a prior trade is open
            continue
        # Walk forward up to hold_days, but stop early if another fire happens
        target_exit = min(ent + hold_days, n - 1)
        # Check for early-exit fires in (ent+1 .. target_exit)
        actual_exit = target_exit
        for j in range(ent + 1, target_exit + 1):
            if fired[j]:
                actual_exit = j
                break
        side = side_cont_arr[ent] if direction == "cont" else -side_cont_arr[ent]
        if side == 0 or actual_exit <= ent:
            continue
        gross = side * (close[actual_exit] - close[ent]) / close[ent]
        net = gross - rt_cost
        trade_dates.append(sig.index[ent])
        trade_returns.append(net)
        last_exit = actual_exit

    s = pd.Series(trade_returns, index=pd.DatetimeIndex(trade_dates), name=direction)
    stats = {"trades": len(s), "fired_count": int(fired.sum())}
    return s, stats


def metric_block(label: str, r: pd.Series, trades_per_year_est: float) -> dict:
    if len(r) < 2:
        print(f"  {label:<32s} (insufficient trades: {len(r)})")
        return {"trades": len(r), "sharpe": 0.0, "mdd": 0.0, "total": 0.0,
                "cagr": 0.0, "wr": 0.0}
    eq = (1.0 + r).cumprod().to_numpy()
    sh = annualized_sharpe(r.to_numpy(), bars_per_year=trades_per_year_est)
    mdd = max_drawdown(eq)
    total = float(eq[-1] - 1.0)
    years = max(1e-9, (r.index[-1] - r.index[0]).days / 365.25)
    cagr = (1.0 + total) ** (1.0 / years) - 1.0
    wr = float((r > 0).mean())
    print(f"  {label:<32s} trades {len(r):>4d}  ret {total * 100:>+8.2f}%  "
          f"CAGR {cagr * 100:>+6.2f}%  Sh {sh:>+6.2f}  MDD {mdd * 100:>+7.2f}%  "
          f"WR {wr * 100:>5.1f}%")
    return {"trades": len(r), "sharpe": sh, "mdd": mdd, "total": total,
            "cagr": cagr, "wr": wr}


def kill_check(label: str, m: dict, fade_gap: float, cost_zero_sh: float,
               w4_sharpe: float) -> bool:
    def v(c: bool) -> str: return "PASS" if c else "FAIL"
    p1 = m['sharpe'] > 0.30
    p2 = abs(m['mdd']) < 0.20
    p3 = m['trades'] >= 100
    p4 = fade_gap > 0.40
    p5 = cost_zero_sh > 0.30
    p6 = w4_sharpe > 0.20    # institutionalization-decay pre-commit
    print(f"\n  Phase 2 kill criteria ({label}):")
    print(f"    Sharpe > +0.30 (10 bps)   : {v(p1)}  ({m['sharpe']:+.2f})")
    print(f"    MDD < 20%                 : {v(p2)}  ({m['mdd'] * 100:+.2f}%)")
    print(f"    Trades >= 100             : {v(p3)}  ({m['trades']})")
    print(f"    Fade-gap > +0.40          : {v(p4)}  ({fade_gap:+.2f})")
    print(f"    Cost-zero Sharpe > +0.30  : {v(p5)}  ({cost_zero_sh:+.2f})")
    print(f"    W4 Sharpe > +0.20         : {v(p6)}  ({w4_sharpe:+.2f})")
    overall = p1 and p2 and p3 and p4 and p5 and p6
    print(f"    OVERALL                   : {v(overall)}")
    return overall


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section(f"Loading {SYMBOL}")
    df = load_btc()
    print(f"  {SYMBOL:<8s} {len(df):>5,} bars  "
          f"{df.index[0].date()} -> {df.index[-1].date()}")

    section("Phase 2 -- baseline (10 bps, VOL_MULT=1.5, hold=3d, MIN_RET=1%)")
    sig = build_signals(df, BASE_ATR_LOOKBACK, BASE_VOL_MULT, BASE_MIN_RETURN_PCT)
    n_fired = int(sig['fired'].sum())
    print(f"  Vol-expansion fires (raw signal): {n_fired} days of {len(sig)}")
    print(f"  Mean TR/ATR ratio on fire days: {sig.loc[sig['fired'], 'tr_over_atr'].mean():.2f}")
    print(f"  Mean |return| on fire days:    {sig.loc[sig['fired'], 'ret_pct'].abs().mean():.2f}%")
    print()

    cont_ret, cont_stats = simulate(sig, "cont", BASE_HOLD_DAYS, BASE_COST_BPS)
    fade_ret, fade_stats = simulate(sig, "fade", BASE_HOLD_DAYS, BASE_COST_BPS)
    # Trades-per-year for Sharpe annualization (post-overlap-suppression)
    years = (df.index[-1] - df.index[0]).days / 365.25
    tpy = max(1.0, cont_stats['trades'] / max(years, 1e-9))
    print(f"  Effective trades/year for annualization: {tpy:.1f}")
    print()
    cont_m = metric_block("continuation (long if ret>0)", cont_ret, tpy)
    fade_m = metric_block("fade (long if ret<0)        ", fade_ret, tpy)

    # Cost-zero diagnostic
    cont_ret_cz, _ = simulate(sig, "cont", BASE_HOLD_DAYS, 0.0)
    fade_ret_cz, _ = simulate(sig, "fade", BASE_HOLD_DAYS, 0.0)
    cz_cont = annualized_sharpe(cont_ret_cz.to_numpy(), bars_per_year=tpy)
    cz_fade = annualized_sharpe(fade_ret_cz.to_numpy(), bars_per_year=tpy)
    print(f"\n  Cost-zero Sharpe (diagnostic):")
    print(f"    continuation @ 0 bps : {cz_cont:+.3f}")
    print(f"    fade        @ 0 bps : {cz_fade:+.3f}")

    best_dir = "cont" if cont_m['sharpe'] >= fade_m['sharpe'] else "fade"
    best_m = cont_m if best_dir == "cont" else fade_m
    best_cz = cz_cont if best_dir == "cont" else cz_fade
    fade_gap = abs(cont_m['sharpe'] - fade_m['sharpe'])
    print(f"\n  Best direction        : {best_dir}")
    print(f"  Fade gap              : {fade_gap:+.3f}")

    # ----- Phase 4 -- regime breakdown ---------------------------------
    section("Phase 4 -- regime breakdown (4 non-overlapping windows)")
    WINDOWS = [
        ("W1 2018-2019 (early retail)         ", "2018-01-01", "2019-12-31"),
        ("W2 2020-2021 (parabola + COVID)    ", "2020-01-01", "2021-12-31"),
        ("W3 2022-2023 (FTX + bear)           ", "2022-01-01", "2023-12-31"),
        ("W4 2024-2026 (ETF era / institut.) ", "2024-01-01", "2026-03-31"),
    ]
    w_rows = {"cont": [], "fade": []}
    for direction in ("cont", "fade"):
        print(f"\n  -- direction = {direction} --")
        for wname, ws, we in WINDOWS:
            sub_df = df.loc[ws:we]
            sub_sig = build_signals(sub_df, BASE_ATR_LOOKBACK, BASE_VOL_MULT,
                                    BASE_MIN_RETURN_PCT)
            r, _ = simulate(sub_sig, direction, BASE_HOLD_DAYS, BASE_COST_BPS)
            sub_years = (sub_df.index[-1] - sub_df.index[0]).days / 365.25
            sub_tpy = max(1.0, len(r) / max(sub_years, 1e-9))
            m = metric_block(wname, r, sub_tpy)
            w_rows[direction].append({"name": wname.strip(), **m})

    bd = best_dir
    w1_sh = w_rows[bd][0]['sharpe']
    w4_sh = w_rows[bd][3]['sharpe']
    decay = w1_sh - w4_sh
    print(f"\n  Decay diagnostic ({bd}): W1 {w1_sh:+.2f}, W4 {w4_sh:+.2f}, "
          f"diff {decay:+.2f}")
    w4_floor = w4_sh > 0.20
    print(f"    W4 Sharpe > +0.20 floor   : {'PASS' if w4_floor else 'FAIL'}  "
          f"({w4_sh:+.2f})")

    # Phase 2 kill check using W4 floor pulled in
    kill_check(bd, best_m, fade_gap, best_cz, w4_sh)

    # ----- Phase 5 -- parameter sensitivity (best direction) ----------
    section(f"Phase 5 -- parameter sensitivity (best direction = {bd})")

    print("  [Sweep 1] VOL_MULT (with hold=3, MIN_RET=1%)")
    print(f"  {'mult':>5s} {'fires':>6s} {'trades':>7s} {'Sharpe':>8s} {'MDD':>8s} {'CAGR':>8s}")
    for vm in (1.0, 1.25, 1.5, 2.0, 2.5):
        s_ = build_signals(df, BASE_ATR_LOOKBACK, vm, BASE_MIN_RETURN_PCT)
        r, st = simulate(s_, bd, BASE_HOLD_DAYS, BASE_COST_BPS)
        sub_tpy = max(1.0, len(r) / max(years, 1e-9))
        if len(r) >= 2:
            eq = (1.0 + r).cumprod().to_numpy()
            sh = annualized_sharpe(r.to_numpy(), bars_per_year=sub_tpy)
            mdd = max_drawdown(eq)
            cagr = (eq[-1]) ** (1.0 / max(years, 1e-9)) - 1.0
        else:
            sh = mdd = cagr = 0.0
        mark = " <<" if abs(vm - BASE_VOL_MULT) < 1e-6 else ""
        print(f"  {vm:>5.2f} {int(s_['fired'].sum()):>6d} {len(r):>7d} {sh:>+7.3f} "
              f"{mdd * 100:>+7.2f}% {cagr * 100:>+7.2f}%{mark}")

    print("\n  [Sweep 2] HOLD_DAYS (with VOL_MULT=1.5, MIN_RET=1%)")
    print(f"  {'hold':>5s} {'trades':>7s} {'Sharpe':>8s} {'MDD':>8s} {'CAGR':>8s}")
    for h in (1, 2, 3, 5, 7):
        r, _ = simulate(sig, bd, h, BASE_COST_BPS)
        sub_tpy = max(1.0, len(r) / max(years, 1e-9))
        if len(r) >= 2:
            eq = (1.0 + r).cumprod().to_numpy()
            sh = annualized_sharpe(r.to_numpy(), bars_per_year=sub_tpy)
            mdd = max_drawdown(eq)
            cagr = (eq[-1]) ** (1.0 / max(years, 1e-9)) - 1.0
        else:
            sh = mdd = cagr = 0.0
        mark = " <<" if h == BASE_HOLD_DAYS else ""
        print(f"  {h:>4d}d {len(r):>7d} {sh:>+7.3f} {mdd * 100:>+7.2f}% "
              f"{cagr * 100:>+7.2f}%{mark}")

    print("\n  [Sweep 3] cost (bps/side)")
    print(f"  {'cost':>5s} {'trades':>7s} {'Sharpe':>8s} {'MDD':>8s}")
    for c in (0.0, 5.0, 10.0, 15.0, 20.0, 30.0):
        r, _ = simulate(sig, bd, BASE_HOLD_DAYS, c)
        sub_tpy = max(1.0, len(r) / max(years, 1e-9))
        if len(r) >= 2:
            eq = (1.0 + r).cumprod().to_numpy()
            sh = annualized_sharpe(r.to_numpy(), bars_per_year=sub_tpy)
            mdd = max_drawdown(eq)
        else:
            sh = mdd = 0.0
        mark = " <<" if abs(c - BASE_COST_BPS) < 1e-6 else ""
        print(f"  {c:>5.1f}  {len(r):>7d} {sh:>+7.3f} {mdd * 100:>+7.2f}%{mark}")

    print("\n  [Sweep 4] MIN_RETURN_PCT")
    print(f"  {'min%':>5s} {'fires':>6s} {'trades':>7s} {'Sharpe':>8s} {'MDD':>8s}")
    for m in (0.0, 0.5, 1.0, 2.0, 3.0):
        s_ = build_signals(df, BASE_ATR_LOOKBACK, BASE_VOL_MULT, m)
        r, _ = simulate(s_, bd, BASE_HOLD_DAYS, BASE_COST_BPS)
        sub_tpy = max(1.0, len(r) / max(years, 1e-9))
        if len(r) >= 2:
            sh = annualized_sharpe(r.to_numpy(), bars_per_year=sub_tpy)
            mdd = max_drawdown((1.0 + r).cumprod().to_numpy())
        else:
            sh = mdd = 0.0
        mark = " <<" if abs(m - BASE_MIN_RETURN_PCT) < 1e-6 else ""
        print(f"  {m:>5.2f} {int(s_['fired'].sum()):>6d} {len(r):>7d} "
              f"{sh:>+7.3f} {mdd * 100:>+7.2f}%{mark}")

    # ----- Phase 6 -- walk-forward ------------------------------------
    section("Phase 6 -- walk-forward (5 rolling splits, best direction)")
    splits = [
        ("S1", "2018-01-01", "2020-12-31", "2021-01-01", "2022-12-31"),
        ("S2", "2019-01-01", "2021-12-31", "2022-01-01", "2023-12-31"),
        ("S3", "2020-01-01", "2022-12-31", "2023-01-01", "2024-12-31"),
        ("S4", "2021-01-01", "2023-12-31", "2024-01-01", "2025-12-31"),
        ("S5", "2022-01-01", "2024-12-31", "2025-01-01", "2026-03-31"),
    ]
    print(f"  {'split':<6s} {'IS window':<24s} {'OOS window':<24s} "
          f"{'IS Sh':>7s} {'OOS Sh':>7s} {'degrad':>7s} {'IS tr':>6s} {'OOS tr':>7s}")
    print("  " + "-" * 96)
    wf_rows = []
    for label, is_s, is_e, oos_s, oos_e in splits:
        is_sig = build_signals(df.loc[is_s:is_e], BASE_ATR_LOOKBACK, BASE_VOL_MULT,
                               BASE_MIN_RETURN_PCT)
        oos_sig = build_signals(df.loc[oos_s:oos_e], BASE_ATR_LOOKBACK, BASE_VOL_MULT,
                                BASE_MIN_RETURN_PCT)
        is_r, is_st = simulate(is_sig, bd, BASE_HOLD_DAYS, BASE_COST_BPS)
        oos_r, oos_st = simulate(oos_sig, bd, BASE_HOLD_DAYS, BASE_COST_BPS)
        is_y = (is_sig.index[-1] - is_sig.index[0]).days / 365.25
        oos_y = (oos_sig.index[-1] - oos_sig.index[0]).days / 365.25
        is_tpy = max(1.0, len(is_r) / max(is_y, 1e-9))
        oos_tpy = max(1.0, len(oos_r) / max(oos_y, 1e-9))
        is_sh = annualized_sharpe(is_r.to_numpy(), bars_per_year=is_tpy) if len(is_r) >= 2 else 0.0
        oos_sh = annualized_sharpe(oos_r.to_numpy(), bars_per_year=oos_tpy) if len(oos_r) >= 2 else 0.0
        degrad = is_sh - oos_sh
        wf_rows.append({"split": label, "is_sh": is_sh, "oos_sh": oos_sh,
                        "degrad": degrad})
        print(f"  {label:<6s} {is_s + '..' + is_e:<24s} {oos_s + '..' + oos_e:<24s} "
              f"{is_sh:>+7.2f} {oos_sh:>+7.2f} {degrad:>+7.3f} "
              f"{is_st['trades']:>6d} {oos_st['trades']:>7d}")

    degrads = [r['degrad'] for r in wf_rows]
    oos_shs = [r['oos_sh'] for r in wf_rows]
    mean_deg = float(np.mean(degrads))
    median_deg = float(np.median(degrads))
    splits_deg_pass = sum(1 for d in degrads if d < 0.5)
    splits_oos_pos = sum(1 for s in oos_shs if s > 0)
    nsp = len(wf_rows)
    print(f"\n  Mean degradation     : {mean_deg:+.3f}  "
          f"({'PASS' if mean_deg < 0.5 else 'FAIL'} -- need < 0.5)")
    print(f"  Median degradation   : {median_deg:+.3f}")
    print(f"  Splits w/ deg < 0.5  : {splits_deg_pass}/{nsp}  "
          f"({'PASS' if splits_deg_pass >= 3 else 'FAIL'} -- need >= 3)")
    print(f"  Splits w/ OOS Sh > 0 : {splits_oos_pos}/{nsp}  "
          f"({'PASS' if splits_oos_pos >= 3 else 'FAIL'} -- need >= 3)")
    wf_pass = mean_deg < 0.5 and splits_deg_pass >= 3 and splits_oos_pos >= 3
    print(f"\n  WALK-FORWARD OVERALL: {'PASS' if wf_pass else 'FAIL'}")

    # ----- Summary -----------------------------------------------------
    section("VERDICT SUMMARY")
    print(f"  Best direction              : {bd}")
    print(f"  Best Sharpe (10 bps)        : {best_m['sharpe']:+.2f}")
    print(f"  Fade gap                    : {fade_gap:+.2f}")
    print(f"  Cost-zero Sharpe (best dir) : {best_cz:+.2f}")
    print(f"  MDD                         : {best_m['mdd'] * 100:+.2f}%")
    print(f"  Trades                      : {best_m['trades']}")
    print(f"  W4 Sharpe (decay floor)     : {w4_sh:+.2f}")
    print(f"  W1-W4 decay                 : {decay:+.2f}")
    print(f"  Walk-forward mean deg       : {mean_deg:+.3f}")
    print(f"  Walk-forward OOS positive   : {splits_oos_pos}/{nsp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
