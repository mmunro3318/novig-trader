import requests, threading, time, uuid, collections
B="http://localhost:8601"; stats=collections.Counter(); stop=time.time()+30
g=[x for x in requests.get(B+"/api/t/games").json()["games"] if x["status"]=="OPEN_INGAME" and x["money"] and all(o["ask"] for o in x["money"]["outcomes"])]
mk=g[0]["money"]; mid=mk["marketId"]; oid=mk["outcomes"][0]["outcomeId"]; print("game", g[0]["desc"])
def hammer(path, abort=False):
    while time.time()<stop:
        try:
            r=requests.get(B+path, timeout=0.05 if abort else 6)
            j=r.json(); stats[(path.split('/')[3], r.status_code, bool(j.get("stale")) if isinstance(j,dict) else False)]+=1
        except requests.exceptions.ReadTimeout: stats[("client-abort",)]+=1
        except Exception as e: stats[("err",type(e).__name__)]+=1
ts=[threading.Thread(target=hammer,args=(p,)) for p in ["/api/t/games"]*6+[f"/api/t/book/{mid}"]*8+["/api/t/portfolio"]*3]
ts+=[threading.Thread(target=hammer,args=(f"/api/t/book/{mid}",True)) for _ in range(3)]   # browser dropping requests
[t.start() for t in ts]; time.sleep(8)
res={}
for act in ("BUY","SELL_ALL"):
    k=str(uuid.uuid4()); t0=time.time()
    requests.post(B+"/api/t/order",json={"idem":k,"action":act,"marketId":mid,"outcomeId":oid,"usd":1,"slipCents":2},timeout=10)
    while True:
        i=requests.get(B+f"/api/t/intent/{k}",timeout=10).json()
        if i["status"] not in ("queued","working"): break
        time.sleep(0.3)
    res[act]=(i["status"], i["message"], f"{time.time()-t0:.1f}s")
[t.join() for t in ts]
print("orders under hammer:", res)
for k,v in sorted(stats.items(), key=str): print(k, v)
print("status:", requests.get(B+"/api/t/status").json()["catalog"])
