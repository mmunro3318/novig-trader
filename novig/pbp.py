"""Play-by-play adapter: turns real-world game events into timeline 'notches' for the journal.

Primary source (verified live 2026-10-22): ESPN's public site API (no key, JSON):
  scoreboard  https://site.api.espn.com/apis/site/v2/sports/football/{nfl|college-football}/scoreboard?dates=YYYYMMDD[&groups=80&limit=300]
  summary     https://site.api.espn.com/apis/site/v2/sports/football/{league}/summary?event={id}
summary.drives.previous[].plays[] carry type, text, period, clock, scores and a UTC `wallclock`
(what we line up against Novig prices), and summary.winprobability[] gives a home win % per play.
Unofficial + undocumented: treat as best-effort, cache aggressively, fail soft.

Stubs (same normalized output, not wired): nflverse (nflfastR parquet, NFL, next-day),
CollegeFootballData API (needs free key CFBD_API_KEY), MMA / soccer (future sports).
"""
from __future__ import annotations
import json, os, re, time, urllib.request
from datetime import datetime, timezone

ESPN = "https://site.api.espn.com/apis/site/v2/sports/football"
LEAGUE_PATH = {"NFL": "nfl", "NCAAF": "college-football"}
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pbp_cache")
os.makedirs(CACHE, exist_ok=True)

# Normalized event types. `hype` = the kind of moment that moves prices (Michael's entry triggers).
EVENT_TYPES = {
    "KICKOFF_GAME": {"label": "Game start", "hype": False, "icon": "whistle"},
    "END_QUARTER": {"label": "End of quarter", "hype": False, "icon": "quarter"},
    "HALFTIME": {"label": "Halftime", "hype": False, "icon": "halftime"},
    "END_GAME": {"label": "Final", "hype": False, "icon": "final"},
    "TD": {"label": "Touchdown", "hype": True, "icon": "td"},
    "FG": {"label": "Field goal", "hype": False, "icon": "fg"},
    "FG_MISS": {"label": "Missed FG", "hype": True, "icon": "fg"},
    "INT": {"label": "Interception", "hype": True, "icon": "int"},
    "PICK_SIX": {"label": "Pick-six", "hype": True, "icon": "int"},
    "FUMBLE_LOST": {"label": "Fumble lost", "hype": True, "icon": "fumble"},
    "FUMBLE_REC": {"label": "Fumble (recovered)", "hype": True, "icon": "fumble"},
    "SACK": {"label": "Sack", "hype": True, "icon": "sack"},
    "SAFETY": {"label": "Safety", "hype": True, "icon": "sack"},
    "TURNOVER_DOWNS": {"label": "Turnover on downs", "hype": True, "icon": "turnover"},
    "BLOCKED": {"label": "Blocked kick", "hype": True, "icon": "turnover"},
    "PENALTY": {"label": "Penalty", "hype": False, "icon": "penalty"},
    "PENALTY_BIG": {"label": "Big penalty (TD nullified / 15+ yds)", "hype": True, "icon": "penalty"},
    "INJURY": {"label": "Injury", "hype": True, "icon": "injury"},
    "CHALLENGE": {"label": "Challenge / review", "hype": True, "icon": "challenge"},
    "TIMEOUT": {"label": "Timeout", "hype": False, "icon": "timeout"},
}

def _get(url, ttl=30):
    fn = os.path.join(CACHE, re.sub(r"[^a-zA-Z0-9]+", "_", url)[-180:] + ".json")
    if os.path.exists(fn) and time.time() - os.path.getmtime(fn) < ttl:
        return json.load(open(fn))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "novig-app/0.2"})
        d = json.load(urllib.request.urlopen(req, timeout=12))
        json.dump(d, open(fn, "w")); return d
    except Exception:
        if os.path.exists(fn): return json.load(open(fn))   # stale beats nothing
        raise

def _ms(iso):
    if not iso: return None
    iso = iso.replace("Z", "+00:00")
    if re.match(r".*T\d\d:\d\d\+", iso): iso = iso.replace("+", ":00+", 1)
    return int(datetime.fromisoformat(iso).timestamp() * 1000)

def scoreboard(league="NFL", date: str | None = None):
    """date YYYYMMDD (default today). Returns compact games list."""
    url = f"{ESPN}/{LEAGUE_PATH[league]}/scoreboard?limit=300" + (f"&dates={date}" if date else "") + ("&groups=80" if league == "NCAAF" else "")
    d = _get(url, ttl=20)
    out = []
    for e in d.get("events", []):
        c = e["competitions"][0]; st = c["status"]
        teams = {t["homeAway"]: {"abbr": t["team"].get("abbreviation"), "name": t["team"].get("displayName"), "short": t["team"].get("shortDisplayName"),
                                 "color": "#" + (t["team"].get("color") or "888888"), "score": t.get("score"), "record": (t.get("records") or [{}])[0].get("summary")} for t in c["competitors"]}
        odds = (c.get("odds") or [{}])[0]
        out.append({"espnId": e["id"], "league": league, "name": e["name"], "startsTs": _ms(e["date"]), "state": st["type"]["state"],
                    "detail": st["type"].get("shortDetail"), "period": st.get("period"), "clock": st.get("displayClock"),
                    "home": teams.get("home"), "away": teams.get("away"), "spread": odds.get("details"), "overUnder": odds.get("overUnder")})
    return {"source": "espn", "url": url, "games": out}

def classify(p) -> list[str]:
    t = p["type"].get("text", ""); x = p.get("text", ""); xl = x.lower(); types = []
    if "Kickoff" in t and p.get("period", {}).get("number") == 1 and p.get("clock", {}).get("displayValue") in ("15:00", None): types.append("KICKOFF_GAME")
    if t == "End Period": types.append("END_QUARTER")
    if t == "End of Half": types.append("HALFTIME")
    if t == "End of Game": types.append("END_GAME")
    if "Interception" in t: types.append("PICK_SIX" if "Touchdown" in t or "TOUCHDOWN" in x else "INT")
    elif "Touchdown" in t or ("TOUCHDOWN" in x and "NULLIFIED" not in x): types.append("TD")
    if "Fumble" in t or "FUMBLES" in x:
        types.append("FUMBLE_LOST" if ("Opp" in t or "RECOVERED by" in x and "Own" not in t) else "FUMBLE_REC")
    if t == "Sack" or " sacked " in xl: types.append("SACK")
    if t == "Safety": types.append("SAFETY")
    if "Field Goal Good" in t: types.append("FG")
    if "Field Goal Missed" in t or "Blocked Field Goal" in t: types.append("FG_MISS")
    if "Blocked" in t: types.append("BLOCKED")
    if "downs" in xl and "turnover" in xl: types.append("TURNOVER_DOWNS")
    if "PENALTY" in x or t == "Penalty":
        yds = re.search(r"(\d+) yards", x.split("PENALTY")[-1] if "PENALTY" in x else x)
        big = "NULLIFIED" in x or (yds and int(yds.group(1)) >= 15) or "Pass Interference" in x
        types.append("PENALTY_BIG" if big else "PENALTY")
    if "injur" in xl and "returned to the game" not in xl: types.append("INJURY")
    if "challenge" in xl or "replay" in xl and "review" in xl: types.append("CHALLENGE")
    if t == "Timeout": types.append("TIMEOUT")
    return types

def game_events(espn_id: str, league="NFL"):
    """Normalized timeline for one game: events[] + winprob[] (home win %, by wallclock)."""
    d = _get(f"{ESPN}/{LEAGUE_PATH[league]}/summary?event={espn_id}", ttl=15)
    comp = d["header"]["competitions"][0]
    teams = {c["homeAway"]: c["team"] for c in comp["competitors"]}
    tid = {c["team"]["id"]: c["team"]["abbreviation"] for c in comp["competitors"]}
    plays = [p for dr in (d.get("drives") or {}).get("previous", []) for p in dr.get("plays", [])]
    cur = (d.get("drives") or {}).get("current") or {}
    plays += [p for p in cur.get("plays", []) if p["id"] not in {q["id"] for q in plays}]
    wpmap = {w["playId"]: w["homeWinPercentage"] for w in d.get("winprobability", [])}
    ev, wp, start_added, lite = [], [], False, []
    for p in plays:
        ts = _ms(p.get("wallclock"))
        if ts is None: continue
        lite.append({"ts": ts, "period": p["period"]["number"], "clock": p["clock"]["displayValue"], "away": p.get("awayScore"), "home": p.get("homeScore")})
        if p["id"] in wpmap: wp.append({"ts": ts, "home": wpmap[p["id"]]})
        types = classify(p)
        if not start_added:
            types = ["KICKOFF_GAME"] + [t for t in types if t != "KICKOFF_GAME"]; start_added = True
        team = None
        for tp in p.get("teamParticipants") or []:
            team = tid.get(tp.get("id")); break
        if not team and p.get("start", {}).get("team"): team = tid.get(p["start"]["team"].get("id"))
        for t in types:
            ev.append({"id": f"espn-{p['id']}-{t}", "ts": ts, "type": t, "label": EVENT_TYPES[t]["label"], "hype": EVENT_TYPES[t]["hype"],
                       "icon": EVENT_TYPES[t]["icon"], "period": p["period"]["number"], "clock": p["clock"]["displayValue"],
                       "away": p.get("awayScore"), "home": p.get("homeScore"), "team": team, "text": p.get("text", "")[:220]})
    pc = (d.get("pickcenter") or [{}])[0]
    return {"source": "espn", "espnId": espn_id, "league": league, "kickoffTs": _ms(comp.get("date")),
            "home": {"abbr": teams["home"]["abbreviation"], "name": teams["home"]["displayName"], "color": "#" + teams["home"].get("color", "888")},
            "away": {"abbr": teams["away"]["abbreviation"], "name": teams["away"]["displayName"], "color": "#" + teams["away"].get("color", "888")},
            "status": comp.get("status", {}).get("type", {}).get("shortDetail"),
            "spread": pc.get("details"), "spreadHome": pc.get("spread"), "overUnder": pc.get("overUnder"),
            "events": ev, "winprob": wp, "plays": lite}

def match_novig(description: str, starts_ts: int, league: str):
    """Best-effort: Novig 'Away @ Home' + start time  ->  ESPN event id (same day, team-name overlap)."""
    try:
        away, home = [s.strip().lower() for s in description.split("@")]
    except ValueError:
        return None
    day = datetime.fromtimestamp(starts_ts / 1000, timezone.utc).strftime("%Y%m%d")
    try: games = scoreboard(league, day)["games"]
    except Exception: return None
    def hit(name, team):
        if not team: return False
        cands = [str(team.get(k) or "").lower() for k in ("abbr", "name", "short")]
        return any(name == c or (len(name) > 3 and name in c) or (len(c) > 3 and c in name) for c in cands if c)
    for g in games:
        if hit(home, g["home"]) and hit(away, g["away"]) and abs((g["startsTs"] or 0) - starts_ts) < 6 * 3600_000:
            return g["espnId"]
    return None

# ---- stubs: same normalized contract, not wired --------------------------------------------
def nflverse_events(game_id: str):
    """STUB. nflverse pbp parquet: https://github.com/nflverse/nflverse-data/releases/tag/pbp (NFL only,
    published next morning; has wp, epa, time_of_day). Map play_type/interception/fumble_lost/sack -> EVENT_TYPES."""
    return {"source": "nflverse", "stub": True, "events": [], "winprob": []}

def cfbd_events(game_id: str):
    """STUB. CollegeFootballData /plays?gameId= (Bearer CFBD_API_KEY, free tier). Use as NCAAF backfill."""
    return {"source": "cfbd", "stub": True, "needsKey": not os.environ.get("CFBD_API_KEY"), "events": [], "winprob": []}

def future_sport_events(sport: str):
    """STUB for MMA / soccer: ESPN has /apis/site/v2/sports/mma/ufc and /soccer/{league} with similar shapes."""
    return {"source": "espn", "sport": sport, "stub": True, "events": []}
