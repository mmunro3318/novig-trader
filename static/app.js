/* novig/clean prototype — vanilla JS SPA, hash routing. Components are pure functions returning HTML strings
   (UI.*), so the design-system sampler (system.html) renders the exact same code with fixture data. */
const $ = (s, el = document) => el.querySelector(s), $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const api = async (p, opt) => { const r = await fetch(p, opt); return r.json(); };
const post = (p, b) => api(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });

/* ---------- settings ---------- */
const DEF = { fmt: "multiplier", stakes: [1, 2, 5, 10], maxStake: 20, gameExposure: 50, dailyStop: 60, kellyFrac: 0.25, trail: 0.03, maxAdds: 2, edgeMin: 0.03 };
const S = Object.assign({}, DEF, JSON.parse(localStorage.getItem("nc.settings") || "{}"));
const save = () => localStorage.setItem("nc.settings", JSON.stringify(S));

/* ---------- price formats (Novig: Multiplier | Percentage | Precise Percentage) ---------- */
const F = {
  one(p, fmt = S.fmt) {
    if (p == null || isNaN(p) || p <= 0) return "—";
    if (fmt === "percentage") return Math.round(p * 100) + "%";
    if (fmt === "precise") return (p * 100).toFixed(1) + "%";
    return (1 / p).toFixed(2) + "×";
  },
  bare(p, fmt = S.fmt) { return F.one(p, fmt).replace("×", ""); },
  pair(a, b, fmt = S.fmt) { return `${F.bare(a, fmt)} : ${F.bare(b, fmt)}`; },
  all(p) { return `${F.one(p, "multiplier")} · ${F.one(p, "precise")}`; },
  usd(v, sign) { if (v == null || isNaN(v)) return "—"; const s = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); return (v < 0 ? "−$" : sign ? "+$" : "$") + s; },
  pv(value, basis) { const d = value - basis; return `<span class="pv">${F.usd(value)}<small class="${d >= 0 ? "gain" : "loss"}">(${d >= 0 ? "+" : "−"}${Math.abs(d).toFixed(2)})</small></span>`; },
  time(ts) { return new Date(ts).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).replace(" ", "").toLowerCase(); },
  day(ts) { return new Date(ts).toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" }); },
  dayKey(ts) { return new Date(ts).toLocaleDateString("en-CA"); },
  ago(ts) { const m = Math.round((Date.now() - ts) / 60000); return m < 60 ? m + "m ago" : m < 1440 ? Math.round(m / 60) + "h ago" : Math.round(m / 1440) + "d ago"; },
};
/* ask to BUY outcome i = 1 − best bid of the other side (Novig books are two-sided bids). */
const book = { bid: o => o?.bid ? +o.bid.price : null, ask(m, i) { const other = m.outcomes[1 - i]; return other?.bid ? +(1 - other.bid.price).toFixed(3) : (m.outcomes[i].last ? +m.outcomes[i].last : null); } };

/* ---------- team marks: hand-drawn-ish monogram roundels ---------- */
const hue = s => [...String(s)].reduce((a, c) => a * 31 + c.charCodeAt(0) >>> 0, 7) % 360;
function mark(abbr, color, size = 22) {
  const c = color && color !== "#888888" ? color : `hsl(${hue(abbr)} 62% 46%)`, t = esc((abbr || "?").slice(0, 4));
  const fs = t.length > 3 ? 7.5 : t.length > 2 ? 9 : 11;
  return `<svg class="mono" width="${size}" height="${size}" viewBox="0 0 32 32"><path d="M16 2.6c7.6.2 13.2 5.6 13.3 13.1.1 7.7-5.6 13.7-13.4 13.6C8.3 29.2 2.7 23.6 2.7 16 2.8 8.4 8.6 2.4 16 2.6z" fill="${c}" stroke="#17171A" stroke-width="1.6"/><text x="16" y="${16 + fs * .36}" text-anchor="middle" font-family="Helvetica Neue,Arial" font-weight="800" font-size="${fs}" fill="#fff">${t}</text></svg>`;
}
const ICON = t => `assets/ic-${t}.svg`;
const EVT = { TD: "td", INT: "int", PICK_SIX: "int", FUMBLE_LOST: "fumble", FUMBLE_REC: "fumble", SACK: "sack", SAFETY: "sack", INJURY: "injury", PENALTY: "penalty", PENALTY_BIG: "penalty", CHALLENGE: "challenge", HALFTIME: "halftime", KICKOFF_GAME: "whistle", END_GAME: "final", FG: "fg", FG_MISS: "fg", TIMEOUT: "timeout", TURNOVER_DOWNS: "turnover", BLOCKED: "turnover", END_QUARTER: "quarter" };

function teamsOf(ev) {
  const p = ev.participants?.competitors || [], hid = ev.participants?.homeCompetitorId;
  const [an, hn] = (ev.description || "Away @ Home").split(" @ ");
  const h = p.find(c => c.competitorId === hid), a = p.find(c => c.competitorId !== hid);
  return { away: { name: an, abbr: a?.symbol || an.slice(0, 3).toUpperCase() }, home: { name: hn, abbr: h?.symbol || hn.slice(0, 3).toUpperCase() } };
}

/* =========================== UI components =========================== */
const UI = {
  badge: (k, txt) => `<span class="badge ${k}">${esc(txt ?? k)}</span>`,
  src: (s, why) => s === "live" ? `<span class="badge src" title="live from API">● live data</span>` : s === "dryrun" ? UI.badge("dry", "dry-run") : `<span class="badge sample" title="${esc(why || "sample data")}">sample</span>`,
  /* the atomic price button */
  px(p, { sub, sel, attrs = "", dir } = {}) {
    if (p == null) return `<div class="px none"><b>—</b><i>${esc(sub || "no book")}</i></div>`;
    return `<button class="px ${sel ? "sel" : ""} ${dir || ""}" ${attrs}><b>${F.bare(p)}</b><i>${esc(sub ?? "")}</i></button>`;
  },
  pxPair(m, ev, i0 = 0) {
    if (!m) return `<div class="pair">${UI.px(null)}${UI.px(null)}</div>`;
    const lab = o => m.marketType === "TOTAL" ? (o.name.startsWith("Over") ? "O " : "U ") + m.strike : m.marketType === "SPREAD" ? o.name.split(" ").pop() : "win";
    return `<div class="pair">${m.outcomes.map((o, i) => UI.px(book.ask(m, i), { sub: lab(o), attrs: `data-slip='${esc(JSON.stringify(slipFrom(ev, m, i)))}'` })).join("")}</div>`;
  },
  gameRow(ev, live) {
    const t = teamsOf(ev), mk = ev.markets || {}, isLive = ev.status === "OPEN_INGAME";
    const sc = live?.[ev.eventId];
    return `<div class="gamerow ${isLive ? "live" : ""}" data-go="#/game/${ev.eventId}">
      <div class="when">${isLive ? `<span class="badge live">live</span><div>${esc(sc?.detail || "")}</div>` : F.time(ev.startsTs)}<div class="muted" style="font-size:10px">${ev.league}</div></div>
      <div class="teams"><div>${mark(t.away.abbr)} ${esc(t.away.name)} ${sc ? `<b class="num" style="margin-left:auto">${sc.away}</b>` : ""}</div><div>${mark(t.home.abbr)} ${esc(t.home.name)} ${sc ? `<b class="num" style="margin-left:auto">${sc.home}</b>` : ""}</div></div>
      <div class="mk">${UI.pxPair(mk.SPREAD, ev)}</div><div class="mk">${UI.pxPair(mk.TOTAL, ev)}</div><div class="mk">${UI.pxPair(mk.MONEY, ev)}</div>
      <div class="muted">›</div></div>`;
  },
  gameHead() { return `<div class="gamerow" style="cursor:default;border-bottom:0;padding:0"><div></div><div></div><div class="colh mk">Spread</div><div class="colh mk">Total</div><div class="colh mk">Winner</div><div></div></div>`; },
  scoreboard(away, home, as, hs, meta = "") {
    return `<div class="score"><div><div class="team">${mark(away.abbr, away.color, 28)} ${esc(away.name)}</div><div class="pts">${as ?? "–"}</div></div><div class="bar"></div>
      <div><div class="team">${mark(home.abbr, home.color, 28)} ${esc(home.name)}</div><div class="pts">${hs ?? "–"}</div></div><div style="margin-left:auto;text-align:right" class="small">${meta}</div></div>`;
  },
  stat(label, v, d, cls = "") { return `<div class="stat"><div class="micro">${esc(label)}</div><div class="v ${cls}">${v}</div>${d ? `<div class="d">${d}</div>` : ""}</div>`; },
  position(p, opts = {}) {
    if (!p) return `<div class="card"><h4>Your position</h4>${UI.empty("shrug", "Flat on this game", "Tap any price to open the slip. Every fill journals itself.", true)}</div>`;
    const be = p.basis / (p.qty / 100);
    return `<div class="card ink"><h4>Your position · ${esc(p.outcome)} ${UI.src(p.source)}</h4>
      <div class="stat"><div class="v">${F.pv(p.value, p.basis)}</div></div>
      <dl class="kv" style="margin:10px 0"><dt>Contracts</dt><dd>${p.qty.toLocaleString()}</dd><dt>Cost basis</dt><dd>${F.usd(p.basis)}</dd><dt>Avg / break-even</dt><dd>${F.one(be)}</dd><dt>Mark</dt><dd>${F.one(p.mark)}</dd><dt>Pays if wins</dt><dd>${F.usd(p.qty / 100)}</dd></dl>
      <div class="chips">${S.stakes.slice(0, 3).map(s => `<button class="btn sm make" data-add="${s}" data-outcome="${esc(p.outcome)}">+$${s}</button>`).join("")}
      <span style="flex:1"></span><button class="btn sm" data-sell="0.5" data-outcome="${esc(p.outcome)}">Sell ½</button><button class="btn sm primary" data-sell="1" data-outcome="${esc(p.outcome)}">Sell all</button></div></div>`;
  },
  rules(checks) {
    return `<div class="rules"><h4>Your rules say</h4><ul style="margin:0;padding-left:16px">${checks.map(c => `<li><span class="${c.ok ? "ok" : "no"}">${c.ok ? "✓" : "✗"}</span> ${c.t}</li>`).join("")}</ul>
      <div class="small" style="margin-top:6px">From <a href="#/settings">rulebook §8</a> · docs/swing-trading-math.md</div></div>`;
  },
  empty(pip, title, body, compact) { return `<div class="empty" ${compact ? 'style="padding:16px"' : ""}><img src="assets/pip-${pip}.svg" ${compact ? 'style="width:90px"' : ""} alt=""><h3>${esc(title)}</h3><p class="small" style="max-width:340px">${body}</p></div>`; },
  ladder(m, bk) {
    if (!m || !bk?.orders) return UI.empty("offline", "No book", "Order book unavailable right now.", true);
    const [A, B] = m.outcomes, agg = arr => { const g = {}; (arr || []).forEach(o => g[o.price] = (g[o.price] || 0) + o.qty); return Object.entries(g).map(([p, q]) => [+p, q]); };
    const bidsA = agg(bk.orders[A.outcomeId]).sort((a, b) => b[0] - a[0]).slice(0, 6), asksA = agg(bk.orders[B.outcomeId]).map(([p, q]) => [+(1 - p).toFixed(3), q]).sort((a, b) => a[0] - b[0]).slice(0, 6);
    const mx = Math.max(1, ...bidsA.map(x => x[1]), ...asksA.map(x => x[1])), w = q => Math.max(4, Math.round(q / mx * 100)) + "%";
    const row = (p, q, side) => `<div class="lv ${side}" data-make='${esc(JSON.stringify({ price: p, side }))}'>${side === "bid" ? `<div class="bar" style="width:${w(q)}"></div><div style="text-align:right;padding-right:8px">${(q / 100).toFixed(0)}</div><div><b>${F.bare(p)}</b></div><div></div>` : `<div></div><div style="text-align:right;padding-right:8px"><b>${F.bare(p)}</b></div><div>${(q / 100).toFixed(0)}</div><div class="bar" style="width:${w(q)}"></div>`}</div>`;
    const spread = asksA[0] && bidsA[0] ? (asksA[0][0] - bidsA[0][0]).toFixed(3) : "—";
    return `<div class="ladder"><div class="micro" style="display:grid;grid-template-columns:1fr 64px 64px 1fr"><span>bids ${esc(A.name)}</span><span style="text-align:right;padding-right:8px">$</span><span></span><span style="text-align:right">asks</span></div>
      ${asksA.slice().reverse().map(([p, q]) => row(p, q, "ask")).join("")}<div class="mid">spread ${spread} · last ${F.one(+A.last)}</div>${bidsA.map(([p, q]) => row(p, q, "bid")).join("")}</div>`;
  },
  /* price line + notches + trade markers (used by game detail AND journal timeline) */
  chart({ series = [], notches = [], markers = [], bands = [], be = null, w = 900, h = 260, t0, t1, dom = [0, 1], yf = F.bare, area = false }) {
    const all = series.flatMap(s => s.pts); if (!all.length) return UI.empty("offline", "No price history yet", "Chart fills in as trades print.", true);
    t0 = t0 ?? Math.min(...all.map(p => p[0])); t1 = t1 ?? Math.max(...all.map(p => p[0])); if (t1 === t0) t1 = t0 + 1;
    const top = notches.length ? 34 : 10, bot = 22, L = 40, R = 10, X = t => L + (t - t0) / (t1 - t0) * (w - L - R), Y = p => top + (1 - (p - dom[0]) / (dom[1] - dom[0] || 1)) * (h - top - bot);
    let g = `<g class="grid">${[0.25, 0.5, 0.75].map(k => dom[0] + k * (dom[1] - dom[0])).map(p => `<line x1="${L}" x2="${w - R}" y1="${Y(p)}" y2="${Y(p)}"/><text x="4" y="${Y(p) + 3}">${yf(p)}</text>`).join("")}</g>`;
    g += bands.map((b, i) => `<rect x="${X(b.a)}" y="${top}" width="${Math.max(0, X(b.b) - X(b.a))}" height="${h - top - bot}" fill="${i % 2 ? "#ECE9E1" : "transparent"}" opacity=".6"/><text x="${X(b.a) + 4}" y="${h - 6}" style="font-weight:700;fill:#17171A">${b.label}</text>`).join("");
    if (be) g += `<line x1="${L}" x2="${w - R}" y1="${Y(be.p)}" y2="${Y(be.p)}" stroke="#FF6A13" stroke-dasharray="5 4" stroke-width="1.5"/><text x="${w - R - 4}" y="${Y(be.p) - 4}" text-anchor="end" style="fill:#9a3d00;font-weight:700">break-even ${F.one(be.p)}</text>`;
    g += series.map(s => `<polyline fill="none" stroke="${s.color}" stroke-width="${s.w || 2}" stroke-linejoin="round" points="${s.pts.map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(" ")}"/>${s.label ? `<text x="${X(s.pts.at(-1)[0]) - 2}" y="${Y(s.pts.at(-1)[1]) - 6}" text-anchor="end" style="fill:${s.color};font-weight:800">${esc(s.label)} ${yf(s.pts.at(-1)[1])}</text>` : ""}`).join("");
    g += notches.map(n => `<g class="notch" data-tip="${esc(`${n.label} · Q${n.period} ${n.clock} · ${n.away}–${n.home}${n.team ? " · " + n.team : ""}\n${n.text || ""}`)}"><line x1="${X(n.ts)}" x2="${X(n.ts)}" y1="${top - 4}" y2="${h - bot}" stroke="${n.hype ? "#FFC21A" : "#BDB9AE"}" stroke-width="${n.hype ? 1.6 : 1}" ${n.hype ? "" : 'stroke-dasharray="2 3"'}/><image href="${ICON(EVT[n.type] || "quarter")}" x="${X(n.ts) - 9}" y="4" width="18" height="18"/></g>`).join("");
    g += markers.map(m => { const x = X(m.ts), y = Y(m.price), up = m.side === "BUY"; return `<g class="notch" data-tip="${esc(m.tip)}"><path d="${up ? `M${x},${y - 1} l-6,10 h12 z` : `M${x},${y + 1} l-6,-10 h12 z`}" fill="${up ? "#17171A" : "#E10600"}" stroke="#fff" stroke-width="1"/></g>`; }).join("");
    return `<svg class="chart" viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none">${g}</svg>`;
  },
  entry(e, g) {
    const tags = (e.tags || []);
    return `<div class="entry" data-entry="${e.id}"><div><div class="num" style="font-weight:700">${F.time(e.ts)}</div><div class="micro">${e.period ? `Q${e.period} ${esc(e.clock)}` : ""}</div></div>
      <div><div class="act ${e.action}">${e.action.replace("_", " ")}</div><div class="small" style="margin-top:4px">${esc(e.outcome)}</div></div>
      <div><div><b>${e.side === "BUY" ? "Bought" : "Sold"} ${F.usd(e.stake)}</b> at <b>${F.one(e.price, "multiplier")}</b> <span class="muted">· ${F.one(e.price, "percentage")} · ${F.one(e.price, "precise")} · ${e.qty} ct</span></div>
        <div class="ctx">${g ? `${esc(g.away)} ${e.away_score ?? "–"} – ${e.home_score ?? "–"} ${esc(g.home)} · ` : ""}position ${F.pv(e.pos_value, e.pos_basis)} · ${e.pos_qty ? `break-even ${F.one(e.avg_price)}` : "flat"}${e.side === "SELL" ? ` · realized <b class="${e.realized >= 0 ? "gain" : "loss"}">${F.usd(e.realized, 1)}</b>` : ""}${e.trigger ? ` · after <b>${esc(e.trigger)}</b>` : ""}</div>
        <div class="tags">${JOURNAL_TAGS.map(t => `<button class="chip tag ${tags.includes(t) ? "on" : ""}" data-tag="${t}">${t}</button>`).join("")}</div>
        <input class="note" placeholder="add a thought… (optional)" value="${esc(e.note)}"></div>
      <div>${UI.src(e.source)}</div></div>`;
  },
};
let JOURNAL_TAGS = ["overreaction", "momentum", "averaging-down", "rebalance", "target-hit", "trailing-stop", "gut", "fomo", "tilt", "calm", "nervous", "rule-break"];

function slipFrom(ev, m, i) {
  const o = m.outcomes[i], t = teamsOf(ev);
  return { eventId: ev.eventId, description: ev.description, league: ev.league, startsTs: ev.startsTs, awayAbbr: t.away.abbr, homeAbbr: t.home.abbr, marketId: m.marketId, outcomeId: o.outcomeId,
    outcome: m.marketType === "MONEY" ? o.name : o.name, marketType: m.marketType, label: `${o.name} · ${m.marketType === "MONEY" ? "Winner" : m.marketType === "SPREAD" ? "Spread" : "Total"}`,
    ask: book.ask(m, i), bid: book.bid(o), fee: m.fee };
}

/* =========================== state & data =========================== */
const ST = { fb: null, live: {}, slip: null, mode: "take", amt: 5, makePx: null, journal: null, open: [] };
async function loadFootball() {
  if (ST.fb) return ST.fb;
  ST.fb = await api("/api/football?days=7").catch(e => ({ events: [], error: String(e) }));
  // live scores from ESPN for in-game events (best effort)
  const lives = (ST.fb.events || []).filter(e => e.status === "OPEN_INGAME");
  if (lives.length) {
    const sb = (await Promise.all(["NFL", "NCAAF"].map(l => api(`/api/pbp/scoreboard?league=${l}`).catch(() => ({ games: [] }))))).flatMap(s => s.games);
    for (const e of lives) { const [a, h] = e.description.toLowerCase().split(" @ "); const g = sb.find(g => (g.home?.name || "").toLowerCase().includes(h) || h.includes((g.home?.short || "~").toLowerCase()));
      if (g) ST.live[e.eventId] = { away: g.away.score, home: g.home.score, detail: g.detail, espnId: g.espnId }; }
  }
  return ST.fb;
}
const refreshOpen = async () => (ST.open = (await api("/api/journal/open")).positions);

/* =========================== views =========================== */
const V = {};
V.games = async (q) => {
  const lg = q.league || "ALL", when = q.when || "week", term = (q.q || $("#q").value || "").toLowerCase();
  const head = `<div class="sechead" style="margin-top:0"><h1>Football<span class="streak"></span></h1><span class="grow"></span>
    <div class="chips">${[["ALL", "All"], ["NFL", "NFL"], ["NCAAF", "College"], ["MMA", "MMA"], ["SOCCER", "Soccer"]].map(([k, l]) => `<a class="chip ${lg === k ? "on" : ""} ${["MMA", "SOCCER"].includes(k) ? "soon" : ""}" href="#/games?league=${k}&when=${when}">${k === "MMA" ? `<img src="${ICON("mma")}">` : k === "SOCCER" ? `<img src="${ICON("soccer")}">` : ""}${l}${["MMA", "SOCCER"].includes(k) ? " · soon" : ""}</a>`).join("")}</div>
    <div class="seg">${[["live", "Live"], ["today", "Today"], ["week", "7 days"]].map(([k, l]) => `<button class="${when === k ? "on" : ""}" data-go="#/games?league=${lg}&when=${k}">${l}</button>`).join("")}</div></div>`;
  if (lg === "MMA" || lg === "SOCCER") {
    const st = await api(`/api/future/${lg === "MMA" ? "MMA" : "SOCCER"}`).catch(() => ({}));
    return head + UI.empty(lg === "MMA" ? "mma" : "soccer", `${lg === "MMA" ? "MMA" : "Soccer"} is warming up`, `The hook is stubbed and ready: <code>${esc(JSON.stringify(st).slice(0, 140))}</code>. Flip it on in <code>novig/client.py FUTURE_SPORTS</code> and the same list, slip and journal work unchanged.`);
  }
  $("#main").innerHTML = head + `<div class="skel" style="margin:20px 0;width:60%"></div><div class="skel" style="width:80%"></div>`;
  const fb = await loadFootball();
  if (!fb.events?.length) return head + UI.empty("offline", "Can't reach Novig right now", `The paper API didn't answer (${esc(fb.error || fb.why || "timeout")}). Retrying on next visit.`);
  const now = Date.now(), endToday = new Date().setHours(23, 59, 59, 999);
  let ev = fb.events.filter(e => (lg === "ALL" || e.league === lg) && (!term || (e.description + " " + e.league).toLowerCase().includes(term) || JSON.stringify(e.participants?.competitors?.map(c => c.symbol) || "").toLowerCase().includes(term)));
  if (when === "live") ev = ev.filter(e => e.status === "OPEN_INGAME"); if (when === "today") ev = ev.filter(e => e.startsTs <= endToday);
  const live = ev.filter(e => e.status === "OPEN_INGAME"), rest = ev.filter(e => e.status !== "OPEN_INGAME");
  const days = {}; rest.forEach(e => (days[F.dayKey(e.startsTs)] ||= []).push(e));
  const next = rest[0];
  let html = head + `<div class="small muted" style="margin:-4px 0 8px">${ev.length} games · ${UI.src(fb.source)} Novig paper · ${new Date(fb.from).toLocaleDateString()} → ${new Date(fb.to).toLocaleDateString()} ${term ? ` · filter “${esc(term)}” <a href="#/games">clear</a>` : ""}</div>`;
  if (live.length) html += `<div class="dayhead"><span class="badge live">live now</span><h2>${live.length} in progress</h2></div>` + UI.gameHead() + live.map(e => UI.gameRow(e, ST.live)).join("");
  else if (next && !term) { const t = teamsOf(next); html += `<div class="card ink" style="margin-top:12px;display:flex;gap:24px;align-items:center" data-go="#/game/${next.eventId}"><img src="assets/pip-cheer.svg" style="width:84px"><div><div class="micro">Next kickoff · ${F.day(next.startsTs)} ${F.time(next.startsTs)}</div><div class="h2">${esc(t.away.name)} <span class="streak"></span> ${esc(t.home.name)}</div><div class="small">Nothing live. Countdown <b class="num" data-countdown="${next.startsTs}"></b></div></div><span style="flex:1"></span>${UI.pxPair(next.markets?.MONEY, next)}</div>`; }
  for (const [k, list] of Object.entries(days)) {
    const d = new Date(list[0].startsTs), dow = d.getDay(), tag = dow === 6 ? "College Saturday" : dow === 0 ? "NFL Sunday" : dow === 1 ? "Monday Night" : dow === 4 ? "Thursday Night" : "";
    html += `<div class="dayhead"><h2>${F.day(list[0].startsTs)}</h2><span class="micro">${tag} · ${list.length} games</span></div>` + UI.gameHead() + list.map(e => UI.gameRow(e, ST.live)).join("");
  }
  return html || head + UI.empty("sleep", "No games match", "Try another filter.");
};

V.game = async (q, id) => {
  $("#main").innerHTML = `<div class="skel" style="width:40%;height:60px"></div>`;
  const fb = await loadFootball(); const ev = fb.events.find(e => e.eventId === id) || { eventId: id, description: "Game", league: "NFL", markets: {} };
  const t = teamsOf(ev);
  const [all, open] = await Promise.all([api(`/api/event-markets/${id}`).catch(() => ({ items: [] })), refreshOpen()]);
  const mkts = (all.items || []); const money = ev.markets?.MONEY || mkts.find(m => m.marketType === "MONEY");
  const selId = q.m || money?.marketId; const sel = mkts.find(m => m.marketId === selId) || money;
  const det = sel ? await api(`/api/market/${sel.marketId}`).catch(() => ({})) : {};
  const match = ev.status !== "OPEN_PREGAME" ? await api(`/api/pbp/match?desc=${encodeURIComponent(ev.description)}&ts=${ev.startsTs}&league=${ev.league}`).catch(() => ({})) : {};
  const pg = match.game; const lastE = pg?.events?.at(-1);
  // price series: candles (signed) → trades → flat from last
  let src = "live", pts = [];
  const cd = det.candles?.items || det.candles?.candles || (Array.isArray(det.candles) ? det.candles : null);
  if (cd?.length) pts = cd.map(c => [c.ts || c.startTs || Date.parse(c.time), +(c.close ?? c.c)]).filter(p => p[1]);
  else if (det.trades?.items?.length) { const oc0 = sel.outcomes[0].outcomeId; pts = det.trades.items.map(x => [x.ts || Date.parse(x.timestamp), x.outcomeId === oc0 ? +x.price : 1 - x.price]).sort((a, b) => a[0] - b[0]); }
  else if (sel) { src = "sample"; const p0 = +(sel.outcomes[0].last || book.ask(sel, 0) || .5); let p = p0; const n = 60; pts = Array.from({ length: n }, (_, i) => { p = Math.min(.95, Math.max(.05, p + (Math.sin(i * 1.7 + p0 * 9) * .012))); return [Date.now() - (n - i) * 60000, i === n - 1 ? p0 : p]; }); }
  const range = q.r || "All", cut = { "1H": 3600e3, "1D": 864e5 }[range]; if (cut) pts = pts.filter(p => p[0] >= Date.now() - cut);
  const myPos = open.filter(p => p.game.game_key === id); const pos = myPos[0];
  const groups = {}; const mainIds = new Set(Object.values(ev.markets || {}).map(m => m.marketId));
  Object.values(ev.markets || {}).forEach(m => (groups[m.marketType] ||= []).push(m));
  mkts.filter(m => !mainIds.has(m.marketId) && m.outcomes.some(o => o.bid)).forEach(m => (groups[m.marketType] ||= []).push(m));
  const order = ["MONEY", "SPREAD", "TOTAL"]; const types = Object.keys(groups).sort((a, b) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99));
  const tab = q.tab || "main";
  if (q.slip != null && money) setTimeout(() => { openSlip(slipFrom(ev, money, +q.slip)); if (q.mode) { ST.mode = q.mode; ST.makePx = +(book.ask(money, +q.slip) - .01).toFixed(3); renderSlip(); } }, 50);
  const mainTypes = types.filter(x => order.includes(x)), otherTypes = types.filter(x => !order.includes(x));
  const row = m => `<tr class="${m.marketId === selId ? "selrow" : ""}"><td><a href="#/game/${id}?m=${m.marketId}&tab=${tab}">${esc(m.description)}</a><div class="micro">${m.marketType} ${m.strike !== "0" ? m.strike : ""} · vol ${m.volume.toLocaleString()}</div></td><td class="r">${UI.pxPair(m, ev)}</td></tr>`;
  const listTypes = tab === "main" ? mainTypes : otherTypes;
  const exposure = myPos.reduce((s, p) => s + p.basis, 0);
  const rulesChecks = [{ ok: exposure <= S.gameExposure, t: `Game exposure ${F.usd(exposure)} ≤ ${F.usd(S.gameExposure)}` }, { ok: true, t: `Enter only on a hype event (INT, fumble lost, TOD, blocked kick) with edge ≥ ${S.edgeMin}` }, { ok: true, t: `Trail ${S.trail} in price once ≥ break-even` }, { ok: true, t: `Max ${S.maxAdds} adds, each ≥ 0.03 lower` }];
  const meta = ev.status === "OPEN_INGAME" ? `<span class="badge live">live</span><div class="h3" style="margin-top:6px">${lastE ? `Q${lastE.period} ${esc(lastE.clock)}` : ""}</div>` : `<div class="micro">kickoff</div><div class="h3">${F.day(ev.startsTs)} ${F.time(ev.startsTs)}</div>`;
  return `<div class="micro" style="margin-bottom:10px"><a href="#/games">Games</a> / ${ev.league} / ${esc(ev.description)}</div>
    ${UI.scoreboard({ ...t.away, color: pg?.away?.color }, { ...t.home, color: pg?.home?.color }, lastE?.away ?? (ev.status === "OPEN_PREGAME" ? "" : null), lastE?.home ?? "", meta + `<div class="small">${ev.marketCount || mkts.length} markets · vol ${(ev.volume || 0).toLocaleString()} ct</div>`)}
    <hr class="rule ink">
    <div class="grid">
      <div class="c8"><div style="display:flex;align-items:center;gap:8px;margin-bottom:6px"><span class="micro">${esc(sel?.description || "")} · price path</span>${UI.src(src, "no candles/trades returned; illustrative path ending at current price")}<span style="flex:1"></span>
        <div class="seg">${["1H", "1D", "All"].map(r => `<button class="${range === r ? "on" : ""}" data-go="#/game/${id}?m=${selId}&tab=${tab}&r=${r}">${r}</button>`).join("")}</div></div>
        ${UI.chart({ series: sel ? [{ pts, color: "#17171A", label: sel.outcomes[0].name }, { pts: pts.map(p => [p[0], 1 - p[1]]), color: "#E10600", label: sel.outcomes[1].name, w: 1.5 }] : [], notches: (pg?.events || []).filter(n => n.hype || n.type === "HALFTIME"), markers: [], h: 240 })}
        <div class="sechead"><h2>Game lines</h2><span class="grow"></span><div class="seg"><button class="${tab === "main" ? "on" : ""}" data-go="#/game/${id}?tab=main">Main</button><button class="${tab === "more" ? "on" : ""}" data-go="#/game/${id}?tab=more">More & props (${otherTypes.reduce((s, x) => s + groups[x].length, 0)})</button></div></div>
        ${listTypes.length ? listTypes.map(x => `<div class="micro" style="margin:14px 0 4px">${x.replaceAll("_", " ")}</div><table class="t">${groups[x].slice(0, tab === "main" ? 4 : 8).map(row).join("")}</table>`).join("") : UI.empty("sleep", "Nothing here yet", "Novig hasn't listed these markets for this game.", true)}
      </div>
      <div class="c4" style="display:flex;flex-direction:column;gap:16px">
        ${UI.position(pos)}
        ${UI.rules(rulesChecks)}
        <div class="card"><h4>Order book · ${esc(sel?.description || "")} ${UI.src("live")}</h4>${UI.ladder(sel, det.book)}<div class="small muted" style="margin-top:6px">Tap a level to MAKE at that price.</div></div>
        ${pg ? `<div class="card"><h4>Play-by-play · ESPN ${UI.badge("src", "live")}</h4>${pg.events.filter(e => e.hype).slice(-6).reverse().map(e => `<div style="display:flex;gap:8px;padding:5px 0;border-bottom:1px solid var(--rule)"><img src="${ICON(EVT[e.type])}" width="22"><div class="small"><b>${e.label}</b> · Q${e.period} ${e.clock} · ${e.away}–${e.home}<br>${esc(e.text.slice(0, 90))}</div></div>`).join("")}</div>` : `<div class="card"><h4>Play-by-play</h4><div class="small">Matched to ESPN at kickoff; notches appear on the chart and in your journal.</div></div>`}
      </div></div>`;
};

V.positions = async () => {
  const [open, acct] = await Promise.all([refreshOpen(), api("/api/account").catch(() => null)]);
  const tot = open.reduce((a, p) => ({ v: a.v + p.value, b: a.b + p.basis }), { v: 0, b: 0 });
  const nov = acct?.positions;
  return `<div class="sechead" style="margin-top:0"><h1>Positions<span class="streak"></span></h1><span class="grow"></span>${UI.stat("Open value", F.pv(tot.v, tot.b))}</div>
   ${open.length ? `<table class="t"><tr><th>Game</th><th>Side</th><th class="r">Value (Δ vs basis)</th><th class="r">Contracts</th><th class="r">Break-even</th><th class="r">Mark</th><th>Add</th><th>Exit</th><th></th></tr>
   ${open.map(p => `<tr><td><a href="#/journal/${p.game.game_key}">${esc(p.game.away)} @ ${esc(p.game.home)}</a><div class="micro">${F.ago(p.lastTs)}</div></td><td><b>${esc(p.outcome)}</b></td><td class="r">${F.pv(p.value, p.basis)}</td><td class="r">${p.qty}</td><td class="r">${F.one(p.avg)}</td><td class="r">${F.one(p.mark)}</td>
     <td>${S.stakes.slice(0, 3).map(s => `<button class="btn sm make" data-add="${s}" data-outcome="${esc(p.outcome)}" data-gk="${p.game.game_key}" data-px="${p.mark}">+${s}</button>`).join(" ")}</td>
     <td><button class="btn sm" data-sell=".5" data-outcome="${esc(p.outcome)}" data-gk="${p.game.game_key}" data-px="${p.mark}">½</button> <button class="btn sm primary" data-sell="1" data-outcome="${esc(p.outcome)}" data-gk="${p.game.game_key}" data-px="${p.mark}">All</button></td><td>${UI.src(p.source)}</td></tr>`).join("")}</table>`
     : UI.empty("shrug", "No open positions", "When you buy, it shows up here with live value vs basis, quick adds and exits.")}
   <div class="sechead"><h2>On Novig · grok-paper-trading</h2>${UI.src(nov?.source, nov?.why)}</div>
   <table class="t"><tr><th>Market</th><th>Outcome</th><th class="r">Qty</th><th class="r">Avg</th></tr>${(Array.isArray(nov?.data) ? nov.data : nov?.data?.items || []).slice(0, 8).map(p => `<tr><td>${esc(acct.names?.markets?.[p.marketId] || p.marketId?.slice(0, 8))}</td><td>${esc(acct.names?.outcomes?.[p.outcomeId] || p.outcomeId?.slice(0, 8))}</td><td class="r">${p.qty ?? p.position ?? ""}</td><td class="r">${p.avgPrice ? F.one(+p.avgPrice) : p.price ? F.one(+p.price) : ""}</td></tr>`).join("") || `<tr><td colspan=4 class="muted">none</td></tr>`}</table>`;
};

V.account = async (q) => {
  const [a, j] = await Promise.all([api("/api/account").catch(() => null), api("/api/journal/days")]);
  if (!a) return UI.empty("offline", "Account unavailable", "Novig paper API didn't answer.");
  const tab = q.tab || "overview", games = j.days; let cum = 0; const curve = games.slice().reverse().map(g => [g.last_ts, (cum += g.realized || 0)]);
  const wins = games.filter(g => g.realized > 0).length;
  const bal = +(a.subBalance?.balance ?? 0), main = +(a.balance.data?.balance ?? 0);
  const tabs = `<div class="seg">${[["overview", "Overview"], ["tx", "Transactions"], ["history", "Orders & fills"]].map(([k, l]) => `<button class="${tab === k ? "on" : ""}" data-go="#/account?tab=${k}">${l}</button>`).join("")}</div>`;
  let body = "";
  if (tab === "overview") body = `<div class="grid" style="margin-top:16px"><div class="c3 card ink">${UI.stat("Trading sub-account", F.usd(bal), "grok-paper-trading " + UI.src(a.subBalance?.balance ? "live" : "sample"))}</div><div class="c3 card">${UI.stat("Main paper wallet", F.usd(main), UI.src(a.balance.source))}</div>
     <div class="c3 card">${UI.stat("Journal P&L (realized)", F.usd(cum, 1), `${games.length} games · ${wins} green`, cum >= 0 ? "gain" : "loss")}</div><div class="c3 card">${UI.stat("Orders", a.writesEnabled ? "LIVE" : "DRY-RUN", "nothing is sent")}</div>
     <div class="c8 card"><h4>Realized P&L by game (journal) ${UI.src("sample")}</h4>${UI.chart({ series: [{ pts: [[curve[0]?.[0] - 36e5, 0], ...curve], color: "#17171A", label: "P&L" }], h: 180, dom: [Math.min(0, ...curve.map(c => c[1])) - 2, Math.max(0, ...curve.map(c => c[1])) + 2], yf: v => F.usd(v) })}</div>
     <div class="c4 card"><h4>By game</h4>${games.map(g => `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--rule)"><a href="#/journal/${g.game_key}">${esc(g.away)} @ ${esc(g.home)}</a><b class="num ${g.realized >= 0 ? "gain" : "loss"}">${F.usd(g.realized, 1)}</b></div>`).join("")}</div></div>`;
  if (tab === "tx") body = `<div class="sechead"><h2>Transactions</h2>${UI.src(a.transactions.source, a.transactions.why)}</div><table class="t"><tr><th>When</th><th>Type</th><th class="r">Amount</th><th class="r">Balance</th></tr>${(a.transactions.data.items || []).slice(0, 25).map(x => `<tr><td>${new Date(x.ts || Date.parse(x.createdAt) || 0).toLocaleString()}</td><td>${esc(x.type || x.kind)}</td><td class="r">${esc(x.amount)}</td><td class="r">${esc(x.balance ?? "")}</td></tr>`).join("")}</table>
     <div class="sechead"><h2>Transfers</h2>${UI.src(a.transfers.source)}</div><table class="t">${(a.transfers.data.items || []).slice(0, 10).map(x => `<tr><td>${esc(x.transferId?.slice(0, 8))}</td><td>${esc(x.status)}</td><td class="r">${esc(x.amount)}</td></tr>`).join("")}</table>`;
  if (tab === "history") body = `<div class="sechead"><h2>Orders</h2>${UI.src(a.orders.source, a.orders.why)}</div><table class="t"><tr><th>Order</th><th>Status</th><th class="r">Price</th><th class="r">Qty</th><th>TIF</th></tr>${(a.orders.data.items || []).map(o => `<tr><td>${esc(a.names?.outcomes?.[o.outcomeId] || o.orderId?.slice(0, 8))}</td><td>${esc(o.status)}</td><td class="r">${F.one(+o.price)}</td><td class="r">${o.qty}</td><td>${o.tif}</td></tr>`).join("")}</table>
     <div class="sechead"><h2>Fills</h2>${UI.src(a.fills.source)}</div><table class="t"><tr><th>When</th><th>Outcome</th><th class="r">Price</th><th class="r">Qty</th><th>Liquidity</th></tr>${(a.fills.data.items || []).map(f => `<tr><td>${new Date(f.ts || 0).toLocaleString()}</td><td>${esc(a.names?.outcomes?.[f.outcomeId] || f.outcomeId?.slice(0, 8))}</td><td class="r">${F.one(+f.price)}</td><td class="r">${f.qty}</td><td>${esc(f.liquidity || f.side || "")}</td></tr>`).join("")}</table>
     <div class="sechead"><h2>Settled positions</h2>${UI.src(a.historyPositions.source)}</div><table class="t">${(a.historyPositions.data.items || []).map(p => `<tr><td>${esc(a.names?.outcomes?.[p.outcomeId] || "")}</td><td>${esc(p.result || p.status || "")}</td><td class="r">${esc(p.pnl ?? p.realizedPnl ?? "")}</td></tr>`).join("")}</table>`;
  return `<div class="sechead" style="margin-top:0"><h1>Account<span class="streak"></span></h1><span class="grow"></span>${tabs}</div>${body}`;
};

V.journal = async () => {
  const j = ST.journal = await api("/api/journal/days"); JOURNAL_TAGS = j.tags || JOURNAL_TAGS;
  if (!j.days.length) return UI.empty("write", "Your journal writes itself", "Place a bet anywhere in the app and an entry appears here, batched by game and day.");
  const byDay = {}; j.days.forEach(g => (byDay[F.dayKey(g.first_ts)] ||= []).push(g));
  return `<div class="sechead" style="margin-top:0"><h1>Journal<span class="streak"></span></h1><span class="grow"></span><span class="small">Every fill auto-logged · tap a game for its story</span></div>` +
    Object.values(byDay).map(gs => `<div class="dayhead"><h2>${F.day(gs[0].first_ts)}</h2><span class="micro">${gs.length} games · ${F.usd(gs.reduce((s, g) => s + (g.realized || 0), 0), 1)}</span></div>` +
      gs.map(g => `<a class="gamebatch" href="#/journal/${g.game_key}"><div style="display:flex;gap:10px;align-items:center">${mark(g.away, g.away_color, 30)}${mark(g.home, g.home_color, 30)}<div><h3>${esc(g.away)} @ ${esc(g.home)}</h3><div class="micro">${g.league} · ${g.spread_text || ""} · ${F.time(g.first_ts)}–${F.time(g.last_ts)}</div></div></div>
        <div class="small">${g.fills} fills</div><div class="small">staked ${F.usd(g.staked)}</div><b class="num ${g.realized >= 0 ? "gain" : "loss"}" style="font-size:20px">${F.usd(g.realized, 1)}</b></a>`).join("")).join("") +
    `<div class="sechead"><h2>Expected price move per hype event</h2>${UI.src("sample", "computed from seeded sample price paths")}</div><div id="impacts">${await impactsTable()}</div>`;
};
async function impactsTable() {
  const d = await api("/api/journal/impacts"); const c = v => `<td class="r ${v >= 0 ? "gain" : "loss"}">${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(3)}</td>`;
  return `<table class="t"><tr><th>Event</th><th>Spread bucket</th><th class="r">n</th><th class="r">+1m</th><th class="r">+3m</th><th class="r">+5m</th><th class="r">+10m</th></tr>${d.impacts.filter(r => r.n >= 2).slice(0, 14).map(r => `<tr><td><img src="${ICON(EVT[r.type])}" width="18" style="vertical-align:middle"> ${esc(d.eventTypes[r.type]?.label || r.type)}</td><td>${esc(r.spread)}</td><td class="r">${r.n}</td>${c(r.d60s)}${c(r.d180s)}${c(r.d300s)}${c(r.d600s)}</tr>`).join("")}</table><div class="small muted">Price change for the team with the ball on the play, in implied-probability points vs 30s before the event. Builds automatically as real games are journaled.</div>`;
}

V.story = async (q, gk) => {
  const s = await api(`/api/journal/story/${gk}`); const g = s.game; const ev = s.events;
  const qs = ev.filter(e => e.type === "END_QUARTER" || e.type === "HALFTIME" || e.type === "END_GAME");
  const k0 = ev[0]?.ts || s.entries[0]?.ts, bounds = [k0, ...qs.map(e => e.ts)];
  const bands = bounds.slice(0, -1).map((a, i) => ({ a, b: bounds[i + 1], label: "Q" + (i + 1) }));
  const evById = Object.fromEntries(ev.map(e => [e.id, e]));
  s.entries.forEach(e => { const t = evById[e.trigger_event_id]; e.trigger = t ? `${t.type.replace("_", " ").toLowerCase()} Q${t.period} ${t.clock}` : null; });
  const outs = Object.keys(s.ticks); const colors = { [g.home]: "#17171A", [g.away]: "#E10600" };
  const hypeOnly = q.all ? ev.filter(e => e.type !== "TIMEOUT" && e.type !== "END_QUARTER") : ev.filter(e => e.hype || ["HALFTIME", "KICKOFF_GAME", "END_GAME"].includes(e.type));
  const last = ev.at(-1) || {}; const traded = [...new Set(s.entries.map(e => e.outcome))];
  const beLine = (() => { const op = Object.entries(s.summary.open)[0]; return op ? { p: op[1].basis / (op[1].qty / 100) } : null; })();
  const legsHtml = s.legs.map((L, i) => { const es = s.entries.filter(e => L.entries.includes(e.id)); return `<div class="dayhead" style="margin-top:20px"><h3>Leg ${i + 1} · ${esc(L.outcome)}</h3><span class="micro">${F.time(L.start)}${L.end ? "–" + F.time(L.end) : " · open"} · ${es.length} fills</span><span class="grow" style="flex:1"></span><b class="num ${L.realized >= 0 ? "gain" : "loss"}">${L.realized != null ? F.usd(L.realized, 1) : "open"}</b></div>` + es.map(e => UI.entry(e, g)).join(""); }).join("");
  return `<div class="micro" style="margin-bottom:10px"><a href="#/journal">Journal</a> / ${F.day(k0)} / ${esc(g.away)} @ ${esc(g.home)}</div>
    ${UI.scoreboard({ abbr: g.away, name: g.away, color: g.away_color }, { abbr: g.home, name: g.home, color: g.home_color }, last.away_score, last.home_score, `<div class="micro">${g.league} · ${esc(g.spread_text || "")}</div><div class="small">${UI.badge("src", "plays: ESPN")} ${UI.src("sample", "price path = ESPN win prob + synthetic overreaction")}</div>`)}
    <hr class="rule ink">
    <div class="grid"><div class="c3">${UI.stat("Realized", F.usd(s.summary.realized, 1), "", s.summary.realized >= 0 ? "gain" : "loss")}</div><div class="c3">${UI.stat("Staked", F.usd(s.summary.staked), `${s.summary.buys} buys · ${s.summary.sells} sells`)}</div><div class="c3">${UI.stat("Entries after a hype event", `${s.summary.entriesAfterHype}/${s.summary.buys}`)}</div><div class="c3">${UI.stat("Hype events", s.summary.hypeEvents)}</div></div>
    <div class="sechead"><h2>Timeline</h2><span class="grow"></span><span class="small">${traded.map(o => `<b style="color:${colors[o] || "#17171A"}">━ ${esc(o)}</b>`).join(" ")} · ▲ buy ▼ sell · <img src="${ICON("int")}" width="14"> notches</span>
      <div class="seg"><button class="${q.all ? "" : "on"}" data-go="#/journal/${gk}">Hype</button><button class="${q.all ? "on" : ""}" data-go="#/journal/${gk}?all=1">All events</button></div></div>
    ${UI.chart({ series: outs.filter(o => traded.includes(o) || outs.length <= 2).map(o => ({ pts: s.ticks[o].map(t => [t.ts, t.price]), color: colors[o] || "#5B5F66", label: o, w: traded.includes(o) ? 2 : 1.2 })), notches: hypeOnly, bands, be: beLine,
      markers: s.entries.map(e => ({ ts: e.ts, price: e.price, side: e.side, tip: `${e.action} ${e.outcome} ${F.usd(e.stake)} @ ${F.all(e.price)}\nQ${e.period} ${e.clock} · ${e.away_score}–${e.home_score}\npos ${F.usd(e.pos_value)} (basis ${F.usd(e.pos_basis)})` })), h: 320, t0: k0, t1: last.ts })}
    <div class="grid" style="margin-top:8px"><div class="c8"><div class="sechead"><h2>The story</h2></div><ol style="padding-left:18px;font-size:15px;line-height:1.55">${s.summary.narrative.map(l => `<li>${esc(l)}</li>`).join("")}</ol>${legsHtml}</div>
      <div class="c4">${UI.rules([{ ok: s.summary.staked <= S.gameExposure, t: `Game exposure ${F.usd(s.summary.staked)} ≤ ${F.usd(S.gameExposure)}` }, { ok: s.summary.entriesAfterHype === s.summary.buys, t: `Every buy follows a hype event (${s.summary.entriesAfterHype}/${s.summary.buys})` }, { ok: !s.entries.some(e => (e.tags || []).includes("rule-break")), t: "No rule-break tags" }, { ok: s.legs.every(L => s.entries.filter(e => L.entries.includes(e.id) && e.action === "ADD").length <= S.maxAdds), t: `≤ ${S.maxAdds} adds per leg` }])}
        <div class="card" style="margin-top:16px"><h4>Event log</h4>${ev.filter(e => e.hype || e.type === "HALFTIME").map(e => `<div style="display:flex;gap:8px;padding:4px 0;border-bottom:1px solid var(--rule)"><img src="${ICON(EVT[e.type])}" width="20"><div class="small"><b>${esc(e.type.replace("_", " "))}</b> Q${e.period} ${e.clock} · ${e.away_score}–${e.home_score} ${e.team ? "· " + esc(e.team) : ""}</div></div>`).join("")}</div></div></div>`;
};

V.settings = async () => {
  const st = await api("/api/status").catch(() => ({}));
  const ex = [0.412, 0.529];
  return `<div class="sechead" style="margin-top:0"><h1>Settings<span class="streak"></span></h1></div>
   <div class="grid"><div class="c6 card ink"><h4>Price format</h4>${[["multiplier", "Multiplier", "default · decimal payout per $1"], ["percentage", "Percentage", "implied probability"], ["precise", "Precise Percentage", "one decimal"]].map(([k, l, d]) => `<label style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--rule);cursor:pointer"><input type="radio" name="fmt" value="${k}" ${S.fmt === k ? "checked" : ""}><div style="flex:1"><b>${l}</b><div class="small">${d}</div></div><span class="num h3">${F.pair(...ex, k)}</span></label>`).join("")}</div>
   <div class="c6 card"><h4>Rules (rulebook §8)</h4>${[["maxStake", "Max stake per entry $"], ["gameExposure", "Max exposure per game $"], ["dailyStop", "Daily stop −$"], ["maxAdds", "Max adds per leg"], ["trail", "Trailing stop (price pts)"], ["edgeMin", "Min edge p − q"]].map(([k, l]) => `<label style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--rule)"><span>${l}</span><input data-set="${k}" value="${S[k]}" style="width:80px;text-align:right;border:1px solid var(--rule-2);padding:3px 6px"></label>`).join("")}
     <div style="margin-top:10px"><span class="small">Quick stakes</span> <input data-set="stakes" value="${S.stakes.join(",")}" style="width:120px;border:1px solid var(--rule-2);padding:3px 6px"></div></div>
   <div class="c6 card"><h4>Data sources</h4><dl class="kv"><dt>Novig</dt><dd>${esc(st.host || "")} ${st.hasKey ? UI.src("live") : UI.src("sample")}</dd><dt>Play-by-play</dt><dd>ESPN site API ${UI.src("live")}</dd><dt>NCAAF backfill</dt><dd>CollegeFootballData · stub</dd><dt>NFL backfill</dt><dd>nflverse · stub</dd><dt>MMA / Soccer</dt><dd>hooks stubbed</dd></dl></div>
   <div class="c6 card"><h4>Orders</h4><p class="small">Orders are <b>dry-run</b>: the slip shows the exact <code>POST /v3/orders</code> body and journals a dry-run fill. Real paper orders need <code>NOVIG_ALLOW_PAPER_ORDERS=1</code> and the sub-account trading key.</p><p class="small">Writes enabled: <b>${st.writesEnabled ? "yes" : "no"}</b></p><button class="btn sm" onclick="localStorage.removeItem('nc.settings');location.reload()">Reset settings</button></div></div>`;
};

/* =========================== slip =========================== */
function openSlip(s) { ST.slip = s; ST.mode = "take"; ST.makePx = s.ask; renderSlip(); $("#slip").classList.add("open"); $("#main").classList.add("withslip"); }
function closeSlip() { $("#slip").classList.remove("open"); $("#main").classList.remove("withslip"); }
function slipChecks(stake) {
  const open = ST.open.filter(p => p.game.game_key === ST.slip?.eventId).reduce((s, p) => s + p.basis, 0);
  return [{ ok: stake <= S.maxStake, t: `Stake ${F.usd(stake)} ≤ max ${F.usd(S.maxStake)} (¼ Kelly cap)` }, { ok: open + stake <= S.gameExposure, t: `Game exposure ${F.usd(open + stake)} ≤ ${F.usd(S.gameExposure)}` }, { ok: true, t: `Did a hype event just happen? Enter on overreaction, not hope.` }];
}
function renderSlip() {
  const s = ST.slip, el = $("#slip"); if (!s) { el.innerHTML = UI.empty("write", "Slip is empty", "Tap any price.", true); return; }
  const p = ST.mode === "take" ? s.ask : ST.makePx, qty = Math.round(ST.amt / p * 100), payout = qty / 100, coef = +(s.fee?.coefficient || .06);
  const fee = coef * qty / 100 * p * (1 - p), checks = slipChecks(ST.amt), bad = checks.some(c => !c.ok);
  el.innerHTML = `<div style="display:flex;align-items:center"><div class="micro">Order slip</div><span style="flex:1"></span><button class="btn ghost sm" data-close>✕</button></div>
   <div><div class="h3">${esc(s.label)}</div><div class="small">${esc(s.description)}</div></div>
   <div class="seg make"><button class="${ST.mode === "take" ? "on" : ""}" data-mode="take">Take</button><button class="mk ${ST.mode === "make" ? "on" : ""}" data-mode="make">Make</button></div>
   <div class="small">${ST.mode === "take" ? "Fill now at the best available price." : "Rest an order on the book at your price (maker credit)."}</div>
   <div style="display:flex;align-items:end;gap:10px"><div class="bigpx">${F.one(p)}</div><div class="small muted" style="padding-bottom:8px">${F.one(p, "precise")}</div>
     ${ST.mode === "make" ? `<div class="stepper" style="margin-left:auto"><button data-step="-1">−</button><button data-step="1">+</button></div>` : ""}</div>
   <div class="amt">${S.stakes.map(v => `<button class="chip ${ST.amt === v ? "on" : ""}" data-amt="${v}">$${v}</button>`).join("")}<input id="amtIn" value="${ST.amt}" inputmode="decimal"></div>
   <dl class="kv"><dt>Contracts</dt><dd>${qty}</dd><dt>Payout if wins</dt><dd>${F.usd(payout)}</dd><dt>Profit if wins</dt><dd class="gain">${F.usd(payout - ST.amt, 1)}</dd><dt>Max taker fee (live)</dt><dd>${F.usd(fee)}</dd></dl>
   ${bad ? UI.rules(checks) : `<div class="small gain">✓ within your rules</div>`}
   <button class="btn primary block" data-place>${ST.mode === "take" ? "Buy" : "Place maker"} ${F.usd(ST.amt)} · ${F.one(p)} ⏎</button>
   <div class="small muted">${UI.badge("dry", "dry-run")} Nothing is sent to Novig. A journal entry is created automatically.</div><div id="slipPrev"></div>`;
}
async function place() {
  const s = ST.slip, p = ST.mode === "take" ? s.ask : ST.makePx;
  const r = await post("/api/journal/fill", { ...s, side: "BUY", price: p, stake: ST.amt, tags: slipChecks(ST.amt).some(c => !c.ok) ? ["rule-break"] : [] });
  $("#slipPrev").innerHTML = r.preview ? `<details class="small"><summary>Request that would be sent</summary><pre style="white-space:pre-wrap;font-size:11px">${esc(JSON.stringify(r.preview.request, null, 1))}</pre></details>` : "";
  toast(r.entry); await refreshOpen(); if (location.hash.startsWith("#/game") || location.hash.startsWith("#/positions")) route();
}
async function quick(btn) {
  const out = btn.dataset.outcome, gk = btn.dataset.gk || location.hash.split("/")[2]?.split("?")[0];
  const p = ST.open.find(x => x.outcome === out && x.game.game_key === gk); const px = +(btn.dataset.px || p?.mark);
  const body = btn.dataset.add ? { game_key: gk, outcome: out, side: "BUY", stake: +btn.dataset.add, price: px } : { game_key: gk, outcome: out, side: "SELL", qty: Math.max(1, Math.round(p.qty * +btn.dataset.sell)), price: px };
  const r = await post("/api/journal/fill", body); toast(r.entry); await refreshOpen(); route();
}
function toast(e) {
  if (!e) return; const t = document.createElement("div"); t.className = "toast";
  t.innerHTML = `<b>${e.action.replace("_", " ")} ${esc(e.outcome)}</b> ${F.usd(e.stake)} @ ${F.one(e.price)} · journaled <span class="chips">${["overreaction", "gut", "nervous", "calm"].map(x => `<button class="chip" data-ttag="${x}">${x}</button>`).join("")}</span>`;
  t.querySelectorAll("[data-ttag]").forEach(b => b.onclick = async () => { b.classList.toggle("on"); const tags = [...t.querySelectorAll(".chip.on")].map(x => x.dataset.ttag); await post("/api/journal/annotate", { id: e.id, tags: [...new Set([...JSON.parse(e.tags || "[]"), ...tags])] }); });
  $("#toasts").appendChild(t); setTimeout(() => t.remove(), 7000);
}

/* =========================== router & events =========================== */
async function route() {
  const [path, qs] = (location.hash.slice(1) || "/games").split("?"); const q = Object.fromEntries(new URLSearchParams(qs || ""));
  const parts = path.split("/").filter(Boolean); const name = parts[0] || "games";
  $$(".rail a").forEach(a => a.classList.toggle("on", a.dataset.r === name));
  const fn = { games: V.games, game: V.game, positions: V.positions, account: V.account, journal: parts[1] ? V.story : V.journal, settings: V.settings }[name] || V.games;
  try { const html = await fn(q, parts[1]); if (html) $("#main").innerHTML = html; } catch (e) { console.error(e); $("#main").innerHTML = UI.empty("offline", "Something broke", esc(e.message)); }
  document.title = `novig/clean · ${name}`; window.scrollTo?.(0, 0); tick();
}
function tick() { $$("[data-countdown]").forEach(el => { const d = +el.dataset.countdown - Date.now(), h = Math.floor(d / 36e5), m = Math.floor(d % 36e5 / 6e4); el.textContent = d > 0 ? `${h}h ${m}m` : "now"; }); }
function boot() {
  document.addEventListener("click", async ev => {
    const t = ev.target.closest("[data-slip],[data-go],[data-close],[data-mode],[data-amt],[data-step],[data-place],[data-add],[data-sell],[data-tag],[data-make]"); if (!t) return;
    if (t.dataset.slip) { ev.stopPropagation(); return openSlip(JSON.parse(t.dataset.slip)); }
    if (t.dataset.add || t.dataset.sell) { ev.stopPropagation(); return quick(t); }
    if (t.dataset.tag) { const en = t.closest("[data-entry]"); t.classList.toggle("on"); return post("/api/journal/annotate", { id: en.dataset.entry, tags: $$(".chip.tag.on", en).map(x => x.dataset.tag) }); }
    if (t.dataset.make && ST.slip) { const m = JSON.parse(t.dataset.make); ST.mode = "make"; ST.makePx = m.price; return renderSlip(); }
    if (t.dataset.go) return location.hash = t.dataset.go;
    if ("close" in t.dataset) return closeSlip();
    if (t.dataset.mode) { ST.mode = t.dataset.mode; return renderSlip(); }
    if (t.dataset.amt) { ST.amt = +t.dataset.amt; return renderSlip(); }
    if (t.dataset.step) { ST.makePx = Math.min(.99, Math.max(.01, +(ST.makePx + .005 * +t.dataset.step).toFixed(3))); return renderSlip(); }
    if ("place" in t.dataset) return place();
  });
  document.addEventListener("change", ev => {
    if (ev.target.name === "fmt") { S.fmt = ev.target.value; save(); $("#fmtChip").textContent = F.pair(.412, .529); }
    if (ev.target.dataset.set) { const k = ev.target.dataset.set; S[k] = k === "stakes" ? ev.target.value.split(",").map(Number) : +ev.target.value; save(); }
    if (ev.target.id === "amtIn") { ST.amt = +ev.target.value || 1; renderSlip(); }
    if (ev.target.classList.contains("note")) post("/api/journal/annotate", { id: ev.target.closest("[data-entry]").dataset.entry, note: ev.target.value });
  });
  document.addEventListener("keydown", ev => {
    if ((ev.key === "/" || (ev.key === "k" && (ev.metaKey || ev.ctrlKey))) && document.activeElement.tagName !== "INPUT") { ev.preventDefault(); $("#q").focus(); }
    if (ev.key === "Escape") { closeSlip(); if (document.activeElement.id === "q") { $("#q").value = ""; $("#q").blur(); route(); } }
    if (ev.key === "Enter" && $("#slip").classList.contains("open") && document.activeElement.tagName !== "INPUT") place();
  });
  $("#q").addEventListener("input", () => { clearTimeout(window._qt); window._qt = setTimeout(() => { if (!location.hash.startsWith("#/games")) location.hash = "#/games"; else route(); }, 120); });
  // notch / marker tooltips
  document.addEventListener("mousemove", ev => { const n = ev.target.closest?.(".notch"), tip = $("#tip"); if (!n) return tip.style.display = "none"; tip.style.display = "block"; tip.style.left = ev.clientX + 12 + "px"; tip.style.top = ev.clientY + 12 + "px"; tip.innerText = n.dataset.tip; });
  $("#fmtChip").textContent = F.pair(.412, .529); $("#fmtChip").onclick = () => { S.fmt = { multiplier: "percentage", percentage: "precise", precise: "multiplier" }[S.fmt]; save(); $("#fmtChip").textContent = F.pair(.412, .529); route(); };
  api("/api/account").then(a => { $("#bal").textContent = F.usd(+(a.subBalance?.balance ?? a.balance?.data?.balance ?? 0)); }).catch(() => {});
  refreshOpen(); renderSlip(); window.addEventListener("hashchange", route); route(); setInterval(tick, 30000);
  setInterval(() => { if (location.hash.startsWith("#/games") || location.hash === "") { ST.fb = null; route(); } }, 60000);
}
if (document.getElementById("main")) boot();
