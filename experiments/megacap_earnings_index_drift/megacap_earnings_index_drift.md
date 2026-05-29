# Mega-cap earnings-cluster INDEX drift (NDX100) — REJECT (marginal residual flagged)

**Status**: Phase 0/1 screen, 2026-05-28. **REJECT** (no sub-test clears the bar with a clean mechanism).
**Verdict**: **REJECT.** Tested whether NDX100 carries an INDEX-LEVEL structural drift around the Mag7
earnings fortnight (distinct from the tombstoned single-stock earnings family). Three sub-tests, none
deploy-grade:
- **A. Reaction-day** (NDX open→close on each Mag7 trade_date): NDX drifts DOWN — SHORT Sh **+0.77**
  (t+2.12, n=210), event-specific gap −24.9 bp vs +5.6 baseline; per-name TSLA −42 / MSFT −40 / NVDA −26
  all negative, only AAPL +6. Suggestive but **mechanism is murky** (likely AH-gap-then-intraday-fade),
  Sh < 1, and it overlaps the tombstoned earnings family — not promotable without a clean mechanism +
  weekday placebo + holdout split.
- **B. Post-NVDA relief** (NDX +1/2/3 sessions after NVDA): LONG +23/+40/+35 bp but Sh only +0.33–0.42,
  multi-day overlapping, dir-gap +0.68–0.85.
- **C. Post-cluster relief** (NDX after last Mag7 report each quarter): LONG Sh +0.15–0.42, weak.

**Residual flag (if ever revisited):** the reaction-day SHORT (A) is the only sub-signal with statistical
life; a clean follow-up would (i) condition on AMC-gap direction, (ii) add a non-event-weekday placebo to
rule out generic intraday-fade beta (lesson #82b), (iii) split the holdout. Not worth the cycles now —
the index-aggregate effect is not distinct enough from the rejected single-stock earnings work.

## Files
- [megacap_earnings_index_drift_screen.py](megacap_earnings_index_drift_screen.py) — screen (uses earnings_fade Mag7 calendar)
