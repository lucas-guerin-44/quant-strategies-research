# Project State

Index of every experiment with verdict + headline numbers. Truth is in the linked thesis docs.
Lessons → [RESEARCH_NOTES.md](RESEARCH_NOTES.md). Rejects → [STATE_GRAVEYARD.md](STATE_GRAVEYARD.md). Live-book posture (expected results, sizing tiers, gates, cadence, candid fears) → [BOOK_PLAN.md](BOOK_PLAN.md).

- **Live** = MT5 VPS only (private). QC retired 2026-05.
- **Tradeability**: datalake M5 ⇒ broker-confirmed; D1-only ⇒ verify via `scripts/mt5_fetch.py --list-symbols`.
- **Datalake**: private; configured via `DATALAKE_URL` / `DATALAKE_API_KEY` env vars. Endpoints: `/catalog`, `/instruments/<symbol>`, `/query`.

---

## Snapshot (2026-05-25)

| Status | Count | Names |
|---|---|---|
| Live (MT5 VPS, paper) | 5 | `orb_dax`, `lunch_fade`, `xau_session`, `event_calendar`, `xau_br_m15` |
| Retired from live | 1 | `xs_momentum` |
| Validated, blocked at broker | 3 | `treasury_trend` (no bonds), `softs_ensemble` (D1 depth too short), `pead_midcap` (research-PASS Sh +0.76 / 3-of-3 regimes / dir-gap +1.71, but **20d hold × CFD swap ~110bp RT eats >half of 100-200bp gross** — deployable on cash equities, not on CFD book) |
| Keep-for-reference / watch-list | 3 | `tsmom`, `btc_trend`, `btc_intraday` |
| Pending Phase 2 | 1 | `gold_trend` |
| **Portfolio overlay — PASS** | 1 | **`portfolio_risk_parity` (inv-vol sizing across 7 strategies; book Sh +1.71 → +1.92, +0.21 lift, 3/4 regimes positive; deploy = static quarterly EA sizing review)** |
| Diagnostic studies (no deploy path) | 1 | `regime_hurst_diagnostic` (MARGINAL — TSMOM-side only) |
| Unvalidated (inherited) | 1 | `imbalance` |
| Institutional-only | 3 | `fx_session` (retail RT cost eats edge); `xag_session` (Eightcap XAG 8bp spread eats Variant C gross); `xpt_session` (Eightcap XPT Asia 23bp spread; killed without Phase 2 — cost ceiling decisive) |
| Rejected | 54 | → [STATE_GRAVEYARD.md](STATE_GRAVEYARD.md) — incl. `xau_break_retest` (M5), `xau_imbalance` (M5, upgraded REJECT after M15 follow-up confirmed W1/W2 weakness), `xau_imbalance_m15` |
| **Total** | **73** | |

---

## DEPLOYED (MT5 VPS — full thesis, params, EA, and sizing are private)

Each entry below shows research-level metrics and the deploy date; mechanism is summarised at the *type* level. Exact parameters, sizing, EA file, and live tracking are kept private to preserve the edge.

### `orb_dax` — DEPLOYED_PAPER
- GER40 H1 | Sh +0.76 / holdout +0.93 / MDD -7.8% / dir-gap +1.04 | 1440 trades (197/yr)
- Mechanism: Xetra opening-range breakout family, LONG-only
- 3/3 regimes positive; cost headroom > 1pt RT
- deployed 2026-04-22

### `lunch_fade` — DEPLOYED_PAPER
- NDX100 M5 | Sh +1.02 / holdout +1.51 / MDD -4.2% / dir-gap +1.87 | 117 trades (16/yr LONG)
- Mechanism: lunch-vacuum fade of NY-AM directional impulse
- 3/3 regimes positive, holdout BEST; very cost-insensitive
- deployed 2026-05-13

### `xau_session` — DEPLOYED_PAPER
- XAUUSD H1 | Sh +0.79 / W4 binding +1.23 / MDD -3.7% / dir-gap +2.28 | 321 trades (39/yr)
- Mechanism: Asian-session-handoff variant with conditional prior-NY filter
- Phases 2-7 all PASS in one session; control-hold confirms session-specific
- deployed 2026-05-16

### `event_calendar` — DEPLOYED_PAPER
- NDX100 H1 | 4-event book (FOMC, CPI, RS, NFP) | ~44 trades/yr | MDD -8.65%
- Per-event research Sh range: +0.37 to +1.22; direction conditional (LONG/SHORT) per event family
- Single multi-event EA; FOMC live 2026-05-22; CPI/RS/NFP paper-enabled 2026-05-24
- XAU cross-asset extension REJECTED 2026-05-25 (lesson #62)

### `xau_break_retest_m15` — DEPLOYED_PAPER
- XAUUSD M15 NY-AM session | Break-of-Structure + retest, **FADE** direction (continuation = REJECT)
- Sh **+1.49** full / **W1 +1.50 / W2 +1.70 / W3 +1.36** | MDD -2.17% | n=753 (95/yr) | WR 38.6% / PF 1.72 | fade-gap +1.92 | deflated Sh +1.30
- All 11/11 Phase 2 kill criteria PASS at baseline; ATR-floor + ADX variants all INSUFFICIENT_N (lesson #63)
- **Phase 3**: ALL 4 controls PASS. C1 cross-session decisive (in-session vs off-sessions Δ Sh > +1.7). C2 block-bootstrap CIs all lower-bounds positive. C4 macro-release calendar PASS (non-macro > macro; mechanism is broader than news-overshoot). C3 real-tick spread audit PASS (datalake ticks, n=47,941: p95 well under deploy bar).
- Mechanism: MM re-anchoring at broken levels + absence of NY-AM directional drift on XAU
- deployed 2026-05-25

---

## RETIRED FROM LIVE

### [xs_momentum](../experiments/xs_momentum/xs_momentum.md) — RETIRED_FROM_LIVE
- 24-instr multi-asset | Sh 0.92 research / **0.35 live** / holdout 1.33 / MDD -23.1%
- 189d trailing return, long top-5 EW, quarterly rebal
- Ran QC paper through early 2026. Retired 2026-05 (QC no longer deploy path)
- Canonical "research-to-live haircut" reference: -0.57 Sh observed

---

## VALIDATED — BROKER ACCESS REQUIRED

### [treasury_trend](../experiments/treasury_trend/treasury_trend.md) — VALIDATED_NO_DEPLOY
- IEF (Tiingo D1, 24y) | Sh 0.67 / holdout 0.42 / MDD -8.1% | 77 trades (7/yr)
- Multi-horizon TSMOM (1M/3M/12M) with BIL/SHY cash flat
- All 7 phases PASS; ~0 corr vs xs_momentum
- **Blocker**: Eightcap MT5 does not offer US Treasury CFDs (confirmed 2026-05-13)

### [softs_ensemble](../experiments/softs_ensemble/softs_ensemble.md) — VALIDATED_NO_DEPLOY
- 6 softs (Yahoo continuous) | Sh 0.85 / holdout 1.44 / MDD -13.3%
- Equal-weight TSMOM ensemble (multi-horizon 1M/3M/12M)
- Phases 2-7 PASS. Q1 2026 real-OOS +1.10% vs B&H -6.57% through cocoa crash
- **Blocker**: Eightcap D1 history for available softs only 332-382 bars (~16-18 months); 12M-lookback TSMOM needs longer

### [pead_midcap](../experiments/pead_midcap/pead_midcap.md) — VALIDATED_BLOCKED_AT_COST (2026-05-24)
- 168-name Eightcap non-Mag7 NAS+NYS universe | D1 bars MT5-fetched, 13,541 yfinance earnings events
- Per-event PEAD (drift, MIN_SUE=5%, HOLD=20d, commission=10bp): Sh **+0.76** / concurrent-MDD **-24.76%** (marginal) / 1663 events 11.2y / WR 53.6% / PF 1.24
- All 4 Phase 2 commission-only kill criteria PASS; dir-gap **+1.71** (decisive); 3/3 regimes positive incl. holdout +0.77; cost-insensitive to 30bp commission
- HOLD sweep monotonic: 20d Sh +0.76 → 60d Sh +1.05; MIN_SUE peak 5%; XS-decile basket REJECTS (tails don't drift; deploy form = per-event book NOT XS)
- **Blocker**: 20-day-hold CFD swap cost. Eightcap (and all CFD brokers) charge ~7% annualized financing on long stock-CFDs = **~55bp per side per 20d hold = ~110bp RT** on long-short basket. Per-event gross 100-200bp → swap eats >50% → live Sharpe ~0 or negative on CFD execution. NOT a research failure; the pre-commit cost model omitted CFD swap (which is unique to CFDs and doesn't appear in equity-cash backtests).
- Deployable shapes elsewhere: (a) cash equities (IBKR margin, prime brokerage) where 20d holds have negligible carry — viable at any AUM > $250k; (b) shorter-hold variants (HOLD ≤ 3 days) on CFD if Sharpe holds — backtest sweep showed HOLD=1d Sh +0.15, HOLD=5d Sh +0.01 — does NOT survive short-hold compression; the multi-day drift IS the signal.
- See [RESEARCH_NOTES.md lesson #59](RESEARCH_NOTES.md) for the CFD-swap-ceiling Phase 0 gate now required on all multi-day-hold CFD theses.

---

## KEEP-FOR-REFERENCE

### [btc_trend](../experiments/btc_trend/btc_trend.md) — KEEP_FOR_REFERENCE
- BTCUSD D1 | Sh 0.83 / real-OOS -0.32 / walk-fwd mean OOS 0.54 / min OOS -0.03
- Multi-horizon TSMOM + K=3 ATR pyramid, vol-target 15%, monthly rebal
- Two failure modes: (1) parabola-V vulnerability (S1+S5 both blew up); (2) institutionalization decay (W4 Sh +0.50 vs +1.38/+1.61 earlier)
- closed 2026-05-13 — see lesson #29 (walk-forward replaces single-split for TSMOM)

### [tsmom](../experiments/tsmom/tsmom.md) — KEEP_FOR_REFERENCE
- 24-instr long-only | Sh 0.40 / holdout 1.14 / MDD -15.5% | 384 trades (35/yr)
- 12-1 trailing return long-when-positive, classical TSMOM
- Mechanically valid but +0.69 corr with xs_momentum → no diversification value

### [btc_intraday](../experiments/btc_intraday/btc_intraday.md) — MARGINAL
- BTCUSD H1 | Sh 0.72 / W4 0.83 / W4-25-26 binding 0.64 PASS / **W4-26 -2.71 (n=20) FAIL**
- Hour-00 UTC drift + |prior-24h z|>1.0 + Tue/Thu/Fri filter, 2h hold
- 3/7 kill criteria PASS. Honest verdict MARGINAL. Two valid options: tombstone now OR wait + re-run on OOS 2026Q2-Q3 (~2026-08-15) with unchanged pre-commits
- closed 2026-05-16; regime-gate overlays NOT valid (goalpost-moving)

---

## PENDING

### [gold_trend](../experiments/gold_trend/gold_trend.md) — UNVALIDATED
- XAUUSD | Phase 1 in-progress
- Classical 12-1 single-instrument TSMOM with vol-targeting; Phase 2 kill if doesn't beat B&H

### [imbalance](../experiments/imbalance/imbalance.md) — UNVALIDATED (inherited)
- 24-instr universe | FVG 3-bar pattern mean-reversion
- Inherited from engine repo, not yet through Phase 1-8 workflow

### [regime_hurst_diagnostic](../experiments/regime_hurst_diagnostic/regime_hurst_diagnostic.md) — MARGINAL (asymmetric, 2026-05-23)
- 8 D1 instruments (SPX/NDX/GER/BTC/ETH/XAU/USO/EUR) | rolling 252d DFA Hurst
- TSMOM-side PASS: 6/8 full-sample, 3/5 W4-eligible post-2023 (Δ Sharpe ≥ +0.30 in H>0.55 vs H<0.45)
- MR-side FAIL: 4/8 full-sample, **0/5 post-2023** — same 0DTE-MR-kill that took down opex_pin_fade / earnings_continuation_mag7 / eth_btc_ratio_mr
- Hurst-as-MR-gate now tombstoned at universe level (corroborates lesson #43)
- Follow-up `tsmom_hurst_gated` ran 2026-05-23 → REJECT (gate redundant with 12-1 signal at portfolio level; null-check failed)
- Combined verdict: Hurst-overlay family fully tombstoned for the existing repo's momentum-family strategies

---

## DEPLOY CANDIDATES (Phase 2 PASS, pending Phase 7-8 build)

(none)

---

## PORTFOLIO OVERLAYS

### `portfolio_risk_parity` — PHASE 2 PASS (2026-05-24)
- Inv-vol sizing overlay across the deployed book
- Research: book Sh **+1.71 EQ → +1.92 RP (lift +0.21)** | MDD essentially flat | **3/4 regimes positive incl. holdout**
- Key insight: dynamic monthly rebal contributes ~0; static inv-vol gives the entire lift (sparse-event strategies fall back to full-sample vol). Deploy as **quarterly sizing review**, not pipelined rebal.
- Re-audit 2026-05-25 with 8th component added: book Sh lifts to **+2.33 RP**, MDD tightens ~50% (-0.75% audit notional)
- Detailed methodology + weights + implementation: private

---

## CROSS-EXPERIMENT PATTERNS

Findings that emerged from multiple experiments and now constrain what's worth proposing. Full detail in [RESEARCH_NOTES.md](RESEARCH_NOTES.md).

-13. **Scheduled US-macro LONG drift on NDX is *first-read-mid-month-mid-cycle* specific — PCE falsifies lesson #56's broad framing (2026-05-24).** `pre_pce_drift` REJECT decisive: LONG full Sh +0.07 / **W4 Sh −1.23** (vs CPI W4 Sh +1.15 on near-identical inflation info), WF 3/3 OOS NEGATIVE monotonic decay (−0.14 → −0.55 → −1.23), null-gap +0.161 (half +0.30 threshold), 6/9 binding pre-commits FAIL. **Placebo benign** (mean −0.040%, t −0.29) RULES OUT month-end structural-drift confound — rejection is PCE-specific signal failure, NOT calendar artefact. The distinguishing axes (extracted ex-post): FOMC (mid-cycle Wed, first-read) PASSES LONG; CPI (mid-month Tue/Wed/Thu, first-read inflation) PASSES LONG; Retail Sales (mid-month Wed, first-read real economy) PASSES LONG; NFP (first-Friday, first-read, Friday-microstructure exception) PASSES SHORT; **PCE (end-of-month Friday-dominated 76%, confirming-read after CPI) has NO drift either side**. Refined framework: only events that align on (a) mid-month/mid-cycle calendar position, (b) non-Friday day-of-week, AND (c) first-read information-cycle position inherit the LONG drift. Macro-event book is therefore **NOT auto-expandable** to every US-macro release — each new candidate (PPI, JOLTS, ISM, GDP, durable goods, consumer confidence) needs explicit 3-axis screening before pre-commit. **Strengthens CPI's deploy stance** (placebo benign rules out the generic-08:30-ET-weekday null). Methodological win: the canonical-test design (close-twin event as falsification test, not diversification add) generated a sharper framework refinement than three diverse extensions would have. Pairs with #-12 — together these bound the macro-event-drift family on two axes: venue-of-asset (index, not own-commodity) AND event-shape (first-read mid-month/cycle, not confirming-read end-of-month Friday). See lesson #62.

-12. **Macro-event-drift family does NOT auto-port from index-on-US-macro to commodity-on-own-fundamental (2026-05-24).** `pre_natgas_eia` REJECT decisive: 24h pre-EIA NG Storage Report on XNGUSD M5 (Eightcap CFD, 2023-2026, 177 events). LONG -0.235% / Sh -0.53 / null-gap +0.13 (below +0.30 threshold). W3 (2023 post-Ukraine collapse) drags -1.20% mean; W4 tentatively LONG (+0.179% / Sh +0.39 / WF OOS mean +0.76) but doesn't clear null-gap or full-sample pre-commits. SHORT side loses more (-0.365%). NG-CFD cost (30bp default, 50bp realistic) eats anything < +0.30% mean gross. The macro_drift / pre_cpi_drift / pre_nfp_drift family's institutional-equity-risk-premium-accumulation flow story does NOT apply when the asset is the *underlying* of the event (XNGUSD ↔ Henry-Hub storage), the print is direct fundamentals (not policy context), weather + pipeline data leak the magnitude in advance, and asymmetric bearish tail discourages pre-event LONG positioning. **Future commodity-on-own-event theses (EIA crude, USDA WASDE)** require asset-specific positioning gates (COT, weather-error, seasonal carry) — neutral prior, no equity LONG-by-default. See lesson #61.

-11. **OPEX-pin family is fully tombstoned for US equities — 0DTE has leaked to non-Mag7 single stocks (2026-05-24).** `opex_pin_singlestock` REJECT on 15-name mid/large-cap basket (LULU, COIN, MSTR, NFLX, SHOP, CRWD, NET, AVGO, ASML, MU, ROKU, DOCU, PLTR, SNOW, NOW) — Sh -1.24, BOTH directions lose (fade -1.24, cont -0.58), holdout WORST regime (Sh -1.27 on n=360), all-Friday null delta -0.06 (calendar lock NOT load-bearing), cost-zero Sh -0.33 (signal-driven loss). Mirrors `opex_pin_fade` index REJECT exactly. Premise that mid-cap names with concentrated monthly OPEX OI would preserve the pin mechanism is REFUTED — 0DTE structural-short-gamma has metastasized from Mag7 (lesson #43) to the broader high-IV single-stock universe. **Tombstone the entire OPEX-pin family for US equities, 2023-2026.** Future "options-expiry hedging flow" theses should pivot to non-US venues, different calendar events, or genuinely low-0DTE single-stock subsets (defensives/REITs/utilities — completely different population). For any future single-stock thesis, the regime filter must be an *external* 0DTE-share indicator (CBOE single-stock 0DTE OI vs total OI), not just population selection. Methodologically, the "all-X null" test (OPEX-only vs all-Friday delta) was the cleanest mechanism falsification — when a generic baseline exists for a calendar-restricted strategy, the delta is the strongest available null.

-10. **PEAD direction-inversion is Mag7-specific, NOT market-wide (2026-05-24).** `pead_midcap` PHASE 1 PASS on 168-name Eightcap non-Mag7 mid/large-cap universe: drift Sh +0.76, dir-gap +1.71 (DECISIVE drift > fade), 3/3 regimes positive INCLUDING holdout (+0.77). Refutes the concern that lesson #43's "post-2022 fade-direction inversion on Mag7" had metastasized to the broader US single-stock universe. The Mag7-specific 0DTE-gamma flow that flipped earnings_continuation_mag7 / earnings_fade / opex_pin_fade / opex_pin_singlestock direction stays Mag7-specific (now also extending to high-IV non-Mag7 single stocks per #-11 above, but ONLY at the intraday/options-expiry mechanism level). On the broader 168-name mid-large-cap universe at the multi-day PEAD horizon, classical Bernard-Thomas drift direction is preserved. Operational implication: the deployable PEAD universe is non-Mag7 (Mag7 quarantined to regime-conditional path per `earnings_continuation_mag7`); strategy form is per-event (NOT cross-sectional decile — tails don't drift). Methodologically, `pead_midcap` introduces the **concurrent-position equity curve** as the proper MDD diagnostic for multi-day-hold overlapping strategies: entry-day-aggregated curve overstates MDD by 3-4× because it ignores diversification across concurrent positions. Apply this to any future strategy with HOLD ≥ 10 days.

-9. **Hurst-regime classifier is asymmetric: useful for TSMOM, dead for MR/fade (2026-05-23).** `regime_hurst_diagnostic` 8-instrument D1 study: TSMOM Δ Sharpe in H>0.55 vs H<0.45 regime passes pre-commit (6/8 full, 3/5 post-2023 eligible); MR Δ FAILS (4/8 full, **0/5 post-2023**). The MR-side null-collapse is not a Hurst failure — it's the same post-2022 0DTE-amplification taking down MR independent of regime label (lesson #43). Operational implication: future fade/MR rescue proposals via "add a Hurst gate" are pre-tombstoned; future TSMOM-family proposals (tsmom / btc_trend / gold_trend) can legitimately consider a Hurst entry filter (next experiment: `tsmom_hurst_gated`).

-8. **Lunch-fade mechanism is INDEX-CASH-vs-FUTURES-BASIS-ARB specific, NOT basket-generalizable (2026-05-22).** single_stock_lunch_fade REJECT decisive: zero of 24 names positive, basket Sh -1.06 (cost=4bp), holdout -1.26, walk-forward 3/3 OOS negative, dir-gap -0.53 (sign-flipped vs NDX +1.87). Sharpens #27 — future "lunch fade on X" proposals require X to have a liquid cash-vs-futures basis-arb counterpart compressing during 11:30-13:30 ET local. FDAX/cash-DAX and FESX/cash-EUSTX50 are candidate next-targets. Single names, FX, niche commodities are mechanism-empty.

-7. **Mag7 single-stock earnings mechanism FLIPS SIGN at 2022/2023 boundary — direction is regime-conditional, not directional (2026-05-22).** earnings_continuation_mag7 REJECT directly tests lesson #43 pre-commit rule: full-sample fade Sh = continuation Sh = -0.18 (dir-gap -0.02), but fade holdout -1.67 vs continuation holdout +0.78 (Δ +2.45). 0DTE-ramp 2022→2024 is the inflection. earnings_fade_nonmag7 also REJECT — passes Phase 2 (Sh +0.57 / dir-gap +1.63 / both regimes positive) but FAILS walk-forward by 0.03 Sharpe (mean OOS +0.27 vs +0.30 floor); OOS Sharpe decays monotonically (+0.47 → +0.27 → +0.06) showing same 0DTE arb is bleeding non-Mag7 over time.

-6. **Single-stock earnings-fade survives on lower-0DTE-OI large-caps but is arbed on Mag7 (2026-05-22).** earnings_fade REJECT on 24-name universe (full Sh +0.37, holdout −0.22) but with dir-gap +1.35 — mechanism real, sign correct, regime-decay REJECT. Holdout sub-universe split: Mag7 Sh −1.67 / non-Mag7 Sh +0.67 (Δ +2.34). Same dealer-short-gamma flow as opex_pin_fade (#-5) but at single-stock event level. Pre-commit 0DTE-OI as universe-selection variable for any future single-stock intraday-fade thesis; pivot to `earnings_fade_nonmag7` requires fresh pre-committed kill criteria + walk-forward, NOT within-experiment refit.

-5. **Monthly-OPEX pin-fade is dead on US-index M5 post-0DTE (2026-05-22).** opex_pin_fade REJECT both NDX and SPX: dir-gap −0.48/−1.33 (INVERTED), holdout worst regime on both, calendar lock anti-load-bearing. Fourth independent US-index intraday MR sign-inversion. Pre-commit *continuation* direction for any new "last-2h-of-Friday" mechanism; 0DTE structural-short-dealer-gamma flips the sign.

-4. **Sentiment intuition mirror-inverts on opening-impulse strategies (2026-05-21).** orb_dax_sentiment REJECT: pre-committed "risk-on = better breakouts" falsified; Q5 risk-on is only losing bucket (-0.0026% avg). Mirror direction has Sh +0.10 lift but null-gap only +0.10 (half of +0.20 threshold) and 2021-2022 breaks under hypothesized filter. Generic rule: discretionary "trade in calm conditions" intuition is wrong-signed on opening-impulse strategies — pre-commit the mirror form.

-3. **Asian-session-handoff family is NOT auto-transferable across 24/7 instruments (2026-05-16).** XAU W4 +1.23 (physical/sovereign — ACTIVATING) / BTC W4 +0.64 (spot-ETF — PARTIAL decay) / WTI W4 -0.58 (overnight oil — REVERSED). Pre-commit driver type: structural-physical → activation; professional-electronic → decay.

-2. **BTC deploy-discipline: pre-commit W4 as binding constraint.** Pre-2022-only edges are not deployable, period. Tight enough that W2-only-driven full-sample pass cannot survive.

-1. **BTC institutionalization driver acts in MIRROR IMAGE across mechanism families.** Same maturation DEGRADES slow-TSMOM (btc_trend) and ACTIVATES weekend-DOW (btc_weekend). Pre-commit which side the mechanism lives.

0. **Walk-forward Phase 6 catches parabola-V vulnerabilities single-split misses.** For TSMOM-family: walk-forward replaces single-split before deploy.

1. **US/EU index intraday "fade overshoot" theses keep sign-inverting.** 11:30-13:30 ET lunch fade is the ONLY exception. Don't propose generic "fade deviation" without explicit vacuum mechanism.

2. **Holdout (2023-26) regime as 0DTE-amplification proxy.** US-index intraday MR: if 2023-26 is >0.5 Sh below 2019-20, 0DTE killed it. Lunch-fade is the only one INTENSIFIED post-2022.

3. **CFD overnight/gap theses must be validated on real futures BEFORE Phase 2 refinement.** DAX overnight +0.80 → FDAX -0.34.

4. **Microstructure prerequisite for "public-info intraday drift"**: (a) public publication during continuous trading AND (b) tradeable basket concentrated on one venue.

5. **Gap-direction effect is venue-specific.** DAX gaps continue (Xetra). NDX gaps fade (NYSE/Nasdaq). Never port across venues without re-testing.

6. **Cost-zero Sharpe as "no edge" vs "edge eaten by friction" diagnostic.** Cost-zero ≈ 0 → no signal. Cost-zero >> 0 with linear collapse → real edge eaten by spread.

7. **Generic intraday triggers on NDX M5 don't survive friction.** Time-of-day-structural triggers can. Require specific microstructure mechanism.

8. **Research-to-live Sharpe haircut is CONFOUND-SPECIFIC, not a generic multiplier (rewritten 2026-05-22).** Original framing ("0.30-0.60 absolute haircut") was a one-data-point overgeneralization from `xs_momentum` (QC port 0.92 → 0.35). That 0.57 gap had three separable sources — universe-swap (Yahoo ETF → MT5 CFD), cost-model differential, QC's risk-free-subtracted Sharpe formula (lesson #21). **None of those confounds apply to the current 4-strategy book** (all researched on actual Eightcap CFD data, conservative cost models, raw Sharpe both sides). **Expected haircut for current book: 10-25% relative, under 0.20 absolute** — NOT 0.30-0.60. Per lesson #5 rewrite, propagate the new framing rather than blanket-applying the old number. Mechanism decay (lessons #6, #28) and sample-size variance remain real haircut sources, but are mechanism-specific and direction-known, not a generic prior.

---

## UPDATE PROTOCOL

On experiment close:
1. Write verdict + numbers into `experiments/<name>/<name>.md` (truth lives there).
2. Add a 4-line entry here (active) or one row in [STATE_GRAVEYARD.md](STATE_GRAVEYARD.md) (REJECT). Link the name to the thesis doc.
3. Cross-experiment pattern → add lesson to [RESEARCH_NOTES.md](RESEARCH_NOTES.md) + 1-line summary to patterns section above.
4. Memory: only for cross-experiment patterns + user preferences + conventions. Not per-experiment status.
