"""End-to-end paper tests through the HTTP API (server on :8601). PAPER ONLY."""
import json, time, uuid, requests, sys
B = "http://localhost:8601"
def post(p, b): return requests.post(B + p, json=b, timeout=10).json()
def get(p): return requests.get(B + p, timeout=10).json()
def wait(idem, t=25):
    t0 = time.time()
    while time.time() - t0 < t:
        i = get(f"/api/t/intent/{idem}")
        if i.get("status") not in ("queued", "working"): return i
        time.sleep(0.5)
    return i
st = get("/api/t/status"); assert st["env"] == "paper" and "paper" in st["host"], st
g = [x for x in get("/api/t/games")["games"] if x["status"] == "OPEN_INGAME" and x["money"] and all(o["ask"] for o in x["money"]["outcomes"])]
mk = g[0]["money"]; mid = mk["marketId"]; o = mk["outcomes"][0]; print("GAME", g[0]["desc"], [(x["name"], x["bid"], x["ask"]) for x in mk["outcomes"]])
R = {}
# 1 buy $2
k = str(uuid.uuid4()); t0 = time.time(); r = post("/api/t/order", {"idem": k, "action": "BUY", "marketId": mid, "outcomeId": o["outcomeId"], "usd": 2, "slipCents": 2})
print("submit latency", round(time.time() - t0, 3), r["ok"]); i = wait(k); R["buy $2"] = (i["status"], i["message"], round(time.time() - t0, 1)); print(R["buy $2"])
# 2 duplicate same idem
r2 = post("/api/t/order", {"idem": k, "action": "BUY", "marketId": mid, "outcomeId": o["outcomeId"], "usd": 2, "slipCents": 2}); R["duplicate idem"] = r2.get("duplicate")
# 3 portfolio
pf = get("/api/t/portfolio"); ps = pf["wallets"][0]["positions"]; print("POS", json.dumps(ps, indent=0)[:700]); R["portfolio net"] = [(p["side"], p["net"], p["value"], p["pnl"], p["breakEven"]) for p in ps]
# 4 add $5 then sell half
k = str(uuid.uuid4()); post("/api/t/order", {"idem": k, "action": "BUY", "marketId": mid, "outcomeId": o["outcomeId"], "usd": 5, "slipCents": 2}); i = wait(k); R["buy $5"] = (i["status"], i["message"])
k = str(uuid.uuid4()); post("/api/t/order", {"idem": k, "action": "SELL_HALF", "marketId": mid, "outcomeId": o["outcomeId"], "slipCents": 2}); i = wait(k); R["sell half"] = (i["status"], i["message"])
pf = get("/api/t/portfolio"); R["after half"] = [(p["side"], p["net"]) for p in pf["wallets"][0]["positions"]]
# 5 caps
R["per-order cap $30"] = post("/api/t/order", {"idem": str(uuid.uuid4()), "action": "BUY", "marketId": mid, "outcomeId": o["outcomeId"], "usd": 30}).get("error")
# 6 sell all
k = str(uuid.uuid4()); post("/api/t/order", {"idem": k, "action": "SELL_ALL", "marketId": mid, "outcomeId": o["outcomeId"], "slipCents": 2}); i = wait(k); R["sell all"] = (i["status"], i["message"])
pf = get("/api/t/portfolio"); R["after sell all"] = [(p["side"], p["net"]) for p in pf["wallets"][0]["positions"]]; R["day"] = pf["wallets"][0]["day"]
# 7 sell with nothing held
k = str(uuid.uuid4()); post("/api/t/order", {"idem": k, "action": "SELL_ALL", "marketId": mid, "outcomeId": o["outcomeId"]}); i = wait(k); R["sell when flat"] = (i["status"], i["message"])
for a, b in R.items(): print(f"{a:20s} {b}")
