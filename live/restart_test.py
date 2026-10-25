import requests, uuid, time, subprocess, os, json
B="http://localhost:8601"
g=[x for x in requests.get(B+"/api/t/games").json()["games"] if x["status"]=="OPEN_INGAME" and x["money"] and all(o["ask"] for o in x["money"]["outcomes"])][0]
mid=g["money"]["marketId"]; oid=g["money"]["outcomes"][0]["outcomeId"]
k=str(uuid.uuid4()); requests.post(B+"/api/t/order",json={"idem":k,"action":"BUY","marketId":mid,"outcomeId":oid,"usd":1,"slipCents":2})
time.sleep(0.35); subprocess.run("pkill -9 -f 'server.py 8601'",shell=True)   # crash mid-order
time.sleep(1); env=dict(os.environ, NOVIG_ALLOW_PAPER_ORDERS="1")
subprocess.Popen("nohup python3 server.py 8601 >> live/trader-server.log 2>&1 &",shell=True,env=env); time.sleep(4)
i=requests.get(B+f"/api/t/intent/{k}").json(); print("after crash+restart:", i["status"], "|", i["message"], "| attempts", i["attempts"])
r=requests.post(B+"/api/t/order",json={"idem":k,"action":"BUY","marketId":mid,"outcomeId":oid,"usd":1}).json(); print("resubmit same idem -> duplicate:", r.get("duplicate"), r["intent"]["status"])
time.sleep(16); i=requests.get(B+f"/api/t/intent/{k}").json(); print("later:", i["status"], i["message"])
pf=requests.get(B+"/api/t/portfolio").json(); print("net", [(p["side"],p["net"]) for p in pf["wallets"][0]["positions"]])
k2=str(uuid.uuid4()); requests.post(B+"/api/t/order",json={"idem":k2,"action":"SELL_ALL","marketId":mid,"outcomeId":oid,"slipCents":2}); time.sleep(5)
print("sell all:", requests.get(B+f"/api/t/intent/{k2}").json()["message"])
