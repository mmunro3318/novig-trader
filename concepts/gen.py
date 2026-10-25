import math,random
random.seed(7)
# realistic: Bengals @ Ravens, Q3, Ravens YES price path after a CIN pick-six swing
P=[0.64,0.65,0.63,0.66,0.67,0.66,0.62,0.48,0.41,0.39,0.43,0.45,0.44,0.47,0.52,0.50,0.55,0.57,0.56,0.58]
G=dict(away="CIN",home="BAL",an="Bengals",hn="Ravens",as_=17,hs=20,clk="Q3 · 6:42",px=0.58,vol="$184,230")
BOOK=[(0.61,410),(0.60,1250),(0.59,880),(0.58,None),(0.57,960),(0.56,2210),(0.55,640)]
POS=dict(side="BAL YES",qty=86,avg=0.41,mark=0.58)
pnl=POS['qty']*(POS['mark']-POS['avg'])
def path(w,h,pad=4):
  lo,hi=min(P)-.02,max(P)+.02
  return " ".join(f"{'M' if i==0 else 'L'}{pad+i*(w-2*pad)/(len(P)-1):.1f},{pad+(hi-v)/(hi-lo)*(h-2*pad):.1f}" for i,v in enumerate(P))
def bars(w,h):
  lo,hi=min(P)-.02,max(P)+.02;n=len(P);bw=(w)/n;o=""
  for i in range(1,n):
    a,b=P[i-1],P[i];y1=(hi-max(a,b))/(hi-lo)*h;y2=(hi-min(a,b))/(hi-lo)*h
    o+=f'<rect x="{i*bw:.1f}" y="{y1:.1f}" width="{bw*.6:.1f}" height="{max(2,y2-y1):.1f}" class="{"up" if b>=a else "dn"}"/>'
  return o
def ladder(fmt):
  return "".join(fmt(p,q) for p,q in BOOK)
C={}
# 1 Terminal
C['01-terminal']=("Bloomberg Terminal","Density over decoration: amber-on-black, monospace, keyboard-first, every pixel is data.",f"""
<style>body{{background:#000;color:#ffb000;font:13px 'IBM Plex Mono',Menlo,monospace;margin:0;padding:14px}}
.g{{display:grid;grid-template-columns:2fr 1fr 1fr;gap:8px}}.p{{border:1px solid #333;padding:8px}}h2{{background:#ffb000;color:#000;margin:-8px -8px 8px;padding:2px 8px;font-size:12px}}
.w{{color:#fff}}.gr{{color:#3f3}}.rd{{color:#f44}}.c{{color:#0cf}}table{{width:100%;border-collapse:collapse}}td{{padding:2px 4px}}
.k{{background:#222;color:#fff;padding:0 4px}}.cmd{{border-top:1px solid #333;margin-top:8px;padding-top:6px}}svg path{{stroke:#ffb000;fill:none;stroke-width:1.5}}
.up{{fill:#3f3}}.dn{{fill:#f44}}</style>
<div class=p style="margin-bottom:8px"><span class=c>NOVIG&lt;GO&gt;</span> NFL WK8 · <span class=w>CIN 17 @ BAL 20</span> {G['clk']} · BAL YES <span class=gr>0.58 ▲+0.17</span> · VOL {G['vol']} · BAL <span class=w>$1,000.00</span> · <span class=rd>LIVE</span></div>
<div class=g><div class=p><h2>1) PRICE BAL YES · TICK</h2><svg width=600 height=230>{bars(600,230)}</svg>
<div>EVT 7:58 <span class=rd>CIN PICK-6</span> 0.66→0.41 · EVT 4:10 <span class=gr>BAL TD</span> 0.45→0.55</div></div>
<div class=p><h2>2) BOOK</h2><table>{ladder(lambda p,q: f'<tr><td class={"rd" if p>0.58 else "gr"}>{p:.2f}</td><td class=w align=right>{q}</td></tr>' if q else '<tr><td colspan=2 class=c>── 0.58 LAST ──</td></tr>')}</table></div>
<div class=p><h2>3) TICKET</h2>SIDE <span class=k>BAL YES</span><br>PX&nbsp;&nbsp; <span class=k>0.58</span><br>QTY&nbsp; <span class=k>50</span><br>COST <span class=w>$29.00</span><br>WIN&nbsp; <span class=gr>$50.00</span><br><br><span class=k>F9</span> BUY <span class=k>F10</span> SELL<h2 style="margin-top:14px">4) POS</h2>BAL YES 86 @0.41<br>MARK 0.58 <span class=gr>+${pnl:.2f}</span></div></div>
<div class=cmd>&gt; BUY BAL Y 50 @.58 <span class=w>▌</span> &nbsp; <span class=k>F1</span>HELP <span class=k>F2</span>GAMES <span class=k>F8</span>TRAIL</div>""")
# 2 Glass
C['02-glass']=("Aurora Glass","Calm premium consumer fintech: frosted panels floating over a soft gradient, big numbers, generous space.",f"""
<style>body{{margin:0;height:800px;font-family:Inter,system-ui,sans-serif;color:#fff;background:radial-gradient(circle at 20% 20%,#7b5cff,transparent 40%),radial-gradient(circle at 80% 70%,#00d4c8,transparent 40%),#0b0d24;display:grid;grid-template-columns:1.4fr 1fr;gap:24px;padding:48px;box-sizing:border-box}}
.c{{background:rgba(255,255,255,.08);backdrop-filter:blur(24px);border:1px solid rgba(255,255,255,.18);border-radius:28px;padding:28px}}.m{{opacity:.6;font-size:14px}}.big{{font-size:64px;font-weight:700;letter-spacing:-2px}}
svg path{{stroke:url(#g);stroke-width:4;fill:none;stroke-linecap:round}}.pill{{display:inline-block;padding:8px 16px;border-radius:99px;background:rgba(255,255,255,.12);margin-right:8px}}
.btn{{display:block;text-align:center;padding:18px;border-radius:18px;background:linear-gradient(90deg,#7b5cff,#00d4c8);font-weight:600;font-size:18px;margin-top:18px}}</style>
<div class=c style="grid-row:span 2"><div class=m>NFL · LIVE · {G['clk']}</div><div style="display:flex;justify-content:space-between;font-size:28px;margin:12px 0"><span>🐯 Bengals <b>17</b></span><span><b>20</b> Ravens 🐦‍⬛</span></div>
<div class=m>Ravens to win</div><div class=big>58¢ <span style="font-size:22px;color:#7fffd4">+17¢</span></div>
<svg width=620 height=260><defs><linearGradient id=g><stop stop-color=#b9a8ff /><stop offset=1 stop-color=#5ff /></linearGradient></defs><path d="{path(620,260)}"/></svg>
<span class=pill>1H</span><span class=pill style="background:#fff;color:#111">Game</span><span class=pill>Vol {G['vol']}</span></div>
<div class=c><div class=m>Quick buy · Ravens YES</div><div class=big style="font-size:44px">$29.00</div><div class=m>50 shares · pays $50.00 if Ravens win</div><a class=btn>Swipe to buy</a></div>
<div class=c><div class=m>Your position</div><div style="font-size:30px;font-weight:600;margin:8px 0">86 × Ravens YES</div><div class=m>avg 41¢ → 58¢</div><div style="font-size:36px;color:#7fffd4;font-weight:700">+${pnl:.2f}</div></div>""")
# 3 Brutalist
C['03-brutalist']=("Neo-Brutalist","Loud, honest, tactile: thick black borders, hard offset shadows, flat primaries, giant type. Feels like a fanzine trading desk.",f"""
<style>body{{margin:0;padding:32px;background:#fffbe6;font-family:'Arial Black',Arial,sans-serif;color:#000;display:grid;grid-template-columns:1.3fr 1fr;gap:24px}}
.b{{border:4px solid #000;box-shadow:8px 8px 0 #000;padding:20px;background:#fff}}h1{{font-size:88px;margin:0;line-height:.9}}.tag{{background:#000;color:#ff0;padding:4px 10px;font-size:14px}}
.y{{background:#ffe600}}.p{{background:#ff6bd6}}.g{{background:#4dff88}}svg path{{stroke:#000;stroke-width:6;fill:none}}.btn{{border:4px solid #000;box-shadow:5px 5px 0 #000;padding:16px;font-size:26px;text-align:center;margin-top:10px}}
table{{width:100%;border-collapse:collapse;font-size:22px}}td{{border-bottom:3px solid #000;padding:4px 8px}}</style>
<div class="b y" style="grid-row:span 2"><span class=tag>● LIVE {G['clk']}</span><h1>CIN 17<br>BAL 20</h1><div style="font-size:30px;margin:10px 0">RAVENS WIN? <span style="background:#000;color:#fff;padding:0 10px">58¢</span></div>
<svg width=560 height=250 style="background:#fff;border:4px solid #000"><path d="{path(560,250,12)}"/></svg><div style="font-size:18px;margin-top:8px">▼ PICK-SIX PANIC → 41¢. ▲ CRAWLED BACK.</div></div>
<div class="b p"><div class=tag>BOOK</div><table>{ladder(lambda p,q: f'<tr><td>{int(p*100)}¢</td><td align=right>{q}</td></tr>' if q else '<tr style="background:#000;color:#fff"><td colspan=2>58¢ ← LAST</td></tr>')}</table></div>
<div class="b g"><div class=tag>YOU</div><div style="font-size:32px">86 BAL @ 41¢</div><div style="font-size:54px">+${pnl:.0f}</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:12px"><div class="btn y">BUY</div><div class="btn" style="background:#fff">SELL</div></div></div>""")
# 4 Win95
C['04-win95']=("Windows 95 Desktop","Nostalgic neo-retro OS: each widget is a draggable window, bevels and system fonts. Your Soul Reaver era, made playful.",f"""
<style>body{{margin:0;height:800px;background:#008080;font:12px 'MS Sans Serif',Tahoma,sans-serif;position:relative}}
.w{{position:absolute;background:#c0c0c0;border:2px solid;border-color:#fff #000 #000 #fff;box-shadow:1px 1px 0 #808080 inset}}.t{{background:linear-gradient(90deg,#000080,#1084d0);color:#fff;font-weight:bold;padding:3px 4px;display:flex;justify-content:space-between}}
.x{{background:#c0c0c0;color:#000;border:1px solid;border-color:#fff #000 #000 #fff;padding:0 4px}}.in{{background:#fff;border:2px solid;border-color:#808080 #fff #fff #808080;margin:6px;padding:6px}}
.bt{{border:2px solid;border-color:#fff #000 #000 #fff;padding:4px 18px;display:inline-block;margin:4px}}svg path{{stroke:#000080;stroke-width:2;fill:none}}.bar{{position:absolute;bottom:0;left:0;right:0;height:30px;background:#c0c0c0;border-top:2px solid #fff;display:flex;align-items:center;gap:6px;padding:0 4px}}
td{{padding:1px 8px}}</style>
<div class=w style="left:30px;top:30px;width:640px"><div class=t>📈 Ravens.exe — CIN 17 @ BAL 20 ({G['clk']})<span><span class=x>_</span> <span class=x>×</span></span></div><div class=in><svg width=610 height=280 style="background:#fff">{''.join(f'<line x1=0 x2=610 y1={y} y2={y} stroke=#ddd />' for y in range(0,280,35))}<path d="{path(610,280)}"/></svg></div><div style="padding:0 8px 6px">Last: 58¢ &nbsp; Vol: {G['vol']}</div></div>
<div class=w style="left:700px;top:40px;width:250px"><div class=t>Order Book<span class=x>×</span></div><div class=in><table>{ladder(lambda p,q: f'<tr style="color:{"#a00" if p>.58 else "#060"}"><td>{p:.2f}</td><td>{q}</td></tr>' if q else '<tr style="background:#000080;color:#fff"><td colspan=2>0.58 last</td></tr>')}</table></div></div>
<div class=w style="left:980px;top:60px;width:270px"><div class=t>Quick Bet Wizard<span class=x>×</span></div><div style="padding:10px">Side: <select><option>Ravens YES</option></select><br><br>Qty: <input value=50 size=6> @ <input value=0.58 size=5><br><br>Cost $29.00 · Pays $50.00<br><br><span class=bt><u>B</u>uy</span><span class=bt>Cancel</span></div></div>
<div class=w style="left:720px;top:360px;width:380px"><div class=t>⚠ My Position<span class=x>×</span></div><div style="padding:14px;display:flex;gap:12px">💰<div>86 × Ravens YES @ 0.41<br>Mark 0.58<br><b style="color:#060">Unrealized: +${pnl:.2f}</b></div></div><div style="text-align:center"><span class=bt>Trail Stop...</span><span class=bt>OK</span></div></div>
<div class=bar><span class=bt style="font-weight:bold;margin:0">🪟 Start</span><span class=bt style="margin:0">Ravens.exe</span><span class=bt style="margin:0">Order Book</span><span style="margin-left:auto" class=in>Bal $1,000.00 · 3:14 PM</span></div>""")
# 5 Swiss editorial
C['05-swiss']=("Swiss Editorial","International Typographic Style: strict grid, one red accent, the game told like a newspaper front page.",f"""
<style>body{{margin:0;padding:48px 56px;background:#f4f1ea;color:#111;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;display:grid;grid-template-columns:repeat(12,1fr);gap:0 24px}}
.r{{color:#e10600}}hr{{grid-column:1/-1;border:0;border-top:2px solid #111;margin:10px 0}}.s{{font-size:11px;letter-spacing:2px;text-transform:uppercase}}
h1{{grid-column:1/9;font-size:110px;letter-spacing:-5px;line-height:.85;margin:0;font-weight:700}}svg path{{stroke:#111;stroke-width:2;fill:none}}</style>
<div class=s style="grid-column:1/7">Novig — NFL Week 8 — Live</div><div class=s style="grid-column:7/13;text-align:right">{G['clk']} · Vol {G['vol']}</div><hr>
<h1>Ravens<br>20<span class=r>—</span>17</h1><div style="grid-column:9/13;font-size:17px;line-height:1.45">A pick-six in the third sent Baltimore from <b>66</b> to <b class=r>41</b>. The market panicked; the drive that followed did not. Now trading at <b>58</b>.</div><hr>
<div style="grid-column:1/8"><div class=s>Ravens YES · price path</div><svg width=640 height=230><path d="{path(640,230)}"/><circle cx=210 cy=200 r=6 fill=#e10600 /></svg></div>
<div style="grid-column:8/10"><div class=s>Book</div>{ladder(lambda p,q: f'<div style="display:flex;justify-content:space-between;border-bottom:1px solid #bbb;padding:3px 0"><span>{int(p*100)}</span><span>{q}</span></div>' if q else '<div class=r style="font-weight:700;padding:3px 0">58 Last</div>')}</div>
<div style="grid-column:10/13"><div class=s>Position</div><div style="font-size:44px;font-weight:700">+{pnl:.2f}</div><div>86 shares at 41</div><div class=s style="margin-top:24px">Order</div><div style="border:2px solid #111;padding:10px;margin-top:6px">Buy 50 at 58 — $29.00</div><div style="background:#e10600;color:#fff;padding:12px;margin-top:6px;font-weight:700">Place order →</div></div>""")
# 6 HUD
C['06-hud']=("Sci-Fi HUD","Tactical heads-up display: cyan wireframes, corner brackets, scanlines, radial gauges. The game as a mission.",f"""
<style>body{{margin:0;height:800px;background:radial-gradient(#06202a,#010508);color:#5ef2ff;font-family:'Orbitron','Rajdhani',monospace;padding:30px;box-sizing:border-box;display:grid;grid-template-columns:1.5fr 1fr;gap:24px;
background-image:repeating-linear-gradient(0deg,rgba(94,242,255,.04) 0 1px,transparent 1px 3px)}}.f{{position:relative;padding:20px;border:1px solid rgba(94,242,255,.25);clip-path:polygon(16px 0,100% 0,100% calc(100% - 16px),calc(100% - 16px) 100%,0 100%,0 16px)}}
.l{{font-size:11px;letter-spacing:3px;opacity:.7}}.o{{color:#ff9d2e}}svg .ln{{stroke:#5ef2ff;stroke-width:2;fill:none;filter:drop-shadow(0 0 6px #5ef2ff)}}.btn{{border:1px solid #5ef2ff;padding:12px;text-align:center;letter-spacing:4px;margin-top:10px;background:rgba(94,242,255,.1)}}</style>
<div class=f style="grid-row:span 2"><div class=l>TARGET // BAL RAVENS // WIN PROB</div><div style="font-size:46px">CIN 17 <span class=o>⟡</span> BAL 20 <span style="font-size:16px" class=o>{G['clk']}</span></div>
<svg width=640 height=300>{''.join(f'<line x1={x} y1=0 x2={x} y2=300 stroke="rgba(94,242,255,.08)"/>' for x in range(0,640,40))}<path class=ln d="{path(640,300)}"/><line x1=0 x2=640 y1=228 y2=228 stroke=#ff9d2e stroke-dasharray=4 /><text x=6 y=222 fill=#ff9d2e font-size=11>ENTRY 0.41</text></svg>
<div class=l>ANOMALY DETECTED Q3 07:58 · OVERREACTION −25¢ · REVERSION 68%</div></div>
<div class=f style="text-align:center"><div class=l>MARKET PRICE</div><svg width=200 height=200><circle cx=100 cy=100 r=80 stroke="rgba(94,242,255,.15)" stroke-width=10 fill=none /><circle cx=100 cy=100 r=80 stroke=#5ef2ff stroke-width=10 fill=none stroke-dasharray="{2*math.pi*80*.58:.0f} 999" transform="rotate(-90 100 100)"/><text x=100 y=112 text-anchor=middle fill=#5ef2ff font-size=40>58</text></svg><div class=l>VOL {G['vol']}</div></div>
<div class=f><div class=l>POSITION LOCK</div><div style="font-size:26px">86 × BAL YES @ .41</div><div class=o style="font-size:34px">+${pnl:.2f}</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><div class=btn>ENGAGE +50</div><div class=btn style="border-color:#ff9d2e;color:#ff9d2e">EJECT</div></div></div>""")
# 7 e-ink
C['07-eink']=("E-Ink Calm","Paper-quiet, grayscale, serif: designed to lower heart rate mid-swing and make rules louder than noise.",f"""
<style>body{{margin:0;padding:56px 90px;background:#ecebe6;color:#222;font-family:Georgia,'Iowan Old Style',serif;filter:grayscale(1)}}.row{{display:flex;gap:60px}}.s{{font:12px system-ui;color:#777;letter-spacing:1px;text-transform:uppercase}}
svg path{{stroke:#333;stroke-width:1.5;fill:none}}.box{{border:1px solid #999;padding:18px 22px;flex:1}}.rule{{border-left:3px solid #222;padding-left:12px;margin:8px 0;font-style:italic}}</style>
<div class=s>Thursday · NFL · {G['clk']}</div><div style="font-size:52px;margin:10px 0 24px">Bengals 17, Ravens 20</div>
<div class=row><div style="flex:2"><div class=s>Ravens · 58¢</div><svg width=640 height=220><path d="{path(640,220)}"/></svg></div>
<div class=box><div class=s>Your rules say</div><div class=rule>Target hit (+$14.62 &lt; $20). Hold.</div><div class=rule>Trail stop: 52¢.</div><div class=rule>Exposure 3.5% of bankroll — OK.</div></div></div>
<div class=row style="margin-top:30px"><div class=box><div class=s>Position</div><div style="font-size:34px">86 @ 41¢ · <b>+${pnl:.2f}</b></div></div><div class=box><div class=s>Next order</div><div style="font-size:22px">Sell 86 at 60¢ (limit)</div><div style="margin-top:10px;border:1px solid #222;display:inline-block;padding:8px 22px">Confirm</div></div></div>""")
# 8 sportsbook
C['08-sportsbook']=("Neon Sportsbook","DraftKings/Kalshi energy: dark, team colors, chunky tap targets, live pulse — built for thumbs and speed.",f"""
<style>body{{margin:0;height:800px;background:#0e0f13;color:#fff;font-family:'Inter',system-ui,sans-serif;display:flex;gap:28px;padding:40px;box-sizing:border-box;justify-content:center}}
.ph{{width:380px;background:#17181f;border-radius:36px;padding:20px;border:1px solid #2a2b36}}.tm{{display:flex;align-items:center;gap:12px;font-size:20px;font-weight:700;margin:10px 0}}.dot{{width:36px;height:36px;border-radius:50%}}
.odd{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:14px 0}}.o{{background:#23242e;border-radius:14px;padding:14px;text-align:center;font-weight:700;font-size:22px}}.sel{{background:#53d337;color:#000}}
.live{{background:#ff2d55;padding:3px 8px;border-radius:6px;font-size:12px;font-weight:800}}svg path{{stroke:#53d337;stroke-width:3;fill:none}}.cta{{background:#53d337;color:#000;text-align:center;padding:18px;border-radius:16px;font-weight:800;font-size:20px}}
.chip{{display:inline-block;background:#23242e;padding:10px 14px;border-radius:12px;margin:4px 4px 0 0}}</style>
<div class=ph><span class=live>● LIVE</span> <span style="opacity:.6">{G['clk']}</span><div class=tm><div class=dot style="background:#fb4f14"></div>Bengals<span style="margin-left:auto">17</span></div><div class=tm><div class=dot style="background:#241773"></div>Ravens<span style="margin-left:auto">20</span></div>
<svg width=340 height=150><path d="{path(340,150)}"/></svg><div class=odd><div class=o><div style="font-size:12px;opacity:.6">CIN</div>0.42</div><div class="o sel"><div style="font-size:12px">BAL</div>0.58</div></div>
<div style="opacity:.6;font-size:13px">Vol {G['vol']} · 🔥 2.1k trades in 10m</div></div>
<div class=ph><div style="font-weight:800;font-size:22px">Bet slip</div><div style="background:#23242e;border-radius:14px;padding:14px;margin:14px 0">Ravens to win · <b>0.58</b><div style="font-size:42px;font-weight:800;margin-top:8px">$29.00</div><div style="opacity:.6">To pay $50.00</div></div>
<span class=chip>$10</span><span class=chip>$25</span><span class=chip style="background:#53d337;color:#000">$29</span><span class=chip>Max</span>
<div style="background:#23242e;border-radius:14px;padding:14px;margin:18px 0"><div style="opacity:.6;font-size:13px">Open: Ravens 86 @ 0.41</div><div style="font-size:28px;font-weight:800;color:#53d337">+${pnl:.2f}</div><div style="opacity:.6;font-size:13px">Cash out now: ${POS['qty']*0.58:.2f}</div></div><div class=cta>Place bet</div></div>""")
idx=""
for k,(n,ph,body) in C.items():
  open(f"{k}.html","w").write(f"<!doctype html><meta charset=utf-8><title>{n}</title><body>{body}")
  idx+=f'<a href="{k}.html" style="color:#fff;text-decoration:none"><figure style="margin:0"><img src="{k}.png" style="width:100%;border-radius:8px"><figcaption><b>{n}</b><br><span style="opacity:.6">{ph}</span></figcaption></figure></a>'
open("index.html","w").write(f'<!doctype html><meta charset=utf-8><title>Novig UI concepts</title><body style="background:#111;color:#fff;font-family:system-ui;padding:30px"><h1>Novig UI concepts — round 1</h1><p style="opacity:.6">Sample: CIN @ BAL, Q3, Ravens YES 0.58 after a pick-six overreaction. Your position 86 @ 0.41 (sample).</p><div style="display:grid;grid-template-columns:1fr 1fr;gap:28px">{idx}</div>')
