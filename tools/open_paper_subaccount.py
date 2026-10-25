"""PAPER (play money) setup: opens a Novig PAPER sub-account with its trading key and funds it from your
paper cash wallet. Paper host only (https://api.paper.novig.com); it refuses to talk to anything else.
Run it once, yourself, from the novig-app folder:

  PowerShell:  python tools\\open_paper_subaccount.py --pem "$HOME\\.secrets\\novig-api-key-paper-mgmt.pem"
  Mac/Linux:   python3 tools/open_paper_subaccount.py --pem ~/.secrets/novig-api-key-paper-mgmt.pem

It asks for your PAPER management key ID in the terminal (the ID, never the private key), shows your paper
balance, and asks you to type YES. Writes ~/.secrets/novig_subaccount.env (on Windows
%USERPROFILE%\\.secrets\\novig_subaccount.env) with NOVIG_SUB_API_KEY / NOVIG_SUB_API_SECRET, the file the
trader reads in paper mode. Never prints the private key, never overwrites an existing file.
Requires the `cryptography` package OR uses the bundled pure-python Ed25519 keygen."""
import argparse, os, sys, uuid, secrets, base64
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from novig.client import Novig, PAPER_HOST, SUB_ENV_FILE
from novig.ed25519_pure import PureEd25519Key

HINT = """  PowerShell:  python tools\\open_paper_subaccount.py --pem "$HOME\\.secrets\\novig-api-key-paper-mgmt.pem"
  Mac/Linux:   python3 tools/open_paper_subaccount.py --pem ~/.secrets/novig-api-key-paper-mgmt.pem
  (Make the key on paper.novig.com: Profile -> Settings -> Novig API -> Create Key.)"""

def spki_pem(pub32: bytes) -> str:
    der = bytes.fromhex("302a300506032b6570032100") + pub32
    b = base64.b64encode(der).decode(); return "-----BEGIN PUBLIC KEY-----\n" + b + "\n-----END PUBLIC KEY-----\n"

def failed(r): return not isinstance(r, dict) or r.get("ok") is False

def describe(r):
    if not isinstance(r, dict): return str(r)[:200]
    return " ".join(str(x) for x in (r.get("status"), r.get("code") or r.get("error"), r.get("message")) if x)

ap = argparse.ArgumentParser(description="Open a PAPER (play money) Novig sub-account + trading key.")
ap.add_argument("--pem", help="path to your PAPER management key .pem (default: $NOVIG_PAPER_MGMT_PEM)")
ap.add_argument("--label", default="paper-trading", help="sub-account label (display only)")
ap.add_argument("--fund", default="500", help="play money to move into the sub-account (default 500; 0 = none)")
a = ap.parse_args()

# ---- paper only: refuse anything that points at production
if os.getenv("NOVIG_ENV", "paper").lower() == "production":
    sys.exit("NOVIG_ENV is set to production in this window. This tool is PAPER only.\n"
             "  Open a new window, or clear it:  PowerShell: Remove-Item Env:NOVIG_ENV   Mac/Linux: unset NOVIG_ENV\n"
             "  For real money use tools/open_live_subaccount.py instead (see docs/LIVE_TRADING.md).")
if os.getenv("NOVIG_HOST") and os.getenv("NOVIG_HOST").rstrip("/") != PAPER_HOST:
    sys.exit(f"NOVIG_HOST is {os.getenv('NOVIG_HOST')}, not the paper host {PAPER_HOST}. Refusing.\n"
             "  Clear it:  PowerShell: Remove-Item Env:NOVIG_HOST   Mac/Linux: unset NOVIG_HOST")
try: fund = float(a.fund)
except ValueError: sys.exit(f"--fund must be a number, got {a.fund!r}")
if fund < 0: sys.exit("--fund can't be negative")

out = SUB_ENV_FILE
if os.path.exists(out):
    sys.exit(f"{out} already exists, so a paper trading key is already set up. Not overwriting it.\n"
             "  To start over, move or rename that file first, then run this again.")

pem = (a.pem or os.getenv("NOVIG_PAPER_MGMT_PEM") or "").strip().strip('"').strip("'")
if not pem:
    sys.exit("No .pem given. Pass the path to your PAPER management key file with --pem:\n" + HINT)
pem = os.path.expanduser(pem)
if not os.path.exists(pem):
    sys.exit(f"--pem points to a file that does not exist: {pem}\n" + HINT)

kid = (os.getenv("NOVIG_PAPER_MGMT_KEY_ID") or input("Paste your PAPER management key ID (the ID, not the private key), then Enter: ")).strip()
if not kid: sys.exit("No key ID entered.\n" + HINT)

m = Novig(host=PAPER_HOST, key_id=kid, secret=pem)
if m.host != PAPER_HOST or not m.is_paper: sys.exit("internal check failed: not the paper host. Refusing.")
bal = m.balance()
if failed(bal):
    sys.exit(f"Novig refused that key on PAPER: {describe(bal)}\n"
             "  401 'api key not found' usually means the key was made on novig.com (real money), not paper.novig.com.\n"
             "  401 SIGNATURE_REJECTED: the .pem doesn't belong to that key ID, or your clock is off.\n" + HINT)
print("paper cash wallet:", bal.get("balance", bal))
if input(f"Open PAPER sub-account '{a.label}'" + (f" and move ${fund:g} of play money into it" if fund > 0 else "") + "? type YES: ") != "YES":
    sys.exit("aborted")

seed = secrets.token_bytes(32); k = PureEd25519Key(seed)
r = m._signed("POST", "/v3/account/subaccounts", body={"label": a.label, "publicKey": spki_pem(k.pub), "algorithm": "Ed25519"})
if failed(r) or "keyId" not in r: sys.exit(f"Could not open the paper sub-account: {describe(r)}")
os.makedirs(os.path.dirname(out), exist_ok=True)
fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)   # never overwrite, private on mac/Linux
with os.fdopen(fd, "w") as fh: fh.write(f"NOVIG_SUB_API_KEY={r['keyId']}\nNOVIG_SUB_API_SECRET={seed.hex()}\n")
print("opened paper sub-account; trading key saved to", out)
if fund > 0:
    t = m._signed("POST", f"/v3/account/subaccounts/{r['keyId']}/transfer",
                  body={"direction": "fund", "amount": f"{fund:.5f}", "clientTransferId": str(uuid.uuid4())})
    if failed(t): print(f"funding failed: {describe(t)}. The sub-account exists; fund it on paper.novig.com or ask for help.")
    else: print(f"moved ${fund:g} of PLAY money into it")
print("next: set NOVIG_ALLOW_PAPER_ORDERS=1 and run the server\n"
      '  PowerShell:  $env:NOVIG_ALLOW_PAPER_ORDERS="1"; python server.py 8601\n'
      "  Mac/Linux:   export NOVIG_ALLOW_PAPER_ORDERS=1; python3 server.py 8601")
