# Session Protocol

**A copy that can silently disagree with the truth is a liability** — stable reference goes
in the knowledge base, living state is attached fresh, and the two must never both hold the
same file.

This records how the Claude project chat (no memory between sessions) stays in sync with
this repo, and which files live where.

---

## Section 1 — Start of session (paste to the CHAT, not Claude Code)

Attach the current `STATUS.md` and `LEARNING_BACKLOG.md`, then paste:

> New session. Here's where we left off — read these and give me a 5-line summary of where
> things stand and what's pending, then wait.

These two files are attached fresh from disk each session rather than kept in the project
knowledge base, so they're never stale.

---

## Section 2 — End of session (paste to CLAUDE CODE)

> End-of-session wrap. Update STATUS.md with what changed and what's pending; append any new
> to-learn items to LEARNING_BACKLOG.md; show me the diffs; then commit everything with a
> descriptive message and confirm with git status that the working tree is clean.

The clean-tree check is the fail-safe — positive confirmation nothing was left uncommitted.
`STATUS.md`, not the commit log, is the source of truth the next session reads.

---

## Section 3 — Where each file lives, and why

**Project knowledge base (stable reference, rarely changes):** `AGENT_SYSTEM_PROMPT.md`,
`VULN_CATALOG.md`, `CLAUDE.md`, `PORTFOLIO_PLAN.md`, `BUILD_ENV_HARDENING.md`,
`SESSION_PROTOCOL.md`, the `MANUAL_VULN_*` files, the two `README.md` files. These give the
chat durable context without re-explaining the project. Replace a file here only when it
gets a real revision.

**Attached fresh to the chat each session (living state, changes every session):**
`STATUS.md`, `LEARNING_BACKLOG.md`, and `main.py` when the session's work is code-focused.
Never kept in the knowledge base, because a constantly-changing file there goes stale
immediately and can silently contradict the truth.

**Git repo only (evidence for human reviewers, not useful to the chat):** all screenshots.
They belong in the portfolio for a hiring manager to see; the chat gets the same information
as text from the `MANUAL_VULN_*` write-ups.
