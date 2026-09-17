# VULN_CATALOG.md — WITI agent

Master reference for the deliberately-vulnerable-by-design build. For each item: build the **v1** weakness, **exploit** it, apply the **v2 patch**, and tie the fix to a **principle**. Keep a three-sentence write-up per vuln (what I built / the issue / the fix) — that's the portfolio artifact.

**How this fits the learning framework:** building, breaking, and patching WITI is the **"walk it" (action) piece for AI security** — your PortSwigger-lab equivalent for AI security *engineering*. Complementary structured practice you can track alongside it: PortSwigger's "Web LLM attacks" labs, and HackTheBox's "AI Red Teamer" job-role path (in HTB **Academy**). Those cover the attacker side; this project covers the builder/defender side and produces an artifact you can show.

Full detail for the core items A–H lives in `AGENT_SYSTEM_PROMPT.md`; this file indexes them and then adds extra capabilities you can bolt on for more surface.

---

## Part 1 — Core vulnerabilities (current build)

- **A. Untrusted content ingestion (`fetch_url`/`search_web`).** Fetched text is treated as instructions; no domain limit. -> **Indirect prompt injection.** Patch: delimit fetched content as untrusted data, domain allow-list, optional quarantined (tool-less) pass. *Trust boundary; allow-listing.*
- **B. Egress (`send_digest` via Gmail).** Model chooses recipient + content. -> **Data exfiltration** (chained with A). Patch: recipient fixed in config, egress filter for secrets/PII, human approval. *Confused deputy; egress control.*
- **C. State (`update_tracker`/`append_memory`).** Broad writes; unfiltered memory. -> **Excessive agency + stored injection.** Patch: append-only, fixed path, size caps, sanitize + provenance-tag, treat memory as untrusted on read. *Least privilege.*
- **D. No human-in-the-loop.** Irreversible actions auto-run. Patch: deterministic approval **hook in code** (not a prompt request). *Deterministic controls; hooks.*
- **E. Retrieval authz (`search_notes`).** Returns all notes regardless of sensitivity. -> **Private-data leak.** Patch: `sensitivity` tags + retrieval filtered by mode/identity in code. *Data-layer authorization; ABAC.*
- **F. Secrets in the system prompt.** Planted key/instructions. -> **Prompt extraction.** Patch: no secrets/logic in prompt; env/vault; treat prompt as public. *Sensitive-info disclosure.*
- **G. Tools exposed in every phase.** Send/write reachable while handling untrusted content. Patch: **capability separation** — untrusted-content phase has no send/write tools. *Least privilege; blast-radius containment.*
- **H. Inbox reading (`read_inbox` via Gmail).** Inbox contents treated as instructions. -> **Inbound injection.** Patch: inbox is untrusted data, no send/write from inbox content, sender allow-list, human approval. *Trust boundary on a new inbound channel.*

---

## Part 2 — Extended functionality (bolt on for more attack surface)

Each adds a **new vulnerability class** beyond A–H. Start with the star items — they carry the most weight.

### * I. Code-execution tool ("run this snippet" / shell)
- **New class:** **RCE**, command injection, sandbox escape.
- **Exploit:** injection makes the agent run arbitrary shell/Python — the ultimate excessive-agency case.
- **Patch:** run in a locked-down sandbox (container, no network, allow-listed calls) or don't grant it at all; never build commands from untrusted input.
- **Value:** shows you understand where agentic power becomes catastrophic. High.

### * J. File / document ingestion (drop a PDF or doc to summarize)
- **New class:** malicious-file parsing, **path traversal**, resource bombs.
- **Exploit:** a PDF with hidden injected text; a filename like `../../etc/...` on save; a zip/XML bomb.
- **Patch:** parse in isolation, sanitize extracted text as untrusted, safe/normalized file paths, size limits.
- **Value:** bridges straight to a web-app pentest background (path traversal, malicious uploads). High.

### K. Browser-automation tool (a real browser to research/log in)
- **New class:** session/cookie abuse, action-on-your-behalf, live-page injection.
- **Exploit:** it reuses your logged-in sessions; an injected page makes it click/act as you — the grocery-agent lesson at full power.
- **Patch:** give the browser its **own profile/identity**, never reuse your real session, allow-list domains, HITL on actions.
- **Value:** a concrete identity-boundary lesson — never let an agent reuse your real session.

### L. Integrations vault + OAuth (store tokens for Gmail, Calendar, etc.)
- **New class:** secrets management, **over-broad OAuth scopes**, token theft.
- **Exploit:** injection exfiltrates stored tokens; an over-scoped Gmail grant lets the agent do far more than send.
- **Patch:** least-privilege scopes (send-only vs full mailbox), encrypted secret store, short-lived tokens, never expose tokens to the model.
- **Value:** concrete least-privilege + JIT-access story.

### M. Unattended scheduling (cron — runs while you sleep)
- **New class:** removal of oversight amplifies everything; persistence fires unattended.
- **Exploit:** a stored injection (from C or H) triggers on the next scheduled run with nobody watching.
- **Patch:** no irreversible actions in autonomous mode; queue them for later approval; tighter allow-lists when unattended.
- **Value:** shows you reason about blast radius and autonomy.

### N. Multi-user / sharing (a friend can query your coach)
- **New class:** authN/authZ + **tenant isolation** at real scale.
- **Exploit:** user B retrieves user A's notes/memory.
- **Patch:** authenticate users; scope every data access by identity; ABAC on all stores.
- **Value:** the multi-tenant chatbot authorization scenario, for real.

### O. Self-modification (agent edits its own prompt / CLAUDE.md / tools)
- **New class:** **guardrail tampering**, privilege escalation, persistence.
- **Exploit:** injection makes the agent rewrite its own system prompt to drop the untrusted-content rule -> permanent compromise.
- **Patch:** the agent's config/prompt is **read-only** to the agent; changes require you + review; integrity checks. Separate the control plane from the data plane.
- **Value:** advanced and memorable — not commonly considered.

---

## Part 3 — OWASP LLM Top 10 quick map (so you can name the framework)
- Prompt injection (direct/indirect) -> A, H, J, K
- Sensitive information disclosure -> B, E, F, L
- Improper output handling / excessive agency -> C, I, K, M
- Data/model poisoning -> C (memory), H (inbox), auto-ingested articles
- Supply chain -> MCP servers / third-party tools (if you add them)
- System prompt leakage -> F
- Vector/embedding weaknesses -> E (once you add Chroma)

*"We follow established best practice (OWASP LLM Top 10, least privilege, identity as the trust bearer) and design novel controls where none exist yet."*

---

## Part 4 — Messaging channel decision
Use **Gmail**, not Telegram or WhatsApp.
- **Gmail:** short OAuth setup (or SMTP + app password). Adds useful surface (OAuth scopes L, inbox reading H). Recommended.
- **WhatsApp:** requires a Meta Business account, a separate verified number, and template approvals; general-purpose AI bots are restricted on the platform. Too much friction for this.
- **Telegram:** easy, but you preferred Gmail — and Gmail teaches more.

Wherever the build refers to a send channel, use Gmail. Consider adding **H (inbox reading)** early — it's the richest new attack surface and pairs naturally with Gmail send.
