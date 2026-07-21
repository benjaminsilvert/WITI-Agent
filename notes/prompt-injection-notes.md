# Prompt injection

Prompt injection is when untrusted content — a web page, a document, an email, a tool
result — contains text crafted to look like instructions, and a model acts on it as if it
came from the developer or user instead of from data.

Two flavors:
- **Direct injection**: the attacker is the one talking to the model directly (a malicious
  user prompt trying to override the system prompt).
- **Indirect injection**: the attacker's text arrives secondhand, through content the agent
  was told to go fetch/read/summarize (a hidden instruction on a web page, inside a PDF, in
  an inbox message). This is the more dangerous case for agents with tools, because the
  model may have write/send capability by the time it encounters the injected text.

Why it's hard to fully prevent: today's models don't have a hard structural boundary between
"instructions" and "data" the way, say, SQL parameterization separates code from values — it's
all just tokens in a context window. Mitigations are about narrowing blast radius rather than
making injection impossible: treat fetched/inbound content as data (not instructions), restrict
which tools are reachable while processing untrusted content, add a human approval gate before
anything irreversible, and use allow-lists for where the agent is even allowed to fetch from.

This is WITI's own flagship vulnerability (see AGENT_SYSTEM_PROMPT.md sections A+B) — build it
vulnerable, exploit it, then harden it.
