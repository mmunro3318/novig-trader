"""Auto-journal: every fill (live, dry-run or sample) becomes an entry. SQLite at data/journal.sqlite.

Data model (designed so price moves can later be aggregated by event type x pregame spread):
  games(game_key, novig_event_id, espn_id, league, away, home, kickoff_ts, spread_home, source)
  events(id, game_key, ts, type, period, clock, away_score, home_score, team, text, hype)  <- play-by-play notches
  ticks(game_key, outcome, ts, price, source)                                             <- price line (implied prob 0..1)
  entries(id, game_key, ts, outcome, side, action, stake, price, qty, fee, score/clock, position snapshot,
          trigger_event_id, tags, note, source)                                           <- the journal
Positions: Novig contracts pay $0.01 each, so qty = stake / price * 100; value = qty/100 * price.
"""
from __future__ import annotations
import json, os, sqlite3, time, uuid, threading
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "journal.sqlite")
_l = threading.Lock()
SCHEMA = """
create table if not exists games(game_key text primary key, novig_event_id text, espn_id text, league text, away text, home text,
  away_color text, home_color text, kickoff_ts integer, spread_home real, spread_text text, source text);
create table if not exists events(id text primary key, game_key text, ts integer, type text, period integer, clock text,
  away_score integer, home_score integer, team text, text text, hype integer);
create table if not exists ticks(game_key text, outcome text, ts integer, price real, source text);
create index if not exists ticks_g on ticks(game_key, outcome, ts);
create table if not exists entries(id text primary key, game_key text, ts integer, market_id text, outcome_id text, outcome text,
  side text, action text, stake real, price real, qty integer, fee real, away_score integer, home_score integer, period integer, clock text,
  pos_qty integer, pos_basis real, avg_price real, pos_value real, realized real, trigger_event_id text, order_id text,
  source text, tags text default '[]', note text default '');
"""
TAGS = ["overreaction", "momentum", "averaging-down", "rebalance", "target-hit", "trailing-stop", "gut", "fomo", "tilt", "calm", "nervous", "rule-break"]

def db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, check_same_thread=False); c.row_factory = sqlite3.Row; c.executescript(SCHEMA); return c

def rows(c, q, *a): return [dict(r) for r in c.execute(q, a)]

def upsert_game(c, g):
    c.execute("insert or replace into games values(?,?,?,?,?,?,?,?,?,?,?,?)", (g["game_key"], g.get("novig_event_id"), g.get("espn_id"), g.get("league"),
              g["away"], g["home"], g.get("away_color"), g.get("home_color"), g.get("kickoff_ts"), g.get("spread_home"), g.get("spread_text"), g.get("source", "sample")))

def add_events(c, game_key, evs):
    c.executemany("insert or replace into events values(?,?,?,?,?,?,?,?,?,?,?)", [(e["id"], game_key, e["ts"], e["type"], e["period"], e["clock"],
                  e.get("away"), e.get("home"), e.get("team"), e.get("text"), int(bool(e.get("hype")))) for e in evs])

def position(c, game_key, outcome):
    q = basis = realized = 0.0
    for e in rows(c, "select * from entries where game_key=? and outcome=? order by ts", game_key, outcome):
        if e["side"] == "BUY": q += e["qty"]; basis += e["stake"] + (e["fee"] or 0)
        else:
            avg = basis / q if q else 0; basis -= avg * e["qty"]; q -= e["qty"]
    return int(q), basis

def record_fill(c, f):
    """f: game_key, outcome, side BUY|SELL, price (0..1), stake (BUY $) or qty (SELL), ts, score/clock, source, order_id, ..."""
    with _l:
        gk, oc, side, p = f["game_key"], f["outcome"], f["side"].upper(), float(f["price"])
        q0, b0 = position(c, gk, oc)
        if side == "BUY":
            qty = int(f.get("qty") or round(float(f["stake"]) / p * 100)); stake = round(qty / 100 * p, 4)
            had = rows(c, "select count(*) n from entries where game_key=? and outcome=?", gk, oc)[0]["n"]
            action = "ADD" if q0 > 0 else ("REENTER" if had else "ENTER")
            q1, b1, realized = q0 + qty, b0 + stake + float(f.get("fee") or 0), 0.0
        else:
            qty = min(int(f.get("qty") or q0), q0)
            if qty <= 0: raise ValueError("nothing to sell")
            stake = round(qty / 100 * p, 4); avg = b0 / q0
            realized = stake - avg * qty - float(f.get("fee") or 0)
            q1, b1 = q0 - qty, b0 - avg * qty
            action = "EXIT" if q1 == 0 else "PARTIAL_EXIT"
        ts = int(f.get("ts") or time.time() * 1000)
        trig = rows(c, "select id from events where game_key=? and hype=1 and ts<=? and ts>=? order by ts desc limit 1", gk, ts, ts - 240_000)
        e = {"id": f.get("id") or uuid.uuid4().hex[:12], "game_key": gk, "ts": ts, "market_id": f.get("market_id"), "outcome_id": f.get("outcome_id"),
             "outcome": oc, "side": side, "action": action, "stake": stake, "price": p, "qty": qty, "fee": float(f.get("fee") or 0),
             "away_score": f.get("away_score"), "home_score": f.get("home_score"), "period": f.get("period"), "clock": f.get("clock"),
             "pos_qty": q1, "pos_basis": round(b1, 4), "avg_price": round(b1 / q1 * 100, 4) if q1 else None, "pos_value": round(q1 / 100 * p, 4),
             "realized": round(realized, 4), "trigger_event_id": trig[0]["id"] if trig else None, "order_id": f.get("order_id"),
             "source": f.get("source", "dryrun"), "tags": json.dumps(f.get("tags", [])), "note": f.get("note", "")}
        c.execute(f"insert into entries({','.join(e)}) values({','.join('?' * len(e))})", tuple(e.values())); c.commit()
        return e

def annotate(c, entry_id, tags=None, note=None):
    if tags is not None: c.execute("update entries set tags=? where id=?", (json.dumps(tags), entry_id))
    if note is not None: c.execute("update entries set note=? where id=?", (note, entry_id))
    c.commit(); return rows(c, "select * from entries where id=?", entry_id)[0]

def price_at(ticks, ts):
    best = None
    for t in ticks:
        if t["ts"] <= ts: best = t["price"]
        else: break
    return best if best is not None else (ticks[0]["price"] if ticks else None)

def story(c, game_key):
    g = rows(c, "select * from games where game_key=?", game_key)[0]
    ev = rows(c, "select * from events where game_key=? order by ts", game_key)
    en = rows(c, "select * from entries where game_key=? order by ts", game_key)
    for e in en: e["tags"] = json.loads(e["tags"] or "[]")
    outs = sorted({e["outcome"] for e in en} | {r["outcome"] for r in rows(c, "select distinct outcome from ticks where game_key=?", game_key)})
    ticks = {o: rows(c, "select ts, price from ticks where game_key=? and outcome=? order by ts", game_key, o) for o in outs}
    evmap = {e["id"]: e for e in ev}
    # legs: flat -> in -> flat
    legs, cur = [], None
    for e in en:
        if cur is None or cur["outcome"] != e["outcome"] and e["action"] in ("ENTER", "REENTER"):
            cur = {"outcome": e["outcome"], "entries": [], "start": e["ts"]}; legs.append(cur)
        cur["entries"].append(e["id"])
        if e["side"] == "SELL": cur["realized"] = round(cur.get("realized", 0) + e["realized"], 4)
        if e["pos_qty"] == 0: cur["end"] = e["ts"]; cur = None
    buys = [e for e in en if e["side"] == "BUY"]; sells = [e for e in en if e["side"] == "SELL"]
    realized = round(sum(e["realized"] for e in sells), 2)
    lines = []
    for i, L in enumerate(legs, 1):
        es = [e for e in en if e["id"] in L["entries"]]; first = es[0]; trig = evmap.get(first["trigger_event_id"])
        adds = [e for e in es if e["action"] == "ADD"]; exits = [e for e in es if e["side"] == "SELL"]
        s = f"Leg {i}: bought {first['outcome']} at {1/first['price']:.2f}× (${first['stake']:.2f})"
        if trig: s += f" right after a {trig['type'].replace('_', ' ').lower()} (Q{trig['period']} {trig['clock']})"
        if adds: s += f", added {len(adds)}× (${sum(a['stake'] for a in adds):.2f}) down to {1/min(a['price'] for a in adds):.2f}×"
        if exits: s += f", out at {1/exits[-1]['price']:.2f}× for {'+' if L.get('realized', 0) >= 0 else '−'}${abs(L.get('realized', 0)):.2f}"
        else: s += ", still open"
        lines.append(s + ".")
    open_pos = {}
    for o in outs:
        q, b = position(c, game_key, o)
        if q: last = ticks[o][-1]["price"] if ticks[o] else en[-1]["price"]; open_pos[o] = {"qty": q, "basis": round(b, 2), "value": round(q / 100 * last, 2)}
    return {"game": g, "events": ev, "entries": en, "ticks": ticks, "legs": legs,
            "summary": {"fills": len(en), "buys": len(buys), "sells": len(sells), "staked": round(sum(e["stake"] for e in buys), 2),
                        "realized": realized, "open": open_pos, "hypeEvents": sum(1 for e in ev if e["hype"]),
                        "entriesAfterHype": sum(1 for e in buys if e["trigger_event_id"]), "narrative": lines}}

def days(c):
    gs = rows(c, "select g.*, count(e.id) fills, min(e.ts) first_ts, max(e.ts) last_ts, round(sum(e.realized),2) realized, round(sum(case when e.side='BUY' then e.stake else 0 end),2) staked "
                 "from games g join entries e on e.game_key=g.game_key group by g.game_key order by first_ts desc")
    return gs

def impacts(c, horizons=(60_000, 180_000, 300_000, 600_000)):
    """Expected price move per hype event type x spread bucket. Price is the HOME side; sign flipped so that
    'move' is from the perspective of the team the event hurt (team field = team with possession at the play)."""
    out = {}
    for g in rows(c, "select * from games"):
        home = g["home"]; t = rows(c, "select ts, price from ticks where game_key=? and outcome=? order by ts", g["game_key"], home)
        if len(t) < 5: continue
        sp = g["spread_home"]; bucket = "fav ≥7" if sp is not None and sp <= -7 else "fav 3-6.5" if sp is not None and sp <= -3 else "pick'em ±2.5" if sp is not None and abs(sp) < 3 else "dog 3-6.5" if sp is not None and sp < 7 else "dog ≥7" if sp is not None else "unknown"
        for e in rows(c, "select * from events where game_key=? and hype=1", g["game_key"]):
            p0 = price_at(t, e["ts"] - 30_000)
            if p0 is None: continue
            sign = 1 if e["team"] == home else -1
            k = (e["type"], bucket); o = out.setdefault(k, {"type": e["type"], "spread": bucket, "n": 0, **{f"d{h//1000}s": 0.0 for h in horizons}})
            o["n"] += 1
            for h in horizons: o[f"d{h//1000}s"] += sign * (price_at(t, e["ts"] + h) - p0)
    res = []
    for o in out.values():
        for h in horizons: o[f"d{h//1000}s"] = round(o[f"d{h//1000}s"] / o["n"], 4)
        res.append(o)
    return sorted(res, key=lambda r: -r["n"])

def open_positions(c):
    out = []
    for r in rows(c, "select distinct game_key, outcome from entries"):
        q, b = position(c, r["game_key"], r["outcome"])
        if q <= 0: continue
        g = rows(c, "select * from games where game_key=?", r["game_key"])[0]
        lt = rows(c, "select price, ts from ticks where game_key=? and outcome=? order by ts desc limit 1", r["game_key"], r["outcome"])
        last = rows(c, "select * from entries where game_key=? and outcome=? order by ts desc limit 1", r["game_key"], r["outcome"])[0]
        p = lt[0]["price"] if lt else last["price"]
        out.append({"game": g, "outcome": r["outcome"], "qty": q, "basis": round(b, 4), "avg": b / q * 100, "mark": p, "value": round(q / 100 * p, 4),
                    "source": last["source"], "lastTs": last["ts"]})
    return out
