# In-game odds swing trading: math & ruleset

v0.1 · 2026-10-22 · $1,000 paper bankroll (`grok-paper-trading`). Odds are decimal here; the two-sided `1.73 : 2.89` format comes in a later round.

**TL;DR.** Your edge, if there is one, is a *mean-reverting overreaction* after turnovers. Measure it: fair win prob from a model vs price. Trade only when price is below fair by more than fees + slippage; size at ≤¼ Kelly; cap adds at 2; a sell-and-rebuy changes exposure, never EV.

## 1. Conversions
- Implied probability / Novig price: `q = 1/d` (d = decimal odds). Contract pays $1 if the team wins.
- Decimal odds from price: `d = 1/q`. Payout per $1 staked = d; profit = d − 1.
- Two-sided book: `q_A + q_B = 1 + v` (v = overround/vig). Devig: `q̂_A = q_A / (q_A + q_B)`. On an exchange, the spread (best ask − best bid) plus per-fill fees is your vig.
- Contracts bought with stake S at price q: `n = S/q`. Position value at price q': `n·q'`.

| Decimal | Price q | Profit per $1 if wins |
|---|---|---|
| 2.00 | 0.500 | 1.00 |
| 3.50 | 0.286 | 2.50 |
| 5.20 | 0.192 | 4.20 |
| 5.38 | 0.186 | 4.38 |
| 7.00 | 0.143 | 6.00 |
| 7.30 | 0.137 | 6.30 |
| 10.30 | 0.097 | 9.30 |
| 19.00 | 0.053 | 18.00 |

Note: odds are nonlinear. 3.5→5.38 is −0.100 in probability; 7.3→19 is only −0.084. Think and set stops in **probability (price) ticks**, not odds.

## 2. Expected value
Your probability p, buy price q (incl. fees f per contract):
- EV per contract to settlement: `EV = p − q − f`. EV per $ staked: `p/q − 1`.
- Edge threshold: trade only if `p − q > f + slippage + model error margin ε` (start ε = 0.03).
- Example: price 5.38 (q=0.186), your p = 0.25 → EV/contract +0.064, +34% on stake. If p = 0.19, EV ≈ 0 before fees → no trade.

## 3. Estimating your own p in-game
1. **Prior:** pregame spread → win prob. NFL: `p₀ ≈ Φ(−spread/13.45)` (spread for the team, negative = favored; σ≈13.45 pts). Or Elo: `p₀ = 1/(1+10^(−ΔElo/400))`.
2. **In-game model** (nflfastR-style logistic / GAM): `logit p = β₀ + β₁·scoreDiff + β₂·scoreDiff/√(secondsLeft+1) + β₃·spreadPrior·(secondsLeft/3600) + β₄·yardline + β₅·down + β₆·ydsToGo + β₇·possession + β₈·timeouts`. Use `nflfastR` `wp` / `vegas_wp` columns as an off-the-shelf fair value (play-by-play, free, 1999–present). College: `cfbfastR`.
3. **Event impact:** `ΔWP_fair = WP(after play) − WP(before play)` from the model. A turnover in midfield in Q2 is typically −0.10 to −0.20 WP; near own red zone late, more.
4. **Calibration:** Brier score `B = (1/N)Σ(p_i − y_i)²`. Bin predictions in deciles; plot predicted vs realized. Compare your p's Brier against the market's (q̂). If yours isn't lower on ≥100 games, use the model/market, not your gut.

## 3b. Pregame prior adjustments

Work in **points of expected margin** M for your team (positive = favored), then convert. "(est.)" marks a rule-of-thumb or single-source estimate rather than a settled number. The market already prices most of these, so they only give you an edge when news is late or the market misreads it.

**Additive formula**
```
M = R_team − R_opp            # rating diff (power rating, or market spread with sign flipped)
  + HFA                       # +if home, −if away, 0 neutral
  + QB_adj + Σ nonQB_adj      # starter → backup losses (negative for your team, positive if the opponent's are out)
  + rest_adj + travel_adj + tz_adj + weather_adj
spread = −M ;  p₀ = Φ(M / 13.45) = Φ(−spread / 13.45)
```
Elo ↔ points: 538 used about 25 Elo ≈ 1 pt, so an Elo tweak ΔE ≈ ΔE/25 pts.

| Factor | Default (NFL) | Notes / source |
|---|---|---|
| Home field | +1.5 to 2.0 pts (est.); about half that in divisional games | nfelo: HFA declined to about 2.5 pts over 2000s–2010s and is lower now; divisional familiarity cuts it about 50%. 538: about 48 Elo (≈1.9 pt). https://www.nfeloapp.com/analysis/a-further-exploration-of-home-field-advantage-in-the-nfl/ · https://fivethirtyeight.com/methodology/how-our-nfl-predictions-work/ |
| Home field, college | +2.5 to 4 pts (est., wide) | Surveys put recent FBS HFA at about 2.4 pts; older studies say about 4 to 5. Big crowds and long travel make it larger. https://www.degruyterbrill.com/document/doi/10.1515/jqas-2024-0016/html · https://www.tandfonline.com/doi/full/10.1080/24733938.2018.1524581 |
| Starting QB out | −1 to −7 pts; median NFL starter about −4 | 2026 oddsmaker panel: avg 4.09 over backup (Allen 7.23, Mahomes 6.32 … Tua 1.02). https://www.bookmakersreview.com/industry/nfl-qb-point-spread-value-rankings-josh-allen-no-1/ · https://sports.yahoo.com/nfl/betting/article/oddsmakers-rank-all-32-nfl-starting-qbs-by-point-spread-value-josh-allen-is-the-clear-no-1-130725555.html |
| Non-QB star | 0 to −2 pts; most players about 0 to −0.5 | Only a few skill players move lines; the top TE was 1.83 pts in a past panel. Treat OL/CB clusters (several starters out) as −1 to −2 (est.). PFF WAR is a cross-check. https://bfawkes22.substack.com/p/ranking-the-top-10-nfl-qbs-by-point |
| Bye / extra rest | +0.5 to 1 pt (est.), worth more to the away team | 538: +25 Elo ≈ 1 pt. nfelo: the home-team bye edge has faded; byes help visitors more. |
| Short week (Thu after Mon) | −0.5 to −1.5 pts for the short-rested team (est.) | Rest-differential rule of thumb is about 0.15 pt per day (secondary source). https://datafield.dev/nfl-football-analytics/appendices/appendix-e-formula-reference.html |
| Travel distance | −0.16 pt per 1,000 mi for the traveler | 538: 4 Elo per 1,000 mi. |
| West team, 1 pm ET kickoff | Raw about −4.5 pts vs ratings, but about 0 vs the spread since 2012 | Already priced, so don't add it on top of a market prior. https://edgedesksports.com/research/environment/travel-circadian/ (single source). Night games historically favored West Coast teams: https://pmc.ncbi.nlm.nih.gov/articles/PMC3825451/ |
| Altitude (DEN) | About 0 beyond normal HFA | No significant elevation effect in 2020–24 data (single source, low confidence). https://regression.thestochasticparrot.com/runs/552-altitude-home-field-advantage/ |
| Weather | Mostly moves totals, not sides; about 0 to ±1 pt to the side | Wind hurts passing (10 mph ≈ −6.8% pass yds); heat, wind and rain lower scoring. Use it mainly as a lower total, which pulls the underdog's p toward 0.5. 538 found weather didn't improve its model. https://scholarship.claremont.edu/cgi/viewcontent.cgi?article=1982&context=cmc_theses · https://www.tandfonline.com/doi/abs/10.1080/09603100701335432 |
| Back-to-back road games | 0 to −0.5 pt (est.) | No strong published effect; post-trip "hangover" was about 0 vs the spread (edgedesk). Treat it as noise unless it combines with a short week. |

Don't double count. If your base is the market spread, only add what the market hasn't priced yet (late QB news, a weather change). Rest, travel and time zones are already in the line.

**In-game, the prior fades.** A simple Brownian margin model with t = seconds remaining, s = current score diff for your team, and σ = 13.45:
```
WP(t) ≈ Φ( (s + M·t/3600) / (σ·√(t/3600)) )
```
The pregame edge M scales with time left (t), but the noise only scales with √t, so a pregame adjustment worth Δ pts moves WP by about φ(·)·Δ·√(t/3600)/σ. At halftime its effect is about 0.71×, in Q4 with 7:30 left it's about 0.35×, and it's 0 at the end. nflfastR's `vegas_wp` applies this time decay to the spread.

**Worked example** (NFL, Thursday). Your team A is home; the market opened A −3 before QB news. B played Monday, so B is on the short week, and this is B's second straight road game. A's starter (worth 4.1 pts) is ruled out Wednesday night.
- M = 3.0 (rating, from market) + 0 (HFA, already in the line) + 0.5 (B short week, est., partly priced) − 4.1 (A QB) + 0 (back-to-back) = −0.6
- Fair spread A +0.6, so p₀ = Φ(−0.6/13.45) = Φ(−0.045) = 0.482. Before the news: Φ(3.5/13.45) = 0.603. If the market only moved to A −1 (Φ(1/13.45) = 0.530), you have a 0.048 edge on B at kickoff.
- At halftime tied, M = −0.6: WP ≈ Φ(−0.3/(13.45·0.707)) = 0.487. The same −4.1 QB news moves WP about 0.12 at kickoff and about 0.09 at half.

**Pregame checklist**
- [ ] Base M: market spread with sign flipped (or your own rating diff)
- [ ] QB status for both teams → panel value
- [ ] Other starters out: skill stars, OL or secondary clusters
- [ ] Home, away or neutral; divisional game?
- [ ] Rest days for each side; bye; Thursday after Monday
- [ ] Travel miles and time zones; kickoff time on each team's body clock
- [ ] Weather: wind ≥ 15 mph, rain or snow, heat (lowers totals)
- [ ] Back-to-back road (only with a short week)
- [ ] Remove anything the market already priced → p₀ = Φ(M/13.45) → log `my_p_pregame` with the adjustments

## 4. Formalizing the overreaction hypothesis
Define per event e (turnover/fumble/INT), team T:
- `q_pre` = mid price 30 s before event; `q_peak` = extreme within 90 s after; `q_fair` = q_pre + ΔWP_fair (model).
- **Overshoot** `O = q_fair − q_peak` (positive = market too pessimistic).
- **Reversion** at horizon h: `R_h = q(t_peak + h) − q_peak`, h ∈ {2, 5, 10 min game-clock or wall-clock}.
- Hypotheses: H1: E[O] > 0. H2: E[R_h] > 0 and > round-trip cost c (spread + fees). H3: R_h is predicted by O (regress `R_h = a + b·O`, expect b ∈ (0,1]).
- **Data:** Novig candles/trade history per market (see `novig-cheatsheet.md`) + nflfastR play timestamps for event times. Join on game + wall-clock (allow ±20 s).
- **Test:** one-sided t-test on R_h − c, cluster by game (events within a game are correlated). Also a placebo: random timestamps without events should show E[R_h] ≈ 0.
- **Sample size:** n ≈ (z·σ/μ)². If σ(R_h) ≈ 0.06 and true edge μ ≈ 0.015 (1.5¢): n ≈ (1.645·0.06/0.015)² ≈ 43 for 95% one-sided, ~100+ for 80% power at 5%: `n ≈ ((1.645+0.84)σ/μ)² ≈ 99`. Weekly ~4–8 turnovers/game × ~15 games → a few weeks of logging gets you there.
- Kill criteria: if after 100 events E[R_h − c] ≤ 0 or CI includes 0 → no edge; stop sizing up.

## 5. Trading the path
- Break-even exit price after round-trip fee c: `q_be = q_entry + c`.
- Profit in $: `π = n·(q_exit − q_entry) − fees` = `S·(q_exit/q_entry − 1)`. Target $X ⇒ `q_target = q_entry·(1 + X/S)`.
  - S = $20 at 5.38 (q=.186): $20 target needs q_exit = .372 (odds 2.69). $50 target needs q=.651 — rare. Bigger stake or a smaller target.
  - S = $100 at 5.38: +$20 at q=.223 (4.48); +$50 at q=.279 (3.58, ~your 3.5 pre-event price).
- **Trailing stop in price ticks:** stop = max price since entry − k, with k ≈ 1.5× typical noise (std of 1-min price changes during live non-event play; start k = 0.03). Stop never moves down. Activate it once in profit ≥ c.
- **Time stop:** if no reversion within h* (from your test, e.g. 2 drives), exit; the edge has decayed.
- Expected holding outcome (barrier model): with target up u and stop down s in price, and drift μ≈0, `P(hit target first) ≈ s/(u+s)`. Edge only exists if measured reversion makes this higher than s/(u+s).

## 6. Averaging down
Entries (S_i, q_i): `n = Σ S_i/q_i`, avg price `q̄ = ΣS_i / n`, break-even odds `1/q̄`.

Your example, $50 per entry: 5.2, 8, 10.3, 19:
| Entry | Odds | q | Contracts | Cum. cost | Cum. contracts | Avg q | BE odds |
|---|---|---|---|---|---|---|---|
| 1 | 5.2 | 0.192 | 260 | 50 | 260 | 0.192 | 5.2 |
| 2 | 8.0 | 0.125 | 400 | 100 | 660 | 0.152 | 6.6 |
| 3 | 10.3 | 0.097 | 515 | 150 | 1175 | 0.128 | 7.8 |
| 4 | 19.0 | 0.053 | 950 | 200 | 2125 | 0.094 | 10.6 |

If team loses: −$200 (4× the original risk). If wins: +$1,925. Mark-to-market at 7.3: value $291, P&L +$91 — the adds made the bounce to 7.3 profitable, but only because you risked 4×.
- Why it raises ruin risk: risk grows exactly when the market says you're more likely wrong. Losses are correlated (same game).
- Rational only if (a) your fair p is *unchanged* by what moved the price (no new information: crowd panic, not injury/score), (b) p − q now exceeds the threshold, (c) total game exposure stays ≤ cap. Each add is a new trade judged on its own EV.
- Hard cap: max 2 adds, and total game exposure ≤ 5% of bankroll.

### Selling a loss and re-entering
Hold 260 contracts from 5.2 (cost $50); price now 7.3 (q=.137). Value = $35.62.
- A: hold → 260 contracts, value $35.62.
- B: sell (realize −$14.38), rebuy $35.62 at .137 → 260 contracts. Same exposure, same outcome in every future state, minus 2× fees. "Better entry" is bookkeeping: the −$14.38 is real either way (sunk cost).
- It only matters if you **rebuy a different size**: that's a sizing decision (more/less exposure), judged by Kelly on current p and q.

## 7. Sizing
- Kelly for a binary contract at price q, your p: `f* = (p − q)/(1 − q)` (fraction of bankroll to stake).
  - p=.25, q=.186 → f* = 7.9%. Use ¼ Kelly → 2.0% = $20.
  - p=.22, q=.137 (7.3) → f*=9.6%, ¼ → 2.4%.
- Fractional Kelly because p is estimated; ½ Kelly cuts growth ~25% and variance ~75%; ¼ is safe while unproven.
- Caps (min of): ¼ Kelly, 2% bankroll per entry, 5% per game, 3 open games.
- Daily loss limit: 6% ($60). Max drawdown circuit breaker: −15% from peak equity → stop for a week, review journal; −25% → back to paper only / reset.

## 8. Rulebook ($1,000 paper)
1. Only trade events: fumble lost, INT, turnover on downs, blocked kick, big injury? → no (injury is information).
2. Compute fair p (model WP after play). Enter only if `p − q ≥ 0.03 + c`.
3. Stake = min(¼ Kelly, $20). Max game exposure $50. Max 3 games open.
4. Target: exit at q ≥ q_entry + (p − q_entry)·0.7 or at pre-event price, whichever first.
5. Trailing stop 0.03 price below the high since entry, active once ≥ break-even.
6. Time stop: 2 opponent possessions with no reversion → exit.
7. Adds: max 2, each ≥ 0.03 lower in price, each must pass rule 2 on its own, only with no new information.
8. No sell-and-rebuy at the same size. Rebuys are new trades.
9. Daily stop −$60. Drawdown breaker −$150 from peak.
10. Log every trade (§9) before closing the app. Review every 25 trades.

## 9. Journal schema (per fill / trade)
`trade_id, game_id, league, market_id, team, side, event_type, event_play_id, game_clock, quarter, score_diff, possession, yardline, q_pre, q_peak, q_entry, model_wp_before, model_wp_after, my_p, edge(p−q), kelly_f, stake, contracts, add_number, fee, spread_at_entry, exit_reason(target|trail|time|flip|manual), q_exit, exit_time, hold_seconds, pnl, mfe(max favorable), mae(max adverse), settled_result, emotion(1–5), followed_rules(y/n), notes`

Metrics to compute weekly: hit rate, avg R_h, avg pnl/trade with CI, Brier(my_p) vs Brier(market), pnl by event_type, rule-break pnl vs rule-follow pnl.
