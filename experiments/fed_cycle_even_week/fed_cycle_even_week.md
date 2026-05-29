# Fed-cycle even-week equity drift — REJECT (anomaly inverted OOS)

**Status**: Phase 0/1 screen, 2026-05-28. **REJECT — the Cieslak even-week anomaly has INVERTED post-publication.**
**Verdict**: **REJECT.** Cieslak-Morse-Vissing-Jorgensen (2019, JoF) found the entire US equity premium
1994-2016 was earned in EVEN weeks of the FOMC cycle. In 2019-2026 (mostly OOS to the paper, which
published right at our sample start) the sign is **reversed**: the premium is in ODD weeks.

- NDX100: even-week mean +3.98 bp vs odd-week +12.03 bp → **even-odd gap −8.05 bp** (inverted).
  Even-week-LONG timing strategy ann-Sh +0.21 vs Buy&Hold +0.90 → **fails lesson-#73 gate** (halves
  return for a worse Sharpe). SPX500 identical shape (gap −8.56 bp; strategy −0.01 vs B&H +0.80).
- Regime: W2 2021-22 catastrophically inverted (NDX even-odd gap −30 bp). Only W3H holdout shows a faint
  original-sign revival (+4 bp gap) but the timing strategy still underperforms B&H there too.

## Mechanism / why it failed
Published anomaly decay/arb (lesson #7 — weight literature decay warnings heavily). CMV published 2019;
the biweekly Fed-cycle pattern appears to have been arbed/inverted in the subsequent period. Also: even
if it had survived, it is **beta-timing not alpha** (correlated with the index-heavy book) — diversification
value would have been the separate, harder question. Adds a clean "famous-anomaly-inverted-OOS" data point.

## Files
- [fed_cycle_even_week_screen.py](fed_cycle_even_week_screen.py) — screen (even/odd null + B&H gate + regime)
