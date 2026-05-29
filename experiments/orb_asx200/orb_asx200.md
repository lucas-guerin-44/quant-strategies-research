# ORB on ASX200 — REJECT (one-window-wonder; ORB still DAX-specific)

**Status**: Phase 0/1 screen via `orb_demo.py` (ORB_SYMBOL=ASX200 ORB_SESSION=AU), 2026-05-28. **REJECT.**
**Verdict**: **REJECT.** ASX200 is single-venue (ASX) + retail-heavy — the structural profile that *might*
have given it DAX-like opening-impulse momentum. It doesn't: baseline Sh **+0.04** (MDD −26.4%, fails),
and the regime split is a textbook one-window-wonder — W1 2019-20 Sh **+1.37**, W2 2021-22 **−0.68**,
**holdout W3H −0.62**. The edge was entirely pre-COVID. tight+trend variant holdout also negative (−0.87).

## Why it failed
ASX200 is commodities/financials-heavy, the same reason `orb_uk100` (FTSE) REJECTED ("no opening-impulse").
**ORB is now REJECT on SPX500, NDX100, UK100, EUSTX50, FRA40, ASX200 — DAX/GER40 is the lone survivor.**
Confirms lesson #71/#19: ORB needs BOTH a literal single-venue cash auction AND a momentum-prone
opening-impulse tape; single-venue alone is insufficient, and DAX's clean 3h opening-impulse is venue-specific.
Pre-tombstone further ORB instrument-ports without a Phase-0b in-session-vs-off-session control clearing +0.40.

## Files
- run log: `runs/orb_asx200.log` (reuses the deployed `experiments/_live/orb/orb_demo.py`)
