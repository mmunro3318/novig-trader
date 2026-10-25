"""Live PAPER swing session, Oct 22 2026 NE @ CHI. Paper host only; <=$5/order; <=$50 total buys."""
import os, sys, time, json, logging, math, signal, faulthandler
faulthandler.register(signal.SIGUSR1)
def _alarm(*a):
    logging.info('watchdog: loop stuck >90s, exiting for restart'); os._exit(3)
signal.signal(signal.SIGALRM, _alarm)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["NOVIG_ALLOW_PAPER_ORDERS"] = "1"
from novig.client import trading_client, PAPER_HOST
from novig import pbp, journal
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session-20261022.log")
logging.basicConfig(filename=LOG, level=logging.INFO, format="%(asctime)s %(message)s")
L = logging.info
MKT, EVT, ESPN = "01a136e6-e503-7e61-bda8-4972197d7147", "01a136e6-e43c-7041-871f-53e6ddc49dec", "401873010"
OUT = {"CHI": "01a136e6-e503-7e61-bda8-498ff0475ce7", "NE": "01a136e6-e503-7e61-bda8-499c60ec5730"}
OTHER = {"CHI": "NE", "NE": "CHI"}; GK = "espn-" + ESPN
MAX_ORDER, MAX_TOTAL = 5.0, 50.0
n = trading_client(); assert n.host == PAPER_HOST and n.is_paper and n.writes_enabled
c = journal.db()
journal.upsert_game(c, {"game_key": GK, "novig_event_id": EVT, "espn_id": ESPN, "league": "NFL", "away": "NE", "home": "CHI",
                        "kickoff_ts": 1792714500000, "source": "novig-paper-live"})
LOCK = "/tmp/novig_session.lock"
if os.path.exists(LOCK) and os.path.exists(f"/proc/{open(LOCK).read().strip()}"): sys.exit("another session running")
open(LOCK, "w").write(str(os.getpid()))
spent = 0.0; pos = {"CHI": None, "NE": None}
def reconcile():
    """Source of truth = exchange. Net position per side = own qty - opposite qty (complete sets are locked $1)."""
    global spent
    fl = n.fills().get("items", []); spent = sum(float(x["cost"]) for x in fl)
    q = {k: 0 for k in OUT}; cst = {k: 0.0 for k in OUT}
    for p in n.positions():
        for k, oid in OUT.items():
            if p["outcomeId"] == oid: q[k] = p["qty"]; cst[k] = float(p["cost"])
    for k in OUT:
        net = q[k] - q[OTHER[k]]
        if net <= 0: pos[k] = None
        elif not pos[k] or pos[k]["qty"] != net:
            P = pos[k] or {"adds": 1, "t": time.time(), "plain": True, "peak": 0}
            last = [x for x in sorted(fl, key=lambda x: x["ts"]) if x["outcomeId"] == OUT[k]][-1]
            P.update(qty=net, cost=net * float(last["cost"]) / last["qty"]); P["peak"] = max(P["peak"], P["cost"] / net * 100); pos[k] = P
hist = {"CHI": [], "NE": []}; last_plain = time.time(); seen = set()

def quotes():
    b = n.market(MKT); bid = {o["name"]: float((o.get("bid") or {}).get("price") or 0) for o in b["outcomes"]}
    return {k: {"bid": bid[k], "ask": round(1 - bid[OTHER[k]], 3) if bid[OTHER[k]] else None} for k in OUT}, b

def journal_fill(f):
    try: return journal.record_fill(c, f)
    except Exception as ex: L(f"journal err {ex!r}"); return {"id": None, "realized": None}
def snap(p): return f"{math.floor(p * 200 + 1e-9) / 200:.3f}"  # 0.005 grid
def snapup(p): return f"{math.ceil(p * 200 - 1e-9) / 200:.3f}"

def fills_for(oid):
    for _ in range(5):
        time.sleep(1); f = [x for x in n.fills().get("items", []) if x["orderId"] == oid]
        if f: return f
    return []

def buy(team, usd, q, tags, note, ctx):
    global spent
    ask = q[team]["ask"]
    if not ask or ask >= 0.97 or ask <= 0.02: return None
    usd = min(usd, MAX_ORDER, MAX_TOTAL - spent)
    if usd < 0.5: L("exposure cap hit"); return None
    qty = int(usd / ask * 100); r = n.place_order({"outcomeId": OUT[team], "price": snapup(ask), "qty": qty, "tif": "IOC"})
    L(f"BUY {team} {qty}@{ask} -> {json.dumps(r)}")
    if "orderId" not in r: return None
    fs = fills_for(r["orderId"]); fq = sum(x["qty"] for x in fs); cost = sum(float(x["cost"]) for x in fs); fee = sum(float(x["fee"]) for x in fs)
    if not fq: L("no fill"); return None
    spent += cost; p = cost / fq * 100
    e = journal_fill({"game_key": GK, "outcome": team, "side": "BUY", "price": p, "qty": fq, "fee": fee, "market_id": MKT,
        "outcome_id": OUT[team], "order_id": r["orderId"], "source": "novig-paper", "tags": tags, "note": note, **ctx})
    P = pos[team] or {"qty": 0, "cost": 0, "adds": 0, "peak": p, "t": time.time(), "plain": "gut" in tags}
    P["qty"] += fq; P["cost"] += cost + fee; P["adds"] += 1; pos[team] = P
    L(f"FILL BUY {team} qty={fq} px={p:.3f} fee={fee} spent={spent:.2f} entry={e['id']}"); return e

def sell(team, q, tags, note, ctx):
    """Exit = buy the opposite outcome for the same qty (complete set pays $1)."""
    P = pos[team]; o = OTHER[team]; ask_o = q[o]["ask"]
    if not P or not ask_o: return None
    r = n.place_order({"outcomeId": OUT[o], "price": snapup(ask_o), "qty": P["qty"], "tif": "IOC"})
    L(f"SELL {team} via BUY {o} {P['qty']}@{ask_o} -> {json.dumps(r)}")
    if "orderId" not in r: return None
    fs = fills_for(r["orderId"]); fq = sum(x["qty"] for x in fs); cost = sum(float(x["cost"]) for x in fs); fee = sum(float(x["fee"]) for x in fs)
    if not fq: L("no fill"); return None
    px = 1 - cost / fq * 100  # effective sale price of team
    e = journal_fill({"game_key": GK, "outcome": team, "side": "SELL", "price": px, "qty": fq, "fee": fee, "market_id": MKT,
        "outcome_id": OUT[team], "order_id": r["orderId"], "source": "novig-paper", "tags": tags, "note": note, **ctx})
    P["qty"] -= fq
    if P["qty"] <= 0: pos[team] = None
    L(f"FILL SELL {team} qty={fq} px={px:.3f} fee={fee} realized={e['realized']} entry={e['id']} positions={json.dumps(n.positions())}")
    return e

L("session start")
t_end = time.time() + 4 * 3600
while time.time() < t_end:
    signal.alarm(90)
    try:
        reconcile()
        q, b = quotes()
        if b.get("status") != "OPEN": L(f"market status {b.get('status')}");
        now = time.time()
        for k in OUT:
            if q[k]["ask"]: hist[k].append((now, q[k]["ask"])); hist[k] = hist[k][-40:]
        for k in OUT:
            if q[k]["bid"]: c.execute("insert into ticks values(?,?,?,?,?)", (GK, k, int(now * 1000), (q[k]["bid"] + (q[k]["ask"] or q[k]["bid"])) / 2, "novig-paper"))
        c.commit()
        try:
            g = pbp.game_events(ESPN); journal.add_events(c, GK, g["events"]); c.commit()
            last = g["plays"][-1] if g["plays"] else {}
            ctx = {"period": last.get("period"), "clock": last.get("clock"), "away_score": last.get("away"), "home_score": last.get("home")}
            final = "Final" in (g.get("status") or "")
            new = [e for e in g["events"] if e["hype"] and e["id"] not in seen and now * 1000 - e["ts"] < 300_000]
            for e in g["events"]: seen.add(e["id"])
        except Exception as ex:
            L(f"pbp err {ex}"); ctx, final, new = {}, False, []
        L(f"q CHI {q['CHI']} NE {q['NE']} ctx {ctx} spent {spent:.2f} pos {json.dumps({k:(v and v['qty']) for k,v in pos.items()})}")
        if final or b.get("status") not in ("OPEN", None):
            L("game final/market closed"); break
        # exits: target / trailing stop / stop-loss / plain time exit
        for k in OUT:
            P = pos[k]
            if not P: continue
            bid = q[k]["bid"]; avg = P["cost"] / P["qty"] * 100 if P["qty"] else 0
            P["peak"] = max(P["peak"], bid)
            if bid >= 0.5 and avg < 0.45: sell(k, q, ["target-hit"], "odds reverted to ~2.0", ctx)
            elif bid - avg >= 0.06: sell(k, q, ["target-hit"], f"+{(bid-avg)*100:.1f}c over avg", ctx)
            elif P["peak"] - avg >= 0.04 and bid <= P["peak"] - 0.03: sell(k, q, ["trailing-stop"], "gave back 3c from peak", ctx)
            elif avg - bid >= 0.15: sell(k, q, ["rule-break"], "stop-loss -15c", ctx)
            elif P.get("plain") and now - P["t"] > 600: sell(k, q, ["calm"], "plain round-trip exit after 10m", ctx)
        # entries: spike after negative event
        for e in new:
            if e["type"] not in ("INT", "PICK_SIX", "FUMBLE_LOST", "TURNOVER_DOWNS", "SACK", "FG_MISS", "SAFETY", "TD", "INJURY", "PENALTY_BIG", "BLOCKED"): continue
            # who got hurt? team on the play for turnovers is usually the offense
            victim = e.get("team")
            if e["type"] == "TD" and victim: victim = OTHER.get(victim)
            if victim not in OUT: continue
            h = [p for t, p in hist[victim] if now - t <= 240]
            drop = (max(h) - q[victim]["ask"]) if h and q[victim]["ask"] else 0
            L(f"event {e['type']} victim {victim} drop {drop:.3f}: {e['text'][:90]}")
            P = pos[victim]
            if drop >= 0.03 and (not P or P["adds"] < 4):
                buy(victim, 1.0 if not P else 2.0, q, ["overreaction"] + (["averaging-down"] if P else []), f"bought spike after {e['type']}", ctx)
        # plain entries so we get fills regardless
        if now - last_plain > 600 and not any(pos.values()):
            dog = min(OUT, key=lambda k: q[k]["ask"] or 1)
            buy(dog, 1.0, q, ["gut"], "plain entry (data gathering)", ctx); last_plain = now
            if pos[dog]: pos[dog]["plain"] = True
    except Exception as ex:
        L(f"loop err {ex!r}")
    signal.alarm(0)
    time.sleep(40)
L(f"session end spent={spent:.2f} positions={json.dumps(n.positions())} fills={len(n.fills().get('items', []))}")
