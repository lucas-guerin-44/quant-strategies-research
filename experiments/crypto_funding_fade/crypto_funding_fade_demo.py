#!/usr/bin/env python3
"""Crypto perp funding-rate fade — Phase 2 simulator (short-biased).

Thesis: experiments/crypto_funding_fade/crypto_funding_fade.md

Mechanism: funding settles 8h (00/08/16 UTC). Funding-z extreme-high => crowded
longs => FADE SHORT; extreme-low => FADE LONG. Funding is positive most of the
time, so the fade is structurally short-biased without a hand-set short switch.

Vessels:
  BTC_CFD  : Eightcap BTCUSD_M5.csv resampled to 8h grid  (PRIMARY / deploy)
  BTC_PERP : Binance BTCUSDT 8h klines                    (mechanism-clean read)
  ETH_PERP : Binance ETHUSDT 8h klines                    (cross-instrument check)

No-lookahead: fund_z[t] uses funding settled at t; ENTER at open[t+1].

Run:
    venv/Scripts/python.exe experiments/crypto_funding_fade/crypto_funding_fade_demo.py
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
OHLC = os.path.join(_ROOT, 'ohlc_data')

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
LB = int(os.environ.get('FUND_LB', 90))          # z-score lookback (intervals)
THR = float(os.environ.get('FUND_THR', 1.0))     # |z| trigger
HOLD = int(os.environ.get('FUND_HOLD', 1))       # hold in 8h intervals
COST_BPS = float(os.environ.get('FUND_COST_BPS', 10.0))  # RT bps baseline
PROP_CLIP = float(os.environ.get('FUND_CLIP', 2.0))      # form-2 z clip

PERIODS_PER_YEAR = 365.25 * 3  # 8h grid

WINDOWS = [
    ('W1 2019-2020',        '2019-09-01', '2020-12-31'),
    ('W2 2021-2022',        '2021-01-01', '2022-12-31'),
    ('W3 2023-2026 HOLDOUT', '2023-01-01', '2026-05-31'),
]

# Pre-committed kill criteria (see thesis §Fail conditions)
KILL = dict(full_sh=0.30, mdd=-25.0, trades=200, fade_gap=0.30,
            holdout_sh=0.0, cost20_sh=0.0, short_frac=55.0)


# --------------------------------------------------------------------------- #
# Helpers (repo conventions: numpy inner loops, compounding MDD)
# --------------------------------------------------------------------------- #
def section(t: str) -> None:
    print(f"\n{'=' * 92}\n  {t}\n{'=' * 92}\n")


def ann_sharpe(r: np.ndarray, per_yr: float) -> float:
    r = r[np.isfinite(r)]
    if r.size < 2:
        return 0.0
    s = float(r.std(ddof=1))
    return float(r.mean() / s * np.sqrt(per_yr)) if s > 0 else 0.0


def max_dd_pct(r_pct: np.ndarray) -> float:
    if r_pct.size == 0:
        return 0.0
    eq = np.cumprod(1.0 + r_pct / 100.0)
    rm = np.maximum.accumulate(eq)
    return float(((eq - rm) / rm).min()) * 100.0


def tpy_est(ts: np.ndarray, n: int) -> float:
    if n < 2:
        return 0.0
    yrs = (ts[-1] - ts[0]) / np.timedelta64(1, 'D') / 365.25
    return n / float(yrs) if yrs > 0 else 0.0


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def _floor8h(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True, format='mixed').dt.floor('8h')


def load_funding(sym: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(OHLC, f'{sym}_FUNDING.csv'))
    df['ts'] = _floor8h(df['timestamp'])
    return df[['ts', 'funding_rate']].drop_duplicates('ts').sort_values('ts')


def load_perp(sym: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(OHLC, f'{sym}_PERP_8H.csv'))
    df['ts'] = _floor8h(df['timestamp'])
    return df[['ts', 'open']].rename(columns={'open': 'price'}).drop_duplicates('ts')


def load_cfd_8h() -> pd.DataFrame:
    """Resample Eightcap BTCUSD_M5 to the 8h grid; price = first open in bucket."""
    df = pd.read_csv(os.path.join(OHLC, 'BTCUSD_M5.csv'))
    df['ts'] = pd.to_datetime(df['timestamp'], utc=True, format='mixed')
    df = df.sort_values('ts')
    df['grid'] = df['ts'].dt.floor('8h')
    g = df.groupby('grid', as_index=False).agg(price=('open', 'first'))
    return g.rename(columns={'grid': 'ts'})


def build(price_df: pd.DataFrame, fund_df: pd.DataFrame) -> tuple:
    """Merge price + funding on the 8h grid; return (ts, price, fund_z) arrays."""
    m = price_df.merge(fund_df, on='ts', how='inner').sort_values('ts').reset_index(drop=True)
    fr = m['funding_rate']
    mean = fr.rolling(LB, min_periods=LB // 2).mean()
    std = fr.rolling(LB, min_periods=LB // 2).std(ddof=1)
    m['z'] = ((fr - mean) / std)
    return (m['ts'].to_numpy(),
            m['price'].to_numpy(dtype=float),
            m['z'].to_numpy(dtype=float))


# --------------------------------------------------------------------------- #
# Simulators
# --------------------------------------------------------------------------- #
def sim_fade(ts, price, z, thr, hold, cost_bps, invert=False):
    """Form 1 discrete fade. invert=True runs the null (opposite direction).

    Returns (rets_pct, entry_ts, signed_dirs)."""
    cost = cost_bps / 100.0
    n = len(price)
    rets, ets, dirs = [], [], []
    sgn = +1.0 if invert else -1.0   # fade = -sign(z); null = +sign(z)
    for i in range(n):
        zi = z[i]
        if not np.isfinite(zi) or abs(zi) <= thr:
            continue
        ei = i + 1                    # no-lookahead entry
        xi = ei + hold
        if xi >= n:
            continue
        p_in, p_out = price[ei], price[xi]
        if not (np.isfinite(p_in) and np.isfinite(p_out)) or p_in <= 0:
            continue
        d = sgn * np.sign(zi)
        rets.append(d * (p_out - p_in) / p_in * 100.0 - cost)
        ets.append(ts[i])
        dirs.append(d)
    return (np.asarray(rets), np.asarray(ets, dtype='datetime64[ns]'),
            np.asarray(dirs))


def sim_prop(ts, price, z, clip, cost_bps):
    """Form 2 continuous funding-proportional. Returns (per-interval rets, ts, pos)."""
    cost = cost_bps / 100.0
    n = len(price)
    pos = np.clip(-z / clip, -1.0, 1.0)        # target at t (short when z high)
    pos = np.where(np.isfinite(pos), pos, 0.0)
    rets, ets, held = [], [], []
    prev = 0.0
    for i in range(n - 2):
        if not np.isfinite(z[i]):
            prev = 0.0
            continue
        ei, xi = i + 1, i + 2
        p_in, p_out = price[ei], price[xi]
        if not (np.isfinite(p_in) and np.isfinite(p_out)) or p_in <= 0:
            continue
        ret_next = (p_out - p_in) / p_in * 100.0
        turn = abs(pos[i] - prev)
        rets.append(pos[i] * ret_next - turn * cost)
        ets.append(ts[i])
        held.append(pos[i])
        prev = pos[i]
    return (np.asarray(rets), np.asarray(ets, dtype='datetime64[ns]'),
            np.asarray(held))


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def report(label, rets, ts, per_yr=None, dirs=None):
    n = rets.size
    if n < 5:
        print(f"  {label:<30s} n={n} (too sparse)")
        return {'label': label, 'n': n, 'sharpe': float('nan'), 'mdd': float('nan'),
                'mean': float('nan'), 'short_frac': float('nan')}
    py = per_yr if per_yr is not None else tpy_est(ts, n)
    sh = ann_sharpe(rets, py)
    mdd = max_dd_pct(rets)
    sf = float((dirs < 0).mean() * 100.0) if dirs is not None and dirs.size else float('nan')
    sf_s = f"sh%={sf:>3.0f}" if np.isfinite(sf) else "        "
    print(f"  {label:<30s} n={n:>5d} py={py:>6.0f} mean={rets.mean():+.4f}% "
          f"Sh={sh:+.2f} MDD={mdd:+6.2f}% WR={ (rets>0).mean()*100:>3.0f}% {sf_s}")
    return {'label': label, 'n': n, 'sharpe': sh, 'mdd': mdd,
            'mean': float(rets.mean()), 'short_frac': sf, 'tpy': py}


def by_regime(ts, rets, per_yr=None, dirs=None):
    out = {}
    tn = ts.astype('datetime64[ns]')
    for wn, ws, we in WINDOWS:
        s = np.datetime64(ws); e = np.datetime64(we)
        m = (tn >= s) & (tn <= e)
        d = dirs[m] if dirs is not None else None
        out[wn] = report(wn, rets[m], ts[m], per_yr=per_yr, dirs=d)
    return out


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    print(f"  Config: LB={LB} THR={THR} HOLD={HOLD} cost={COST_BPS}bp RT  "
          f"clip={PROP_CLIP}")
    fund_btc = load_funding('BTCUSDT')
    fund_eth = load_funding('ETHUSDT')
    vessels = {
        'BTC_CFD':  build(load_cfd_8h(),       fund_btc),
        'BTC_PERP': build(load_perp('BTCUSDT'), fund_btc),
        'ETH_PERP': build(load_perp('ETHUSDT'), fund_eth),
    }
    for name, (ts, price, z) in vessels.items():
        fin = np.isfinite(z).sum()
        print(f"  {name:<9s} bars={len(ts):>5d}  z-finite={fin:>5d}  "
              f"[{pd.Timestamp(ts[0]).date()} .. {pd.Timestamp(ts[-1]).date()}]")

    # ============ FORM 1 — directional fade, all vessels ============
    section('FORM 1 — DIRECTIONAL FADE (baseline THR=%.1f HOLD=%d, %gbp)'
            % (THR, HOLD, COST_BPS))
    results = {}
    for name, (ts, price, z) in vessels.items():
        r, t, d = sim_fade(ts, price, z, THR, HOLD, COST_BPS)
        results[name] = report(f'{name} FADE', r, t, dirs=d)
        results[name]['_arr'] = (r, t, d)

    # ============ NULL CHECK (inverse direction) ============
    section('NULL CHECK — inverse direction (LONG-on-high-funding)')
    fade_gaps = {}
    for name, (ts, price, z) in vessels.items():
        rn, tn, dn = sim_fade(ts, price, z, THR, HOLD, COST_BPS, invert=True)
        nrep = report(f'{name} NULL', rn, tn, dirs=dn)
        gap = results[name]['sharpe'] - nrep['sharpe']
        fade_gaps[name] = gap
        print(f"     fade-gap [{name}] = {gap:+.2f}  (need > +{KILL['fade_gap']})")

    # ============ REGIME — BTC_CFD primary ============
    section('REGIME BREAKDOWN — BTC_CFD (primary deploy vessel)')
    r, t, d = results['BTC_CFD']['_arr']
    btc_regime = by_regime(t, r, dirs=d)

    section('REGIME BREAKDOWN — BTC_PERP / ETH_PERP (cross-check)')
    for name in ('BTC_PERP', 'ETH_PERP'):
        print(f"  --- {name} ---")
        rr, tt, dd = results[name]['_arr']
        by_regime(tt, rr, dirs=dd)

    # ============ THR SWEEP — BTC_CFD ============
    section('THRESHOLD SWEEP — BTC_CFD (full-sample)')
    ts, price, z = vessels['BTC_CFD']
    for thr in (0.5, 0.75, 1.0, 1.5, 2.0):
        rr, tt, dd = sim_fade(ts, price, z, thr, HOLD, COST_BPS)
        report(f'THR={thr}', rr, tt, dirs=dd)

    # ============ HOLD SWEEP — BTC_CFD ============
    section('HOLD SWEEP — BTC_CFD (intervals of 8h)')
    for h in (1, 2, 3, 6):
        rr, tt, dd = sim_fade(ts, price, z, THR, h, COST_BPS)
        report(f'HOLD={h} ({h*8}h)', rr, tt, dirs=dd)

    # ============ COST SWEEP — BTC_CFD ============
    section('COST SENSITIVITY — BTC_CFD (RT bps)')
    cost20 = {}
    for c in (4.0, 10.0, 20.0, 40.0):
        rr, tt, dd = sim_fade(ts, price, z, THR, HOLD, c)
        rep = report(f'cost={c}bp', rr, tt, dirs=dd)
        if c == 20.0:
            cost20 = rep

    # ============ FORM 2 — funding-proportional ============
    section('FORM 2 — FUNDING-PROPORTIONAL (continuous, per-interval Sharpe)')
    for name in ('BTC_CFD', 'BTC_PERP', 'ETH_PERP'):
        tsv, pv, zv = vessels[name]
        rp, tp, hp = sim_prop(tsv, pv, zv, PROP_CLIP, COST_BPS)
        sf = float((hp < 0).mean() * 100.0)
        sh = ann_sharpe(rp, PERIODS_PER_YEAR)
        print(f"  {name:<9s} n={rp.size:>5d} Sh={sh:+.2f} "
              f"MDD={max_dd_pct(rp):+6.2f}% mean={rp.mean():+.5f}%/8h "
              f"net-short%={sf:.0f} avg-pos={hp.mean():+.3f}")
        if name == 'BTC_CFD':
            print("     (form-2 regime split:)")
            # quick regime on the per-interval series
            tn = tp.astype('datetime64[ns]')
            for wn, ws, we in WINDOWS:
                m = (tn >= np.datetime64(ws)) & (tn <= np.datetime64(we))
                if m.sum() > 5:
                    print(f"       {wn:<22s} Sh={ann_sharpe(rp[m], PERIODS_PER_YEAR):+.2f}")

    # ============ KILL CRITERIA — BTC_CFD form 1 baseline ============
    section('PRE-COMMITTED KILL CRITERIA — BTC_CFD FORM 1 baseline')
    b = results['BTC_CFD']
    ho = btc_regime['W3 2023-2026 HOLDOUT']
    n_pos = sum(1 for k, v in btc_regime.items() if v['sharpe'] > 0)

    def chk(label, val, thr, op='>', p=2):
        ok = val > thr if op == '>' else val < thr
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:<42s} "
              f"{val:+.{p}f}  need {op} {thr:+.{p}f}")
        return ok

    checks = [
        chk('1 full net Sharpe (10bp)', b['sharpe'], KILL['full_sh']),
        chk('2 MDD (>-25%)', b['mdd'], KILL['mdd']),  # mdd>-25 => shallower than 25%
        chk('3 trade count', b['n'], KILL['trades'], p=0),
        chk('4 fade-gap (fade - null)', fade_gaps['BTC_CFD'], KILL['fade_gap']),
        chk('5 holdout 2023-26 Sharpe', ho['sharpe'], KILL['holdout_sh']),
        chk('6 regimes positive (of 3)', n_pos, 1.5, p=0),
        chk('7 cost-robust Sh @20bp', cost20.get('sharpe', float('nan')), KILL['cost20_sh']),
        chk('8 short fraction %', b['short_frac'], KILL['short_frac'], p=0),
    ]
    passed = sum(bool(c) for c in checks)
    print(f"\n  VERDICT: {passed}/{len(checks)} binding criteria pass.")
    if passed == len(checks):
        print("  -> PASS. Proceed to Phase 3.")
    elif passed >= len(checks) - 1:
        print("  -> MARGINAL. One criterion short.")
    else:
        print("  -> REJECT. Tombstone with mechanistic interpretation.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
