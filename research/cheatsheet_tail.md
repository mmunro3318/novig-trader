
---

## WebSocket — `GET /v3/ws` (📄 from docs, unverified; needs trading or trading::read key)

Same host as REST (`wss://api.paper.novig.com/v3/ws`), signed handshake. Every message from the client carries a `nonce`. Verbs: `subscribe`, `unsubscribe`, `snapshot`, `place`, `cancel`, `cancel_all`. Each market/subject has its own `seq`; a gap in `seq` ⇒ resubscribe for a fresh snapshot.

| Channel | Subject | Cost | Snapshot shape | Delta shape |
|---|---|---|---|---|
| `lifecycle` | market / event | 1 | `{seq, status}` | `{seq, deltas:["OPEN"\|"CLOSE"\|"GRADE"\|"START"\|"END"\|"GOLIVE"\|"UNLIVE"]}` |
| `bbo` | market | – | `BboSnapshot` (best bid per outcome) | `BboDelta` |
| `trades` | market | 4 | `{seq, trades:[{seq, deltas:[{tradeId,takeId,outcomeId,price,qty,ts}]}]}` | same per batch |
| `book` | market | 16 | `{seq, orders:{<outcomeId>:[{order,price,qty}]}}` (best first, array order = queue) | `{seq, deltas:[{kind:"add"\|"remove"\|…, order, outcome, price, qty}]}` |
| `private.orders` | your subaccount | 1 | `{seq, open:[{orderId,clientId,marketId,outcomeId,price,qty,tif}]}` | `deltas:[open\|fill\|cancel\|reject]` |
| `private.positions` | your subaccount | – | `PositionsSnapshot` | `Position` |

Subscribe example: `{"nonce":3,"subscribe":{"markets":{"<marketId>":["book"]},"private":["orders","positions"]}}`

Private order events:
- `open` `{kind,orderId,clientId?,marketId,outcomeId,price,qty,tif,expiresAt?}` — **this, not the 201, confirms rest**
- `fill` `{kind,fillId,orderId,clientId?,outcomeId,price,qty,remaining,taker}` (no fee; fee is on `GET /v3/portfolio/fills`)
- `cancel` `{kind,orderId,reason?: GO_LIVE|MARKET_CLOSED|SETTLED|NEUTRALIZED,remaining?}`
- `reject` `{kind,orderId,code,…}`

Lifecycle notes: `GOLIVE` voids every resting order and turns taker fees on (for `fee.charged=WHEN_LIVE`).

⚠️ Shape difference: REST public book levels use `orderId`; the WS book snapshot uses `order` (per docs). Client normalizes both.

## Money, grid and fees (from docs)
- Price = probability string, 3 places. Grid: 0.001–0.050 step 0.001; 0.055–0.945 step 0.005; 0.950–0.999 step 0.001 (279 prices). Off-grid ⇒ 400 `INVALID_PRICE`. **Snap down.**
- Qty = whole contracts; a winning contract pays **1¢**. cost = P·N·1¢. 110 @ 0.665 costs $0.73150, pays $1.10.
- Balance = decimal string, 5 places. Never parse money through float.
- Taker fee = c·P·(1−P)·N·1¢, c = `fee.coefficient` (0.06). Makers pay nothing; `makerCredit` (0.25 game / 0.5 futures from 2026-10-22) is maker's share of the taker's fee. `WHEN_LIVE` charges only while `OPEN_INGAME`.
- Book holds bids only. Ask on A = 1 − best bid on B. American odds from p: p≥0.5 ⇒ −100p/(1−p); else +100(1−p)/p.

## Public daily CSVs — `https://data.novig.com/reporting/trade-data/` (✅ LIVE-VERIFIED, no auth)
| Path | Shape |
|---|---|
| `index.json` | `{dates: string[], marketDates?: string[]}` (latest seen: 2026-10-20) |
| `<date>/trades.csv` | `timestamp,outcomeId,marketId,contractSeries,league,marketType,tradeType(STRAIGHT\|COMBO),legs,cost,qty,side(TAKER\|MAKER)` |
| `<date>/markets.csv` | `date,marketId,reportTicker,openInterest,dailyVolume,open,high,low,close(cents 0–100),status(active\|closed\|determined\|finalized)` |

Live row: `2026-10-20T04:00:00.376Z,01a15777-…,01a15777-…,Parlay,,,COMBO,2,4.6585,16.94,TAKER`

## Live-verification log (2026-10-22, ~00:55 PT)
- All `/v3/public/*` GETs returned 200 on both `api.novig.com` and `api.paper.novig.com`.
- Signed routes without a key return `401 {"code":"SIGNATURE_REJECTED","message":"novig-key-id header is required"}` — verified (that's the only part of them verified).
- Observed in live catalog: every market carried `strike` (moneyline sends `"0"`, not omitted as docs say), `voids:"FMV"`, outcome `bid`/`last` present only when a bid rests / a trade has happened.
- The public event object has only `eventId, description, sport, league, status, startsTs` — no scores/clock. Team names come from `description` ("Away @ Home").

## Your paper key — what it is (verified 2026-10-22 ~00:58 PT)
- `NOVIG_API_KEY` = key UUID (header `Novig-Key-Id`); `NOVIG_API_SECRET` = base64 PKCS#8 DER Ed25519 private key (client accepts PEM, path, DER-b64, or raw hex seed).
- `GET /v3/keys` shows it is a **management** key named `paper-account-prime`, Ed25519, no expiry. Balance `10000.00000`, one `CREDIT` transaction of $10,000, no subaccounts, no orders/positions/fills.
- A management key **cannot place orders** and gets `400 NOT_A_SUBACCOUNT_KEY` on `/v3/account/subaccounts/{itsOwnKeyId}/…`. Management reads of trading routes (`/v3/orders`, `/v3/portfolio/*`, `/v3/history/positions`, `/v3/account/orders|positions`) come back as the **per-wallet map** `{ "<subaccountKeyId>": {...} }`.
- To trade on paper you'd: `POST /v3/account/subaccounts` (opens subaccount + registers a trading public key) → `POST …/{keyId}/transfer` (fund) → sign orders with that trading key. All are writes; **not done** — awaiting your go-ahead.
- Paper and production have **different marketIds** for the same game; use one host consistently (this app uses paper).
