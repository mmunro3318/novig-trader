import json, time, requests, datetime as dt
U="https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event=401873010"
seen={}; out=open("/workspace/novig-app/live/espn_latency.jsonl","a")
def ms(s): return int(dt.datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()*1000)
end=time.time()+4*3600
while time.time()<end:
    try:
        d=requests.get(U,timeout=10).json(); now=int(time.time()*1000)
        dr=d.get("drives") or {}; plays=[(x,p) for x in dr.get("previous",[])+[dr.get("current") or {}] for p in x.get("plays",[])]
        for x,p in plays:
            if p["id"] in seen or not p.get("wallclock"): continue
            seen[p["id"]]=now
            if len(seen)<=len(plays) and now-ms(p["wallclock"])>600000: continue  # backlog
            s=p.get("start",{})
            out.write(json.dumps({"id":p["id"],"seen":now,"wall":ms(p["wallclock"]),"lag_s":(now-ms(p["wallclock"]))/1000,"type":p["type"].get("text"),
              "down":s.get("down"),"dist":s.get("distance"),"yl":s.get("possessionText"),"poss":(s.get("team") or {}).get("id"),
              "scoring":p.get("scoringPlay"),"text":p.get("text","")[:120]})+"\n"); out.flush()
        st=d["header"]["competitions"][0]["status"]["type"]
        if st.get("completed"): break
    except Exception as e: print(e)
    time.sleep(5)
