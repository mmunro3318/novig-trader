"""Phase-1 trading engine: quotes, net positions, safe one-click orders.

Reliability rules (learned Thu Oct 22):
  * every click is an INTENT with an idempotency key (browser-generated); the same key is never executed twice,
    even across server restarts (SQLite data/orders.sqlite).
  * each send attempt gets its own clientId, recorded BEFORE the POST. If the POST times out we reconcile by
    looking the clientId up in fills/orders instead of blindly resending.
  * IOC limit orders only: limit = best price + slippage cents, so a fill is never worse than that.
  * partial fills are re-quoted and retried (max 4 attempts) only while the new price is still inside the
    original slippage band. Sells are re-sized from the live net position each attempt (never oversell).
  * all HTTP has (5s connect, 12s read) timeouts; the worker thread never blocks the UI.
"""
from __future__ import annotations
import json, math, os, queue, sqlite3, threading, time, traceback, uuid, datetime as dt
from novig.client import Novig, PAPER_HOST, PROD_HOST, trading_client, prod_read_client, live_trading_client, _load_env_file
from novig import pbp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.getenv("NOVIG_ENV", "paper").lower()
CFG = {  # safety rules; override with env vars
    "max_order_usd": float(os.getenv("NOVIG_MAX_ORDER_USD", "25")),
    "daily_loss_cap_usd": float(os.getenv("NOVIG_DAILY_LOSS_CAP_USD", "40")),
    "default_slip_cents": float(os.getenv("NOVIG_SLIP_CENTS", "2")),
    "max_attempts": 4,               # failed sends / buy re-quotes
    "max_exit_rounds": int(os.getenv("NOVIG_MAX_EXIT_ROUNDS", "12")),   # cash-sized chunks per sell click
    "flatten_alert_clock_s": 300,   # Q4 5:00
    # fee model: Novig taker fee = coef * p * (1 - p) per contract ($ per 100 contracts). "auto" follows each market's own
    # fee.charged (WHEN_LIVE = only while the game is in progress, ALWAYS = futures); "in_game_only", "always", "off" override it.
    "fee_mode": os.getenv("NOVIG_FEE_MODE", "auto"),
    "fee_coef": float(os.getenv("NOVIG_FEE_COEF", "0")) or None,   # None = use the market's coefficient (0.06 today)
    "risky_price": float(os.getenv("NOVIG_RISKY_PRICE", "0.10")),   # buys below this price (odds > 10) ask for a confirm
    "risky_clock_s": int(os.getenv("NOVIG_RISKY_CLOCK_S", "120")),  # buys in the last 2:00 of Q4 / OT ask for a confirm
    "double_click_s": float(os.getenv("NOVIG_DOUBLE_CLICK_S", "1.5")),  # identical buy within this window = double click
}
FEE_MODES = ("auto", "in_game_only", "always", "off")
_LOCK = threading.RLock()
SETTINGS_PATH = os.path.join(ROOT, "data", "settings.json")
try:
    with open(SETTINGS_PATH) as _f:
        for _k, _v in json.load(_f).items():
            if _k in ("daily_loss_cap_usd", "max_order_usd") and isinstance(_v, (int, float)) and _v > 0: CFG[_k] = float(_v)
            if _k == "fee_mode" and _v in FEE_MODES: CFG[_k] = _v
            if _k == "fee_coef" and (_v is None or (isinstance(_v, (int, float)) and 0 <= _v <= 0.2)): CFG[_k] = _v
except Exception: pass
def update_settings(b):
    """UI settings: daily loss cap (soft: buys past it need a confirm), per-order cap (hard, max 100)."""
    ch = {}
    if b.get("daily_loss_cap_usd") is not None:
        v = float(b["daily_loss_cap_usd"]);
        if not 1 <= v <= 10000: return {"ok": False, "error": "loss cap must be $1-$10000"}
        ch["daily_loss_cap_usd"] = v
    if b.get("max_order_usd") is not None:
        v = float(b["max_order_usd"])
        if not 1 <= v <= 100: return {"ok": False, "error": "per-order cap must be $1-$100"}
        ch["max_order_usd"] = v
    if b.get("fee_mode") is not None:
        if b["fee_mode"] not in FEE_MODES: return {"ok": False, "error": "fee mode must be one of " + ", ".join(FEE_MODES)}
        ch["fee_mode"] = b["fee_mode"]
    if "fee_coef" in b:
        v = b["fee_coef"]
        if v in (None, "", 0): ch["fee_coef"] = None
        else:
            v = float(v)
            if not 0 < v <= 0.2: return {"ok": False, "error": "fee coefficient must be 0-0.2 (Novig uses 0.06)"}
            ch["fee_coef"] = v
    CFG.update(ch)
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w") as f: json.dump({k: CFG[k] for k in ("daily_loss_cap_usd", "max_order_usd", "fee_mode", "fee_coef")}, f)
    return {"ok": True, "cfg": CFG}

# ------------------------------------------------------------------ clients per environment
if ENV == "production":
    C = Novig(host=PROD_HOST, key_id="", secret="")          # public catalog
    R = prod_read_client()                                     # management::read: reads all wallets
    W = live_trading_client()                                  # None unless he creates a live trading key
    TRADABLE = bool(W and W.live_writes_enabled)
else:
    C = Novig(host=PAPER_HOST, key_id="", secret="")
    W = trading_client(PAPER_HOST)
    R = W
    TRADABLE = bool(W and W.writes_enabled)

def wallets():
    """[(label, client, keyId-or-None, tradable)] whose positions we show."""
    if ENV == "production":
        out = []
        if W: out.append(("API sub-account (tradable)" if TRADABLE else "API sub-account (orders OFF)", R if R.has_key else W, W.key_id, TRADABLE))
        if R.has_key: out.append(("Novig app wallet (read-only)", R, R.key_id, False))
        return out
    return [("Paper sub-account", W, None, TRADABLE)]

def _unwrap(r, key_id=None):
    if isinstance(r, dict) and r and all(len(k) == 36 and k.count("-") == 4 for k in r):
        if key_id and key_id in r: return r[key_id]
        return next(iter(r.values()))
    return r

def _err(r): return isinstance(r, dict) and r.get("ok") is False

# ------------------------------------------------------------------ price grid / fees
def grid_ok(m):  # m = price in thousandths
    return 1 <= m <= 50 or 950 <= m <= 999 or (51 <= m <= 949 and m % 5 == 0)
def snap(p, direction):
    """Snap to Novig's grid. direction='down' never exceeds p (use for buy limits)."""
    m = int(math.floor(p * 1000 + 1e-9)) if direction == "down" else int(math.ceil(p * 1000 - 1e-9))
    m = max(1, min(999, m))
    while not grid_ok(m): m += -1 if direction == "down" else 1
    return m / 1000
def fee(price, qty, coef=0.06, live=True): return coef * price * (1 - price) * qty / 100 if live else 0.0
def fee_coef(mfee=None):
    """Coefficient in 0.06 * p * (1 - p): settings override, else the market's own, else 0.06."""
    return float(CFG.get("fee_coef") or (mfee or {}).get("coefficient") or 0.06)
def fee_applies(mfee=None, live=None):
    """Does a taker fill pay a fee right now? Pregame fills on WHEN_LIVE game markets pay $0 (seen on Novig fills)."""
    mode = CFG.get("fee_mode", "auto")
    if mode == "off": return False
    if mode == "always": return True
    if live is None: live = True            # unknown game state: assume the fee (conservative)
    if mode == "in_game_only": return bool(live)
    return True if ((mfee or {}).get("charged") or "WHEN_LIVE") == "ALWAYS" else bool(live)
def game_for(eid):
    for g in (_cache.get("games") or (0, {"games": []}))[1].get("games", []):
        if g["eventId"] == eid: return g
    return None
def event_live(eid):
    """True in-game, False pregame/final, None unknown (not in the games list)."""
    g = game_for(eid)
    if not g: return None
    return g["phase"] == "live"

# ------------------------------------------------------------------ catalog / quotes
class RateLimited(Exception): pass

class Bucket:
    """Global token bucket for ALL catalog reads (games, markets, books). Novig's per-key 'read' bucket is
    64 burst / 16 per s (GET /v3/limits) and the edge also limits per IP; catalog gets <= CAT_RATE/s so the
    order path (place / order status / fills / positions) always has headroom. A 429 pauses catalog reads for
    Retry-After seconds (default 3s) instead of retrying in a loop."""
    def __init__(self, rate, burst):
        self.rate, self.burst, self.tokens, self.t, self.until = rate, burst, burst, time.time(), 0.0
        self.lock = threading.Lock()
    def take(self, wait=0.6, n=1):
        deadline = time.time() + wait
        while True:
            with self.lock:
                now = time.time()
                self.tokens = min(self.burst, self.tokens + (now - self.t) * self.rate); self.t = now
                if now >= self.until and self.tokens >= n: self.tokens -= n; return True
                need = max(self.until - now, (n - self.tokens) / self.rate)
            if time.time() + need > deadline: return False
            time.sleep(min(need, 0.2))
    def pause(self, secs):
        with self.lock: self.until = max(self.until, time.time() + secs)
    def state(self): return {"pausedFor": round(max(0, self.until - time.time()), 1), "tokens": round(self.tokens, 1)}
CAT = Bucket(float(os.getenv("NOVIG_CATALOG_RATE", "5")), float(os.getenv("NOVIG_CATALOG_BURST", "8")))

def _catalog_client():
    """Separate client (own HTTP session) for catalog reads, so they never queue behind/in front of orders."""
    src = R if (ENV == "production" and R and R.has_key) else (W if (W and W.has_key) else None)
    if not src: return None
    c = Novig(host=src.host, key_id=src.key_id, secret=src._secret); return c
CK = _catalog_client()

def _cat(path, priority=False, tokens=1, **params):
    """Catalog read. priority=True (order path) skips the local bucket; otherwise RateLimited is raised
    immediately when the bucket is empty/paused so callers can serve stale data instead of blocking."""
    if not priority and tokens and not CAT.take(n=tokens):
        raise RateLimited(f"catalog throttled locally ({path})")
    k = (W if priority and W and W.has_key else CK)
    if k:
        r = k._signed("GET", "/v3/catalog" + path, {a: b for a, b in params.items() if b is not None} or None)
        if isinstance(r, dict) and r.get("ok") is False:
            if r.get("status") == 429:
                try: ra = float(r.get("retryAfter") or 3)
                except ValueError: ra = 3
                CAT.pause(ra)
                if priority:   # order path: up to 3 short retries (~2.5s total), never give up silently
                    for i in range(3):
                        time.sleep(min(ra, 0.4 * (i + 1) + 0.2)); r = k._signed("GET", "/v3/catalog" + path, {a: b for a, b in params.items() if b is not None} or None)
                        if not (isinstance(r, dict) and r.get("ok") is False): return r
                raise RateLimited(f"429 on {path} (retry after {ra:.0f}s)")
            raise RuntimeError(f"catalog {path}: {r.get('status')} {r.get('code')}")
        return r
    try: return C._public("/v3/public/catalog" + path, **params)
    except Exception as e:
        resp = getattr(e, "response", None)
        if resp is not None and resp.status_code == 429:
            try: ra = float(resp.headers.get("Retry-After") or 3)
            except ValueError: ra = 3
            CAT.pause(ra); raise RateLimited(f"429 on {path} (retry after {ra:.0f}s)")
        raise
def cat_market(mid, priority=False, tokens=1): return _cat(f"/markets/{mid}", priority=priority, tokens=tokens)
def cat_book(mid, priority=False, tokens=1): return _cat(f"/markets/{mid}/book", priority=priority, tokens=tokens)

_cache = {}; _inflight = {}; _cl = threading.Lock()
def cached(k, ttl, fn, stale_ok=True):
    """TTL cache + single-flight (concurrent identical fetches share one upstream call) + stale fallback:
    on RateLimited/network errors return the last good value marked stale (dicts get 'stale': True)."""
    h = _cache.get(k)
    if h and time.time() - h[0] < ttl: return h[1]
    with _cl:
        ev = _inflight.get(k); leader = ev is None
        if leader: ev = _inflight[k] = threading.Event()
    if not leader:
        ev.wait(15); h = _cache.get(k)
        if h: return h[1]
        raise RateLimited(f"no data yet for {k}")
    try:
        v = fn()
        if isinstance(v, dict): v.pop("stale", None)
        _cache[k] = (time.time(), v); return v
    except Exception as e:
        if stale_ok and h:
            v = h[1]
            if isinstance(v, dict): v = {**v, "stale": True, "staleAge": round(time.time() - h[0]), "staleWhy": str(e)[:120]}
            return v
        raise
    finally:
        with _cl: _inflight.pop(k, None)
        ev.set()

def games():
    def get():
        now = int(time.time() * 1000)
        evs = []
        for j, st in enumerate(("OPEN_INGAME", "OPEN_PREGAME")):
            r = _cat("/events", tokens=3 if j == 0 else 0, league="NFL,NCAAF", status=st, startsBefore=now + 16 * 3600_000, limit=500)
            evs += [e for e in r.get("items", []) if e["startsTs"] > now - 6 * 3600_000 and " @ " in e["description"]]
        mk = _cat("/markets", tokens=0, league="NFL,NCAAF", marketType="MONEY", eventStatus="OPEN_INGAME,OPEN_PREGAME", limit=1000)
        by = {}
        for m in mk.get("items", []):
            if m["eventId"] not in by or m["volume"] > by[m["eventId"]]["volume"]: by[m["eventId"]] = m
        out = []
        for e in evs:
            m = by.get(e["eventId"]); ck = clock_for(e)
            q = order_away_home(quote_from_market(m), ck) if m else None
            away, _, home = e["description"].partition(" @ ")
            out.append({"eventId": e["eventId"], "desc": e["description"], "away": away.strip(), "home": home.strip(), "league": e["league"],
                        "status": e["status"], "phase": "live" if e["status"] == "OPEN_INGAME" else "upcoming", "startsTs": e["startsTs"],
                        "money": q, "clock": ck})
        try: out += past_games(now)
        except Exception: pass
        out.sort(key=lambda g: (["live", "upcoming", "past"].index(g["phase"]), g["startsTs"]))
        return {"ts": now, "games": out}
    return cached("games", 15, get)

def past_games(now):
    """Today's finished games (dimmed PAST section). Cached 5 min: they don't change."""
    def get():
        today0 = int(dt.datetime.combine(dt.date.today(), dt.time()).timestamp() * 1000)
        r = _cat("/events", tokens=0, league="NFL,NCAAF", status="FINAL,SETTLED,CLOSED_PREGAME", startsAfter=today0 - 3 * 3600_000, startsBefore=now, limit=200)
        out = []
        for e in r.get("items", []):
            if " @ " not in e["description"] or e["startsTs"] < today0: continue
            away, _, home = e["description"].partition(" @ ")
            out.append({"eventId": e["eventId"], "desc": e["description"], "away": away.strip(), "home": home.strip(), "league": e["league"],
                        "status": e["status"], "phase": "past", "startsTs": e["startsTs"], "money": None, "clock": clock_for(e)})
        return out
    return cached("past", 300, get)

def quote_from_market(m):
    outs = m["outcomes"]; bid = {o["outcomeId"]: float((o.get("bid") or {}).get("price") or 0) for o in outs}
    res = []
    for o in outs:
        other = [x for x in outs if x["outcomeId"] != o["outcomeId"]]
        ob = bid[other[0]["outcomeId"]] if other else 0
        res.append({"outcomeId": o["outcomeId"], "name": o["name"], "bid": bid[o["outcomeId"]] or None, "ask": round(1 - ob, 3) if ob else None, "last": o.get("last")})
    return {"marketId": m["marketId"], "type": m["marketType"], "strike": m.get("strike"), "status": m["status"], "desc": m["description"],
            "fee": m.get("fee"), "volume": m.get("volume"), "outcomes": res}

def event_markets(eid):
    def get_l():
        r = _cat("/markets", event=eid, marketType="MONEY,SPREAD,TOTAL,TEAM_TOTAL", limit=500)
        ms = [quote_from_market(m) for m in r.get("items", []) if len(m["outcomes"]) == 2 and m["status"] == "OPEN"]
        ms.sort(key=lambda m: (["MONEY", "SPREAD", "TOTAL"].index(m["type"]) if m["type"] in ("MONEY", "SPREAD", "TOTAL") else 9, -(m["volume"] or 0)))
        return ms
    return {"markets": cached("em" + eid, 30, get_l)}["markets"]

def book(mid, priority=False):
    """UI: cached ~1.5s + stale fallback.  Order path (priority=True): always fresh, bypasses the catalog bucket."""
    if priority: return _book(mid, True)
    return cached("book" + mid, 1.5, lambda: _book(mid, False))

def _book(mid, priority):
    """Market + book. Asks for outcome A are the bids of B, mirrored (1 - p)."""
    m = cat_market(mid, priority, tokens=2); b = cat_book(mid, priority, tokens=0)   # reserve both calls at once
    q = quote_from_market(m); orders = b.get("orders", {})
    for o in q["outcomes"]:
        other = [x for x in q["outcomes"] if x["outcomeId"] != o["outcomeId"]][0]
        lv = {}
        for x in orders.get(o["outcomeId"], []): lv[float(x["price"])] = lv.get(float(x["price"]), 0) + x["qty"]
        o["bids"] = sorted(lv.items(), reverse=True)[:6]
        lv = {}
        for x in orders.get(other["outcomeId"], []): lv[round(1 - float(x["price"]), 3)] = lv.get(round(1 - float(x["price"]), 3), 0) + x["qty"]
        o["asks"] = sorted(lv.items())[:6]
    q["eventId"] = m.get("eventId"); q["seq"] = b.get("seq"); q["ts"] = int(time.time() * 1000)
    return q

# ------------------------------------------------------------------ game clock (ESPN) for Q4 alerts
def _clock_board():
    def get():
        games = []
        for lg in ("NFL", "NCAAF"):
            try: games += pbp.scoreboard(lg)["games"]
            except Exception: pass
        return games
    return cached("espn", 20, get)
def _espn_match(e):
    try: away, home = [s.strip().lower() for s in e["description"].split("@")]
    except ValueError: return None
    for g in _clock_board():
        names = lambda t: [str((t or {}).get(k) or "").lower() for k in ("name", "short", "abbr")]
        if any(n and (n == home or n in home or home in n) for n in names(g["home"])) and any(n and (n == away or n in away or away in n) for n in names(g["away"])):
            return g
    return None

def clock_for(e):
    """ESPN game state for a Novig event (pre/in/post). Names are away @ home (US convention; Novig desc is 'Away @ Home')."""
    g = _espn_match(e)
    if not g: return None
    secs = None
    try: mm, ss = (g.get("clock") or "0:00").split(":"); secs = int(mm) * 60 + int(float(ss))
    except Exception: pass
    live = g.get("state") == "in"
    late = live and ((g.get("period") or 0) >= 5 or ((g.get("period") or 0) == 4 and secs is not None and secs <= CFG["flatten_alert_clock_s"]))
    a, h = g["away"] or {}, g["home"] or {}
    return {"period": g.get("period"), "clock": g.get("clock"), "detail": g.get("detail"), "state": g.get("state"), "espnId": g.get("espnId"),
            "league": g.get("league"), "secs": secs,
            "score": f"{a.get('abbr')} {a.get('score')} - {h.get('abbr')} {h.get('score')}" if g.get("state") != "pre" else None, "late": late,
            "away": {"abbr": a.get("abbr"), "score": a.get("score"), "color": a.get("color"), "record": a.get("record")},
            "home": {"abbr": h.get("abbr"), "score": h.get("score"), "color": h.get("color"), "record": h.get("record")},
            "situation": g.get("situation") if live else None}

def order_away_home(q, clock):
    """Put moneyline outcomes in away, home order (Novig lists home first). Uses ESPN abbrs when matched."""
    if not q or len(q["outcomes"]) != 2: return q
    o = q["outcomes"]
    if clock and clock.get("away", {}).get("abbr"):
        aw = clock["away"]["abbr"].upper()
        if o[1]["name"].upper().split()[0] == aw: q["outcomes"] = [o[1], o[0]]
        q["orderedBy"] = "espn"
    else:
        q["outcomes"] = [o[1], o[0]]; q["orderedBy"] = "assumed-home-first"
    q["outcomes"][0]["homeAway"] = "away"; q["outcomes"][1]["homeAway"] = "home"
    return q

# ------------------------------------------------------------------ positions (net, basis incl fees, value, break-even)
_FC = {}   # fill cache per wallet: {"items": {fillId: fill}, "last": ts, "polled": t}
def _fills_raw(client, key_id, **p):
    items, after = [], None
    for _ in range(10):
        q = {"limit": 500, **p}
        if key_id and ENV == "production": q["keyId"] = key_id
        if after: q["after"] = after
        r = _unwrap(client.fills(**q), key_id)
        if _err(r): raise RuntimeError(f"fills: {r.get('status')} {r.get('code') or r.get('error')}")
        items += r.get("items", []); after = r.get("next")
        if not after: break
    return items
def remember_fills(key_id, fills):
    c = _FC.setdefault(key_id or "-", {"items": {}, "last": 0, "polled": 0})
    for f in fills: c["items"][f["fillId"]] = f; c["last"] = max(c["last"], f["ts"])
def _fills(client, key_id, max_age=15):
    """Fills are on the expensive 'history' throttle (8 tokens, refill 4/s): fetch all once, then incremental
    every ~15s; our own orders push their fills in directly (remember_fills)."""
    c = _FC.setdefault(key_id or "-", {"items": {}, "last": 0, "polled": 0})
    if time.time() - c["polled"] > max_age:
        new = _fills_raw(client, key_id, **({"startsAfter": c["last"] - 60_000} if c["last"] else {}))
        remember_fills(key_id, new); c["polled"] = time.time()
    return sorted(c["items"].values(), key=lambda x: x["ts"])

def _positions(client, key_id):
    r = client._signed("GET", "/v3/portfolio/positions", {"keyId": key_id} if key_id and ENV == "production" else None)
    r = _unwrap(r, key_id)
    if _err(r): raise RuntimeError(f"positions: {r.get('status')} {r.get('code') or r.get('error')}")
    return r

def _shrink(L, take):
    if take <= 0 or L["qty"] <= 0: return
    fr = min(1.0, take / L["qty"]); L["cost"] -= L["cost"] * fr; L["fee"] -= L["fee"] * fr; L["qty"] -= take

def _reduce_lots(trip, cq, cid, lot_of_cid):
    """An exit of cq contracts: a 'sell this lot' order (its clientId maps to a lot) comes out of that lot first;
    any other exit (sell all / half / $N / %) comes out of every lot pro rata, so each lot keeps its own entry odds."""
    rem = cq; tgt = lot_of_cid.get(cid) if cid else None
    if tgt and tgt in trip["lots"]:
        L = trip["lots"][tgt]; take = min(L["qty"], rem); _shrink(L, take); rem -= take
    ls = [L for L in trip["lots"].values() if L["qty"] > 0]; tot = sum(L["qty"] for L in ls)
    if rem <= 0 or not tot: return
    rem = min(rem, tot); alloc = [int(rem * L["qty"] / tot) for L in ls]; left = rem - sum(alloc)
    for i in sorted(range(len(ls)), key=lambda i: -ls[i]["qty"]):
        if left <= 0: break
        if alloc[i] < ls[i]["qty"]: alloc[i] += 1; left -= 1
    for L, t in zip(ls, alloc): _shrink(L, t)

def replay(fills_m, outs, lot_of_cid=None):
    """One market's fills -> (open trip or None, closed trips). Exits = buys of the opposite side.
    trip: side, net (contracts), basis (cost + fees - exit proceeds), stake (entry cost of what's left, before fees),
    entry/exit fees, lots {orderId: qty, cost, fee, ts} (one lot per buy order)."""
    lot_of_cid = lot_of_cid or {}; q = {o: 0 for o in outs}; trip = None; closed = []
    def new_trip(side, ts): return {"side": side, "basis": 0.0, "openTs": ts, "entry_fees": 0.0, "exit_fees": 0.0, "adds": 0, "lots": {}}
    def add_lot(t, f, qty, cost, fe):
        k = f.get("orderId") or f.get("fillId") or str(f["ts"])
        L = t["lots"].setdefault(k, {"id": k, "qty": 0, "cost": 0.0, "fee": 0.0, "ts": f["ts"]}); L["qty"] += qty; L["cost"] += cost; L["fee"] += fe
    for f in fills_m:
        o = f["outcomeId"]; qty = f["qty"]; cost = float(f["cost"]); fe = float(f.get("fee") or 0)
        if o not in q: q[o] = 0
        n0 = q[outs[0]] - q[outs[1]] if len(outs) == 2 else q[o]
        held = (outs[0] if n0 > 0 else outs[1] if n0 < 0 else None) if len(outs) == 2 else (o if n0 > 0 else None)
        if held and o != held and len(outs) == 2:
            cq = min(qty, abs(n0)); proceeds = cq / 100 - (cost + fe) * cq / qty
            trip["basis"] -= proceeds; trip["exit_fees"] += fe * cq / qty
            _reduce_lots(trip, cq, f.get("clientId"), lot_of_cid)
            q[o] += qty
            if q[outs[0]] - q[outs[1]] == 0:
                trip["pnl"] = -trip["basis"]; trip["closeTs"] = f["ts"]; trip["net"] = 0; closed.append(trip); trip = None
            if qty > cq:
                rq = qty - cq; trip = new_trip(o, f["ts"]); trip["basis"] = (cost + fe) * rq / qty; trip["entry_fees"] = fe * rq / qty; trip["adds"] = 1
                add_lot(trip, f, rq, cost * rq / qty, fe * rq / qty)
            continue
        if trip is None: trip = new_trip(o, f["ts"])
        trip["basis"] += cost + fe; trip["entry_fees"] += fe; trip["adds"] += 1; q[o] += qty; add_lot(trip, f, qty, cost, fe)
    if trip is not None:
        trip["net"] = abs(q[outs[0]] - q[outs[1]]) if len(outs) == 2 else q.get(trip["side"], 0)
        trip["stake"] = sum(L["cost"] for L in trip["lots"].values())
    return trip, closed

def settle_payout(mkt, side_id):
    """Per-contract payout fraction for a settled market: WIN 1, LOSS 0, '0.50' = half (push/dead heat). None if not graded."""
    for o in (mkt or {}).get("outcomes", []):
        if o.get("outcomeId") == side_id:
            st = str(o.get("status") or "").upper()
            if st == "WIN": return 1.0
            if st in ("LOSS", "LOSE", "LOST"): return 0.0
            try: return max(0.0, min(1.0, float(st)))
            except ValueError: return None
    return None

CLOSED_ST = ("CLOSED", "SETTLED", "VOIDED", "FINAL")
def market_summary(fm, outs, mkt, lot_of_cid=None):
    """Closed trips for one market, INCLUDING a trip held to the final once Novig grades it (settled WIN/LOSS).
    Returns {closed: [...], open: trip|None, settled: bool, settling: bool}."""
    trip, closed = replay(fm, outs, lot_of_cid)
    st = (mkt or {}).get("status")
    settled = st == "SETTLED"
    res = {"closed": [dict(t, kind="exit") for t in closed], "open": trip, "settled": False, "settling": False}
    if trip and trip.get("net"):
        if settled:
            pay = settle_payout(mkt, trip["side"])
            if pay is not None:
                t = dict(trip); t["payout"] = round(trip["net"] / 100 * pay, 4); t["pnl"] = t["payout"] - trip["basis"]
                t["closeTs"] = int(mkt.get("settledTs") or fm[-1]["ts"]); t["kind"] = "settled"
                t["result"] = "WIN" if pay >= 1 else "LOSS" if pay <= 0 else "PUSH"
                res["closed"].append(t); res["open"] = None; res["settled"] = True
            else: res["settling"] = True
        elif st in CLOSED_ST: res["settling"] = True
    elif settled: res["settled"] = True
    return res

def history_market(client, mid):
    """GET /v3/history/markets/{id}: settled markets with each outcome's grade (WIN / LOSS / 0.50). History throttle."""
    try:
        r = _unwrap(client.history_market(mid))
        return r if isinstance(r, dict) and r.get("outcomes") and not _err(r) else None
    except Exception: return None

def _strip(t):   # what we persist / send for a closed trip (no lots)
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in t.items() if k != "lots"}

def _settled_db():
    DB.execute("create table if not exists settled(wallet text, market_id text, ts integer, data text, primary key(wallet, market_id))"); DB.commit()
def settled_get(wallet, mid):
    with _LOCK: r = DB.execute("select data from settled where wallet=? and market_id=?", (wallet, mid)).fetchone()
    return json.loads(r["data"]) if r else None
def settled_put(wallet, mid, summ):
    with _LOCK:
        DB.execute("insert or replace into settled values(?,?,?,?)", (wallet, mid, int(time.time() * 1000), json.dumps(summ))); DB.commit()

def _lot_map():
    """clientId -> lot id, for 'sell this lot' orders (so that exit comes out of that lot)."""
    out = {}
    with _LOCK: rows = DB.execute("select client_ids, lot from intents where lot != '' and lot is not null").fetchall()
    for r in rows:
        for c in json.loads(r["client_ids"] or "[]"): out[c] = r["lot"]
    return out

_MS = {}   # (wallet, marketId) -> (expires, market dict or None) for markets that are no longer open
def portfolio(fresh=False):
    if fresh: return _portfolio()
    return cached("portfolio", 2, _portfolio)

def _add_closed(w, t, today0):
    if t["closeTs"] >= today0:
        w["day"]["realized"] += t["pnl"]; w["day"]["trades_closed"] += 1
        if t.get("kind") == "settled": w["day"]["settled"] += 1
    w["life"]["realized"] += t["pnl"]; w["life"]["closed"] += 1; w["life"]["wins"] += t["pnl"] > 0
    if t.get("kind") == "settled": w["life"]["settled"] += 1; w["life"]["settledWins"] += t["pnl"] > 0
    if t["closeTs"] >= today0: w["closedToday"].append(_strip(t))

def _portfolio():
    """All wallets: net positions with live value, P&L after exit fee, break-even, lots; day + lifetime stats.
    Day/lifetime realized P&L and the win rate count (a) trips closed by selling and (b) trips held to the final,
    once Novig grades the market (WIN pays $1/contract, LOSS $0). Graded markets are stored in orders.sqlite
    (table settled) so they keep counting after Novig drops them from the open catalog."""
    with _LOCK: pass
    today0 = int(dt.datetime.combine(dt.date.today(), dt.time()).timestamp() * 1000)
    out = {"env": ENV, "tradable": TRADABLE, "wallets": [], "cfg": CFG, "ts": int(time.time() * 1000)}
    lot_of_cid = _lot_map()
    for label, client, kid, tradable in wallets():
        wk = kid or ENV
        w = {"label": label, "tradable": tradable, "positions": [], "error": None, "closedToday": [],
             "day": {"fees": 0.0, "realized": 0.0, "fills": 0, "trades_closed": 0, "settled": 0},
             "life": {"realized": 0.0, "closed": 0, "wins": 0, "settled": 0, "settledWins": 0}}
        try:
            fl = _fills(client, kid); pos = _positions(client, kid)
            held = {}
            for p in pos: held.setdefault(p["marketId"], {})[p["outcomeId"]] = p["qty"]
            by = {}
            for f in fl: by.setdefault(f["marketId"], []).append(f)
            for f in fl:
                if f["ts"] >= today0: w["day"]["fees"] += float(f.get("fee") or 0); w["day"]["fills"] += 1
            for mid, fm in by.items():
                hq = {k: v for k, v in held.get(mid, {}).items() if v}
                done = settled_get(wk, mid)
                if done and not hq and done.get("nFills") == len(fm):      # graded and nothing new since: use the stored result
                    for t in done["closed"]: _add_closed(w, t, today0)
                    continue
                m = None; mc = _MS.get((wk, mid))
                if mc and mc[0] > time.time() and not hq: m = mc[1]       # closed market: re-check every 10 min, not every poll
                else:
                    try: m = cached("mkt" + mid, 5, lambda: cat_market(mid))
                    except RateLimited: w["stale"] = True; m = mc[1] if mc else None
                    except Exception as e:
                        m = mc[1] if mc else None
                        if "NOT_FOUND" in str(e) or "404" in str(e):   # finished markets leave the catalog: the grade lives in history
                            m = history_market(client, mid) or m
                    if m and m.get("stale"): w["stale"] = True
                    if m and m.get("status") != "OPEN" and not hq: _MS[(wk, mid)] = (time.time() + 600, m)
                outs = [o["outcomeId"] for o in m["outcomes"]] if m else list(dict.fromkeys(f["outcomeId"] for f in fm))
                if len(outs) != 2:
                    continue                                              # can't pair exits without both outcome ids
                summ = market_summary(fm, outs, m, lot_of_cid)
                for t in summ["closed"]: _add_closed(w, t, today0)
                if summ["settled"] and not hq:
                    settled_put(wk, mid, {"closed": [_strip(t) for t in summ["closed"]], "nFills": len(fm)})
                if not m: continue
                q = quote_from_market(m)
                trip = summ["open"]
                net = (hq.get(outs[0], 0) - hq.get(outs[1], 0)) if hq else 0
                g = game_for(m.get("eventId"))
                over = bool(g and (g["phase"] == "past" or ((g.get("clock") or {}).get("state") == "post")))
                settling = summ["settling"] or (bool(hq) and (m.get("status") in CLOSED_ST or over))
                if settling and m.get("status") in CLOSED_ST: _SETTLING[mid] = f"market {str(m.get('status')).lower()}, game over"
                if not net and not (settling and trip and trip.get("net")): continue
                if not net:
                    side = trip["side"]; n = trip["net"]
                else:
                    side = outs[0] if net > 0 else outs[1]; n = abs(net)
                so = [o for o in q["outcomes"] if o["outcomeId"] == side][0]; opp = [o for o in q["outcomes"] if o["outcomeId"] != side][0]
                live = event_live(m.get("eventId"))
                coef = fee_coef(m.get("fee")); charge = fee_applies(m.get("fee"), live)
                basis = trip["basis"] if trip and trip["side"] == side else None
                if basis is not None and trip.get("lots"):
                    # P&L of what is still held = cash-out minus what THOSE contracts cost (incl. their entry fees).
                    # Partial sells already made are realized P&L (counted in day / lifetime totals, not here).
                    rem_cost = sum(L["cost"] + L["fee"] for L in trip["lots"].values() if L["qty"] > 0)
                    part = rem_cost - basis
                    if abs(part) > 1e-9:
                        w["life"]["realized"] += part
                        if (fm[-1]["ts"] if fm else 0) >= today0: w["day"]["realized"] += part
                    basis = rem_cost
                sale = (so["bid"] or 0) if not settling else 0   # what selling gets now (= 1 - opposite ask)
                xfee = fee(1 - sale, n, coef, charge) if sale else 0
                value = n / 100 * sale
                be = None
                if basis is not None and n:
                    be = basis / (n / 100)
                    for _ in range(6): be = (basis + fee(1 - be, n, coef, charge)) / (n / 100)
                lots = []
                if trip and trip["side"] == side:
                    for L in sorted(trip["lots"].values(), key=lambda L: L["ts"]):
                        if L["qty"] <= 0: continue
                        lots.append({"id": L["id"], "qty": L["qty"], "stake": round(L["cost"], 2), "fees": round(L["fee"], 2),
                                     "price": round(L["cost"] / (L["qty"] / 100), 4), "ts": L["ts"],
                                     "value": round(L["qty"] / 100 * sale, 2)})
                stake = round(sum(L["stake"] for L in lots), 2) if lots else None
                cash_out = round(value - xfee, 2)
                pnl = round(cash_out - basis, 2) if basis is not None and not settling else None
                w["positions"].append({"marketId": mid, "eventId": m.get("eventId"), "market": q["desc"], "type": q["type"], "strike": q["strike"],
                    "side": so["name"], "sideId": side, "oppId": opp["outcomeId"], "oppName": opp["name"], "net": n, "bid": so["bid"], "ask": so["ask"],
                    "state": "settling" if settling else ("paused" if m.get("status") != "OPEN" else "open"), "marketStatus": m.get("status"),
                    "value": round(value, 2), "basis": round(basis, 2) if basis is not None else None, "exitFee": round(xfee, 2),
                    "cashOut": cash_out if not settling else None, "stake": stake, "lots": lots,
                    "pnl": pnl, "pnlPct": round(pnl / basis * 100, 2) if pnl is not None and basis else None,
                    "breakEven": round(be, 3) if be else None, "feeLive": charge, "feeCoef": coef,
                    "avg": round(basis / (n / 100), 3) if basis is not None and n else None,
                    "entryPrice": round(stake / (n / 100), 4) if stake and n else None,
                    "openTs": trip["openTs"] if trip else None,
                    "entryFees": round((trip or {}).get("entry_fees", 0), 2),
                    "feesPaid": round((trip or {}).get("entry_fees", 0) + (trip or {}).get("exit_fees", 0), 2), "adds": (trip or {}).get("adds"),
                    # an exit = buying the other side at its ask (1 - my bid): cash Novig wants up front to exit in ONE order
                    "exitCash": round(n / 100 * (1 - sale) + xfee, 2) if sale else None,
                    # held to settlement: pays n/100 if it wins. Win chance ~ market mid (bid/ask midpoint of my side)
                    "payout": round(n / 100, 2), "winProb": round(((so["bid"] or 0) + (so["ask"] or so["bid"] or 0)) / 2, 3) if so["bid"] and not settling else None,
                    "expValue": round(n / 100 * ((so["bid"] or 0) + (so["ask"] or so["bid"] or 0)) / 2, 2) if so["bid"] and not settling else None,
                    "gameLive": live, "gameDesc": g["desc"] if g else None})
        except Exception as e:
            w["error"] = str(e)[:300]
        if tradable:
            w["cash"] = cash(fresh=False); w["cashError"] = _CASH_ERR.get("msg") if w["cash"] is None else None
            w["exitCashAll"] = round(sum(p["exitCash"] or 0 for p in w["positions"]), 2)
        w["day"] = {k: round(v, 2) if isinstance(v, float) else v for k, v in w["day"].items()}
        unreal = sum(p["pnl"] or 0 for p in w["positions"])
        w["day"]["unrealized"] = round(unreal, 2); w["day"]["total"] = round(w["day"]["realized"] + unreal, 2)
        w["day"]["lossCapHit"] = w["day"]["total"] <= -CFG["daily_loss_cap_usd"]
        ps = w["positions"]; live_ps = [p for p in ps if p["state"] != "settling"]
        w["summary"] = {"openCount": len(ps), "settlingCount": len(ps) - len(live_ps), "openValue": round(sum(p["value"] or 0 for p in live_ps), 2),
            "openBasis": round(sum(p["basis"] or 0 for p in live_ps), 2), "payoutIfAllWin": round(sum(p["payout"] for p in ps), 2),
            "expValue": round(sum(p["expValue"] or 0 for p in live_ps), 2),
            "expReturn": round(sum((p["expValue"] or 0) - (p["basis"] or 0) for p in live_ps if p["basis"] is not None), 2),
            "realizedAll": round(w["life"]["realized"], 2), "totalPnl": round(w["life"]["realized"] + unreal, 2),
            "winRate": round(w["life"]["wins"] / w["life"]["closed"], 4) if w["life"]["closed"] else None, "closedAll": w["life"]["closed"],
            "settledAll": w["life"]["settled"], "settledWins": w["life"]["settledWins"],
            "equity": round((w.get("cash") or 0) + sum(p["value"] or 0 for p in live_ps), 2) if w.get("cash") is not None else None}
        w["life"]["realized"] = round(w["life"]["realized"], 2)
        out["wallets"].append(w)
    return out

# ------------------------------------------------------------------ order intents (idempotent queue)
DB_PATH = os.getenv("NOVIG_ORDERS_DB") or os.path.join(ROOT, "data", "orders.sqlite")   # tests point this at a temp file
def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10); c.row_factory = sqlite3.Row
    c.execute("""create table if not exists intents(idem text primary key, created integer, updated integer, env text, action text,
        market_id text, outcome_id text, usd real, slip real, target_qty integer, ref_price real, max_price real, status text,
        filled_qty integer default 0, cost real default 0, fee real default 0, attempts integer default 0, client_ids text default '[]',
        message text default '', log text default '[]')""")
    cols = {r[1] for r in c.execute("pragma table_info(intents)")}
    for col in ("label", "kind", "event_desc", "outcome_name", "source", "lot"):
        if col not in cols: c.execute(f"alter table intents add column {col} text default ''")
    for col, typ in (("qty_req", "integer default 0"), ("pct", "real default 0"), ("riding", "integer default 0")):
        if col not in cols: c.execute(f"alter table intents add column {col} {typ}")
    c.commit(); return c
DB = _db(); Q = queue.Queue(); _settled_db()

def _upd(idem, **kw):
    with _LOCK:
        if "log" in kw:
            row = DB.execute("select log from intents where idem=?", (idem,)).fetchone()
            lg = json.loads(row["log"]) + [f"{time.strftime('%H:%M:%S')} {kw.pop('log')}"]; kw["log"] = json.dumps(lg[-30:])
        kw["updated"] = int(time.time() * 1000)
        DB.execute(f"update intents set {','.join(k + '=?' for k in kw)} where idem=?", (*kw.values(), idem)); DB.commit()

def intent(idem):
    with _LOCK: r = DB.execute("select * from intents where idem=?", (idem,)).fetchone()
    if not r: return None
    d = dict(r); d["log"] = json.loads(d["log"]); d["client_ids"] = json.loads(d["client_ids"]); return d

def recent(n=30):
    with _LOCK: ids = [r["idem"] for r in DB.execute("select idem from intents order by created desc limit ?", (n,)).fetchall()]
    return [intent(i) for i in ids]

SELL_ACTS = ("SELL_ALL", "SELL_HALF", "SELL_USD", "SELL_PCT", "SELL_QTY")
_NEED_CASH = {}   # (marketId, outcomeId) -> (ts, cash, message): last exit that stopped for cash
def risk_check(lab, mid, oid):
    """Buys that deserve a second look: the last ~2:00 of a game, or long shots priced under ~10c (odds > 10)."""
    why = []
    hb = _cache.get("book" + str(mid)); px = None
    if hb:
        o = next((x for x in hb[1].get("outcomes", []) if x["outcomeId"] == oid), None); px = o and o.get("ask")
    if px and px < CFG["risky_price"]:
        why.append(f"long shot: buying at {px * 100:.1f}c (odds {1 / px:.1f}); it pays only if this side comes back to win")
    ev = (hb[1].get("eventId") if hb else None)
    g = game_for(ev) if ev else None
    ck = (g or {}).get("clock") or {}
    if ck.get("state") == "in" and ck.get("secs") is not None and ((ck.get("period") or 0) >= 5 or ((ck.get("period") or 0) == 4 and ck["secs"] <= CFG["risky_clock_s"])):
        why.append(f"{ck.get('clock')} left in the game: little time to sell before it ends, and the market can close any second")
    return why

def submit(b):
    """b: idem, action BUY|SELL_ALL|SELL_HALF|SELL_USD|SELL_PCT|SELL_QTY, marketId, outcomeId (BUY: side to buy; SELL: side held),
    usd, pct (SELL_PCT), qty + lot (SELL_QTY: sell one buy lot), slipCents. Confirms: confirmSpecial, overrideLossCap, confirmRisky."""
    idem = str(b.get("idem") or "")[:64]
    if len(idem) < 8: return {"ok": False, "error": "missing idempotency key"}
    act = b.get("action"); usd = float(b.get("usd") or 0); slip = float(b.get("slipCents") or CFG["default_slip_cents"])
    pct = float(b.get("pct") or 0); qty_req = int(float(b.get("qty") or 0)); lot = str(b.get("lot") or "")[:64]
    if not TRADABLE: return {"ok": False, "error": "ORDERS_OFF", "message": f"Orders are disabled in {ENV} mode (see README: live trading key)."}
    if act not in ("BUY",) + SELL_ACTS: return {"ok": False, "error": "bad action"}
    if act == "SELL_USD" and not 0 < usd <= 10000: return {"ok": False, "error": "sell amount must be > $0"}
    if act == "SELL_PCT" and not 0 < pct <= 100: return {"ok": False, "error": "sell percent must be 1-100"}
    if act == "SELL_QTY" and qty_req < 1: return {"ok": False, "error": "contracts to sell must be >= 1"}
    old = intent(idem)
    if old: return {"ok": True, "duplicate": True, "intent": old}
    # name the exact market on every order; anything that is not a plain single-game line needs its own confirm
    lab = label_for(b.get("marketId"), b.get("outcomeId"), b.get("eventDesc"))
    if act == "BUY" and lab["kind"] != "GAME" and not b.get("confirmSpecial"):   # exits are never held up
        return {"ok": False, "error": "CONFIRM_SPECIAL", "kind": lab["kind"], "label": lab["label"],
                "message": f"This is a {lab['kind'].lower()} market, not a single-game bet: {lab['label']}. Confirm to send."}
    now = int(time.time() * 1000)
    if act == "BUY":
        if not 0 < usd <= CFG["max_order_usd"]: return {"ok": False, "error": "PER_ORDER_CAP", "message": f"Max ${CFG['max_order_usd']:.0f} per order."}
        # double-click guard: the same buy (market, side, $) from a different click within ~1.5s is refused
        with _LOCK:
            dup = DB.execute("select idem, created from intents where action='BUY' and market_id=? and outcome_id=? and abs(usd-?)<0.001 and created>? and env=? order by created desc limit 1",
                             (b["marketId"], b["outcomeId"], usd, now - int(CFG["double_click_s"] * 1000), ENV)).fetchone()
        if dup and not b.get("confirmRepeat"):
            return {"ok": False, "error": "DOUBLE_SUBMIT", "message": f"Same ${usd:g} buy of {lab['outcome'] or 'this side'} was sent {(now - dup['created']) / 1000:.1f}s ago - ignored as a double click. If you meant to buy twice, wait a second and click again."}
        why = risk_check(lab, b.get("marketId"), b.get("outcomeId"))
        if why and not b.get("confirmRisky"):
            return {"ok": False, "error": "CONFIRM_RISKY", "label": lab["label"], "reasons": why, "message": "Are you sure? " + "; ".join(why) + "."}
        try:
            pf = portfolio(); w = [x for x in pf["wallets"] if x["tradable"]][0]
            if w["day"]["lossCapHit"] and not b.get("overrideLossCap"):   # soft cap: warn, he can override per order
                return {"ok": False, "error": "LOSS_CAP_CONFIRM", "message": f"Day P&L {w['day']['total']:+.2f} is past your -${CFG['daily_loss_cap_usd']:.0f} daily loss cap. Confirm to keep buying."}
        except IndexError: pass
    else:
        # a sell that just stopped for cash would fail again the same way: say why instead of sending it again
        nc = _NEED_CASH.get((b.get("marketId"), b.get("outcomeId")))
        if nc and time.time() - nc[0] < 30:
            c_now = cash()
            if c_now is None or c_now <= nc[1] + 0.01:
                return {"ok": False, "error": "NEED_CASH", "message": nc[2] + " Not sent again: add cash or sell a smaller amount (Sell $N / %)."}
        st = _SETTLING.get(b.get("marketId"))
        if st: return {"ok": False, "error": "SETTLING", "message": f"{lab['label']}: {st}. Nothing to sell; Novig pays it out at the final."}
    if not 0 < slip <= 10: return {"ok": False, "error": "slippage must be 0-10 cents"}
    with _LOCK:
        cur = DB.execute("insert or ignore into intents(idem,created,updated,env,action,market_id,outcome_id,usd,slip,status,label,kind,event_desc,outcome_name,source,lot,qty_req,pct) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (idem, now, now, ENV, act, b["marketId"], b["outcomeId"], usd, slip, "queued",
                          lab["label"], lab["kind"], lab["event"], lab["outcome"], str(b.get("source") or "ui")[:40], lot, qty_req, pct))
        DB.commit()
    if cur.rowcount == 0: return {"ok": True, "duplicate": True, "intent": intent(idem)}
    Q.put(idem); return {"ok": True, "intent": intent(idem)}
_SETTLING = {}   # marketId -> reason, set when Novig says the market is closed (game over)

GAME_TYPES = ("MONEY", "SPREAD", "TOTAL", "TEAM_TOTAL")
def label_for(mid, oid, event_desc=None):
    """Plain-English market name + kind: GAME (single game line), FUTURE (season-long, e.g. Super Bowl winner),
    PARLAY (combo), OTHER. Built from the catalog so the browser can't mislabel it."""
    hb = _cache.get("book" + str(mid))   # the ticket's book is almost always cached already (no extra call before an order)
    if hb and time.time() - hb[0] < 120: q = hb[1]; league = ""
    else:
        try: m = cached("mkt" + str(mid), 30, lambda: cat_market(mid, priority=True))
        except Exception: m = None
        if not m: return {"kind": "OTHER", "label": f"unknown market {str(mid)[-6:]}", "event": event_desc or "", "outcome": ""}
        q = {**quote_from_market(m), "eventId": m.get("eventId")}; league = (m.get("league") or "").upper()
    o = next((x for x in q["outcomes"] if x["outcomeId"] == oid), None)
    on = o["name"] if o else "?"; t = (q.get("type") or "").upper(); desc = q.get("desc") or ""; ev = ""
    g = game_for(q.get("eventId"))
    if g: ev = g["desc"]
    known = bool(ev)
    if not ev and q.get("eventId"):   # not in today's list (finished / tomorrow): ask the catalog for the event's name
        try: ev = (cached("ev" + q["eventId"], 3600, lambda: _cat(f"/events/{q['eventId']}", priority=True)) or {}).get("description") or ""
        except Exception: ev = ""
        known = bool(ev) and " @ " in ev     # the catalog itself names it as a two-team game
    ev = ev or event_desc or ""   # GAME only when the server itself knows the event as a listed game
    if "PARLAY" in t or "COMBO" in t or league == "COMBO": kind = "PARLAY"
    elif t in GAME_TYPES and known and " @ " in ev and len(q["outcomes"]) == 2: kind = "GAME"
    elif not known: kind = "FUTURE" if t not in GAME_TYPES else "OTHER"
    else: kind = "OTHER"
    vs = ev.replace(" @ ", " at ")
    if t == "MONEY": lab = f"{on} to win ({vs})"
    elif t == "SPREAD": lab = f"{on} spread ({vs})"
    elif t == "TOTAL": lab = f"{on} total points ({vs})"
    elif t == "TEAM_TOTAL": lab = f"{desc.replace(' TEAM_TOTAL', '')} team points: {on} ({vs})"
    else: lab = f"{on}: {desc or t}" + (f" ({vs})" if vs else "")
    return {"kind": kind, "label": lab, "event": ev, "outcome": on}

def backfill_labels(limit=200, pause=0.3):
    """Older orders were saved without a market name (empty label / event_desc / outcome_name). Fill them in from the
    catalog (settled markets stay readable there), a few per second so it never competes with trading."""
    with _LOCK: rows = DB.execute("select idem, market_id, outcome_id, event_desc from intents where (label is null or label='' or outcome_name is null or outcome_name='') order by created desc limit ?", (limit,)).fetchall()
    n = 0
    for r in rows:
        try:
            lab = label_for(r["market_id"], r["outcome_id"], r["event_desc"] or None)
            if lab["outcome"] and lab["outcome"] != "?":
                _upd(r["idem"], label=lab["label"], kind=lab["kind"], event_desc=lab["event"], outcome_name=lab["outcome"]); n += 1
        except Exception: pass
        time.sleep(pause)
    return n

def _find_by_client(cid):
    """Did an order with this clientId reach the exchange? -> (orderId|None, fills[])"""
    fl = [f for f in _fills(W, None, max_age=0) if f.get("clientId") == cid]
    if fl: return fl[0]["orderId"], fl
    r = _unwrap(W.orders(limit=50))
    for o in (r.get("items", []) if isinstance(r, dict) else []):
        if o.get("clientId") == cid: return o["orderId"], []
    return None, []

def _fills_for(oid, wait=6.0, want=None):
    """Poll until the order is done, then return its fills. Order status lags ~3s behind fills (paper, Oct 25:
    PENDING for 3s+ while the fill was readable after ~1s), so also check fills every ~0.75s and stop as soon
    as the whole qty (`want`) has filled. Partial IOC fills still wait for a terminal status (or `wait`)."""
    t0 = time.time(); st = None; got = None; n = 0
    while time.time() - t0 < wait:
        o = _unwrap(W.order(oid))
        st = o.get("status") if isinstance(o, dict) else None
        if st in ("FILLED", "CANCELED", "REJECTED", "EXPIRED"): break
        n += 1
        if want and n % 3 == 0:
            r = _unwrap(W.fills(order=oid))
            if not _err(r) and isinstance(r, dict) and sum(f["qty"] for f in r.get("items", [])) >= want: got = r.get("items", []); break
        time.sleep(0.25)
    if got is None:
        for i in range(3):
            r = _unwrap(W.fills(order=oid))
            if not _err(r): break
            time.sleep(0.6 * (i + 1))
        got = r.get("items", []) if isinstance(r, dict) else []
    remember_fills(W.key_id if ENV == "production" else None, got)
    return got

def _net(mid, side, other):
    pos = _positions(W, None); h = {p["outcomeId"]: p["qty"] for p in pos if p["marketId"] == mid}
    return h.get(side, 0) - h.get(other, 0)

def cash(fresh=True):
    """Tradable sub-account cash (USD) or None if unreadable. GET /v3/account/subaccounts/{keyId}/balance works with
    the sub-account's own trading key (docs: 'Key: any', trading key reads its own sub-account)."""
    def get():
        errs = []
        for cl in ([W] + ([R] if ENV == "production" and R is not W and R and R.has_key else [])):
            r = _unwrap(cl.subaccount_balance(W.key_id), W.key_id)
            if not _err(r) and isinstance(r, dict) and r.get("balance") is not None:
                _CASH_ERR.pop("msg", None); return {"cash": float(r["balance"])}
            errs.append(f"{'trading' if cl is W else 'read'} key: {r.get('status') if isinstance(r, dict) else '?'} {(r.get('code') or r.get('error') or '') if isinstance(r, dict) else str(r)[:60]}")
        _CASH_ERR["msg"] = "balance unreadable (" + "; ".join(errs) + ")"; raise RuntimeError(_CASH_ERR["msg"])
    if not (W and W.has_key): _CASH_ERR["msg"] = "no trading key"; return None
    try: return (get() if fresh else cached("cash", 3, get))["cash"]
    except Exception as e:
        _CASH_ERR.setdefault("msg", str(e)[:160]); return None
_CASH_ERR = {}

def per_ctr_cash(price, coef=0.06):
    """Cash Novig wants up front per contract for a taker buy at `price` (cost + fee). Exits are buys of the
    other side, so an exit needs this cash up front too; paired contracts pay back $0.01 each the moment they fill."""
    return (price + coef * price * (1 - price)) / 100

def _is_insufficient(r): return (r.get("code") or r.get("error")) == "INSUFFICIENT_BALANCE"

def execute(idem):
    """BUY: one IOC at ask+slip, partial fills re-quoted up to max_attempts; INSUFFICIENT_BALANCE stops at once.
    SELL: buys the opposite side in cash-sized chunks. Each chunk is sized from the live balance
    (floor(cash / per-contract cash)); every filled chunk pairs off contracts, which Novig pays out immediately
    ($0.01 per pair, verified on paper Oct 25), so the next chunk can be bigger. Stops when done, no liquidity,
    price outside the limit, or cash can't cover even 1 contract."""
    it = intent(idem)
    if not it or it["status"] not in ("queued",): return
    if time.time() * 1000 - it["created"] > 30_000:
        return _upd(idem, status="expired", message="queued >30s (stale price) - not sent", log="expired before send")
    try:
        try: q = book(it["market_id"], priority=True)
        except RateLimited:
            h = _cache.get("book" + it["market_id"])
            if not h or time.time() - h[0] > 5: raise
            q = h[1]; _upd(idem, log=f"quote throttled; using {time.time() - h[0]:.1f}s-old quote (limit price still caps the fill)")
        outs = {o["outcomeId"]: o for o in q["outcomes"]}
        mine = outs[it["outcome_id"]]; other = [o for k, o in outs.items() if k != it["outcome_id"]][0]
        coef = fee_coef(q.get("fee"))   # cash sizing always counts the fee (over-reserving is safe, under-reserving gets rejected)
        selling = it["action"] != "BUY"
        mst = q.get("status")
        if mst and mst != "OPEN":
            if mst in ("CLOSED", "SETTLED", "VOIDED", "FINAL"):
                _SETTLING[it["market_id"]] = f"market {mst.lower()} (game over)"
                return _upd(idem, status="settling", message=f"Game is over (market {mst}). Not sent; your position is settling and Novig pays it at the final.", log=f"market {mst} - stop")
            return _upd(idem, status="rejected", message=f"Market is {mst} right now (paused). Not sent; try again when it reopens.", log=f"market {mst} - stop")
        if not selling:
            buy_id, ref = mine["outcomeId"], mine["ask"]
            if not ref: return _upd(idem, status="rejected", message="no offers on this side", log="no ask")
            target = int(it["usd"] * 100 / ref)
        else:
            net = _net(it["market_id"], mine["outcomeId"], other["outcomeId"])
            if net <= 0: return _upd(idem, status="rejected", message="no net position to sell", log=f"net={net}")
            buy_id, ref = other["outcomeId"], other["ask"]
            if not ref: return _upd(idem, status="rejected", message="nobody bidding for your side right now (no liquidity)", log="no bid")
            if it["action"] == "SELL_USD":   # $N of proceeds at today's sell price (1 - opposite ask), never more than held
                target = min(net, max(1, int(math.ceil(it["usd"] * 100 / max(0.001, 1 - ref)))))
            elif it["action"] == "SELL_PCT": target = min(net, max(1, int(round(net * float(it.get("pct") or 0) / 100))))
            elif it["action"] == "SELL_QTY": target = min(net, max(1, int(it.get("qty_req") or 0)))
            else: target = net if it["action"] == "SELL_ALL" else max(1, net // 2)
        max_price = snap(min(0.999, ref + it["slip"] / 100), "down")
        if not selling and target * max_price / 100 > CFG["max_order_usd"] + 0.01:
            target = int(CFG["max_order_usd"] * 100 / max_price)
        _upd(idem, status="working", target_qty=target, ref_price=ref, max_price=max_price,
             log=f"{it['action']} target {target} ctr, ref {ref:.3f}, limit <= {max_price:.3f}")
        filled = cost = fees = 0; cids = []; sends = 0; fails = 0; dry = 0; cap = None; why = ""; last_cash = None; need_have = None
        pc = per_ctr_cash(max_price, coef)
        max_sends = CFG["max_exit_rounds"] if selling else CFG["max_attempts"]
        while sends < max_sends and fails < CFG["max_attempts"]:
            remaining = target - filled
            if selling:
                remaining = min(remaining, _net(it["market_id"], mine["outcomeId"], other["outcomeId"]))
            if remaining <= 0: break
            if sends or fails:
                try: q = book(it["market_id"], priority=True)
                except RateLimited: why = "requote throttled"; _upd(idem, log="requote throttled - stop"); break
                px = [o for o in q["outcomes"] if o["outcomeId"] == buy_id][0]["ask"]
                if not px: why = "no liquidity"; _upd(idem, log="no offers left - stop"); break
                if px > max_price:
                    why = f"price moved to {px:.3f}, outside your limit {max_price:.3f}"; _upd(idem, log=f"requote {px:.3f} outside limit {max_price:.3f} - stop"); break
            qty = remaining
            if selling:
                last_cash = cash()
                if last_cash is not None:
                    afford = int(math.floor(last_cash * 0.995 / pc))
                    if afford < qty: _upd(idem, log=f"cash ${last_cash:.2f} covers {afford} of {qty} ctr (${qty * pc:.2f} needed) - chunking")
                    qty = min(qty, afford)
                if cap is not None: qty = min(qty, cap)
                if qty < 1: why = "cash"; _upd(idem, log=f"cash ${last_cash if last_cash is not None else 0:.2f} < 1 contract - stop"); break
            sends += 1
            cid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"novig-intent:{idem}:{sends + fails}")); cids.append(cid)
            _upd(idem, attempts=sends + fails, client_ids=json.dumps(cids), log=f"send #{sends + fails}: buy {qty} @<={max_price:.3f} IOC ({cid[-6:]})")
            order = {"outcomeId": buy_id, "price": f"{max_price:.3f}", "qty": int(qty), "tif": "IOC", "clientId": cid}
            oid = None
            try:
                r = W.place_order(order)
                if _err(r):
                    code = r.get("code") or r.get("error"); _upd(idem, log=f"rejected {r.get('status')} {code}: {str(r.get('message', ''))[:120]}")
                    if r.get("status") in (401, 403, 451) or code in ("REFUSED_NOT_PAPER",): _upd(idem, status="rejected", message=f"{code}: {r.get('message', '')}"); return
                    if code == "MARKET_CLOSED" or (r.get("status") == 409 and code != "MARKET_INACTIVE"):   # game over: stop at once, never retry
                        _SETTLING[it["market_id"]] = "market closed (game over)"
                        m0 = f"Game is over (market closed) after {filled} contracts." if filled else "Game is over (market closed). Nothing sent."
                        return _upd(idem, status="settling" if not filled else "partial", filled_qty=filled, cost=round(cost, 5), fee=round(fees, 5),
                                    message=m0 + " Your position is settling; Novig pays it at the final.", log="MARKET_CLOSED - stop (no retry)")
                    if code == "MARKET_INACTIVE":
                        why = "market paused (inactive)"; _upd(idem, log="MARKET_INACTIVE - stop (no retry)"); break
                    if _is_insufficient(r):
                        if not selling:
                            cb = cash(); need = qty * per_ctr_cash(max_price, coef)
                            msg = f"Not enough cash: this buy needs ~${need:.2f}" + (f", you have ${cb:.2f}" if cb is not None else "") + ". Nothing bought."
                            if filled: msg = f"Bought {filled}/{target}; then out of cash" + (f" (have ${cb:.2f})" if cb is not None else "") + "."
                            return _upd(idem, status="partial" if filled else "rejected", filled_qty=filled, cost=round(cost, 5), fee=round(fees, 5), message=msg, log="insufficient balance - stop (no retry)")
                        # never resend the same size: re-read cash and size strictly smaller, or stop and say why
                        sends -= 1; fails += 1; cb = cash(); need = qty * pc
                        afford = int(math.floor(cb * 0.99 / pc)) if cb is not None else qty // 2
                        cap = max(0, min(qty - 1, qty // 2 if cb is None else afford))
                        need_have = (need, cb); last_cash = cb
                        _upd(idem, log=f"insufficient balance for {qty} ctr (need ${need:.2f}, have " + (f"${cb:.2f}" if cb is not None else "?") + f") - " + (f"retry smaller: {cap}" if cap >= 1 else "stop"))
                        why = "cash"
                        if cap < 1: break
                        continue
                    sends -= 1; fails += 1; time.sleep(0.6); continue
                if r.get("dryRun"): _upd(idem, status="rejected", message="dry run (orders not enabled)"); return
                oid = r.get("orderId")
            except Exception as ex:   # timeout / network: reconcile, never blind-resend
                _upd(idem, log=f"send error {type(ex).__name__} - reconciling by clientId")
                for _ in range(3):
                    time.sleep(1.0)
                    try:
                        oid, fl = _find_by_client(cid)
                        if oid: break
                    except Exception as ex2: _upd(idem, log=f"reconcile error {type(ex2).__name__}")
                if not oid: _upd(idem, log="not found on exchange -> treated as not sent"); sends -= 1; fails += 1; continue
            fl = _fills_for(oid, want=int(qty)) if oid else []
            fq = sum(f["qty"] for f in fl); fc = sum(float(f["cost"]) for f in fl); ff = sum(float(f.get("fee") or 0) for f in fl)
            filled += fq; cost += fc; fees += ff
            _upd(idem, filled_qty=filled, cost=round(cost, 5), fee=round(fees, 5),
                 log=f"#{sends + fails} filled {fq}/{qty}" + (f" avg {fc / fq * 100:.3f}" if fq else ""))
            if fq: cap = None if fq >= qty else cap; why = ""   # a full chunk clears any halving cap; cash re-read next round
            dry = 0 if fq else dry + 1
            if dry >= 2: why = "no liquidity at your limit"; break
        st = "filled" if filled >= target else ("partial" if filled else "unfilled")
        left = 0; riding = 0
        if selling:
            netnow = _net(it["market_id"], mine["outcomeId"], other["outcomeId"])
            goal = 0 if it["action"] == "SELL_ALL" else max(0, (filled + netnow) - target)   # SELL_HALF / SELL_USD: keep the rest
            left = max(0, netnow - goal); riding = max(0, netnow)
            if filled and left <= 0: st = "filled"
        avg = cost / filled * 100 if filled else None
        msg = f"{filled}/{target} contracts" + (f", paid avg {avg:.3f}" if avg else "") + (f" (= sold @ {1 - avg:.3f})" if avg and selling else "") + f", fees ${fees:.2f}"
        if selling and left > 0:
            cb = cash() if last_cash is None or filled else last_cash
            need = left * per_ctr_cash(max_price, coef)
            if why == "cash":
                msg = (f"Not enough cash to sell: need ${need:.2f}, have " + (f"${cb:.2f}" if cb is not None else "$?") + f" (selling = buying the other side, paid up front). "
                       f"Sold {filled} of {target}; {left} left" + (f" (~${max(0, need - cb):.2f} more cash needed)" if cb is not None else "") + ". " + msg)
                _NEED_CASH[(it["market_id"], it["outcome_id"])] = (time.time(), cb if cb is not None else 0.0, f"Not enough cash to sell: need ${need:.2f}, have " + (f"${cb:.2f}" if cb is not None else "$?") + ".")
            elif why:
                msg = f"Sold {filled} of {target}, stopped: {why}. {left} left. " + msg
        if selling and riding > 0 and it["action"] != "SELL_ALL":
            msg += f". {riding} contracts still ride to the final (pay ${riding / 100:.2f} if {mine['name']} wins, $0 if not)"
        if selling and filled: _NEED_CASH.pop((it["market_id"], it["outcome_id"]), None)
        _upd(idem, status=st, message=msg, riding=riding, log=f"done: {st}" + (f" ({why})" if why else ""))
    except Exception as e:
        if not isinstance(e, RateLimited): traceback.print_exc()
        print(time.strftime("%H:%M:%S"), "[order]", idem[:8], type(e).__name__, ascii(str(e)[:120]), flush=True)
        sent = (intent(idem) or {}).get("attempts", 0)
        _upd(idem, status="error", message=f"{type(e).__name__}: {str(e)[:200]}" + (" - check position (order may have been sent)" if sent else " - not sent, tap again"), log="error")

def worker():
    while True:
        try: idem = Q.get(timeout=2)
        except queue.Empty:   # sweeper: nothing may sit in 'queued' silently
            with _LOCK: stuck = [r["idem"] for r in DB.execute("select idem from intents where status='queued' and created < ?", (int(time.time() * 1000) - 3000,)).fetchall()]
            for i in stuck: Q.put(i)
            continue
        try: execute(idem)
        except Exception as e:
            traceback.print_exc()
            try: _upd(idem, status="error", message=f"{type(e).__name__}: {str(e)[:200]}", log="worker error")
            except Exception: pass

def reconcile_stuck(statuses=("working", "queued", "check")):
    """Restart safety: intents that may have sends in flight are reconciled from the exchange, never resent."""
    with _LOCK: rows = DB.execute(f"select idem, client_ids, status from intents where status in ({','.join('?' * len(statuses))})", statuses).fetchall()
    for r in rows:
        msg = "server restarted mid-order; reconciled from exchange, not resent"
        try:
            got = 0
            for cid in json.loads(r["client_ids"]):
                _, fl = _find_by_client(cid); got += sum(f["qty"] for f in fl)
            _upd(r["idem"], status="reconciled", filled_qty=got, message=msg + f" ({got} contracts filled)", log="restart reconcile ok")
        except Exception as e:
            _upd(r["idem"], status="check", message=f"restart: could not verify yet ({str(e)[:80]}); retrying - not resent", log="reconcile retry")

def start():
    reconcile_stuck()
    threading.Thread(target=backfill_labels, daemon=True).start()
    def bg():
        while True:
            time.sleep(10)
            try: reconcile_stuck(("check",))
            except Exception: pass
    threading.Thread(target=bg, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=trigger_watcher, daemon=True).start()

# ------------------------------------------------------------------ local triggers ("limit orders" that live on OUR side, not on Novig's book)
# The watcher checks armed triggers every ~2s against the live quote and, the moment one is hit, submits a normal
# IOC intent (same slippage cap, same idempotency: idem = trg-<id>, so a trigger can only ever fire once).
TRIG_CONDS = {"odds_gte": "odds ≥", "odds_lte": "odds ≤", "profit_pct_gte": "profit ≥ %", "profit_pct_lte": "loss ≤ % (stop)"}
DB.execute("""create table if not exists triggers(id text primary key, created integer, env text, market_id text, outcome_id text, action text,
    usd real, cond text, target real, slip real, status text, label text default '', idem text default '', message text default '', expires integer)"""); DB.commit()

def triggers(n=50):
    with _LOCK: rows = DB.execute("select * from triggers where env=? order by created desc limit ?", (ENV, n)).fetchall()
    return [dict(r) for r in rows]

def add_trigger(b):
    if not TRADABLE: return {"ok": False, "error": "ORDERS_OFF", "message": "orders are off in this mode"}
    act = b.get("action"); cond = b.get("cond")
    if act not in ("BUY", "SELL_ALL", "SELL_HALF", "SELL_USD"): return {"ok": False, "error": "bad action"}
    if cond not in TRIG_CONDS: return {"ok": False, "error": "bad condition"}
    if cond.startswith("profit") and act == "BUY": return {"ok": False, "error": "profit/loss targets are for sells"}
    try: target = float(b.get("target"))
    except (TypeError, ValueError): return {"ok": False, "error": "target must be a number"}
    usd = float(b.get("usd") or 0)
    if act == "BUY" and not 0 < usd <= CFG["max_order_usd"]: return {"ok": False, "error": "PER_ORDER_CAP", "message": f"Max ${CFG['max_order_usd']:.0f} per order."}
    lab = label_for(b.get("marketId"), b.get("outcomeId"), b.get("eventDesc"))
    if act == "BUY" and lab["kind"] != "GAME": return {"ok": False, "error": "triggers can only buy single-game lines"}
    tid = uuid.uuid4().hex[:12]; hrs = min(24.0, float(b.get("hours") or 6))
    with _LOCK:
        DB.execute("insert into triggers values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (tid, int(time.time() * 1000), ENV, b["marketId"], b["outcomeId"], act, usd, cond, target,
                   float(b.get("slipCents") or CFG["default_slip_cents"]), "armed", lab["label"], "", "", int((time.time() + hrs * 3600) * 1000))); DB.commit()
    return {"ok": True, "trigger": next(t for t in triggers() if t["id"] == tid)}

def cancel_trigger(tid):
    with _LOCK: DB.execute("update triggers set status='canceled', message='canceled by you' where id=? and status='armed'", (tid,)); DB.commit()
    return {"ok": True}

def _trig_set(tid, **kw):
    with _LOCK: DB.execute(f"update triggers set {','.join(k + '=?' for k in kw)} where id=?", (*kw.values(), tid)); DB.commit()

def _check_trigger(t):
    if time.time() * 1000 > t["expires"]: return _trig_set(t["id"], status="expired", message="expired unfired")
    q = book(t["market_id"]); side = next((o for o in q["outcomes"] if o["outcomeId"] == t["outcome_id"]), None)
    if not side: return
    if q.get("status") not in (None, "OPEN"): return _trig_set(t["id"], status="expired", message=f"market {q.get('status')}")
    hit = False; now_txt = ""
    if t["cond"].startswith("odds"):
        px = side["ask"] if t["action"] == "BUY" else side["bid"]   # buy at ask, sell gets bid
        if not px: return
        odds = 1 / px; now_txt = f"odds {odds:.2f}"
        hit = odds >= t["target"] if t["cond"] == "odds_gte" else odds <= t["target"]
    else:
        pf = portfolio(); pos = next((p for w in pf["wallets"] if w["tradable"] for p in w["positions"] if p["marketId"] == t["market_id"] and p["sideId"] == t["outcome_id"]), None)
        if not pos: return _trig_set(t["id"], status="expired", message="no position left to sell")
        if pos["pnl"] is None or not pos["basis"]: return
        pct = pos["pnl"] / pos["basis"] * 100; now_txt = f"P&L {pct:+.1f}%"
        hit = pct >= t["target"] if t["cond"] == "profit_pct_gte" else pct <= -abs(t["target"])
    if not hit: return _trig_set(t["id"], message=f"watching: {now_txt}")
    idem = "trg-" + t["id"]
    r = submit({"idem": idem, "action": t["action"], "marketId": t["market_id"], "outcomeId": t["outcome_id"], "usd": t["usd"], "slipCents": t["slip"], "source": "trigger"})
    if r.get("ok"): _trig_set(t["id"], status="fired", idem=idem, message=f"fired at {now_txt}")
    else: _trig_set(t["id"], status="blocked", message=f"hit at {now_txt} but not sent: {r.get('message') or r.get('error')}")

def trigger_watcher():
    while True:
        time.sleep(2)
        try:
            with _LOCK: armed = [dict(r) for r in DB.execute("select * from triggers where env=? and status='armed'", (ENV,)).fetchall()]
            for t in armed:
                try: _check_trigger(t)
                except RateLimited: pass
                except Exception as e: _trig_set(t["id"], message=f"check error: {str(e)[:80]}")
        except Exception: traceback.print_exc()

def status():
    return {"catalog": CAT.state(), "env": ENV, "trigConds": TRIG_CONDS, "host": C.host, "tradable": TRADABLE, "cfg": CFG, "readKey": bool(R and R.has_key), "tradingKey": bool(W and W.has_key),
            "wallets": [w[0] for w in wallets()]}
