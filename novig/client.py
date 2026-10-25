"""Typed Novig API v3 client.

* Public `/v3/public/*` reads + data.novig.com CSVs work with no key (live).
* Signed routes need NOVIG_API_KEY (key UUID) + NOVIG_API_SECRET (PKCS#8 PEM private key,
  Ed25519 or P-256 -- either the PEM text itself or a path to the .pem file).
  Without them every signed call returns a NoKey result instead of raising.
* Writes (orders, cancels, transfers, keys) are GATED:
    - refused outright unless NOVIG_HOST is the PAPER host;
    - even on paper, they are dry-run previews unless NOVIG_ALLOW_PAPER_ORDERS=1.
  There is no code path that sends a write to production.
Contracts: see ../novig-cheatsheet.md (generated from the official OpenAPI 3.1 spec).
"""
from __future__ import annotations
import base64, hashlib, json, os, time, uuid, urllib.parse
from decimal import Decimal, ROUND_DOWN
from typing import Any, Literal, NotRequired, TypedDict
import requests

PAPER_HOST = "https://api.paper.novig.com"
PROD_HOST = "https://api.novig.com"
DATA_HOST = "https://data.novig.com/reporting/trade-data"

# ---------------------------------------------------------------- contracts (typed)
EventStatus = Literal["OPEN_PREGAME", "CLOSED_PREGAME", "OPEN_INGAME", "SETTLED", "FINAL", "DELAYED", "CANCELED"]
MarketStatus = Literal["OPEN", "CLOSED", "SETTLED"]
TIF = Literal["GTC", "GTT", "IOC", "FOK", "PO"]
OrderStatus = Literal["PENDING", "OPEN", "FILLED", "CANCELED", "REJECTED"]
TransactionKind = Literal["FILL", "FEE", "MAKER_CREDIT", "SETTLEMENT", "TRANSFER_IN", "TRANSFER_OUT", "DEPOSIT",
                          "WITHDRAWAL", "CREDIT", "CREDIT_RECLAIM", "ADJUSTMENT", "FORWARDING"]

class Event(TypedDict):
    eventId: str; description: str; sport: str; league: str; status: EventStatus; startsTs: int
class Level(TypedDict):
    price: str; qty: int
class Outcome(TypedDict):
    outcomeId: str; name: str; status: str; last: NotRequired[str]; bid: NotRequired[Level]
class MarketFee(TypedDict):
    coefficient: str; makerCredit: str; charged: Literal["ALWAYS", "WHEN_LIVE"]
class Market(TypedDict):
    marketId: str; eventId: str; description: str; marketType: str; strike: NotRequired[str]
    status: MarketStatus; voids: Literal["PUSH", "FMV"]; startsTs: int; fee: MarketFee
    outcomes: list[Outcome]; volume: int; openInterest: int
class BookOrder(TypedDict):
    orderId: str; price: str; qty: int
class Book(TypedDict):
    marketId: str; seq: int; orders: dict[str, list[BookOrder]]
class Trade(TypedDict):
    tradeId: str; takeId: str; outcomeId: str; price: str; qty: int; ts: int
class Page(TypedDict):
    items: list; next: NotRequired[str]
class Order(TypedDict):
    orderId: str; clientId: NotRequired[str]; marketId: str; outcomeId: str; price: str; qty: int
    remaining: int; status: OrderStatus; tif: TIF; createdTs: int; expiresTs: NotRequired[int]
class Fill(TypedDict):
    fillId: str; orderId: str; clientId: NotRequired[str]; marketId: str; outcomeId: str
    qty: int; cost: str; fee: NotRequired[str]; taker: bool; ts: int
class Position(TypedDict):
    marketId: str; outcomeId: str; qty: int; cost: str
class HistoricalPosition(Position):
    positionId: str; status: MarketStatus; result: str; payout: NotRequired[str]; pnl: NotRequired[str]
    settledTs: NotRequired[int]; resettled: bool
class Transaction(TypedDict):
    transactionId: str; kind: TransactionKind; amount: str; ref: NotRequired[str]; ts: int
class PlaceOrder(TypedDict):
    outcomeId: str; price: str; qty: int; tif: TIF; ttl: NotRequired[int]; clientId: NotRequired[str]

# ---------------------------------------------------------------- math helpers
def on_grid(price: str) -> bool:
    m = int((Decimal(price) * 1000).to_integral_value())
    return Decimal(price) * 1000 == m and (1 <= m <= 50 or 950 <= m <= 999 or (51 <= m <= 949 and m % 5 == 0))

def snap_down(p: float | str | Decimal) -> str:
    m = int((Decimal(str(p)) * 1000).to_integral_value(rounding=ROUND_DOWN))
    if not 1 <= m <= 999: raise ValueError("price must be in (0,1)")
    if 51 <= m <= 949: m -= m % 5
    return f"{m/1000:.3f}"

def american(p: float) -> str:
    if p <= 0 or p >= 1: return "—"
    return f"{-100*p/(1-p):+.0f}" if p >= 0.5 else f"+{100*(1-p)/p:.0f}"

def cost_usd(price: str, qty: int) -> Decimal:   # 1 contract pays 1 cent
    return (Decimal(price) * qty / 100).quantize(Decimal("0.00001"))

def taker_fee_usd(price: str, qty: int, coefficient: str = "0.06") -> Decimal:
    p = Decimal(price); return (Decimal(coefficient) * p * (1 - p) * qty / 100).quantize(Decimal("0.00001"))

# ---------------------------------------------------------------- signing (NOVIG-V3)
def canonical_query(raw: str) -> str:
    if not raw: return ""
    pairs = []
    for part in raw.split("&"):
        k, _, v = part.partition("=")
        dec = lambda s: urllib.parse.unquote(s.replace("+", "%2B"))
        enc = lambda s: urllib.parse.quote(s, safe="-._~")
        pairs.append((enc(dec(k)), enc(dec(v))))
    pairs.sort(key=lambda kv: (kv[0].encode(), kv[1].encode()))
    return "&".join(f"{k}={v}" for k, v in pairs)

def canonical_string(ts: int, method: str, path: str, raw_query: str, body: bytes) -> str:
    return "\n".join(["NOVIG-V3", str(ts), method.upper(), path, canonical_query(raw_query),
                      hashlib.sha256(body).hexdigest()])

def _load_key(secret: str):
    """Accepts PKCS#8 PEM text, a path to a .pem, or a raw 32-byte Ed25519 seed as hex (64 chars) / base64.
    Uses `cryptography` when installed, else a pure-python Ed25519 signer (Windows without pip)."""
    if os.path.exists(secret.strip()): secret = open(secret.strip()).read()
    try:
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        from novig.ed25519_pure import load
        return load(secret)
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    secret = secret.strip()
    if "BEGIN" not in secret and not os.path.exists(secret):
        try: raw = bytes.fromhex(secret)
        except ValueError: raw = base64.b64decode(secret)
        if len(raw) not in (32, 64):  # base64 PKCS#8 DER body (Ed25519 = 48 bytes, P-256 ~138)
            return serialization.load_der_private_key(raw, password=None)
        if len(raw) == 64: raw = raw[:32]  # seed||pub form
        return ed25519.Ed25519PrivateKey.from_private_bytes(raw)
    pem = open(secret, "rb").read() if os.path.exists(secret) else secret.encode()
    return serialization.load_pem_private_key(pem, password=None)

def sign(key, msg: str) -> str:
    if type(key).__name__ == "PureEd25519Key": return base64.b64encode(key.sign(msg.encode())).decode()
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519
    from cryptography.hazmat.primitives import hashes
    if isinstance(key, ed25519.Ed25519PrivateKey): sig = key.sign(msg.encode())
    else: sig = key.sign(msg.encode(), ec.ECDSA(hashes.SHA256()))  # DER
    return base64.b64encode(sig).decode()

# ---------------------------------------------------------------- client
def no_key(route: str) -> dict:
    return {"ok": False, "error": "NO_KEY", "route": route,
            "message": "Set NOVIG_API_KEY (key id) and NOVIG_API_SECRET (PEM private key or path) for the PAPER account."}

class Novig:
    def __init__(self, host: str | None = None, key_id: str | None = None, secret: str | None = None, timeout=(5, 12)):
        self.host = (host or os.getenv("NOVIG_HOST") or PAPER_HOST).rstrip("/")
        self.key_id = ((os.getenv("NOVIG_API_KEY") if key_id is None else key_id) or "").strip() or None
        self._secret = os.getenv("NOVIG_API_SECRET") if secret is None else secret
        self._key = _load_key(self._secret) if (self.key_id and self._secret) else None
        self.timeout = timeout; self.s = requests.Session()

    @property
    def has_key(self) -> bool: return self._key is not None
    @property
    def is_paper(self) -> bool: return self.host == PAPER_HOST
    @property
    def writes_enabled(self) -> bool:
        return self.has_key and self.is_paper and os.getenv("NOVIG_ALLOW_PAPER_ORDERS") == "1"

    # low level
    def _public(self, path: str, **params) -> Any:
        r = self.s.get(self.host + path, params={k: v for k, v in params.items() if v is not None}, timeout=self.timeout)
        r.raise_for_status(); return r.json()

    def _signed(self, method: str, path: str, params: dict | None = None, body: Any = None) -> Any:
        if not self.has_key: return no_key(f"{method} {path}")
        q = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        raw = json.dumps(body, separators=(",", ":")).encode() if body is not None else b""
        ts = int(time.time() * 1000)
        h = {"Novig-Key-Id": self.key_id, "Novig-Timestamp": str(ts),
             "Novig-Signature": sign(self._key, canonical_string(ts, method, path, q, raw))}
        if body is not None: h["Content-Type"] = "application/json"
        r = self.s.request(method, self.host + path + (f"?{q}" if q else ""), data=raw or None, headers=h, timeout=self.timeout)
        try: data = r.json()
        except ValueError: data = {"raw": r.text}
        if r.ok: return data
        out = {"ok": False, "status": r.status_code, **(data if isinstance(data, dict) else {"body": data})}
        if r.status_code == 429: out["retryAfter"] = r.headers.get("Retry-After")
        return out

    live_trading = False   # only live_trading_client() sets this

    @property
    def live_writes_enabled(self) -> bool:
        return (not self.is_paper and self.live_trading and self.has_key and os.getenv("NOVIG_ENV") == "production"
                and os.getenv("NOVIG_ALLOW_LIVE_ORDERS") == "1")

    def _write(self, method: str, path: str, body: Any = None, params: dict | None = None) -> Any:
        if not self.is_paper:
            if self.live_writes_enabled and path.startswith("/v3/orders"):
                return self._signed(method, path, params, body)   # REAL MONEY: triple-gated, orders/cancels only
            return {"ok": False, "error": "REFUSED_NOT_PAPER", "message": "Live orders need NOVIG_ENV=production, NOVIG_ALLOW_LIVE_ORDERS=1 and a trading-scoped live key."}
        if not self.has_key: return no_key(f"{method} {path}")
        if not self.writes_enabled:
            return {"ok": True, "dryRun": True, "would_send": {"method": method, "path": path, "params": params, "body": body},
                    "message": "Dry run. Set NOVIG_ALLOW_PAPER_ORDERS=1 to send to the PAPER exchange."}
        return self._signed(method, path, params, body)

    # ---- public (live, no key)
    def sports(self) -> list[str]: return self._public("/v3/public/types/sports")
    def leagues(self) -> list[str]: return self._public("/v3/public/types/leagues")
    def market_types(self) -> list[str]: return self._public("/v3/public/types/markets")
    def live_market_types(self) -> dict[str, list[str]]: return self._public("/v3/public/types/markets/live")
    def event_statuses(self) -> list[str]: return self._public("/v3/public/types/event-statuses")
    def events(self, league=None, eventStatus=None, startsAfter=None, startsBefore=None, limit=None, after=None) -> Page:
        return self._public("/v3/public/catalog/events", league=league, eventStatus=eventStatus, startsAfter=startsAfter,
                            startsBefore=startsBefore, limit=limit, after=after)
    def event(self, event_id: str) -> Event: return self._public(f"/v3/public/catalog/events/{event_id}")
    def markets(self, league=None, marketType=None, eventStatus=None, event=None, startsAfter=None, startsBefore=None,
                limit=None, after=None) -> Page:
        return self._public("/v3/public/catalog/markets", league=league, marketType=marketType, eventStatus=eventStatus,
                            event=event, startsAfter=startsAfter, startsBefore=startsBefore, limit=limit, after=after)
    def all_markets(self, **kw) -> list[Market]:
        out, after = [], None
        while True:
            pg = self.markets(after=after, limit=kw.pop("limit", 1000), **kw); out += pg["items"]; after = pg.get("next")
            if not after or not pg["items"]: return out
    def market(self, market_id: str) -> Market: return self._public(f"/v3/public/catalog/markets/{market_id}")
    def book(self, market_id: str) -> Book: return self._public(f"/v3/public/catalog/markets/{market_id}/book")
    def trades(self, market_id: str, limit=None, after=None) -> Page:
        return self._public(f"/v3/public/catalog/markets/{market_id}/trades", limit=limit, after=after)
    # data.novig.com
    def data_index(self) -> dict: return self.s.get(f"{DATA_HOST}/index.json", timeout=self.timeout).json()
    def data_csv(self, date: str, which: Literal["trades", "markets"]) -> str:
        return self.s.get(f"{DATA_HOST}/{date}/{which}.csv", timeout=60).text

    # ---- signed reads (any key)
    def time(self): return self._signed("GET", "/v3/time")
    def exchange_status(self): return self._signed("GET", "/v3/exchange/status")
    def limits(self): return self._signed("GET", "/v3/limits")
    def echo(self, body: dict): return self._signed("POST", "/v3/echo", body=body)
    def consensus(self, **p): return self._signed("GET", "/v3/catalog/consensus", p)
    def participants(self, **p): return self._signed("GET", "/v3/catalog/participants", p)
    def history_events(self, **p): return self._signed("GET", "/v3/history/events", p)
    def history_event(self, i): return self._signed("GET", f"/v3/history/events/{i}")
    def history_markets(self, **p): return self._signed("GET", "/v3/history/markets", p)
    def history_market(self, i): return self._signed("GET", f"/v3/history/markets/{i}")
    def candles(self, market_id, interval: Literal["1m", "5m", "1h", "1d"] = "1h", **p):
        return self._signed("GET", f"/v3/history/markets/{market_id}/candles", {"interval": interval, **p})
    def history_trades(self, **p): return self._signed("GET", "/v3/history/trades", p)
    # ---- account / portfolio
    def balance(self): return self._signed("GET", "/v3/account/balance")
    def account_orders(self): return self._signed("GET", "/v3/account/orders")
    def account_positions(self): return self._signed("GET", "/v3/account/positions")
    def subaccounts(self): return self._signed("GET", "/v3/account/subaccounts")
    def subaccount_balance(self, key_id): return self._signed("GET", f"/v3/account/subaccounts/{key_id}/balance")
    def subaccount_transactions(self, key_id, **p): return self._signed("GET", f"/v3/account/subaccounts/{key_id}/transactions", p)
    def subaccount_transfer_get(self, key_id, tid): return self._signed("GET", f"/v3/account/subaccounts/{key_id}/transfers/{tid}")
    def transactions(self, **p): return self._signed("GET", "/v3/account/transactions", p)
    def transfers(self, **p): return self._signed("GET", "/v3/account/transfers", p)
    def transfer(self, tid): return self._signed("GET", f"/v3/account/transfers/{tid}")
    def keys(self): return self._signed("GET", "/v3/keys")
    def key(self, kid): return self._signed("GET", f"/v3/keys/{kid}")
    def orders(self, **p): return self._signed("GET", "/v3/orders", p)
    def order(self, oid): return self._signed("GET", f"/v3/orders/{oid}")
    def fills(self, **p): return self._signed("GET", "/v3/portfolio/fills", p)
    def positions(self): return self._signed("GET", "/v3/portfolio/positions")
    def history_positions(self, **p): return self._signed("GET", "/v3/history/positions", p)
    def history_position(self, pid): return self._signed("GET", f"/v3/history/positions/{pid}")

    # ---- writes (GATED: paper only, dry-run unless NOVIG_ALLOW_PAPER_ORDERS=1)
    @staticmethod
    def validate_order(o: dict) -> PlaceOrder:
        price = str(o["price"])
        if not on_grid(price): raise ValueError(f"price {price} off grid; snap_down -> {snap_down(price)}")
        qty = int(o["qty"]); tif = o.get("tif", "GTC")
        if qty <= 0: raise ValueError("qty must be > 0")
        if tif not in ("GTC", "GTT", "IOC", "FOK", "PO"): raise ValueError("bad tif")
        out: PlaceOrder = {"outcomeId": str(o["outcomeId"]), "price": f"{Decimal(price):.3f}", "qty": qty, "tif": tif,
                           "clientId": o.get("clientId") or str(uuid.uuid4())}
        if tif == "GTT" and not o.get("ttl"): raise ValueError("GTT requires ttl")
        if o.get("ttl"):
            if tif not in ("GTT", "PO"): raise ValueError("ttl only for GTT/PO")
            out["ttl"] = int(o["ttl"])
        return out
    def place_order(self, o: dict): return self._write("POST", "/v3/orders", self.validate_order(o))
    def place_batch(self, orders: list[dict]): return self._write("POST", "/v3/orders/batch", {"orders": [self.validate_order(o) for o in orders]})
    def cancel_order(self, oid: str): return self._write("DELETE", f"/v3/orders/{oid}")
    def cancel_batch(self, ids: list[str]): return self._write("DELETE", "/v3/orders/batch", {"orderIds": ids})
    def cancel_all(self, market=None, event=None): return self._write("DELETE", "/v3/orders", params={"market": market, "event": event})
    def fund_subaccount(self, key_id, amount: str, direction: Literal["fund", "defund"] = "fund"):
        return self._write("POST", f"/v3/account/subaccounts/{key_id}/transfer",
                           {"amount": amount, "direction": direction, "clientTransferId": str(uuid.uuid4())})
    def open_subaccount(self, body: dict): return self._write("POST", "/v3/account/subaccounts", body)
    def label_subaccount(self, key_id, label): return self._write("PATCH", f"/v3/account/subaccounts/{key_id}", {"label": label})
    def create_key(self, body: dict): return self._write("POST", "/v3/keys", body)
    def revoke_key(self, kid): return self._write("DELETE", f"/v3/keys/{kid}")

# ---------------------------------------------------------------- sub-account trading key
SUB_ENV_FILE = os.path.expanduser(os.getenv("NOVIG_SUB_ENV_FILE", "~/.secrets/novig_subaccount.env"))
def _load_env_file(path: str) -> dict:
    out = {}
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); out[k.strip()] = v.strip()
    return out

def trading_client(host: str | None = None) -> "Novig":
    """Client signed with the SUB-ACCOUNT trading key (NOVIG_SUB_API_KEY / NOVIG_SUB_API_SECRET from env,
    else from ~/.secrets/novig_subaccount.env). Management keys cannot trade; use this for orders/fills/positions.
    Writes stay gated exactly like Novig._write (paper only, dry-run unless NOVIG_ALLOW_PAPER_ORDERS=1)."""
    f = _load_env_file(SUB_ENV_FILE)
    kid = os.getenv("NOVIG_SUB_API_KEY") or f.get("NOVIG_SUB_API_KEY")
    sec = os.getenv("NOVIG_SUB_API_SECRET") or f.get("NOVIG_SUB_API_SECRET")
    if not (kid and sec): return Novig(host=host, key_id="", secret="")  # behaves as no-key
    return Novig(host=host or f.get("NOVIG_HOST"), key_id=kid, secret=sec)

# ---------------------------------------------------------------- production (real money) clients
PROD_READ_ENV_FILE = os.path.expanduser(os.getenv("NOVIG_PROD_READ_ENV_FILE", "~/.secrets/novig_prod_read.env"))
LIVE_TRADING_ENV_FILE = os.path.expanduser(os.getenv("NOVIG_LIVE_ENV_FILE", "~/.secrets/novig_live_trading.env"))

def prod_read_client() -> "Novig":
    """management::read key on PRODUCTION (reads every wallet; cannot trade or move money)."""
    f = _load_env_file(PROD_READ_ENV_FILE)
    kid = os.getenv("NOVIG_READ_API_KEY") or f.get("NOVIG_READ_API_KEY"); sec = os.getenv("NOVIG_READ_API_SECRET") or f.get("NOVIG_READ_API_SECRET")
    return Novig(host=PROD_HOST, key_id=kid or "", secret=sec or "")

def live_trading_client() -> "Novig | None":
    """Sub-account TRADING key on PRODUCTION (NOVIG_LIVE_API_KEY / NOVIG_LIVE_API_SECRET, env or ~/.secrets/novig_live_trading.env).
    Orders only go out when NOVIG_ENV=production AND NOVIG_ALLOW_LIVE_ORDERS=1 as well."""
    f = _load_env_file(LIVE_TRADING_ENV_FILE)
    kid = os.getenv("NOVIG_LIVE_API_KEY") or f.get("NOVIG_LIVE_API_KEY"); sec = os.getenv("NOVIG_LIVE_API_SECRET") or f.get("NOVIG_LIVE_API_SECRET")
    if not (kid and sec): return None
    c = Novig(host=PROD_HOST, key_id=kid, secret=sec); c.live_trading = True; return c

# ---------------------------------------------------------------- future sports (non-live hooks)
FUTURE_SPORTS = {
    "MMA": {"sport": "MIXED_MARTIAL_ARTS", "leagues": ["UFC"], "live": False,
            "markets": ["MONEY", "TOTAL", "GO_THE_DISTANCE", "VICTORY_BY_KO_KTO_OR_DQ"]},
    "SOCCER": {"sport": "SOCCER", "leagues": ["EPL", "MLS", "La Liga", "Serie A", "Bundesliga", "Ligue 1", "Champions League"],
               "live": False, "markets": ["1X2", "MONEYLINE_3_WAY_WIN", "MONEYLINE_3_WAY_DRAW", "SPREAD", "TOTAL"]},
}
def future_sport_hook(name: str) -> dict:
    """Stub: flip FUTURE_SPORTS[name]['live']=True and the server will query these leagues with the same code path."""
    cfg = FUTURE_SPORTS[name.upper()]
    return {"sport": name.upper(), "enabled": cfg["live"], "leagues": cfg["leagues"], "markets": cfg["markets"], "events": []}
