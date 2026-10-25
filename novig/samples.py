"""Realistic SAMPLE data shaped exactly to the OpenAPI contracts, for widgets whose live
response is empty on a fresh paper account (orders, fills, positions, position history...).
Every payload is wrapped as {"sample": True, "data": ...} by the server so the UI labels it."""
import time, uuid
NOW = int(time.time() * 1000); H = 3600_000; D = 24 * H
def u(): return str(uuid.uuid4())
M1, O1a, O1b = u(), u(), u()
M2, O2a, O2b = u(), u(), u()
M3, O3a, O3b = u(), u(), u()
OUTCOME_NAMES = {O1a: "Chicago Bears", O1b: "Seattle Seahawks", O2a: "Over 47.5", O2b: "Under 47.5", O3a: "Ohio State -6.5", O3b: "Penn State +6.5"}
MARKET_NAMES = {M1: "Bears @ Seahawks — Moneyline", M2: "Eagles @ Commanders — Total 47.5", M3: "Penn State @ Ohio State — Spread"}
orders = {"items": [
    {"orderId": u(), "clientId": u(), "marketId": M1, "outcomeId": O1a, "price": "0.415", "qty": 5000, "remaining": 3200, "status": "OPEN", "tif": "GTC", "createdTs": NOW - 2 * H},
    {"orderId": u(), "clientId": u(), "marketId": M2, "outcomeId": O2b, "price": "0.505", "qty": 2000, "remaining": 2000, "status": "OPEN", "tif": "GTT", "createdTs": NOW - 30 * 60_000, "expiresTs": NOW + 4 * H},
    {"orderId": u(), "marketId": M3, "outcomeId": O3a, "price": "0.550", "qty": 1000, "remaining": 1000, "status": "PENDING", "tif": "PO", "createdTs": NOW - 60_000}]}
fills = {"items": [
    {"fillId": u(), "orderId": orders["items"][0]["orderId"], "clientId": orders["items"][0]["clientId"], "marketId": M1, "outcomeId": O1a, "qty": 1800, "cost": "7.47000", "taker": False, "ts": NOW - 90 * 60_000},
    {"fillId": u(), "orderId": u(), "marketId": M3, "outcomeId": O3a, "qty": 4000, "cost": "21.80000", "fee": "0.05886", "taker": True, "ts": NOW - 5 * H},
    {"fillId": u(), "orderId": u(), "marketId": M2, "outcomeId": O2a, "qty": 2500, "cost": "12.50000", "taker": True, "ts": NOW - 26 * H}]}
positions = [
    {"marketId": M1, "outcomeId": O1a, "qty": 1800, "cost": "7.47000"},
    {"marketId": M3, "outcomeId": O3a, "qty": 4000, "cost": "21.80000"},
    {"marketId": M2, "outcomeId": O2a, "qty": 2500, "cost": "12.50000"}]
_res = [("WIN", 1.0), ("LOSS", 0), ("WIN", 1.0), ("WIN", 1.0), ("LOSS", 0), ("PUSH", None), ("LOSS", 0), ("WIN", 1.0), ("LOSS", 0), ("WIN", 1.0), ("WIN", 1.0), ("LOSS", 0)]
history_positions = {"items": []}
for i, (r, pay) in enumerate(_res):
    qty = 1000 + 250 * (i % 5); price = [0.42, 0.55, 0.61, 0.38, 0.5, 0.52, 0.47, 0.66, 0.58, 0.35, 0.44, 0.6][i]
    cost = qty * price / 100; payout = cost if r == "PUSH" else qty * pay / 100
    history_positions["items"].append({"positionId": u(), "marketId": u(), "outcomeId": u(), "qty": qty, "cost": f"{cost:.5f}",
        "status": "SETTLED", "result": r, "payout": f"{payout:.5f}", "pnl": f"{payout - cost:.5f}",
        "settledTs": NOW - (len(_res) - i) * 1.5 * D, "resettled": i == 5})
history_positions["items"].append({"positionId": u(), "marketId": M1, "outcomeId": O1a, "qty": 1800, "cost": "7.47000", "status": "OPEN", "result": "TBD", "resettled": False})
transactions = {"items": [
    {"transactionId": u(), "kind": "CREDIT", "amount": "10000.00000", "ref": u(), "ts": NOW - 20 * D},
    {"transactionId": u(), "kind": "TRANSFER_OUT", "amount": "-500.00000", "ref": u(), "ts": NOW - 19 * D},
    {"transactionId": u(), "kind": "FILL", "amount": "-21.80000", "ref": fills["items"][1]["fillId"], "ts": NOW - 5 * H},
    {"transactionId": u(), "kind": "FEE", "amount": "-0.05886", "ref": fills["items"][1]["fillId"], "ts": NOW - 5 * H},
    {"transactionId": u(), "kind": "MAKER_CREDIT", "amount": "0.01471", "ref": u(), "ts": NOW - 4 * H},
    {"transactionId": u(), "kind": "SETTLEMENT", "amount": "18.00000", "ref": u(), "ts": NOW - 2 * D}]}
subaccounts = [{"keyId": u(), "label": "nfl-mm-bot", "balance": "500.00000"}, {"keyId": u(), "label": "manual-tickets", "balance": "250.00000"}]
transfers = {"items": [{"transferId": u(), "clientTransferId": u(), "subaccountKeyId": subaccounts[0]["keyId"], "direction": "fund", "amount": "500.00000",
                        "status": "Applied", "actualBalance": "500.00000", "createdAt": "2026-10-02T17:01:00Z", "updatedAt": "2026-10-02T17:01:01Z"},
                       {"transferId": u(), "clientTransferId": u(), "subaccountKeyId": subaccounts[1]["keyId"], "direction": "defund", "amount": "50.00000",
                        "status": "Requested", "createdAt": "2026-10-21T22:10:00Z", "updatedAt": "2026-10-21T22:10:00Z"}]}
batch_cancel = {"canceled": [orders["items"][0]["orderId"]], "notCanceled": [{"orderId": u(), "reason": "FILLED"}, {"orderId": u(), "reason": "NOT_FOUND"}]}
ALL = dict(orders=orders, fills=fills, positions=positions, history_positions=history_positions, transactions=transactions,
           subaccounts=subaccounts, transfers=transfers, batch_cancel=batch_cancel, outcomeNames=OUTCOME_NAMES, marketNames=MARKET_NAMES)
