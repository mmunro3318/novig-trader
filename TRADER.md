# Novig Trader (Phase 1)
Run (Windows or Mac/Linux; needs Python 3.10+ and `requests`; `cryptography` is optional because a pure-python signer is bundled):
```
python server.py 8601          ->  http://localhost:8601/
```
Setting env vars on Windows:
- PowerShell: `$env:NOVIG_ALLOW_PAPER_ORDERS="1"`, or `$env:NOVIG_ENV="production"`
- cmd.exe: `set NOVIG_ALLOW_PAPER_ORDERS=1`
- macOS/Linux: `export NOVIG_ALLOW_PAPER_ORDERS=1`

Set them in the same window before running `python server.py 8601`. In the table below, `set X=1` means use whichever form matches your shell.

Environment:
| Mode | How | Orders |
|---|---|---|
| Paper (default) | `~/.secrets/novig_subaccount.env` (NOVIG_SUB_API_KEY/SECRET) + `set NOVIG_ALLOW_PAPER_ORDERS=1` | paper sub-account |
| Production read-only | `set NOVIG_ENV=production` + `~/.secrets/novig_prod_read.env` | OFF (shows your app wallet) |
| Production live | see docs/LIVE_TRADING.md | ON only with NOVIG_ALLOW_LIVE_ORDERS=1 + a trading key |

## What's on screen
- **Games:** NFL and CFB, live games first, with the Q4 clock from ESPN. The moneyline is shown as a multiplier (2.30x = 1/price).
- **Market:**
  - Each side shows ask, bid and last, plus 5 levels of depth.
  - Buy buttons: **$1 / $2 / $5 / $10**, or a custom amount.
  - Every buy is an **IOC limit at ask + max slip** (header selector, 1–5¢), so you never pay more than that.
- **Positions:**
  - **NET** contracts. Exits are buys of the opposite side, and pairs pay $1.
  - `$value (P&L)`, where P&L = value − exit fee − basis, and basis includes the fees you paid.
  - Break-even sale price, including the exit fee.
  - Buttons: **SELL ALL** and **Sell half**.
  - A **FLATTEN** badge appears when the game is in Q4 with 5:00 or less left. Positions held to the end went 0–4 (−$83.80) on Oct 22–24.
- **Header:**
  - Day P&L (realized + open) and fees today.
  - Loss cap: blocks buys only.
  - **FLATTEN ALL** button.
  - Connection dot: turns red and shows "stale Ns" if updates stop.
- **Orders list:**
  - Every click shows its status: QUEUED → WORKING → FILLED / PARTIAL / UNFILLED / REJECTED / ERROR / RECONCILED.
  - Each click has its own expandable log.

## Reliability design
- **One idempotency key per click** (made in the browser). A double-click or network retry with the same key is ignored, even after a server restart (`data/orders.sqlite`).
- **Each send attempt gets a deterministic clientId (UUIDv5), recorded *before* the POST.**
  - On a timeout, the app looks that clientId up on the exchange before deciding anything. It never blindly resends.
  - If the server crashes mid-order, on restart that order is **reconciled** from the exchange's fills and not resent.
- **Partial fills:** re-quoted and topped up, up to 4 attempts, only while the price stays inside the slippage band. Sells are re-sized from the live net position on every attempt, so they never oversell.
- **Timeouts:** every HTTP call has (5s connect, 12s read). The order worker is a background thread, and the UI never waits on it.
- **Catalog rate limiting (hotfix Oct 25):**
  - All catalog reads (games, markets, books) share one token bucket, 5/s with bursts of 8 (`NOVIG_CATALOG_RATE` / `NOVIG_CATALOG_BURST`). Novig's per-key read limit is 16/s with bursts of 64, plus a per-IP edge limit.
  - A 429 pauses catalog reads for the `Retry-After` time.
  - When throttled, the app serves the last good data marked **stale**, and the header shows "prices stale Ns". The browser backs off its polling.
  - Cache times: games 15s, market lists 30s, book 1.5s (only for the market you have open).
  - Identical requests that arrive together share a single upstream call.
  - **The order path skips this bucket.** It uses its own HTTP session, fetches a fresh quote, and does one short retry on a 429, so a slow market view can never block an order.
  - Disconnected browser requests (WinError 10053) and rate limits now log one line instead of a traceback. Set `NOVIG_DEBUG=1` for full tracebacks.
- **Rate limits (orders and fills):**
  - Catalog and book reads use the signed `/v3/catalog/*` routes (16/s per key) with backoff on 429.
  - Fills (the expensive history bucket) are cached and fetched incrementally. Our own orders' fills are added to the cache directly.
- **Novig's in-game order delay:** on paper, in-game IOC orders stay PENDING about **5 seconds** before filling. That's Novig's live-betting delay, not the app, and probably why their app looks frozen when you exit. This app shows WORKING during that time.

## Files
- `novig/trader.py`: engine
- `static/trade.html`: UI
- `novig/ed25519_pure.py`: fallback signer
- `live/e2e_test.py`, `live/restart_test.py`: tests
- `docs/LIVE_TRADING.md`

## Selling with little cash (hotfix Oct 25, 2026)
On Novig a sell is a BUY of the other side, so Novig wants the cash for it up front
(contracts/100 x price + fee). Example: selling 2,091 contracts at 0.69 needs about $14.43 cash.
Paper test (Oct 25): every contract that pairs off pays back $0.01 **immediately**, so cash
goes UP right after each sell fills.

What the app does now:
* SELL ALL / Sell half read your sub-account cash and sell as many contracts as that cash covers,
  then re-read the position, re-quote and sell the next chunk (up to 12 chunks, about 1s each).
  It stops on: done, no liquidity, price moved outside your slippage limit, or cash below 1 contract.
  If Novig still says INSUFFICIENT_BALANCE it halves the chunk instead of resending the same size.
* BUY with INSUFFICIENT_BALANCE stops at once (no retries) and says how much it needed vs your cash.
* Header shows **cash**. Each position shows "cash needed to exit at once ~$X". Buy buttons get a
  yellow ring and a warning line when that buy would leave less cash than a one-shot exit of
  everything needs. That's only a warning, so you can still buy.

## UI pass from Michael's feedback board (Oct 25, 2026)

Files: `static/trade.html` (shell), `static/trade.css` (design tokens at the top: colors, sport colors, odds color), `static/trade.js` (one render function per component).

- **Game cards**: sport shown as a colored left strip (NFL blue, CFB purple, ...). Title is always `Away @ Home` with a small HOME tag; outcome buttons follow the same left/right order (server reorders Novig's home-first list using ESPN abbreviations). Center row: clock + scoreline `🏈 DEN 30 - 16 ARI` (ball icon on the side that has it), then `ARI ball · 1st & Goal · 1 yd to end zone`. Quick row: `[away odds] BUY SELL▾ [home odds]`: pick a team, then BUY $amount (two clicks = the confirm). SELL = sell all; ▾ = sell half / sell $N. Position row: cost · avg odds · pays-if-wins, ▼ for details.
- **Filters**: search, sport, status (live/upcoming/past), date (today/tomorrow/all), ★ Mine. Sections: Today · your positions, Today, Later, Past (dimmed; folded on phones).
- **Markets**: organized rows: WINNER, SPREAD − (sorted), SPREAD +, TOTAL, team points. Each chip shows the line and its odds.
- **Ticket**: pick a side, pick/type an amount ($1/$2/$5/$10 fill the field; typing works; the ticket is no longer re-drawn every 1.5s, which is what wiped typed numbers), then one big confirm button that names the exact market: `BUY $5 · KC to win (Kansas City Chiefs at Seattle Seahawks) @ 2.35`.
- **Feedback**: every click shows a toast at once (sending → queued → FILLED with contracts, odds, fees) and the button shows `sending…` / `✓ sent`.
- **Receipts**: market name, contracts, odds and cents you got (buy) or sold at (sell), cost or proceeds, fees, time with zone (e.g. PT).
- **Special markets**: the server labels every order itself (GAME / FUTURE / PARLAY / OTHER). Any buy that isn't a single-game line needs a separate confirm naming the market.
- **Daily loss cap**: now soft. Past the cap, a buy pops a confirm ("I'm sure"); sells are never blocked. Cap and per-order max are editable in ⚙ (saved to `data/settings.json`), with the time zone (default = this computer's).
- **Account hero** (top right, labels on hover): account value (cash + open), cash, open value, today's P&L, win rate, open count, est. return if held (win chance × payout − cost), total P&L.
- **Targets (local limit orders)**: Ticket → Advanced. "When odds ≥ / ≤ X" (buy uses the ask, sell uses the sell-now price) or "profit ≥ X% / loss ≥ X%" for sells. Watched server-side every ~2s; fires one normal IOC order (same slippage cap, idempotent `trg-<id>`), then disarms. Expires after 1-12h. Trailing and compound rules are not built yet.
