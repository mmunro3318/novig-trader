"""Hand-drawn-style SVG art generator. Every shape is jittered + double-stroked so it reads as a felt-tip sketch.
Colors: ink #17171A, red #E10600 (streak), orange #FF6A13, yellow #FFC21A, paper #F4F2EC.  Run: python3 tools/gen_assets.py"""
import math, os, random
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "assets")
INK, RED, ORG, YEL, PAPER = "#17171A", "#E10600", "#FF6A13", "#FFC21A", "#F4F2EC"
def wob(pts, amp=0.6, seg=6, closed=False, seed=0):
    r = random.Random(seed); out = []
    P = pts + ([pts[0]] if closed else [])
    for (x1, y1), (x2, y2) in zip(P, P[1:]):
        n = max(1, int(math.hypot(x2 - x1, y2 - y1) / seg))
        for i in range(n):
            t = i / n; out.append((x1 + (x2 - x1) * t + r.uniform(-amp, amp), y1 + (y2 - y1) * t + r.uniform(-amp, amp)))
    out.append((P[-1][0] + r.uniform(-amp, amp), P[-1][1] + r.uniform(-amp, amp)))
    d = f"M{out[0][0]:.1f},{out[0][1]:.1f} " + " ".join(f"L{x:.1f},{y:.1f}" for x, y in out[1:])
    return d
def ell(cx, cy, rx, ry, n=28, rot=0):
    a = math.radians(rot); return [(cx + rx * math.cos(t) * math.cos(a) - ry * math.sin(t) * math.sin(a), cy + rx * math.cos(t) * math.sin(a) + ry * math.sin(t) * math.cos(a)) for t in [2 * math.pi * i / n for i in range(n)]]
def stroke(pts, closed=False, w=2.2, col=INK, seed=1, double=True):
    s = f'<path d="{wob(pts, closed=closed, seed=seed)}" fill="none" stroke="{col}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>'
    if double: s += f'<path d="{wob(pts, amp=0.9, closed=closed, seed=seed + 50)}" fill="none" stroke="{col}" stroke-width="{w*0.45:.2f}" stroke-linecap="round" opacity=".55"/>'
    return s
def fill(pts, col, dx=1.5, dy=1.5, seed=3):
    return f'<path d="{wob([(x + dx, y + dy) for x, y in pts], amp=0.5, closed=True, seed=seed)} Z" fill="{col}"/>'
def ball(cx, cy, rx=11, ry=6.5, rot=-25, col=ORG, laces=True, seed=4):
    pts = ell(cx, cy, rx, ry, rot=rot); s = fill(pts, col, seed=seed) + stroke(pts, True, seed=seed)
    if laces:
        a = math.radians(rot); ux, uy = math.cos(a), math.sin(a); vx, vy = -uy, ux
        s += stroke([(cx - ux * 5, cy - uy * 5), (cx + ux * 5, cy + uy * 5)], w=1.6, seed=seed + 1, double=False)
        for k in (-3, 0, 3): s += stroke([(cx + ux * k - vx * 1.8, cy + uy * k - vy * 1.8), (cx + ux * k + vx * 1.8, cy + uy * k + vy * 1.8)], w=1.4, seed=seed + 2 + k, double=False)
    return s
def svg(body, vb=48, w=None):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb} {vb}" width="{w or vb}" height="{w or vb}">{body}</svg>'
def face(cx, cy, mood="happy", s=1.0):
    e = lambda x: f'<circle cx="{cx + x*s:.1f}" cy="{cy - 2*s:.1f}" r="{1.4*s:.1f}" fill="{INK}"/>'
    if mood == "sleep": eyes = stroke([(cx - 6*s, cy - 2*s), (cx - 3*s, cy - 1*s)], w=1.6, double=False) + stroke([(cx + 3*s, cy - 1*s), (cx + 6*s, cy - 2*s)], w=1.6, double=False)
    else: eyes = e(-4.5) + e(4.5)
    mouth = {"happy": [(cx - 3*s, cy + 2*s), (cx, cy + 4*s), (cx + 3*s, cy + 2*s)], "sleep": [(cx - 1.5*s, cy + 3*s), (cx + 1.5*s, cy + 3*s)],
             "meh": [(cx - 3*s, cy + 3*s), (cx + 3*s, cy + 3*s)], "wow": ell(cx, cy + 3*s, 1.6*s, 2*s, 10)}[mood]
    return eyes + stroke(mouth, mood == "wow", w=1.6, double=False)
I = {}
I["td"] = stroke([(14, 44), (14, 22)], seed=1) + stroke([(6, 22), (34, 22)], seed=2) + stroke([(6, 22), (6, 6)], seed=3) + stroke([(34, 22), (34, 6)], seed=4) + ball(32, 32, 9, 5.5, -35, seed=6) + stroke([(40, 8), (44, 4)], col=RED, w=2, double=False) + stroke([(42, 13), (47, 12)], col=RED, w=2, double=False)
I["int"] = fill([(8, 30), (20, 22), (28, 26), (26, 40), (10, 42)], YEL, seed=7) + stroke([(8, 30), (20, 22), (28, 26), (26, 40), (10, 42)], True, seed=8) + stroke([(20, 22), (16, 14)], w=1.8, seed=9) + stroke([(24, 24), (22, 14)], w=1.8, seed=10) + stroke([(28, 26), (28, 17)], w=1.8, seed=11) + ball(34, 14, 9, 5.5, -20, seed=12) + stroke([(42, 30), (46, 34)], col=RED, w=2, double=False)
I["fumble"] = ball(26, 26, 11, 6.5, 30, seed=13) + stroke([(6, 12), (12, 16)], w=1.8, double=False) + stroke([(4, 22), (11, 23)], w=1.8, double=False) + stroke([(8, 32), (13, 29)], w=1.8, double=False) + stroke([(34, 40), (38, 44)], col=RED, w=2, double=False) + stroke([(40, 36), (45, 38)], col=RED, w=2, double=False)
star = [(24 + (14 if i % 2 == 0 else 6) * math.cos(math.pi * i / 6), 24 + (14 if i % 2 == 0 else 6) * math.sin(math.pi * i / 6)) for i in range(12)]
I["sack"] = fill(star, YEL, seed=14) + stroke(star, True, seed=15) + stroke([(18, 22), (30, 28)], w=2.4, seed=16) + stroke([(30, 22), (18, 28)], w=2.4, seed=17)
I["injury"] = fill([(17, 6), (31, 6), (31, 17), (42, 17), (42, 31), (31, 31), (31, 42), (17, 42), (17, 31), (6, 31), (6, 17), (17, 17)], RED, seed=18) + stroke([(17, 6), (31, 6), (31, 17), (42, 17), (42, 31), (31, 31), (31, 42), (17, 42), (17, 31), (6, 31), (6, 17), (17, 17)], True, seed=19)
flag = [(14, 8), (40, 10), (34, 18), (40, 26), (14, 24)]
I["penalty"] = fill(flag, YEL, seed=20) + stroke(flag, True, seed=21) + stroke([(14, 6), (14, 44)], w=2.6, seed=22)
I["challenge"] = fill(flag, RED, seed=23) + stroke(flag, True, seed=24) + stroke([(14, 6), (14, 44)], w=2.6, seed=25) + stroke([(24, 13), (27, 11), (29, 14), (26, 17), (26, 19)], w=1.6, double=False) + '<circle cx="26" cy="22" r="1" fill="#17171A"/>'
circ = ell(24, 24, 17, 17)
I["halftime"] = f'<path d="M24,7 A17,17 0 0,1 24,41 Z" fill="{ORG}" transform="translate(1.5,1.5)"/>' + stroke(circ, True, seed=26) + stroke([(24, 7), (24, 41)], seed=27) + stroke([(24, 24), (31, 18)], w=1.8, seed=28)
I["whistle"] = fill(ell(20, 28, 12, 10), ORG, seed=29) + stroke(ell(20, 28, 12, 10), True, seed=30) + stroke([(28, 20), (44, 14), (44, 22), (31, 25)], seed=31) + '<circle cx="20" cy="28" r="3" fill="#17171A"/>' + stroke([(6, 8), (10, 13)], col=RED, w=2, double=False) + stroke([(14, 4), (15, 11)], col=RED, w=2, double=False)
chk = "".join(f'<rect x="{14 + 7*i}" y="{8 + 6*j}" width="7" height="6" fill="{INK if (i + j) % 2 else PAPER}" opacity=".85"/>' for i in range(4) for j in range(3))
I["final"] = chk + stroke([(14, 8), (42, 8), (42, 26), (14, 26)], True, seed=32) + stroke([(14, 6), (14, 44)], w=2.6, seed=33)
I["fg"] = stroke([(24, 44), (24, 26)], seed=34) + stroke([(10, 26), (38, 26)], seed=35) + stroke([(10, 26), (10, 6)], seed=36) + stroke([(38, 26), (38, 6)], seed=37) + stroke([(4, 44), (12, 30), (22, 14)], w=1.4, col=ORG, double=False) + ball(24, 12, 5, 3, -40, laces=False, seed=38)
I["timeout"] = stroke([(10, 12), (38, 12)], w=3, seed=39) + stroke([(24, 12), (24, 40)], w=3, seed=40) + stroke([(36, 30), (42, 36)], col=ORG, w=2, double=False)
I["turnover"] = stroke([(8, 18), (36, 18)], seed=41) + stroke([(30, 12), (37, 18), (30, 24)], seed=42) + stroke([(40, 32), (12, 32)], col=RED, seed=43) + stroke([(18, 26), (11, 32), (18, 38)], col=RED, seed=44)
I["quarter"] = stroke([(24, 6), (24, 42)], w=2.4, seed=45) + stroke([(18, 42), (30, 42)], w=2, seed=46)
# UI icons
I["games"] = ball(24, 24, 16, 9.5, -30, seed=47)
I["positions"] = stroke([(6, 38), (16, 26), (24, 32), (40, 12)], w=2.6, seed=48) + stroke([(32, 12), (40, 12), (40, 20)], w=2.6, seed=49) + stroke([(6, 44), (42, 44)], w=1.6, seed=50)
book = [(10, 6), (36, 6), (36, 42), (10, 42)]
I["journal"] = fill(book, YEL, seed=51) + stroke(book, True, seed=52) + stroke([(15, 6), (15, 42)], w=1.6, seed=53) + stroke([(20, 16), (31, 16)], w=1.6, double=False) + stroke([(20, 22), (29, 22)], w=1.6, double=False) + stroke([(40, 10), (44, 14), (30, 34), (26, 35), (27, 31), (40, 10)], w=1.8, col=RED, seed=54)
I["account"] = fill(ell(24, 17, 8, 8), ORG, seed=55) + stroke(ell(24, 17, 8, 8), True, seed=56) + stroke([(8, 42), (12, 32), (24, 28), (36, 32), (40, 42)], seed=57)
gear = [(24 + (15 if (i // 2) % 2 == 0 else 11) * math.cos(math.pi * i / 8), 24 + (15 if (i // 2) % 2 == 0 else 11) * math.sin(math.pi * i / 8)) for i in range(16)]
I["settings"] = stroke(gear, True, seed=58) + fill(ell(24, 24, 5, 5), YEL, seed=59) + stroke(ell(24, 24, 5, 5), True, seed=60)
I["search"] = stroke(ell(20, 20, 12, 12), True, w=2.6, seed=61) + stroke([(29, 29), (42, 42)], w=3.2, seed=62)
I["system"] = "".join(fill([(x, y), (x + 14, y), (x + 14, y + 14), (x, y + 14)], c, seed=63 + k) + stroke([(x, y), (x + 14, y), (x + 14, y + 14), (x, y + 14)], True, seed=70 + k) for k, (x, y, c) in enumerate([(8, 8, RED), (26, 8, ORG), (8, 26, YEL), (26, 26, PAPER)]))
I["bolt"] = fill([(26, 4), (10, 26), (22, 26), (18, 44), (38, 18), (26, 18)], YEL, seed=80) + stroke([(26, 4), (10, 26), (22, 26), (18, 44), (38, 18), (26, 18)], True, seed=81)
I["mma"] = fill(ell(24, 22, 14, 12), RED, seed=82) + stroke(ell(24, 22, 14, 12), True, seed=83) + stroke([(14, 32), (14, 42), (34, 42), (34, 32)], seed=84) + stroke([(16, 18), (30, 18)], w=1.6, double=False)
soc = ell(24, 24, 17, 17); pent = [(24 + 6 * math.cos(math.pi * (2 * i / 5 - .5)), 24 + 6 * math.sin(math.pi * (2 * i / 5 - .5))) for i in range(5)]
I["soccer"] = stroke(soc, True, seed=85) + fill(pent, INK, 0, 0, seed=86) + "".join(stroke([pent[i], (24 + 16 * math.cos(math.pi * (2 * i / 5 - .5)), 24 + 16 * math.sin(math.pi * (2 * i / 5 - .5)))], w=1.6, double=False, seed=87 + i) for i in range(5))
for k, v in I.items(): open(os.path.join(OUT, f"ic-{k}.svg"), "w").write(svg(v))
# logo: sketch football + red streak + wordmark
logo = ball(22, 24, 15, 9, -25, seed=90) + f'<path d="{wob([(42, 27), (70, 27)], amp=.4, seed=91)}" stroke="{RED}" stroke-width="5" stroke-linecap="round" fill="none"/>' \
       f'<text x="76" y="33" font-family="Helvetica Neue,Arial,sans-serif" font-weight="800" font-size="22" letter-spacing="-1" fill="{INK}">novig</text>' \
       f'<text x="140" y="33" font-family="Helvetica Neue,Arial,sans-serif" font-weight="400" font-size="22" letter-spacing="-1" fill="{RED}">/clean</text>'
open(os.path.join(OUT, "logo.svg"), "w").write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 210 48" width="210" height="48">{logo}</svg>')
open(os.path.join(OUT, "logo-mark.svg"), "w").write(svg(ball(24, 24, 17, 10, -25, seed=90) + f'<path d="{wob([(6, 42), (42, 42)], amp=.4, seed=91)}" stroke="{RED}" stroke-width="4" stroke-linecap="round"/>'))
# mascot "Pip" — empty states, 160x160
def pip(mood, extra="", col=ORG, seed=100):
    b = ell(80, 84, 46, 30, 40, rot=-15)
    s = f'<ellipse cx="82" cy="142" rx="40" ry="5" fill="{INK}" opacity=".08"/>' + fill(b, col, 3, 3, seed=seed) + stroke(b, True, w=3, seed=seed + 1)
    s += stroke([(44, 70), (116, 98)], w=1.6, seed=seed + 2, double=False) if False else ""
    s += stroke([(52, 112), (46, 132)], w=3, seed=seed + 3) + stroke([(104, 114), (112, 132)], w=3, seed=seed + 4)  # legs
    s += stroke([(40, 132), (52, 132)], w=3, seed=seed + 5) + stroke([(106, 132), (118, 132)], w=3, seed=seed + 6)
    s += f'<g transform="translate(0,0)">{face(80, 82, mood, 2.2)}</g>' + extra
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160" width="160" height="160">{s}</svg>'
zz = '<text x="118" y="44" font-family="Helvetica Neue,Arial" font-weight="700" font-size="22" fill="#17171A">z</text><text x="134" y="28" font-family="Helvetica Neue,Arial" font-weight="700" font-size="15" fill="#17171A">z</text>'
arms_shrug = stroke([(36, 84), (22, 70), (16, 56)], w=3, seed=120) + stroke([(124, 84), (138, 70), (144, 56)], w=3, seed=121) + stroke([(10, 50), (22, 50)], col=RED, w=2.4, double=False) + stroke([(138, 50), (150, 50)], col=RED, w=2.4, double=False)
pen = stroke([(124, 96), (146, 70)], w=4, col=RED, seed=122) + stroke([(36, 92), (20, 104)], w=3, seed=123) + fill([(108, 118), (150, 118), (150, 146), (108, 146)], YEL, 0, 0, seed=124) + stroke([(108, 118), (150, 118), (150, 146), (108, 146)], True, seed=125) + stroke([(114, 128), (142, 128)], w=1.4, double=False) + stroke([(114, 136), (136, 136)], w=1.4, double=False)
cheer = stroke([(36, 80), (18, 50)], w=3, seed=126) + stroke([(124, 80), (142, 50)], w=3, seed=127) + stroke([(12, 42), (18, 34)], col=RED, w=2.4, double=False) + stroke([(146, 42), (152, 34)], col=RED, w=2.4, double=False)
helmet = stroke([(36, 84), (16, 96)], w=3, seed=128) + stroke([(124, 84), (140, 96)], w=3, seed=129) + f'<g transform="translate(118,96) scale(.75)">{I["mma"]}</g>'
kick = stroke([(36, 84), (16, 96)], w=3, seed=130) + stroke([(124, 84), (140, 96)], w=3, seed=131) + f'<g transform="translate(118,104) scale(.8)">{I["soccer"]}</g>'
wire = stroke([(10, 30), (30, 20), (50, 34), (70, 18)], col=RED, w=2.4, seed=132) + stroke([(66, 12), (74, 24)], col=RED, w=2.4, double=False) + stroke([(74, 12), (66, 24)], col=RED, w=2.4, double=False)
for name, m, ex, col in [("sleep", "sleep", zz, ORG), ("shrug", "meh", arms_shrug, ORG), ("write", "happy", pen, ORG), ("cheer", "happy", cheer, YEL),
                         ("mma", "wow", helmet, ORG), ("soccer", "happy", kick, YEL), ("offline", "wow", wire, "#D9D6CE")]:
    open(os.path.join(OUT, f"pip-{name}.svg"), "w").write(pip(m, ex, col))
print(len(I), "icons +", "logo, logo-mark, 7 mascots ->", OUT)
