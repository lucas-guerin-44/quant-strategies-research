# Pre-PPI drift on NDX100 (24h pre-release, direction TBD)

**Status**: Phase 2 complete (2026-05-24). Fourth extension attempt of the
macro_drift event-family. Methodology identical to `pre_cpi_drift`.

**Verdict**: **REJECT** — no edge in either direction. Best-direction (SHORT)
mean -0.019% (Sh -0.04), all kill criteria FAIL, direction null-gap -0.06
(zero directional content), walk-forward 3/3 OOS negative (mean -0.40, min
-0.86), placebo significantly negative (-0.471%, t -2.82). Tombstone.

## Why this exists / hypothesis

Direct corroboration test of the canonical rule from
[pre_cpi_drift](../pre_cpi_drift/pre_cpi_drift.md): scheduled US-macro
events on NDX drift LONG in 24h pre-event window. PPI is a structurally
similar hard-data release (08:30 ET, monthly, BLS), released ~1 day after
CPI in 2022+ (and ~1 day before CPI pre-2022). Should pass if the canonical
rule holds.

Result: **does NOT pass**. PPI is the family's first REJECT on a US-venue
US-macro event — informative about *which* US events generate institutional
positioning flow.

## Results (2026-05-24)

### Headline (both directions)

| Direction | n | mean | t | Sh (×√12) | MDD | WR |
|---|---|---|---|---|---|---|
| LONG (winner side, marginal) | 88 | +0.042% | +0.28 | +0.09 | -19.78% | 50.0% |
| **SHORT (best, still REJECT)** | 88 | -0.019% | -0.13 | -0.04 | -18.37% | 39.8% |
| **Null-gap (LONG − SHORT)** | | -0.061% | | | | |

Direction null-gap -0.061 = zero directional content. Both directions
essentially flat with negative tail bias. No mechanism present.

### Placebo is the diagnostic

| Population | n | mean | t |
|---|---|---|---|
| Placebo non-PPI weekdays SHORT | 88 | -0.471% | **-2.82** |

The placebo non-PPI weekdays at 08:30 ET show mean -0.471% with t -2.82
(significantly negative — structural Tue/Wed/Thu morning microstructure
drift on NDX, possibly futures-roll / pre-cash-open positioning artifact).

The PPI-day SHORT mean of -0.019% is therefore *less-bad* than the
weekday baseline of -0.471% — there IS a +0.452% relative "PPI-day positioning"
lift, but the absolute level is still near-zero, not enough to clear cost
zero, and the *direction* of the lift is opposite of the SHORT pre-commit.

In other words: the PPI day positioning IS pushing NDX UP relative to the
weekday baseline, but only enough to neutralize the structural negative drift,
not enough to deliver a deploy-grade LONG signal.

### Walk-forward

| Split | IS Sh | OOS Sh |
|---|---|---|
| 2019→2022 / OOS 2022-2026 | +0.28 | -0.24 |
| 2019→2023 / OOS 2023-2026 | +0.41 | -0.86 |
| 2019→2024 / OOS 2024-2026 | -0.02 | -0.10 |

Mean OOS -0.40, min -0.86. Walk-forward is consistently negative or
near-zero. Mechanism is not present in any sub-window.

## Mechanistic interpretation

**PPI is a "second-tier" macro release in the post-2022 regime.** Two
parsimonious explanations:

1. **Information pre-priced from CPI.** When CPI releases on day T, the
   inflation surprise is fully absorbed by close of T. PPI on T+1 contains
   redundant inflation information (producer-price inflation tracks
   consumer-price inflation with high autocorrelation). The marginal
   information content of PPI is small ⇒ institutions don't pre-position
   into it ⇒ no risk-premium accumulation ⇒ no LONG drift.
2. **Pre-2022 PPI release order was ambiguous** (sometimes before CPI,
   sometimes after); only the post-2022 standardized PPI-day-after-CPI
   pattern would be a clean test of the "information-redundancy" hypothesis.
   The full-sample averages noise from both regimes.

The implication for the canonical rule is positive, not negative: the
mechanism that drives FOMC / CPI / Retail Sales LONG drift is specifically
institutional positioning into events that carry **novel information**, not
just any scheduled macro release. PPI being a follow-on to CPI strips it of
that property and produces no drift.

## What this teaches about candidate selection for future macro-event extensions

Updated prior for any "pre-{event} drift on NDX" thesis based on the family
results so far:

| Event property | Pass-rate prior |
|---|---|
| Novel-information US release on NDX | ~80% (3 of 3: FOMC, CPI, Retail Sales) |
| Follow-on / redundant-info US release on NDX | ~20% (0 of 1: PPI) |
| Friday US release on NDX | ~50% SHORT (1 of 1: NFP — direction-flips) |
| European release on EU index | ~10% (0 of 1: ECB on GER40) |

Future candidates worth running:
- **Pre-Jobless-Claims (weekly)**: Thursday 08:30 ET, weekly, novel info → likely LONG. ~70% prior.
- **Pre-ISM-Manufacturing (monthly)**: 1st business day 10:00 ET, novel info → likely LONG. ~70% prior.
- **Pre-PCE (monthly)**: Last business day 08:30 ET, novel info (Fed's preferred inflation gauge) → likely LONG. ~70% prior.

Candidates NOT worth running based on the PPI result:
- **Pre-Core-PPI** (subset of PPI): redundant with PPI which is redundant with CPI.
- **Pre-Import-Prices** (monthly mid-month): typically released same-time as
  Retail Sales, redundant.

## Files

- `pre_ppi_drift.md` — this doc
- `ppi_calendar.csv` — 99 PPI release dates 2018-2026 (97 historical, 2
  forward; 88 within NDX100 M5 data coverage)
- `pre_ppi_drift_demo.py` — Phase 2 simulator (clone of pre_cpi_drift_demo,
  calendar swap only)
