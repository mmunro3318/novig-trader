/* Novig Trader UI. Small render functions (one per component) + one state object S.
   Rule: anything with an <input> is built once and then updated in place, so polling never wipes what you typed. */
'use strict';
const $ = s => document.querySelector(s);
const S = {event: null, market: null, mkts: [], book: null, pf: null, games: [], gamesById: {}, sel: null, amt: null, quick: {}, openPos: {},
  f: {q: '', sport: '', status: '', date: 'today', mine: false}, watch: {}, lastOk: Date.now(), mktStale: 0, cash: null, exitAll: 0, trig: [],
  parlay: false, legs: [], oddsHist: {}, prevGame: {}, flash: {}, tl: {}, lastSend: {}, showBook: localStorage.getItem('showBook') == '1'};
S.tz = localStorage.getItem('tz') || Intl.DateTimeFormat().resolvedOptions().timeZone;

// ---------- formatting ----------
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const money = v => v == null ? '–' : (v < 0 ? '-' : '') + '$' + Math.abs(v).toFixed(2);
const sg = v => v == null ? '–' : (v >= 0 ? '+' : '-') + '$' + Math.abs(v).toFixed(2);
const odds = p => p ? (1 / p).toFixed(2) : '–';
const cents = p => p == null ? '–' : (p * 100).toFixed(1) + '¢';
const kq = n => !n ? '' : n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e4 ? Math.round(n / 1e3) + 'k' : n;
const cls = v => v == null ? '' : v >= 0 ? 'up' : 'dn';
function tzName() { try { return new Intl.DateTimeFormat('en-US', {timeZone: S.tz, timeZoneName: 'shortGeneric'}).formatToParts(new Date()).find(p => p.type == 'timeZoneName').value } catch (e) { return S.tz } }
const fmtT = (ts, o = {}) => new Date(ts).toLocaleTimeString([], {timeZone: S.tz, hour: 'numeric', minute: '2-digit', ...o});
const dayKey = ts => new Date(ts).toLocaleDateString('en-CA', {timeZone: S.tz});
const LEAGUE = {NCAAF: 'CFB', NFL: 'NFL', UFC: 'MMA', NCAAB: 'CBB'};
const sportVar = lg => ['NFL', 'NCAAF', 'NBA', 'UFC', 'MMA', 'MLB', 'NHL'].includes(lg) ? `var(--sport-${lg})` : 'var(--sport-other)';

// ---------- network ----------
async function api(path, opt = {}, ms = 6000) {
  const ac = new AbortController(); const t = setTimeout(() => ac.abort(), ms);
  try {
    const r = await fetch(path, {...opt, signal: ac.signal}); const j = await r.json(); S.lastOk = Date.now();
    if (/\/api\/t\/(book|games)/.test(path)) { if (j && (j.stale || j.error == 'rate_limited')) S.mktStale = S.mktStale || Date.now(); else if (j && j.ok !== false) S.mktStale = 0 }
    return j
  } finally { clearTimeout(t) }
}
const post = (path, body, ms = 6000) => api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}, ms);
function err(m) { const e = $('#err'); if (!m) { e.style.display = 'none'; return } e.textContent = m; e.style.display = 'block' }
const idem = () => crypto.randomUUID ? crypto.randomUUID() : Date.now() + '-' + Math.random().toString(36).slice(2);

// ---------- toasts / modal / popover ----------
function toast(html, kind = '', ms = 6000, el = null) {
  el = el || document.createElement('div'); el.className = 'toast ' + kind; el.innerHTML = html;
  if (!el.parentNode) $('#toasts').prepend(el);
  clearTimeout(el._t); if (ms) el._t = setTimeout(() => el.remove(), ms); return el
}
function confirmBox(title, body, yes = 'Confirm') {
  return new Promise(res => { $('#mH').textContent = title; $('#mB').innerHTML = body; $('#mYes').textContent = yes; $('#modal').style.display = 'flex';
    const done = v => { $('#modal').style.display = 'none'; $('#mYes').onclick = $('#mNo').onclick = null; res(v) };
    $('#mYes').onclick = () => done(true); $('#mNo').onclick = () => done(false) })
}
function pop(anchor, html) { const p = $('#pop'); p.innerHTML = html; p.style.display = 'block'; const r = anchor.getBoundingClientRect();
  p.style.left = Math.min(innerWidth - 210, r.left) + 'px'; p.style.top = Math.min(innerHeight - p.offsetHeight - 8, r.bottom + 4) + 'px'; return p }
function unpop() { $('#pop').style.display = 'none' }
document.addEventListener('click', e => { if (!e.target.closest('#pop') && !e.target.closest('[data-pop]')) unpop() });

// ---------- market naming (server stores its own label too; this is for buttons before sending) ----------
function gameOf(eid) { return S.gamesById[eid] }
function vsText(g) { return g ? `${g.away} at ${g.home}` : '' }
function mLabel(m, o, g) {
  if (!m || !o) return '';
  const vs = vsText(g);
  if (m.type == 'MONEY') return `${o.name} to win (${vs})`;
  if (m.type == 'SPREAD') return `${o.name} spread (${vs})`;
  if (m.type == 'TOTAL') return `${o.name} total points (${vs})`;
  if (m.type == 'TEAM_TOTAL') return `${(m.desc || '').replace(/ ?TEAM_TOTAL/, '').replace(/[\d.]+$/, '').trim()} team points ${o.name}`;
  return `${o.name}: ${m.desc || m.type}`
}
// away-left / home-right for any 2-outcome market of a game
function orderSides(outs, g) {
  if (!outs || outs.length != 2) return outs || [];
  const aw = g && g.money && g.money.outcomes && g.money.outcomes[0] && g.money.outcomes[0].name;
  if (/^under/i.test(outs[0].name)) return [outs[1], outs[0]];
  if (aw && outs[1].name.split(' ')[0] == aw) return [outs[1], outs[0]];
  return outs
}

// ---------- selection highlight: the clicked odds badge is cyan, every other badge for the SAME outcome gets a fainter teal ----------
function selectedOids() { return new Set([S.sel, ...Object.values(S.quick)].concat(S.parlay ? S.legs.map(l => l.outcomeId) : []).filter(Boolean)) }
function markTwins() {
  const sel = selectedOids();
  document.querySelectorAll('[data-oid]').forEach(el => { const on = sel.has(el.dataset.oid); el.classList.toggle('twin', on && !el.classList.contains('sel')) })
}

// ---------- positions index ----------
function positions(tradableOnly) { return ((S.pf && S.pf.wallets) || []).filter(w => !tradableOnly || w.tradable).flatMap(w => w.positions.map(p => ({...p, tradable: w.tradable}))) }
function posFor(eid) { return positions().filter(p => p.eventId == eid) }

// ---------- header / hero ----------
async function status() {
  S.status = await api('/api/t/status'); const st = S.status;
  $('#env').textContent = st.env.toUpperCase(); $('#env').className = 'badge ' + (st.env == 'production' ? 'live' : 'paper');
  $('#ord').textContent = 'orders ' + (st.tradable ? 'ON' : 'OFF'); $('#ord').className = 'badge ' + (st.tradable ? 'on' : 'off')
}
function renderHero(w) {
  if (!w) return; const s = w.summary || {}, d = w.day || {};
  $('#hEq').textContent = s.equity != null ? money(s.equity) : (w.cash == null ? 'cash ?' : money(s.equity));
  $('#hEq').dataset.tip = s.equity != null ? `Account value: ${money(w.cash)} cash + ${money(s.openValue)} open (sell-now)` : 'Cash unreadable: ' + (w.cashError || 'unknown') + '. Open positions still shown.';
  $('#hCash').textContent = money(w.cash);
  $('#hOpen').textContent = money(s.openValue); $('#hOpen').dataset.tip = `Open positions value (sell-now) · cost ${money(s.openBasis)} · pays ${money(s.payoutIfAllWin)} if all win`;
  $('#hDay').innerHTML = `<span class="${cls(d.total)}">${sg(d.total)}</span>`;
  $('#hDay').dataset.tip = `Today: realized ${sg(d.realized)} · open ${sg(d.unrealized)} · fees ${money(d.fees)} · loss cap -$${S.pf.cfg.daily_loss_cap_usd}${d.lossCapHit ? ' (HIT: buys ask for a confirm)' : ''}`;
  $('#hDay').style.outline = d.lossCapHit ? '2px solid var(--rd)' : '';
  $('#hWr').textContent = s.winRate == null ? '–%' : (s.winRate * 100).toFixed(1) + '%'; $('#hWr').dataset.tip = `Win rate: ${s.closedAll || 0} closed trades on this wallet`;
  $('#hCnt').textContent = s.openCount ?? '–';
  $('#hExp').innerHTML = `<span class="${cls(s.expReturn)}">≈${sg(s.expReturn)}</span>`;
  $('#hExp').dataset.tip = `Est. return if all held to the end: expected payout ${money(s.expValue)} (win chance × payout) minus cost ${money(s.openBasis)}`;
  $('#hTot').innerHTML = `<span class="${cls(s.totalPnl)}">${sg(s.totalPnl)}</span>`; $('#hTot').dataset.tip = `Total P&L: realized ${sg(s.realizedAll)} all time + open`;
}

// ---------- games list ----------
async function loadGames() {
  try {
    const g = await api('/api/t/games'); if (!g.games) return false;
    detectFlashes(g.games); S.games = g.games; S.gamesById = Object.fromEntries(g.games.map(x => [x.eventId, x])); drawSports(); drawGames();
    if (S.event) drawTimeline(); return !g.stale
  } catch (e) { return false }
}
function drawSports() {
  const lgs = [...new Set(S.games.map(g => g.league))];
  $('#fSport').innerHTML = [['', 'All']].concat(lgs.map(l => [l, LEAGUE[l] || l])).map(([v, n]) =>
    `<button class="pill ${S.f.sport == v ? 'on' : ''}" onclick="S.f.sport='${v}';drawSports();drawGames()">${v ? `<span class="dot" style="background:${sportVar(v)}"></span>` : ''}${n}</button>`).join('')
}
function gameFilter(g) {
  const f = S.f, today = dayKey(Date.now()), tmr = dayKey(Date.now() + 86400000), dk = dayKey(g.startsTs);
  if (f.q && !g.desc.toLowerCase().includes(f.q.toLowerCase())) return false;
  if (f.sport && g.league != f.sport) return false;
  if (f.status && g.phase != f.status) return false;
  if (f.date == 'today' && dk != today && g.phase != 'live') return false;
  if (f.date == 'tomorrow' && dk != tmr) return false;
  if (f.mine && !posFor(g.eventId).length) return false;
  return true
}
function drawGames() {
  const list = S.games.filter(gameFilter), today = dayKey(Date.now());
  const sec = {mine: [], today: [], later: [], past: []};
  for (const g of list) {
    if (g.phase == 'past') sec.past.push(g);
    else if (posFor(g.eventId).length) sec.mine.push(g);
    else if (dayKey(g.startsTs) == today || g.phase == 'live') sec.today.push(g);
    else sec.later.push(g)
  }
  const T = {mine: 'Today · your positions', today: 'Today', later: 'Later', past: 'Past'};
  $('#tzLab').textContent = 'times in ' + tzName();
  if (S.showPast == null) S.showPast = !matchMedia('(max-width:1000px)').matches;   // phone: past games folded so the ticket stays close
  $('#glist').innerHTML = Object.entries(sec).filter(([, v]) => v.length).map(([k, v]) => k == 'past'
    ? `<div class="sect" style="cursor:pointer" onclick="S.showPast=!S.showPast;drawGames()">${T[k]} (${v.length}) ${S.showPast ? '▾' : '▸ show'}</div>` + (S.showPast ? v.map(gameCard).join('') : '')
    : `<div class="sect">${T[k]} (${v.length})</div>` + v.map(gameCard).join('')).join('')
    || '<div class="sect">no games match</div>';
  markTwins()
}
function scoreline(g) {
  const c = g.clock, a = c && c.away, h = c && c.home, st = c && c.situation, ball = '🏈';
  if (!c || c.state == 'pre') return `<span class="scoreline"><span class="tk">${esc(a ? a.abbr : g.away)}</span> <span class="mut">vs</span> <span class="tk">${esc(h ? h.abbr : g.home)}</span></span>`;
  const pa = st && st.poss == 'away', ph = st && st.poss == 'home';
  return `<span class="scoreline num">${pa ? `<span class="ball">${ball}</span> ` : ''}<span class="tk">${esc(a.abbr)}</span> <span class="sc">${esc(a.score)}</span><span class="mut"> - </span><span class="sc">${esc(h.score)}</span> <span class="tk">${esc(h.abbr)}</span>${ph ? ` <span class="ball">${ball}</span>` : ''}</span>`
}
// score / turnover flashes: compare each live game with the last poll
const TURNOVER_RX = /intercept|fumble.*recovered by|turnover on downs|blocked|safety/i;
function detectFlashes(games) {
  for (const g of games) {
    const c = g.clock; if (!c || c.state != 'in') continue;
    const p = S.prevGame[g.eventId], sa = +(c.away || {}).score || 0, sh = +(c.home || {}).score || 0, poss = c.situation && c.situation.poss, lp = (c.situation && c.situation.lastPlay) || '';
    if (p) {
      if (sa != p.sa || sh != p.sh) { const who = sa != p.sa ? c.away.abbr : c.home.abbr, d = sa != p.sa ? sa - p.sa : sh - p.sh; S.flash[g.eventId] = {kind: 'score', text: `${who} +${d}`, until: Date.now() + 9000} }
      else if (poss && p.poss && poss != p.poss && TURNOVER_RX.test(lp)) S.flash[g.eventId] = {kind: 'turnover', text: 'TURNOVER', until: Date.now() + 9000}
    }
    S.prevGame[g.eventId] = {sa, sh, poss}
  }
}
function clockText(g) {
  const c = g.clock;
  if (g.phase == 'past') return 'Final';
  if (c && c.state == 'in') return esc((c.detail || '').replace(' - ', ' · '));
  if (g.phase == 'live') return 'LIVE';
  const d = dayKey(g.startsTs) == dayKey(Date.now()) ? '' : new Date(g.startsTs).toLocaleDateString([], {timeZone: S.tz, weekday: 'short'}) + ' ';
  return d + fmtT(g.startsTs) + ' ' + tzName()
}
function situText(g) {
  const st = g.clock && g.clock.situation; if (!st) return '';
  const who = st.poss == 'away' ? g.clock.away.abbr : g.clock.home.abbr;
  return `<div class="situ ${st.redZone ? 'rz' : ''}">${esc(who)} ball · ${esc(st.down || '')}${st.toGoal != null ? ` · <b>${st.toGoal} yd${st.toGoal == 1 ? "" : "s"}</b> to end zone` : ''}${st.redZone ? ' · RED ZONE' : ''}</div>`
}
function gameCard(g) {
  const m = g.money, ps = posFor(g.eventId), tps = ps.filter(p => p.tradable), live = g.phase == 'live', off = !(S.status && S.status.tradable);
  const q = S.quick[g.eventId], qo = m && m.outcomes.find(o => o.outcomeId == q), amt = S.amt || 1;
  const ob = (o, r) => o ? `<button class="oddbtn ${r ? 'r' : ''} ${q == o.outcomeId ? 'sel' : ''}" data-oid="${o.outcomeId}" ${!o.ask ? 'disabled' : ''} onclick="event.stopPropagation();quickPick('${g.eventId}','${o.outcomeId}')" data-tip="${esc(o.name)} to win · buy at ${cents(o.ask)}"><span class="nm">${esc(o.name)}</span><span class="odds num">${odds(o.ask)}</span></button>` : '<span></span>';
  const quick = g.phase == 'past' || !m ? '' : `<div class="quick">${ob(m.outcomes[0])}
    <button class="mini buy ${qo ? 'armed' : ''}" ${!qo || off ? 'disabled' : ''} onclick="event.stopPropagation();quickBuy(this,'${g.eventId}')" data-tip="${qo ? `Buy $${amt} of ${esc(qo.name)} to win` : 'Pick a team first'}">${qo ? `BUY $${amt}` : 'BUY'}</button>
    <span style="display:flex"><button class="mini sell" ${!tps.length ? 'disabled' : ''} onclick="event.stopPropagation();quickSell(this,'${g.eventId}')" data-tip="${tps.length ? 'Sell all' : 'No position to sell'}">SELL</button><button class="mini sell" data-pop="1" style="padding:5px 5px;margin-left:1px" ${!tps.length ? 'disabled' : ''} onclick="event.stopPropagation();sellMenu(this,'${g.eventId}')">▾</button></span>
    ${ob(m.outcomes[1], true)}</div>`;
  const prow = ps.map(p => { const k = p.marketId + p.sideId, open = S.openPos[k];
    return `<div class="posrow num" onclick="event.stopPropagation();S.openPos['${k}']=!S.openPos['${k}'];drawGames()">
      <span class="stake" data-tip="Cost incl. fees">${money(p.basis)}</span><span class="avg" data-tip="Avg odds you bought at">${p.avg ? odds(p.avg) : '–'}</span>
      <span class="pay" data-tip="Pays if it wins">${money(p.payout)}</span><span class="mut" style="font-size:11px">${esc(p.side)}${p.type != 'MONEY' ? ' ' + esc(p.type.toLowerCase()) : ''}${p.tradable ? '' : ' · app'}${p.state == 'settling' ? ' · <b class="yl">settling</b>' : ''}</span>
      <span class="exp">${open ? '▲' : '▼'}</span></div>
      ${open ? `<div class="posdetail">${p.state == 'settling' ? `game over: settling, pays ${money(p.payout)} if ${esc(p.side)} won` : `cash out ${money(p.cashOut)} <span class="${cls(p.pnl)}">(${sg(p.pnl)})</span> · now ${odds(p.bid)} · win chance ${p.winProb ? (p.winProb * 100).toFixed(0) + '%' : '–'}`}</div>` : ''}` }).join('');
  const fl = S.flash[g.eventId] && S.flash[g.eventId].until > Date.now() ? S.flash[g.eventId] : null;
  return `<div class="card ${S.event == g.eventId ? 'sel' : ''} ${g.phase == 'past' ? 'past' : ''} ${ps.length ? 'mine' : ''} ${fl ? 'flash-' + fl.kind : ''}" style="--sport:${sportVar(g.league)}" onclick="pickEvent('${g.eventId}')">
    ${fl ? `<span class="flashtag ${fl.kind}">${esc(fl.text)}</span>` : ''}
    <div class="strip"><span>${LEAGUE[g.league] || esc(g.league)}</span></div><div class="body">
    ${live ? `<span class="livetag ${g.clock && g.clock.late ? 'late' : ''}">${g.clock && g.clock.late ? 'Q4 ≤5:00' : 'LIVE'}</span>` : ''}
    <div class="ttl" title="${esc(g.desc)} (away @ home)">${esc(g.away)} <span class="mut">@</span> ${esc(g.home)}<span class="hometag">HOME</span></div>
    <div class="meta"><span class="clock">${clockText(g)}</span>${scoreline(g)}</div>${situText(g)}${quick}${prow}</div></div>`
}
function quickPick(eid, oid) {
  const g = gameOf(eid), m = g && g.money;
  if (S.parlay && m) { const o = m.outcomes.find(x => x.outcomeId == oid); if (o) toggleLeg(m, o, g); return }
  S.quick[eid] = S.quick[eid] == oid ? null : oid; drawGames(); markTwins()
}
function quickBuy(btn, eid) {
  const g = gameOf(eid), m = g && g.money, o = m && m.outcomes.find(x => x.outcomeId == S.quick[eid]); if (!o) return;
  sendOrder(btn, {action: 'BUY', marketId: m.marketId, outcomeId: o.outcomeId, usd: S.amt || 1, eventDesc: g.desc}, mLabel(m, o, g)).then(() => { S.quick[eid] = null; drawGames() })
}
function quickSell(btn, eid) { const ps = posFor(eid).filter(p => p.tradable); if (ps.length == 1) return sellPos(btn, ps[0], 'SELL_ALL'); sellMenu(btn, eid) }
function sellMenu(btn, eid) {
  const ps = posFor(eid).filter(p => p.tradable); if (!ps.length) return;
  pop(btn, ps.map((p, i) => `<div class="mut" style="font-size:11px;margin-top:${i ? 8 : 0}px">${esc(posLabel(p))} · ${money(p.value)}</div>
    <button class="btn s" onclick="sellPosIdx(this,'${eid}',${i},'SELL_ALL')">Sell all</button><button class="btn h" onclick="sellPosIdx(this,'${eid}',${i},'SELL_HALF')">Sell half</button>
    <div style="display:flex;gap:4px"><input id="sn-${i}" type="text" inputmode="decimal" placeholder="$" style="width:70px"><button class="btn h" style="flex:1" onclick="sellPosIdx(this,'${eid}',${i},'SELL_USD')">Sell $N</button></div>`).join(''))
}
function sellPosIdx(btn, eid, i, act) { const p = posFor(eid).filter(p => p.tradable)[i]; if (!p) return; sellPos(btn, p, act, act == 'SELL_USD' ? parseFloat(($('#sn-' + i) || {}).value) : null) }

// ---------- market grid (organized rows) ----------
async function pickEvent(eid) {
  const g = gameOf(eid); if (!g) return;
  if (S.event != eid) { S.event = eid; S.market = g.money ? g.money.marketId : null; S.sel = null; S.mkts = []; S.book = null; $('#ticket').innerHTML = ''; $('#mgrid').innerHTML = '<div class="sect">loading markets…</div>' }
  if (!location.hash.includes(eid)) history.replaceState(null, '', '#e=' + eid); $('#mtitle').textContent = `${g.away} @ ${g.home}`; drawGames();
  await loadEvent(); loadBook(); loadTimeline()
}
async function loadEvent() {
  if (!S.event || (gameOf(S.event) || {}).phase == 'past') { if (S.event) $('#mgrid').innerHTML = '<div class="sect">game is over</div>'; return true }
  try { const r = await api('/api/t/event/' + S.event); S.mkts = r.markets || []; if (!S.market && S.mkts.length) S.market = S.mkts[0].marketId; drawMkts(); return true } catch (e) { return false }
}
const fstrike = s => { const v = parseFloat(s); return isNaN(v) ? '' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v) };
function drawMkts() {
  const g = gameOf(S.event), rows = [], by = t => S.mkts.filter(m => m.type == t), num = m => parseFloat(m.strike) || 0;
  const isSel = (m, o) => S.parlay ? S.legs.some(l => l.outcomeId == (o && o.outcomeId)) : m.marketId == S.market && (!S.sel || !o || S.sel == o.outcomeId || m.type != 'MONEY');
  const chip = (m, txt, o) => `<button class="chip-m ${isSel(m, o) ? 'sel' : ''} ${o && o.ask ? '' : 'dead'}" ${o ? `data-oid="${o.outcomeId}"` : ''} onclick="pickChip('${m.marketId}','${o ? o.outcomeId : ''}')" title="${esc(mLabel(m, o, g))}"><b>${txt}</b><i>${o ? odds(o.ask) : ''}</i></button>`;
  const money = by('MONEY')[0];
  if (money) { const os = orderSides(money.outcomes, g); rows.push(['WINNER', os.map(o => chip(money, esc(o.name), o)).join('').replace(/onclick="pickMarket\('([^']+)'\)"/g, (x) => x)]) }
  const sp = by('SPREAD');
  if (sp.length) {
    const team = sp[0].outcomes[0].name.split(' ')[0], o0 = m => m.outcomes[0];
    const neg = sp.filter(m => num(m) < 0).sort((a, b) => num(a) - num(b)), pos = sp.filter(m => num(m) > 0).sort((a, b) => num(a) - num(b));
    if (neg.length) rows.push([`SPREAD ${esc(team)} −`, neg.map(m => chip(m, fstrike(m.strike), o0(m))).join('')]);
    if (pos.length) rows.push([`SPREAD ${esc(team)} +`, pos.map(m => chip(m, fstrike(m.strike), o0(m))).join('')]);
  }
  const tot = by('TOTAL').sort((a, b) => num(a) - num(b));
  if (tot.length) rows.push(['TOTAL (over)', tot.map(m => chip(m, num(m), m.outcomes.find(o => /^over/i.test(o.name)) || m.outcomes[0])).join('')]);
  const tt = {}; by('TEAM_TOTAL').forEach(m => { const t = (m.desc || '').replace(/ ?TEAM_TOTAL/, '').replace(/[\d.]+\s*$/, '').trim(); (tt[t] = tt[t] || []).push(m) });
  Object.entries(tt).forEach(([t, ms]) => rows.push([`${esc(t.split(' ').pop().toUpperCase())} PTS (over)`, ms.sort((a, b) => num(a) - num(b)).map(m => chip(m, num(m), m.outcomes.find(o => /^over/i.test(o.name)))).join('')]));
  const other = S.mkts.filter(m => !['MONEY', 'SPREAD', 'TOTAL', 'TEAM_TOTAL'].includes(m.type));
  if (other.length) rows.push(['OTHER', other.map(m => chip(m, esc(m.type), m.outcomes[0])).join('')]);
  $('#mgrid').innerHTML = rows.length ? `<div class="mgrid">${rows.map(([l, c]) => `<div class="lab">${l}</div><div class="chips">${c}</div>`).join('')}</div>` : '<div class="sect">no open markets</div>';
  markTwins()
}
function pickMarket(mid) { if (S.market == mid) return; S.market = mid; S.sel = null; S.book = null; $('#ticket').innerHTML = ''; drawMkts(); loadBook() }
// clicking an odds chip picks that market AND that side (in parlay mode it adds / removes a leg instead)
function pickChip(mid, oid) {
  const m = S.mkts.find(x => x.marketId == mid), o = m && m.outcomes.find(x => x.outcomeId == oid), g = gameOf(S.event);
  if (S.parlay && m && o) return toggleLeg(m, o, g);
  if (S.market != mid) { S.market = mid; S.book = null; $('#ticket').innerHTML = ''; S.sel = oid || null; drawMkts(); loadBook(); return }
  S.sel = oid || S.sel; drawMkts(); updateTicket()
}

// ---------- ticket (built once per market, updated in place) ----------
function sideBox(o, g, b, sides) {
  return `<div class="side" id="sd-${o.outcomeId}" data-oid="${o.outcomeId}" onclick="pickSide('${o.outcomeId}')">
      <div class="nm">${esc(o.name)} ${o.homeAway == 'home' || (g && g.home && sides[1] == o && b.type != 'TOTAL') ? '<span class="hometag">HOME</span>' : ''}</div>
      <div class="big num" id="od-${o.outcomeId}">–</div><div class="ba num" id="ab-${o.outcomeId}"></div>
      <div class="mine num" id="my-${o.outcomeId}"></div>
      <div class="liq num" id="lq-${o.outcomeId}"></div>
      <table class="depth num ${S.showBook ? '' : 'hidden'}"><thead><tr><th>bid</th><th>ctr</th><th>ask</th><th>ctr</th></tr></thead><tbody id="dp-${o.outcomeId}"></tbody></table></div>`
}
function buildTicket(b) {
  const g = gameOf(S.event), off = !(S.status && S.status.tradable), sides = orderSides(b.outcomes, g);
  S.ticketFor = b.marketId; S.ticketSides = sides.map(o => o.outcomeId);
  $('#ticket').innerHTML = `<div class="ticket">
    <div class="sides3">${sideBox(sides[0], g, b, sides)}<div class="tl" id="tl"></div>${sides[1] ? sideBox(sides[1], g, b, sides) : ''}</div>
    <div class="amt">${[1, 2, 5, 10].map(u => `<button class="preset" data-u="${u}" onclick="setAmt(${u})">$${u}</button>`).join('')}
      <input id="amtIn" type="text" inputmode="decimal" autocomplete="off" placeholder="$ amount" oninput="setAmt(this.value,true)">
      <div class="gobar"><div id="slipLegs" class="legs hidden"></div><button class="go" id="goBtn" ${off ? 'disabled' : ''} onclick="ticketBuy(this)">Pick a side</button>
        <label class="plz ${S.parlay ? 'on' : ''}" id="plzLab" data-tip="Parlay: click odds anywhere to add legs"><input type="checkbox" id="plz" ${S.parlay ? 'checked' : ''} onchange="setParlay(this.checked)"> PARLAY</label></div></div>
    <div id="tWarn"></div>
    <div class="stubs">
      <div class="stub"><div class="sh">Game data <span class="mut">· money waiting on Novig's book</span></div><div id="gdata" class="num"></div>
        <label class="mut tgl"><input type="checkbox" ${S.showBook ? 'checked' : ''} onchange="toggleBook(this.checked)"> show full order book (price · contracts)</label></div>
      <div class="stub"><div class="sh">Key events <span class="mut">· injuries, ejections, ref calls</span></div>
        <select disabled style="width:100%;margin-top:4px"><option>Injuries &amp; news by team: not built yet (backlog)</option></select>
        <div class="mut" style="font-size:11.5px;margin-top:4px">Planned: critical list first (out / injured in-game), then the roster as <code>name F/L - Role - {status}</code>.</div></div>
    </div>
    <details class="adv" id="adv"><summary><span class="advbtn">🎯 Advanced order ▾</span> <span class="mut">buy/sell at a target odds or profit (watched by the app, not posted on Novig's book)</span></summary>
      <div class="trow">When
        <select id="tAct"><option value="BUY">buy $ amount</option><option value="SELL_ALL">sell all</option><option value="SELL_HALF">sell half</option><option value="SELL_USD">sell $ amount</option></select>
        of <b id="tSide">(pick a side)</b>
        <select id="tCond"><option value="odds_gte">odds ≥</option><option value="odds_lte">odds ≤</option><option value="profit_pct_gte">profit ≥ %</option><option value="profit_pct_lte">loss ≥ % (stop)</option></select>
        <input id="tTarget" type="text" inputmode="decimal" placeholder="e.g. 3.0" style="width:70px">
        <input id="tUsd" type="text" inputmode="decimal" placeholder="$" style="width:56px" title="$ amount (buy / sell $)">
        for <select id="tHrs"><option>1</option><option>3</option><option selected>6</option><option>12</option></select>h
        <button class="btn" onclick="armTrigger(this)">Arm</button></div>
      <div class="mut" style="font-size:11.5px;margin-top:4px">Checked every ~2s while the server runs. When hit, it sends one normal order (same slippage cap) and disarms. Buy odds use the ask, sell odds use what selling gets now. Trailing stops and compound rules are next.</div>
      <div id="tList"></div></details>
    <div class="mut" style="padding-top:8px" id="tNote"></div></div>`;
  const hs = location.hash.match(/side=(\d)/), ha = location.hash.match(/amt=([\d.]+)/);   // deep link: #e=<event>&side=0|1&amt=5 preselects (never sends)
  if (hs && !S.sel && !S.hashUsed) { S.sel = S.ticketSides[+hs[1]]; S.hashUsed = 1 } if (ha && !S.amt) S.amt = +ha[1];
  if (S.amt) { $('#amtIn').value = S.amt; markPresets() }
  drawTriggers(); drawLegs(); drawTimeline(); drawMkts()
}
function toggleBook(on) { S.showBook = on; localStorage.setItem('showBook', on ? '1' : '0'); document.querySelectorAll('.depth').forEach(t => t.classList.toggle('hidden', !on)) }
const kmoney = v => v == null ? '–' : v >= 1e6 ? '$' + (v / 1e6).toFixed(1) + 'M' : v >= 1e4 ? '$' + Math.round(v / 1e3) + 'k' : money(v);
const usdAt = lv => (lv || []).reduce((a, [p, q]) => a + p * q / 100, 0);
function pickSide(oid) {
  const b = S.book, o = b && b.outcomes.find(x => x.outcomeId == oid);
  if (S.parlay && o) return toggleLeg(b, o, gameOf(S.event));
  S.sel = oid; updateTicket(); drawMkts()
}
function markPresets() { document.querySelectorAll('.preset').forEach(b => b.classList.toggle('on', +b.dataset.u == S.amt)) }
function setAmt(v, typed) { const n = parseFloat(String(v).replace(/[^\d.]/g, '')); S.amt = n > 0 ? Math.round(n * 100) / 100 : null; if (!typed) { const i = $('#amtIn'); if (i) i.value = S.amt || '' } markPresets(); updateTicket(); drawGames() }
function updateTicket() {
  const b = S.book; if (!b || S.ticketFor != b.marketId) return;
  const g = gameOf(S.event);
  for (const o of b.outcomes) {
    const od = $('#od-' + o.outcomeId); if (!od) continue;
    od.textContent = odds(o.ask); $('#ab-' + o.outcomeId).innerHTML = `<span>buy ${cents(o.ask)}</span><span>sell ${cents(o.bid)}</span><span>last ${o.last ? cents(+o.last) : '–'}</span>`;
    $('#dp-' + o.outcomeId).innerHTML = [0, 1, 2, 3, 4].map(i => { const bb = o.bids[i] || [], aa = o.asks[i] || []; return `<tr><td class="b">${bb[0] != null ? cents(bb[0]) : ''}</td><td>${kq(bb[1])}</td><td class="a">${aa[0] != null ? cents(aa[0]) : ''}</td><td>${kq(aa[1])}</td></tr>` }).join('');
    const p = positions().find(x => x.marketId == b.marketId && x.sideId == o.outcomeId);
    $('#my-' + o.outcomeId).innerHTML = p ? `<span data-tip="What you paid (before fees) and what selling now would pay you">you: ${money(p.stake ?? p.basis)} @ <b class="odds">${odds(p.entryPrice || p.avg)}</b> → ${p.state == 'settling' ? 'settling' : money(p.cashOut)}</span>` : '';
    $('#lq-' + o.outcomeId).innerHTML = `<span data-tip="Dollars resting on Novig's book to BUY ${esc(o.name)} (top levels)">bids ${kmoney(usdAt(o.bids))}</span>`;
    const inLeg = S.parlay && S.legs.some(l => l.outcomeId == o.outcomeId);
    $('#sd-' + o.outcomeId).classList.toggle('sel', S.parlay ? inLeg : S.sel == o.outcomeId)
  }
  const tb = b.outcomes.map(o => usdAt(o.bids)), tot = tb.reduce((a, x) => a + x, 0);
  $('#gdata').innerHTML = b.outcomes.length == 2 ? `<div class="lbar"><span style="width:${tot ? Math.max(18, Math.min(82, tb[0] / tot * 100)).toFixed(0) : 50}%">${esc(b.outcomes[0].name)} ${kmoney(tb[0])}</span><span>${esc(b.outcomes[1].name)} ${kmoney(tb[1])}</span></div>
    <div class="mut" style="font-size:11.5px">matched so far on this market: ${b.volume != null ? kq(Math.round(b.volume)) + ' ctr' : '–'} · split of bets placed per side isn't published by Novig</div>` : '';
  const o = b.outcomes.find(x => x.outcomeId == S.sel), go = $('#goBtn'), off = !(S.status && S.status.tradable);
  if (!go.classList.contains('pend')) {
    if (S.parlay) { go.disabled = S.legs.length < 2 || !S.amt; go.textContent = S.legs.length < 2 ? 'Click 2+ odds to build a parlay' : !S.amt ? 'Pick or type an amount' : `Review ${S.legs.length}-leg parlay · $${S.amt} @ ~${parlayOdds().toFixed(2)}` }
    else {
      go.disabled = off || !o || !S.amt || !o.ask;
      go.textContent = off ? 'Orders are OFF in this mode' : !o ? 'Pick a side above' : !S.amt ? 'Pick or type an amount' : !o.ask ? 'No offers on this side' : `BUY $${S.amt} · ${mLabel(b, o, g)} @ ${odds(o.ask)}`
    }
  }
  markTwins();
  $('#tSide').textContent = o ? mLabel(b, o, g) : '(pick a side)';
  $('#tWarn').innerHTML = o && S.amt ? buyWarnLine(o, S.amt) : '';
  $('#tNote').innerHTML = `Buy = IOC limit at ask + max slip (never worse). Fee ≈ 6%·p·(1−p) per contract in-game. ${b.status != 'OPEN' ? '<b class="dn">market ' + b.status + '</b>' : ''}${b.stale ? ' <b class="dn">prices ' + b.staleAge + 's old (rate limited)</b>' : ''}`
}
async function loadBook() {
  if (!S.market) return true;
  try {
    const b = await api('/api/t/book/' + S.market, {}, 4000); if (b.marketId != S.market) return !!b.outcomes && !b.stale;
    S.book = b; if (S.ticketFor != b.marketId || !$('#goBtn')) buildTicket(b); updateTicket(); return !b.stale
  } catch (e) { return false }
}
function ticketBuy(btn) {
  if (S.parlay) return reviewParlay();
  const b = S.book, o = b && b.outcomes.find(x => x.outcomeId == S.sel), g = gameOf(S.event); if (!o || !S.amt) return;
  sendOrder(btn, {action: 'BUY', marketId: b.marketId, outcomeId: o.outcomeId, usd: S.amt, eventDesc: g && g.desc}, mLabel(b, o, g))
}
// ---------- parlay slip (planning only: Novig's trading API has no parlay order; parlays are priced by RFQ inside the Novig app) ----------
function setParlay(on) { S.parlay = on; const l = $('#plzLab'), c = $('#plz'); if (l) l.classList.toggle('on', on); if (c) c.checked = on; drawLegs(); drawMkts(); drawGames(); updateTicket() }
function toggleLeg(m, o, g) {
  const i = S.legs.findIndex(l => l.marketId == m.marketId);
  if (i >= 0 && S.legs[i].outcomeId == o.outcomeId) S.legs.splice(i, 1);
  else { const leg = {marketId: m.marketId, outcomeId: o.outcomeId, short: m.type == 'MONEY' ? o.name : m.type == 'SPREAD' ? `${o.name.split(' ')[0]} ${fstrike(m.strike)}` : `${m.type == 'TEAM_TOTAL' ? (m.desc || '').replace(/ ?TEAM_TOTAL/, '').replace(/[\d.]+\s*$/, '').trim().split(' ').pop() + ' ' : ''}${/^under/i.test(o.name) ? 'U' : 'O'} ${parseFloat(m.strike) || ''}`.trim(), label: mLabel(m, o, g), ask: o.ask, game: g ? `${g.away} @ ${g.home}` : ''};
    if (i >= 0) S.legs[i] = leg; else S.legs.push(leg) }
  drawLegs(); drawMkts(); drawGames(); updateTicket()
}
function parlayOdds() { return S.legs.reduce((a, l) => a * (l.ask ? 1 / l.ask : 1), 1) }
function drawLegs() {
  const el = $('#slipLegs'); if (!el) return; el.classList.toggle('hidden', !S.parlay || !S.legs.length);
  el.innerHTML = S.legs.map((l, i) => `<span class="leg" data-oid="${l.outcomeId}" title="${esc(l.label)}"><b>${esc(l.short)}</b><i class="num">${odds(l.ask)}</i><button onclick="S.legs.splice(${i},1);drawLegs();drawMkts();drawGames();updateTicket()" title="remove leg">×</button></span>`).join('')
}
async function reviewParlay() {
  if (S.legs.length < 2 || !S.amt) return; const o = parlayOdds(), same = new Set(S.legs.map(l => l.game)).size < S.legs.length;
  const txt = S.legs.map(l => `${l.label} @ ${odds(l.ask)}`).join('\n');
  const ok = await confirmBox(`Parlay · ${S.legs.length} legs`, `<div class="num">${S.legs.map(l => `<div>• ${esc(l.label)} <b class="odds">${odds(l.ask)}</b></div>`).join('')}</div>
    <p class="num">$${S.amt} at ~<b class="odds">${o.toFixed(2)}</b> pays ~<b>${money(S.amt * o)}</b> if every leg wins.</p>
    ${same ? '<p class="cw">Two or more legs are from the same game, so they move together: Novig will price this lower than the simple product shown.</p>' : ''}
    <p class="mut">Novig's trading API can't place parlays (they're priced by quote inside the Novig app), so this app won't send it. Copy the slip and place it in the Novig app.</p>`, 'Copy slip');
  if (ok) { try { await navigator.clipboard.writeText(txt + `\n$${S.amt} @ ~${o.toFixed(2)}`); toast('Parlay slip copied', 'ok') } catch (e) { toast('Copy failed: select the legs by hand', 'warn') } }
}

// ---------- game timeline (left = start, right = end of Q4) + field position (left = own goal line, right = the end zone they attack) ----------
const TL_TYPES = new Set(['TD', 'FG', 'FG_MISS', 'INT', 'PICK_SIX', 'FUMBLE_LOST', 'SAFETY', 'TURNOVER_DOWNS', 'BLOCKED', 'PENALTY_BIG', 'INJURY', 'TIMEOUT', 'CHALLENGE']);
const BIG_TYPES = new Set(['TD', 'PICK_SIX', 'INT', 'FUMBLE_LOST', 'SAFETY', 'TURNOVER_DOWNS', 'BLOCKED']);
function gameMin(period, clock) { const [m, s] = String(clock || '15:00').split(':').map(Number); return Math.min(60, (Math.max(1, period || 1) - 1) * 15 + (15 - (m + (s || 0) / 60))) }
async function loadTimeline() {
  const g = gameOf(S.event), c = g && g.clock; if (!c || !c.espnId || c.state == 'pre') return true;
  const k = c.espnId; if (S.tl[k] && Date.now() - S.tl[k].t < 20000) return true;
  try { const d = await api(`/api/pbp/game/${k}?league=${c.league || g.league}`, {}, 8000); if (d && d.events) { S.tl[k] = {t: Date.now(), d}; drawTimeline() } } catch (e) {}
  return true
}
// team colour if it shows up on the dark background and the two teams differ; else cyan (away) / bisque (home)
function lum(hex) { const m = /^#?([\da-f]{6})$/i.exec(hex || ''); if (!m) return 0; const n = parseInt(m[1], 16); return (0.299 * (n >> 16) + 0.587 * (n >> 8 & 255) + 0.114 * (n & 255)) / 255 }
function teamCol(d, side) {
  const fb = side == 'away' ? '#22d3ee' : '#ffc89a'; if (!d || !d.away || !d.home) return fb;
  const a = d.away.color, h = d.home.color, ok = c => lum(c) > 0.35;
  if (!ok(a) || !ok(h) || Math.abs(lum(a) - lum(h)) < 0.08) return fb;
  return side == 'away' ? a : h
}
function drawTimeline() {
  const el = $('#tl'); if (!el) return; const g = gameOf(S.event), c = g && g.clock;
  const st = c && c.situation, live = c && c.state == 'in', d = c && c.espnId && S.tl[c.espnId] && S.tl[c.espnId].d;
  const now = live ? gameMin(c.period, c.clock) : c && c.state == 'post' ? 60 : 0;
  const col = side => teamCol(d, side);
  const abbrSide = ab => d && d.home.abbr == ab ? 'home' : 'away';
  const marks = (d ? d.events : []).filter(e => TL_TYPES.has(e.type)).map(e => {
    const x = gameMin(e.period, e.clock) / 60 * 100, sd = abbrSide(e.team);
    return `<i class="ev ${BIG_TYPES.has(e.type) ? 'big' : ''}" style="left:${x.toFixed(1)}%;background:${col(sd)}" data-tip="${esc(e.label)} · ${esc(e.team || '')} · Q${e.period} ${esc(e.clock)}"></i>` }).join('');
  const down = st ? (st.down || '') : '', poss = st && st.poss, pc = poss ? col(poss) : '#888';
  const yl = st && st.toGoal != null ? 100 - st.toGoal : null, who = poss ? c[poss].abbr : '';
  const fieldTxt = yl == null ? '' : yl < 50 ? `own ${yl}` : yl == 50 ? 'midfield' : `opp ${100 - yl}`;
  el.innerHTML = `<div class="tlh">${live && down ? `<span class="dd">${esc(down)}</span>` : `<span class="mut">${c && c.state == 'pre' ? 'kickoff ' + clockText(g) : c ? esc(c.detail || '') : 'no game clock'}</span>`}</div>
    <div class="tbar">${['Q1', 'Q2', 'Q3', 'Q4'].map((q, i) => `<span class="ql" style="left:${i * 25 + 12.5}%">${q}</span>`).join('')}
      <i class="qline" style="left:25%"></i><i class="qline half" style="left:50%"></i><i class="qline" style="left:75%"></i>${marks}
      ${live || (c && c.state == 'post') ? `<i class="nowm" style="left:${(now / 60 * 100).toFixed(1)}%" data-tip="now: ${esc(c.detail || '')}"></i>` : ''}</div>
    <div class="fbar" data-tip="Field position of the team with the ball: left = their own goal line, right = the end zone they're attacking">
      <i class="fl" style="left:50%"></i><i class="fl rz" style="left:80%"></i>
      ${yl != null ? `<i class="ballm" style="left:${yl}%;background:${pc}"></i><span class="yd" style="left:${yl}%">${esc(who)} ${esc(fieldTxt)}</span>` : ''}</div>
    <div class="fscale mut"><span>0</span><span>50</span><span>100</span></div>
    ${d ? `<div class="tleg mut"><span><i style="background:${col('away')}"></i>${esc(d.away.abbr)}</span><span><i style="background:${col('home')}"></i>${esc(d.home.abbr)}</span><span>tall = turnover / TD</span></div>` : ''}`
}

// cash check: exits are buys of the other side and need cash up front. Warning only.
// fee per contract = coef * p * (1 - p) (coef 0.06), so a $u buy at price a costs about coef * (1 - a) * u in fees; in-game only by default
function feeCoef() { const c = (S.pf && S.pf.cfg) || (S.status && S.status.cfg) || {}; return c.fee_mode == 'off' ? 0 : (c.fee_coef || 0.06) }
function cashAfter(o, u) { if (S.cash == null || !o.ask) return null; const a = o.ask, bd = o.bid || Math.max(0.01, a - 0.03), k = feeCoef();
  return {left: S.cash - u - k * (1 - a) * u, need: (S.exitAll || 0) + (u / a) * (1 - bd) * (1 + k * bd)} }
function buyWarnLine(o, u) { const r = cashAfter(o, u); if (!r || r.left >= r.need) return '';
  return `<div class="cw"><b>Cash warning:</b> after this $${u} buy you'd have ~$${Math.max(0, r.left).toFixed(2)} cash; selling everything at once would need ~$${r.need.toFixed(2)}. You can still buy; sells will go out in chunks.</div>` }

// ---------- sending orders (immediate feedback, confirms only where they matter) ----------
async function sendOrder(btn, body, label) {
  if (btn && btn.classList.contains('pend')) return;
  const sig = [body.action, body.marketId, body.outcomeId, body.usd, body.pct, body.qty].join('|');
  if (Date.now() - (S.lastSend[sig] || 0) < 1500) { toast('Double click ignored (same order 1s ago)', 'warn', 3000); return }
  S.lastSend[sig] = Date.now();
  const key = idem(); body.idem = key; body.slipCents = +$('#slip').value;
  const verb = verbOf(body);
  const old = btn ? btn.textContent : ''; if (btn) { btn.classList.add('pend'); btn.textContent = 'sending…' }
  const t = toast(`⏳ Sending <b>${verb}</b> · ${esc(label)}`, '', 0);
  let r = null;
  for (let pass = 0; pass < 3; pass++) {
    r = null; for (let i = 0; i < 3 && !r; i++) { try { r = await post('/api/t/order', body, 5000) } catch (e) { await new Promise(z => setTimeout(z, 500)) } }
    if (r && r.error == 'CONFIRM_SPECIAL') {
      const ok = await confirmBox(`⚠ ${r.kind == 'PARLAY' ? 'PARLAY' : r.kind == 'FUTURE' ? 'FUTURES bet' : 'Not a single-game bet'}`, `<p>${esc(r.message)}</p><p><b>${esc(r.label)}</b></p>`, `Yes, ${verb}`);
      if (!ok) { r = {ok: false, error: 'canceled', message: 'you canceled'}; break } body.confirmSpecial = true; continue
    }
    if (r && r.error == 'CONFIRM_RISKY') {
      const ok = await confirmBox('⚠ Are you sure?', `<p><b>${esc(r.label || label)}</b></p>${(r.reasons || []).map(x => `<p>• ${esc(x)}</p>`).join('')}`, `Yes, ${verb}`);
      if (!ok) { r = {ok: false, error: 'canceled', message: 'you canceled'}; break } body.confirmRisky = true; continue
    }
    if (r && r.error == 'LOSS_CAP_CONFIRM') {
      const ok = await confirmBox('Daily loss cap reached', `<p>${esc(r.message)}</p><p>Sells are never blocked. Buy anyway?</p>`, `I'm sure: ${verb}`);
      if (!ok) { r = {ok: false, error: 'canceled', message: 'you canceled'}; break } body.overrideLossCap = true; continue
    }
    break
  }
  if (btn) { btn.classList.remove('pend'); btn.textContent = old }
  if (!r) { toast(`❌ Server unreachable: <b>${verb}</b> may not have been sent. Check Orders.`, 'bad', 10000, t); return }
  if (!r.ok) { toast(`❌ <b>${verb}</b> not sent: ${esc(r.message || r.error)}`, 'bad', 8000, t); return }
  if (btn) { btn.textContent = '✓ sent'; setTimeout(() => { if (btn.textContent == '✓ sent') btn.textContent = old; updateTicket() }, 1500) }
  toast(`✅ <b>${verb}</b> queued · ${esc(label)} · waiting for fill…`, '', 0, t); S.watch[key] = t; S.fast = Date.now() + 15000; loadIntents()
}
function verbOf(b) { return b.action == 'BUY' ? `BUY $${b.usd}` : b.action == 'SELL_ALL' ? 'SELL ALL' : b.action == 'SELL_HALF' ? 'SELL HALF' : b.action == 'SELL_PCT' ? `SELL ${b.pct}%` : b.action == 'SELL_QTY' ? `SELL LOT (${b.qty} ctr)` : `SELL $${b.usd}` }
function sellPos(btn, p, act, usd, extra = {}) {
  if (act == 'SELL_USD' && !(usd > 0)) return toast('Type a $ amount to sell', 'warn');
  if (act == 'SELL_PCT' && !(extra.pct > 0 && extra.pct <= 100)) return toast('Type a percent (1-100)', 'warn');
  unpop(); return sendOrder(btn, {action: act, marketId: p.marketId, outcomeId: p.sideId, usd: usd || 0, eventDesc: (gameOf(p.eventId) || {}).desc, ...extra}, posLabel(p))
}

// ---------- positions ----------
function posLabel(p) { const g = gameOf(p.eventId); return mLabel({type: p.type, desc: p.market}, {name: p.side}, g) || `${p.side} · ${p.market}` }
async function loadPf() {
  try {
    const p = await api('/api/t/portfolio', {}, 8000); if (!p.wallets) return false; S.pf = p;
    const cw = p.wallets.find(w => w.tradable); S.cash = cw && cw.cash != null ? cw.cash : null; S.exitAll = cw ? cw.exitCashAll || 0 : 0;
    const now = Date.now();
    for (const x of positions()) { if (!x.bid) continue; const k = x.marketId + x.sideId, h = S.oddsHist[k] = S.oddsHist[k] || [];
      h.push({t: now, o: 1 / x.bid}); while (h.length && now - h[0].t > 180000) h.shift() }
    renderHero(cw || p.wallets[0]); drawPositions(); drawGames(); return !p.wallets.some(w => w.stale)
  } catch (e) { return false }
}
// odds momentum: change in sell-now odds over the last ~60s (falling odds = your side got more likely = good for you)
function momentum(x) {
  const h = S.oddsHist[x.marketId + x.sideId]; if (!h || h.length < 2 || !x.bid) return null;
  const now = Date.now(), ref = h.find(p => now - p.t <= 75000) || h[0]; if (now - ref.t < 8000) return null;
  return 1 / x.bid - ref.o
}
function posTitle(p) {
  const g = gameOf(p.eventId), st = fstrike(p.strike);
  if (p.type == 'MONEY') return [`${p.side} to win`, 'match'];
  if (p.type == 'SPREAD') return [`${p.side.split(' ')[0]} ${st}`, 'spread'];
  if (p.type == 'TOTAL') return [`${p.side}`, 'total points'];
  if (p.type == 'TEAM_TOTAL') return [`${(p.market || '').replace(/ ?TEAM_TOTAL.*/, '')} ${p.side}`, 'team points'];
  return [p.side, (p.type || '').toLowerCase()]
}
function drawPositions() {
  const p = S.pf, late = [];
  const sm = (p.wallets.find(w => w.tradable) || p.wallets[0] || {}).summary || {};
  $('#psum').innerHTML = `<div class="sumbar num"><span data-tip="What selling everything now would pay, after exit fees">cash out ${money(sm.openValue)}</span><span data-tip="Paid incl. fees">cost ${money(sm.openBasis)}</span>
    <span data-tip="If every open position wins">max ${money(sm.payoutIfAllWin)}</span><span data-tip="Expected payout (win chance × payout) − cost">est. return <b class="${cls(sm.expReturn)}">${sg(sm.expReturn)}</b></span>${sm.settlingCount ? `<span class="yl" data-tip="Game over; Novig pays these at the final">${sm.settlingCount} settling</span>` : ''}</div>`;
  $('#plist').innerHTML = p.wallets.map(w => `<h3>${esc(w.label)}${w.error ? ' — <span class="dn">' + esc(w.error) + '</span>' : ''}${w.tradable && w.cash == null && w.cashError ? ' — <span class="dn">' + esc(w.cashError) + '</span>' : ''}</h3>` + (w.positions.map(x => {
    const g = gameOf(x.eventId), lt = g && g.clock && g.clock.late; if (lt && w.tradable && x.state != 'settling') late.push(x.side);
    const i = positions(true).findIndex(q => q.marketId == x.marketId && q.sideId == x.sideId), [ttl, kind] = posTitle(x);
    const mo = momentum(x), set = x.state == 'settling', entry = x.entryPrice || x.avg;
    const lots = x.lots || [], many = lots.length > 1;
    const lotRows = many ? lots.map(L => `<div class="lot num"><span class="ls">${money(L.stake)}</span><b class="odds">${odds(L.price)}</b><span class="mut">now ${money(L.value)}</span>
        ${w.tradable && !set ? `<button class="btn h xs" onclick="sellLot(this,${i},'${L.id}',${L.qty})" data-tip="Sell only this buy (${L.qty} contracts)">sell</button>` : ''}</div>`).join('') : '';
    const ride = x.net ? `${x.net} ctr pay ${money(x.payout)} if ${esc(x.side)} wins` : '';
    return `<div class="pcard ${set ? 'settling' : ''}">
      <div class="ph"><span class="pt">${esc(ttl)}</span> <span class="pk">(${esc(kind)})</span>${lt && !set ? '<span class="livetag late" style="position:static;border-radius:3px;margin-left:auto">FLATTEN? Q4 ≤5:00</span>' : ''}${set ? '<span class="chip settling" style="margin-left:auto">SETTLING</span>' : ''}</div>
      <div class="pg mut">${esc(x.gameDesc ? x.gameDesc.replace(' @ ', ' at ') : x.market)}${w.tradable ? '' : ' · Novig app'}</div>
      <div class="pmid">
        <div class="pleft num">
          <div class="ptot" data-tip="What you paid (before fees) and the odds you got">${money(x.stake ?? x.basis)} <b class="odds">${odds(entry)}</b></div>
          ${lotRows}
        </div>
        <div class="pright num">
          ${set ? `<div class="pval yl" data-tip="Game over: Novig grades it and pays at the final">settling</div><div class="mut">${ride}</div>`
            : `<div class="pvrow"><span class="pval" data-tip="Cash out: what SELL ALL would pay you now, after the ${money(x.exitFee)} exit fee">${money(x.cashOut)}</span>
                <span class="pnow" data-tip="Odds now (sell side)${mo != null ? '; bracket = change over the last minute' : ''}"><b class="odds">${odds(x.bid)}</b>${mo != null && Math.abs(mo) >= 0.01 ? ` <span class="mom ${mo < 0 ? 'up' : 'dn'}">[${mo > 0 ? '+' : ''}${mo.toFixed(2)}]</span>` : ''}</span></div>
              <div class="ppnl ${cls(x.pnl)}" data-tip="Profit if you sold everything now, after all fees (in + out)">${sg(x.pnl)} <span>(${x.pnlPct != null ? (x.pnlPct > 0 ? '+' : '') + x.pnlPct.toFixed(1) + '%' : '–'})</span></div>`}
        </div>
      </div>
      <div class="pfee mut num">${set ? '' : `fees: in ${money(x.entryFees)} · out ${money(x.exitFee)}${x.feeLive ? '' : ' (pregame: no fee)'} · ${ride} · win ${x.winProb ? (x.winProb * 100).toFixed(0) + '%' : '–'}`}</div>
      ${w.tradable && !set && x.exitCash != null && S.cash != null && x.exitCash > S.cash ? `<div class="cw">selling all at once needs ≈ ${money(x.exitCash)} cash up front, you have ${money(S.cash)}: SELL ALL goes out in chunks</div>` : ''}
      <div class="btns pbtns">${set ? '<span class="mut">nothing to sell: Novig pays it at the final</span>' : w.tradable ? `<button class="btn h" onclick="sellPos(this,positions(true)[${i}],'SELL_HALF')" data-tip="Sells half; the other ~${Math.ceil(x.net / 2)} contracts keep riding to the final">Sell half</button><button class="btn h" data-pop="1" onclick="sellUsdPop(this,${i})">Sell $N / %…</button><button class="btn s" onclick="sellPos(this,positions(true)[${i}],'SELL_ALL')">SELL ALL</button>` : '<span class="mut">read-only wallet (sell in Novig app)</span>'}</div></div>` }).join('') || '<div class="pos mut">flat</div>')).join('');
  const a = $('#alerts'); if (late.length) { a.style.display = 'block'; a.textContent = '⚠ Q4 under 5:00 with open positions: ' + late.join(', ') + ' — held-to-end went 0-4 (-$83.80). Flatten?' } else a.style.display = 'none'
}
function sellLot(btn, i, lot, qty) { const p = positions(true)[i]; if (!p) return; sellPos(btn, p, 'SELL_QTY', 0, {qty, lot}) }
function sellUsdPop(btn, i) { const p = positions(true)[i]; if (!p) return;
  pop(btn, `<div class="mut" style="font-size:11px">${esc(posLabel(p))} · cash out ${money(p.cashOut)}</div>
    <div style="display:flex;gap:4px;margin-top:4px"><input id="snp" type="text" inputmode="decimal" placeholder="$" style="width:70px"><button class="btn h" style="flex:1" onclick="sellPos(this,positions(true)[${i}],'SELL_USD',parseFloat($('#snp').value))">Sell $N</button></div>
    <div style="display:flex;gap:4px;margin-top:4px"><input id="snpp" type="text" inputmode="decimal" placeholder="%" style="width:70px"><button class="btn h" style="flex:1" onclick="sellPos(this,positions(true)[${i}],'SELL_PCT',0,{pct:parseFloat($('#snpp').value)})">Sell N%</button></div>
    <div class="mut" style="font-size:11px;margin-top:4px">Whatever you don't sell keeps riding to the final.</div>`);
  setTimeout(() => $('#snp').focus(), 0) }

// ---------- orders / receipts ----------
function receipt(i) {
  const f = i.filled_qty || 0, avg = f ? i.cost * 100 / f : null, sell = i.action != 'BUY';
  let fill = '', detail = '';
  if (f && !sell) { fill = `bought <b>${money(i.cost)}</b> @ <b class="odds">${odds(avg)}</b> · fees ${money(i.fee)}`; detail = `${f} contracts @ ${cents(avg)}` }
  if (f && sell) { fill = `sold @ <b class="odds">${odds(1 - avg)}</b> · got <b>${money(f / 100 - i.cost - i.fee)}</b> · fees ${money(i.fee)}`; detail = `${f} contracts @ ${cents(1 - avg)}` }
  const ride = sell && i.riding > 0 && i.action != 'SELL_ALL' ? `<div class="yl">${i.riding} contracts still ride to the final</div>` : '';
  const verb = verbOf({action: i.action, usd: i.usd, pct: i.pct, qty: i.qty_req});
  return `<div class="it"><span class="chip ${i.status}">${i.status.toUpperCase()}</span> <b>${verb}</b> ${i.kind && i.kind != 'GAME' ? `<span class="chip expired">${esc(i.kind)}</span>` : ''}${i.source == 'trigger' ? ' <span class="chip armed">TARGET</span>' : ''}
    <span class="lbl">${esc(i.label || '(older order: market not recorded)')}</span> <span class="mut">${fmtT(i.created, {second: '2-digit'})} ${tzName()}</span>
    <div class="num">${fill || esc(i.message || '')}</div>${ride}${fill && i.status != 'filled' ? `<div class="mut">${esc(i.message || '')}</div>` : ''}
    <details><summary>log</summary><pre>${esc((detail ? detail + '\n' : '') + i.log.join('\n'))}</pre></details></div>`
}
async function loadIntents() {
  try {
    const r = await api('/api/t/intents?n=25'); const its = r.intents.filter(Boolean);
    if (its.some(i => ['queued', 'working'].includes(i.status))) S.fast = Date.now() + 5000;
    $('#ilist').innerHTML = its.map(receipt).join('') || '<div class="it mut">no orders yet</div>';
    for (const i of its) { const t = S.watch[i.idem]; if (!t || ['queued', 'working', 'check'].includes(i.status)) continue;
      const good = i.status == 'filled', f = i.filled_qty || 0, avg = f ? i.cost * 100 / f : null;
      const rideT = i.action != 'BUY' && i.action != 'SELL_ALL' && i.riding > 0 ? `<br><b class="yl">${i.riding} contracts still ride to the final</b> (pay ${money(i.riding / 100)} if it wins, $0 if not)` : '';
      toast(`${good ? '✅' : i.status == 'partial' ? '◐' : i.status == 'settling' ? '⏳' : '❌'} <b>${i.status.toUpperCase()}</b> · ${esc(i.label || '')}<br><span class="num">${f ? (i.action == 'BUY' ? `${money(i.cost)} @ ${odds(avg)}` : `sold @ ${odds(1 - avg)} · got ${money(f / 100 - i.cost - i.fee)}`) + ` · fees ${money(i.fee)}` : esc(i.message || '')}</span>${rideT}`, good ? 'ok' : 'bad', rideT ? 14000 : 9000, t);
      delete S.watch[i.idem]; loadPf() }
  } catch (e) {}
}

// ---------- local triggers ----------
async function loadTriggers() { try { const r = await api('/api/t/triggers'); S.trig = r.triggers || []; drawTriggers() } catch (e) {} }
function drawTriggers() {
  const el = $('#tList'); if (!el) return; const ts = S.trig.filter(t => t.status == 'armed' || Date.now() - t.created < 3600e3);
  el.innerHTML = ts.map(t => `<div class="trig"><span class="chip ${t.status}">${t.status.toUpperCase()}</span><span>${t.action.replace('_', ' ')}${t.usd ? ' $' + t.usd : ''} · ${esc(t.label)} when ${esc(((S.status && S.status.trigConds) || {})[t.cond] || t.cond)} ${t.target}</span>
    <span class="mut">${esc(t.message || '')}</span>${t.status == 'armed' ? `<button class="btn h" style="padding:3px 8px;margin-left:auto" onclick="cancelTrigger('${t.id}')">cancel</button>` : ''}</div>`).join('')
}
async function armTrigger(btn) {
  const b = S.book, o = b && b.outcomes.find(x => x.outcomeId == S.sel), g = gameOf(S.event); if (!o) return toast('Pick a side first', 'warn');
  const act = $('#tAct').value, target = parseFloat($('#tTarget').value), usd = parseFloat($('#tUsd').value) || (act == 'BUY' ? S.amt : 0);
  if (!(target > 0)) return toast('Type a target number', 'warn');
  if ((act == 'BUY' || act == 'SELL_USD') && !(usd > 0)) return toast('Type a $ amount', 'warn');
  const r = await post('/api/t/trigger', {action: act, marketId: b.marketId, outcomeId: o.outcomeId, usd, cond: $('#tCond').value, target, hours: +$('#tHrs').value, slipCents: +$('#slip').value, eventDesc: g && g.desc});
  if (!r.ok) return toast('❌ Target not armed: ' + esc(r.message || r.error), 'bad');
  toast('🎯 Armed: ' + esc(r.trigger.label), 'ok'); loadTriggers()
}
async function cancelTrigger(id) { await post('/api/t/trigger/cancel', {id}); loadTriggers() }

// ---------- settings ----------
$('#setBtn').onclick = async () => {
  const c = (S.pf && S.pf.cfg) || (S.status && S.status.cfg) || {};
  const zones = [...new Set([Intl.DateTimeFormat().resolvedOptions().timeZone, S.tz, 'America/Los_Angeles', 'America/Denver', 'America/Chicago', 'America/New_York', 'UTC'])];
  const ok = await confirmBox('Settings', `<div class="trow">Daily loss cap $<input id="sCap" type="text" inputmode="decimal" value="${c.daily_loss_cap_usd || 40}" style="width:70px"> <span class="mut">past it, buys ask you to confirm</span></div>
    <div class="trow">Max per order $<input id="sMax" type="text" inputmode="decimal" value="${c.max_order_usd || 25}" style="width:70px"></div>
    <div class="trow">Time zone <select id="sTz">${zones.map(z => `<option ${z == S.tz ? 'selected' : ''}>${z}</option>`).join('')}</select></div>
    <div class="trow">Fees <select id="sFee">${[['auto', "auto (each market's rule: game lines in-game only)"], ['in_game_only', 'in-game only'], ['always', 'always'], ['off', 'off (ignore fees)']].map(([v, n]) => `<option value="${v}" ${(c.fee_mode || 'auto') == v ? 'selected' : ''}>${n}</option>`).join('')}</select></div>
    <div class="trow">Fee coefficient <input id="sCoef" type="text" inputmode="decimal" value="${c.fee_coef || ''}" placeholder="0.06 (market)" style="width:90px"> <span class="mut">fee per contract = coef × p × (1 − p)</span></div>`, 'Save');
  if (!ok) return;
  S.tz = $('#sTz').value; localStorage.setItem('tz', S.tz);
  const r = await post('/api/t/settings', {daily_loss_cap_usd: parseFloat($('#sCap').value), max_order_usd: parseFloat($('#sMax').value), fee_mode: $('#sFee').value, fee_coef: parseFloat($('#sCoef').value) || null});
  toast(r.ok ? 'Settings saved' : '❌ ' + esc(r.error), r.ok ? 'ok' : 'bad'); drawGames(); loadPf(); status()
};
$('#flatAll').onclick = async () => {
  if (!await confirmBox('Flatten everything?', 'Sell ALL open positions in the tradable wallet now?', 'Sell all')) return;
  await post('/api/t/flatten', {batch: 'flat-' + Date.now(), slipCents: Math.max(3, +$('#slip').value)}); S.fast = Date.now() + 15000; loadIntents()
};
$('#fq').oninput = e => { S.f.q = e.target.value; drawGames() };
$('#fStatus').onchange = e => { S.f.status = e.target.value; drawGames() };
$('#fDate').onchange = e => { S.f.date = e.target.value; drawGames() };
$('#fMine').onclick = () => { S.f.mine = !S.f.mine; $('#fMine').classList.toggle('on', S.f.mine); drawGames() };

// ---------- loops ----------
setInterval(() => { const a = (Date.now() - S.lastOk) / 1000, m = S.mktStale ? (Date.now() - S.mktStale) / 1000 : 0, bad = a > 6 || m > 4;
  $('#conn').style.background = bad ? 'var(--rd)' : 'var(--gr)'; $('#age').textContent = a > 6 ? 'server unreachable ' + a.toFixed(0) + 's' : (m > 4 ? 'prices stale ' + m.toFixed(0) + 's (rate limited)' : '') }, 1000);
function loop(fn, base, max) { let d = base; const run = async () => { let ok = true; if (!document.hidden) { try { ok = await fn() } catch (e) { ok = false } } d = ok === false ? Math.min(max, d * 2) : base; setTimeout(run, d) }; run() }
status().then(() => loadGames()).then(() => { const m = location.hash.match(/e=([\w-]+)/); if (m && S.gamesById[m[1]]) pickEvent(m[1]) });
setTimeout(() => loop(loadGames, 15000, 60000), 15000); setTimeout(() => loop(loadEvent, 30000, 60000), 30000); loop(loadBook, 1500, 10000); loop(loadPf, 3000, 15000); loop(loadTimeline, 20000, 60000);
setInterval(() => { if (Object.values(S.flash).some(f => f.until < Date.now() && !f.cleared)) { Object.values(S.flash).forEach(f => { if (f.until < Date.now()) f.cleared = 1 }); drawGames() } }, 2000);
setInterval(() => { if ((S.fast || 0) > Date.now()) loadIntents() }, 700); setInterval(loadIntents, 4000); setInterval(status, 30000); loadIntents();
setInterval(loadTriggers, 4000); loadTriggers();
