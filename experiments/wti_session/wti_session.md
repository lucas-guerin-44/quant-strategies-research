# USOUSD intraday session structure — Phase 0/1 — REJECT

**Status (2026-05-16):** All three candidate energy theses on USOUSD H1
2018-01-02 → 2026-05-15 (46,371 bars, MT5-topped-up) **REJECTED**.
- Thesis A (EIA-Wed): Phase 0 — no across-regime consistency
- Thesis C (NYMEX pit-close): Phase 0 — no directional drift
- **Thesis B (Asian-session drift)**: **Phase 1 REJECT** on W4-floor failure.
  Mechanism real 2018-2023, decayed/reversed in 2024-2026. Same shape as
  `btc_volbreak` per [[feedback_btc_w4_floor_binding]] — pre-W4 edge is
  not deployable.

**Verdict-summary table (Phase 1 variants @ 5bp RT, 9-hour 22→07 UTC):**

| variant | Sh full | Sh W4 | MDD | n | fade-gap | WF deg | Sh@8bp | kc | verdict |
|---|---|---|---|---|---|---|---|---|---|
| unconditional | +0.32 | **-0.58** | -22.3% | 738 | +1.53 | +0.815 | +0.06 | 5/9 | REJECT |
| mag (\|z\|>1.0) | +0.46 | **-0.27** | -14.5% | 242 | +1.49 | +1.009 | +0.28 | 7/9 | REJECT |
| dnmed | -0.04 | +0.27 | -8.2% | 159 | +0.39 | -0.004 | -0.19 | 2/9 | REJECT |

W4 binding fails on all three. Mag has 7/9 PASS but the failures are W4
Sharpe (binding) and walk-forward degradation +1.009 — exactly the failure
mode the W4-floor rule was designed to catch.

**Cross-asset corroboration of the regime-decay story:** Same hour-window
family (Asian session handoff), three completely divergent W4 trajectories:
- Gold (`xau_session`): W4 Sh **+1.23** — Asian institutional flow ACCELERATING
- BTC (`btc_intraday`): W4 binding Sh **+0.64** — partial W4 decay
- WTI (`wti_session`): W4 Sh **-0.58** — mechanism REVERSED

Same hour, different drivers: gold benefits from sovereign + Indian/Chinese
ETF rotation (still building post-2022); BTC benefits from spot-ETF Asian
inflow (peaked 2024-25); WTI's prior structural overnight drift apparently
got arbed out by professional electronic Asian crude flow post-2022. The
"Asian-session microstructure" family is **not** auto-transferable across
24/7-tradeable assets — driver matters.

## Origin

User-requested exploration: "Energy CFDs (USOUSD on Eightcap) — 24h trade,
different cycle". USOUSD is the only energy product the repo has touched
to date — STATE.md has zero energy entries. Broker confirms USOUSD/UKOUSD/
XNGUSD on Eightcap (memory `reference_eightcap_broker_symbols`).

The "24h, different cycle" framing pointed at three structurally distinct
candidate mechanisms that don't exist in the equity-index playbook:

1. **EIA Wednesday inventory release** — scheduled public-info release at
   10:30 ET / 15:30 UTC (winter) — closest to a `preclose_drift`-style
   info-event mechanism but on a single-venue (NYMEX) instrument that
   satisfies the microstructure prerequisite (lesson #4).
2. **Asian-session drift** — xau_session structural analog. WTI is 24/5
   tradeable so the session-handoff family applies; gold's Asian-physical-
   demand mechanism may or may not transfer to oil (oil's physical demand
   is Western — US driving / EU industrial — so sign-inversion is possible).
3. **NYMEX pit-close (14:30 ET / 19:30 UTC winter)** — settlement-window
   microstructure legacy.

## Phase 0 — Hour-of-day profile (`_profile_uso_phase0.py`)

Data: 46,371 H1 bars USOUSD 2018-01-02 → 2026-05-15 (datalake H1,
auto-derived from M5 — MT5 top-up 2025-09-01 → today injected 49,842 M5
bars before Phase 0).

### Thesis B (winner): Asian-session drift

Per-hour mean H1 bar return, FULL + W1-W4:

| hour UTC | FULL n | FULL bps | t | W1 | W2 | W3 | W4 |
|---|---|---|---|---|---|---|---|
| 1 | 1546 | +3.94 | +1.58 | +3.97 | +5.90 | -1.59 | +5.95 |
| **10** | 2145 | **+2.89** | **+2.08** | +1.28 | +6.61 | +0.91 | +2.74 |
| 14 | 2145 | +1.86 | +1.03 | -2.16 | +10.96 | +0.62 | -1.45 |
| **15** | 2146 | **-3.65** | **-1.89** | -1.39 | -6.52 | -2.69 | -3.90 |
| 17 | 2146 | +1.69 | +1.13 | +2.65 | -3.59 | +4.65 | +2.85 |
| 22 | 940 | +1.36 | +1.18 | -2.44 | +1.00 | +1.70 | +3.65 |

The signal-rich hours by all-regime consistency:
- **Hour 10 UTC (+2.89 t=+2.08)**: positive in all 4 regimes. European
  morning crude flow (LSE open + Asia book-flat).
- **Hour 15 UTC (-3.65 t=-1.89)**: negative in all 4 regimes. US morning
  open 10-11 ET; EIA-Wed release window contaminates this hour.

Session cumulative drift (sum of bar returns over window, per trading day):

| session | FULL | W1 | W2 | W3 | W4 |
|---|---|---|---|---|---|
| **Asia 23-07 UTC** | **+5.41** | **+8.37** | **+2.86** | **+5.60** | **+4.83** |
| London 07-13 UTC | +0.51 | -0.59 | +0.08 | +2.05 | +0.54 |
| US-morning 13-18 UTC | +0.16 | -3.47 | +2.00 | +3.01 | -0.56 |
| US-pit-close 18-20 UTC | -0.35 | -0.55 | +3.49 | -8.46 | +3.17 |
| US-late 20-23 UTC | +1.10 | -1.61 | +4.90 | -0.20 | +1.34 |

**Headline:** Asia 23-07 UTC cumulative drift +5.41 bps/day with all four
regime windows positive. This is the deploy-relevant pattern.

The Asia window is weaker than xau_session's gold equivalent (gold Asia +5.6
bps W4 is similar absolute, but on a much lower-vol instrument so the
Sharpe contribution is bigger) — but it's structurally consistent and
W4-positive, clearing the institutionalization rule's W4-floor prerequisite.

This DIFFERS from the prior expectation that oil's physical demand is
Western-only — there IS a structural overnight drift, just narrower than
gold's. Working hypothesis: not Asian-physical-demand per se, but
Asian-session position-squaring + the structural overnight backwardation
roll on a contract with active Asian arbitrage.

### Thesis A (rejected at Phase 0): EIA Wednesday inventory release

Per-hour Wed-vs-non-Wed comparison (mean bps, all regimes pooled):

| hour UTC | Wed (n=430) | !Wed (n=1715) | gap |
|---|---|---|---|
| 14 | +2.37 | +1.73 | +0.64 |
| 15 | -1.39 | -4.21 | +2.82 |
| 16 | -1.66 | -0.19 | -1.47 |
| 19 | **-4.96** (t=-1.58) | +0.93 | **-5.89** |
| 20 | -0.93 | +0.93 | -1.86 |

DOW slice for hour 19 UTC: Mon -2.05 / Tue +0.44 / **Wed -4.96** /
Thu +2.75 / Fri +2.51 — a real Wed-specific outlier ~3h post-release.

But across-regime per-Wed bucket (n~100/regime/hour) bounces sign:
W1 h17 +8.84 / W3 h15 -9.86 / W4 h14 +2.68. No consistent direction.

The Wed h19 -4.96 (t=-1.58) is the cleanest single observation but doesn't
clear the 2-sigma bar, and the per-regime sample is too thin to confirm
this isn't 2018-2026 noise concentrated in one DOW.

**Verdict A: REJECT at Phase 0.** Not pursuing as standalone thesis.
Lesson preserved: EIA inventory release is the dominant scheduled-info
cycle in WTI but doesn't show retail-extractable directional drift at H1
post-release. May resurface as an event-skip filter for the Phase 1
Asian-session strategy.

### Thesis C (rejected at Phase 0): NYMEX pit-close settlement drift

Pit-close hours 18-20 UTC, per-regime:

| hour | FULL | W1 | W2 | W3 | W4 |
|---|---|---|---|---|---|
| 18 | -0.10 | +2.48 | -2.14 | -3.12 | +2.03 |
| 19 | -0.26 | -3.10 | +5.75 | -5.33 | +1.38 |
| 20 | +0.55 | -0.36 | +4.48 | -2.27 | +0.41 |

Three pit-close hours, four regimes, no across-regime directional consistency.
Volatility-window mechanism may exist but no extractable directional drift.

**Verdict C: REJECT at Phase 0.** Tombstoned.

## Phase 1 thesis (pre-committed) — Asian-session drift on USOUSD

### Variant C (deploy candidate)

Mirrors the xau_session_demo.py Variant C structure exactly (so xau_session
methodology transfers and cross-asset comparison is honest).

- **Entry**: 22:00 UTC close (start of 23-00 UTC bar = Asia session start)
- **Exit**: 07:00 UTC close (end of 06-07 UTC bar = European open)
- **Hold**: 9 hours
- **Direction**: long
- **Filter variants**:
  - `baseline` — unconditional Asia long every trade-day
  - `filter_z` — fire only when |prior US-session zscore| > 1.0
  - `filter_dnmed` — fire only when prior US session DOWN AND 0.5 < |z| < 1.5
- **Cost model**: 5 bps RT realistic (Eightcap Raw USOUSD spread ~3-5 bps
  + commission ~1 bp = 4-6 bps). Stress at 8 bps RT.
- **Null check**: same simulator with direction=short (Variant C-SHORT).

### Pre-committed kill criteria

These are LOCKED in before running the Phase 1 simulator. Any failure → REJECT.

- **Full-sample net Sharpe > +0.30** at 5 bp RT cost (research bar; expect
  10-25% relative live haircut per rewritten lesson #5 in
  [[project_research_to_qc_degradation]] — to be validated against 6-12
  months of live data)
- **W4 net Sharpe > +0.40** at 5 bp RT cost (binding constraint per
  [[feedback_btc_w4_floor_binding]])
- **MDD < 20%** on FULL
- **Trade count ≥ 200** cumulative (with daily cadence × 8 years, baseline
  has ~1500 candidates, filtered variants ~300-500)
- **Fade-gap > +0.40** vs symmetric short-direction null
- **Walk-forward mean degradation < 0.6** across 5 rolling 3y-IS/2y-OOS
  splits (looser than 0.5 bar — oil regime has known structural breaks
  from COVID + Russia; we want to catch *systematic* OOS failure, not
  punish for the 2020 negative-price event)
- **Cost stress at 8 bp**: must remain Sharpe > 0
- **All-regime non-negative**: no single W1/W2/W3/W4 with Sharpe < -0.3

The looser walk-forward bar (0.6 vs xau_session's 0.5) reflects that crude
oil had THREE structural breaks in the backtest window (2020 COVID + April
2020 negative front-month + 2022 Russia/Ukraine) — split degradation
will spike for those window-pair combinations, mechanically.

### Why this thesis is structurally different from anything in the book

- **Asset**: crude oil. Repo has zero energy strategies. Correlation with
  GER40 (orb_dax) and NDX100 (lunch_fade) likely low (oil moves on supply
  shocks unrelated to equity-index info-resolution).
- **Mechanism family**: session-handoff microstructure. Same family as
  lunch_fade and xau_session. Cross-asset evidence: if USOUSD shows the
  same Asian-session activation as xau_session, that's a third independent
  data point for the "post-2022 Asian-OTC institutional flow" mechanism
  beyond gold+BTC.
- **Time-of-day**: overnight (Asian hours). Live book is EU-morning
  (orb_dax 09:00 Berlin) and US-lunch (lunch_fade 11:30-13:30 ET).
  xau_session is also Asian-hours so this is the second overnight strategy
  — execution-time correlation, but if both deploy paper concurrently
  we'll see whether the gold-and-oil flows are independent or coupled.
- **Sign expectation**: if signed UP like gold, that's "Asian flows lift
  alt-store-of-value assets". If signed DOWN (which Phase 0 does NOT
  support — Asia 23-07 is +5.41 across all regimes), would have been a
  publishable cross-asset divergence.

### Expected performance (per Phase 0, pre-Phase-1)

- Asia 23-07 cumulative ~5.4 bps/day FULL ≈ 0.054% per trade gross
- ~252 trade-days/yr × 0.054% gross = ~13.6% gross/yr
- Net at 5 bp RT cost: ~0.054% - 0.05% = +0.004% per trade → ~+1%/yr
- Filtered variants targeting +0.10% per trade gross: net ~+0.05% ×
  50-80 trades/yr = +2-4%/yr
- **Sharpe target: research +0.5 to +1.0; live +0.2 to +0.6**

If results clear pre-commit, next steps are Phase 2 (full kill-criteria
battery), Phase 3 (stat battery), Phase 4 (regime block-bootstrap), Phase 7
(MT5 EA) — same staircase as xau_session.

## Phase 1 results (2026-05-16, `wti_session_demo.py`)

Three variants run end-to-end through the pre-committed kill-criteria battery:
unconditional, mag (|prior US z|>1.0), dnmed (DOWN-med). All at 5 bp RT
deploy cost, 8 bp stress.

### Variant: unconditional (Variant C 22→07 UTC long)

| metric | value | bar | pass |
|---|---|---|---|
| Sharpe FULL | +0.32 | > +0.30 | PASS |
| Sharpe W4 | **-0.58** | > +0.40 | **FAIL** (binding) |
| MDD | -22.3% | < 20% | FAIL |
| Trades | 738 (89/yr) | ≥ 200 | PASS |
| Fade-gap | +1.53 | > +0.40 | PASS |
| WF mean deg | +0.815 | < 0.60 | FAIL |
| Cost stress @8bp | +0.06 | > 0 | PASS |
| Regime floor | -0.58 | > -0.30 | FAIL |
| DOW concentration | 31.4% | < 50% | PASS |

Per-regime decomposition is the load-bearing read-out:

| regime | CAGR | Sharpe | MDD | trades | mean/trade |
|---|---|---|---|---|---|
| W1 2018-2019 | +1.28% | +0.29 | -4.3% | 153 | +0.018% |
| W2 2020-2021 | +5.47% | +0.60 | -9.8% | 160 | +0.072% |
| W3 2022-2023 | +17.06% | **+1.93** | -5.1% | 159 | +0.201% |
| **W4 2024-2026** | **-8.78%** | **-0.58** | **-22.3%** | 266 | **-0.073%** |

W4 is not just weaker — it has SIGN-FLIPPED. The strategy lost 8.78% CAGR
over 2024-2026 on 266 trades, with the deepest drawdown of any window.
n=266 is a real sample; this is not noise.

Walk-forward exposes the timing of the decay cleanly:

| split | IS years | OOS years | IS Sh | OOS Sh | deg |
|---|---|---|---|---|---|
| S1 | 2018-2020 | 2021-2022 | +0.62 | **+1.62** | -1.00 |
| S2 | 2019-2021 | 2022-2023 | +0.53 | **+1.93** | -1.40 |
| S3 | 2020-2022 | 2023-2024 | +1.37 | **-0.25** | +1.62 |
| S4 | 2021-2023 | 2024-2025 | +1.33 | **-1.65** | +2.98 |
| S5 | 2022-2024 | 2025-2026 | +1.28 | **-0.60** | +1.88 |

IS Sharpe is uniformly strong across all 5 splits (the discovered edge is
robustly present in any 3-year IS window). OOS Sharpe is the story — strong
when OOS=2021-2023 (carries 2022 Russia/OPEC vol), collapses the moment OOS
enters 2024+. This is a regime change, not a fit-failure.

### Variant: mag (|prior US z|>1.0)

| metric | value | bar | pass |
|---|---|---|---|
| Sharpe FULL | +0.46 | > +0.30 | PASS |
| Sharpe W4 | -0.27 | > +0.40 | **FAIL** (binding) |
| MDD | -14.5% | < 20% | PASS |
| Trades | 242 (29/yr) | ≥ 200 | PASS |
| Fade-gap | +1.49 | > +0.40 | PASS |
| WF mean deg | +1.009 | < 0.60 | **FAIL** |
| Cost stress @8bp | +0.28 | > 0 | PASS |
| Regime floor | -0.27 | > -0.30 | PASS (just) |
| DOW concentration | 40.9% | < 50% | PASS |

7/9 PASS — and the two FAILs are exactly the regime-decay-detection bars.
This is the most insidious variant: full-sample Sharpe +0.46 with passing
cost stress and clean fade-gap looks deployable until you check W4.

### Variant: dnmed

| metric | value | bar | pass |
|---|---|---|---|
| Sharpe FULL | -0.04 | > +0.30 | FAIL |
| Sharpe W4 | +0.27 | > +0.40 | FAIL |
| MDD | -8.2% | < 20% | PASS |
| Trades | 159 | ≥ 200 | FAIL |
| Fade-gap | +0.39 | > +0.40 | FAIL (barely) |
| WF mean deg | -0.004 | < 0.60 | PASS |
| Cost stress @8bp | -0.19 | > 0 | FAIL |
| Regime floor | -0.52 | > -0.30 | FAIL |
| DOW concentration | 58.5% | < 50% | FAIL |

2/9 PASS. Strictest filter, but the selection is too tight on this signal —
absolute Sharpe collapses with too few trades.

### Phase 1 verdict: REJECT on pre-committed kill criteria

All three variants fail the **W4 Sharpe > +0.40** binding constraint, which
was set per [[feedback_btc_w4_floor_binding]] specifically to catch
pre-institutionalization edges that don't deploy. The unconditional and mag
variants pass the looser bars (full Sharpe, fade-gap, cost stress) but the
W4 sign-flip is decisive.

This is the same failure pattern as `btc_volbreak`: a real mechanism
concentrated in early-regime windows that has decayed (or here, reversed)
in the post-2022 regime. Per the BTC institutionalization mirror-image
rule (STATE.md pattern -1), strategies in a mechanism family that decays
under market maturation inherit the decay; those that activate under
maturation inherit the activation.

WTI Asian-session drift sits on the **decay side**: pre-2024 the structural
overnight drift was retail-and-Asian-physical-flow extractable; post-2024 the
flow is professional electronic — algos arb the open-to-Asia handoff faster
and direction has flipped.

### What NOT to do (per repo conventions)

- DO NOT refine variants to find a W4-positive cell post-hoc. That is the
  exact goalpost-moving trap from the lumber_oats lesson — adding a regime
  gate fit to retroactively skip 2024-2026 is fitting to the binding bar.
- DO NOT pivot to a "post-2024 fade direction" thesis without writing it
  as a separate Phase 1 with its own pre-committed kill criteria. The
  short_null run showed Sharpe -1.21 on the unconditional, so a naive sign
  flip doesn't deploy either — the 2018-2023 long signal is too strong to
  let a flipped strategy net positive across the full sample.
- DO NOT propose more energy theses without first reading the cross-asset
  divergence lesson (next section). Different physical-demand cycles can
  produce opposite W4 trajectories on the same hour-of-day signal.

### Cross-asset divergence — the publishable lesson

Same hour-window family (Asian session handoff, ~22-08 UTC), three 24/7
instruments, three completely divergent W4 trajectories:

| asset | mechanism | W4 Sharpe | verdict |
|---|---|---|---|
| XAU (`xau_session`) | Asian-OTC physical / sovereign / Indian/Chinese ETF | **+1.23** | DEPLOY |
| BTC (`btc_intraday`) | Tokyo/HK/SGP institutional open + spot-ETF inflow | +0.64 binding | MARGINAL |
| WTI (`wti_session`) | (historical) Asian-physical-flow + overnight roll | **-0.58** | REJECT |

The "Asian-session microstructure" family is NOT auto-transferable across
24/7 instruments. Driver-specificity matters:
- Gold's driver is intact and growing (CB reserve diversification post-Russia,
  Indian/Chinese ETF inflow accelerating).
- BTC's driver peaked with spot-ETF launch (Q1 2024) and is showing partial
  decay in 2026Q1.
- Oil's driver was retail/regional and has been arbed out by professional
  electronic flow.

For future scoping: pre-commit which side of "post-2022 institutionalization"
the candidate mechanism lives on before writing a thesis doc. Asian-session
theses on assets whose Asian driver is professional/electronic
(FX-G10, oil, base metals) should expect the WTI shape; those with structural
Asian-physical demand (gold, agricultural softs, perhaps silver) should
expect the gold shape.

## Files

- `wti_session.md` — this doc
- `_fetch_uso_h1.py` — pulls USOUSD H1 from datalake (year-by-year, caps at
  10000 rows/request) into `ohlc_data/USOUSD_H1.csv`
- `_profile_uso_phase0.py` — Phase 0 profile, three theses in one pass
- `wti_session_demo.py` — **Phase 1 simulator** (Variant C baseline +
  filter_z + filter_dnmed, with kill-criteria battery, regime breakdown,
  walk-forward, cost-stress, null-check)

## Lineage

- Adapted from `xau_session.md` structure and `xau_session_demo.py`
  simulator. Same Variant C 9-hour overnight, same |prior-NY z| filter
  framework, same kill-criteria template (looser walk-forward bar
  documented above).
- Cross-asset corroboration of the Asian-session-handoff mechanism family
  identified in xau_session + btc_intraday.
