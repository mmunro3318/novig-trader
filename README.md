# Novig Trader

Hi! 👋 This project was born of necessity.

I swing-trade live sports odds on [Novig](https://novig.com): buy the overreaction after a big play, sell as the odds settle back. That only works if you can get *out* when you mean to, and Novig's own app kept failing me right at the worst moment. It would freeze, lag or crash just as I hit sell, and a winning trade would slip away while I stared at a spinner.

So I built my own trader on top of the official Novig API. It's a small Python server plus a web page with big one-tap buttons: buy $1 / $2 / $5 / $10, **SELL ALL** and **Sell half**, with a clear status on every click so you always know what happened. I can still keep Novig's app open on the side for scores and info, but trades go through this. The longer-term goal is to automate my live swing-trading strategy, so a bot watches for the setups and follows the rules without chasing losses.

> **Disclaimer:** this is an experimental personal project. It can place **real-money** orders, it comes with **no guarantees** of any kind (see the license), and bugs can cost you money. Start on paper (play money), then $1 orders. This project is **not affiliated with, endorsed by or supported by Novig**.

> **Phase 1 trader:** run `python server.py 8601` and open http://localhost:8601/ — see TRADER.md and docs/LIVE_TRADING.md.
>
> **New here?** Give `docs/HANDOFF_PROMPT.md` to your AI assistant; it walks you through `docs/AI_SETUP_GUIDE.md`. Paper (play money) setup is one command: `python tools/open_paper_subaccount.py --pem <path to your paper .pem>` (opens a paper sub-account + trading key and saves it to `~/.secrets/novig_subaccount.env`). Real money: `tools/open_live_subaccount.py`, see docs/LIVE_TRADING.md.

# NOVIG app — prototype v0.2 (novig/clean)

**Open `http://localhost:8601/`** after `python3 server.py 8601`. That is the navigable prototype:
Games (live + next 7 days, NFL + NCAAF, MMA/Soccer stubs) · Game detail (chart, lines, order book, position, rules) · Order slip (Take/Make, $1/$2/$5) · Positions · **Journal** (auto-entries, per-game story + timeline) · Account · Settings (price format).
- `/system.html`: the design system sampler (tokens, art, components, data widgets with variants, API map)
- `/functional.html`: the v0.1 functional widget system (every API field)
- Docs: `docs/USER_FLOWS.md` (flows + wireframes), `docs/DESIGN_SYSTEM.md`, `docs/DECISIONS.md`, `docs/swing-trading-math.md`
- Shortcuts: `/` search · `Enter` place (slip open) · `Esc` close · click the header odds chip to cycle price formats.

### Journal & play-by-play
- Every fill (dry-run today, live paper later) writes a row to `data/journal.sqlite` with action, stake, price, score, clock, position value vs basis, break-even and the triggering hype event. Tag and annotate later.
- Game events come from ESPN's public JSON (`novig/pbp.py`, no key). nflverse and CollegeFootballData are stubs.
- `python3 tools/seed_journal.py` rebuilds the demo journal: 3 real Oct 18 NFL games (real ESPN events, **sample** prices and trades). It wipes the journal DB.
- `python3 tools/gen_assets.py` regenerates the hand-drawn SVGs in `static/assets/`.
- New endpoints: `GET /api/journal/days|open|impacts|story/{gameKey}`, `GET /api/pbp/scoreboard|game/{espnId}|match`, `POST /api/journal/fill|annotate`.

---
# NOVIG app: Functional Design System (phase 1)

A small Python server plus a single-page "functional design system". Every Novig API field is displayed by a widget, followed by a football demo page (live and upcoming NFL and NCAAF games for the next 7 days, search, account panel, quick-bet ticket).
**Safety:** by default everything runs against Novig's **paper** (play-money) exchange, and orders are only sent if you set `NOVIG_ALLOW_PAPER_ORDERS=1`. Real-money orders need all three: `NOVIG_ENV=production`, `NOVIG_ALLOW_LIVE_ORDERS=1`, and a live trading key you create yourself (see `docs/LIVE_TRADING.md`). Per-order and daily-loss caps apply in both modes.

## Requirements
Python **3.10+**. Packages: `requests` and `cryptography` (for signing requests). No build step and no Node.

## Setup & run
**macOS / Linux**
```bash
cd novig-app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export NOVIG_API_KEY="<management key UUID>"
export NOVIG_API_SECRET="<management private key>"
python3 server.py 8601            # → http://localhost:8601
```
**Windows (PowerShell)**
```powershell
cd novig-app
py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:NOVIG_API_KEY="<management key UUID>"
$env:NOVIG_API_SECRET="<management private key>"
py server.py 8601
```
(Windows cmd: `set NOVIG_API_KEY=...`.) With no keys at all, the page still runs using Novig's public endpoints, and account widgets show labelled SAMPLE data.

## Credentials (environment variables)
| Var | What | Shape |
|---|---|---|
| `NOVIG_API_KEY` | **Management** key ID (header `Novig-Key-Id`). Reads balance, transactions, sub-accounts, keys and the catalog. **Cannot trade.** | UUID |
| `NOVIG_API_SECRET` | Management private key | base64 PKCS#8 DER Ed25519 (64 chars). PEM text, a path to a `.pem` file, or a hex seed also work |
| `NOVIG_SUB_API_KEY` | **Trading** key of the paper sub-account `grok-paper-trading`. This ID is also the sub-account's address | UUID |
| `NOVIG_SUB_API_SECRET` | Trading-key private key | base64 PKCS#8 DER Ed25519 |
| `NOVIG_SUB_ENV_FILE` | Optional path to an env file holding the two `NOVIG_SUB_*` vars. Default `~/.secrets/novig_subaccount.env` (on Windows: `%USERPROFILE%\.secrets\novig_subaccount.env`) | `KEY=value` lines |
| `NOVIG_HOST` | Default `https://api.paper.novig.com`. Writes refuse any other host | URL |
| `NOVIG_ALLOW_PAPER_ORDERS` | `1` lets `novig.client.trading_client().place_order(...)` actually send to **paper**. Leave unset for dry-run | `1` / unset |

**No secrets are in this zip.** Copy the sub-account env file over yourself and keep it private (`chmod 600` on mac/Linux). For the sub-account key, a `NOVIG_SUB_*` env var overrides the env file.

Which key does what: the management key signs balance, sub-account, transfer and key routes. The trading key (`trading_client()`) signs orders, fills, positions and the sub-account's own balance (`GET /v3/account/subaccounts/{keyId}/balance`; `/v3/account/balance` returns 403 for a trading key).

## Python usage
```python
from novig.client import Novig, trading_client
mgmt = Novig()                       # management key
t = trading_client()                 # sub-account trading key
t.subaccount_balance(t.key_id)       # {'keyId': ..., 'balance': '1000.00000'}
t.place_order({"outcomeId": "...", "price": "0.525", "qty": 100, "tif": "GTC"})  # dry run unless NOVIG_ALLOW_PAPER_ORDERS=1
```

## Files
| Path | What |
|---|---|
| `novig-cheatsheet.md` | All 64 REST operations, websocket channels and data.novig.com CSV files, with pinned contracts. Each is marked ✅ live-verified or 📄 from docs |
| `contracts.json` | Fields per endpoint; the page's coverage matrix checks against this |
| `novig/client.py` | Typed client: NOVIG-V3 signing, every endpoint, price-grid/fee/odds helpers, `trading_client()`, MMA and soccer stubs |
| `novig/samples.py` | Sample data shaped like real responses, for widgets whose live data is empty |
| `server.py` | JSON API and static server (`/api/football`, `/api/account`, `/api/market/{id}`, `/api/activity`, previews…) |
| `static/` | `index.html`, `ds.css`, `ds.js` |
| `tools/open_paper_subaccount.py` | One-time PAPER setup: opens a paper sub-account + trading key, writes `~/.secrets/novig_subaccount.env`, funds it with play money (`--fund`, default 500). Paper host only |
| `tools/gen_cheatsheet.py` | Regenerates the cheatsheet from `research/openapi-v3.json` and the live captures |
| `research/` | Official OpenAPI spec, docs pages, live response captures |
| `*.png` | Screenshots |

## Ports
Default **8601**: `python3 server.py <port>`. The tradekit dashboard uses 8501, so the two don't clash.

## Troubleshooting
- **401 `SIGNATURE_REJECTED` "signature verification failed"**: wrong secret for that key ID, or your clock is more than 30 s off (sync your system clock). `Novig().time()` returns server time.
- **401 "api key not found"**: a paper key used against production, or the other way round. Keys only work in the environment they were made in.
- **403 `SCOPE_INSUFFICIENT`**: wrong key for that route (see "Which key does what").
- **400 `NOT_A_SUBACCOUNT_KEY`**: you passed the management key ID where a sub-account (trading) key ID is expected.
- **Account widgets say SAMPLE**: that live list is empty (no orders or fills yet). This is expected until you trade on paper.
- **Port busy**: use another port. To find the process: mac/Linux `lsof -i :8601`, Windows `netstat -ano | findstr 8601`.
- **`cryptography` won't install**: upgrade pip (`python -m pip install -U pip`). It ships prebuilt wheels for Windows, macOS and Linux.
- **PowerShell won't activate the venv**: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## License
Released under the **GNU General Public License v3.0** (GPL-3.0); the full text is in [`LICENSE`](LICENSE).
In plain terms: you're free to use, study, share and modify this code. If you distribute a modified version or anything built from it, you must release it under the same GPL-3.0 license, with its source code available. It comes with no warranty.

Copyright (C) 2026 Michael Munro
