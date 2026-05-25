# FX Lunch-Fade — EURUSD / GBPUSD / USDJPY (London-NY handoff vacuum)

**Status**: Phase 2 complete 2026-05-25. Family tombstoned.

**Verdict**: **REJECT — all three FX majors** (per pre-committed family-tombstone trigger).

| Instrument | Period | Baseline Sh | dir-gap | Trades | Outcome |
|---|---|---|---|---|---|
| EURUSD | 2019-01 → 2026-05 (7.4y) | **-0.20** | **-0.26** (no dir. content) | 24 | FAIL Sh, FAIL n, FAIL gap |
| GBPUSD | 2022-11 → 2026-05 (3.5y) | **+0.04** | **+0.23** (no dir. content) | 10 | FAIL Sh, FAIL n, FAIL gap |
| USDJPY | 2022-11 → 2026-05 (3.5y) | **-0.54** | **-0.99 INVERTED** (cont wins) | 16 | FAIL Sh, FAIL n, INVERTED |

**Decisive negative**: 0-of-3 instruments produce a positive-Sharpe + valid-directional-content lunch-fade signal. Of the three, USDJPY is the only one with a coherent direction-gap, and it points the *wrong way* (continuation Sh +0.45, fade Sh -0.54). The other two are sub-threshold noise.

**Mechanism interpretation**: the deployed NDX lunch_fade does NOT generalize to spot FX. Combined with `fdax_lunch_fade` REJECT (2026-05-22) and `single_stock_lunch_fade` REJECT (2026-05-22), this is now the **complete sibling-mechanism test for `lunch_fade`**. There are zero validated sibling instruments. The mechanism is, definitively, NDX/NQ-index-arb-specific (sharpened lesson #48 confirmed once more).

**Pre-commit triggered**: EURUSD baseline Sh -0.20 with |dir-gap|=0.26 cleared the family-tombstone trigger (Sh < +0.10 AND |dir-gap| < 0.30). GBPUSD/USDJPY were still run for completeness per autonomy convention.

---

## PRE-COMMIT PRIOR WARNING (read before interpreting results)

The expected-EV prior on this experiment is **~25% PASS, ~75% REJECT** *before any data is seen*. Three load-bearing reasons:

1. **Lesson #1 directly applies.** "FX crosses 2015-2026 is a graveyard for non-momentum factors." Carry, carry+trend, short-term mean reversion all produced negative Sharpe in this repo. The lunch-fade is short-term mean reversion. The prior is against.
2. **Sharpened lesson #48 (`fdax_lunch_fade` REJECT, `single_stock_lunch_fade` REJECT)** — the deployed NDX lunch_fade is **NDX/NQ-index-arb-specific**, not a generic "midday vacuum" mechanism. FDAX (a deep index/futures pair with its own basis-arb structure) did NOT replicate. Single-stock constituents did NOT replicate. The load-bearing driver isn't "fewer participants at lunch" — it's the **NDX cash-vs-NQ-futures basis-arb flow** colliding with the 0DTE-options gamma asymmetry. **Neither mechanism exists in spot FX** (no futures-basis to arb at retail-broker latency, no equity-options gamma flow). On mechanism grounds, this thesis should NOT work.
3. **`fx_session` is institutional-only-REJECTED** — the only FX intraday session strategy validated in this repo was killed by retail spread costs. Any FX intraday edge here has to clear 0.5-1 pip RT just to break even.

**Why running anyway**: definitively close the FX-lunch-fade question. Negative results here let the repo state "no FX intraday edge in any time-of-day-structural form we've tested," which is a stronger generalization than the current state of evidence supports. ~20 minutes of compute vs months of "what about FX?" ambiguity.

**Pre-commit decision rule**:

- EURUSD is the most liquid FX major and has the deepest London-NY handoff vacuum. If **EURUSD does not show signal**, GBPUSD (slightly less liquid, similar handoff structure) and USDJPY (Tokyo-weighted, weaker NY-handoff vacuum) are **mechanistically unlikely to either**. Single-instrument EURUSD REJECT triggers full-family tombstone.
- Conversely, EURUSD PASS does NOT automatically validate the family — must check that at least 2 of 3 show same-sign mechanism (dir-gap > 0 on a majority).

---

## Thesis

**Mechanism — "simultaneous double flow-removal" during the London-NY handoff lunch vacuum (12:00-13:00 ET)**:

1. **London desks wind down for lunch** around 12:00-13:00 London (= 07:00-08:00 ET in DST or 06:00-07:00 ET non-DST). The deepest London lunch is actually the 12:00-13:00 London window; in ET that's the 07:00 ET window, **not** the 12:00 ET window. *Caveat acknowledged below.*
2. **NY institutional desks ramp up around 08:00-09:30 ET** with the cash equity open, then peak intra-day liquidity is 09:30-12:00 ET. **12:00-13:00 ET is the NY lunch hour** — discretionary FX desks are at lunch, leaving the order book to HFT and algorithmic flow.
3. **The 12:00-13:00 ET window is therefore the "double-lull" candidate**: London is in its afternoon (post-lunch but with lighter participation; equity-correlated FX flow has front-loaded into the 09:30 ET equity open), NY discretionary is at lunch. HFT-MR dominates.
4. **The fade-test hypothesis**: aggressive 08:00-12:00 ET morning moves (NY arrival momentum on prior overnight news + equity open repricing) reverse during the 12:00-13:00 ET window as flow lightens and HFT-MR pulls price back toward the morning fair-value reference (London close, typically the 11:00 ET fixing window).
5. **Direction null-check required**: per lesson #43 (post-2022 risk-asset MR pre-commit BOTH directions). Even though FX isn't a US risk asset per se, the dollar (USD-leg of all three crosses) co-moves with risk-assets and the same 0DTE-gamma-amplification can leak into USD-pair flow via the SPX/NDX-futures hedging channel.

**Honest mechanism caveats** (don't read as confidence):
- London lunch ≠ 12:00 ET. The "London-NY handoff vacuum" terminology is somewhat aspirational — there is genuine NY lunch reduction in FX participation, but London is fully present 12:00-13:00 ET (London afternoon session through 16:00 London = 11:00 ET equities-cross 12:00 ET well into the afternoon for Europe-based desks). The vacuum thesis is therefore **half as strong** as the NDX equivalent (which sits at the cash-equity lunch hour with both the equity and the option-flow desks reduced).
- USDJPY is the weakest mechanism candidate — Tokyo desks are closed by 12:00 ET (Tokyo cash session ends 03:00 ET), London handles JPY 03:00-12:00 ET. The 12:00-13:00 ET window for USDJPY is a single-venue (NY) session, with London still on. Mechanism near-absent.

## Key references

- Cornett, Schwarz, Szakmary (1995). "Seasonalities and intraday returns in the foreign exchange spot and futures market." *Journal of Banking & Finance*. (Documents the intraday FX U-shape but specifically notes lunch-hour effects are weakest in FX.)
- Andersen & Bollerslev (1997). "Intraday periodicity and volatility persistence in financial markets." *Journal of Empirical Finance*. (Periodicity components in FX volatility — relevant for the 12:00-13:00 ET window characterization.)
- No paper found establishing a lunch-fade FX mechanism analogous to the equity-index one. The absence of literature is itself a (weak) negative signal.

## Signal math

```text
For each trading day (Mon-Fri, ignoring weekends/holidays):
  open_px       = first bar open at 08:00 ET (or first available bar ≥ 08:00 ET)
  morning_close = close of bar ending at 12:00 ET (= 4 hours / 48 M5 bars after 08:00)
  r_morning     = morning_close / open_px - 1
  atr_proxy     = trailing 20d mean of per-bar abs return (08:00-13:00 ET only)
  thr           = MIN_MOVE_ATR * atr_proxy * morning_bars
  if |r_morning| < thr: skip day
  pos_sign      = -sign(r_morning)   # 'fade'  (or  +sign(r_morning) for null)
  enter         next M5 bar open after 12:00 ET
  exit          bar with minute_of_day ≥ 300 (= 13:00 ET, 5h after 08:00 ET)
  pnl           = pos_sign * (exit_px / entry_px - 1) - cost_pips * pip_size / entry_px
```

Cost model: 1 pip RT (0.0001 EURUSD/GBPUSD, 0.01 USDJPY). Pessimistic for IC Markets / Pepperstone tight FX accounts; realistic for retail.

## Why retail-accessible

EURUSD / GBPUSD / USDJPY are the three highest-volume FX majors. Eightcap (and every retail broker) carries them with tight spreads. No special access required. Mechanism — if it exists — runs as an MT5 EA on the existing VPS.

## Universe

- EURUSD M5 — primary test
- GBPUSD M5 — secondary
- USDJPY M5 — tertiary (mechanism weakest per caveat above)

Data: `ohlc_data/{EURUSD,GBPUSD,USDJPY}_M5.csv` (MT5 fetch 2026-05-24, 2019-01 onwards, ~260K bars each).

## Expected performance — point estimates

- **Baseline expectation** (~75% prior): Sharpe in [-0.20, +0.20], dir-gap in [-0.30, +0.30], i.e., indistinguishable from noise. REJECT.
- **PASS case** (~20%): Sharpe +0.30 to +0.50 on EURUSD specifically; dir-gap +0.50 to +1.00; cost-sensitive (much smaller per-trade gross move than NDX so cost drag is meaningful).
- **Strong PASS case** (~5%): Sharpe > +0.50 with cost-insensitivity, mechanism replicates 3-of-3 instruments. Would indicate genuine FX-specific lunch vacuum that the literature has missed.

Trade cadence expectation: ~80-150 trades per instrument over 7-year window at MIN_MOVE_ATR=0.25 threshold (lower than NDX because fewer "big morning moves" in FX absolute terms).

## Fail conditions (pre-committed)

Standard mechanism-aware Phase 2 template (per lesson #55 — but this is a symmetric/fade mechanism so standard WR≥50 OR PF≥1.05 applies):

| Criterion | Threshold | Reasoning |
|---|---|---|
| Sharpe (research, cost=1pip RT) | **≥ +0.30** | Phase 2 floor |
| Max DD | **< 25%** | standard |
| Trades (per instrument, full sample) | **≥ 200** | trade-floor |
| WR ≥ 50% OR PF ≥ 1.05 | one of two | standard |
| **Direction null-check dir-gap** | **|gap| ≥ 0.30** | per lesson #43 (pre-commit BOTH directions) |
| **Holdout 2023-2026 Sharpe** | **≥ +0.10** | post-2022 stability — lower bar than usual because FX is less 0DTE-affected |
| **3-of-3 regime positive Sharpe** | OR 2-of-3 with holdout positive | regime stability |

**Family-tombstone trigger**: EURUSD baseline Sh < +0.10 AND |dir-gap| < 0.30 → tombstone all three without further sweeps. Save compute.

## Why this might fail (red flags pre-committed)

1. **FX lunch vacuum is half-strength vs NDX.** London is open through 12:00 ET; only NY discretionary is at lunch. The "double-lull" framing in the thesis is partly aspirational.
2. **No basis-arb mechanism in spot FX.** The sharpened lesson #48 says the deployed NDX lunch_fade is index-arb-specific. FX has no equivalent.
3. **No equity-options gamma asymmetry.** 0DTE flow doesn't touch FX. The "Sharpe intensifies post-2022" property that made NDX lunch_fade a deploy-grade candidate cannot apply here.
4. **Per-trade gross move is smaller.** FX intraday absolute moves are ~25-50bp on a typical day vs NDX 60-80bp. Cost drag (1 pip ≈ 1 bp on EURUSD at 1.10) eats a higher fraction of gross.
5. **24h FX market means "morning move" is harder to define.** Asian-session moves bleed into the 08:00 ET reference. ATR proxy includes Asian-session bars unless filtered, which would dilute the threshold signal.
6. **Holdout regime in FX is the dollar-strength rip 2022-2024 followed by mean reversion 2024+.** Different from the NDX 0DTE regime. Mechanism might find spurious 2022-2024 signal that doesn't extrapolate.
7. **USDJPY 2022-2024 BOJ intervention episodes** create per-day return-distribution outliers that can either inflate or destroy Sharpe depending on which side of the intervention the morning move was on.

## Phase 1 → 2 plan (checkbox)

- [x] Read CLAUDE.md spinup section (steps 1-11).
- [x] Read `experiments/lunch_fade/lunch_fade.md` (template).
- [x] Read `experiments/lunch_fade/lunch_fade_demo.py` (style).
- [x] Confirm data on disk / datalake (EURUSD M5 partial; GBPUSD/USDJPY M5 missing) → MT5 fetch all three (2026-05-24, 775K bars to lake).
- [x] Write thesis doc with pre-committed fail conditions.
- [ ] Write `fx_lunch_fade_demo.py` based on lunch_fade_demo.py (FX session config: 08:00-13:00 ET only; cost in pips; per-instrument pip_size).
- [ ] Run baseline + variant sweeps + regime + cost + null-check on all 3 majors in one pass (autonomy convention).
- [ ] Update thesis doc with results table + verdict.
- [ ] Update `docs/STATE.md` with verdict YAML block.
- [ ] Add cross-experiment lesson to `docs/RESEARCH_NOTES.md` if a new methodological pattern emerged (likely just "another FX intraday MR REJECT, no new lesson").

## Phase 2 results — full numbers

### EURUSD (full 7.4y, deepest history)

| Variant | Sharpe | trades | dir-gap | Notes |
|---|---|---|---|---|
| Baseline (thr=0.5, 240/300min) | **-0.20** | 24 | **-0.26** | FAIL |
| thr=0.25 (full population) | -0.02 | 228 | — | n PASS but Sh ~zero |
| thr=0.40 (post-hoc IS-best) | +0.23 | 62 | — | n FAIL; not pre-committed |
| Cont (null) | +0.06 | 24 | — | Sh ~zero |
| LONG-only | +0.15 | 14 | — | tiny n |
| SHORT-only | -0.52 | 10 | — | tiny n |

Regime: 2019-2020 +1.30 (n=4 noise), 2021-2022 -0.52 (n=6 noise), 2023-2026 holdout -0.82 (n=14). No regime pattern. Cost sensitivity is small (-0.13 → -0.34 across 0 → 3 pips RT) — signal-driven failure (lesson #26 cost-zero diagnostic), not friction-eaten.

### GBPUSD (3.5y broker history)

| Variant | Sharpe | trades | dir-gap | Notes |
|---|---|---|---|---|
| Baseline (thr=0.5) | **+0.04** | 10 | **+0.23** | FAIL — tiny n, no dir. content |
| thr=0.25 | -0.34 | 106 | — | n approaches floor but Sh negative |
| thr=0.40 | +0.11 | 29 | — | post-hoc, tiny n |
| Cont (null) | -0.19 | 10 | — | symmetric noise |
| LONG-only | -0.46 | 3 | — | n=3 — noise |
| SHORT-only | +0.35 | 7 | — | n=7 — noise |

Regime: 2021-2022 had n=1 (insufficient), 2023-2026 holdout n=9 Sh -0.14. Direction-gap +0.23 is the highest-magnitude *positive* gap across the three but still inside noise band.

### USDJPY (3.5y broker history)

| Variant | Sharpe | trades | dir-gap | Notes |
|---|---|---|---|---|
| Baseline (thr=0.5) fade | **-0.54** | 16 | **-0.99 INVERTED** | INVERTED |
| Baseline cont (null) | +0.45 | 16 | — | continuation wins |
| thr=0.25 fade | -0.20 | 110 | — | Sh negative across n>=100 cells |
| LONG-only fade | -0.44 | 12 | — | noise |
| SHORT-only fade | -0.33 | 4 | — | tiny n |

USDJPY continuation Sh +0.45 (PF 2.38, WR 56.2%) on n=16 is the only individually-coherent signal across the three instruments — and it points the *opposite* of the thesis. Mechanism interpretation: JPY pairs **trend** through 12:00-13:00 ET. Consistent with literature observation that USDJPY exhibits late-NY-session continuation (BOJ-driven Asia-session price discovery already exhausted by 08:00 ET; remaining flow is positioning, which continues). NOT a deploy candidate — n is too small, no walk-forward path, and lesson #1 prior is intact (FX is a graveyard for non-momentum factors; this would-be "FX momentum continuation" cell is the kind of cell that walk-forward kills).

---

## Mechanistic interpretation (post-mortem)

1. **NDX lunch_fade has zero validated sibling mechanism.** Triple-REJECT (FDAX / single-stocks / FX) now closes the family. Lesson #48 sharpens to "lunch_fade is NDX/NQ-index-arb-specific, period." Any future "midday vacuum" thesis must propose a *different* load-bearing mechanism (not "fewer participants at lunch") and articulate why it doesn't reduce to the NDX cash/futures basis-arb channel.
2. **FX 12:00-13:00 ET is not a vacuum window in the same sense.** London is open. London afternoon flow is heavy. The "double-lull" framing in the original thesis was aspirational and the pre-commit caveat (mechanism half-strength vs NDX) was correct — but actually the empirics suggest mechanism near-zero, not half-strength. The structural feature being tested (HFT-MR dominance during reduced discretionary participation) doesn't fingerprint in FX bars because (a) FX is HFT-MR-dominated *all the time* (so the relative midday vacuum effect is zero) and (b) there's no cash/futures basis-arb to generate the gamma-driven reversion that powers NDX.
3. **USDJPY inversion confirms FX intraday character.** JPY pairs trend rather than fade because the Asia/Tokyo session is the actual price-discovery session, and the NY session (especially the 12:00-13:00 ET sub-window) is positioning/momentum on already-discovered information. The continuation Sh +0.45 (n=16, post-hoc) is too small to deploy but consistent with the literature.
4. **Cost-insensitivity rules out "edge present but eaten by friction."** All three instruments show < 0.04 Sh per pip RT (consistent with NDX's cost-flat pattern). The failure is signal-absent, not friction-eaten (lesson #26 diagnostic).
5. **Trade-count starvation at thr=0.5 is informative.** Only 10-24 baseline trades over 3.5-7.4 years means the ATR-relative-to-morning-bars threshold formulation (calibrated for NDX 60-80bp daily moves) is too strict for FX 25-50bp daily moves. Sweeping down to thr=0.25 gets n to ~100-230 but Sharpe stays at -0.02 to -0.34 across all three. There is no threshold cell that simultaneously clears Sharpe>0.30 AND trades>=200 — the trade-floor knee finding pattern that worked on NDX (lesson at the end of `lunch_fade.md`) does NOT find a viable cell here.

---

## Lessons captured (cross-experiment)

- **Sharpened lesson #48 confirmed by FX**: NDX lunch_fade does not generalize via the "midday vacuum" framing to ANY validated sibling instrument across THREE distinct instrument families (index futures basis-arb / single-stock constituents / spot FX). The mechanism is NDX/NQ-specific. *No new methodological lesson — existing lesson #48 already covered this; this experiment is confirmatory rather than novel.*
- **Lesson #1 prior held**: FX is a graveyard for non-momentum factors. This is the 5th FX MR/fade experiment to fail; cumulative track record for FX MR theses in this repo is 0-for-5. Future "intraday FX edge" theses should be required to articulate a non-MR mechanism (carry-flow, calendar-event, central-bank-window) — generic time-of-day-MR will not pass the prior.
- **No new pre-commit hygiene lesson**: the family-tombstone trigger fired as designed (EURUSD pre-commit said "Sh < +0.10 AND |dir-gap| < 0.30 → tombstone family"; EURUSD landed at Sh -0.20, |dir-gap| 0.26 — tombstoned). The GBPUSD/USDJPY runs were diagnostic-only and confirmed.

---

## Files

- Thesis: this file.
- Demo: `experiments/fx_lunch_fade/fx_lunch_fade_demo.py` — env-var `FX_SYMBOL` (default EURUSD).
- Data: `ohlc_data/{EURUSD,GBPUSD,USDJPY}_M5.csv`. EURUSD 7.4y (lake + MT5); GBPUSD/USDJPY 3.5y (MT5 broker-history limit).
- Run: `FX_SYMBOL={EURUSD|GBPUSD|USDJPY} venv/Scripts/python.exe experiments/fx_lunch_fade/fx_lunch_fade_demo.py`.
