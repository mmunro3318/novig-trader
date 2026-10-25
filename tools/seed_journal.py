"""Seed data/journal.sqlite with REAL ESPN play-by-play for 3 NFL games (Oct 18-19 2026) and SAMPLE price paths +
SAMPLE trades that follow Michael's overreaction playbook. Everything seeded is source='sample'."""
import os, sys, math, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from novig import pbp, journal as J
random.seed(7)
GAMES = ["401872996", "401872999", "401872997"]
if os.path.exists(J.DB): os.remove(J.DB)
c = J.db()
def snap(p): return min(0.98, max(0.02, round(p * 200) / 200))
for gid in GAMES:
    g = pbp.game_events(gid, "NFL"); h, a = g["home"]["abbr"], g["away"]["abbr"]; gk = f"espn-{gid}"
    J.upsert_game(c, {"game_key": gk, "espn_id": gid, "league": "NFL", "away": a, "home": h, "away_color": g["away"]["color"], "home_color": g["home"]["color"],
                      "kickoff_ts": g["kickoffTs"], "spread_home": g["spreadHome"], "spread_text": g["spread"], "source": "espn+sample"})
    J.add_events(c, gk, g["events"])
    wp = sorted(g["winprob"], key=lambda w: w["ts"]); hype = [e for e in g["events"] if e["hype"]]
    t0, t1 = wp[0]["ts"], wp[-1]["ts"]; ticks = []; noise = 0
    def base(ts):
        prev = wp[0]
        for w in wp:
            if w["ts"] > ts: return prev["home"]
            prev = w
        return prev["home"]
    for ts in range(t0, t1 + 1, 20_000):
        p = base(ts); over = 0
        for e in hype:
            dt = ts - e["ts"]
            if 0 <= dt < 900_000:
                jump = base(e["ts"] + 5000) - base(e["ts"] - 5000)
                over += (0.9 * jump + (0.05 if jump >= 0 else -0.05) * (1 if e["type"] in ("INT", "FUMBLE_LOST", "PICK_SIX", "INJURY") else 0.4)) * math.exp(-dt / 160_000)
        noise = noise * 0.8 + random.gauss(0, 0.006)
        ticks.append((ts, snap(p + over + noise)))
    c.executemany("insert into ticks values(?,?,?,?,?)", [(gk, h, ts, p, "sample:espn-wp+overreaction") for ts, p in ticks] +
                  [(gk, a, ts, snap(1 - p + 0.01), "sample:espn-wp+overreaction") for ts, p in ticks])
    c.commit()
    # ---- simulated trader ------------------------------------------------------------------
    price = {h: dict(ticks), a: {ts: snap(1 - p + 0.01) for ts, p in ticks}}
    grid = [ts for ts, _ in ticks]
    def at(o, ts):
        i = max(0, min(len(grid) - 1, (ts - t0) // 20_000)); return price[o][grid[i]]
    def ctx(ts):
        last = [e for e in g["plays"] if e["ts"] <= ts]
        e = last[-1] if last else {"away": 0, "home": 0, "period": 1, "clock": "15:00"}
        return {"away_score": e["away"], "home_score": e["home"], "period": e["period"], "clock": e["clock"]}
    busy_until, legs = 0, 0
    for e in hype:
        if e["ts"] < busy_until or legs >= 4 or e["period"] == 4 and e["clock"] < "2:00": continue
        dh = at(h, e["ts"] + 60_000) - at(h, e["ts"] - 30_000)
        if abs(dh) < 0.06: continue
        o = a if dh > 0 else h; ts = e["ts"] + random.randint(25, 70) * 1000; p = at(o, ts)
        if p < 0.06 or p > 0.8: continue
        legs += 1
        tags = random.choice([["overreaction", "nervous"], ["overreaction"], ["gut", "fomo"], ["overreaction", "calm"]])
        f = J.record_fill(c, {"game_key": gk, "outcome": o, "side": "BUY", "price": p, "stake": 5, "ts": ts, "source": "sample", "tags": tags,
                              "note": random.choice(["", "fans panicking, this is too far", "", "classic overreaction", ""]), **ctx(ts)})
        last_buy, end, hi = p, None, p; panicky = random.random() < 0.4
        for ts2 in range(ts + 20_000, min(t1, ts + 1_500_000), 20_000):
            q = at(o, ts2); qty, basis = J.position(c, gk, o); avg = basis / qty * 100
            hi = max(hi, q)
            if panicky and q <= last_buy - 0.06:
                J.record_fill(c, {"game_key": gk, "outcome": o, "side": "SELL", "price": q, "ts": ts2, "source": "sample", "tags": ["nervous", "rule-break"], "note": "couldn't stomach it", **ctx(ts2)}); end = ts2; break
            if q <= last_buy - 0.05 and q > 0.04 and basis < 14:
                J.record_fill(c, {"game_key": gk, "outcome": o, "side": "BUY", "price": q, "stake": random.choice([1, 2, 2, 5]), "ts": ts2, "source": "sample",
                                  "tags": ["averaging-down"], **ctx(ts2)}); last_buy = q; continue
            if q >= avg + 0.07 and hi - q >= 0.02:
                if random.random() < 0.35 and qty > 300:
                    J.record_fill(c, {"game_key": gk, "outcome": o, "side": "SELL", "price": q, "qty": qty // 2, "ts": ts2, "source": "sample", "tags": ["target-hit"], **ctx(ts2)}); continue
                J.record_fill(c, {"game_key": gk, "outcome": o, "side": "SELL", "price": q, "ts": ts2, "source": "sample", "tags": ["trailing-stop"], **ctx(ts2)}); end = ts2; break
            if ts2 - ts > 1_200_000:
                J.record_fill(c, {"game_key": gk, "outcome": o, "side": "SELL", "price": q, "ts": ts2, "source": "sample", "tags": ["rebalance"] if q < avg else ["momentum"],
                                  "note": "bounces not touching entry, cutting it", **ctx(ts2)}); end = ts2; break
        if end is None:
            q, _ = J.position(c, gk, o)
            if q: J.record_fill(c, {"game_key": gk, "outcome": o, "side": "SELL", "price": at(o, t1 - 60_000), "ts": t1 - 60_000, "source": "sample", **ctx(t1 - 60_000)}); end = t1
        busy_until = end + 60_000
    print(gk, a, "@", h, len(g["events"]), "events", len(ticks), "ticks", J.rows(c, "select count(*) n, round(sum(realized),2) r from entries where game_key=?", gk)[0])
