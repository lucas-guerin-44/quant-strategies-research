# ORB_DAX × Market Sentiment Overlay — Layer 1 (quantified composite)

**Status**: Phase 2 complete (2026-05-21). Layer 1 — cheap, on-disk, point-in-time-clean sentiment composite — fully evaluated. Layer 2 (LLM-scored headline sentiment) **decision: not pursued for ORB_DAX overlay** based on Layer 1 evidence (see verdict).

**Verdict**: **REJECT — pre-committed hypothesis falsified, mirror direction marginal at best.** The composite carries informational content but in the OPPOSITE direction from the original intuition: risk-ON days are the *worst* environment for ORB_DAX LONG breakouts, not the best. Even the mirror-image overlay fails the pre-committed null-check (+0.20 threshold) and the lift sits right at the +0.10 floor — pre-committed bars say do not deploy.

Headline numbers (re-simulated baseline, 1pt RT cost, 2019-01 → 2026-04):

| Variant | Sharpe | MDD | Trades | Note |
|---|---|---|---|---|
| Baseline (deployed) | **+0.46** | -11.3% | 1457 | re-impl; deployed orb.md reports +0.76 — see methodological note below |
| `gate_q1` (skip risk-off, hypothesized) | +0.46 | -8.8% | 1164 | delta +0.004 — **FAIL** pre-committed +0.10 lift |
| `gate_neg` (skip composite < 0) | +0.38 | -6.1% | 855 | worse |
| `size_q5` (2× risk-on, hypothesized) | +0.34 | -14.7% | 1457 | worse, worse MDD |
| `combo` (gate Q1 + size Q5) | +0.29 | -11.9% | 1164 | worse |
| `inv_gate` (skip risk-ON Q5, **null variant**) | **+0.56** | -8.7% | 1169 | beats baseline by +0.099 |
| `inv_size` (2× risk-off, null) | +0.38 | -17.8% | 1457 | worse |

**Pre-committed kill-criteria check** (against `gate_q1`):
- Sharpe lift ≥ +0.10: **FAIL** (+0.004)
- MDD not worse by >1pp: PASS
- Trade count ≥ 200: PASS (1164)
- Null check (G-Q1 − Inv-G-Q1 ≥ +0.20): **FAIL DECISIVELY** (gap = **-0.096**, the inversion BEATS the hypothesis)

## Why the inversion can't just be adopted

`inv_gate` looks attractive (Sh +0.56 vs +0.46 baseline, +0.099 lift, -8.7% MDD better than baseline -11.3%). But:

1. **It is a post-hoc redirection.** The thesis was pre-committed to "risk-on helps, risk-off hurts." Adopting the mirror after seeing the data is exactly the goalpost-moving pattern the `orb.md` lessons warn against ("optimized variant wins in-sample that fail OOS is the single most common failure mode").
2. **Symmetric null check still fails.** With `inv_gate` re-cast as the candidate, its null is `gate_q1` (skip the opposite quintile). Gap = +0.56 − +0.46 = **+0.10**, still half the pre-committed +0.20 null-check threshold.
3. **The 2021-2022 regime breaks** under `gate_q1` (Sh +0.12 baseline → **-0.46** filtered). High-vol days were the high-payoff days that year; filtering them caused harm. The mirror has the symmetric risk in any future regime where the "wrong" tail becomes the alpha-bearing tail.

Honest deploy path: **do not overlay sentiment on ORB_DAX**. Keep the deployed baseline. Re-test the mirror direction on PRE-COMMITTED future OOS (2026-Q3+) with the inverted hypothesis written down ahead of time. If it holds at +0.10 lift on truly unseen data, reconsider.

## Per-quintile diagnostic (where the signal actually lives)

Trade-level PnL by entry-day composite bucket (293 / 873 / 288 trades):

| Bucket | Sentiment reading | n | avg PnL | WR | sum PnL |
|---|---|---|---|---|---|
| Bottom Q1 | risk-OFF (high VIX, SPX down overnight, DAX below MAs) | 293 | **+0.0262%** | 27.0% | +7.68% |
| Mid Q2-Q4 | neutral | 873 | +0.0238% | 26.1% | **+20.77%** |
| Top Q5 | risk-ON (low VIX, SPX up overnight, DAX above MAs) | 288 | **-0.0026%** | 20.1% | **-0.74%** |

The top quintile (the "best" tape by every retail-intuition metric) is the **only losing bucket** at the per-trade level and the lowest win rate. The risk-off quintile is *marginally* the best per-trade. The mid quintile carries the bulk of cumulative PnL by sheer count.

## Regime breakdown (gate_q1 — hypothesized direction)

| Window | Baseline Sh | gate_q1 Sh | Baseline MDD | gate_q1 MDD |
|---|---|---|---|---|
| 2019-2020 | +0.446 | +0.595 | -8.80% | -4.82% |
| 2021-2022 | +0.123 | **-0.456** | -11.29% | -8.79% |
| 2023-2026 holdout | +0.806 | **+0.967** | -5.04% | -4.06% |

`gate_q1` is whipsawed by the 2021-2022 vol regime — that's where risk-off filters threw out the alpha-bearing days. 2/3 windows pass; the middle window catastrophically fails. This is precisely the failure shape the regime-window check exists to catch.

## Cost sensitivity (gate_q1)

| Cost RT | Sharpe |
|---|---|
| 0.5pt | +0.594 |
| 1.0pt | +0.464 |
| 1.5pt | +0.334 |
| 2.0pt | +0.205 |

Linear collapse with cost — same shape as baseline ORB_DAX (cost-zero edge eaten linearly), so the cost-zero-Sharpe diagnostic doesn't help distinguish "no edge" from "edge eaten by friction" for the overlay specifically.

## Mechanistic interpretation — why the mirror direction has signal

Three plausible mechanisms (non-exclusive):

1. **Risk-on exhaustion at the Xetra open.** When the US session closed strong, VIX is at recent lows, and DAX is above MAs, the *most* of the up-move has already been priced into the GER40 CFD overnight (FDAX trades 22:00-08:00 Berlin). The Xetra-open auction is then setting marks at the top of the digested move. The first M5 break above OR-high tends to be a buying climax that fades — the marginal buyer who triggers the breakout is buying the high after the move is done.

2. **Risk-off as information-gap rather than panic.** Counter-intuitively, risk-off overnight (VIX up, SPX down, term-structure flatter) often *resolves* into a genuine information event for European stocks during the Xetra auction — German exporters, DAX banks, and ASML/SAP carry US-driven overnight news that needs price discovery at the open. The opening range captures that resolution; the breakout direction is the new information cut. Note: this matches the **opening-impulse mechanism** at the core of orb.md — the strategy works *because* there is information to incorporate at the open, and risk-off nights deliver more of that.

3. **Q5 days have weaker fade-tail asymmetry.** With low VIX, the realized intraday range on DAX shrinks (~30-40% smaller bars), so the OR is tighter, the breakout signal is more easily noise-driven, and the stop is closer relative to noise. The bottom 20% Q1 days have wider ORs that are harder to break by chance, so the breakout has higher information content per unit of trade.

These are post-hoc; do not treat them as load-bearing. They are the kind of story we would want a pre-committed Phase-2 retest in 2026-Q3+ to either confirm or refute.

## Lesson for next-Q3 OOS retest

If we revisit, the pre-commit should be the **inverted form**:

> "Gating out the top sentiment quintile (composite ≥ q80, expanding-window) of GER40 ORB T+180 LONG-only entries lifts Sharpe by ≥+0.20 over the deployed baseline on data after 2026-04-18, without worsening MDD by >1pp, with the mirror-direction (`gate_q1`) confirming the gap by underperforming `inv_gate` by ≥+0.20."

That is a real, testable, pre-committed hypothesis on unseen data, with the lessons of this Phase 2 run baked in. Layer 2 (LLM headlines) becomes more interesting *if* the mirror Layer 1 direction validates on OOS — because then the question becomes whether headline-tone resolves the risk-on/exhaustion vs risk-off/info-gap distinction more crisply than the quantitative composite does.

## Methodological note — baseline Sharpe discrepancy

This re-implementation produces baseline Sharpe **+0.46** vs the +0.76 reported in `orb.md` for the same nominal config (T+180 LONG-only, 1pt RT, GER40 M5). Trade count matches within ~1% (1457 here vs 1440 reported). Possible causes (not investigated this session): (a) bar-level Sharpe annualization differs based on session-minute count, (b) cost-charging amortization differs (entire cost on exit bar vs split across trade duration), (c) end-date 2026-04-17 vs 2026-04-18. Crucial for this experiment: **the overlay comparison uses the same re-implementation throughout, so relative results (overlay vs baseline within this demo) are internally valid even if absolute level differs from orb.md.** The discrepancy is flagged here for follow-up; it does not affect the Phase 2 verdict for the overlay since all overlay variants are scored against the *internal* +0.46 baseline.

---

## Thesis (mechanism, as pre-committed)

The deployed `orb_dax` strategy (T+180 LONG-only Xetra ORB) is mechanism-clean and regime-positive (full Sh +0.76, holdout +0.93, 3/3 regimes). It is, however, **session-blind**: every Xetra open is treated identically regardless of what the world said overnight. The hypothesis is that conditioning entry on a quantitative "market sentiment" reading at the Xetra-open instant improves selectivity:

1. **Risk-off panic days** (VIX up sharply overnight, SPX overnight down hard, term-structure backwardated) damage opening-range breakouts because the breakout often flips into a stop-run as the EU session digests the US-session weakness, and dispersion overwhelms single-name momentum-continuation.
2. **Calm-up days** (low VIX, modest SPX overnight up, term-structure contango, DAX above MA50/MA200) are the natural habitat for a long-only opening-impulse strategy — the up-breakout aligns with the dominant macro tape rather than fighting it.
3. **Neutral days** carry the bulk of the deployed-strategy edge already; overlay should not destroy them.

Net hypothesis: gating out the worst sentiment quintile (and/or sizing up the best quintile) lifts Sharpe and trims MDD without collapsing trade count below the deploy floor.

This is a **selectivity overlay**, not a new strategy. The base mechanism does not change; only the day-by-day participation decision does.

## Key reference

- Whaley, R. E. (2009). "Understanding the VIX." *Journal of Portfolio Management* 35(3). VIX as forward-looking risk-aversion premium.
- Bollerslev, Tauchen, Zhou (2009). "Expected stock returns and variance risk premia." *Review of Financial Studies* 22(11). Variance-risk-premium predicts returns at short horizons.
- Connolly, Stivers, Sun (2005). "Stock market uncertainty and the stock-bond return relation." *JFQA* 40(1). Risk-aversion regimes flip cross-asset correlation structure → relevant to whether DAX equity-impulse "behaves" intraday.

## Signal math — sentiment composite (Layer 1)

All inputs are read on the **prior-day D1 close**, which is observable strictly before Xetra opens at 09:00 Berlin (US close = 22:00 Berlin previous calendar day; EU D1 close = previous Xetra close at 17:30 Berlin). Zero look-ahead by construction.

```
Inputs (all D1, point-in-time = trading-day t-1 close):
  VIX_close[t-1]         CBOE VIX (US fear gauge; 0.85 corr w/ V2X)
  VIX3M_close[t-1]       3-month VIX (term-structure ref)
  SPX_close[t-1]         SPX500 (overnight US tape)
  GER40_close[t-1]       DAX cash (own-trend reference)
  EURUSD_close[t-1]      EUR/USD (DXY-inverse proxy)
  HYG_close[t-1]         HY credit ETF (risk-on/off)

Derived features (signs chosen so larger = MORE risk-ON / bullish):
  f_vix_z         = - z_score(VIX, 60d)
  f_vix_chg       = - (VIX[t-1] / VIX[t-2] - 1)
  f_term          = - (VIX[t-1] / VIX3M[t-1] - 1)        # backwardation < 0 ⇒ risk-off
  f_spx_overnight = SPX[t-1] / SPX[t-2] - 1
  f_dax_trend     = +1 if GER40[t-1] > MA50(GER40, t-1) and GER40[t-1] > MA200(GER40, t-1)
                    -1 if GER40[t-1] < MA50 and GER40[t-1] < MA200
                    else 0
  f_eur_chg       = EURUSD[t-1] / EURUSD[t-6] - 1         # 5d weak-dollar = risk-on
  f_hyg_chg       = HYG[t-1] / HYG[t-6] - 1               # 5d credit improvement = risk-on

Each feature is converted to a unit-variance z-score over a 252-day trailing window
(using EXPANDING window before 252 obs, NEVER full-sample stats).

composite[t] = mean( z(f_vix_z), z(f_vix_chg), z(f_term),
                     z(f_spx_overnight), z(f_dax_trend),
                     z(f_eur_chg), z(f_hyg_chg) )
```

Composite is a daily scalar, positive = risk-on / bullish-tape, negative = risk-off / bearish-tape.

## Overlay variants

Applied on top of the existing `orb_dax` T+180 LONG-only baseline trades:

| Variant | Rule |
|---|---|
| **Baseline (control)** | No filter — exactly the deployed strategy |
| **G-Q1**: gate worst 20% | Skip trades whose entry-day composite is in the bottom quintile |
| **G-neg**: gate negative | Skip trades whose entry-day composite < 0 |
| **S-Q5**: size top 20% | 2× lot on top-quintile composite, 1× otherwise |
| **G+S**: gate Q1, size Q5 | Combined |
| **Inv-G-Q1** (null) | Invert sentiment: gate trades whose composite is in **top** quintile (must hurt) |
| **Inv-S-Q5** (null) | 2× lot on **bottom** quintile (must hurt) |

The inverted variants are the directional null check — if `Inv-G-Q1` or `Inv-S-Q5` improves on baseline, the composite has no real informational content and we are just reshaping the distribution.

## Why retail-accessible

All inputs are free, daily, and lagged-1-day relative to entry. No paid news feeds, no broker-specific filings, no privileged data. Composite is computed once per day from 6 D1 series already on disk.

## Universe

- **Target**: existing deployed `orb_dax` strategy on GER40 M5, 2019-01-02 → 2026-04-17.
- **Sentiment inputs**: VIX, VIX3M, SPX500, GER40 D1 (all on disk); EURUSD D1, HYG D1 (on disk).

## Expected performance

If sentiment carries selectivity content, expect on the gated-Q1 variant:
- Sharpe lift +0.15 to +0.30 absolute (current full Sh +0.76 → +0.90 to +1.05).
- Trade-count drop ~20% (from 1440 → ~1150 trades), still ≥ 200 floor.
- MDD improvement of 1-2 percentage points if the worst quintile concentrates losing trades.
- Holdout (2023-26) lift at least as large as full-sample; otherwise it's curve-fit.

If no signal: composite quintiles produce statistically indistinguishable Sharpes (~all within ±0.15 of baseline). That is also a clean result — it tells us Layer 1 quantified sentiment is already priced into the M5 tape by the time the breakout fires, and Layer 2 (LLM news) becomes the only path forward.

## Fail conditions (pre-committed)

The overlay PASSES if **all** hold on the G-Q1 variant:
- Full-period Sharpe improves by ≥ +0.10 absolute over baseline (+0.76 → ≥ +0.86).
- Holdout 2023-2026 Sharpe improves by ≥ +0.10 absolute (+0.93 → ≥ +1.03).
- Max DD does not worsen by more than 1 percentage point.
- Trade count remains ≥ 200 over the 7-year window.
- **Null-check fade-gap**: `Inv-G-Q1` Sharpe must be **at least +0.20 BELOW** the G-Q1 Sharpe. If inverting the sentiment doesn't hurt clearly more than applying it helps, the composite is noise.

The overlay is MARGINAL if Sharpe improves by 0.0 to +0.10 absolute and null-check passes. **Do not deploy** in MARGINAL — keep the simple baseline.

The overlay is REJECTED if any of: Sharpe doesn't improve, holdout doesn't improve, MDD worsens >1pp, or null-check `Inv-G-Q1` Sharpe is **within ±0.20** of G-Q1.

## Why this might fail (red flags)

1. **VIX is already reflected in M5 GER40 open price** by the time the OR fires. The breakout is downstream of risk-off pricing; sentiment overlay may be re-applying information already in the tape.
2. **Composite over-weights US tape** (VIX, SPX, HYG are all USD). DAX has its own opening-auction mechanism — US-tape overlay may misclassify "DAX up despite US down" days that are the highest-edge days.
3. **Long-only strategy + risk-off filter = small sample of "good" days**, raising sampling noise. The 20%-gate variant cuts trades from 1440 to ~1150 — still fine, but composite-Q5 (top 20%) is only ~290 trades, low power.
4. **In-sample threshold tuning**: quintile breakpoints are themselves estimated from the data. We use **expanding-window** breakpoints (not full-sample) to keep this honest, but the choice of "five quintiles" is itself a hyperparameter.
5. **Sentiment may help only in regime windows where ORB already works**, i.e., redundant with existing edge. The interesting question is whether sentiment adds *orthogonal* info — null-check addresses this partially but a full-orthogonality decomposition isn't run here.

## Phase 1 → 2 plan

- [x] Read `orb.md` and `orb_demo.py` to confirm style and re-implement the deployed baseline.
- [x] Verify data on disk: VIX, VIX3M, SPX500, GER40, EURUSD, HYG D1 all present.
- [x] Pre-commit fail conditions and null-check threshold.
- [x] Run baseline (re-impl gave +0.46; +0.76 deploy figure differs — see methodological note).
- [x] Build sentiment composite with expanding-window z-scoring.
- [x] Run 6 overlay variants (G-Q1, G-neg, S-Q5, G+S, Inv-G-Q1, Inv-S-Q5).
- [x] Regime breakdown (2019-2020 / 2021-2022 / 2023-2026).
- [x] Cost sensitivity (0.5 / 1.0 / 1.5 / 2.0 pt RT).
- [~] Per-feature ablation — **not run**; composite did not pass, so ablation is moot at this stage. Add to next-Q3 OOS retest plan if mirror direction validates.
- [x] Update this doc with results table + verdict.
- [x] Update `docs/STATE.md`.

## Files

- Thesis: this file (`experiments/orb_dax_sentiment/orb_dax_sentiment.md`).
- Demo: `experiments/orb_dax_sentiment/sentiment_demo.py` — runs baseline + 6 overlays + regime + cost.
- Data dependencies (all on disk):
  - `ohlc_data/GER40_M5.csv` (base strategy)
  - `ohlc_data/GER40_D1.csv` (trend filter)
  - `ohlc_data/VIX_D1.csv`, `VIX3M_D1.csv` (fear + term structure)
  - `ohlc_data/SPX500_D1.csv` (overnight US tape)
  - `ohlc_data/EURUSD_D1.csv` (DXY-inverse proxy)
  - `ohlc_data/HYG_D1.csv` (credit / risk-on proxy)
