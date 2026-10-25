# Handoff prompt (copy-paste this to your AI)

Copy everything inside the box below and paste it into Claude, Gemini or ChatGPT as your first message. (The repo link is already filled in.)

---

```text
Hi! I'd like your help installing and running a small trading app my friend built for himself. It's called Novig Trader, and its code is here: https://github.com/mmunro3318/novig-trader

About me: I'm not a programmer and I've never really used a terminal. Please be patient and explain things simply.

Before you do anything else, read these files in the repo (open the links from the GitHub page, or ask me to paste them if you can't open links):
  1. docs/AI_SETUP_GUIDE.md   (written for you, the AI; follow it)
  2. README.md
  3. TRADER.md
  4. docs/LIVE_TRADING.md

Then help me set it up, following these rules:
- Go ONE small step at a time. Give me one instruction, explain in a sentence what it does, and wait until I tell you it worked (or paste what I see) before the next step.
- Use plain language. Tell me exactly where to click and what to type. First ask whether I'm on Windows or a Mac, and give me only the commands for my system (Windows = PowerShell, Mac = Terminal).
- NEVER ask me for secret values: private keys, the contents of any .pem file, or anything in my .secrets folder. If I start to paste one, stop me and tell me how to fix it (revoke the key on Novig and make a new one). Secrets stay on my computer, outside the app folder.
- Stay in PAPER mode (play money) until a $1 paper buy AND a paper sell have both worked. Don't bring up real-money setup before that.
- Before anything involving real money, tell me clearly: "This is real money." Also remind me that this is an experimental personal project with no guarantees, that I should start with $1 orders, and that I should only use money I'm fine losing.
- Use the checklist in docs/AI_SETUP_GUIDE.md and tick items off with me as we go.
- If something breaks, use the troubleshooting table in the guide. Don't change the app's code. If we're stuck, help me write a short note to my friend with the error message (with no keys in it).

When you've read the docs, reply with a short, friendly summary of what we're going to do (3 to 5 bullets), then ask me your first question.
```

---

**Tip:** if your AI can't open GitHub links, download the ZIP (green **Code** button → **Download ZIP**), unzip it, and paste the contents of `docs/AI_SETUP_GUIDE.md` into the chat after the prompt. That one file is enough to get started.
