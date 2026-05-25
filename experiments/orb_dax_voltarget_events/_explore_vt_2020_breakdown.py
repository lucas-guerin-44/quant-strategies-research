"""Year-by-year and Mar-2020-isolated diagnostic on VT alone.

Question: does VT damage 2019-2020 because of Mar 2020 COVID, or because
inverse-vol sizing is structurally wrong in a steadily-rising 2019?
"""

from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from voltarget_events_demo import (  # noqa: E402
    SYMBOL, COST_POINTS_ROUND_TRIP, BARS_PER_YEAR,
    load_m5, load_d1,
    simulate_orb_long_t180, build_vol_scale, apply_overlay,
    annualized_sharpe_bar, max_drawdown,
)


def main() -> None:
    bars = load_m5(SYMBOL)
    d1 = load_d1(SYMBOL)
    scale_by_date = build_vol_scale(d1)
    ret_arr, trades = simulate_orb_long_t180(bars, cost_points=COST_POINTS_ROUND_TRIP)
    vt_ret, _ = apply_overlay(ret_arr, trades, scale_by_date=scale_by_date)

    years = bars.index.year.values
    months = bars.index.month.values

    print("Year-by-year: baseline vs VT")
    for y in sorted(set(years)):
        mask = years == y
        if not mask.any():
            continue
        sh_b = annualized_sharpe_bar(ret_arr[mask])
        sh_v = annualized_sharpe_bar(vt_ret[mask])
        print(f"  {y}: baseline Sh {sh_b:+.3f}   VT Sh {sh_v:+.3f}   Δ {sh_v-sh_b:+.3f}")

    print("\n2020 month-by-month:")
    mask_2020 = years == 2020
    for m in range(1, 13):
        mm = mask_2020 & (months == m)
        if not mm.any():
            continue
        sh_b = annualized_sharpe_bar(ret_arr[mm])
        sh_v = annualized_sharpe_bar(vt_ret[mm])
        # Sum PnL approximated as sum of bar returns (small) for ranking.
        sum_b = ret_arr[mm].sum() * 100
        sum_v = vt_ret[mm].sum() * 100
        print(f"  2020-{m:02d}: baseline Sh {sh_b:+.3f}  PnL {sum_b:+.2f}%   "
              f"VT Sh {sh_v:+.3f}  PnL {sum_v:+.2f}%")

    print("\nRe-run regime windows EXCLUDING 2020-Mar/Apr (the COVID shock):")
    excl_mask = ~((years == 2020) & ((months == 3) | (months == 4)))
    for name, m in [
        ("2019-2020 (excl Mar-Apr 2020)", (years >= 2019) & (years <= 2020) & excl_mask),
        ("2021-2022", (years >= 2021) & (years <= 2022)),
        ("2023-2026", years >= 2023),
        ("FULL (excl Mar-Apr 2020)", excl_mask),
    ]:
        if not m.any():
            continue
        sh_b = annualized_sharpe_bar(ret_arr[m])
        sh_v = annualized_sharpe_bar(vt_ret[m])
        print(f"  {name}: baseline {sh_b:+.3f}  VT {sh_v:+.3f}  Δ {sh_v-sh_b:+.3f}")


if __name__ == "__main__":
    main()
