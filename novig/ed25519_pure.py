"""Pure-python Ed25519 signing (RFC 8032) + minimal PKCS#8 PEM parsing.
Fallback so the app runs on a plain Windows python3 without the `cryptography` package. ~1-2 ms per signature."""
import base64, hashlib
p = 2**255 - 19; L = 2**252 + 27742317777372353535851937790883648493
d = -121665 * pow(121666, p - 2, p) % p; I = pow(2, (p - 1) // 4, p)
def _inv(x): return pow(x, p - 2, p)
def _xrecover(y):
    xx = (y * y - 1) * _inv(d * y * y + 1); x = pow(xx, (p + 3) // 8, p)
    if (x * x - xx) % p: x = x * I % p
    return p - x if x % 2 else x
By = 4 * _inv(5) % p; B = (_xrecover(By), By, 1, _xrecover(By) * By % p)
def _add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % p; Bv = (P[1] + P[0]) * (Q[1] + Q[0]) % p
    C = 2 * P[3] * Q[3] * d % p; D = 2 * P[2] * Q[2] % p; E, F, G, H = Bv - A, D - C, D + C, Bv + A
    return (E * F % p, G * H % p, F * G % p, E * H % p)
def _mul(s, P):
    Q = (0, 1, 1, 0)
    while s:
        if s & 1: Q = _add(Q, P)
        P = _add(P, P); s >>= 1
    return Q
def _enc(P):
    zi = _inv(P[2]); x = P[0] * zi % p; y = P[1] * zi % p
    return (y | ((x & 1) << 255)).to_bytes(32, "little")
class PureEd25519Key:
    def __init__(self, seed: bytes):
        h = hashlib.sha512(seed).digest(); a = int.from_bytes(h[:32], "little")
        a &= (1 << 254) - 8; a |= 1 << 254
        self.a, self.prefix = a, h[32:]; self.pub = _enc(_mul(a, B))
    def sign(self, msg: bytes) -> bytes:
        r = int.from_bytes(hashlib.sha512(self.prefix + msg).digest(), "little") % L
        R = _enc(_mul(r, B)); k = int.from_bytes(hashlib.sha512(R + self.pub + msg).digest(), "little") % L
        return R + ((r + k * self.a) % L).to_bytes(32, "little")
def load(secret: str) -> "PureEd25519Key":
    """PEM PKCS#8 Ed25519, base64 DER, or hex/base64 32/64-byte seed."""
    s = secret.strip()
    if "BEGIN" in s:
        s = "".join(l for l in s.splitlines() if l and "-----" not in l)
        raw = base64.b64decode(s)
    else:
        try: raw = bytes.fromhex(s)
        except ValueError: raw = base64.b64decode(s)
    if len(raw) == 48 and raw[9:12] == bytes([0x2b, 0x65, 0x70]): raw = raw[16:]   # PKCS#8 Ed25519 OID 1.3.101.112
    elif len(raw) == 64: raw = raw[:32]
    if len(raw) != 32: raise ValueError("not an Ed25519 key (P-256 keys need the `cryptography` package)")
    return PureEd25519Key(raw)
