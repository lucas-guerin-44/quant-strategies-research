# Monthly-OPEX Pin Fade — NDX100 / SPX500 (M5)

**Status**: REJECT — Phase 2, 2026-05-22. Pre-committed direction falsified on both instruments; pre-committed 0DTE-decay scenario realized (holdout is the worst regime on both); calendar lock not load-bearing.

**Verdict**: REJECT. Three independent kill-criteria failed simultaneously:

| Instrument | Sh full | Holdout (HO) | Dir-gap (fade-cont) | OPEX-vs-allFriday | Trades |
|---|---|---|---|---|---|
| NDX100 | −0.25 | **−0.87** | **−0.48 (INVERTED)** | −0.34 | 7 (vs 150 floor) |
| SPX500 | −0.68 | **−1.01** | **−1.33 (INVERTED)** | −0.42 | 5 (vs 150 floor) |

Continuation (long-into-AM-move) PNL is positive on both: NDX cont Sh +0.23, SPX cont Sh +0.64 — the AM-move on OPEX days carries into the close, opposite of the pinning thesis. Mechanism interpretation in section below.

---

## Thesis (mechanism)

On monthly equity-index options expiration days ("OPEX Friday" = 3rd Friday of each month), the underlying index tends to **pin** near strikes with high option open interest (OI) into the cash close. The proposed mechanism has been documented in the academic literature for ~20 years:

1. **Dealer net-short-gamma hedging.** Market-makers who have written calls and puts to retail/funds are typically net short gamma at major monthly strikes. To delta-hedge as the underlying moves toward those strikes, they sell rallies and buy dips — that hedging flow is *mean-reverting* intraday.
2. **Stacked OI at round-number strikes.** Monthly OPEX accumulates open interest over multiple months (vs daily/weekly options which decay each day). The largest strikes — by convention round numbers (e.g., SPX 5500, NDX 20000) — concentrate hedging activity into a tight band.
3. **Pin tightens into the close.** The hedging-flow magnitude scales with `1 / time-to-expiry`, so the mean-reverting pressure is strongest in the final 1-2 hours of the cash session before expiration.
4. **Asymmetric pinning under retail-skewed OI.** When retail is net long calls (common on tech/QQQ), dealer pin pressure tilts toward suppressing rallies more than dips — partially anti-symmetric, but in this implementation we test the symmetric form first.

Without an OI feed in this repo, the pin-strike is unobservable directly. The proxy here is: **the AM session establishes a reference price; if PM drifts away from that reference, the pin pulls it back.** We fade the morning move during the afternoon, OPEX-day only.

This is **NOT** a generic intraday fade. Per lesson #27, generic "fade overshoot on US indices" theses have inverted three independent times (vwap_fade NDX/SPX, gap_continuation, dax-equivalent fades). Only mechanism-specific fades (lunch_fade vacuum window) survive. This experiment proposes a *different* explicit mechanism (dealer gamma hedging on a hard calendar event) and rises or falls on whether the OPEX-day-only restriction has directional content that the all-day variants don't.

## Key references

- **Ni, Pearson, Poteshman (2005)**, "Stock price clustering on option expiration dates", *J. Financial Economics* 78(1). Classic pin paper — documents clustering at strikes on US equity options expiration, with stronger effect for stocks with heavy single-stock option activity.
- **Stoll & Whaley (1991)**, "Expiration day effects of index options on stock market volume and prices", *J. Futures Markets*.
- **Avellaneda & Lipkin (2003)**, "A market-induced mechanism for stock pinning", *Quantitative Finance*. The theoretical gamma-hedging model.
- **Golez & Jackwerth (2012)**, "Pinning in the S&P 500 futures", *J. Financial Economics*. Index-futures specific evidence of pinning at SPX OPEX.
- **Modern context — 0DTE risk**: Brogaard et al. (2024) and other working papers on the 2022-2024 rise of 0DTE/weekly options. The hypothesis here is that 0DTE has *diluted* monthly OPEX OI but not eliminated it (multiple-month accumulation at common strikes still exceeds single-day OI). The empirical test is whether the holdout 2023-2026 sub-period preserves the pin signal.

## Signal math

```
Parameters:
  MORNING_END_MIN    = 120     (11:30 ET; AM reference window length)
  AFTERNOON_END_MIN  = 385     (15:55 ET; 5 min before cash close, into pin)
  MIN_MOVE_ATR       = 0.5     (require non-trivial AM move to fade)
  COST_POINTS_RT     = 1.0     (pessimistic retail CFD)
  ATR_LOOKBACK_DAYS  = 20

Per US trading day (US/Eastern, 09:30-16:00):

  If date is NOT 3rd Friday of month:
    skip (no signal)

  Else:
    r_morning = close[11:30 ET] / open[09:30 ET] - 1
    ATR_proxy = mean of |bar return| over prior 20 trading days

    if |r_morning| < MIN_MOVE_ATR * ATR_proxy * morning_bars:
      skip (no overshoot to fade)

    direction = -sign(r_morning)              # FADE
    enter at next bar open after 11:30 ET
    exit at first bar with minute_of_day >= 385 (15:55 ET)
```

One round-trip per OPEX day max. No same-day stop — the entire pin-fade thesis depends on the pin pulling price back into close; an intrabar stop would risk-manage exactly the noise the mechanism feeds on. MDD control is via the trade-count cap (max ~12/yr/instrument) and the per-trade gross magnitude, not stops.

## Why retail-accessible

The signal needs only: index futures or CFD price, a clock, and a monthly-OPEX calendar. No options data, no order-book data, no premium feed. Both NDX100 and SPX500 are tradeable on Eightcap MT5 (M5 data confirmed on disk, ~7.3y depth each). Deployment analog: MES (SPX) / MNQ (NDX) on CME futures, both micro-sized for retail capital.

## Universe

- **Research**: NDX100, SPX500 CFDs on Eightcap. M5 bars, 2019-01-02 → 2026-04-17 (~7.3 years).
- **Live target**: same MT5 broker the lunch_fade EA already runs on. No new platform integration needed.

OPEX-Friday count per instrument: 12/yr × 7.3y ≈ 88 days. Combined NDX + SPX: ≈ 176 *eligible* days. After AM-move-threshold filter (~70% pass), expect **~120 combined trades** over the full window.

## Expected performance (at thesis time)

If the mechanism works on retail CFDs:
- Per-trade gross ~30-60 bp (modest pin pull on ~0.5-1% AM moves) — should dwarf 2-4 bp 1pt CFD cost.
- Sharpe 0.4-0.8 full-sample after cost.
- Trade cadence ~12/yr/instrument LIMITED by calendar. Combined NDX+SPX: ~16/yr post-filter.
- MDD: pin-failure days can be -2 to -3% if AM continuation extends into close. Total MDD < 15% expected over 7.3y.
- WR 55-65% (pin-positive days should dominate); PF 1.4-1.8.

If 0DTE has leaked monthly OPEX OI elsewhere, **expect holdout collapse**: 2019-2020 Sharpe positive, 2023-2026 holdout near-zero or negative. That is the kill scenario — see Phase 4/6.

## Fail conditions (pre-committed)

Phase 2 kills if ANY:
- Full-period Sharpe < 0.30 after 1pt RT cost.
- Max DD > 25%.
- **Trade count < 150** over 7.3 years (relaxed from the usual 200 — monthly OPEX is structurally capped at ~12/yr/instrument; combined NDX+SPX with AM-threshold filter is the maximum honest cadence). Below 150 means the AM-threshold is killing most days and the strategy has no usable population.
- WR < 50% AND PF < 1.1.

Phase 4 kills if Sharpe positive in < 2 of 3 regime windows (2019-2020 / 2021-2022 / 2023-2026).

Phase 6 kills if 2023-2026 holdout Sharpe < 0.

**Fade-test null check** (lesson #38): continuation variant (trade WITH the AM move, same OPEX-day filter, same threshold). Require **fade-gap (fade Sh − cont Sh) ≥ +0.30**. If gap ≤ 0, the AM-move-direction has no information about PM direction on OPEX days specifically.

**Cross-instrument fade test** (lesson #15): require fade-gap positive on BOTH NDX100 AND SPX500. If one inverts, the signal is venue-specific noise, not a generic options-expiry effect.

**All-day null check**: same simulator with `OPEX_ONLY=False` (every Friday afternoon). Require **OPEX-only Sharpe − all-Friday Sharpe ≥ +0.20**. If the all-day variant matches or beats the OPEX-day variant, the "monthly expiry calendar" lock is not load-bearing — the strategy is just lunch_fade with a worse trade count. (lunch_fade is already deployed; running this would be redundant.)

## Why this might fail (red flags, pre-commit)

1. **0DTE dilution post-2022.** The clearest decay mechanism. Daily-expiry options have dragged ~50-70% of SPX option volume away from monthly OPEX over 2022-2024 (CBOE data). If dealer pin pressure scales with monthly-OPEX OI / total OI, monthly OPEX is now ~30-50% as load-bearing as in 2019-2021. The holdout window will catch this.
2. **The pin proxy is wrong-shaped.** "Fade the AM move" assumes AM drift is *away from* the pin and PM is *back to* it. But the AM move could just as easily be *toward* the pin (overnight gap away → AM moves back), in which case afternoon fade is fade-the-pin = lose.
3. **Asymmetric retail-OI tilt on NDX.** Tech options OI skews retail-call-heavy; dealer pin pressure may suppress rallies more than dips on NDX, breaking the symmetric form. Long-only and short-only legs separately will surface this if it exists.
4. **CFD friction on small per-trade gross.** Pin pull of 30-50 bp leaves margin to absorb 2-4 bp cost, but if pin is weaker than expected (~10-15 bp post-0DTE), 1pt RT cost is the binding constraint. Cost-zero Sharpe extrapolation will diagnose (lesson #26).
5. **N is small.** ~88 OPEX days per instrument over 7.3y means a single bad year (say 2020 COVID-March OPEX week) carries disproportionate weight. Regime breakdown will expose if so.
6. **Pinning is well-known and likely arbed.** This is the most-cited intraday-equity-options edge in academic literature; if anything is going to be arbed away on US indices, this is a leading candidate. Mirrors the orb_spx500 outcome.

## Phase 2 results — by instrument

### NDX100 — REJECT

M5, RTH 09:30-16:00 ET, 146,245 bars, 1,885 trading days, 85 monthly-OPEX Fridays in window.

**Baseline (fade, OPEX-only, AM=120min, PM=385min, thr=0.5, cost=1pt)**:

| Metric | Value | vs threshold |
|---|---|---|
| Sharpe | −0.25 | FAIL |
| Max DD | −4.16% | PASS |
| Trades | 7 (1.0/yr) | FAIL (vs ≥150 floor) |
| WR / PF | 57.1% / 0.52 | partial (WR PASS, PF FAIL) |
| Avg win / loss | +0.501% / −1.293% | — |

**Regime breakdown**:

| Window | Sh | trades |
|---|---|---|
| 2019-2020 pre/COVID | +1.11 | 2 |
| 2021-2022 vol | +0.07 | 1 |
| **2023-2026 holdout** | **−0.87** | 4 |

**Threshold sweep** (loosening the AM-move filter expands the trade population):

| thr | Sh | trades |
|---|---|---|
| 0.00 | +0.02 | 85 (every OPEX day) |
| 0.25 | −0.19 | 16 |
| 0.50 | −0.25 | 7 |
| 0.75 | −0.18 | 1 |

Even with the threshold removed entirely (every OPEX day = 1 trade), full-sample Sh is +0.02. The signal is mechanically population-capped at 85 trades over 7.3y — well below the 150 floor — and the per-trade EV at the population limit is zero.

**Null-check (continuation)**: Sh +0.23, WR 42.9%, PF 1.85, avg win +1.285%. **Direction-gap −0.48** = INVERTED. The thesis says fade-back-to-pin; the data says continuation-into-close.

**All-Friday null check**: Sh +0.10 across 13 trades. **OPEX-only is WORSE by Δ=−0.34** — the monthly-OPEX calendar lock has no incremental signal over generic Friday-afternoon fade (which is itself near-zero).

**Long/short split**: LONG-only Sh +0.38 (n=2), SHORT-only Sh −0.47 (n=5). Long-only is uninterpretable on n=2; consistent with the underlying asymmetry that NDX has secular drift but not pinning structure.

**Cost-insensitivity**: Sh moves from −0.24 at zero cost to −0.26 at 3pt. The negative Sharpe is signal-driven, not friction-driven (lesson #26 diagnostic — cost-zero ≈ baseline ⇒ "no edge" rather than "edge eaten by friction").

### SPX500 — REJECT

M5, RTH 09:30-16:00 ET, 146,054 bars, 1,884 trading days, 85 monthly-OPEX Fridays.

**Baseline**:

| Metric | Value | vs threshold |
|---|---|---|
| Sharpe | −0.68 | FAIL |
| Max DD | −3.68% | PASS |
| Trades | 5 (0.7/yr) | FAIL |
| WR / PF | 0.0% / 0.00 | FAIL |

All 5 baseline trades lost. Below threshold of significance, but cleanly directional.

**Regime breakdown**:

| Window | Sh | trades |
|---|---|---|
| 2019-2020 pre/COVID | −0.14 | 1 |
| 2021-2022 vol | −0.26 | 1 |
| **2023-2026 holdout** | **−1.01** | 3 |

Holdout is the worst regime on SPX500 too — same 0DTE-decay signature pre-committed in the thesis.

**Null-check (continuation)**: Sh +0.64, WR 100% (5/5), avg win +0.665%. **Direction-gap −1.33** = decisively INVERTED. SPX500 OPEX-day AM moves carry into the close with high reliability — the exact opposite of the pin thesis. SPX is THE poster-child instrument for the academic pinning literature (Golez/Jackwerth 2012), so this is the strongest possible falsification of the thesis on its highest-conviction venue.

**All-Friday null check**: Sh −0.26, 16 trades. OPEX-only loses by Δ=−0.42 — calendar lock is anti-load-bearing.

**Cost-insensitivity**: −0.66 (zero cost) → −0.73 (3pt). Same diagnostic — signal-driven loss, not cost-driven.

## Cross-instrument mechanistic interpretation

Two independent index venues, one decade of monthly OPEX data, **both sign-inverted in the same direction**. The pin thesis is not refuted by noise — it is refuted by a consistent pattern across the two instruments where it should work strongest.

Three reinforcing factors:

1. **0DTE has cannibalized monthly OPEX OI.** CBOE data shows 0DTE option volume on SPX rose from ~5% of total in 2019 to >50% by 2024. Monthly OPEX OI in absolute terms is still large, but dealer hedging-flow magnitude is driven by *aggregate* gamma exposure across all expiries, and on any given day the 0DTE book swamps the leftover monthly book. The "third Friday pin" was a real intraday signature when monthly was the dominant gamma — that condition no longer holds.

2. **0DTE dealer gamma is structurally short, not long.** Retail/fund customer flow on 0DTE is net-long calls (most documented) and tends to chase intraday direction (call-buying after rallies, put-buying after dips). Dealers absorb this as *short-gamma* exposure, which forces them to *trend-amplify* via delta hedging (sell rallies → buy after they continue up, vice versa). The post-2022 intraday tape on Fridays is structurally trend-continuing, not mean-reverting. This is the exact dual of the pre-0DTE monthly-OPEX-pin mechanism.

3. **Friday-specific drift bias.** Above the OPEX-specific 0DTE effect, Fridays in 2023-2026 have shown a generic continuation bias on US indices — consistent with the all-Friday null check (Sh +0.10 NDX) being non-negative while baseline OPEX-Friday fade (Sh −0.25) is worse. The OPEX-only restriction selects FOR the days where the continuation bias is strongest, opposite to the thesis.

Combined: the deployed lunch_fade strategy works *despite* this Friday-PM trend bias because its mechanism (institutional flow vacuum in 11:30-13:30 ET) is calendar-orthogonal — it doesn't care about OPEX-day microstructure. OPEX-pin-fade has no such orthogonal protection; it sits squarely in the late-PM trend window that 0DTE amplifies.

## Lessons captured (added to RESEARCH_NOTES.md)

- **Monthly-OPEX pin-fade on US indices is dead post-0DTE.** Adds to lessons #1, #27, #28: another generic "fade-to-pin" intraday MR thesis on US indices sign-inverts. The 0DTE structural-short-gamma narrative now has *three* independent supporting observations (vwap_fade, eod_unwind, opex_pin_fade) all from different angles. Lesson #28's holdout-decay diagnostic predicted exactly this outcome before the backtest was run.
- **Calendar-restricted populations make AM-move-threshold filters miscalibrate.** Lunch_fade's `thr=0.5` was tuned on a 1885-day universe with ~1900 candidate-days; here on an 85-day universe the same threshold leaves only 5-7 trades, defeating the strategy's own population. For any "subset-of-days × magnitude-filter" structure: re-calibrate the filter against the subset's own distribution, not the parent universe's.

## Files

- Thesis: this file.
- Demo: `experiments/opex_pin_fade/opex_pin_fade_demo.py`.
- Data: `ohlc_data/NDX100_M5.csv`, `ohlc_data/SPX500_M5.csv`.
- Run commands:
  - `OPEX_SYMBOL=NDX100 venv/Scripts/python.exe experiments/opex_pin_fade/opex_pin_fade_demo.py`
  - `OPEX_SYMBOL=SPX500 venv/Scripts/python.exe experiments/opex_pin_fade/opex_pin_fade_demo.py`

## Files

- Thesis: this file.
- Demo: `experiments/opex_pin_fade/opex_pin_fade_demo.py`.
- Data:
  - `ohlc_data/NDX100_M5.csv` (already on disk, broker-confirmed)
  - `ohlc_data/SPX500_M5.csv` (already on disk, broker-confirmed)
- Run commands:
  - `OPEX_SYMBOL=NDX100 venv/Scripts/python.exe experiments/opex_pin_fade/opex_pin_fade_demo.py`
  - `OPEX_SYMBOL=SPX500 venv/Scripts/python.exe experiments/opex_pin_fade/opex_pin_fade_demo.py`
