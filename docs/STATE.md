# Project State

**Where are we now, and what's been done.** Index of every experiment with verdict + headline numbers — **truth is in the linked thesis docs**, keep entries terse.
Lessons → [RESEARCH_NOTES.md](RESEARCH_NOTES.md). Rejects → [STATE_GRAVEYARD.md](STATE_GRAVEYARD.md). Live-book posture → [BOOK_PLAN.md](BOOK_PLAN.md).

- **Live** = MT5 VPS only (private). QC retired 2026-05.
- **Tradeability**: datalake M5 ⇒ broker-confirmed; D1-only ⇒ verify via `scripts/mt5_fetch.py --list-symbols`.
- **TZ-FIX (2026-05-28)**: pre-fix "research" Sharpes were on 3h-shifted bars (lesson #80). Deployed strategies' validated numbers are in their thesis-doc TZ-FIX banners; live EAs are UTC-explicit or reconfigured to the shifted session.

---

## Snapshot (2026-05-29)

| Status | Count | Names |
|---|---|---|
| Live (MT5 VPS) | **7** | one book, per-strategy detail private (`experiments/_live/`, `live_tracking/`); posture → [BOOK_PLAN.md](BOOK_PLAN.md) |
| Validated, blocked at broker | 3 | `treasury_trend` (no bonds), `softs_ensemble` (Eightcap subset fails), `pead_midcap` (CFD-swap-cost) |
| Keep-for-reference | 3 | `tsmom`, `btc_trend`, `btc_intraday` |
| Portfolio overlay — PASS | 1 | `portfolio_risk_parity` (quarterly sizing review) |
| Diagnostic (no deploy path) | 2 | `regime_hurst_diagnostic` (MARGINAL); `regime_classifier_diagnostic` (queued ~2027) |
| Institutional-only | 3 | `fx_session`, `xag_session`, `xpt_session` |
| Rejected | 82 | → [STATE_GRAVEYARD.md](STATE_GRAVEYARD.md) |
| **Total** | **101** | |

---

## LIVE BOOK

**7 strategies live on MT5 VPS** as of 2026-06-01. Per-strategy thesis, mechanism, instrument, params, sizing, and live tracking are deliberately **not** in this committed doc, they live in `experiments/_live/<name>/`, `live_tracking/<name>.md`, and `deploy/` (all gitignored). **The book is the unit that matters here, not the legs.** Book-level posture, sizing tiers, validation gates, and expected results → [BOOK_PLAN.md](BOOK_PLAN.md).

---

## VALIDATED — BROKER ACCESS REQUIRED

### [treasury_trend](../experiments/treasury_trend/treasury_trend.md) — VALIDATED_NO_DEPLOY
- IEF (Tiingo D1, 24y) | Sh 0.67 / holdout 0.42 / MDD -8.1% | 77 trades (7/yr). MH TSMOM, ~0 corr vs equities. All 7 phases PASS
- **Blocker**: Eightcap has no US Treasury CFDs (confirmed 2026-05-13)

### [softs_ensemble](../experiments/softs_ensemble/softs_ensemble.md) — VALIDATED_NO_DEPLOY
- 6 softs (Yahoo continuous) | Sh 0.85 / holdout 1.44 / MDD -13.3%. EW MH-TSMOM ensemble. Phases 2-7 PASS
- **Blocker**: Eightcap D1 depth too short to validate; and the tradeable + swap-survivable subset (COCOA+COFFEE only — cotton/corn swap-dead ~17%/yr, soybean/cattle not offered) is a one-window-wonder (Sh +0.59, 82% in 2023-26 bull, null-gap +0.24). REJECT for Eightcap 2026-05-29; 6-name research unchanged. Lesson #86

### [pead_midcap](../experiments/pead_midcap/pead_midcap.md) — VALIDATED_BLOCKED_AT_COST (2026-05-24)
- 168-name non-Mag7 universe | per-event PEAD (MIN_SUE=5%, HOLD=20d, 10bp comm): Sh +0.76 / concurrent-MDD -24.8% / 1663 events / dir-gap +1.71 / 3/3 regimes positive. All 4 Phase-2 kill criteria PASS
- **Blocker**: 20-day-hold CFD swap (~110bp RT) eats >50% of gross → live Sh ~0. NOT a research failure (pre-commit omitted CFD swap). Deployable on cash equities (IBKR); short-hold variants don't survive compression. Lesson #59

---

## KEEP-FOR-REFERENCE

### [btc_trend](../experiments/btc_trend/btc_trend.md) — KEEP_FOR_REFERENCE
- BTCUSD D1 | Sh 0.83 / real-OOS -0.32 / walk-fwd mean OOS 0.54. MH TSMOM + ATR pyramid. Failure modes: parabola-V + institutionalization decay. closed 2026-05-13 (lesson #29)

### [tsmom](../experiments/tsmom/tsmom.md) — KEEP_FOR_REFERENCE
- 24-instr long-only | Sh 0.40 / holdout 1.14 / MDD -15.5%. Classical 12-1 TSMOM. Mechanically valid but +0.69 corr with xs_momentum → no diversification value

### [btc_intraday](../experiments/btc_intraday/btc_intraday.md) — MARGINAL
- BTCUSD H1 | Sh 0.72 / W4 0.83 / **W4-26 -2.71 (n=20) FAIL**. Hour-00 UTC drift + z-filter, 2h hold. 3/7 kill PASS. closed 2026-05-16; tombstone-or-revisit on 2026Q2-Q3 OOS

---

## PORTFOLIO OVERLAYS

### `portfolio_risk_parity` — PASS (re-audit 2026-05-29, post-tz-fix 9-comp book incl. global_settlement_short)
- Inv-vol sizing overlay: EQ Sh +0.56 → **RP +0.78** (lift +0.23); MDD -3.39% → -1.66%; **4/4 regimes positive** (RP W1 +0.60 / W2 +0.15 / W3 +1.65 / W4 +1.08). Deploy as **quarterly sizing review** (static inv-vol gives the lift; sparse strategies capped 25%). `global_settlement_short` ~0-corr to all legs → lifted book RP Sh +0.61→+0.78
- Book-yearly w/ per-strategy sizing: total +113.3% / CAGR +24.98% / Sh +2.63 / MDD -3.68% / Calmar +6.78 (since 2023). Methodology + weights private

---

## CROSS-EXPERIMENT PATTERNS

One-line index; full detail in [RESEARCH_NOTES.md](RESEARCH_NOTES.md) and the linked thesis docs.

34. **Forced-flow calendar mechanisms port across jurisdictions by settlement-timing, not clock; event-vs-generic-calendar is the placebo** (`jpn225_sq_open_short`; #87)
33. **A validated multi-instrument ensemble doesn't survive restriction to the broker-tradeable subset** when robustness lived in un-tradeable names (`softs_ensemble` Eightcap cut; #86)
32. **Crypto perp funding-fade is correctly signed but institutionalised to ~0 post-2022** (`crypto_funding_fade`; #85)
31. **Single-instrument retail-CFD TSMOM needs B&H + null-check as Phase-0 gates** — kill criteria hide passive-beta (`gold_trend`; #73)
30. **Structural-flow calendar audit is a productive idea-source** (~1 candidate / 17 cells) (`structural_flow_audit`; #72)
29. **"Institutional-absence" ≠ edge; the fill-flow can sign-invert W2→W3** (`retail_overshoot_fade`)
28. **Capacity-moat is a deploy-prerequisite, not a predictor** (`cfd_wed_rollover_eurusd`)
27. **DXY-mechanical-mirror confirmed across pass- and fail-primary vessels; FX-side event legs pre-tombstoned** (`pre_ecb_drift_eurusd`)
26. **FX has independent pre-CB flow only with no equity-primary AND modal-non-event; direction = carry-MAINTAIN** (`pre_boj_drift`; #54)
25. **Secondary cross-asset vessels are magnitude-shadows of the primary, decay first** (`pre_fomc_drift`)
24. **TF×window is 2-D; wider windows extract only at coarser TF (M-shape)** (`xau_break_retest_h1`)
23. **Intraday-microstructure edge doesn't auto-transfer across sessions on the same instrument** (`xau_ldn_am_fade`)
22. **Scheduled US-macro LONG drift is first-read / mid-month / mid-cycle specific** (`pre_pce_drift`; #62)
21. **Macro-event-drift doesn't port from index-on-US-macro to commodity-on-own-fundamental** (`pre_natgas_eia`; #61)
20. **OPEX-pin family fully tombstoned for US equities** (0DTE leaked to non-Mag7 single stocks) (`opex_pin_singlestock`)
19. **PEAD direction-inversion is Mag7-specific, not market-wide**; concurrent-position curve is the MDD diagnostic for HOLD≥10d (`pead_midcap`)
18. **Hurst regime classifier: useful for TSMOM, dead for MR/fade post-2023** (`regime_hurst_diagnostic`)
17. **Lunch-fade is index-cash-vs-futures-basis-arb specific, not basket-generalizable** (`single_stock_lunch_fade`)
16. **Mag7 earnings mechanism flips sign at 2022/23 (regime-conditional)** (`earnings_continuation_mag7`)
15. **Single-stock earnings-fade survives on low-0DTE-OI large-caps, arbed on Mag7** (`earnings_fade`)
14. **Monthly-OPEX pin-fade dead on US-index M5 post-0DTE** (`opex_pin_fade`)
13. **Sentiment intuition mirror-inverts on opening-impulse strategies** (`orb_dax_sentiment`)
12. **Asian-session-handoff not auto-transferable across 24/7 instruments** (XAU activates / WTI reverses)
11. **BTC: pre-commit W4 as binding; pre-2022-only edges aren't deployable**
10. **BTC institutionalization acts in mirror image across mechanism families** (degrades TSMOM, activates weekend-DOW)
9. **Walk-forward Phase 6 catches parabola-V vulnerabilities single-split misses** (TSMOM-family)
8. **US/EU index intraday "fade overshoot" keeps sign-inverting** — lunch-fade is the only exception
7. **Holdout (2023-26) as 0DTE-amplification proxy** for US-index intraday MR
6. **CFD overnight/gap theses must be validated on real futures first** (DAX +0.80 → FDAX -0.34)
5. **"Public-info intraday drift" needs continuous-trading publication + one-venue basket**
4. **Gap-direction effect is venue-specific** (DAX continues / NDX fades)
3. **Cost-zero Sharpe diagnostic**: ≈0 → no signal; ≫0 w/ linear collapse → edge eaten by spread
2. **Generic intraday triggers on NDX M5 don't survive friction**; time-of-day-structural can
1. **Research-to-live haircut is confound-specific (~10-25% rel. for this book), not a generic multiplier** (#5)

---

## UPDATE PROTOCOL

**On experiment close:**
1. Verdict + numbers into `experiments/<name>/<name>.md` (truth lives there).
2. 4-line entry here (active) or one row in [STATE_GRAVEYARD.md](STATE_GRAVEYARD.md) (REJECT). Graveyard failure-mode column: one sentence (≤120 chars), no bold.
3. Cross-experiment pattern → lesson in [RESEARCH_NOTES.md](RESEARCH_NOTES.md) + 1-line above.
4. Memory: only cross-experiment patterns + user prefs + conventions.

**On graduating to DEPLOYED (paper or real):**
1. Move dir into `experiments/_live/<name>/`; fix `_ROOT`/`sys.path` (+1 `os.path.dirname()`).
2. STATE.md → move entry to DEPLOYED (public-summary, no private params); bump Live count.
3. README header counter + status paragraph + aggregate metrics (after step 6).
4. `book_review/book_yearly.py` — add `run_<name>()`, wire in, re-run tearsheet.
5. `_live/portfolio_risk_parity/portfolio_risk_parity_demo.py` — add `run_<name>()` + STRATS row; re-run audit → feeds BOOK_PLAN §2.1.
6. BOOK_PLAN §1 row, §4 Gate-0 count, §2.1 numbers (from step 5), §2.2 live-target if moved.
7. `live_tracking/<name>.md` — kill-trigger spec, starting balance, first-fire date.
8. Private deploy: `deploy/mq5/<name>.mq5` (or `.../Services/`), magic registration, hedging + margin check.
9. Memory only if the deploy surfaces a new methodological rule.

Cadence: the research-side audit (step 5) re-runs every graduation; the live-side sizing review stays quarterly per BOOK_PLAN §5.
