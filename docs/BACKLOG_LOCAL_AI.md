# Backlog: an AI helper/agent for the trader (stub)

Status: **ideas only, nothing built.** The current priority is getting a friend set up with the handoff prompt (`docs/HANDOFF_PROMPT.md`) and their own free-tier chat AI. This note keeps the later options in one place.

## Goal
Eventually, an agent watches games and the market, follows the written trading rules, and helps (or acts) without chasing losses. First it needs a model it can call cheaply and reliably.

## Options

| Option | What it is | Cost | Pros | Cons / open questions |
|---|---|---|---|---|
| **Ollama (local)** | Runs open models (Llama, Qwen, DeepSeek-distills, etc.) on your own computer | Free after hardware | Private, no API bills, works offline, no rate limits | Needs a decent GPU or Apple Silicon; smaller models are weaker at multi-step reasoning; we'd bundle install steps into setup |
| **DeepSeek API (cloud)** | DeepSeek's hosted models via an OpenAI-compatible API | Pay-as-you-go, very cheap | Strong reasoning for the price; easy to plug into existing agent harnesses (e.g. tools that accept an OpenAI-style base URL) | Needs an API key and billing; data leaves the machine; check terms and availability |
| **OpenRouter free models** | One API, many models, some with `:free` variants | Free tier (rate-limited) | Zero cost to try; switch models without code changes | Tight rate limits and daily caps; free models come and go; not reliable enough for in-game timing |

## Likely path
1. Short term: friends use their own chat AI with the handoff prompt (no harness needed).
2. Try OpenRouter free models or DeepSeek as a cheap "brain" for a simple harness (read-only first: summarize game state, flag rule triggers).
3. Move to Ollama locally once the agent's job is clear and stable, and add it to the setup guide.

## Ground rules for any agent (carry over from the app)
- Never sees or handles private keys; reads them only from `~/.secrets` through the app.
- Paper first. Real-money actions stay behind `NOVIG_ENV=production` + `NOVIG_ALLOW_LIVE_ORDERS=1` and the app's caps.
- Obeys the daily loss cap; never "averages down" to chase a loss.

## Open questions
- Which harness? (Claude Code / Cline / Aider-style tools, or a small custom loop in this repo.)
- What hardware do Kayden and Mike have for local models?
- How fast do decisions need to be in-game, and can a local model keep up?
