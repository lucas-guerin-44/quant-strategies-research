# JPN225 lunch-fade — REJECT (formal cash halt ≠ continuous-trading lunch lull)

**Status**: Phase 0/1 screen, 2026-05-28 (JPN225 M5 fetched via MT5 this session). **REJECT.**
**Verdict**: **REJECT — decisive.** Most mechanism-justified `lunch_fade` transplant target (TSE is the
one major index with a formal cash lunch halt + deep futures trading through it), yet the edge is absent:
- **Phase-0b C1 control (lesson #72, binding): delta +0.27 < +0.40** — lunch-window fade zero-cost Sh vs
  off-session (06-12 UTC) fade. Not lunch-specific.
- **dir-gap +0.00** (fade −0.03 = cont −0.03) → signal-absent (lesson #26), not friction-eaten.
- All regimes flat (W1 −0.11 / W2 −0.08 / W3 holdout +0.05); no exit-window or threshold cell clears +0.10.

## Mechanistic finding (the value of this REJECT)
A **formal cash halt is the OPPOSITE of what lunch-fade needs.** `lunch_fade` (NDX, deployed) works because
during the US lunch BOTH cash and futures trade but liquidity thins, so cash/futures basis-arb HFT inventory
mean-reverts in the vacuum (lessons #8/#27). During the TSE lunch (11:30-12:30 JST) the **cash is halted**
while Nikkei futures (which the CFD tracks) trade with full OSE/SGX liquidity — there is no basis to compress
and no thin continuous-trading vacuum to revert. The halt removes the arb leg rather than creating a
mean-reverting lull. **Refines lessons #8/#27**: the lunch-fade prerequisite is a *continuous-trading lunch
lull where both legs trade thin*, NOT merely "the venue has a lunch." Formal-halt indices are pre-tombstoned
for the basis-arb-fade mechanism. (Every prior transplant — fdax/fx/single_stock — failed for *no lunch*;
this one fails for *the wrong kind of lunch*, completing the enumeration.)

## Note
JPN225 M5 (2005-2026) is now on disk + injected to the datalake. The obvious remaining JPN225 idea is a
Nikkei cash-open ORB (TSE Itayose single-venue auction + retail-momentum tape = the most DAX-like of the
untested indices) — but ORB is 0-for-6 outside DAX, so it needs the lesson-#72 C1 control gate first.

## Files
- [jpn225_lunch_fade_screen.py](jpn225_lunch_fade_screen.py) — screen (lunch_fade transplant + C1 control)
