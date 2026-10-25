# Going live (real money): what key to create and how to plug it in

**Status (Oct 25, 2026):** the trader runs on PAPER with orders ON. In production it is **read-only**: it shows your Novig app wallet (positions, value, P&L, break-even) through the `management::read` key. **Live orders have never been sent or tested by the bot.**

## Why a new key is needed
- Novig API orders can only be placed by a **`trading` key, and every trading key belongs to one sub-account**. Your management key ("Proto") can't place orders, and neither can `management::read`.
- **Positions you open in the Novig app sit in your cash wallet, and the API can't trade the cash wallet.** In this app they show as *read-only*, so sell those in Novig's app. Only positions opened through this app, in the API sub-account, get the one-tap **SELL ALL** button.

## Steps (you do these yourself; nothing moves money automatically)
1. On your PC, with your production management key.
   - **PowerShell** (the default Windows terminal; `set X=...` does nothing there):
     ```powershell
     $env:NOVIG_MGMT_KEY_ID="<management key id>"
     $env:NOVIG_MGMT_PEM="$HOME\Downloads\novig-api-key-<name>.pem"
     python tools\open_live_subaccount.py --label grok-live --fund 50
     ```
   - **cmd.exe:**
     ```bat
     set NOVIG_MGMT_KEY_ID=<management key id>
     set NOVIG_MGMT_PEM=%USERPROFILE%\Downloads\novig-api-key-<name>.pem
     python tools\open_live_subaccount.py --label grok-live --fund 50
     ```
   - Run the script in the same window where you set the variables.
   - This opens a sub-account plus its **trading** key (`POST /v3/account/subaccounts`), saves the key to `%USERPROFILE%\.secrets\novig_live_trading.env`, and optionally moves $50 from your cash wallet (`.../transfer`, direction `fund`).
   - It asks you to type YES first.
   - You can also do this in the Novig web app if it offers sub-accounts.
2. Run the trader in live mode. **All three switches are required:**
   ```powershell
   # PowerShell
   $env:NOVIG_ENV="production"; $env:NOVIG_ALLOW_LIVE_ORDERS="1"; python server.py 8601
   ```
   ```bat
   :: cmd.exe
   set NOVIG_ENV=production
   set NOVIG_ALLOW_LIVE_ORDERS=1
   python server.py 8601
   ```
   - The trading key is read from `novig_live_trading.env`, or from `NOVIG_LIVE_API_KEY` / `NOVIG_LIVE_API_SECRET`.
   - Reads use `novig_prod_read.env` (`NOVIG_READ_API_KEY` / `NOVIG_READ_API_SECRET`, the management::read key).
3. The header badge turns red **PRODUCTION / orders ON**. Start with $1 orders.
4. Safety caps (change them with env vars):
   - `NOVIG_MAX_ORDER_USD` (default 25)
   - `NOVIG_DAILY_LOSS_CAP_USD` (default 40; blocks BUYs, sells still work)
   - `NOVIG_SLIP_CENTS` (default 2)

Production also runs a **location check**. If orders return 451, Novig wants device geolocation in the last 3 days (open the Novig app on that device).
