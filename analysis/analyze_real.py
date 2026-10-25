"""Rebuild Michael's real Novig trades from raw API pulls (analysis/raw/*.json). Read-only."""
import json, csv, datetime as dt, collections
R = "analysis/raw/"
F = sorted(json.load(open(R+"fills.json")), key=lambda x: x["ts"]); T = json.load(open(R+"transactions.json"))
M = json.load(open(R+"markets.json")); H = json.load(open(R+"history_positions.json"))
pt = lambda ms: dt.datetime.fromtimestamp(ms/1000)
fid = {x["fillId"] for x in F}
settle = collections.defaultdict(list)
for t in T:
    if t["kind"] == "SETTLEMENT": settle[t["ref"]].append(t)
parlay_fill = [t for t in T if t["kind"] == "FILL" and t["ref"] not in fid]
parlay_fee = {t["ref"]: -float(t["amount"]) for t in T if t["kind"] == "FEE" and t["ref"] not in fid}

rows = []; trips = []; mk_sum = {}
by_m = collections.defaultdict(list)
for f in F: by_m[f["marketId"]].append(f)
for m, fs in by_m.items():
    meta = M[m]; outs = list(meta["outcomes"]); name = {o: meta["outcomes"][o]["name"] for o in outs}
    game = meta["event"] + ("" if meta["type"] == "MONEY" else f" [{meta['type']} {meta['strike']}]")
    q = {o: 0 for o in outs}; trip = None; last_close = None
    def net(): return q[outs[0]] - q[outs[1]]
    for f in fs:
        o = f["outcomeId"]; other = [x for x in outs if x != o][0]
        qty, cost, fee = f["qty"], float(f["cost"]), float(f.get("fee") or 0); px = cost/qty*100
        held_sign = 1 if o == outs[0] else -1
        n0 = net()
        closing = n0 != 0 and (n0 > 0) != (held_sign > 0)
        if closing:
            held = outs[0] if n0 > 0 else outs[1]
            cq = min(qty, abs(n0))
            proceeds = cq/100 - cost*cq/qty - fee*cq/qty
            trip["exits"].append((f["ts"], cq, 1-px, proceeds)); trip["cash"] += proceeds; trip["exit_q"] += cq
            act = "EXIT" if cq == abs(n0) else "PARTIAL_EXIT"
            rows.append(dict(ts=pt(f["ts"]), game=game, held=name[held], action=act, side_bought=name[o], qty=qty, price=round(px,4), eff_sell_price=round(1-px,4),
                             cost=cost, fee=fee, cash=round(proceeds,4), league=meta["league"]))
            q[o] += qty
            if net() == 0:
                trip["close_ts"] = f["ts"]; trip["held_to_settle"] = False; trips.append(trip); last_close = trip; trip = None
            if qty > cq:  # flip: remainder opens a new trip
                rq = qty-cq; rc = cost*rq/qty; rf = fee*rq/qty
                trip = dict(market=m, game=game, side=name[o], league=meta["league"], open_ts=f["ts"], entries=[(f["ts"], rq, px, rc+rf)], exits=[], cash=-(rc+rf), entry_q=rq, exit_q=0, flip=True, prev=last_close)
            continue
        if trip is None:
            trip = dict(market=m, game=game, side=name[o], league=meta["league"], open_ts=f["ts"], entries=[], exits=[], cash=0.0, entry_q=0, exit_q=0, flip=False, prev=last_close)
        act = "ENTER" if not trip["entries"] else "ADD"
        trip["entries"].append((f["ts"], qty, px, cost+fee)); trip["cash"] -= cost+fee; trip["entry_q"] += qty
        q[o] += qty
        rows.append(dict(ts=pt(f["ts"]), game=game, held=name[o], action=act, side_bought=name[o], qty=qty, price=round(px,4), eff_sell_price="", cost=cost, fee=fee, cash=round(-(cost+fee),4), league=meta["league"]))
    if trip:  # held into settlement (or still open)
        held = trip["side"]; rq = abs(net())
        st = [v["status"] for k, v in meta["outcomes"].items() if v["name"] == held][0]
        trip["residual_q"] = rq; trip["held_to_settle"] = True; trip["result"] = st
        if meta["status"] == "SETTLED":
            pay = rq/100 if st == "WIN" else 0.0
            trip["cash"] += pay; trip["close_ts"] = meta.get("settledTs"); trip["settle_pay"] = pay
        else:
            bid = [v["bid"] for v in meta["outcomes"].values() if v["name"] == held][0]
            trip["mark"] = rq/100*float(bid or 0); trip["close_ts"] = None
        trips.append(trip)
    cash_check = sum(float(t["amount"]) for t in settle[m]) - sum(float(f["cost"])+float(f.get("fee") or 0) for f in fs)
    mk_sum[m] = dict(game=game, league=meta["league"], fills=len(fs), cash_pnl=round(cash_check,2), status=meta["status"])

# behavior flags
trips.sort(key=lambda t: t["open_ts"])
for i, t in enumerate(trips):
    fl = []; ps = [e[2] for e in t["entries"]]
    stake = sum(e[3] for e in t["entries"]); t["stake"] = stake
    t["avg_entry"] = sum(e[1]*e[2] for e in t["entries"])/max(1, sum(e[1] for e in t["entries"]))
    if len(ps) > 1:
        run = ps[0]
        if any(p < run - 0.005 for p in ps[1:]): fl.append("averaging-down")
        if any(p > run + 0.005 for p in ps[1:]): fl.append("adding-higher")
    if t["prev"] and t["open_ts"] - (t["prev"]["close_ts"] or 0) < 45*60_000: fl.append("re-entry" + ("(flip)" if t["flip"] or t["prev"]["side"] != t["side"] else ""))
    prior = [p for p in trips[:i] if p.get("close_ts") and p["close_ts"] <= t["open_ts"] and t["open_ts"] - p["close_ts"] < 15*60_000]
    if prior:
        p = max(prior, key=lambda x: x["close_ts"])
        if p["cash"] > 0 and stake > 1.25*p.get("stake", 0): fl.append("bigger-after-win")
        if p["cash"] < 0 and stake > 1.25*p.get("stake", 0): fl.append("bigger-after-loss")
    if t["held_to_settle"]: fl.append("held-to-settlement" if t.get("close_ts") else "OPEN")
    if t["avg_entry"] < 0.2: fl.append("longshot<0.20")
    t["flags"] = fl
    t["hold_min"] = round(((t["close_ts"] or t["open_ts"]) - t["open_ts"])/60000, 1) if t.get("close_ts") else None

with open("analysis/real_fills_20261022-25.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader()
    for r in rows: r = dict(r); r["ts"] = r["ts"].strftime("%Y-%m-%d %H:%M:%S PT"); w.writerow(r)
with open("analysis/real_positions_20261022-25.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["open_pt","close_pt","game","league","side","entries","exits","stake_incl_fees","avg_entry_px","avg_entry_decimal","contracts","realized_pnl","hold_min","held_to_settle","flags"])
    for t in trips:
        w.writerow([pt(t["open_ts"]).strftime("%m-%d %H:%M"), pt(t["close_ts"]).strftime("%m-%d %H:%M") if t.get("close_ts") else "OPEN", t["game"], t["league"], t["side"],
                    len(t["entries"]), len(t["exits"]), round(t["stake"],2), round(t["avg_entry"],3), round(1/t["avg_entry"],2), t["entry_q"], round(t["cash"],2) if t.get("close_ts") else "", t["hold_min"], t["held_to_settle"], ";".join(t["flags"])])
json.dump({"trips": [{k: v for k, v in t.items() if k != "prev"} for t in trips], "markets": mk_sum,
           "parlays": [dict(ts=str(pt(p["ts"])), stake=-float(p["amount"]), fee=parlay_fee.get(p["ref"]), ref=p["ref"], payout=sum(float(s["amount"]) for s in settle.get(p["ref"], []))) for p in parlay_fill],
           "orphan_settlements": [dict(ts=str(pt(s["ts"])), amount=s["amount"], ref=s["ref"]) for k, v in settle.items() if k not in by_m for s in v]},
          open("analysis/raw/summary.json", "w"), indent=1, default=str)
print("ok", len(rows), len(trips))
