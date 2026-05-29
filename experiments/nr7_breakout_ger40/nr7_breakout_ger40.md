# NR7 volatility-contraction breakout (GER40) — REJECT

**Status**: Phase 0/1 screen, 2026-05-28. **REJECT (phantom-alpha bug caught; no real edge).**
**Verdict**: **REJECT.** First-pass screen looked spectacular (continuation Sh **+2.69**, holdout W3H
**+4.29**, dir-gap +5.59, t+4.05) — which tripped the lesson-#77 "observed Sh > 2× prior ⇒ mandatory
code audit" rule. Audit found a **lesson-#81-class fill bug**: on NR7 (tight-range) days the next session
frequently **gaps through** the NR7 level at the open, but the sim filled at the exact breakout level
`nr_hi`/`nr_lo`, booking the (open − level) gap as phantom profit. Gap-aware fill (fill at the open when
the bar opens past the level) **collapsed the edge to Sh +0.04** (full), cost-zero +0.16 (signal-absent
per lesson #26), continuation only positive in the W3 holdout (+9.91/Sh+1.95) but negative W1/W2
(−1.60/−0.38) ⇒ recent-only artifact, full-sample dead. **No real edge once fills are realistic.**

## Thesis (refuted)
Crabel volatility-contraction: the day after a narrowest-range-in-7 (NR7) session, price expands and
breaks the range; orb_dax proves DAX has opening-impulse momentum (lesson #18) so a vol-contraction
breakout might tap the same Xetra property. Refuted: the apparent edge was entirely gap-through fill
optimism, not a real breakout-continuation premium.

## Why it failed
- **Phantom gap-fill alpha** (lesson #81 class). Realistic fills (open-on-gap) erase it.
- Cost-zero Sh +0.16 ⇒ signal-absent, not friction-eaten (lesson #26).
- 3rd phantom-alpha catch in the repo (after #77 `fra40_mid_morning_momentum` same-bar-leak and #81
  `xau_imbalance` stop-geometry) — corroborates the "too-good intraday breakout ⇒ audit fills first" rule.

## Files
- [nr7_breakout_ger40_screen.py](nr7_breakout_ger40_screen.py) — screen (with the gap-aware-fill guard + gap-through counter)
