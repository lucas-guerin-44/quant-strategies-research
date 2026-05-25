# Cross-asset M5 lead-lag

**Status**: Phase 0 ran 2026-05-22 — REJECT at Phase 0 gate.

**Verdict**: REJECT (Phase 0 fail — no pair clears |corr| > 0.10).

## Verdict summary (2026-05-22)

Phase 0 computed 1400 (pair, lag) correlations across 5 leaders × ~29 followers × 10 lags. **Strongest |corr| in the entire matrix is 0.0505** (USOUSD → GER40 at lag=2). Pre-committed gate: at least one pair with lag-1 |corr| > 0.10 AND asymmetry > 0.02. **Neither condition is met for any pair.**

Top asymmetry table:

| leader | follower | +lag | +corr | -lag | -corr | asymm | n |
|---|---|---|---|---|---|---|---|
| USOUSD | GER40 | 2 | -0.0505 | -3 | -0.0155 | +0.0349 | 38,419 |
| USOUSD | SPX500 | 5 | -0.0256 | -2 | -0.0071 | +0.0185 | 44,225 |
| USOUSD | BAC | 3 | +0.0248 | -2 | -0.0105 | +0.0142 | 13,420 |
| USOUSD | NDX100 | 5 | -0.0179 | -2 | -0.0064 | +0.0116 | 44,224 |
| NDX100 | NVDA | 1 | -0.0161 | -2 | -0.0055 | +0.0106 | 87,470 |
| SPX500 | NVDA | 1 | -0.0192 | -1 | +0.0089 | +0.0103 | 87,432 |

Even the strongest "lead" correlation (USOUSD → GER40 lag=2) at -0.05 means oil's prior 10 min explains < 0.3% of GER40's next-bar variance — well below any tradeable threshold after 4 bp RT cost.

## Mechanistic interpretation — why M5 lead-lag is dead

Phase 0 confirms the "Why this might fail" red flag #1 verbatim: **HFT closes cross-asset lead-lag within seconds**. By the time an M5 bar closes, basket-arb and stat-arb desks have already propagated leader moves into followers. The residual correlation at lag ≥ 1 bar is indistinguishable from noise.

Notable patterns in the noise:

1. **USOUSD → equity index sign-flip**: every USOUSD-leader correlation against an equity follower (GER40, SPX500, NDX100, META, UNH, GS, AVGO, ORCL) is **negative** at the chosen +lag. Direction is "oil up → equities down N bars later". This is a weak risk-off contagion signature, not a tradeable basket-arb lag. And -0.05 isn't enough edge to clear 4 bp.

2. **Index → constituent**: NDX100 → NVDA at lag 1 is -0.016. SPX500 → NVDA at lag 1 is -0.019. If basket-arb worked at M5 horizon, these would be positive at lag 0-1; instead they're slightly negative — consistent with overshoot/mean-revert noise, not lead-lag.

3. **Index → cross-index** (NDX100 → GER40, SPX500 → GER40 at lag 1): +0.011 / +0.011 with n = 282K bars. Statistically distinguishable from zero, but |corr| is 9× below the gate. Time-zone overlap (US open vs EU late-session) explains the residual; not a strategy.

4. **All same-direction lead correlations are below noise**: highest forward-lag |corr| from any (NDX-leader or SPX-leader) → equity-name pair is 0.019. Equity-name basket-arb is closed at sub-M5 frequencies.

Phase 2 is **not run** because no pair clears Phase 0. This is the correct stop — running a strategy on a -0.05 correlation would be parameter-search on noise.

## Lessons for the family

- **"Leader-confirmation cross-asset M5 lead-lag" is now empirically rejected.** Add to the priors: M5 is too slow a frequency for any cross-asset propagation. Sub-minute (M1) might show transient lead-lag, but M5 is irreversibly post-arb.
- **Where a residual signal exists, it's negative cross-asset risk-off (oil up → US/EU equities down)**, magnitude ~ -0.05. Not tradeable as a direct lead-lag, but worth noting for risk-overlay use (e.g., a portfolio-level oil-spike de-risk filter — separate research path).
- **The pre-committed Phase 0 gate did exactly what it was designed to do**: stopped a 120-pair multiple-testing fishing expedition before it could pick a spurious 0.025-corr pair and over-fit a strategy to it.

---

## Original thesis (preserved below)

---

## Thesis

Identify pairs where one M5 instrument's return systematically predicts another's next-N-bar return, then trade the predicted direction. This is **leader-confirmation**, not laggard-mean-revert (the latter has been rejected multiple times: dax_us_lead, fx_safe_haven, etc.).

Mechanism families with ex-ante prediction:
1. **Commodity → equity sector**: USOUSD (oil futures) leads CVX/XOM (pure-play energy stocks). Oil futures move on supply/demand news; energy-stock prices follow with ~5-30 min lag because equity arb desks are slower than commodity desks.
2. **Index → constituent**: NDX100 leads NVDA/AAPL/MSFT/etc. via basket-arbitrage HFT. The constituent prices recompose the basket within seconds, but at the **outlier-magnitude** level (NDX moves > 0.5% in 30 min), individual-name reactions can lag if the move is initiated by the index futures (NQ) and propagates through cash.
3. **DXY-proxy → gold / FX**: we don't have DXY M5 directly; using USDJPY_H1 / EURUSD_D1 as a proxy isn't M5-frequency-compatible. Skip in Phase 0.

## Universe (instruments with M5 on disk)

Leaders to test: USOUSD (oil), NDX100, SPX500, GER40, BTCUSD.

Followers to test: 24 single-stocks (AAPL ... AVGO), plus the leader cross-correlations (NDX100 vs SPX500, etc.).

## Phase 0 — correlation hunt

For each (leader, follower) pair, compute the correlation matrix:
```
corr(leader_M5_return[t], follower_M5_return[t + lag])  for lag in {-3, -2, -1, 0, 1, 2, 3, 5, 10, 20}
```

Identify pairs with:
- Significant lead correlation (lag > 0 where leader → follower) e.g., > 0.10 absolute
- Asymmetry — corr(L[t], F[t+1]) > corr(L[t+1], F[t]) → genuine lead-lag

## Signal math (Phase 2, after Phase 0 selects leaders)

Generic form:
```
For top pair (leader, follower):
  At each M5 bar t:
    leader_30min_return = leader.close[t] / leader.close[t-6] - 1  # 30 min = 6 bars
    if |leader_30min_return| < THRESHOLD:  # e.g., 0.3 × leader's daily ATR
      skip
    position = sign(leader_30min_return)
    enter follower at follower.open[t+1]
    exit follower at follower.close[t+HOLD_BARS]  # e.g., 6 bars = 30 min
    cost = 4 bps RT
```

## Fail conditions (pre-committed)

### Phase 0
- ≥ 1 pair with lag-1 correlation > 0.10 AND clear asymmetry (lag-1 > -lag-1).

### Phase 2 (per top pair found in Phase 0)
- Sharpe > +0.30 after 4 bp RT cost.
- Direction null-gap ≥ +0.30.
- Trades ≥ 200.
- MDD < 25%.

### Phase 4
- All 3 regimes positive.

### Phase 6
- Holdout > 0.

## Why this might fail

1. **HFT closes lead-lag within seconds**. M5 (5-minute bars) is too slow to capture the actual lead-lag; the M5 close has already reflected the leader. Best-case finding will be at lag = 0 (contemporaneous), which isn't tradeable.
2. **Direction-conditional auto-correlation** — if NDX moves 0.5% in 30 min, NVDA usually has also moved similarly contemporaneously, and the "lag-1" auto-correlation is just trend persistence.
3. **Volume / liquidity confounds** — outlier moves often happen on news that hits both leader and follower simultaneously. The "lag" is a function of which exchange's matching engine processed faster, not real lead.
4. **Multiple-testing risk** — 5 leaders × 24+ followers = 120+ pairs. Even with no real signal, ~6 pairs will show p < 0.05 by chance. Phase 2 walk-forward is the binding gate.

## Files

- Thesis: this file.
- Phase 0 + Phase 2 demo: `cross_asset_lead_lag_demo.py`
