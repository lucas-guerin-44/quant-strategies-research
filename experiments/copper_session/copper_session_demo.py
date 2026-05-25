#!/usr/bin/env python3
"""XCUUSD overnight Asia-handoff hold (Variant C: 23:00 UTC -> 08:00 UTC, 9h).

Thesis: experiments/copper_session/copper_session.md (pre-committed 2026-05-24).

Mechanism (Driver A pre-commit): Asian industrial-flow accumulation. Chinese
property close + Asian electronics manufacturing demand + LME copper warrant
flow into 08 UTC London open. Pre-commit: LONG Variant C.

Direction null-check is co-equal (per lesson #54). If SHORT wins, verdict
flips to PASS-SHORT / REJECT-LONG (Driver B was right — professional-
electronic decay like WTI).

Data caveat: W4-only (2024-02-06 onward, ~2.3y). No regime stability check
possible — Eightcap server-side history hard-cap.

Run:
  venv/Scripts/python.exe experiments/copper_session/copper_session_demo.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
DATA_PATH = os.path.join(_ROOT, 'ohlc_data', 'XCUUSD_H1.csv')

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENTRY_HOUR = 23
EXIT_HOUR = 8
ENTRY_IS_PRIOR_DAY = True

NY_START_HOUR = 13
NY_END_HOUR = 21
ATR_DAYS = 20

# Copper CFD is materially wider than XAU. Eightcap quoted ~5pip = 0.05c
# ~ 8bp half-spread at $6.30 spot. Default realistic 5bp RT; stress at 12bp.
COST_BPS_DEFAULT = 5.0
COST_BPS_SWEEP = (0.0, 3.0, 5.0, 8.0, 12.0)

TRADES_PER_YEAR_ANNUAL = 250

# Pre-committed kill criteria (W4-only adjusted, per thesis 2026-05-24)
KC_SHARPE_W4 = 0.50
KC_MDD = 0.15
KC_TRADES = 200
KC_FADE_GAP = 0.60
KC_CONTROL_GAP = 0.40
KC_COST_STRESS_BP = 8.0
KC_DOW_MAX_SHARE = 0.50
KC_WF_DEG = 0.70


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(t: str) -> None:
    print(f'\n{"=" * 92}\n  {t}\n{"=" * 92}\n')


def annualized_sharpe(r: np.ndarray, trades_per_year: float = TRADES_PER_YEAR_ANNUAL) -> float:
    r = r[np.isfinite(r)]
    if r.size < 2:
        return 0.0
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(trades_per_year))


def max_drawdown(eq: np.ndarray) -> float:
    if len(eq) == 0:
        return 0.0
    rm = np.maximum.accumulate(eq)
    dd = (eq - rm) / rm
    return float(dd.min())


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_h1() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, parse_dates=['timestamp'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.sort_values('timestamp').reset_index(drop=True)
    df['hour'] = df['timestamp'].dt.hour
    df['date'] = df['timestamp'].dt.normalize()
    return df


def build_ny_summary(df: pd.DataFrame) -> pd.DataFrame:
    ny_mask = (df['hour'] >= NY_START_HOUR) & (df['hour'] < NY_END_HOUR)
    ny = df.loc[ny_mask].copy()
    g = ny.groupby('date')
    out = pd.DataFrame({
        'ny_open': g['open'].first(),
        'ny_close': g['close'].last(),
        'ny_n_bars': g.size(),
    })
    out['ny_ret_pct'] = (out['ny_close'] - out['ny_open']) / out['ny_open'] * 100.0
    out = out.sort_index()
    out['ny_atr_pct'] = (
        out['ny_ret_pct']
        .rolling(ATR_DAYS, min_periods=max(2, ATR_DAYS // 2))
        .std(ddof=1)
        .shift(1)
    )
    return out


# ---------------------------------------------------------------------------
# Phase 0 — hour-of-day profile
# ---------------------------------------------------------------------------

def hour_of_day_profile(df: pd.DataFrame) -> None:
    """Mean H1 return per UTC hour with t-stat."""
    df = df.copy()
    df['ret_pct'] = (df['close'] - df['open']) / df['open'] * 100.0
    print(f'  {"hr":>3s} {"n":>6s} {"mean%":>10s} {"std%":>8s} {"t":>7s} {"sharpe":>8s}')
    print('  ' + '-' * 55)
    for h in range(24):
        sub = df.loc[df['hour'] == h, 'ret_pct'].dropna().to_numpy()
        if len(sub) < 30:
            continue
        mean = sub.mean()
        std = sub.std(ddof=1)
        if std == 0:
            continue
        t = mean / (std / np.sqrt(len(sub)))
        sh = mean / std * np.sqrt(252 * 24)  # H1 -> annualized
        flag = ''
        if t > 2.0:
            flag = '  <-- t>+2'
        elif t < -2.0:
            flag = '  <-- t<-2'
        print(f'  {h:>3d} {len(sub):>6d} {mean:>+10.5f} {std:>8.4f} {t:>+7.2f} {sh:>+8.2f}{flag}')


# ---------------------------------------------------------------------------
# Simulator (Variant C window-defined, any entry/exit hour)
# ---------------------------------------------------------------------------

def simulate(
    df: pd.DataFrame,
    ny: pd.DataFrame,
    entry_hour: int = ENTRY_HOUR,
    exit_hour: int = EXIT_HOUR,
    entry_is_prior_day: bool = True,
    direction: str = 'long',
    cost_bps: float = COST_BPS_DEFAULT,
) -> tuple[pd.Series, list[dict]]:
    """Build per-trade return series. Entry at entry_hour close (UTC),
    exit at exit_hour close. entry_is_prior_day=True means entry is the
    day BEFORE the exit-day (overnight hold). cost_bps is RT in bps.
    direction in {'long', 'short'}.
    """
    closes = df.set_index(['date', 'hour'])['close']
    trade_dates = sorted(df.loc[df['hour'] == exit_hour, 'date'].unique())

    one_day = pd.Timedelta(days=1)
    rows = []
    cost_pct = cost_bps / 10000.0
    for d in trade_dates:
        d = pd.Timestamp(d)
        entry_date = d - one_day if entry_is_prior_day else d
        try:
            entry_close = closes.loc[(entry_date, entry_hour)]
            exit_close = closes.loc[(d, exit_hour)]
        except KeyError:
            continue

        gross_pct = (exit_close - entry_close) / entry_close
        if direction == 'long':
            net_pct = gross_pct - cost_pct
        else:
            net_pct = -gross_pct - cost_pct

        rows.append({
            'date': d,
            'entry_close': float(entry_close),
            'exit_close': float(exit_close),
            'gross_pct': gross_pct,
            'net_pct': net_pct,
            'dow': d.day_name(),
        })

    if not rows:
        return pd.Series(dtype=float, name='ret'), []

    trades_df = pd.DataFrame(rows)
    ret = pd.Series(trades_df['net_pct'].to_numpy(), index=pd.to_datetime(trades_df['date']),
                    name='ret')
    return ret, trades_df.to_dict('records')


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_run(label: str, ret: pd.Series) -> dict:
    if len(ret) == 0:
        print(f'  [{label}]: empty')
        return {}
    r = ret.to_numpy()
    eq = (1.0 + r).cumprod()
    n = len(r)
    years = (ret.index[-1] - ret.index[0]).days / 365.25
    total = float(eq[-1] - 1.0)
    cagr = (1 + total) ** (1 / max(years, 1e-9)) - 1
    tpy = n / max(years, 1e-9)
    sh = annualized_sharpe(r, trades_per_year=tpy)
    mdd = max_drawdown(eq)
    mean_pct = r.mean()
    wins = r[r > 0]
    losses = r[r <= 0]
    wr = len(wins) / n if n else 0.0
    gw = float(wins.sum()) if len(wins) else 0.0
    gl = float(-losses.sum()) if len(losses) else 0.0
    pf = gw / gl if gl > 0 else float('inf')

    print(f'  [{label}]')
    print(f'    period      : {ret.index[0].date()} -> {ret.index[-1].date()} ({years:.2f}y)')
    print(f'    total ret   : {total * 100:+.2f}%')
    print(f'    CAGR        : {cagr * 100:+.2f}%')
    print(f'    Sharpe      : {sh:+.2f}')
    print(f'    Max DD      : {mdd * 100:+.2f}%')
    print(f'    trades      : {n}  ({tpy:.0f}/yr)')
    print(f'    win rate    : {wr * 100:.1f}%')
    print(f'    profit fac. : {pf:.2f}')
    print(f'    mean/trade  : {mean_pct * 100:+.4f}%')
    return {'sharpe': sh, 'mdd': mdd, 'cagr': cagr, 'n': n, 'wr': wr, 'pf': pf,
            'mean': mean_pct, 'tpy': tpy}


def cost_sweep(df: pd.DataFrame, ny: pd.DataFrame, label: str,
               entry_hour: int, exit_hour: int, direction: str = 'long') -> None:
    print(f'  [{label} — cost sweep]')
    for cb in COST_BPS_SWEEP:
        ret, _ = simulate(df, ny, entry_hour=entry_hour, exit_hour=exit_hour,
                          direction=direction, cost_bps=cb)
        if len(ret) == 0:
            continue
        r = ret.to_numpy()
        eq = (1 + r).cumprod()
        years = (ret.index[-1] - ret.index[0]).days / 365.25
        tpy = len(r) / max(years, 1e-9)
        sh = annualized_sharpe(r, trades_per_year=tpy)
        mdd = max_drawdown(eq)
        cagr = (1 + (float(eq[-1]) - 1)) ** (1 / max(years, 1e-9)) - 1
        flag = ''
        if cb == COST_BPS_DEFAULT:
            flag = ' (deploy)'
        elif cb == KC_COST_STRESS_BP:
            flag = ' (stress)'
        print(f'    cost={cb:>4.1f}bp  Sharpe {sh:>+6.2f}  CAGR {cagr * 100:>+6.2f}%  '
              f'MDD {mdd * 100:>+7.2f}%  n={len(r)}{flag}')


def control_hold(df: pd.DataFrame, ny: pd.DataFrame, direction: str = 'long') -> dict:
    """Run identical 9-hour holds during NY-hours and London-hours."""
    print(f'  Control-hold check (direction={direction}, cost={COST_BPS_DEFAULT}bp RT)')
    print(f'  {"window":<28s} {"entry":>5s} {"exit":>4s} {"n":>5s} {"Sh":>7s} {"mean%":>8s}')
    print('  ' + '-' * 65)
    windows = [
        ('Variant C (Asia handoff)', 23, 8, True),
        ('Control NY (11->20)', 11, 20, False),
        ('Control LDN (06->15)', 6, 15, False),
        ('Control mid-Asia (02->11)', 2, 11, False),
    ]
    out = {}
    for name, eh, xh, prior in windows:
        ret, _ = simulate(df, ny, entry_hour=eh, exit_hour=xh,
                          entry_is_prior_day=prior, direction=direction,
                          cost_bps=COST_BPS_DEFAULT)
        if len(ret) == 0:
            continue
        r = ret.to_numpy()
        years = (ret.index[-1] - ret.index[0]).days / 365.25
        sh = annualized_sharpe(r, trades_per_year=len(r) / max(years, 1e-9))
        mean = r.mean() * 100.0
        out[name] = sh
        print(f'  {name:<28s} {eh:>5d} {xh:>4d} {len(r):>5d} {sh:>+7.2f} {mean:>+8.4f}')
    return out


def dow_concentration(trades: list[dict]) -> tuple[float, dict]:
    if not trades:
        return 0.0, {}
    df = pd.DataFrame(trades)
    counts = df['dow'].value_counts()
    n = len(df)
    share = counts / n
    return float(share.max()), share.to_dict()


def walk_forward_single(df: pd.DataFrame, ny: pd.DataFrame, direction: str = 'long') -> float:
    """Single 1.5y IS / 0.8y OOS split given the 2.3y window."""
    print(f'  [walk-forward single split, direction={direction}]')
    ret, _ = simulate(df, ny, direction=direction, cost_bps=COST_BPS_DEFAULT)
    if len(ret) == 0:
        return float('nan')
    cut = ret.index.min() + pd.Timedelta(days=int(365.25 * 1.5))
    is_r = ret[ret.index <= cut].to_numpy()
    oos_r = ret[ret.index > cut].to_numpy()
    if len(is_r) < 50 or len(oos_r) < 30:
        print(f'    insufficient: IS={len(is_r)} OOS={len(oos_r)}')
        return float('nan')
    is_years = max((ret[ret.index <= cut].index[-1] - ret[ret.index <= cut].index[0]).days / 365.25, 1e-9)
    oos_years = max((ret[ret.index > cut].index[-1] - ret[ret.index > cut].index[0]).days / 365.25, 1e-9)
    is_sh = annualized_sharpe(is_r, trades_per_year=len(is_r) / is_years)
    oos_sh = annualized_sharpe(oos_r, trades_per_year=len(oos_r) / oos_years)
    deg = is_sh - oos_sh
    print(f'    IS  {ret[ret.index <= cut].index[0].date()} -> {ret[ret.index <= cut].index[-1].date()}'
          f'  n={len(is_r)}  Sh={is_sh:+.2f}')
    print(f'    OOS {ret[ret.index > cut].index[0].date()} -> {ret[ret.index > cut].index[-1].date()}'
          f'  n={len(oos_r)}  Sh={oos_sh:+.2f}')
    print(f'    degradation: {deg:+.3f}  (bar: < {KC_WF_DEG:.2f})')
    return deg


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    section('Loading XCUUSD H1 (W4-only, 2024-02 -> 2026-05, UTC)')
    df = load_h1()
    print(f'  bars   : {len(df):,}')
    print(f'  range  : {df["timestamp"].min()} -> {df["timestamp"].max()}')
    ny = build_ny_summary(df)
    print(f'  NY-session summary rows: {len(ny):,}')

    section('Phase 0 — hour-of-day profile (XCUUSD H1, 2024-02 onward)')
    hour_of_day_profile(df)

    # ---------- LONG (pre-committed primary direction) ----------
    section('Variant C LONG — 23:00 -> 08:00 UTC, 9h hold, cost 5bp RT')
    ret_L, tr_L = simulate(df, ny, direction='long', cost_bps=COST_BPS_DEFAULT)
    stats_L = report_run('LONG', ret_L)

    section('Cost sweep — Variant C LONG')
    cost_sweep(df, ny, 'LONG', ENTRY_HOUR, EXIT_HOUR, direction='long')

    # ---------- SHORT (null-check, co-equal pre-commit) ----------
    section('Variant C SHORT (null-check) — 23:00 -> 08:00 UTC, cost 5bp RT')
    ret_S, tr_S = simulate(df, ny, direction='short', cost_bps=COST_BPS_DEFAULT)
    stats_S = report_run('SHORT', ret_S)

    fade_gap = stats_L.get('sharpe', 0) - stats_S.get('sharpe', 0)
    print(f'\n  direction-gap (LONG - SHORT Sharpe): {fade_gap:+.2f}  (bar: > {KC_FADE_GAP:.2f})')
    if stats_L.get('sharpe', 0) > 0 and stats_S.get('sharpe', 0) > 0:
        print('  *** WARNING: BOTH directions positive — structural confound (cost model or entry/exit wrong) ***')
    elif stats_S.get('sharpe', 0) > stats_L.get('sharpe', 0) + KC_FADE_GAP:
        print('  *** Driver B wins: PASS-SHORT / REJECT-LONG candidate ***')

    # ---------- Control-hold (session-specificity) ----------
    section('Control-hold check — confirm Asia handoff is session-specific')
    ctrl_L = control_hold(df, ny, direction='long')
    print()
    print('  Control-hold (SHORT direction, for completeness):')
    ctrl_S = control_hold(df, ny, direction='short')

    # ---------- Walk-forward ----------
    section('Walk-forward (single split)')
    wf_L = walk_forward_single(df, ny, direction='long')

    # ---------- DOW ----------
    dow_max_L, dow_dist_L = dow_concentration(tr_L)
    section('DOW concentration — LONG')
    print(f'  distribution: {dow_dist_L}')
    print(f'  max share   : {dow_max_L * 100:.1f}%  (bar: < {KC_DOW_MAX_SHARE * 100:.0f}%)')

    # ---------- Cost-stress @ 8bp ----------
    section('Cost-stress @ 8bp RT — LONG (worst-case copper CFD)')
    ret_L8, _ = simulate(df, ny, direction='long', cost_bps=KC_COST_STRESS_BP)
    stats_L8 = report_run('LONG @ 8bp', ret_L8)

    # ---------- Kill criteria ----------
    section('Phase 2 kill criteria — Variant C LONG (W4-only)')
    sh_L = stats_L.get('sharpe', 0)
    mdd_L = stats_L.get('mdd', -1)
    n_L = stats_L.get('n', 0)
    ny_sh_L = ctrl_L.get('Control NY (11->20)', 0)
    ctrl_gap = sh_L - ny_sh_L
    cost_stress_L = stats_L8.get('sharpe', 0)

    checks = [
        (f'W4 Sharpe  > {KC_SHARPE_W4:.2f}',         sh_L > KC_SHARPE_W4,        f'{sh_L:+.2f}'),
        (f'MDD        < {KC_MDD * 100:.0f}%',         abs(mdd_L) < KC_MDD,        f'{mdd_L * 100:+.2f}%'),
        (f'Trades    >= {KC_TRADES}',                n_L >= KC_TRADES,           f'{n_L}'),
        (f'Fade-gap   > {KC_FADE_GAP:.2f}',           fade_gap > KC_FADE_GAP,     f'{fade_gap:+.2f}'),
        (f'Control gap> {KC_CONTROL_GAP:.2f}',        ctrl_gap > KC_CONTROL_GAP,  f'{ctrl_gap:+.2f}'),
        (f'WF deg     < {KC_WF_DEG:.2f}',             wf_L < KC_WF_DEG,           f'{wf_L:+.2f}'),
        (f'DOW share  < {KC_DOW_MAX_SHARE * 100:.0f}%',
                                                      dow_max_L < KC_DOW_MAX_SHARE,
                                                      f'{dow_max_L * 100:.1f}%'),
        (f'Cost stress@{KC_COST_STRESS_BP:.0f}bp > 0', cost_stress_L > 0,         f'{cost_stress_L:+.2f}'),
    ]
    n_pass = 0
    for desc, ok, val in checks:
        v = 'PASS' if ok else 'FAIL'
        print(f'    {desc:<32s} : {v}  ({val})')
        if ok:
            n_pass += 1
    overall = 'PASS' if n_pass == len(checks) else f'FAIL {n_pass}-of-{len(checks)}'
    print(f'    -> {overall}')

    # ---------- Summary ----------
    section('Summary')
    print(f'  LONG  Variant C @ 5bp: Sharpe {sh_L:+.2f}  MDD {mdd_L * 100:+.2f}%  n={n_L}  mean {stats_L.get("mean", 0) * 100:+.4f}%')
    print(f'  SHORT Variant C @ 5bp: Sharpe {stats_S.get("sharpe", 0):+.2f}  mean {stats_S.get("mean", 0) * 100:+.4f}%')
    print(f'  Fade gap (LONG - SHORT)  : {fade_gap:+.2f}')
    print(f'  Control NY-hours LONG Sh : {ny_sh_L:+.2f}  (gap {ctrl_gap:+.2f})')
    print(f'  Kill criteria            : {overall}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
