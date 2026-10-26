"""Offline tests for the Oct 26 money-flow fixes (no network, no orders: Novig is faked).
Run:  python -m unittest discover -s tests -v      (from the novig-app folder)"""
import os, sys, tempfile, time, unittest, json
_tmp = tempfile.mkdtemp()
os.environ["NOVIG_ORDERS_DB"] = os.path.join(_tmp, "orders.sqlite")
os.environ.setdefault("NOVIG_ENV", "paper")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from novig import trader as TR

A, B = "out-A", "out-B"          # A = the team he backs, B = the other side
MID, EID = "mkt-1", "ev-1"
def fill(fid, o, qty, price, fee=0.0, ts=1, oid=None, cid=None):
    return {"fillId": fid, "outcomeId": o, "qty": qty, "cost": f"{qty / 100 * price:.6f}", "fee": f"{fee:.6f}", "ts": ts,
            "marketId": MID, "orderId": oid or fid, "clientId": cid}
def market(status="OPEN", a_status="TBD", b_status="TBD", charged="WHEN_LIVE", bid=0.40, ask=0.42):
    return {"marketId": MID, "eventId": EID, "marketType": "MONEY", "description": "KC", "status": status, "settledTs": int(time.time() * 1000),
            "fee": {"coefficient": "0.06", "charged": charged}, "volume": 1,
            "outcomes": [{"outcomeId": A, "name": "KC", "status": a_status, "bid": {"price": str(bid)}},
                         {"outcomeId": B, "name": "SEA", "status": b_status, "bid": {"price": str(round(1 - ask, 3))}}]}
def games_cache(phase="live", period=2, clock="7:00", state="in"):
    mm, ss = clock.split(":")
    g = {"eventId": EID, "desc": "Kansas City Chiefs @ Seattle Seahawks", "away": "Kansas City Chiefs", "home": "Seattle Seahawks", "phase": phase,
         "clock": {"state": state, "period": period, "clock": clock, "secs": int(mm) * 60 + int(ss)}}
    TR._cache["games"] = (time.time(), {"games": [g]})

class Base(unittest.TestCase):
    def setUp(self):
        TR.DB.execute("delete from intents"); TR.DB.execute("delete from settled"); TR.DB.commit()
        TR._cache.clear(); TR._MS.clear(); TR._SETTLING.clear(); TR._NEED_CASH.clear()
        TR.CFG.update({"fee_mode": "auto", "fee_coef": None, "max_order_usd": 25, "daily_loss_cap_usd": 40})
        TR.TRADABLE = True
        self._saved = {k: getattr(TR, k) for k in ("cash", "book", "_net", "label_for", "portfolio", "_fills", "_positions", "cat_market", "wallets", "_fills_for", "W")}
        TR.label_for = lambda mid, oid, ev=None: {"kind": "GAME", "label": "KC to win (Kansas City Chiefs at Seattle Seahawks)", "event": "Kansas City Chiefs @ Seattle Seahawks", "outcome": "KC"}
        TR.portfolio = lambda fresh=False: {"wallets": [{"tradable": True, "day": {"lossCapHit": False, "total": 0}, "positions": []}]}
    def tearDown(self):
        for k, v in self._saved.items(): setattr(TR, k, v)

# ------------------------------------------------------------------ (1) settled markets count in P&L + win rate
class SettledPnL(Base):
    def _run(self, fills, mkt, held=()):
        class C: pass
        TR.wallets = lambda: [("Paper sub-account", C(), None, True)]
        TR._fills = lambda c, k, max_age=15: fills
        TR._positions = lambda c, k: [{"marketId": MID, "outcomeId": o, "qty": q} for o, q in held]
        TR.cat_market = lambda mid, priority=False, tokens=1: mkt
        TR.cash = lambda fresh=True: 50.0
        return TR._portfolio()["wallets"][0]

    def test_held_to_final_loss_counts(self):
        w = self._run([fill("f1", A, 1000, 0.20, ts=int(time.time() * 1000))], market("SETTLED", "LOSS", "WIN"))
        self.assertAlmostEqual(w["day"]["realized"], -2.00, places=2)
        self.assertEqual(w["life"]["closed"], 1); self.assertEqual(w["summary"]["winRate"], 0.0)
        self.assertEqual(w["day"]["settled"], 1); self.assertEqual(w["positions"], [])

    def test_held_to_final_win_counts(self):
        w = self._run([fill("f1", A, 1000, 0.20, ts=int(time.time() * 1000))], market("SETTLED", "WIN", "LOSS"))
        self.assertAlmostEqual(w["day"]["realized"], 8.00, places=2); self.assertEqual(w["summary"]["winRate"], 1.0)

    def test_sell_half_then_final_counts_both(self):
        now = int(time.time() * 1000)
        fl = [fill("f1", A, 1000, 0.40, ts=now), fill("f2", B, 500, 0.50, ts=now + 1)]   # sold half at 0.50
        w = self._run(fl, market("SETTLED", "LOSS", "WIN"))
        # paid 4.00; exit returned 5.00 - 2.50 = 2.50; the other 500 lost -> -1.50 total
        self.assertAlmostEqual(w["day"]["realized"], -1.50, places=2); self.assertEqual(w["life"]["closed"], 1)

    def test_settled_result_persists_after_market_disappears(self):
        now = int(time.time() * 1000); fl = [fill("f1", A, 1000, 0.20, ts=now)]
        self._run(fl, market("SETTLED", "LOSS", "WIN"))
        TR._cache.clear(); TR._MS.clear()
        w = self._run(fl, None)            # catalog no longer returns it
        self.assertAlmostEqual(w["day"]["realized"], -2.00, places=2); self.assertEqual(w["life"]["closed"], 1)

    def test_closed_market_not_settled_shows_settling(self):
        now = int(time.time() * 1000)
        w = self._run([fill("f1", A, 1000, 0.20, ts=now)], market("CLOSED"), held=[(A, 1000)])
        self.assertEqual(w["positions"][0]["state"], "settling"); self.assertIsNone(w["positions"][0]["pnl"])
        self.assertIn(MID, TR._SETTLING)

    def test_partial_sell_is_realized_and_card_pnl_is_what_is_left(self):
        now = int(time.time() * 1000); games_cache("upcoming", state="pre")   # pregame: no fee
        fl = [fill("f1", A, 1000, 0.40, ts=now), fill("f2", B, 500, 0.55, ts=now + 1)]   # sold half at 0.45
        w = self._run(fl, market(bid=0.45, ask=0.47), held=[(A, 500)])
        p = w["positions"][0]
        self.assertAlmostEqual(w["day"]["realized"], 0.25, places=2)          # 500 ctr sold 5c above cost
        self.assertAlmostEqual(p["stake"], 2.00, places=2); self.assertAlmostEqual(p["cashOut"], 2.25, places=2)
        self.assertAlmostEqual(p["pnl"], 0.25, places=2); self.assertAlmostEqual(w["day"]["total"], 0.50, places=2)

    def test_open_position_fields_and_lots(self):
        now = int(time.time() * 1000); games_cache("live")
        fl = [fill("f1", A, 500, 0.25, fee=0.09, ts=now, oid="o1"), fill("f2", A, 1000, 0.40, fee=0.14, ts=now + 1, oid="o2")]
        w = self._run(fl, market(bid=0.45, ask=0.47), held=[(A, 1500)])
        p = w["positions"][0]
        self.assertEqual(len(p["lots"]), 2); self.assertAlmostEqual(p["stake"], 5.25, places=2)
        self.assertAlmostEqual(p["value"], 6.75, places=2)
        xfee = 0.06 * 0.55 * 0.45 * 1500 / 100
        self.assertAlmostEqual(p["cashOut"], round(6.75 - xfee, 2), places=2)
        self.assertAlmostEqual(p["pnl"], round(p["cashOut"] - (5.25 + 0.23), 2), places=2)
        self.assertTrue(p["feeLive"])

# ------------------------------------------------------------------ lots: a 'sell this lot' exit comes out of that lot
class Lots(unittest.TestCase):
    def test_specific_lot(self):
        fl = [fill("f1", A, 500, 0.25, oid="o1", ts=1), fill("f2", A, 1000, 0.40, oid="o2", ts=2), fill("f3", B, 1000, 0.55, cid="c-lot", ts=3)]
        trip, closed = TR.replay(fl, [A, B], {"c-lot": "o2"})
        self.assertEqual(trip["lots"]["o2"]["qty"], 0); self.assertEqual(trip["lots"]["o1"]["qty"], 500); self.assertEqual(trip["net"], 500)
    def test_pro_rata(self):
        fl = [fill("f1", A, 500, 0.25, oid="o1", ts=1), fill("f2", A, 1000, 0.40, oid="o2", ts=2), fill("f3", B, 750, 0.55, ts=3)]
        trip, _ = TR.replay(fl, [A, B])
        self.assertEqual(trip["lots"]["o1"]["qty"], 250); self.assertEqual(trip["lots"]["o2"]["qty"], 500)

# ------------------------------------------------------------------ (6) fee model
class Fees(Base):
    def test_formula(self): self.assertAlmostEqual(TR.fee(0.20, 1000), 0.06 * 0.2 * 0.8 * 10)
    def test_auto_when_live(self):
        f = {"coefficient": "0.06", "charged": "WHEN_LIVE"}
        self.assertFalse(TR.fee_applies(f, False)); self.assertTrue(TR.fee_applies(f, True)); self.assertTrue(TR.fee_applies(f, None))
        self.assertTrue(TR.fee_applies({"charged": "ALWAYS"}, False))
    def test_overrides(self):
        TR.CFG["fee_mode"] = "off"; self.assertFalse(TR.fee_applies({"charged": "ALWAYS"}, True))
        TR.CFG["fee_mode"] = "always"; self.assertTrue(TR.fee_applies({"charged": "WHEN_LIVE"}, False))
        TR.CFG["fee_mode"] = "in_game_only"; self.assertFalse(TR.fee_applies({"charged": "ALWAYS"}, False))
        TR.CFG["fee_coef"] = 0.05; self.assertEqual(TR.fee_coef({"coefficient": "0.06"}), 0.05)
    def test_pregame_position_has_no_exit_fee(self):
        games_cache("upcoming", state="pre")
        class C: pass
        TR.wallets = lambda: [("Paper", C(), None, True)]
        TR._fills = lambda c, k, max_age=15: [fill("f1", A, 1000, 0.40, ts=int(time.time() * 1000))]
        TR._positions = lambda c, k: [{"marketId": MID, "outcomeId": A, "qty": 1000}]
        TR.cat_market = lambda mid, priority=False, tokens=1: market()
        TR.cash = lambda fresh=True: 50.0
        p = TR._portfolio()["wallets"][0]["positions"][0]
        self.assertEqual(p["exitFee"], 0); self.assertFalse(p["feeLive"])
    def test_settings_validation(self):
        TR.SETTINGS_PATH = os.path.join(_tmp, "settings.json")
        self.assertFalse(TR.update_settings({"fee_mode": "flat3"})["ok"])
        self.assertTrue(TR.update_settings({"fee_mode": "in_game_only", "fee_coef": 0.06})["ok"])

# ------------------------------------------------------------------ order execution with a fake exchange
class FakeW:
    key_id = None; has_key = True
    def __init__(self, reject=None): self.sent = []; self.reject = reject or (lambda o: None)
    def place_order(self, o):
        self.sent.append(o); r = self.reject(o)
        return r if r else {"orderId": "oid-%d" % len(self.sent)}
    def order(self, oid): return {"status": "FILLED"}
    def fills(self, **k): return {"items": []}
    def orders(self, **k): return {"items": []}

def book_q(status="OPEN", bid=0.40, ask=0.42):
    return {"marketId": MID, "eventId": EID, "status": status, "fee": {"coefficient": "0.06", "charged": "WHEN_LIVE"},
            "outcomes": [{"outcomeId": A, "name": "KC", "bid": bid, "ask": ask, "bids": [], "asks": []},
                         {"outcomeId": B, "name": "SEA", "bid": round(1 - ask, 3), "ask": round(1 - bid, 3), "bids": [], "asks": []}]}

class Execution(Base):
    def _submit(self, action, **kw):
        k = "test-" + str(time.time_ns())
        r = TR.submit({"idem": k, "action": action, "marketId": MID, "outcomeId": A, "slipCents": 2, **kw}); return k, r

    def test_exit_insufficient_never_same_size(self):
        held = {"n": 1000}
        TR._net = lambda mid, side, other: held["n"]
        TR.book = lambda mid, priority=False: book_q()
        TR.cash = lambda fresh=True: None if False else 1.0         # $1 cash: covers ~ 160 ctr of the 0.60 exit
        W = FakeW(lambda o: {"ok": False, "status": 422, "code": "INSUFFICIENT_BALANCE", "message": "no"}); TR.W = W
        k, r = self._submit("SELL_ALL"); self.assertTrue(r["ok"]); TR.execute(k)
        sizes = [o["qty"] for o in W.sent]
        self.assertTrue(all(b < a for a, b in zip(sizes, sizes[1:])), sizes)   # strictly smaller each time
        it = TR.intent(k); self.assertIn("need $", it["message"]); self.assertIn("have $1.00", it["message"])
        # a second click right away is refused with the same explanation, not sent again
        n_before = len(W.sent); k2, r2 = self._submit("SELL_ALL")
        self.assertFalse(r2["ok"]); self.assertEqual(r2["error"], "NEED_CASH"); self.assertEqual(len(W.sent), n_before)

    def test_market_closed_stops_at_once(self):
        TR._net = lambda mid, side, other: 500
        TR.book = lambda mid, priority=False: book_q()
        TR.cash = lambda fresh=True: 100.0
        W = FakeW(lambda o: {"ok": False, "status": 409, "code": "MARKET_CLOSED", "message": "closed"}); TR.W = W
        k, _ = self._submit("SELL_ALL"); TR.execute(k)
        self.assertEqual(len(W.sent), 1); self.assertEqual(TR.intent(k)["status"], "settling")
        k2, r2 = self._submit("SELL_ALL"); self.assertEqual(r2["error"], "SETTLING")

    def test_market_status_closed_not_sent(self):
        TR._net = lambda mid, side, other: 500; TR.cash = lambda fresh=True: 100.0
        TR.book = lambda mid, priority=False: book_q(status="CLOSED"); W = FakeW(); TR.W = W
        k, _ = self._submit("SELL_ALL"); TR.execute(k)
        self.assertEqual(W.sent, []); self.assertEqual(TR.intent(k)["status"], "settling")

    def test_sell_half_reports_riding(self):
        held = {"n": 1000}; TR._net = lambda mid, side, other: held["n"]
        TR.book = lambda mid, priority=False: book_q(); TR.cash = lambda fresh=True: 100.0
        def ff(oid, wait=6.0, want=None):
            held["n"] -= want; return [{"fillId": oid, "qty": want, "cost": str(want / 100 * 0.60), "fee": "0", "ts": 1, "outcomeId": B}]
        TR._fills_for = ff; TR.W = FakeW()
        k, _ = self._submit("SELL_HALF"); TR.execute(k)
        it = TR.intent(k); self.assertEqual(it["riding"], 500); self.assertIn("500 contracts still ride to the final", it["message"])

    def test_sell_pct_and_qty(self):
        held = {"n": 1000}; TR._net = lambda mid, side, other: held["n"]
        TR.book = lambda mid, priority=False: book_q(); TR.cash = lambda fresh=True: 100.0
        W = FakeW(); TR.W = W; TR._fills_for = lambda oid, wait=6.0, want=None: []
        k, _ = self._submit("SELL_PCT", pct=25); TR.execute(k); self.assertEqual(W.sent[0]["qty"], 250)
        k, r = self._submit("SELL_QTY", qty=300, lot="o2"); TR.execute(k); self.assertEqual(W.sent[-1]["qty"], 300)
        self.assertEqual(TR.intent(k)["lot"], "o2")

# ------------------------------------------------------------------ (4) risky buys + (8) double submit + (7) labels
class Guards(Base):
    def test_long_shot_needs_confirm(self):
        TR._cache["book" + MID] = (time.time(), book_q(bid=0.05, ask=0.06)); games_cache("live")
        r = TR.submit({"idem": "risk-000001", "action": "BUY", "marketId": MID, "outcomeId": A, "usd": 5})
        self.assertEqual(r["error"], "CONFIRM_RISKY"); self.assertIn("long shot", r["message"])
    def test_last_two_minutes_needs_confirm(self):
        TR._cache["book" + MID] = (time.time(), book_q()); games_cache("live", period=4, clock="1:40")
        r = TR.submit({"idem": "risk-000002", "action": "BUY", "marketId": MID, "outcomeId": A, "usd": 5})
        self.assertEqual(r["error"], "CONFIRM_RISKY"); self.assertIn("1:40 left", r["message"])
    def test_q4_with_time_left_is_fine(self):
        TR._cache["book" + MID] = (time.time(), book_q()); games_cache("live", period=4, clock="6:00")
        self.assertEqual(TR.risk_check({}, MID, A), [])
    def test_double_submit(self):
        TR._cache["book" + MID] = (time.time(), book_q()); games_cache("live")
        TR.Q = __import__("queue").Queue()
        r1 = TR.submit({"idem": "dbl-0000001", "action": "BUY", "marketId": MID, "outcomeId": A, "usd": 5}); self.assertTrue(r1["ok"])
        r2 = TR.submit({"idem": "dbl-0000002", "action": "BUY", "marketId": MID, "outcomeId": A, "usd": 5}); self.assertEqual(r2["error"], "DOUBLE_SUBMIT")
        r3 = TR.submit({"idem": "dbl-0000001", "action": "BUY", "marketId": MID, "outcomeId": A, "usd": 5}); self.assertTrue(r3.get("duplicate"))
        r4 = TR.submit({"idem": "dbl-0000003", "action": "BUY", "marketId": MID, "outcomeId": A, "usd": 10}); self.assertTrue(r4["ok"])   # different $ is a different buy
        TR.DB.execute("update intents set created=created-2000"); TR.DB.commit()
        r5 = TR.submit({"idem": "dbl-0000004", "action": "BUY", "marketId": MID, "outcomeId": A, "usd": 5}); self.assertTrue(r5["ok"])
    def test_labels_saved(self):
        TR.label_for = self._saved["label_for"]; games_cache("live")
        TR._cache["book" + MID] = (time.time(), {**book_q(), "type": "MONEY", "desc": "KC"})
        TR.Q = __import__("queue").Queue()
        r = TR.submit({"idem": "lab-0000001", "action": "BUY", "marketId": MID, "outcomeId": A, "usd": 5})
        it = TR.intent("lab-0000001")
        self.assertEqual(it["outcome_name"], "KC"); self.assertEqual(it["event_desc"], "Kansas City Chiefs @ Seattle Seahawks")
        self.assertEqual(it["label"], "KC to win (Kansas City Chiefs at Seattle Seahawks)")
    def test_backfill(self):
        TR.label_for = self._saved["label_for"]; games_cache("live")
        TR._cache["book" + MID] = (time.time(), {**book_q(), "type": "MONEY", "desc": "KC"})
        TR.DB.execute("insert into intents(idem,created,updated,env,action,market_id,outcome_id,usd,slip,status) values('old-1',1,1,'paper','BUY',?,?,5,2,'filled')", (MID, A)); TR.DB.commit()
        self.assertEqual(TR.backfill_labels(pause=0), 1); self.assertEqual(TR.intent("old-1")["outcome_name"], "KC")

if __name__ == "__main__": unittest.main()
