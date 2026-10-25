# Decisions log (prototype v0.2, 2026-10-22)
Decisions made autonomously while Michael was at work. Each is easy to reverse.

| # | Decision | Why | Revisit |
|---|---|---|---|
| D1 | **Standalone app**, same `server.py` (port 8601). Prototype at `/`, sampler at `/system.html`, old functional widgets moved to `/functional.html` | Michael suggested standalone; no new deps | merge into tradekit later |
| D2 | **Vanilla JS SPA + hash routing**, no build step, no framework | runs anywhere with `python3 server.py`; matches "fast" goal; components are pure string functions so the sampler reuses them | React/Svelte if it grows past ~3k lines |
| D3 | **Aesthetic**: Swiss editorial base (paper #F4F2EC, ink, red streak); orange = maker/adds/selection; industrial yellow+steel = rules/hype/book depth; hand-drawn art only for icons, mascot, empty states | his ranking: Swiss ≫ Glass ≈ Sportsbook; moodboard white/orange + gray/yellow + hand-drawn | Glass/Sportsbook "skins" via token swap |
| D4 | Light mode only | Swiss reference is light; Novig's dark UI is what he dislikes | dark tokens later |
| D5 | **Red is overloaded on purpose**: LIVE, primary Buy, sell markers, losses. Gains are green | keeps the palette to one accent; buy/sell are disambiguated by ▲/▼ shape and labels | if confusing, move Buy to ink |
| D6 | **Price math**: ask to buy outcome A = 1 − best bid of B (Novig books are two-sided bids). Multiplier = 1/p. Contracts = stake/price×100 (1 contract pays $0.01) | matches Novig contracts in cheatsheet | — |
| D7 | Default price format **Multiplier**, two-sided `2.43 : 1.89`; header chip cycles; Settings radios (Percentage, Precise Percentage) | mirrors Novig | — |
| D8 | **Orders stay dry-run.** The slip previews the exact `POST /v3/orders` body and writes a `source=dryrun` journal entry at the shown price (assumes full fill). Nothing sent | your standing rule; also lets you test the journal now | wire `trading_client().place_order` + real fills behind `NOVIG_ALLOW_PAPER_ORDERS=1` |
| D9 | Quick add/exit (+$1/+$2/+$5, Sell ½/All) fill instantly without a confirm modal (dry-run). Live mode will ask once per session | speed is the main goal | |
| D10 | **Journal storage: SQLite** `data/journal.sqlite` (games, events, ticks, entries) | atomic, queryable for later aggregation | — |
| D11 | Journal **action** inferred: ENTER (first buy), ADD (buy while holding), PARTIAL_EXIT, EXIT, REENTER (buy after flat). Trigger = latest hype event ≤ 4 min before the fill | no typing needed live | tune window |
| D12 | Cost basis = average cost; break-even shown as a multiplier | matches his mental model ("break-even 10.6×") | FIFO option |
| D13 | **Play-by-play source: ESPN public site API** (scoreboard + summary). Verified live today: plays carry `wallclock`, period, clock, scores, plus `winprobability`. nflverse and CollegeFootballData are stubs (same normalized shape) | free, no key, near-real-time, NFL + NCAAF | add CFBD key for college backfill |
| D14 | Event taxonomy (20 types) with a `hype` flag. INT, pick-six, fumbles, sacks, safety, TOD, blocked kick, missed FG, big penalty (TD nullified / ≥15 yds / PI), injury, challenge, TD are hype | his list plus what moves prices | tune after 100 events |
| D15 | Novig ↔ ESPN game matching by team-name overlap + kickoff within 6h | no shared IDs | store a manual override |
| D16 | **Seed data**: 3 real NFL games from Oct 18 (HOU@JAX, CHI@ATL, BAL@CLE) with **real ESPN events**, but **sample price paths** (ESPN win probability + synthetic overreaction that decays, τ≈160s) and **sample trades** from a bot following his playbook (enter $5 after a ≥6-pt drop, add $1–5 on further drops, trailing exit, time stop, 40% "panicky" exits). All labelled `sample` | journal demos well without pretending | replace with real fills Sunday |
| D17 | Event impact metric: price change of the team **with the ball on the play** at +1/+3/+5/+10 min vs 30s before; bucketed by pregame home spread (fav ≥7, fav 3–6.5, pick'em, dog 3–6.5, dog ≥7) | first cut of "expected price move per hype event" | condition on score diff and time left |
| D18 | Game detail chart: signed candles → public trades → illustrative path labelled `sample` | candles/trades endpoints time out often on paper | streaming tape (ws) |
| D19 | Main line per type = most-volume market (server rule from v0.1). Can surface odd alt lines (e.g. total 30.5) | kept from v0.1 | prefer line nearest 50/50 |
| D20 | MMA/Soccer: tabs visible with "soon" chip, Pip empty state, hook status from `/api/future/*` | stubs he asked for | |
| D21 | Team marks are generated roundels, not real logos | no trademark assets in a repo he may publish | |
| D22 | Name "novig/clean" for the prototype | it's a cleaner Novig client; avoid implying it's official | rename before GitHub |
| D23 | Rules defaults from `swing-trading-math.md §8`: $20 max stake, $50 per game, −$60 daily stop, 2 adds, 0.03 trail, 0.03 min edge; editable in Settings (localStorage) | — | |
| D24 | No auth, single user, localhost only | prototype | |

## Open questions for Michael
1. Should quick adds ever require confirmation in live mode? (D9)
2. Average-cost vs FIFO for break-even? (D12)
3. Is the 4-minute trigger window right for linking a fill to a hype event? (D11)
4. Red for both Buy and losses — fine, or move Buy to ink/orange? (D5)
5. Want a dark "stadium" theme next to light?
