"""RUN THIS YOURSELF (Michael) on your own computer: opens a REAL-MONEY Novig API sub-account with its trading key,
and optionally funds it from your cash wallet. Nothing here runs automatically; the bot does not run it.

  PowerShell:  $env:NOVIG_MGMT_KEY_ID="<management key id>"
               $env:NOVIG_MGMT_PEM="C:\\path\\to\\novig-api-key-<name>.pem"
  cmd.exe:     set NOVIG_MGMT_KEY_ID=<management key id>
               set NOVIG_MGMT_PEM=C:\\path\\to\\novig-api-key-<name>.pem
  then:        python tools\\open_live_subaccount.py --label grok-live --fund 50

Writes %USERPROFILE%\\.secrets\\novig_live_trading.env (NOVIG_LIVE_API_KEY / NOVIG_LIVE_API_SECRET). Keep it private.
Requires the `cryptography` package OR uses the bundled pure-python Ed25519 keygen."""
import argparse, os, sys, uuid, hashlib, secrets, base64
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from novig.client import Novig, PROD_HOST
from novig.ed25519_pure import PureEd25519Key

def spki_pem(pub32: bytes) -> str:
    der = bytes.fromhex("302a300506032b6570032100") + pub32
    b = base64.b64encode(der).decode(); return "-----BEGIN PUBLIC KEY-----\n" + b + "\n-----END PUBLIC KEY-----\n"

ap = argparse.ArgumentParser(); ap.add_argument("--label", default="grok-live"); ap.add_argument("--fund", default="0")
a = ap.parse_args()
kid, pem = os.environ.get("NOVIG_MGMT_KEY_ID"), os.environ.get("NOVIG_MGMT_PEM")
if not (kid and pem): sys.exit("""NOVIG_MGMT_KEY_ID and NOVIG_MGMT_PEM are not set (production management key).
  PowerShell (note: `set X=...` does NOT work in PowerShell):
      $env:NOVIG_MGMT_KEY_ID="<management key id>"
      $env:NOVIG_MGMT_PEM="C:\\Users\\<you>\\Downloads\\novig-api-key-<name>.pem"
  cmd.exe:
      set NOVIG_MGMT_KEY_ID=<management key id>
      set NOVIG_MGMT_PEM=C:\\Users\\<you>\\Downloads\\novig-api-key-<name>.pem
  Then run this script again in the SAME window.""")
if not os.path.exists(pem) and "BEGIN" not in pem: sys.exit(f"NOVIG_MGMT_PEM points to a file that does not exist: {pem}")
m = Novig(host=PROD_HOST, key_id=kid, secret=pem)
print("balance (cash wallet):", m.balance())
if input(f"Open REAL-MONEY sub-account '{a.label}'" + (f" and move ${a.fund} into it" if float(a.fund) > 0 else "") + "? type YES: ") != "YES": sys.exit("aborted")
seed = secrets.token_bytes(32); k = PureEd25519Key(seed)
r = m._signed("POST", "/v3/account/subaccounts", body={"label": a.label, "publicKey": spki_pem(k.pub), "algorithm": "Ed25519"})
if "keyId" not in r: sys.exit(f"failed: {r}")
out = os.path.join(os.path.expanduser("~"), ".secrets"); os.makedirs(out, exist_ok=True); path = os.path.join(out, "novig_live_trading.env")
with open(path, "w") as fh: fh.write(f"NOVIG_LIVE_API_KEY={r['keyId']}\nNOVIG_LIVE_API_SECRET={seed.hex()}\n")
try: os.chmod(path, 0o600)
except Exception: pass
print("opened sub-account; trading key saved to", path)
if float(a.fund) > 0:
    t = m._signed("POST", f"/v3/account/subaccounts/{r['keyId']}/transfer", body={"direction": "fund", "amount": f"{float(a.fund):.5f}", "clientTransferId": str(uuid.uuid4())})
    print("fund:", t)
