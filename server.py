"""Novig Functional Design System server.  python3 server.py [port]   (default 8601)
Serves static/index.html and a JSON API that the widgets consume. Reads go to the
PAPER host (live, signed when NOVIG_API_KEY/NOVIG_API_SECRET are set). Order/cancel
endpoints are PREVIEW-ONLY here: they validate + price the ticket and return what
*would* be sent. Nothing is ever POSTed/DELETEd to Novig from this server."""
import csv, io, json, os, sys, threading, time, traceback
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from novig.client import Novig, trading_client, cost_usd, taker_fee_usd, american, on_grid, snap_down, future_sport_hook, FUTURE_SPORTS
from novig import samples, pbp, journal as J, trader as TR
JDB = J.db()

ROOT = os.path.dirname(os.path.abspath(__file__)); STATIC = os.path.join(ROOT, "static")
N = Novig()   # management key (paper): balances, sub-accounts, catalog
T = trading_client()  # sub-account trading key: orders, fills, positions (writes still preview-only here)
_cache = {}; _lock = threading.Lock()
def cached(key, ttl, fn):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl: return hit[1]
    v = fn()
    with _lock: _cache[key] = (time.time(), v)
    return v

def unwrap(r):
    """Management keys get per-wallet maps {keyId: body}; flatten to one body (or the first wallet)."""
    if isinstance(r, dict) and len(r) == 1:
        (k, v), = r.items()
        if len(k) == 36 and k.count("-") == 4: return v
    return r

def is_err(r): return isinstance(r, dict) and r.get("ok") is False

def live_or_sample(name, live, sample, empty):
    """Returns {source, data}. If live call errored or came back empty, show contract-shaped sample (labelled)."""
    if is_err(live): return {"source": "sample", "why": live.get("error") or live.get("code"), "data": sample}
    if empty(live): return {"source": "sample", "why": "live response empty on this paper account", "live": live, "data": sample}
    return {"source": "live", "data": live}

def football(days=7):
    now = int(time.time() * 1000); end = now + days * 86400_000
    def get():
        ev, after = [], None
        for _ in range(20):
            pg = N.events(league="NFL,NCAAF", startsAfter=now - 5 * 3600_000, startsBefore=end, limit=1000, after=after)
            ev += pg["items"]; after = pg.get("next")
            if not after or not pg["items"]: break
        live_ev = N.events(league="NFL,NCAAF", eventStatus="OPEN_INGAME", limit=200)["items"]
        seen = {e["eventId"] for e in ev}; ev += [e for e in live_ev if e["eventId"] not in seen and e.get("status") == "OPEN_INGAME" and now - 12 * 3600_000 < e["startsTs"] < end]
        mk = N.all_markets(league="NFL,NCAAF", marketType="MONEY,SPREAD,TOTAL", startsAfter=now - 5 * 3600_000, startsBefore=end)
        by = {}
        for m in mk: by.setdefault(m["eventId"], []).append(m)
        parts = {}
        if N.has_key:
            after = None
            for _ in range(10):
                p = unwrap(N.participants(league="NFL,NCAAF", limit=1000, after=after, startsAfter=now - 5 * 3600_000, startsBefore=end))
                if is_err(p): break
                for it in p.get("items", []): parts[it["eventId"]] = it
                after = p.get("next")
                if not after or not p.get("items"): break
        for e in ev:
            ms = by.get(e["eventId"], [])
            # keep the main line per type: the one with most volume, else most liquidity
            main = {}
            for m in ms:
                t = m["marketType"]; score = (m["volume"], sum(1 for o in m["outcomes"] if "bid" in o))
                if t not in main or score > main[t][0]: main[t] = (score, m)
            e["markets"] = {t: v[1] for t, v in main.items()}
            e["marketCount"] = len(ms); e["volume"] = sum(m["volume"] for m in ms); e["openInterest"] = sum(m["openInterest"] for m in ms)
            e["participants"] = parts.get(e["eventId"])
        ev.sort(key=lambda e: e["startsTs"])
        return {"source": "live", "host": N.host, "from": now, "to": end, "events": ev}
    return cached(f"fb{days}", 30, get)

def market_detail(mid):
    with ThreadPoolExecutor(4) as ex:
        f = {k: ex.submit(fn) for k, fn in {
            "market": lambda: N.market(mid), "book": lambda: N.book(mid), "trades": lambda: N.trades(mid, limit=50),
            "candles": lambda: N.candles(mid, "1h") if N.has_key else {"ok": False, "error": "NO_KEY"},
            "consensus": lambda: N.consensus(limit=5) if N.has_key else {"ok": False, "error": "NO_KEY"}}.items()}
        return {k: (v.result() if not v.exception() else {"ok": False, "error": str(v.exception())}) for k, v in f.items()}

def account():
    def get():
        with ThreadPoolExecutor(8) as ex:
            calls = {"balance": N.balance, "transactions": lambda: N.transactions(limit=100), "transfers": N.transfers,
                     "subaccounts": N.subaccounts, "subBalance": ((lambda: T.subaccount_balance(T.key_id)) if T.has_key else (lambda: {"ok": False, "error": "NO_KEY"})), "orders": (T if T.has_key else N).orders, "accountOrders": (T if T.has_key else N).account_orders,
                     "accountPositions": (T if T.has_key else N).account_positions, "fills": (T if T.has_key else N).fills, "positions": (T if T.has_key else N).positions,
                     "historyPositions": (T if T.has_key else N).history_positions, "keys": N.keys, "limits": N.limits,
                     "status": N.exchange_status, "time": N.time}
            fut = {k: ex.submit(f) for k, f in calls.items()}
            R = {k: unwrap(v.result()) for k, v in fut.items()}
        S = samples.ALL
        out = {"hasKey": N.has_key, "hasTradingKey": T.has_key, "subBalance": R["subBalance"], "host": N.host, "writesEnabled": False,
               "balance": live_or_sample("balance", R["balance"], {"balance": "10000.00000"}, lambda r: False),
               "transactions": live_or_sample("tx", R["transactions"], S["transactions"], lambda r: len(r.get("items", [])) < 2),
               "transfers": live_or_sample("tr", R["transfers"], S["transfers"], lambda r: not r.get("items")),
               "subaccounts": live_or_sample("sub", R["subaccounts"], S["subaccounts"], lambda r: not r),
               "orders": live_or_sample("ord", R["orders"], S["orders"], lambda r: not r.get("items")),
               "accountOrders": live_or_sample("aord", R["accountOrders"], {"seq": 42, "open": [{k: o[k] for k in ("orderId", "clientId", "marketId", "outcomeId", "price", "qty", "tif") if k in o} for o in S["orders"]["items"][:2]]}, lambda r: not r.get("open")),
               "accountPositions": live_or_sample("apos", R["accountPositions"], {"seq": 17, "positions": S["positions"]}, lambda r: not r.get("positions")),
               "fills": live_or_sample("fills", R["fills"], S["fills"], lambda r: not r.get("items")),
               "positions": live_or_sample("pos", R["positions"], S["positions"], lambda r: not r),
               "historyPositions": live_or_sample("hp", R["historyPositions"], S["history_positions"], lambda r: not r.get("items")),
               "keys": live_or_sample("keys", R["keys"], [], lambda r: False),
               "limits": live_or_sample("lim", R["limits"], {}, lambda r: False),
               "status": live_or_sample("st", R["status"], {"trading": "OPEN"}, lambda r: False),
               "time": live_or_sample("t", R["time"], {"ts": int(time.time() * 1000)}, lambda r: False),
               "batchCancelExample": {"source": "sample", "data": S["batch_cancel"]},
               "names": {"outcomes": S["outcomeNames"], "markets": S["marketNames"]}}
        # never leak raw key ids to the browser
        for k in out.get("keys", {}).get("data", []) or []:
            if isinstance(k, dict) and k.get("keyId"): k["keyId"] = k["keyId"][:8] + "…"
        return out
    return cached("acct", 10, get)

def activity():
    def get():
        idx = N.data_index(); date = idx["dates"][-1]; mdate = (idx.get("marketDates") or [date])[-1]
        tr = list(csv.DictReader(io.StringIO(N.data_csv(date, "trades"))))
        mk = list(csv.DictReader(io.StringIO(N.data_csv(mdate, "markets"))))
        by_league, by_series, hourly = {}, {}, [0] * 24
        for r in tr:
            if r["side"] != "TAKER": continue
            q = float(r["qty"]); lg = r["league"] or "COMBO"
            by_league[lg] = by_league.get(lg, 0) + q; by_series[r["contractSeries"]] = by_series.get(r["contractSeries"], 0) + q
            hourly[int(r["timestamp"][11:13])] += q
        fb = [r for r in mk if r["reportTicker"].startswith(("NFL-", "NCAAF-"))]
        by_ticker = {}
        for r in fb:
            t = by_ticker.setdefault(r["reportTicker"], {"dailyVolume": 0, "openInterest": 0, "markets": 0})
            t["dailyVolume"] += float(r["dailyVolume"] or 0); t["openInterest"] += float(r["openInterest"] or 0); t["markets"] += 1
        top = sorted([r for r in fb if r["close"]], key=lambda r: -float(r["dailyVolume"]))[:12]
        return {"source": "live", "date": date, "marketDate": mdate, "dates": idx["dates"][-14:], "trades": sum(1 for r in tr if r["side"] == "TAKER"),
                "notional": sum(float(r["qty"]) for r in tr if r["side"] == "TAKER") , "stake": sum(float(r["cost"]) for r in tr),
                "byLeague": sorted(by_league.items(), key=lambda x: -x[1])[:12], "bySeries": sorted(by_series.items(), key=lambda x: -x[1])[:10],
                "hourlyUTC": hourly, "footballTickers": by_ticker, "topFootballMarkets": top,
                "sampleTradeRows": tr[:4], "sampleMarketRows": mk[:3]}
    return cached("act", 900, get)

def order_preview(body):
    try:
        o = N.validate_order(body)
    except Exception as e:
        p = body.get("price")
        return {"ok": False, "error": str(e), "snapped": snap_down(p) if p else None}
    coef = body.get("coefficient", "0.06"); live = bool(body.get("live"))
    cost = cost_usd(o["price"], o["qty"]); fee = taker_fee_usd(o["price"], o["qty"], coef) if live else 0
    return {"ok": True, "preview": True, "sent": False, "request": {"method": "POST", "path": "/v3/orders", "body": o},
            "economics": {"cost": str(cost), "payoutIfWin": f"{o['qty']/100:.5f}", "profitIfWin": f"{o['qty']/100 - float(cost):.5f}",
                          "maxTakerFee": str(fee), "impliedProb": o["price"], "american": american(float(o["price"]))},
            "note": "PREVIEW ONLY. This server never sends orders. Management key cannot trade; a funded subaccount trading key is required."}


def journal_fill(b):
    """Prototype order path: preview the exact Novig request (never sent), then auto-journal the (dry-run) fill.
    When NOVIG_ALLOW_PAPER_ORDERS=1 and a real paper fill comes back, the same record_fill() is called with source='live'."""
    gk = b.get("eventId") or b["game_key"]
    if not J.rows(JDB, "select 1 from games where game_key=?", gk):
        away, _, home = (b.get("description") or "Away @ Home").partition(" @ ")
        J.upsert_game(JDB, {"game_key": gk, "novig_event_id": b.get("eventId"), "league": b.get("league"), "away": b.get("awayAbbr") or away,
                            "home": b.get("homeAbbr") or home, "kickoff_ts": b.get("startsTs"), "source": "novig"})
        try:
            eid = pbp.match_novig(b.get("description", ""), int(b.get("startsTs") or 0), b.get("league") or "NFL")
            if eid:
                JDB.execute("update games set espn_id=? where game_key=?", (eid, gk)); JDB.commit()
        except Exception: pass
    g = J.rows(JDB, "select * from games where game_key=?", gk)[0]
    if g.get("espn_id") and b.get("period") is None:   # pull live score/clock + notches for context
        try:
            pg = pbp.game_events(g["espn_id"], g.get("league") or "NFL"); J.add_events(JDB, gk, pg["events"]); JDB.commit()
            if pg["plays"]: e = pg["plays"][-1]; b.update(away_score=e["away"], home_score=e["home"], period=e["period"], clock=e["clock"])
        except Exception: pass
    prev = None
    if b.get("outcomeId") and b.get("side", "BUY") == "BUY":
        prev = order_preview({"outcomeId": b["outcomeId"], "price": str(b["price"]), "qty": int(round(float(b["stake"]) / float(b["price"]) * 100)), "tif": "IOC"})
    JDB.execute("insert into ticks values(?,?,?,?,?)", (gk, b["outcome"], int(time.time() * 1000), float(b["price"]), "dryrun-fill")); JDB.commit()
    e = J.record_fill(JDB, {**b, "game_key": gk, "source": "dryrun", "market_id": b.get("marketId"), "outcome_id": b.get("outcomeId")})
    return {"entry": e, "preview": prev, "sent": False}

DISCONNECTS = (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)
_last_warn = {}
def warn(msg):
    """Rate-limited one-line log (same message at most every 10s)."""
    k = msg[:60]; now = time.time()
    if now - _last_warn.get(k, 0) > 10: _last_warn[k] = now; print(time.strftime("%H:%M:%S"), "[warn]", msg, flush=True)

class Server(ThreadingHTTPServer):
    daemon_threads = True; request_queue_size = 128
    def handle_error(self, request, client_address):
        e = sys.exc_info()[1]
        if isinstance(e, DISCONNECTS): return
        warn(f"request error from {client_address[0]}: {type(e).__name__}: {e}")

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=STATIC, **k)
    def log_message(self, *a): pass
    def end_headers(self):
        self.send_header("Cache-Control", "no-store"); super().end_headers()
    def j(self, obj, code=200):
        b = json.dumps(obj, default=str).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        except DISCONNECTS: pass   # browser gave up on the request (tab closed / timed out) - nothing to do
    def fail(self, p, e):
        """One-line log; full traceback only for unexpected errors when NOVIG_DEBUG=1."""
        if isinstance(e, DISCONNECTS): return
        if isinstance(e, TR.RateLimited):
            warn(f"rate-limited {p}: {e}"); return self.j({"ok": False, "error": "rate_limited", "stale": True, "message": str(e)}, 503)
        warn(f"{p}: {type(e).__name__}: {str(e)[:160]}")
        if os.getenv("NOVIG_DEBUG") == "1": traceback.print_exc()
        return self.j({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)
    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}; p = u.path
        try:
            if p == "/" : self.path = "/trade.html"; return super().do_GET()
            if p == "/api/t/status": return self.j(TR.status())
            if p == "/api/t/games": return self.j(TR.games())
            if p.startswith("/api/t/event/"): return self.j({"markets": TR.event_markets(p.split("/")[4])})
            if p.startswith("/api/t/book/"): return self.j(TR.book(p.split("/")[4]))
            if p == "/api/t/portfolio": return self.j(TR.portfolio())
            if p == "/api/t/intents": return self.j({"intents": TR.recent(int(q.get("n", 30)))})
            if p.startswith("/api/t/intent/"): return self.j(TR.intent(p.split("/")[4]) or {"ok": False, "error": "unknown"})
            if p == "/api/journal/days": return self.j({"days": J.days(JDB), "tags": J.TAGS})
            if p.startswith("/api/journal/story/"): return self.j(J.story(JDB, p.split("/")[4]))
            if p == "/api/journal/open": return self.j({"positions": J.open_positions(JDB)})
            if p == "/api/journal/impacts": return self.j({"impacts": J.impacts(JDB), "eventTypes": pbp.EVENT_TYPES})
            if p == "/api/pbp/scoreboard": return self.j(pbp.scoreboard(q.get("league", "NFL"), q.get("date")))
            if p.startswith("/api/pbp/game/"): return self.j(pbp.game_events(p.split("/")[4], q.get("league", "NFL")))
            if p == "/api/pbp/match":
                eid = pbp.match_novig(q.get("desc", ""), int(q.get("ts", 0)), q.get("league", "NFL"))
                return self.j({"espnId": eid, "game": pbp.game_events(eid, q.get("league", "NFL")) if eid else None})
            if p == "/api/status": return self.j({"hasKey": N.has_key, "host": N.host, "writesEnabled": False, "futureSports": FUTURE_SPORTS})
            if p == "/api/types": return self.j(cached("types", 3600, lambda: {"sports": N.sports(), "leagues": N.leagues(), "marketTypes": N.market_types(), "liveMarketTypes": N.live_market_types(), "eventStatuses": N.event_statuses()}))
            if p == "/api/football": return self.j(football(int(q.get("days", 7))))
            if p.startswith("/api/event-markets/"): return self.j(cached("em" + p, 30, lambda: N.markets(event=p.split("/")[3], limit=500)))
            if p.startswith("/api/market/"): return self.j(market_detail(p.split("/")[3]))
            if p == "/api/account": return self.j(account())
            if p == "/api/activity": return self.j(activity())
            if p == "/api/contracts": return self.j(json.load(open(os.path.join(ROOT, "contracts.json"))))
            if p.startswith("/api/future/"): return self.j(future_sport_hook(p.split("/")[3]))
            if p == "/api/history":
                return self.j({"events": N.history_events(league="NFL", limit=5), "markets": N.history_markets(league="NFL", limit=3), "trades": N.history_trades(limit=20)})
        except Exception as e:
            return self.fail(p, e)
        try: return super().do_GET()
        except DISCONNECTS: pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            if self.path == "/api/t/order": return self.j(TR.submit(body))
            if self.path == "/api/t/flatten":
                pf = TR.portfolio(fresh=True); res = []
                for w in pf["wallets"]:
                    if not w["tradable"]: continue
                    for ps in w["positions"]:
                        res.append(TR.submit({"idem": f"{body.get('batch', 'flat')}-{ps['marketId'][-12:]}", "action": "SELL_ALL", "marketId": ps["marketId"],
                                              "outcomeId": ps["sideId"], "slipCents": body.get("slipCents", 3)}))
                return self.j({"ok": True, "results": res})
        except Exception as e:
            return self.fail(self.path, e)
        if self.path == "/api/journal/fill": return self.j(journal_fill(body))
        if self.path == "/api/journal/annotate": return self.j(J.annotate(JDB, body["id"], body.get("tags"), body.get("note")))
        if self.path == "/api/order/preview": return self.j(order_preview(body))
        if self.path == "/api/cancel/preview":
            return self.j({"ok": True, "preview": True, "sent": False, "request": {"method": "DELETE", "path": f"/v3/orders/{body.get('orderId')}" if body.get("orderId") else "/v3/orders", "params": {k: body.get(k) for k in ("market", "event") if body.get(k)}}})
        self.j({"ok": False, "error": "not found"}, 404)

if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):   # Windows cp1252 console: never crash on a non-ASCII char in a log line
        try: _s.reconfigure(errors="replace")
        except Exception: pass
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8601
    TR.start()
    print(f"Novig TRADER on http://localhost:{port}/  env={TR.ENV} orders={'ON' if TR.TRADABLE else 'OFF'}   (prototype: /index.html)", flush=True)
    print(f"Novig design system on http://localhost:{port}  host={N.host} key={'yes' if N.has_key else 'no'}", flush=True)
    Server(("0.0.0.0", port), H).serve_forever()
