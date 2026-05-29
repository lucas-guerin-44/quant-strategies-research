# Crypto perp funding-rate fade — short-biased (BTC primary / ETH cross-check)

**Status**: Phase 2 complete (2026-05-28). Vessel = **Eightcap BTCUSD CFD proxy** (exchange funding as signal, CFD bars as trade). ETH on perp price = cross-instrument robustness only.

**Verdict**: **REJECT (2/8 binding criteria).** The fade *direction* is decisively real (fade-gap +1.22 BTC-CFD / +2.09 BTC-perp / +1.48 ETH — the inverse loses −1.5 to −2.0 Sh), but the edge is (a) **negative in the 2023-2026 holdout** (W3 −0.79), (b) **tiny and friction-eaten** (cost-zero ≈ +0.35 → −0.33 at 10 bp → −1.27 at 20 bp), and (c) **not actually short-biased** (50% short — z-vs-rolling-mean neutralised the structural tilt). A correctly-signed mechanism that has been institutionalised to zero post-2022. Tombstone; keep for the directional finding + the methodological lessons.

---

## Thesis (mechanism)

Perpetual swaps have no expiry, so the **funding rate** is the mechanism that tethers the perp price to spot: when the perp trades at a premium (more aggressive longs than shorts), longs periodically pay shorts; at a discount, shorts pay longs. Funding settles every 8h (00:00 / 08:00 / 16:00 UTC). The directional content comes from four mechanistic points:

1. **Funding is a real-time crowding gauge.** A large positive funding rate means leveraged longs are paying up to hold the position — i.e. positioning is crowded long. Crowded leverage is fragile: it is the fuel for long-liquidation cascades.
2. **Structural long bias of retail leverage** → funding is *positive the large majority of the time*. So a rule that "shorts when funding-z is extreme-high" fires far more often than its long counterpart, making the strategy **structurally short-biased without imposing a short-only constraint** — it earns its short tilt from the data, not from a hand-set switch.
3. **Mean-reversion of extreme funding.** Funding spikes precede either (a) a basis-arb unwind (cash-and-carry desks short the perp to collect funding, pressing price down) or (b) a long-liquidation flush. Both push price down over the subsequent intervals — the fade direction.
4. **Carry-as-decay on a CFD.** On the actual perp the edge can be *collected* as funding; on a CFD you cannot receive funding, but the same over-leverage resolves as **price decay**, which a short position captures directly. (This is the form-2 reframing — see §Forms.)

Effect is expected to have compressed as cash-and-carry basis desks and funding-arb bots have grown post-2021; the holdout window (2023-2026) is the binding test.

## Key reference

- **Hutchison & Smith / BitMEX research notes on funding-rate carry** and the broad "perpetual basis / funding premium" literature (e.g. *Funding Rates and the Perpetual Futures Basis*, 2021-2023 crypto-microstructure working papers). The directional-fade variant is closest to the **crowding / liquidation-cascade** literature (e.g. analyses of Binance/Bybit liquidation clusters vs funding extremes).
- Methodologically anchored on this repo's own [orb.md](../_live/orb/orb.md) (pre-committed kills, symmetric null-check, 3-regime split) and [btc_intraday](../btc_intraday/btc_intraday.md) (8h-grid numpy simulator, crypto cost model).

## Signal math

```
Grid: 8h funding settlements t = 00:00 / 08:00 / 16:00 UTC.
Inputs at t: funding_rate[t], price open[t] (CFD-proxy or perp).

  fund_z[t] = (funding_rate[t] - rollmean(funding_rate, LB)) / rollstd(funding_rate, LB)
              LB = 90 intervals (~30 days), computed on data up to t.

Form 1 — DIRECTIONAL FADE (discrete):
  if fund_z[t] > +THR:  SHORT  for HOLD intervals
  if fund_z[t] < -THR:  LONG   for HOLD intervals
  THR = 1.0, HOLD = 1 interval (8h) baseline.

Form 2 — FUNDING-PROPORTIONAL (continuous):
  target_position[t] = -clip(fund_z[t], -C, +C) / C    # in [-1, +1]
  rebalanced every interval; structurally net-short because E[fund_z] > 0.

No-lookahead rule: fund_z[t] uses funding settled at t; ENTER at open[t+1]
(next interval). A contemporaneous-entry variant (open[t]) is reported as a
labelled OPTIMISTIC diagnostic only.

Cost: bps round-trip (per [feedback_bps_cost_methodology]). Baseline 10 bps RT.
```

## Why retail-accessible

Perps are the most retail-accessible leveraged instrument in existence; funding history is free/public (Binance `/fapi/v1/fundingRate`). Deploy vessel here is the **Eightcap BTCUSD CFD** (the live platform), with exchange funding pulled as a daily/8h signal feed. Short-side crypto CFD swap is frequently *positive* (you receive) at retail brokers — a potential tailwind for a short-biased book, modelled conservatively as a cost here.

## Universe

- **Primary (deploy candidate)**: BTCUSD — signal from Binance BTCUSDT funding, trade on Eightcap `BTCUSD_M5.csv` resampled to the 8h grid (2019-09 → 2026-05).
- **Cross-check (robustness, NOT deploy)**: ETHUSDT on Binance perp price (no intraday ETH CFD bars on disk; MT5 fetch deferred to post-PASS). Also BTC on perp price as the mechanism-clean read vs the CFD-proxy.

## Expected performance (at thesis time)

Funding-fade / liquidation-cascade studies report Sharpe ~0.5-1.2 gross on the clean perp; heavy compression expected on a CFD vessel with retail spread. Point estimate: **net Sharpe +0.3-0.7, 100-250 trades/yr (form 1 at THR=1.0), short fraction 60-75%, MDD 10-20%.** Form 2 expected lower turnover-adjusted Sharpe but smoother. Live target after 10-25% haircut: +0.2-0.5.

## Fail conditions (pre-committed) — locked BEFORE the run

Phase 2 **REJECT** if ANY of the binding criteria fail (BTC CFD-proxy, baseline config):

| # | Criterion | Threshold |
|---|---|---|
| 1 | Full-period net Sharpe (10 bps RT) | > +0.30 |
| 2 | Max drawdown | < 25% (MDD > −25%) |
| 3 | Trade count over window | ≥ 200 |
| 4 | **Direction null-check fade-gap** (fade Sh − inverse-direction Sh) | **> +0.30** |
| 5 | Holdout 2023-2026 Sharpe | > 0 |
| 6 | Regime windows positive | ≥ 2 of 3 (2019-20 / 21-22 / 23-26) |
| 7 | Cost-robustness: net Sharpe at 20 bps RT | > 0 |
| 8 | **Short-bias realised** (short fraction of trades) | > 55% |

Criterion 4 is the load-bearing one (per CLAUDE.md §6): if the inverse direction (LONG-on-high-funding) also wins, there is a structural confound in the cost/exit model, not a real crowding edge. Criterion 8 enforces the user's short-bias requirement — if the data-earned tilt isn't actually short, that's a thesis-falsification, not a free pass.

## Why this might fail (red flags)

1. **Funding-arb is institutionalised.** Cash-and-carry desks may have already compressed the fade to zero post-2021 → holdout (criterion 5) is where this shows.
2. **8h-delayed no-lookahead entry** may miss the move — the crowded position can unwind within the same interval the funding prints.
3. **CFD ≠ perp.** The signal is exchange funding; the trade is a CFD that tracks spot, not the perp basis. Tracking error + spread could eat the edge (the whole point of the CFD-proxy vessel choice — measure it honestly).
4. **Short-into-parabola tail.** A structurally short book gets run over in a melt-up (2020-Q4, 2023-2024). Regime split + MDD criterion guard this.
5. **Funding regime non-stationarity.** Binance changed funding caps/intervals over time; early-2019 data may be a different mechanism.

## Phase 1 → 2 plan

- [x] Fetch Binance funding + 8h klines (BTC, ETH) — `scripts/binance_funding_fetch.py`.
- [ ] Build numpy simulator (both forms, both vessels, null-check, regime, cost sweep, short-fraction).
- [ ] Run baseline + THR sweep + HOLD sweep + null-check + regime + cost + ETH cross-check in one pass.
- [ ] Verdict + mechanistic interpretation; update STATE.md YAML block + RESEARCH_NOTES if a cross-experiment pattern emerges.

## Phase 2 results (2026-05-28)

Data: BTC funding+price 2019-09→2026-05 (6,775 z-finite 8h bars), ETH 2019-11→2026-05. No-lookahead entry (open[t+1]), 10 bps RT baseline.

### Form 1 — directional fade (baseline THR=1.0, HOLD=1×8h)

| Vessel | n | net Sh | MDD | short% | mean/trade |
|---|---|---|---|---|---|
| BTC_CFD (primary) | 1944 | **−0.33** | −69.7% | 50% | −0.035% |
| BTC_PERP (clean) | 2097 | +0.08 | −65.8% | 49% | +0.009% |
| ETH_PERP (x-check) | 1958 | +0.01 | −71.1% | 51% | +0.002% |

### Null check — inverse direction (long-on-high-funding)

| Vessel | null Sh | MDD | **fade-gap** |
|---|---|---|---|
| BTC_CFD | −1.55 | −97.3% | **+1.22** |
| BTC_PERP | −2.01 | −99.2% | **+2.09** |
| ETH_PERP | −1.47 | −99.2% | **+1.48** |

The inverse is a catastrophe in every vessel → **the fade direction carries genuine, decisive directional content.** This is the one unambiguous win.

### Regime breakdown — BTC_CFD (the binding test)

| Window | n | Sh | mean | note |
|---|---|---|---|---|
| W1 2019-2020 | 184 | −0.14 | −0.027% | flat/negative |
| W2 2021-2022 | 548 | **+0.33** | +0.045% | the only positive regime |
| W3 2023-2026 HOLDOUT | 1209 | **−0.79** | −0.059% | **decayed/inverted** |

BTC_PERP mirrors it (W1 +0.46 / W2 +0.94 / **W3 −0.85**). ETH_PERP is noisier (W1 −1.25 / W2 −0.20 / W3 +0.58) — no coherent cross-instrument regime story. **The edge lived in the 2021-2022 leverage-cycle and is gone in the holdout.**

### Threshold / hold / cost sweeps (BTC_CFD)

- THR sweep: 0.5 → −0.48, 0.75 → −0.22, 1.0 → −0.33, 1.5 → +0.33, **2.0 → +0.34** (but only 67 trades/yr, MDD −26.9%). Higher THR "rescues" full-sample Sharpe — classic select-the-best-cell overfit; the holdout stays negative regardless, so not pursued (CLAUDE.md "don't aggregate the best variant as the strategy").
- HOLD sweep: 8h −0.33 → 48h +0.20, all sub-bar, MDD worsens monotonically to −90%.
- Cost: 4 bp +0.23 / 10 bp −0.33 / 20 bp −1.27 / 40 bp −3.14. **Cost-zero ≈ +0.35** → a tiny real gross edge linearly eaten by spread (lesson #6 diagnostic: real-but-tiny edge, not signal-absent).

### Form 2 — funding-proportional continuous

BTC_CFD Sh −0.09 (W1 −0.33 / W2 **+0.85** / W3 −0.65), BTC_PERP +0.17, ETH +0.02. Same regime shape: only 2021-2022 positive. Net-short ~51% (avg position ≈ −0.004 — barely net short, confirming the z-vs-mean neutralisation). No improvement over form 1.

### Kill-criteria scorecard

| # | Criterion | Result | |
|---|---|---|---|
| 1 | Full net Sh > +0.30 | −0.33 | FAIL |
| 2 | MDD > −25% | −69.7% | FAIL |
| 3 | Trades ≥ 200 | 1944 | PASS |
| 4 | Fade-gap > +0.30 | +1.22 | **PASS** |
| 5 | Holdout Sh > 0 | −0.79 | FAIL |
| 6 | ≥2/3 regimes + | 1/3 | FAIL |
| 7 | Sh @20bp > 0 | −1.27 | FAIL |
| 8 | Short fraction > 55% | 50% | FAIL |

## Mechanistic interpretation (why REJECT)

1. **The mechanism is correctly signed — funding extremes are a real crowding gauge.** The +1.2 to +2.1 fade-gap and the −1.5 to −2.0 inverse-direction Sharpe are unambiguous: leaning *against* crowded-long funding is the right direction. This is not a noise strategy (contrast SPX500 ORB, where both directions lost identically).

2. **It has been institutionalised to ~zero post-2022 — red flag #1 fired exactly.** Positive only in the 2021-2022 leverage cycle (BTC W2 +0.33 CFD / +0.94 perp), negative in the 2023-2026 holdout on both BTC vessels. Cash-and-carry basis desks and funding-arb bots grew enormously after 2021; they now compress the funding premium and front-run the liquidation-cascade fade. Same post-2022-decay shape as the 0DTE-MR family (lessons #43, #-5/#-9), arrived at via a completely different mechanism — **funding-arb is the crypto analogue of equity 0DTE-gamma institutionalisation.**

3. **What gross edge remains is below the cost floor.** Cost-zero ≈ +0.35; the CFD spread (10 bp RT) flips it negative. Even on the clean perp it is only +0.08. This is a friction-eaten tiny edge (lesson #6), not a friction-free winner.

4. **The "structural short bias" did not materialise — and the reason is a methodological catch.** Short fraction was 50%, not >55%, because z-scoring funding against its *own rolling 30-day mean* removes the unconditional positive bias that was supposed to create the short tilt. To earn a short bias you must threshold on **absolute funding level / z-vs-zero**, not z-vs-rolling-mean. BUT an absolute-level short would bleed *worse* in the 2023-2024 melt-up (short-into-parabola, red flag #4), so the z-design is not the load-bearing failure — the holdout decay is. Recorded as a lesson, not pursued as a rescue (would be goalpost-moving).

5. **MDD bar mis-calibrated for crypto (caveat, not load-bearing).** The −70% MDD is on full-notional, unsized, overlapping 8h trades; a 15%-vol-targeted curve (à la btc_trend) would scale it well under 25%. But Sharpe is bet-size-invariant and fails the holdout, so sizing cannot rescue the verdict. **Future crypto theses should apply the 25% MDD bar to a vol-targeted equity curve, not raw notional.**

**Forward options (not pursued now):** the decisive directional content means funding-z is plausibly useful as a *filter/overlay* on another crypto signal rather than a standalone, or on a fresher/less-arbed venue (alt-perps, Bybit) — but any such follow-up must pre-commit the holdout as binding, because the standalone fade is dead in the current regime.

## Files

- Thesis: this file.
- Demo: `experiments/crypto_funding_fade/crypto_funding_fade_demo.py`.
- Data: `ohlc_data/{BTCUSDT,ETHUSDT}_FUNDING.csv`, `ohlc_data/{BTCUSDT,ETHUSDT}_PERP_8H.csv`, `ohlc_data/BTCUSD_M5.csv` (CFD vessel).
- Fetcher: `scripts/binance_funding_fetch.py`.
