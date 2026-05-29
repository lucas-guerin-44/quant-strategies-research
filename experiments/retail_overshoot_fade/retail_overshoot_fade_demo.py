#!/usr/bin/env python3
"""Retail-concentrated single-name CFD overshoot fade — Phase 2 simulator.

Thesis: experiments/retail_overshoot_fade/retail_overshoot_fade.md

Mechanism:
  * Per ticker, per M5 RTH bar t: compute 1h intraday spike
    spike_pct = (close[t] - close[t - SPIKE_WINDOW]) / close[t - SPIKE_WINDOW]
  * On spike_pct > SPIKE_THRESHOLD (up-spike) AND cooldown OK:
      FADE direction (baseline): SHORT at NEXT bar open
      CONT direction (null):     LONG  at NEXT bar open
  * Exit on FIRST of:
      - stop hit (STOP_PCT adverse from entry)
      - time exit (HOLD_DAYS trading days elapsed since entry)
      - (optional) 50% retracement of the spike (target)
  * Cooldown: no re-entry on same name within COOLDOWN_DAYS.

Universe (Phase 0 reconciled):
  Thesis listed 12 retail-popular names; Eightcap MT5 only carries 7 of them.
  Missing on MT5: MARA, RIOT, GME, AMC, SOFI — Phase 0 finding, documented in
  the thesis red flags. The 7-name working universe is the operationally
  tradeable subset.

Cost: 30 bps RT default (spread + 2-day long-side CFD swap). Stress to 60 bps.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_EXPERIMENTS = _HERE.parent
_ROOT = _EXPERIMENTS.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT.parent / 'backtesting-engine-2.0'))

from data import fetch_ohlc  # noqa: E402


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Working universe — 7 of 12 thesis names that are on Eightcap MT5.
UNIVERSE = ['TSLA', 'NVDA', 'PLTR', 'COIN', 'MSTR', 'HOOD', 'RDDT']
UNIVERSE_MISSING = ['MARA', 'RIOT', 'GME', 'AMC', 'SOFI']  # not on broker, Phase 0

TIMEFRAME = 'M5'
START_DATE = '2019-01-01'
END_DATE = '2026-05-22'

# Baseline params (6 free, under 7-cap; UNIVERSE is universe-fixed).
SPIKE_THRESHOLD = 0.05    # 5% intraday move triggers entry
SPIKE_WINDOW = 12         # 12 * M5 = 1h spike window
HOLD_DAYS = 2             # exit after 2 trading days
STOP_PCT = 0.05           # 5% adverse move from entry = stop
COOLDOWN_DAYS = 5         # no re-entry on same name within 5d
COST_BPS_RT = 30.0        # spread + 2d long swap; stress to 60

# Regime windows (per CLAUDE.md 3-window convention; sample starts 2021-09).
REGIMES = [
    ('W1 2019-2020 pre/COVID', '2019-01-01', '2020-12-31'),
    ('W2 2021-2022 vol      ', '2021-01-01', '2022-12-31'),
    ('W3 2023-2026 holdout  ', '2023-01-01', '2026-12-31'),
]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f'\n{"=" * 80}\n  {t}\n{"=" * 80}\n')


def load_m5(symbol: str) -> pd.DataFrame:
    """Load RTH M5 bars (broker labels as UTC; cluster within US RTH window)."""
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f'No bars for {symbol} {TIMEFRAME}')
    df = raw[['timestamp', 'open', 'high', 'low', 'close']].copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.set_index('timestamp').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    return df


# ---------------------------------------------------------------------------
# Simulator (numpy inner loop)
# ---------------------------------------------------------------------------

@dataclass
class SimParams:
    direction: str = 'fade'           # 'fade' (short up-spike) or 'cont' (long)
    spike_thr: float = SPIKE_THRESHOLD
    window: int = SPIKE_WINDOW
    hold_days: int = HOLD_DAYS
    stop_pct: float = STOP_PCT
    cooldown_days: int = COOLDOWN_DAYS
    cost_bps_rt: float = COST_BPS_RT
    use_target: bool = False
    target_retrace: float = 0.5


def simulate_one(ticker: str, df: pd.DataFrame, p: SimParams) -> list[dict]:
    """Per-ticker numpy state machine. Returns trade dicts."""
    if df.empty or len(df) < p.window + 2:
        return []

    ts = df.index.values  # datetime64[ns, UTC]
    o = df['open'].to_numpy(np.float64)
    h = df['high'].to_numpy(np.float64)
    l = df['low'].to_numpy(np.float64)
    c = df['close'].to_numpy(np.float64)

    # Day index per bar (broker bars are within-day; .normalize gives UTC date).
    # Use np.unique on normalized index to be unit-agnostic (pandas 2.x default
    # is datetime64[us, UTC] for fetched bars; .asi8 returns raw int in that unit).
    _, day_int = np.unique(df.index.normalize().to_numpy(), return_inverse=True)
    day_int = day_int.astype(np.int64)

    sign = -1.0 if p.direction == 'fade' else +1.0
    cost = p.cost_bps_rt / 1e4
    n = len(df)

    trades: list[dict] = []
    last_exit_day = -(10 ** 9)  # cooldown tracker (in day_int units)

    i = p.window
    while i < n - 1:
        t0 = i - p.window
        # Spike window must be within same trading day.
        if day_int[t0] != day_int[i]:
            i += 1
            continue

        base = c[t0]
        if base <= 0 or not np.isfinite(base):
            i += 1
            continue
        spike_pct = (c[i] - base) / base

        # Trigger: up-spike only (we fade up-spikes, or long-extend the up).
        if spike_pct <= p.spike_thr:
            i += 1
            continue

        # Cooldown.
        if (day_int[i] - last_exit_day) <= p.cooldown_days:
            i += 1
            continue

        # Entry at next bar open (realistic; never at signal bar close).
        entry_i = i + 1
        if entry_i >= n:
            break
        entry_px = o[entry_i]
        if entry_px <= 0 or not np.isfinite(entry_px):
            i += 1
            continue

        spike_dollar = c[i] - base
        if p.direction == 'fade':
            stop_px = entry_px * (1.0 + p.stop_pct)
            target_px = entry_px - p.target_retrace * spike_dollar
        else:
            stop_px = entry_px * (1.0 - p.stop_pct)
            target_px = entry_px + p.target_retrace * spike_dollar

        entry_day = day_int[entry_i]
        exit_day_thr = entry_day + p.hold_days

        # Walk forward.
        j = entry_i
        exit_px = np.nan
        exit_reason = 'time'
        while j < n:
            if p.direction == 'fade':
                if h[j] >= stop_px:
                    exit_px = stop_px
                    exit_reason = 'stop'
                    break
                if p.use_target and l[j] <= target_px:
                    exit_px = target_px
                    exit_reason = 'target'
                    break
            else:
                if l[j] <= stop_px:
                    exit_px = stop_px
                    exit_reason = 'stop'
                    break
                if p.use_target and h[j] >= target_px:
                    exit_px = target_px
                    exit_reason = 'target'
                    break
            if day_int[j] >= exit_day_thr:
                exit_px = c[j]
                exit_reason = 'time'
                break
            j += 1
        if not np.isfinite(exit_px):
            j = n - 1
            exit_px = c[j]
            exit_reason = 'eod_data'

        ret = sign * (exit_px - entry_px) / entry_px - cost
        trades.append({
            'ticker': ticker,
            'entry_ts': pd.Timestamp(ts[entry_i]),
            'exit_ts': pd.Timestamp(ts[j]),
            'entry_px': float(entry_px),
            'exit_px': float(exit_px),
            'spike_pct': float(spike_pct),
            'ret': float(ret),
            'reason': exit_reason,
            'days_held': int(day_int[j] - entry_day),
        })
        last_exit_day = int(day_int[j])
        i = j + 1

    return trades


def simulate_basket(cache: dict[str, pd.DataFrame], p: SimParams) -> pd.DataFrame:
    rows: list[dict] = []
    for tk in UNIVERSE:
        rows.extend(simulate_one(tk, cache[tk], p))
    if not rows:
        return pd.DataFrame(columns=[
            'ticker', 'entry_ts', 'exit_ts', 'entry_px', 'exit_px',
            'spike_pct', 'ret', 'reason', 'days_held'
        ])
    df = pd.DataFrame(rows).sort_values('entry_ts').reset_index(drop=True)
    df['entry_ts'] = pd.to_datetime(df['entry_ts'], utc=True)
    df['exit_ts'] = pd.to_datetime(df['exit_ts'], utc=True)
    return df


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def max_drawdown(eq: np.ndarray) -> float:
    if eq.size == 0:
        return 0.0
    rm = np.maximum.accumulate(eq)
    dd = (eq - rm) / rm
    return float(dd.min())


def equity_curve(trades: pd.DataFrame) -> np.ndarray:
    """Equal-weight per-trade compounded equity curve (1/N sizing per trade)."""
    if trades.empty:
        return np.array([1.0])
    rets = trades['ret'].to_numpy()
    # Compound assuming sequentially-sized at 1/n_universe-of-tickers per leg;
    # simple proxy is full-notional per trade. Use full-notional → naive Sharpe.
    eq = np.cumprod(1.0 + rets)
    return eq


def trade_sharpe(rets: np.ndarray, trades_per_year: float) -> float:
    rets = rets[np.isfinite(rets)]
    if rets.size < 2:
        return 0.0
    std = rets.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(rets.mean() / std * np.sqrt(trades_per_year))


def annualized_trade_rate(trades: pd.DataFrame) -> float:
    if trades.empty:
        return 0.0
    span_days = (trades['entry_ts'].max() - trades['entry_ts'].min()).total_seconds() / 86400.0
    if span_days <= 0:
        return 0.0
    return len(trades) / (span_days / 365.25)


def report(label: str, trades: pd.DataFrame) -> dict:
    if trades.empty:
        print(f'  [{label}] no trades')
        return {'label': label, 'sharpe': 0.0, 'mdd': 0.0, 'n': 0, 'wr': 0.0, 'pf': 0.0, 'cagr': 0.0}
    rets = trades['ret'].to_numpy()
    rate = annualized_trade_rate(trades)
    sh = trade_sharpe(rets, trades_per_year=max(rate, 1.0))
    eq = equity_curve(trades)
    mdd = max_drawdown(eq)
    wr = float((rets > 0).mean())
    gw = float(rets[rets > 0].sum())
    gl = float(-rets[rets <= 0].sum())
    pf = gw / gl if gl > 0 else float('inf')
    span_days = (trades['entry_ts'].max() - trades['entry_ts'].min()).total_seconds() / 86400.0
    years = max(span_days / 365.25, 1e-9)
    total = float(eq[-1] - 1.0)
    cagr = (1 + total) ** (1 / years) - 1
    print(f'  [{label}]')
    print(f'    period   : {trades["entry_ts"].min().date()} -> {trades["entry_ts"].max().date()} ({years:.1f}y)')
    print(f'    Sharpe   : {sh:+.2f}   (annualized at {rate:.1f} trades/yr)')
    print(f'    Max DD   : {mdd*100:+.2f}%')
    print(f'    trades   : {len(trades)}  ({rate:.1f}/yr)')
    print(f'    CAGR     : {cagr*100:+.2f}%')
    print(f'    WR       : {wr*100:.1f}%   PF: {pf:.2f}')
    return {
        'label': label, 'sharpe': sh, 'mdd': mdd, 'n': len(trades),
        'wr': wr, 'pf': pf, 'cagr': cagr, 'rate_yr': rate,
    }


def kill_check(label: str, trades: pd.DataFrame, n_floor: int = 100) -> None:
    if trades.empty:
        print(f'  [{label}] no trades — KILL')
        return
    rets = trades['ret'].to_numpy()
    rate = annualized_trade_rate(trades)
    sh = trade_sharpe(rets, max(rate, 1.0))
    eq = equity_curve(trades)
    mdd = max_drawdown(eq)
    n = len(trades)
    v = lambda ok: 'PASS' if ok else 'FAIL'
    print(f'  [{label}]')
    print(f'    Sharpe >= +0.30 net    : {v(sh >= 0.30)}  ({sh:+.2f})')
    print(f'    Max DD < 25%           : {v(abs(mdd) < 0.25)}  ({mdd*100:+.2f}%)')
    print(f'    Trades >= {n_floor:>3d}        : {v(n >= n_floor)}  ({n})')


def regime_breakdown(trades: pd.DataFrame) -> None:
    if trades.empty:
        print('  no trades')
        return
    for label, s, e in REGIMES:
        sub = trades[(trades['entry_ts'] >= pd.Timestamp(s, tz='UTC')) &
                     (trades['entry_ts'] <= pd.Timestamp(e, tz='UTC'))]
        if len(sub) < 5:
            print(f'  {label:<26s} n={len(sub):>4d}  (insufficient)')
            continue
        rets = sub['ret'].to_numpy()
        rate = annualized_trade_rate(sub)
        sh = trade_sharpe(rets, max(rate, 1.0))
        eq = equity_curve(sub)
        mdd = max_drawdown(eq)
        wr = (rets > 0).mean()
        print(f'  {label:<26s} n={len(sub):>4d}  Sh {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  WR {wr*100:>5.1f}%')


def per_name(trades: pd.DataFrame) -> int:
    """Return count of names with cost-zero Sharpe > 0."""
    if trades.empty:
        return 0
    n_pos = 0
    print(f'  {"ticker":<7s} {"n":>4s}  {"Sh(net)":>8s}  {"Sh(gross)":>10s}  {"WR":>6s}  {"avg_ret":>9s}')
    for tk in UNIVERSE:
        sub = trades[trades['ticker'] == tk]
        if sub.empty:
            print(f'  {tk:<7s} (no trades)')
            continue
        rets = sub['ret'].to_numpy()
        # gross = strip the cost back out
        rate = annualized_trade_rate(sub)
        sh_net = trade_sharpe(rets, max(rate, 1.0))
        gross = rets + COST_BPS_RT / 1e4  # add cost back for gross
        sh_gross = trade_sharpe(gross, max(rate, 1.0))
        wr = (rets > 0).mean()
        avg = rets.mean() * 100
        if sh_gross > 0:
            n_pos += 1
        print(f'  {tk:<7s} {len(sub):>4d}  {sh_net:>+7.2f}  {sh_gross:>+9.2f}  {wr*100:>5.1f}%  {avg:>+7.2f}%')
    return n_pos


def walk_forward(cache: dict[str, pd.DataFrame]) -> tuple[float, float]:
    """3-fold rolling walk-forward; anchored to data span."""
    splits = [
        ('2021-09-01', '2023-01-01', '2024-06-01'),  # IS 1.3y / OOS 1.4y
        ('2022-01-01', '2024-01-01', '2025-06-01'),  # IS 2.0y / OOS 1.4y
        ('2023-01-01', '2025-01-01', '2026-05-21'),  # IS 2.0y / OOS 1.4y
    ]
    p = SimParams(direction='fade')
    ev_full = simulate_basket(cache, p)
    if ev_full.empty:
        print('  no trades — skip walk-forward')
        return 0.0, 0.0
    print(f'  {"split":<40s} {"IS Sh":>8s} {"OOS Sh":>8s} {"OOS n":>7s} {"OOS MDD":>10s}')
    oos = []
    for is_s, is_e, oos_e in splits:
        is_m = (ev_full['entry_ts'] >= pd.Timestamp(is_s, tz='UTC')) & (ev_full['entry_ts'] < pd.Timestamp(is_e, tz='UTC'))
        oos_m = (ev_full['entry_ts'] >= pd.Timestamp(is_e, tz='UTC')) & (ev_full['entry_ts'] <= pd.Timestamp(oos_e, tz='UTC'))
        is_t = ev_full[is_m]
        oos_t = ev_full[oos_m]
        is_sh = trade_sharpe(is_t['ret'].to_numpy(), max(annualized_trade_rate(is_t), 1.0)) if not is_t.empty else 0.0
        if oos_t.empty:
            oos_sh = 0.0; oos_mdd = 0.0
        else:
            oos_sh = trade_sharpe(oos_t['ret'].to_numpy(), max(annualized_trade_rate(oos_t), 1.0))
            oos_mdd = max_drawdown(equity_curve(oos_t)) * 100
        print(f'  IS {is_s[:7]}->{is_e[:7]} / OOS->{oos_e[:7]}      '
              f'{is_sh:>+7.2f}  {oos_sh:>+7.2f}  {len(oos_t):>7d}  {oos_mdd:>+8.2f}%')
        oos.append(oos_sh)
    mean_oos = float(np.mean(oos))
    min_oos = float(np.min(oos))
    print(f'\n  Walk-forward mean OOS Sharpe: {mean_oos:+.2f}  (kill if < +0.20)')
    print(f'  Walk-forward min  OOS Sharpe: {min_oos:+.2f}  (kill if < -0.10)')
    return mean_oos, min_oos


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section('Retail-overshoot fade — Phase 2 (CFD multi-day FADE on retail-heavy single names)')
    print(f'  Working universe ({len(UNIVERSE)}): {", ".join(UNIVERSE)}')
    print(f'  Missing on broker  ({len(UNIVERSE_MISSING)}): {", ".join(UNIVERSE_MISSING)}')
    print(f'  Baseline params: spike>{SPIKE_THRESHOLD*100:.0f}% in {SPIKE_WINDOW} bars, '
          f'hold={HOLD_DAYS}d, stop={STOP_PCT*100:.0f}%, cooldown={COOLDOWN_DAYS}d, cost={COST_BPS_RT}bp RT')

    # Load all data once.
    cache: dict[str, pd.DataFrame] = {}
    for tk in UNIVERSE:
        df = load_m5(tk)
        cache[tk] = df
        print(f'  {tk:<6s} {len(df):>7d} bars  {df.index[0].date()} -> {df.index[-1].date()}')

    # ------------------------------------------------------------------
    # Baseline FADE
    # ------------------------------------------------------------------
    section('Baseline FADE — short on >5% / 1h spike, 2-day hold, 5% stop, 30bp RT')
    ev_fade = simulate_basket(cache, SimParams(direction='fade'))
    base = report('baseline FADE', ev_fade)

    section('Phase 2 kill criteria — basket')
    kill_check('baseline FADE', ev_fade, n_floor=100)

    section('Regime breakdown — FADE')
    regime_breakdown(ev_fade)

    # ------------------------------------------------------------------
    # Direction null-check: CONTINUATION
    # ------------------------------------------------------------------
    section('Direction null-check — CONT (long the spike)')
    ev_cont = simulate_basket(cache, SimParams(direction='cont'))
    cont = report('null CONT', ev_cont)
    rate_fade = max(annualized_trade_rate(ev_fade), 1.0)
    rate_cont = max(annualized_trade_rate(ev_cont), 1.0)
    sh_fade = trade_sharpe(ev_fade['ret'].to_numpy(), rate_fade) if not ev_fade.empty else 0.0
    sh_cont = trade_sharpe(ev_cont['ret'].to_numpy(), rate_cont) if not ev_cont.empty else 0.0
    gap = sh_fade - sh_cont
    print(f'\n  Direction-gap (FADE - CONT) = {gap:+.2f}  (kill if < +0.30)')
    if gap >= 0.30:
        verdict_dir = 'PASS — fade direction has decisive directional content'
    elif gap <= -0.30:
        verdict_dir = 'INVERTED — continuation wins (lesson #43 generalizes multi-day)'
    else:
        verdict_dir = 'FAIL — no decisive direction (|gap| < 0.30)'
    print(f'  -> {verdict_dir}')

    # ------------------------------------------------------------------
    # Per-name breakdown
    # ------------------------------------------------------------------
    section('Per-name breakdown — FADE')
    n_pos = per_name(ev_fade)
    # Floor adapted to 7-name working universe: was "6 of 12", now ">= 4 of 7" (~57%).
    n_floor = max(4, int(np.ceil(0.55 * len(UNIVERSE))))
    print(f'\n  Names with cost-zero (gross) Sharpe > 0: {n_pos}/{len(UNIVERSE)}  '
          f'(kill if < {n_floor})')

    # ------------------------------------------------------------------
    # Variant sweep — SPIKE_THRESHOLD
    # ------------------------------------------------------------------
    section('Variant sweep — SPIKE_THRESHOLD (FADE)')
    for thr in (0.03, 0.04, 0.05, 0.06, 0.08, 0.10):
        ev = simulate_basket(cache, SimParams(direction='fade', spike_thr=thr))
        if ev.empty:
            print(f'  thr={thr*100:>4.1f}%  no trades'); continue
        rate = annualized_trade_rate(ev)
        sh = trade_sharpe(ev['ret'].to_numpy(), max(rate, 1.0))
        mdd = max_drawdown(equity_curve(ev))
        print(f'  thr={thr*100:>4.1f}%  Sh {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  n {len(ev):>4d}  rate {rate:>5.1f}/yr')

    # ------------------------------------------------------------------
    # Variant sweep — HOLD_DAYS
    # ------------------------------------------------------------------
    section('Variant sweep — HOLD_DAYS (FADE)')
    for hd in (1, 2, 3, 5):
        # Adjust cost roughly: 7 bp swap/yr → ~2 bp/day; baseline COST already includes 2d
        # but be honest: for hd days, swap component ≈ 2*hd bp per side, so RT swap ≈ 4*hd bp.
        # Use floor 20 bp (spread) + 4*hd swap.
        cost = 20.0 + 4.0 * hd
        ev = simulate_basket(cache, SimParams(direction='fade', hold_days=hd, cost_bps_rt=cost))
        if ev.empty:
            print(f'  hd={hd}d (cost={cost:>4.0f}bp)  no trades'); continue
        rate = annualized_trade_rate(ev)
        sh = trade_sharpe(ev['ret'].to_numpy(), max(rate, 1.0))
        mdd = max_drawdown(equity_curve(ev))
        print(f'  hd={hd}d (cost={cost:>4.0f}bp)  Sh {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  n {len(ev):>4d}')

    # ------------------------------------------------------------------
    # Variant sweep — STOP_PCT
    # ------------------------------------------------------------------
    section('Variant sweep — STOP_PCT (FADE)')
    for sp in (0.03, 0.05, 0.08, 0.10, 0.15):
        ev = simulate_basket(cache, SimParams(direction='fade', stop_pct=sp))
        if ev.empty:
            print(f'  stop={sp*100:>4.1f}%  no trades'); continue
        rate = annualized_trade_rate(ev)
        sh = trade_sharpe(ev['ret'].to_numpy(), max(rate, 1.0))
        mdd = max_drawdown(equity_curve(ev))
        wr = (ev['ret'] > 0).mean()
        print(f'  stop={sp*100:>4.1f}%  Sh {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  WR {wr*100:>5.1f}%  n {len(ev):>4d}')

    # ------------------------------------------------------------------
    # Variant sweep — COOLDOWN_DAYS
    # ------------------------------------------------------------------
    section('Variant sweep — COOLDOWN_DAYS (FADE)')
    for cd in (0, 1, 3, 5, 10):
        ev = simulate_basket(cache, SimParams(direction='fade', cooldown_days=cd))
        if ev.empty:
            print(f'  cd={cd}d  no trades'); continue
        rate = annualized_trade_rate(ev)
        sh = trade_sharpe(ev['ret'].to_numpy(), max(rate, 1.0))
        mdd = max_drawdown(equity_curve(ev))
        print(f'  cd={cd}d  Sh {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  n {len(ev):>4d}')

    # ------------------------------------------------------------------
    # Cost sensitivity
    # ------------------------------------------------------------------
    section('Cost sensitivity (FADE)')
    for c in (0.0, 15.0, 30.0, 40.0, 60.0, 100.0):
        ev = simulate_basket(cache, SimParams(direction='fade', cost_bps_rt=c))
        if ev.empty:
            print(f'  cost={c:>5.1f}bp  no trades'); continue
        rate = annualized_trade_rate(ev)
        sh = trade_sharpe(ev['ret'].to_numpy(), max(rate, 1.0))
        mdd = max_drawdown(equity_curve(ev))
        print(f'  cost={c:>5.1f}bp  Sh {sh:>+6.2f}  MDD {mdd*100:>+7.2f}%  n {len(ev):>4d}')

    # ------------------------------------------------------------------
    # Walk-forward
    # ------------------------------------------------------------------
    section('Walk-forward (3 rolling splits)')
    mean_oos, min_oos = walk_forward(cache)

    # ------------------------------------------------------------------
    # Summary verdict
    # ------------------------------------------------------------------
    section('Summary verdict')
    # Re-run regime W3 specifically (kill if W3 Sh <= 0).
    w3_label, w3_s, w3_e = REGIMES[2]
    w3 = ev_fade[(ev_fade['entry_ts'] >= pd.Timestamp(w3_s, tz='UTC')) &
                 (ev_fade['entry_ts'] <= pd.Timestamp(w3_e, tz='UTC'))]
    w3_sh = trade_sharpe(w3['ret'].to_numpy(), max(annualized_trade_rate(w3), 1.0)) if not w3.empty else 0.0
    # Cost-stress at 60 bp.
    ev_60 = simulate_basket(cache, SimParams(direction='fade', cost_bps_rt=60.0))
    sh_60 = trade_sharpe(ev_60['ret'].to_numpy(), max(annualized_trade_rate(ev_60), 1.0)) if not ev_60.empty else 0.0

    print(f'  retail_overshoot_fade Phase 2 results:')
    print(f'    baseline FADE Sharpe   : {base["sharpe"]:+.2f}  (kill if < +0.30)')
    print(f'    baseline FADE MDD      : {base["mdd"]*100:+.2f}%  (kill if > 25%)')
    print(f'    trades                 : {base["n"]}      (kill if < 100)')
    print(f'    W3 holdout Sharpe      : {w3_sh:+.2f}  (kill if <= 0.00)')
    print(f'    direction gap          : {gap:+.2f}  (kill if < +0.30)')
    print(f'    cost-stress 60bp Sh    : {sh_60:+.2f}  (kill if <= 0)')
    print(f'    walk-fwd mean OOS Sh   : {mean_oos:+.2f}  (kill if < +0.20)')
    print(f'    walk-fwd min  OOS Sh   : {min_oos:+.2f}  (kill if < -0.10)')
    print(f'    positive names (gross) : {n_pos}/{len(UNIVERSE)}  (kill if < {n_floor})')

    fails = []
    if base['sharpe'] < 0.30: fails.append('Sharpe')
    if abs(base['mdd']) > 0.25: fails.append('MDD')
    if base['n'] < 100: fails.append('trade-count')
    if w3_sh <= 0.0: fails.append('W3-holdout')
    if gap < 0.30: fails.append('direction-gap')
    if sh_60 <= 0.0: fails.append('cost-stress')
    if mean_oos < 0.20: fails.append('walk-fwd-mean')
    if min_oos < -0.10: fails.append('walk-fwd-min')
    if n_pos < n_floor: fails.append('per-name-diag')

    if not fails:
        print('\n  -> PASS: all kill criteria cleared. Phase 3 controls next.')
    else:
        print(f'\n  -> REJECT: failed [{", ".join(fails)}]')
    return 0


if __name__ == '__main__':
    sys.exit(main())
