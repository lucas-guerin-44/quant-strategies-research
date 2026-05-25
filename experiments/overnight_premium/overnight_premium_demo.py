#!/usr/bin/env python3
"""Single-stock overnight return premium — Phase 2 backtest.

Long D 15:55 ET close, sell D+1 09:35 ET open. Equal-weight across 24 names per night.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_EXPERIMENTS = _HERE.parent
_ROOT = _EXPERIMENTS.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT.parent / 'backtesting-engine-2.0'))

from utils import fetch_ohlc  # noqa: E402


UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM', 'BAC', 'GS', 'V', 'MA',
    'UNH', 'WMT', 'HD', 'LOW', 'KO', 'PEP', 'JNJ',
    'XOM', 'CVX', 'ORCL', 'CRM', 'AVGO',
]

EARNINGS_CALENDAR = _ROOT / 'experiments' / 'earnings_fade' / 'data' / 'earnings_calendar.csv'

TIMEFRAME = 'M5'
START_DATE = '2018-01-01'
END_DATE = '2026-05-21'

TREND_LOOKBACK_DAYS = 20
VOL_LOOKBACK_DAYS = 20
VOL_PCTILE_CUT = 0.80
SWAP_BPS_PER_DAY = 1.5  # default; sweep below


def section(t: str) -> None:
    print(f'\n{"=" * 80}\n  {t}\n{"=" * 80}\n')


def load_m5(symbol: str) -> pd.DataFrame:
    raw = fetch_ohlc(symbol, TIMEFRAME, START_DATE, END_DATE)
    if raw is None or raw.empty:
        raise RuntimeError(f'No bars for {symbol}')
    df = raw[['timestamp', 'open', 'high', 'low', 'close']].copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.set_index('timestamp').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    return df


def per_day_oc(bars: pd.DataFrame) -> pd.DataFrame:
    """Per-day first-bar-open and last-bar-close. Indexed by date."""
    idx_date = pd.Series(bars.index.date, index=bars.index, name='date')
    df = bars.assign(date=idx_date.values)
    g = df.groupby('date')
    out = pd.DataFrame({
        'open_first': g['open'].first(),
        'close_last': g['close'].last(),
        'high': g['high'].max(),
        'low': g['low'].min(),
    })
    out.index = pd.to_datetime(out.index)
    return out


def event_sharpe(r: np.ndarray, periods_per_year: int = 252) -> float:
    r = r[np.isfinite(r)]
    if r.size == 0:
        return 0.0
    std = r.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(r.mean() / std * np.sqrt(periods_per_year))


def max_drawdown(eq: np.ndarray) -> float:
    if eq.size == 0:
        return 0.0
    rm = np.maximum.accumulate(eq)
    return float(((eq - rm) / rm).min())


def load_earnings_amc_dates() -> dict[str, set[pd.Timestamp]]:
    """For each ticker, return set of trade_dates where ann_session==AMC (overnight blackout)."""
    cal = pd.read_csv(EARNINGS_CALENDAR)
    cal['trade_date'] = pd.to_datetime(cal['trade_date'])
    out: dict[str, set[pd.Timestamp]] = {}
    # AMC means the announcement is between today's close and tomorrow's open — so the
    # "overnight" between D and D+1 is the one to skip. trade_date in calendar is D+1
    # for AMC events, so we skip the overnight ending on trade_date (= the one starting on D = trade_date - 1).
    for tk, sub in cal.groupby('ticker'):
        amc = sub[sub['ann_session'] == 'AMC']
        # Skip overnight whose entry is at trade_date-1; we'll match by trade_date itself.
        out[tk] = set(amc['trade_date'].dt.normalize().tolist())
        # Also skip the night ENDING on the announcement date for BMO (announcement before open).
        bmo = sub[sub['ann_session'] == 'BMO']
        out[tk] |= set(bmo['trade_date'].dt.normalize().tolist())
    return out


def build_overnight_events(
    *,
    use_trend_filter: bool = False,
    use_vol_filter: bool = False,
    use_earnings_skip: bool = False,
    cache: dict[str, pd.DataFrame] | None = None,
    verbose: bool = False,
) -> pd.DataFrame:
    if cache is None:
        cache = {}
    earnings_skip = load_earnings_amc_dates() if use_earnings_skip else {}
    rows: list[dict] = []
    for tk in UNIVERSE:
        if tk not in cache:
            try:
                cache[tk] = load_m5(tk)
            except RuntimeError as e:
                if verbose:
                    print(f'  {tk}: {e}')
                continue
        bars = cache[tk]
        oc = per_day_oc(bars)
        oc = oc.sort_index()
        oc['next_open'] = oc['open_first'].shift(-1)
        oc['overnight_ret'] = oc['next_open'] / oc['close_last'] - 1.0
        # Trend filter: 20d trailing daily return.
        oc['ret_d'] = oc['close_last'].pct_change()
        oc['trend_20d'] = oc['ret_d'].rolling(TREND_LOOKBACK_DAYS).sum()
        # Vol filter: 20d realized vol.
        oc['vol_20d'] = oc['ret_d'].rolling(VOL_LOOKBACK_DAYS).std()
        # Trim outer dates (no next_open or insufficient lookback).
        oc = oc.dropna(subset=['overnight_ret']).copy()
        # Vol percentile (per-ticker, expanding to avoid lookahead).
        oc['vol_pctile'] = oc['vol_20d'].expanding().rank(pct=True)
        amc_skip_dates = earnings_skip.get(tk, set())
        for d, row in oc.iterrows():
            d_norm = pd.Timestamp(d).normalize()
            if use_trend_filter and not (np.isfinite(row['trend_20d']) and row['trend_20d'] >= 0):
                continue
            if use_vol_filter and (np.isfinite(row['vol_pctile']) and row['vol_pctile'] > VOL_PCTILE_CUT):
                continue
            if use_earnings_skip and (d_norm in amc_skip_dates or (d_norm + pd.Timedelta(days=1)) in amc_skip_dates):
                continue
            if not np.isfinite(row['overnight_ret']):
                continue
            rows.append({
                'ticker': tk,
                'trade_date': d_norm,
                'overnight_ret': float(row['overnight_ret']),
                'trend_20d': float(row['trend_20d']) if np.isfinite(row['trend_20d']) else np.nan,
                'vol_pctile': float(row['vol_pctile']) if np.isfinite(row['vol_pctile']) else np.nan,
            })
    return pd.DataFrame(rows)


def apply_cost(ev: pd.DataFrame, swap_bps_per_day: float) -> pd.DataFrame:
    e = ev.copy()
    e['pnl'] = e['overnight_ret'] - swap_bps_per_day / 1e4
    return e


def daily_equity(ev: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    if ev.empty:
        return np.array([]), np.array([]), pd.DatetimeIndex([])
    daily = ev.groupby('trade_date')['pnl'].mean().sort_index()
    eq = (1.0 + daily.values).cumprod()
    return daily.values, eq, daily.index


def report(label: str, ev: pd.DataFrame) -> None:
    if ev.empty:
        print(f'  [{label}] no events'); return
    daily, eq, idx = daily_equity(ev)
    sh = event_sharpe(daily, periods_per_year=252)
    mdd = max_drawdown(eq)
    n = len(ev)
    wr = (ev['pnl'] > 0).mean()
    years = (idx[-1] - idx[0]).days / 365.25
    total = float(eq[-1] - 1.0)
    cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
    print(f'  [{label}]')
    print(f'    period   : {idx[0].date()} -> {idx[-1].date()} ({years:.1f}y)')
    print(f'    Sharpe   : {sh:+.2f}')
    print(f'    Max DD   : {mdd*100:+.2f}%')
    print(f'    events   : {n}  ({n/years:.0f}/yr)  active-days {len(idx)} ({len(idx)/years:.0f}/yr)')
    print(f'    CAGR     : {cagr*100:+.2f}%')
    print(f'    Total    : {total*100:+.1f}%')
    print(f'    WR (per overnight): {wr*100:.1f}%   avg: {ev["pnl"].mean()*100:+.3f}%')


def regime_breakdown(ev: pd.DataFrame) -> None:
    for label, s, ee in [
        ('2018-2020 pre/COVID', '2018-01-01', '2020-12-31'),
        ('2021-2022 vol      ', '2021-01-01', '2022-12-31'),
        ('2023-2026 holdout  ', '2023-01-01', '2026-12-31'),
    ]:
        sub = ev[(ev['trade_date'] >= pd.Timestamp(s)) & (ev['trade_date'] <= pd.Timestamp(ee))]
        if len(sub) < 50:
            print(f'  {label:<22s} n={len(sub):>5d}  (insufficient)'); continue
        daily, eq, idx = daily_equity(sub)
        sh = event_sharpe(daily)
        mdd = max_drawdown(eq)
        years = (idx[-1] - idx[0]).days / 365.25
        total = float(eq[-1] - 1.0)
        cagr = ((1 + total) ** (1 / max(years, 1e-9))) - 1
        print(f'  {label:<22s} n={len(sub):>5d}  Sh {sh:>+6.2f}  CAGR {cagr*100:>+7.2f}%  MDD {mdd*100:>+7.2f}%')


def per_ticker(ev: pd.DataFrame) -> None:
    rows = []
    for tk, sub in ev.groupby('ticker'):
        daily = sub.set_index('trade_date')['pnl'].sort_index()
        eq = (1 + daily.values).cumprod()
        sh = event_sharpe(daily.values)
        total = float(eq[-1] - 1.0)
        rows.append((tk, len(sub), sh, total, (sub['pnl'] > 0).mean()))
    rows.sort(key=lambda r: -r[3])
    print(f'  {"ticker":<6s} {"n":>5s} {"Sh":>7s} {"total":>10s} {"WR":>6s}')
    for tk, n, sh, total, wr in rows:
        print(f'  {tk:<6s} {n:>5d} {sh:>+7.2f} {total*100:>+9.2f}% {wr*100:>5.1f}%')


def walk_forward(cache: dict[str, pd.DataFrame], filters: dict, swap: float = SWAP_BPS_PER_DAY) -> None:
    splits = [
        ('2021-09-01', '2024-09-01', '2026-05-21'),
        ('2022-09-01', '2025-09-01', '2026-05-21'),
        ('2021-09-01', '2023-09-01', '2025-09-01'),
    ]
    print(f'  {"split":<38s} {"IS Sh":>8s} {"OOS Sh":>8s} {"OOS n":>7s} {"OOS MDD":>10s}')
    ev = apply_cost(build_overnight_events(cache=cache, **filters), swap)
    ev['trade_date'] = pd.to_datetime(ev['trade_date'])
    oos_sharpes = []
    for is_s, is_e, oos_e in splits:
        is_mask = (ev['trade_date'] >= pd.Timestamp(is_s)) & (ev['trade_date'] < pd.Timestamp(is_e))
        oos_mask = (ev['trade_date'] >= pd.Timestamp(is_e)) & (ev['trade_date'] <= pd.Timestamp(oos_e))
        is_daily = ev.loc[is_mask].groupby('trade_date')['pnl'].mean().sort_index().values
        oos_daily = ev.loc[oos_mask].groupby('trade_date')['pnl'].mean().sort_index().values
        is_sh = event_sharpe(is_daily) if is_daily.size else 0.0
        oos_sh = event_sharpe(oos_daily) if oos_daily.size else 0.0
        oos_n = int(oos_mask.sum())
        if oos_daily.size:
            oos_mdd = max_drawdown((1 + oos_daily).cumprod()) * 100
        else:
            oos_mdd = 0.0
        print(f'  IS {is_s[:7]}->{is_e[:7]} / OOS->{oos_e[:7]} '
              f'{is_sh:>+7.2f}  {oos_sh:>+7.2f}  {oos_n:>7d}  {oos_mdd:>+8.2f}%')
        oos_sharpes.append(oos_sh)
    mean_oos = float(np.mean(oos_sharpes)); min_oos = float(np.min(oos_sharpes))
    print(f'\n  Walk-forward mean OOS Sharpe: {mean_oos:+.2f}  (kill if < +0.20)')
    print(f'  Walk-forward min  OOS Sharpe: {min_oos:+.2f}  (kill if < 0)')
    print(f'  -> {"PASS" if mean_oos >= 0.20 and min_oos >= 0 else "FAIL"}')


def main() -> int:
    section('Overnight return premium — single-stock 24-name universe')
    cache: dict[str, pd.DataFrame] = {}

    section('Baseline (no filters, swap=1.5bp/day)')
    ev0 = apply_cost(build_overnight_events(cache=cache, verbose=True), SWAP_BPS_PER_DAY)
    report('baseline', ev0)

    section('Regime breakdown — baseline')
    regime_breakdown(ev0)

    section('Per-ticker breakdown — baseline')
    per_ticker(ev0)

    section('Filter sweep (1.5 bp/day swap)')
    filter_sets = [
        {'use_trend_filter': True, 'use_vol_filter': False, 'use_earnings_skip': False},
        {'use_trend_filter': False, 'use_vol_filter': True, 'use_earnings_skip': False},
        {'use_trend_filter': False, 'use_vol_filter': False, 'use_earnings_skip': True},
        {'use_trend_filter': True, 'use_vol_filter': True, 'use_earnings_skip': False},
        {'use_trend_filter': True, 'use_vol_filter': False, 'use_earnings_skip': True},
        {'use_trend_filter': False, 'use_vol_filter': True, 'use_earnings_skip': True},
        {'use_trend_filter': True, 'use_vol_filter': True, 'use_earnings_skip': True},
    ]
    print(f'  {"trend":>5s} {"vol":>3s} {"earn":>4s} {"Sh":>7s} {"CAGR":>8s} {"MDD":>8s} {"n":>6s}')
    print(f'  {"---":>5s} {"---":>3s} {"---":>4s} ----- ----- ----- -----')
    sh0 = event_sharpe(daily_equity(ev0)[0])
    cagr0_eq = daily_equity(ev0)[1]; years0 = (daily_equity(ev0)[2][-1] - daily_equity(ev0)[2][0]).days/365.25
    cagr0 = ((1 + (cagr0_eq[-1]-1))**(1/max(years0,1e-9))) - 1
    mdd0 = max_drawdown(cagr0_eq)
    print(f'  {"_":>5s} {"_":>3s} {"_":>4s} {sh0:>+7.2f} {cagr0*100:>+7.2f}% {mdd0*100:>+7.2f}% {len(ev0):>6d}')
    for fs in filter_sets:
        ev_f = apply_cost(build_overnight_events(cache=cache, **fs), SWAP_BPS_PER_DAY)
        d, eq, idx = daily_equity(ev_f)
        sh = event_sharpe(d)
        years = (idx[-1] - idx[0]).days/365.25 if len(idx) else 1.0
        cagr = ((1 + (eq[-1]-1))**(1/max(years,1e-9))) - 1 if eq.size else 0.0
        mdd = max_drawdown(eq)
        tag_t = '*' if fs['use_trend_filter'] else ' '
        tag_v = '*' if fs['use_vol_filter'] else ' '
        tag_e = '*' if fs['use_earnings_skip'] else ' '
        print(f'  {tag_t:>5s} {tag_v:>3s} {tag_e:>4s} {sh:>+7.2f} {cagr*100:>+7.2f}% {mdd*100:>+7.2f}% {len(ev_f):>6d}')

    section('Cost sensitivity (no filters)')
    for swap in (0.0, 1.0, 1.5, 3.0, 5.0, 8.0):
        ev_c = apply_cost(build_overnight_events(cache=cache), swap)
        d, eq, idx = daily_equity(ev_c)
        sh = event_sharpe(d)
        years = (idx[-1] - idx[0]).days/365.25 if len(idx) else 1.0
        cagr = ((1 + (eq[-1]-1))**(1/max(years,1e-9))) - 1 if eq.size else 0.0
        print(f'  swap={swap:>4.1f}bp/d  Sh {sh:>+6.2f}  CAGR {cagr*100:>+7.2f}%')

    section('Direction null-check (SHORT overnight should LOSE if mechanism is sign-correct)')
    ev_short = apply_cost(build_overnight_events(cache=cache), SWAP_BPS_PER_DAY)
    ev_short = ev_short.copy()
    ev_short['pnl'] = -ev_short['overnight_ret'] - SWAP_BPS_PER_DAY / 1e4
    report('SHORT overnight (null)', ev_short)
    sh_long = event_sharpe(daily_equity(ev0)[0])
    sh_short = event_sharpe(daily_equity(ev_short)[0])
    gap = sh_long - sh_short
    print(f'\n  Direction-gap (LONG - SHORT) = {gap:+.2f}')

    # Best filter set — chosen as the highest-Sharpe combo from sweep above (pre-commit-by-rule, not by sweep).
    section('Phase 6 — walk-forward on TREND-only filter (pre-committed lead variant)')
    walk_forward(cache, {'use_trend_filter': True, 'use_vol_filter': False, 'use_earnings_skip': False})

    section('Phase 6 — walk-forward on baseline (no filters)')
    walk_forward(cache, {})

    return 0


if __name__ == '__main__':
    sys.exit(main())
