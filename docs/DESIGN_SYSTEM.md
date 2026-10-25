# novig/clean — Design System v0.2
Live sampler: **`/system.html`** (renders the real `UI.*` components from `static/app.js`). Tokens live in `static/app.css :root`.

## Principles
1. **Numbers first, chrome last.** Swiss editorial grid, black rules, huge tabular numerals. Decoration is only the red streak and the hand-drawn art.
2. **One tap to act.** Every price is a button; the slip is a persistent drawer; Enter places, Esc closes, `/` searches.
3. **Provenance always visible.** Every data widget carries a badge: `● live data`, `sample`, `dry-run`, `plays: ESPN`.
4. **Calm under stress.** Rules appear inline in industrial yellow, never as blocking modals. Friendly art (Pip) for empty and error states.
5. **The journal writes itself.** No widget asks for input during a fill; tags and notes are optional, one tap, any time.

## Tokens
| Group | Token | Value | Use |
|---|---|---|---|
| Color | `--paper` / `--paper-2` | #F4F2EC / #ECE9E1 | page / hover, quarter bands |
| | `--card` / `--rule` / `--rule-2` | #FFF / #D9D6CE / #BDB9AE | surfaces, hairlines |
| | `--ink` / `--ink-2` / `--ink-3` | #17171A / #4A4A4F / #8A8A85 | text, primary chrome, labels |
| | `--red` (streak) | #E10600 | LIVE, primary CTA (Buy), sell markers, losses, the streak |
| | `--orange` | #FF6A13 | MAKE mode, adds (+$1/+$2/+$5), selected price, break-even line |
| | `--yellow` | #FFC21A | rules panel, hype notches, active tags |
| | `--steel` | #5B5F66 | order-book bid depth |
| | `--gain` | #0F7B4A | positive P&L only |
| Type | `--sans` | Helvetica Neue → Inter → Arial | all UI; `font-variant-numeric: tabular-nums` on numbers |
| | scale | 72 display / 40 h1 / 24 h2 / 17 h3 / 14 body / 12 small / 10.5 micro-caps | weights 800 headings, 700 numbers, 600 labels |
| Space | `--s1..--s8` | 4 8 12 16 24 32 48 64 | 4-pt scale |
| Grid | `--cols` `--gutter` `--rail` `--slip` | 12 / 16px / 184px / 340px | `.c3…c12` spans; slip pushes main via `.withslip` |
| Radii | `--r0` `--r1` `--r2` `--rpill` | 0 / 3 / 8 / 999 | cards square (Swiss); buttons 3; chips pill |
| Elevation | `--e1` `--e2` `--press` | soft neo-skeuo shadows | hover lift, drawer/toast, pressed |
| Motion | `--fast` `--base` `--slow` `--ease` `--spring` | 90 / 160 / 280ms | press+hover / state / drawer+toast. Price flash 600ms yellow |

## Art direction
Hand-drawn felt-tip vectors (`tools/gen_assets.py`): jittered paths, a 0.45-weight ghost stroke, flat color fills offset 1.5px from the outline (riso feel). Palette limited to ink + red + orange + yellow.
- **Event icons** (`assets/ic-*.svg`): td, int, fumble, sack, injury, penalty, challenge, halftime, whistle (start), final, fg, timeout, turnover, quarter. These are the timeline notches.
- **UI icons**: games, positions, journal, account, settings, search, system, bolt, mma, soccer.
- **Pip** the football mascot (`assets/pip-*.svg`): sleep (nothing live), shrug (no position), write (empty journal), cheer (next kickoff), mma, soccer (coming soon), offline (API down).
- **Logo**: sketch football + red streak + `novig/clean` wordmark. **Team marks**: generated roundels with the abbreviation (ESPN team color when known, hashed hue otherwise; no trademarked logos).

## Components
| Component | Class / fn | Variants & states |
|---|---|---|
| Button | `.btn` | primary (red), make (orange), default, ghost, sm, block, disabled, pressed |
| Chip | `.chip` | default, on, soon (dimmed), tag (yellow when on) |
| Segmented | `.seg` | ink on; `.seg.make` turns Make orange |
| Badge | `UI.badge`, `UI.src` | live (pulsing), live data, sample (dashed yellow), dry-run (orange), src |
| Search | `.search` | `/` or ⌘K focus, Esc clears |
| Price button | `UI.px` | default, selected, up, down, none (no book), flash |
| Toast | `toast()` | after every fill, 4 quick mood tags, 7s |
| Drawer (slip) | `.slip` | closed, open; take / make |

## Data widgets (each maps to API fields — see sampler §6 and `novig-cheatsheet.md`)
| Widget | Fn | Variants |
|---|---|---|
| Game row | `UI.gameRow` | A live (score+clock) · B upcoming · C thin book |
| Scoreboard header | `UI.scoreboard` | A live display · B compact · C pregame |
| Price chart | `UI.chart` | A two-sided line + notches + markers · B sparkline · C journal timeline with quarter bands + break-even |
| Order book ladder | `UI.ladder` | two-sided bids folded into bid/ask ladder; empty |
| Game lines table | in `V.game` | Main (Winner/Spread/Total) · More & props (all markets with a book) |
| Order slip | `renderSlip` | Take · Make (0.005 grid stepper, tap a book level) · rules breach |
| Position card | `UI.position` | up · down `$1.12 (−3.82)` · flat |
| Positions table | `V.positions` | journal positions (+1/+2/+5, ½, All) + Novig portfolio |
| Stat block | `UI.stat` | money · signed P&L · ratio · inline value |
| Rules panel | `UI.rules` | all pass · breach |
| Journal entry | `UI.entry` | ENTER · ADD · PARTIAL EXIT · EXIT · REENTER |
| Game batch | `.gamebatch` | per game per day with fills, staked, realized |
| Event impact table | `impactsTable` | event type × spread bucket × +1/+3/+5/+10 min |
| Empty state | `UI.empty` | 7 Pip moods |

## Price formats
`F.one / F.pair` — **Multiplier** `2.43 : 1.89` (default, = 1/p) · **Percentage** `41% : 53%` · **Precise** `41.2% : 52.9%`. The header chip cycles formats; Settings has radio buttons. Journal entries always show all three.

## Number formatting
Money `$1,000.00`, signed `+$10.13 / −$1.63` (true minus sign). Position value `$1.12 (−3.82)` = value (Δ vs basis). Contracts are integers; prices snap to the 0.005 grid.
