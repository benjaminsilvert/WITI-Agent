# CLAUDE.md — WITI agent

## What this project is
**WITI** (Walk-It-Talk-It) is a personal learning agent for a cybersecurity career spanning **web application security** and **AI security**. It supports a two-mode learning framework:
- **Talk it (theory):** understanding concepts, vulnerability types, mechanisms, and controls. WITI researches emerging trends/tech and explains them.
- **Walk it (action):** proving things hands-on — labs, boxes, and building/breaking/patching.

WITI's jobs: (1) **teach** — research emerging AI trends/technologies and explain them (the "talk it" piece); (2) **track** progress on **PortSwigger and HackTheBox across both domains** (web app security and AI security); (3) **email** a daily digest.

It is **also a deliberately-vulnerable-by-design security sandbox.** Building WITI, breaking it, and patching it is itself the "walk it" (action) piece for AI security — the AI-security equivalent of a PortSwigger lab. Each capability is built vulnerable (v1), exploited, then hardened (v2), and the before/after is kept as a portfolio of exploit->fix write-ups.

## Progress-tracking schema (what WITI tracks)
Track progress as **domain x mode**, in `tracker.md` (and/or `memory.json`). For every Action item, record the **source platform**, distinguishing **HTB Academy** (guided modules / job-role paths) from **HTB Labs** (boxes / machines). Each item gets a source, a status (not-started / in-progress / done), and a date.
- **Web App Security — Theory:** concepts read/understood (reading, write-ups, Academy module theory).
- **Web App Security — Action:**
  - PortSwigger Web Security Academy labs (by lab name)
  - HTB Academy — web modules / job-role paths (by module name)
  - HTB Labs — boxes / machines (by box name)
- **AI Security — Theory:** emerging trends/tech WITI has researched and explained (plus AI concept-module theory).
- **AI Security — Action:**
  - PortSwigger "Web LLM attacks" labs (by lab name)
  - HTB Academy — "AI Red Teamer" path modules (by module name)
  - HTB Labs — any AI/ML challenges (by name)
  - WITI build/break/patch items (from VULN_CATALOG.md)

Note: HTB Academy modules blend reading and hands-on exercises, so a module can log Theory (concepts) and Action (exercises) separately if you want that granularity.

## CRITICAL working rule
When I ask for a **v1 / vulnerable** build, do NOT add security controls "to be helpful." Build it exactly as specified, leaving the intended weakness in place. Only add controls when I explicitly ask for the **v2 / hardened** version. Flag security concerns in chat, but do not silently fix them.

## Stack (keep it minimal)
- Python 3, `anthropic` SDK (Messages API with tool use). WITI's "brain" is Claude via the API.
- Local files for storage: `notes/` (markdown), `memory.json`, `tracker.md`. No database to start.
- Add `chromadb` for real RAG only when asked. **No n8n, no heavy frameworks.**
- **Send channel: Gmail** — SMTP with an app password to start; Gmail API OAuth later for scoped access (which itself becomes a vuln to study). Not Telegram, not WhatsApp.
- Secrets (`ANTHROPIC_API_KEY`, Gmail credentials) in a `.env` file (git-ignored), loaded via `python-dotenv` — EXCEPT the one clearly-marked fake secret we deliberately plant in the system prompt for a demo.

## Project structure
```
witi-agent/
  main.py            # agent loop: calls the API, dispatches tool calls
  tools/             # fetch_url, search_notes, memory, tracker, send_digest (Gmail); optional: read_inbox
  prompts/system.md  # WITI's system prompt (see AGENT_SYSTEM_PROMPT.md)
  attacks/           # scripts that exploit the v1 weaknesses
  notes/  memory.json  tracker.md
  .env               # ANTHROPIC_API_KEY + Gmail creds (git-ignored)
```

## Build order (one step per session, commit after each)
1. Minimal loop: API call + a single `fetch_url` tool + print a digest to the terminal.
2. Add tools one at a time: `search_notes`, `read/append_memory`, `update_tracker`, `send_digest` (Gmail).
   - Build `update_tracker`/memory around the **domain x mode** schema above (PortSwigger + HTB progress for both domains, plus WITI vuln progress).
3. (Optional, high value) `read_inbox` (Gmail, read-only) — see capability H in VULN_CATALOG.md.
4. Bake in the **flagship vulnerability** (indirect prompt injection -> data exfiltration via the email send). Write an `attacks/` script proving it. Commit as v1.
5. Harden to v2 (see the functionality->patch mapping in AGENT_SYSTEM_PROMPT.md). Commit.
6. Repeat bake-in -> exploit -> harden for the other functionalities.

## Conventions
- Use plan mode; describe the approach and wait for my approval before implementing.
- Ask before installing any dependency or running network/send actions.
- Keep functions small and readable — I'm learning from this code, so explain non-obvious lines.
- After I correct you, add the lesson here so it isn't repeated.

## Reference docs in this repo
- `AGENT_SYSTEM_PROMPT.md` — WITI's system prompt + the functionality -> deliberate-vulnerability -> patch mapping.
- `VULN_CATALOG.md` — the broader catalogue of vulns, extended attack surfaces, and how the build fits the learning framework.
- `CLAUDE_CODE_WALKTHROUGH.md` — the step-by-step build guide (for me, not required reading for you).

## Run
- `python main.py` — run WITI once.
- `python attacks/<name>.py` — run an exploit demo.
