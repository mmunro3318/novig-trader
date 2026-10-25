# AI setup guide: Novig Trader

**Who this is for:** you, the AI assistant (Claude, Gemini, ChatGPT or similar) helping a friend install and run this app.
**Who you're helping:** a smart person who isn't a programmer. Assume no terminal experience. Your job is to get them from nothing to one successful **paper** (play-money) buy and sell, then stop. Going live with real money is a separate, later step.

This is a personal, experimental project that one person built for his own trading. It works for him, but it has no warranty, no support team and rough edges. Be kind about that, and be honest with your user about it.

---

## 0. Rules for you (read these first)

1. **One small step at a time.** Give one instruction, wait for your user to say it worked (or paste what they see), then move on. Never dump ten commands at once.
2. **Plain language.** Explain each command in one short sentence before giving it ("This installs the two add-ons the app needs."). Say exactly where to click and what to type.
3. **Never ask for secret values, and stop them if they start pasting one.** Secrets here are:
   - the contents of any `.pem` file (it starts with `-----BEGIN PRIVATE KEY-----`);
   - the private key Novig shows on screen once when a key is created;
   - anything in the `.secrets` folder (`novig_subaccount.env`, `novig_live_trading.env`, `novig_prod_read.env`).
   If they paste one by accident, tell them calmly: "Please delete that message. To be safe, revoke that key on Novig (Profile → Settings → Novig API → ×) and make a new one." Then carry on.
   Key **IDs** (UUIDs like `8f14e45f-...`) are not secret, but they don't need to go in the chat either. The setup script asks for them directly.
4. **Secrets never go in the app folder.** They live in a `.secrets` folder in the user's home folder, never inside `novig-app`, never in a GitHub repo, never in a zip.
5. **Paper first, always.** Do not mention, suggest or help with live trading until a paper buy *and* a paper sell have both worked. When you do get there, say clearly: **"This is real money now."**
6. **Confirm before you move on.** Use the checklist in section 10 and tick items off with them.
7. **Don't edit the app's code.** If something is broken, use the troubleshooting table (section 9). If that doesn't fix it, help them write a short note to the person who shared the app (what they did, what they saw, the error text with no secrets in it).
8. **Use the other docs when you need detail:** `README.md` (all settings, troubleshooting), `TRADER.md` (what's on screen, how orders work), `docs/LIVE_TRADING.md` (real money).

---

## 1. What the app is (so you can explain it)

- A small Python program that runs **on the user's own computer** and opens a trading page in their web browser at `http://localhost:8601/`.
- It talks to **Novig** (a US sports prediction exchange) through Novig's official API.
- It has big one-tap buttons: buy **$1 / $2 / $5 / $10**, plus **SELL ALL** and **Sell half**. Each tap shows its status (WORKING → FILLED, etc.) so you know what happened.
- It has two worlds:
  - **Paper:** `paper.novig.com` / `api.paper.novig.com`. Play money (accounts start with $10,000 fake dollars). This is the default.
  - **Production:** `novig.com` / `api.novig.com`. **Real money.**
- The user can keep using Novig's own app at the same time for scores and information.

---

## 2. What they need

| Thing | Details |
|---|---|
| A computer | Windows 10/11 or a Mac. A phone alone won't work. |
| Python 3.10 or newer | Free from python.org. Section 3. |
| Two Python add-ons | `requests` and `cryptography` (from `requirements.txt`). `cryptography` is optional because the app has a built-in fallback, but install it anyway. |
| The app's files | From GitHub (section 4). |
| A Novig account | Sign up on novig.com. Real-money use needs ID checks (KYC) and the user must be in a permitted US state. Novig's docs list Arizona, Michigan and Nevada as restricted for the API. |
| The Novig phone app | Needed for the location check before real-money orders (section 5). |
| No Node, no build tools, no database server | Just Python. |

**PowerShell vs Mac Terminal:** the commands differ, and this guide shows both. On Windows, use **PowerShell** (Start menu → type "PowerShell" → open "Windows PowerShell"). On a Mac, use **Terminal** (Cmd+Space → "Terminal"). Find out which one they have before you give any command.

| Task | Windows PowerShell | Mac Terminal |
|---|---|---|
| Run Python | `python` (or `py`) | `python3` |
| Set a setting for this window | `$env:NAME="value"` | `export NAME=value` |
| Path separator | `tools\open_live_subaccount.py` | `tools/open_live_subaccount.py` |
| Home folder | `$HOME` (= `C:\Users\<name>`) | `~` (= `/Users/<name>`) |
| Stop the server | Ctrl+C | Ctrl+C |

> **Big gotcha:** in PowerShell, `set NAME=value` **does nothing useful** (that's the old cmd.exe syntax). Always use `$env:NAME="value"` in PowerShell. Settings only last for **that one window**: if they close it or open a new one, they must set them again before starting the server.

---

## 3. Install Python

**Windows**
1. Go to https://www.python.org/downloads/ and click the big yellow "Download Python 3.x" button.
2. Run the installer. **Tick "Add python.exe to PATH"** at the bottom of the first screen, then click "Install Now".
3. Open a **new** PowerShell window and check:
   ```powershell
   python --version
   ```
   It should say `Python 3.10` or higher. If it opens the Microsoft Store or says "not recognized", try `py --version`. If `py` works, use `py` everywhere this guide says `python`. If neither works, re-run the installer and make sure the PATH box is ticked.

**Mac**
1. Go to https://www.python.org/downloads/ and download the macOS installer. Run it.
2. Open Terminal and check:
   ```bash
   python3 --version
   ```
   It should say 3.10 or higher. (The `python3` that macOS ships may be older. If it is, the python.org install fixes that, so open a new Terminal window after installing.)

✅ Confirm the version number before moving on.

---

## 4. Get the code

Pick whichever is easier for them. The ZIP is usually easier for non-coders.

**Option A: download the ZIP (no Git needed)**
1. Open `https://github.com/mmunro3318/novig-trader` in the browser.
2. Click the green **Code** button → **Download ZIP**.
3. Unzip it somewhere easy, for example the Desktop. Windows: right-click the zip → "Extract All…". Mac: double-click it.
4. The folder may be called something like `novig-app-main`. That's fine. Inside it they should see `server.py`, `README.md`, `TRADER.md`, and folders `novig`, `static`, `tools`, `docs`.

**Option B: Git clone (if they already have Git)**
```
git clone https://github.com/mmunro3318/novig-trader novig-app
```

**Open a terminal in that folder.**
- Windows: open the folder in File Explorer, click the address bar, type `powershell` and press Enter. Or, in PowerShell: `cd $HOME\Desktop\novig-app-main` (adjust the name).
- Mac: in Terminal, type `cd ` (with a space), drag the folder onto the Terminal window, press Enter.

Check they're in the right place:
- Windows: `dir server.py`
- Mac: `ls server.py`

It should list the file, not say "not found".

**Install the add-ons**
- Windows:
  ```powershell
  python -m pip install -r requirements.txt
  ```
- Mac (use a "virtual environment", a private Python just for this folder, because newer Macs refuse plain installs):
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
  On a Mac they must run `source .venv/bin/activate` again in every new Terminal window before starting the app. The prompt shows `(.venv)` when it's active.

If `cryptography` fails to install, upgrade pip (`python -m pip install -U pip`) and try again. If it still fails, carry on: the app has a built-in fallback signer, and `requests` is the one that must install.

✅ Confirm: the install ends with "Successfully installed…" or "Requirement already satisfied".

---

## 5. Novig account and location check

1. Make an account on **novig.com** if they don't have one, and finish any identity checks Novig asks for.
2. Install the **Novig app on their phone**, sign in, and let it use location. Novig ties the API to the account holder's device location:
   - Every signed API call runs a location check. A failed check returns error **451**.
   - Placing a real-money order needs a passing device location check **in the last 3 days**. Opening the Novig app on the phone refreshes it.
   - VPNs, proxies, iCloud Private Relay and remote-desktop or location-spoofing software make the check fail. Turn them off.
3. The **paper** site is **paper.novig.com**. Have them sign in there too (it may use the same login; if it asks them to sign up, do that). Paper accounts start with $10,000 of play money. Novig's docs say paper has no location check, but production does.

✅ Confirm they can log in on paper.novig.com, and that the Novig app is installed on their phone.

---

## 6. Create the paper API key (play money)

### Background, so you can explain it simply
Novig has a few kinds of keys. Each key **only works on the site where it was made**: a paper key won't work on real money, and a real-money key won't work on paper.

| Key | Made where | What it can do | Needed for |
|---|---|---|---|
| **Management** | Profile → Settings → Novig API on the website | Runs the account: opens sub-accounts, moves money between them, makes other keys. **Can't place orders.** | One-time setup |
| **Trading** | Created by our setup script (with the management key) | Places and cancels orders **in one sub-account only** | Everyday trading in the app |
| `management::read` | Created via the API | Read-only view of every wallet | Optional: see real-money positions opened in Novig's own app |

**Important:** the API **cannot trade the main cash wallet**. It only trades a **sub-account** (a separate mini-wallet inside their Novig account). That's why the setup makes a sub-account, moves some money into it, and gives the app that sub-account's trading key. Bets placed in Novig's own app stay in the main wallet and must be sold in Novig's own app.

### Steps
1. **Make a secrets folder** in their home folder (outside the app folder):
   - Windows: `mkdir $HOME\.secrets`
   - Mac: `mkdir -p ~/.secrets && chmod 700 ~/.secrets`
2. On **paper.novig.com**: Profile → Settings → **Novig API** → **Create Key**. For the nickname, type **`paper-mgmt`** (any name works; this one keeps the files easy to tell apart). Press **Confirm Key Creation**.
3. The browser downloads a file like `novig-api-key-paper-mgmt.pem`. Novig shows the private key **only once**. Tell them: "Don't copy that private key into this chat. The downloaded file is all we need." If the download was blocked, have them copy the key from the screen into Notepad/TextEdit and save it as `novig-api-key-paper-mgmt.pem` in the `.secrets` folder (don't paste it here).
4. Only then press **I've saved my key**. Novig will never show it again. If it's lost, revoke the key on that screen and make a new one; that's fine and costs nothing.
5. Leave that page open. It shows the **key ID** (a long ID like `8f14e45f-…`) that the script will ask for.
6. **Move the .pem into the secrets folder:**
   - Windows: `Move-Item $HOME\Downloads\novig-api-key-paper-mgmt.pem $HOME\.secrets\`
   - Mac: `mv ~/Downloads/novig-api-key-paper-mgmt.pem ~/.secrets/ && chmod 600 ~/.secrets/*.pem`
   Check it's there (`dir $HOME\.secrets` / `ls ~/.secrets`).

✅ Confirm the .pem is in `.secrets` (just the file name, never the contents).

### Open the paper sub-account (one time)
The repo ships a tool for this: `tools/open_paper_subaccount.py`. It only talks to the **paper** site and refuses to run if anything points it at real money.
1. In the app folder (Mac: with `(.venv)` active), run:
   - Windows PowerShell:
     ```powershell
     python tools\open_paper_subaccount.py --pem "$HOME\.secrets\novig-api-key-paper-mgmt.pem"
     ```
   - Mac:
     ```bash
     python3 tools/open_paper_subaccount.py --pem ~/.secrets/novig-api-key-paper-mgmt.pem
     ```
   (If their .pem has a different name, use that name. `--fund 500` is the default amount of play money to move in; they can change it, e.g. `--fund 1000`.)
2. It asks for the **paper key ID**. Have them copy it from the Novig API page and paste it **into the terminal**, not into the chat.
3. It shows the paper balance and asks them to type **YES** (capital letters).
4. It should print `opened paper sub-account; trading key saved to …\.secrets\novig_subaccount.env`, then `moved $500 of PLAY money into it`.

What it did: opened a **paper** sub-account, made its trading key, saved that key to `~/.secrets/novig_subaccount.env` (on Windows `%USERPROFILE%\.secrets\novig_subaccount.env`, the exact file the app reads in paper mode), and moved play money in. It never prints the private key and won't overwrite an existing key file.

✅ Confirm they saw "opened paper sub-account".

---

## 7. Run in paper mode and do the first trade

1. In the app folder (Mac: with `(.venv)` active), turn paper orders on **for this window** and start the server:
   - Windows PowerShell:
     ```powershell
     $env:NOVIG_ALLOW_PAPER_ORDERS="1"
     python server.py 8601
     ```
   - Mac:
     ```bash
     export NOVIG_ALLOW_PAPER_ORDERS=1
     python3 server.py 8601
     ```
2. The first line should say: `Novig TRADER on http://localhost:8601/  env=paper orders=ON`.
   - `orders=OFF` means either the setting wasn't applied in this window (PowerShell: was it `$env:`, not `set`?) or `novig_subaccount.env` wasn't found. Go back to section 6.
   - Leave this window open. Closing it stops the app. Ctrl+C stops it on purpose.
3. Open **http://localhost:8601/** in the browser. The header should show a yellow **PAPER** badge and **orders ON**, plus a cash figure.
4. **First buy:** click a game on the left, then press **$1** on one side.
   - Watch the **Orders** list: QUEUED → WORKING → **FILLED**. During a live game, Novig holds in-game orders for about **5 seconds** before filling. That's normal.
   - UNFILLED means nobody was selling at that price. That's fine and costs nothing. Try again, or pick a busier game (NFL on a Sunday is best).
5. **Then sell it:** in **Positions** (right side), press **SELL ALL** on that position. Wait for FILLED. The position should go to "flat".
6. Celebrate a little. The app works end to end. 🎉

✅ Confirm both a FILLED buy and a FILLED sell.

**How to restart later (paper):** open a terminal in the folder (Mac: `source .venv/bin/activate`), set `NOVIG_ALLOW_PAPER_ORDERS` again, run the server, open the page.

---

## 8. Going live (real money): only later, only if they want to

Don't start this in the same session as the first paper trade unless they clearly want to. Before you begin, say out loud: **"This is real money. This is an experimental personal app with no guarantees. Start with $1 orders and only fund what you're fine losing."**

Full details: `docs/LIVE_TRADING.md`. In short:
1. On **novig.com** (the real site): Profile → Settings → Novig API → Create Key, nickname e.g. `live-mgmt`. Move the downloaded .pem into `.secrets`, same as before. (A paper key will **not** work here: each key only works on the site where it was made.)
2. Open the Novig app on their phone first, so the location check is fresh.
3. Open the real-money sub-account and fund it with a small amount (they choose it; `--fund 30` = $30). The script shows the cash balance and asks them to type **YES**.
   - Windows PowerShell:
     ```powershell
     $env:NOVIG_MGMT_KEY_ID="<live management key ID>"
     $env:NOVIG_MGMT_PEM="$HOME\.secrets\novig-api-key-live-mgmt.pem"
     python tools\open_live_subaccount.py --label live --fund 30
     ```
   - Mac:
     ```bash
     export NOVIG_MGMT_KEY_ID="<live management key ID>"
     export NOVIG_MGMT_PEM="$HOME/.secrets/novig-api-key-live-mgmt.pem"
     python3 tools/open_live_subaccount.py --label live --fund 30
     ```
   The user types the key ID into their own terminal; it doesn't need to go in the chat. The script saves the trading key to `~/.secrets/novig_live_trading.env`.
4. Start in live mode. **Both settings are required** (plus that trading key file):
   - Windows PowerShell:
     ```powershell
     $env:NOVIG_ENV="production"
     $env:NOVIG_ALLOW_LIVE_ORDERS="1"
     python server.py 8601
     ```
   - Mac:
     ```bash
     export NOVIG_ENV=production
     export NOVIG_ALLOW_LIVE_ORDERS=1
     python3 server.py 8601
     ```
   The header turns red: **PRODUCTION / orders ON**. `NOVIG_ALLOW_PAPER_ORDERS` doesn't matter in live mode.
5. Repeat the test with **$1**: one buy, then SELL ALL.
6. Built-in safety caps (they can change them with the same `$env:` / `export` method): `NOVIG_MAX_ORDER_USD` (default 25), `NOVIG_DAILY_LOSS_CAP_USD` (default 40; blocks buys, sells still work), `NOVIG_SLIP_CENTS` (default 2).

### Money mechanics to explain before live trading
- **Selling is really buying the other side.** Novig has no "sell" order. To exit "Team A", the app buys the same number of "Team B" contracts. Each matched A+B pair pays $1 back. Because that's a buy, **a sell needs cash up front**: roughly contracts ÷ 100 × the other side's price, plus the fee.
  - Example: selling 2,091 contracts when the other side costs 0.69 needs about **$14.40** in cash.
  - If cash is short, the app sells **in chunks it can afford**. Each chunk pays cash back right away, which funds the next chunk (usually 3–4 chunks in a few seconds). The Orders log shows each chunk.
  - Each position shows **"cash needed to exit at once"**, and the buy buttons warn (yellow ring) when a buy would leave too little cash to exit everything.
  - Practical rule: **keep spare cash in the sub-account.** Cheap long shots (e.g. 0.20) need the most cash to exit.
- **Fees:** about **3% per leg** on in-game trades, so a buy plus a sell costs roughly **6%, plus the spread**. Small swings can be eaten by fees.
- **Novig's "+$" on a sell** is the total payout, not profit.
- **Liquidity:** a sell needs someone on the other side. Late in a game the book can be thin, and the order may come back UNFILLED or PARTIAL. That costs nothing; try again or try a smaller size.

---

## 9. Troubleshooting

| What they see | Likely cause | Fix |
|---|---|---|
| `python` opens the Microsoft Store / "not recognized" | Python not on PATH | Use `py`, or reinstall with "Add python.exe to PATH" ticked, then open a **new** window |
| `No such file or directory: server.py` / `can't open file` | Terminal isn't in the app folder | `cd` into the folder that contains `server.py` (section 4) |
| `ModuleNotFoundError: requests` | Add-ons not installed (Mac: venv not active) | Re-run the install. Mac: `source .venv/bin/activate` first |
| Mac `error: externally-managed-environment` | Installing without a venv | Use the venv steps in section 4 |
| PowerShell "running scripts is disabled" (venv activate) | Execution policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or skip the venv on Windows |
| Server says `orders=OFF` on paper | `NOVIG_ALLOW_PAPER_ORDERS` not set in **this** window, or `set` used in PowerShell, or no `novig_subaccount.env` | `$env:NOVIG_ALLOW_PAPER_ORDERS="1"` in the same window, restart. Check `.secrets\novig_subaccount.env` exists |
| A script says the setting "is not set" even though they typed `set ...` | `set` doesn't work in PowerShell | Use `$env:NAME="value"` |
| **451** on orders (live) | Location check missing, failed or older than 3 days; VPN/Private Relay/remote desktop on | Open the Novig app on their phone (location on, VPN off), wait a minute, try again |
| 401 "api key not found" | Key used on the wrong site (a paper key on real money or the reverse) | Use a key made on the matching site |
| 401 `SIGNATURE_REJECTED` | Wrong .pem for that key ID, or the computer clock is off by >30 s | Match the .pem to its key ID; turn on automatic time sync |
| 403 `SCOPE_INSUFFICIENT` | Wrong kind of key (e.g. management key trying to trade) | Trading uses the sub-account trading key from the setup script |
| 409 when creating a management key | Only one management key is allowed per account per site | Revoke the old one (×) on the Novig API page, then create a new one |
| `INSUFFICIENT_BALANCE` on a sell | Sells are buys and need cash | The app sells in affordable chunks automatically; keep spare cash in the sub-account. Press SELL ALL again if it stopped |
| `INSUFFICIENT_BALANCE` on a buy | Sub-account cash too low | Buy smaller. Paper: $500 of play money is plenty for $1 tests. Live: move more into the sub-account from the Novig account (ask whoever shared the app how) |
| UNFILLED / PARTIAL | Nobody on the other side at that price (thin book, late game) | Costs nothing. Retry, size down, or raise max slip by 1–2¢ in the header |
| Header says "prices stale Ns", or 429 / RateLimited in the window | Novig rate limits; the app backs off on its own | Wait a few seconds. Close extra tabs of the app. Orders still go through their own lane |
| Buy shows WORKING for ~5 s in-game | Novig's in-game delay | Normal. Wait |
| Positions from Novig's own app show as read-only / can't be sold here | The API can't trade the main wallet | Sell those in Novig's own app |
| `open_paper_subaccount.py`: "does not exist" / "No .pem given" | Wrong `--pem` path | Check the file name in `.secrets` and use that exact path (keep the quotes on Windows) |
| `open_paper_subaccount.py`: "Novig refused that key on PAPER: 401 … api key not found" | The key was made on novig.com (real money), not paper.novig.com | Make the key on **paper.novig.com** |
| `open_paper_subaccount.py`: "NOVIG_ENV is set to production" | Live settings are still active in this window | Open a new window (or `Remove-Item Env:NOVIG_ENV` / `unset NOVIG_ENV`) |
| `open_paper_subaccount.py`: "already exists" | Paper is already set up | Skip to section 7 |
| Port 8601 busy | Another copy is running | Close the other window, or run `python server.py 8602` and open `http://localhost:8602/` |
| Anything else | | Copy the error text (check it has no keys in it) and send it to whoever shared the app. Add `$env:NOVIG_DEBUG="1"` / `export NOVIG_DEBUG=1` for fuller error output |

---

## 10. Checklist (tick off with them, one at a time)

Say each item, do it, and **get a "yes, done" before the next one**.

**Setup**
- [ ] They know whether they're on Windows (PowerShell) or Mac (Terminal).
- [ ] Python 3.10+ installed; `python --version` / `python3 --version` shows it.
- [ ] App files downloaded and unzipped; terminal is open in the folder; `server.py` is there.
- [ ] Add-ons installed (`requests`, `cryptography`). Mac: `.venv` made and active.
- [ ] Novig account exists; they can sign in on paper.novig.com; the Novig phone app is installed.
- [ ] `.secrets` folder exists in their home folder (not in the app folder).
- [ ] Paper management key created (nickname contains `paper`); .pem moved into `.secrets`; "I've saved my key" pressed.
- [ ] Reminded them: never paste key contents into this chat.
- [ ] `tools/open_paper_subaccount.py` ran and said "opened paper sub-account".

**First paper trade**
- [ ] Server started with `NOVIG_ALLOW_PAPER_ORDERS=1`; the first line says `env=paper orders=ON`.
- [ ] Page opens at http://localhost:8601/ with PAPER and orders ON in the header.
- [ ] $1 buy → FILLED.
- [ ] SELL ALL → FILLED, position flat.
- [ ] They know how to restart (new window = set the setting again).

**Live (only later, only if they ask)**
- [ ] Told them: real money, experimental app, no guarantees, start at $1.
- [ ] Live management key made on novig.com; .pem in `.secrets`.
- [ ] Novig phone app opened recently (location check fresh).
- [ ] `open_live_subaccount.py` ran with a small `--fund` amount; trading key saved.
- [ ] Server started with `NOVIG_ENV=production` + `NOVIG_ALLOW_LIVE_ORDERS=1`; header shows PRODUCTION / orders ON.
- [ ] $1 buy → FILLED; SELL ALL → FILLED.
- [ ] Explained: sells need cash (keep spare), ~3% fee per leg, trades from Novig's own app must be sold there.
