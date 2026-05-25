# Pre-ECB drift on GER40 (24h pre-announcement LONG)

**Status**: Phase 2 complete (2026-05-23). Direct European-analog of `macro_drift`
(DEPLOYED_PAPER NDX100 24h pre-FOMC LONG, Sh +1.04 research / W4 +0.55 / MDD -2.37%).
Same mechanism — institutional positioning into a scheduled high-impact monetary
policy release — applied to the ECB Governing Council monetary policy meetings
on GER40 (DAX) CFD.

**Verdict**: **REJECT** — pre-FOMC drift mechanism does not port to pre-ECB on GER40.
Baseline 24h LONG mean -0.056% (Sh -0.11), direction null-gap -0.011% (zero directional
content), walk-forward 3/3 splits OOS near-zero or negative, W3 (hiking cycle) is the
WORST regime (Sh -0.50) — opposite of macro_drift FOMC W3 (+2.38). Five of six load-bearing
kill criteria FAIL. Tombstone; the macro-event-positioning-drift family is now confirmed
US-equity-pre-FOMC-specific, not portable across central banks. See new lesson #54.

## Thesis (mechanism)

Lucca & Moench (2015) documented a robust positive equity drift in the 24h
window before scheduled FOMC announcements on the S&P 500, attributable to
risk-premium accumulation by institutions hedging or positioning ahead of the
announcement. `macro_drift` validated the mechanism survives on retail
CFD-cost terms on NDX100 (Sh +1.04). The same flow logic should apply,
mutatis mutandis, to the European analog: ECB Governing Council monetary
policy meetings on European equity indices.

Why GER40 / DAX specifically:
1. **DAX is the most ECB-sensitive European index** — concentrated bank
   exposure (Deutsche Bank, Commerzbank in legacy DAX; broader financials in
   DAX 40) makes it the most rate-sensitive cash basket in Europe.
2. **Xetra cash trading window (09:00-17:30 CET) brackets the 14:15 CET
   announcement time** — the 24h pre-event window is fully inside continuous
   trading, no overnight-gap or auction-resolution confounds.
3. **Already a deployed venue** (`orb_dax` Xetra-open breakout, +0.76 Sh).
   GER40 CFD spread, fill behaviour, and intraday liquidity profile are
   well-understood from existing book.

Differences vs `macro_drift` (FOMC) that may affect the result:

1. **ECB has TWO scheduled events per meeting**: the rate decision at 13:45
   CET (pre-2023) or 14:15 CET (2023+) AND the press conference 30 minutes
   later (14:30 CET legacy / 14:45 CET modern). The 24h-pre-decision drift
   may compete with positioning that targets the press-conference window. The
   exit-buffer convention from `macro_drift` (30 min before announcement)
   means we exit ~12:45-13:45 CET, well before either event.
2. **Press conference is often where the bigger move occurs**, which means
   institutional positioning AHEAD of the rate decision may be smaller than
   for FOMC (where the rate decision + statement is the primary event).
3. **The "pre-FOMC drift" academic literature is much larger than any
   pre-ECB drift literature** — the European mechanism is theoretically
   plausible but less-documented. Honest expectation: smaller effect size,
   probably lower information ratio.

## Key reference

- **Lucca, D. & Moench, E. (2015), "The Pre-FOMC Announcement Drift", Journal
  of Finance** — the canonical paper. They did not test the ECB analog;
  follow-up European literature (Brusa et al., 2020) found weaker but
  detectable effects on European indices, with much higher cross-section
  variance than the US result.
- **`experiments/macro_drift/macro_drift.md` (2026-05-22)** — direct parent.
  This experiment ports the methodology one-for-one.

## Signal math

```
Per ECB monetary policy meeting at announce_utc:

  entry_t = announce_utc - 24 hours
  exit_t  = announce_utc - 30 minutes

  entry_px = M5 close at nearest bar to entry_t  (tolerance 30 min)
  exit_px  = M5 close at nearest bar to exit_t   (tolerance 30 min)

  gross_pct = (exit_px - entry_px) / entry_px * 100
  net_pct   = gross_pct - cost_bps_RT / 100         (5 bp RT default)

Position: LONG, full notional, one trade per meeting.
```

Per-event 23.5-hour hold. Cadence: ~8 meetings per year. Annualization
factor: sqrt(8).

## Why retail-accessible

Same profile as `macro_drift`:
- Eightcap GER40 CFD confirmed tradeable (already deployed via `orb_dax`).
- 24h hold → minimal swap drag (~0.5-1 bp at typical broker financing).
- Calendar-driven entry: the EA needs to read `ecb_calendar.csv` to know
  when to enter/exit. Same scaffolding as `deploy/mq5/macro_drift.mq5`.
- Forward calendar maintenance: refresh ~quarterly from ecb.europa.eu.

## Universe

- **Research**: GER40 M5, 2018-01-25 → 2026-04-30. 65 historical ECB meetings.
- **Live**: Eightcap MT5 GER40 CFD. Margin and spread profile identical to
  `orb_dax`.

## Expected performance (at thesis time)

Honest priors based on the macro_drift result + the FOMC-vs-ECB literature
gap:

- **Most likely (50%)**: PASS with reduced magnitude vs FOMC. Per-trade
  mean +0.10-0.20%, full Sh +0.40 to +0.70, W4 (2024-2026) Sh +0.20 to +0.40.
  Direction null-gap > +0.30 (mechanism real, sign correct).
- **Plausible (30%)**: MARGINAL. Per-trade mean +0.05-0.10%, full Sh
  +0.20-0.40, W4 borderline. Mechanism present but the press-conference-
  positioning confound dilutes the 24h-pre-decision window.
- **Plausible (20%)**: REJECT. The pre-FOMC drift mechanism doesn't port
  cleanly because the European institutional positioning concentrates on
  the press-conference window, not the rate-decision window. The 24h-pre
  test would show flat or negative drift.

Cross-correlation pre-commit: ECB and FOMC dates do not coincide structurally
(different calendars), so the live combined book (`macro_drift` NDX FOMC +
this strategy GER40 ECB) would have near-zero overlap. If both pass, that's
a useful diversifier-add to the macro-event book.

## Fail conditions (pre-committed)

Phase 2 KILL if ANY of:

1. **Per-trade mean (full sample) ≤ +0.10%** at 5bp RT cost.
2. **W4 (2024-2026) per-trade mean ≤ +0.05%**. (W4 floor mirrors macro_drift.)
3. **Win rate ≤ 55%**.
4. **Max DD > 25%**.
5. **Events count < 50**.
6. **Direction null-gap (LONG − SHORT) < +0.30**. (Per CLAUDE.md step 6.)
7. **Walk-forward mean OOS Sharpe < +0.30** OR **min OOS Sharpe < 0** across
   the three rolling IS/OOS splits matching macro_drift's protocol.
8. **Placebo non-ECB Thursdays show similar magnitude drift** (per-trade
   mean > +0.05% with t > 1.5 on the non-event Thursday sample).

PASS only if ALL of (1)-(8) hold.

## Why this might fail (red flags)

1. **Press-conference positioning competes with the 24h-pre-decision window.**
   European institutions may hedge into the press-conference (14:45 CET)
   rather than the rate-decision (14:15 CET), so the 24h-pre-decision drift
   is smaller than the FOMC analog where statement + decision are one event.
2. **DAX index composition has shifted** (DAX 30 → DAX 40 in 2021). The
   pre-2021 sample is a slightly different basket; the W1-W2 regime split
   may carry composition-change noise.
3. **2022-2023 ECB hiking cycle** may have produced unusually strong /
   unusually weak drift due to the regime-novel event sequence. W3 may
   dominate full-sample stats and W4 (post-2024-cut-cycle) may show a
   different pattern entirely — mirroring the macro_drift W4 attenuation.
4. **CET DST handling**. Europe/Berlin DST runs last-Sunday-March →
   last-Sunday-October. Off-by-one-hour bugs in the conversion would
   misalign the entry/exit times by 60 min, which is non-trivial within a
   23.5h window and could nuke or fabricate the signal.
5. **Pre-2023 announce time was 13:45 CET, post-2023 is 14:15 CET.** The
   30-min shift is hard-coded per-row in the calendar. If the actual flow
   pattern is *clock-tied* (e.g., institutions position by 13:00 CET
   regardless of announce time), this 30-min shift could artificially
   create or destroy the post-2023 signal.

## Phase 2 plan

- [x] Write thesis with pre-committed fail conditions (this doc).
- [x] Compile `ecb_calendar.csv` (65 historical + 5 forward).
- [ ] Implement `pre_ecb_drift_demo.py` — mirrors macro_drift_demo.py
      structure. Includes: per-event return computation, regime breakdown,
      walk-forward, direction null-check, placebo non-ECB Thursdays,
      cost sensitivity.
- [ ] Run end-to-end. Update verdict + mechanistic interpretation.
- [ ] If PASS: scaffold `deploy/mq5/pre_ecb_drift.mq5` (calendar-aware EA
      mirroring `deploy/mq5/macro_drift.mq5`).
- [ ] If REJECT: tombstone; note specific kill reason for future event-drift
      proposals on European venues.

## Files

- `pre_ecb_drift.md` — this doc
- `ecb_calendar.csv` — historical + forward ECB Governing Council monetary
  policy meeting dates 2018-2026
- `pre_ecb_drift_demo.py` — Phase 2 simulator + validation pipeline
- Future (if PASS): `deploy/mq5/pre_ecb_drift.mq5`

---

## Results (2026-05-23)

### Headline

| Metric | Value | vs macro_drift NDX FOMC | Verdict |
|---|---|---|---|
| Events | 58 (of 67 calendar — 9 dropped from data gaps pre-2019) | 56 | PASS |
| Per-trade mean (5bp RT) | **-0.056%** | +0.276% | FAIL (need > +0.10%) |
| Sharpe (ann × √8) | **-0.11** | +1.04 | FAIL |
| W4 mean (2024-2026) | **+0.023%** | +0.234% | FAIL (need > +0.05%) |
| Win rate | **51.7%** | 60.7% | FAIL (need > 55%) |
| MDD | -9.08% | -2.37% | PASS |
| Direction null-gap | **-0.011%** | +1.98 | FAIL (need ≥ +0.30) |
| Walk-forward OOS mean Sh | -0.00 | +0.89 | FAIL (need ≥ +0.30) |
| Walk-forward OOS min Sh  | -0.22 | +0.41 | FAIL (need ≥ 0) |
| Placebo Thursdays mean | -0.261% (t -1.94) | -0.034% (t -0.26) | PASS (placebo benign per spec, but see interpretation below) |

5 of 6 binding kill-criteria FAIL. Verdict: REJECT.

### Regime breakdown

| Window | n | mean | std | t | WR | Sh |
|---|---|---|---|---|---|---|
| W1 (2018-2019) | 8 | +0.096% | 0.492% | +0.55 | 62.5% | +0.55 |
| W2 (2020-2021) | 16 | -0.116% | 2.410% | -0.19 | 56.2% | -0.14 |
| **W3 (2022-2023)** | **16** | **-0.159%** | 0.908% | **-0.70** | 43.8% | **-0.50** |
| W4 (2024-2026) | 18 | +0.023% | 0.723% | +0.13 | 50.0% | +0.09 |

W3 is the **worst** regime — opposite of macro_drift FOMC where W3 was the best
(+0.70%, Sh +2.38). The same monetary-policy regime (rate-hike cycle) produced
opposite-signed pre-event drift on the two venues. This is the most diagnostically
useful finding in the experiment.

### Walk-forward

| Split | IS n | IS Sh | IS mean | OOS n | OOS Sh | OOS mean |
|---|---|---|---|---|---|---|
| IS 2018→2022 / OOS 2022-2026 | 24 | -0.06 | -0.045% | 34 | **-0.22** | -0.063% |
| IS 2018→2023 / OOS 2023-2026 | 32 | -0.21 | -0.128% | 26 | +0.12 | +0.033% |
| IS 2018→2024 / OOS 2024-2026 | 40 | -0.16 | -0.091% | 18 | +0.09 | +0.023% |

WF OOS mean = -0.00, WF OOS min = -0.22. Mechanism does not survive walk-forward
even on the most charitable IS slicing.

### Window sweep (in-sample diagnostic only — NOT used for verdict)

| Window | Buffer | n | Mean | Sh |
|---|---|---|---|---|
| 6h | 30min | 58 | -0.108% | -0.62 |
| 12h | 30min | 17 | -0.340% | -0.72 |
| 18h | 30min | 58 | -0.118% | -0.29 |
| **24h** (pre-commit) | **30min** | **58** | **-0.056%** | **-0.11** |
| 48h | 30min | 58 | +0.219% | +0.29 |

Note: the 48h window is the only one with positive drift, but per lesson #16 / #20,
picking it post-hoc would be in-sample window-fit refinement — exactly the failure mode
those lessons exist to prevent. **The 24h pre-commit failed; the experiment is
REJECTED, not refined.**

### Placebo nuance — useful for interpretation

Placebo non-ECB Thursdays at 14:15 CET anchor show mean -0.261% (t -1.94). The ECB
baseline shows -0.056%. The DIFFERENCE (+0.205% per trade) is real and probably
statistically detectable as an "ECB days are less-bad than placebo Thursdays" effect.
But the absolute level on ECB days is still negative after costs, so this is a
*relative* signal that doesn't survive friction.

This means there IS a pre-ECB positioning effect on GER40 — it lifts the index
~+0.2% vs the structural Thursday baseline — but the structural Thursday baseline
itself is sufficiently negative (likely a Xetra mid-day microstructure artifact in
the 13:15-13:45 UTC window) that the lift doesn't clear zero. Not deployable, but
mechanistically informative.

### Mechanistic interpretation

1. **The pre-FOMC drift mechanism is NOT a generic "monetary-policy positioning"
   effect — it is FOMC-and-US-equity-specific.** Three pieces of evidence in this
   single experiment:
   - W3 sign-flip (hiking cycle helps macro_drift FOMC, hurts pre_ecb_drift)
   - Direction null-gap collapse (LONG ≈ SHORT on ECB days, gap -0.011%)
   - Walk-forward consistent failure across all 3 splits
2. **Press-conference positioning confound (red flag #1 from thesis) is the most
   parsimonious explanation.** European institutions appear to wait for the
   13:45/14:15 CET decision + the 14:30/14:45 CET press conference as a single
   compound event, hedging into the press-conference window rather than the
   24h-pre-decision window. The 24h-pre window captures the wait-and-see "no
   trade until decision is known" period, not positioning flow.
3. **DAX banks-heavy composition** means rate decisions are highest-information,
   high-volatility events, but the DIRECTION of bank-stock response is the
   variable that the pre-event window can't predict. A "long-only-into-rate-event"
   prior has no theoretical basis when the underlying is bank-heavy and the
   decision direction is bi-modal.
4. **48h positive drift (+0.23%) is suggestive of a different mechanism** —
   possibly a 2-day-pre-event volatility-compression / risk-on lift, but
   isolating it would require a pre-committed Phase 2 of its own (write the
   thesis BEFORE seeing the sweep), and there's no theoretical motivation
   strong enough to justify it. Filed as "interesting datapoint, not actionable."
5. **The structural Xetra mid-day negative drift on Thursdays** (placebo
   -0.261%, t -1.94) is a separate finding that might be worth a one-off
   investigation — possibly a futures-roll or US-pre-market positioning artifact
   that systematically pushes DAX cash down in the 13:15-13:45 UTC window. Not
   tradeable as a stand-alone strategy (only -0.26% gross would be eaten by
   2× CFD friction immediately), but a useful artifact to know about when
   designing future GER40 intraday strategies that might unwittingly fight it.

### Tombstone — what the family looks like now

This is the second post-macro_drift event-family extension attempt and the first
REJECT in the family:

- `macro_drift` (FOMC, NDX/SPX/GER) — DEPLOYED_PAPER (NDX), Sh +1.04
- `pre_ecb_drift` (ECB, GER40) — REJECT (this experiment)
- Untested: pre-NFP (US), pre-CPI (US), pre-BOE (UK), pre-BOJ (JPN)

The negative result here updates the prior for these untested extensions:
**the pre-FOMC mechanism appears mechanism-specific to US Fed × US equity**, not
a portable "macro-event positioning" mechanism. This doesn't preclude success on
the other four candidates — it just downweights the prior. Honest expected
outcome for pre-NFP / pre-CPI on NDX (same venue as macro_drift, different event):
~30% chance of PASS. For pre-BOE / pre-BOJ on local indices (different venue +
different central bank): ~15% chance, lower than the pre-ECB prior would have
suggested before this result.

### What's worth doing next (and what isn't)

- **Worth doing**: `pre_nfp_drift` on NDX100 — same venue as macro_drift (already
  validated FOMC mechanism there), different event (monthly employment release at
  08:30 ET). Strong prior on the venue, weak prior on the event-portability after
  pre_ecb_drift REJECT. Pre-commit the same kill criteria as this experiment.
- **NOT worth doing**: any "rescue refinement" of pre_ecb_drift — 48h window,
  press-conference-centered window, ECB-only-cut-meetings, etc. The fundamental
  result is that the LONG-direction prior is wrong on GER40 ECB days; rescuing it
  via parameter tuning would be the exact pattern lessons #16 / #20 / #43 warn
  against.

## Files

- `pre_ecb_drift.md` — this doc
- `ecb_calendar.csv` — 67 historical ECB Governing Council monetary policy
  meetings 2018-2026 + 5 forward dates (2026 H2)
- `pre_ecb_drift_demo.py` — Phase 2 simulator (per-event returns, regime
  breakdown, walk-forward, direction null-check, placebo Thursdays, cost
  sensitivity, window sweep)
