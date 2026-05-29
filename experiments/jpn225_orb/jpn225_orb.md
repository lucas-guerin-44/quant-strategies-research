# Nikkei (JPN225) cash-open ORB — REJECT at C1 gate

**Status**: Phase-0b C1 gate only (lesson #72), 2026-05-28. **REJECT — not built past the gate.**
**Verdict**: **REJECT.** ORB on the TSE cash open (00:00 UTC) shows real opening-momentum directional
content — in-session continuation zero-cost Sh **+0.52**, **dir-gap +1.04** (CONT vs FADE), holdout W3H
+0.68 — making JPN225 the **first non-DAX index with genuine opening-impulse momentum** (FTSE/ASX had
none). BUT the off-session (06:00 UTC) control also runs CONT Sh **+0.24**, so the **C1 delta is +0.28
< +0.40** (lesson-#72 gate). The momentum is **all-session, not TSE-open-specific** — the Itayose auction
does not add the edge Xetra's open does for DAX. Gap-aware fills applied (only 4% gap-through, so the +0.52
is not phantom — lesson #81); cost would erode the residual.

## Why it's a REJECT (and a sharper one than ASX/FTSE)
ORB is now **0-for-7 outside DAX**. But the failure mode differs: FTSE/ASX failed for *no opening-impulse
at all*; JPN225 has the impulse (retail-momentum tape confirmed, dir-gap +1.04) but it is **not anchored to
the open** — generic intraday momentum that exists off-session too. Pursuing the residual would be a
generic-intraday-momentum thesis, which is arbed and cost-bound (lesson #24, zero-cost only +0.52
all-session). DAX remains unique: single-venue auction AND open-anchored impulse. The C1 gate (lesson #72)
did its job — one run, no wasted full simulator.

## The residual all-session momentum — cost-applied (what it's worth)
The C1 reject left a real byproduct: JPN225 has genuine **all-session** intraday continuation (zero-cost
in-session +0.52, off-session +0.24, dir-gap +1.04) — the first non-DAX index where generic intraday
momentum isn't arbed to ~0 (cf. every US-index generic-momentum REJECT, lesson #24). Nikkei is a
more-trending, less-HFT-arbed (retail-heavy Asian) tape. **But it is cost-bound at retail** (lesson #26
edge-eaten-by-friction): per-trade gross +2.30 bp vs 70 bp std →
- cost 0.0 bp: ann-Sh **+0.52**
- cost 1.3 bp (~5pt Raw, default): **+0.23** (below +0.30 bar)
- cost 2.6 bp: **−0.07** ; cost 5.0 bp: −0.61

**Not a standalone retail strategy.** Two legitimate uses of the *characterization* (not a strategy):
1. **Instrument-selection hint** — JPN225 is empirically the best momentum vehicle of the tested indices;
   prefer it if a *new* momentum mechanism needs a vehicle (low value inside the existing `tsmom`/`xs_momentum`
   cluster, ρ +0.69).
2. **Institutional-execution-tier flag (lesson #45)** — like `fx_session`, re-runnable at sub-1bp PB
   execution (~+0.4 net), dead at retail. File institutional-only, do not tombstone-and-forget.

## Files
- [jpn225_orb_c1_gate.py](jpn225_orb_c1_gate.py) — C1 control gate + cost-applied economics (gap-aware, lesson #81)
