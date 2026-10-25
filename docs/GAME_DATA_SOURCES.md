# Live game-state sources (measured Oct 22 2026, NE @ CHI, TNF)

## ESPN (current source, `novig/pbp.py`)
- `site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event=ID` — plays carry `wallclock`, `start.down/distance/possessionText/team`, `scoringPlay`, type text (fumble/INT/sack/TD), plus win probability.
- Measured lag (first seen in feed minus play wall-clock, 5s polling, `live/espn_latency.jsonl`, script `live/latency.py`):
  first window median ~230 s, min ~55 s, max ~575 s. Plays arrive in **batches** (several plays per drive at once). Drive-level, not play-level.
- Verdict: fine for the journal/story timeline; **too slow to trade the turnover spike** — Novig odds move before ESPN shows the play.
- Faster ESPN variants worth testing: `cdn.espn.com/core/nfl/playbyplay?xhr=1&gameId=ID`, `cdn.espn.com/core/nfl/game?xhr=1&gameId=ID` (situation/lastPlay block), and the scoreboard `situation` object (down, distance, possession, lastPlay) which often updates before the drive list.

## Alternatives
1. **NFLMeta** (nflmeta.org) — free tier, API key, `/api/v1/live-scores` + `/api/v1/plays?game_id=`; target ~15–20 s after score changes; free = non-commercial.
2. **nflverse** — excellent post-game PBP (EPA, wp) but published next morning; not live. `nfllivepy` (pip) is just an ESPN wrapper.
3. **NFL GameCenter / NGS JSON** — the old public feed is gone; current api.nfl.com needs a token from the web app (not used: would mean scraping a client token).
- Paid low-latency: Sportradar, SportsDataIO, Genius Sports (official, seconds-level) — trial keys only.
- Audio/commentary (radio streams, NFL+ audio) is faster than any free JSON but not parsed (out of scope).

## Practical idea
Use Novig's own price as the event detector: a ≥3–5c jump in <60 s *is* the turnover; ESPN confirms/labels it later for the journal.
