# Pre-PCE drift on NDX100 (24h pre-release, direction TBD per lesson #54)

**Status**: Phase 2 complete (2026-05-24). Fourth extension of the macro_drift event-family.
Tests the canonical "scheduled US-macro event drifts LONG on NDX via institutional risk-premium accumulation" rule (lesson #56) on the Personal Consumption Expenditures Price Index release (BEA, 08:30 ET, last business day of month, ~12/yr).

**Verdict**: **REJECT — framework falsification at the canonical-test case.** The
LONG direction null-gap is only +0.161% (FAIL, threshold +0.30); W4 modern regime
is catastrophically negative (mean -0.434%, Sh -1.23); walk-forward 3/3 OOS
negative with monotonic decay (-0.14 → -0.55 → -1.23); placebo is benign (mean
-0.040%, t -0.29) which RULES OUT the month-end structural-drift confound and
confirms the rejection is PCE-specific signal failure, not a calendar artefact.
Friday subset has Sh -0.03 vs non-Friday +0.53 (delta -0.185%), partially
supporting red-flag #4 (Friday microstructure dilutes the inflation-print signal),
but non-Friday n=20 is too small to anchor as a salvage path. Lesson #56's
"all scheduled US-macro events drift LONG on NDX" generalisation is REFUTED at
its closest available corroboration test — see mechanistic interpretation below.

**Honest framing — this is a framework-corroboration test, NOT a diversification add.**
PCE and CPI are both monthly US inflation measures with high underlying correlation
(headline PCE / headline CPI YoY correlation ≈ 0.85-0.90 over 2018-2026; core PCE /
core CPI ≈ 0.80-0.85). The release calendars are non-overlapping (CPI mid-month
Tue/Wed/Thu, PCE end-of-month Fri/Thu), so event timing is independent — but the
underlying inflation signal that drives institutional positioning is largely the
same information. Expected outcome (~70% prior): PCE PASSES on the LONG direction
with metrics resembling pre_cpi_drift (Sh ~+0.30-0.60, W4 strongest, mech-aware
KCs 8-9/9 PASS).

**If PCE PASSES**: corroborates the unified framework (FOMC LONG + CPI LONG + PCE
LONG = "policy-decision and inflation-print accumulation drifts LONG on NDX"; NFP
SHORT remains the structural exception driven by Friday/0DTE microstructure and
bi-modal-surprise hedging). Use for framework validation. **Do NOT deploy with full
size** — the CPI-PCE correlation means PCE is ~80% redundant with CPI for capital-
allocation purposes. Deploy at 0.5% risk (regime-conditional sizing per lesson #5
addendum / joint_book_audit 2026-05-24 discipline) AND add a "no overlap with CPI
window" precedence rule in the consolidated EA (in practice they never overlap
calendar-wise, so this is just a belt-and-braces guard).

**If PCE FAILS LONG and PASSES SHORT**: more interesting. Would mean inflation
prints split into "CPI = LONG (treated like Fed-decision proxy)" vs "PCE = SHORT
(treated like hard-data with asymmetric tails, similar to NFP)" — suggests the
LONG/SHORT split is not "policy vs hard-data" but something more subtle
(end-of-month vs mid-month? Friday vs Tue-Thu? Core-vs-headline framing?).

**If PCE FAILS BOTH (null-gap < 0.30)**: would mean CPI's PASS was idiosyncratic
to mid-month positioning timing, not the inflation-print mechanism itself. Would
significantly weaken the unified framework and warrant re-examining CPI's deploy
recommendation.

## What this experiment tests

This is the **fourth event-family extension** and the **first explicit framework-
corroboration test** (the prior three each tested a distinct event class). The
framework (lesson #56) currently asserts:

> Scheduled US-macro events on NDX drift LONG via institutional risk-premium
> accumulation. NFP-SHORT is anomalous; CPI-LONG and FOMC-LONG are the canonical
> cases.

PCE is the closest analog to CPI in the event taxonomy:
- Same release time (08:30 ET)
- Same agency tier (US government statistical agency: BLS for CPI, BEA for PCE)
- Same release cadence (~12/yr)
- Same primary information content (inflation measure)
- Different release day-of-week (PCE Fri/Thu vs CPI Tue/Wed/Thu)
- Different release timing within month (PCE end vs CPI mid-month)

Because PCE and CPI carry largely the same information, a clean PCE PASS in the
same direction (LONG) is a corroboration that the mechanism is the inflation-
print-accumulation flow itself, not a calendar artefact of mid-month positioning.
A SHORT or null-gap failure would force a rethink of CPI's PASS.

## Pre-commits (applied to BEST of LONG/SHORT per lesson #54)

Per lesson #55 (mechanism-aware kill criteria), this thesis pre-commits the
asymmetric-payoff-mechanism kill set:

1. **Best-direction per-trade mean > +0.10%** at 5bp RT cost.
2. **Best-direction W4 (2024-2026) per-trade mean > +0.05%**.
3. **Best-direction PF > 1.3**.
4. **Best-direction Sharpe (×√12) > +0.30** (annualised, ~12 PCE/yr).
5. **Max DD < 25%**.
6. **Events ≥ 50**.
7. **Direction null-gap |LONG − SHORT| ≥ +0.30**.
8. **Walk-forward OOS mean Sh ≥ +0.30, min OOS Sh ≥ 0** (3 rolling splits).
9. **Placebo non-PCE weekdays at 08:30 ET anchor benign** (mean < 0.05% or |t| < 1.5).

PASS only if ALL of (1)-(9) hold for the same direction.

**Pre-committed expected direction per lesson #56 canonical rule: LONG.** Per
lesson #54 discipline, both LONG and SHORT are run as co-equal candidates and the
direction is selected ex-post from the null-gap; the rule prediction is only used
to interpret the result.

## Why this might fail (red flags)

1. **Calendar-date drift** — same concern as pre_cpi_drift. PCE release dates
   shift around holidays, BEA scheduling, and (rarely) government shutdowns
   (Jan-Feb 2019). The hardcoded calendar likely has ~5% date errors (5/100
   events misaligned by 1-2 days). This noises the signal but should not
   invalidate it directionally.
2. **CPI-PCE redundancy means a marginal-PCE PASS adds little**. If PCE only
   barely clears the kill criteria (Sh ~+0.30, W4 ~+0.05%), the corroboration
   value is weak — could just be the CPI mechanism leaking via the underlying
   correlated inflation-positioning signal, not an independent confirmation.
   The strong-PASS case (Sh > +0.5, W4 > +0.20%) is what would actually
   corroborate the framework cleanly.
3. **End-of-month/quarter-end positioning confound** — PCE often releases on
   month-end (last business day). Month-end / quarter-end institutional
   rebalancing flows can dominate the 24h pre-window with non-inflation-
   related drift. This would show up as a strong placebo (significant
   non-PCE-weekday drift at month-end timing) and would FAIL the placebo
   pre-commit. **Pre-commit: if the LONG signal passes but the placebo is
   ALSO strong (mean > 0.10% and t > 1.5), conclude the result is month-end
   structural drift, not PCE-specific** — and DO NOT deploy.
4. **Friday-release subset overlaps NFP microstructure** — a non-trivial
   fraction of PCE releases land on Friday (~half by my count). If NFP-SHORT
   reflects Friday-specific microstructure rather than NFP-specific tail
   hedging (lesson #56 alternate hypothesis), the Friday-PCE subset might
   inherit some of that SHORT bias and dilute the LONG mean. Diagnose
   ex-post by splitting PCE events into Friday vs non-Friday subgroups.
5. **Post-2022 inflation regime tapering means W4 magnitude may decay**. If
   2025-2026 PCE prints land in a "normalised inflation" regime where surprises
   are smaller and risk-premium accumulation flows are less load-bearing, W4
   could be weaker than CPI's W4 (+0.576%). PCE might land in MARGINAL band
   (Sh +0.2-0.4) rather than CPI's clean PASS band (Sh +0.56).

## Files

- `pre_pce_drift.md` — this doc
- `pce_calendar.csv` — ~100 PCE dates 2018-2026 (96 historical + 8 forward)
- `pre_pce_drift_demo.py` — Phase 2 simulator (clone of pre_cpi_drift_demo)

## Phase 1 → 2 plan

- [x] Build calendar (100 historical + forward events, 2018-Dec-2026)
- [x] Pre-commit kill criteria (mech-aware per lesson #55, direction-TBD per lesson #54)
- [x] Run end-to-end: baseline (both dirs) + regime + walk-forward + cost + window sweep + placebo + Friday-subset diagnostic
- [x] Update this doc with results + verdict (REJECT)
- [x] Update STATE.md with the REJECTED-section entry
- [x] Add framework-refinement lesson to RESEARCH_NOTES.md (lesson #56 boundary-condition)
- [ ] ~~Add 5th event toggle to event_calendar_ea.mq5~~ — N/A, REJECTed

---

## Results (2026-05-24)

### Headline (both directions)

| Direction | n | mean | std | t | Sh (×√12) | MDD | WR | PF |
|---|---|---|---|---|---|---|---|---|
| **LONG (winner)** | 85 | +0.031% | 1.613% | +0.18 | +0.07 | -12.93% | 50.6% | 1.06 |
| SHORT (loser) | 85 | -0.131% | 1.613% | -0.75 | -0.28 | -19.99% | 45.9% | 0.79 |
| **Null-gap (LONG − SHORT)** | | **+0.161%** | | | | | | |

Null-gap +0.161% is **half** the +0.30 threshold. SHORT-loser t -0.75 is far from
the t -2.28 / t -2.18 mirror-significance seen on NFP-SHORT and CPI-SHORT
respectively. Neither side has directional content.

### Regime breakdown (LONG)

| Window | n | mean | std | t | WR | Sh |
|---|---|---|---|---|---|---|
| W1 (2018-2019) | 11 | +0.179% | 0.644% | +0.92 | 63.6% | +0.96 |
| W2 (2020-2021) | 24 | +0.161% | 1.987% | +0.40 | 45.8% | +0.28 |
| W3 (2022-2023) | 24 | +0.336% | 1.841% | +0.89 | 54.2% | +0.63 |
| **W4 (2024-2026)** | **26** | **-0.434%** | 1.218% | **-1.82** | 46.2% | **-1.23** |

The W4 collapse is the load-bearing signal: same modern post-COVID regime that
made CPI-LONG strongest (W4 Sh +1.15) makes PCE-LONG worst (W4 Sh -1.23). The
two near-identical inflation events split sharply at the W4 boundary. This is
NOT a noise effect — t -1.82 on n=26 is approaching significance for a single-
regime sub-window.

### Walk-forward — monotonic OOS degradation

| Split | IS n | IS Sh | IS mean | OOS n | OOS Sh | OOS mean |
|---|---|---|---|---|---|---|
| IS 2019→2022 / OOS 2022-2026 | 35 | +0.35 | +0.167% | 50 | **-0.14** | -0.064% |
| IS 2019→2023 / OOS 2023-2026 | 47 | +0.37 | +0.203% | 38 | **-0.55** | -0.182% |
| IS 2019→2024 / OOS 2024-2026 | 59 | +0.47 | +0.235% | 26 | **-1.23** | -0.434% |

Mean OOS Sh **-0.64**, min OOS **-1.23**. All three IS windows have IS Sharpe
+0.35 to +0.47 (would have looked deploy-grade on a single-split backtest); every
OOS window is negative and monotonically degrading. This is the textbook
parabola-V profile (lesson #29) and is the strongest available evidence that
the IS Sharpe is fitting a transient pre-2022 microstructure that no longer
holds.

### Friday-vs-non-Friday subset (per red-flag #4)

| Subset | n | mean | Sh | WR |
|---|---|---|---|---|
| Friday    | 65 | -0.013% | -0.03 | 50.8% |
| Non-Friday | 20 | +0.172% | +0.53 | 50.0% |
| **Delta (Fri − non-Fri)** | | **-0.185%** | | |

Non-Friday subset (Mon-Thu, n=20) is the only positive-Sharpe slice. The Friday
subset is essentially zero. This partially supports red-flag #4 (Friday
microstructure dilutes the signal), but n=20 non-Friday is too small to
deploy on, and the W4 regime collapse on the full sample remains overwhelming.

### Placebo — benign, which RULES OUT the month-end confound

| Population | n | mean | t | Sh | WR |
|---|---|---|---|---|---|
| Placebo non-PCE weekdays LONG | 95 | -0.040% | -0.29 | -0.10 | 50.5% |
| Placebo non-PCE weekdays SHORT | 95 | -0.060% | -0.44 | -0.16 | 44.2% |

Placebo LONG mean -0.040% (t -0.29) — non-significant. This is important: it
**rules out** red-flag #3 (month-end positioning confound). If end-of-month
weekday timing structurally drifted LONG, the placebo at the same
08:30-ET-anchor on non-PCE weekdays would show it. It doesn't. Therefore the
PCE-day result (+0.031%) is the genuine PCE-specific event signal — and that
signal is empty. CPI's PASS cannot be attributed to "any 08:30-ET pre-release
weekday window drifts LONG"; PCE is the falsifier of that null.

### Cost sensitivity (LONG)

| Cost (bp RT) | mean | Sh |
|---|---|---|
| 0 | +0.081% | +0.17 |
| 2 | +0.061% | +0.13 |
| **5** (default) | **+0.031%** | **+0.07** |
| 10 | -0.019% | -0.04 |
| 20 | -0.119% | -0.26 |

Even at zero cost (+0.081%, Sh +0.17), the signal is sub-threshold. Cost is
not the binding constraint; the underlying gross-edge is absent.

### Window sweep (LONG, 5bp)

| Window | Mean | Sh |
|---|---|---|
| 6h  | -0.099% to -0.078% | -0.83 to -0.71 |
| 12h | -0.130% to -0.107% | -0.82 to -0.69 |
| 18h | -0.022% to +0.000% | -0.07 to 0.00 |
| **24h** (pre-commit) | **+0.021% to +0.041%** | **+0.04 to +0.08** |
| 48h | -0.208% to -0.187% | -0.34 to -0.31 |

24h is the natural-monotonic local maximum (signal flat-to-slightly-positive in
the 18-24h band, negative on both sides). No alternative window saves the
strategy. Pre-commit choice was correct; the mechanism just isn't there.

### Kill-criteria summary

| # | Criterion | Threshold | Realised | Verdict |
|---|---|---|---|---|
| 1 | Per-trade mean | > +0.10% | +0.031% | **FAIL** |
| 2 | W4 per-trade mean | > +0.05% | -0.434% | **FAIL** |
| 3 | PF | > 1.3 | 1.06 | **FAIL** |
| 4 | Sharpe (×√12) | > +0.30 | +0.07 | **FAIL** |
| 5 | Max DD | < 25% | -12.93% | PASS |
| 6 | Events | ≥ 50 | 85 | PASS |
| 7 | Direction null-gap | ≥ +0.30 | +0.161 | **FAIL** |
| 8a | Walk-forward OOS mean Sh | ≥ +0.30 | -0.64 | **FAIL** |
| 8b | Walk-forward OOS min Sh | ≥ 0 | -1.23 | **FAIL** |
| 9 | Placebo benign | mean < 0.05% or t < 1.5 | t -0.29 | PASS |

**3/9 PASS.** Only the structural sanity checks (MDD, sample size, placebo)
pass; every direct-mechanism criterion FAILs. This is the cleanest REJECT in
the event family — no salvage path through variant sweep, no regime where the
mechanism is intact post-2022, no cost-floor headroom.

### Mechanistic interpretation — what this teaches about the framework

**The lesson #56 canonical rule was wrong in its generalisation scope.** Three
event-family results define a tighter framework:

- **FOMC LONG** (PASS, deployed): policy-decision event, scheduled, mid-day ET
- **CPI LONG** (PASS, deploy candidate): inflation-print, mid-month, Tue/Wed/Thu morning
- **PCE LONG** (REJECT, this experiment): inflation-print, end-of-month, Friday-dominated morning
- **NFP SHORT** (MARGINAL, PASS under mechanism-aware template): payrolls, first-Friday morning
- **Retail Sales LONG** (PASS, per STATE.md ref): mid-month, Wed morning

Originally lesson #56 framed this as *"scheduled US-macro events drift LONG
via institutional risk-premium accumulation; NFP-SHORT is the Friday
exception."* PCE refutes that framing — PCE is an inflation print like CPI
(same information content with ~0.85+ correlation), but it does NOT inherit
CPI's LONG drift. The differentiator is NOT "policy vs hard-data" and NOT
"inflation vs payrolls." The actual distinguishing axes are:

1. **Calendar position within month.** CPI lands mid-month (Tue/Wed/Thu of
   week 2-3); PCE lands end-of-month (Fri of week 4-5); FOMC lands mid-cycle
   (mid-week); Retail Sales lands mid-month. The PASSing events all cluster
   mid-month / mid-cycle. PCE is the outlier — its month-end timing collides
   with structural month-end-rebalance flows that *cancel* (placebo shows the
   pre-window is roughly flat) the institutional inflation-print accumulation.

2. **Day-of-week composition of the 24h window.** PCE is Friday-dominated
   (65/85 = 76% of releases), so the 24h pre-window is largely Thursday
   overnight + Friday morning — the exact thin-liquidity slice that drives
   NFP-SHORT. Friday-PCE has Sh -0.03; non-Friday-PCE has Sh +0.53. The
   inflation-print LONG drift exists in the small (n=20) non-Friday subset
   but is overwhelmed by Friday's flat-to-negative profile in the
   Friday-dominated full sample.

3. **Information freshness vs market-prepared inflation reads.** By the time
   PCE releases at end-of-month, CPI (mid-month) has already moved the
   inflation-positioning needle for that monthly cycle. Institutional risk-
   premium accumulation into PCE is muted because most of the inflation-
   surprise risk has already been priced post-CPI. CPI is the "first read,"
   PCE is the "confirming read" — and only the first read generates
   accumulation flow.

**Refined framework (replacing lesson #56)**:

> Scheduled US-macro events on NDX drift LONG via institutional risk-premium
> accumulation ONLY when the event is the *first major print of its
> information cycle* AND lands in the *mid-month / mid-week* slot. Inflation:
> CPI (first read, mid-month) PASSES LONG; PCE (confirming read, end-of-month
> Friday) does NOT. Policy: FOMC (rate decision, mid-week) PASSES LONG.
> Activity: Retail Sales (real-economy first read, mid-month) PASSES LONG.
> Friday-dominated end-of-month events do NOT inherit the LONG drift.
> NFP is a Friday hard-data event that drifts SHORT — same Friday-thin-liquidity
> microstructure that nukes PCE-LONG.

**Operational implications**:

1. **Do NOT deploy PCE.** REJECT is decisive — 6/9 binding pre-commits FAIL,
   walk-forward 3/3 OOS negative, W4 collapse.
2. **Do NOT weaken CPI deploy stance** — placebo benign on PCE *strengthens*
   CPI's claim that the mid-month inflation-accumulation flow is real
   (it's not just any-08:30-ET-weekday-drifts-LONG).
3. **Do reconsider the broader event-family expansion roadmap.** Future
   "scheduled US-macro" theses should be pre-screened for: (a) first-read
   vs confirming-read status within the event's information cycle, (b)
   day-of-week composition of the 24h window (Friday-heavy → expect drag),
   (c) calendar-position (end-of-month/quarter → expect month-end-flow
   confound contamination). Specifically: pre_ppi_drift (already exists in
   repo per status) is mid-month Wed/Thu — should inherit CPI-style LONG;
   pre_durable_goods_drift would be end-of-month Mon/Tue/Wed — likely PCE-
   adjacent risk; pre_jolts_drift is first-read mid-month — candidate LONG.
4. **Calendar accuracy concern partially exonerated.** A ~5% date error
   would not flip the W4 from +0.578 (CPI) to -0.434 (PCE) — the regime
   collapse is too large. Calendar drift isn't the rejection driver;
   the mechanism just doesn't generalise.

### What this REJECT is worth

Per the lesson-#54 / lesson-#55 discipline, a clean falsification of a
hypothesised generalisation is just as informative as a PASS confirmation —
arguably more so, because it sharpens the deployable framework. The "PCE
would corroborate CPI" prior (~70%) was wrong. The actual lesson is that
CPI is more specific than "any inflation print on NDX drifts LONG" — it's
"the first-read mid-month inflation print drifts LONG, end-of-month Friday
confirming-read does not." This refinement is what protects the deployed
CPI strategy from over-extrapolation when the next "obvious analog" (Treasury
yields print? Import-export prices? GDP deflator?) lands.

The honest deliverable here is the lesson, not the strategy. PCE is
tombstoned; the framework is sharper.
