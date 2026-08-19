# Learning Backlog

Personal to-learn list — things I've implemented or reviewed but want to understand deeply
later. Not an audit; open questions are expected and fine to leave unanswered here.

---

## Added 2026-08-11 — the tool-policy engine (commits ce0383e, 447eb06)

Reviewed the A/B patch but can't yet explain it unaided. Three things to understand:

1. **`send_digest` is really gated now.**
   Anchor: `check_policy` at `main.py:239-260`, called from `run_tool` at `main.py:266`.
   Claim: a caller-supplied recipient is checked against `$OWNER_EMAIL` and refused before
   the tool runs, so it's enforced in deterministic code, not model judgment.
   Question to answer later: walk through exactly what happens, line by line, when the
   model tries to send to `attacker@evil.example` — where does it get stopped and what
   string comes back?

2. **The gate is upstream, not in the function.**
   Anchor: `send_digest` body at `main.py:187-191`.
   Claim: the function itself has no recipient check — all protection is in
   `check_policy`/`run_tool` above it. This is "single-layer at the chokepoint, not
   defense-in-depth to the sink."
   Question: what would an attacker need to do to bypass `run_tool` entirely, and what
   second layer inside the function body would stop them?

3. **One engine patches both A and B.**
   Anchor: `tool_policy.json` (the `fetch_url.url_host` allow-list vs. the
   `send_digest.recipient` rule), plus the tool-advertising filter at `main.py:301`.
   Claim: the same policy layer enforces A's source control (which domains `fetch_url`
   may hit) and B's sink control (who `send_digest` may email) — this is the "sources
   first" fix from `PORTFOLIO_PLAN.md`.
   Question: how does `check_policy` handle `fetch_url` differently from `send_digest`,
   and why does `url_host` need special-case code when `recipient` doesn't?

---

## Added 2026-08-11 — Claude Code's own permission-write mechanism (`BUILD_ENV_HARDENING.md` Finding 3)

Reviewed live, not yet understood: `.claude/settings.local.json`'s `allow` array grew by
two entries during this session (`Bash(mkdir -p "build-env/screenshots")`,
`Bash(touch "build-env/screenshots/.gitkeep")`) while `Edit(./.claude/settings.local.json)`
and `Write(./.claude/settings.local.json)` were both denied at the time. The rule behaved
exactly as written — it blocked the `Edit`/`Write` tools — but didn't stop the file from
changing, because something else wrote it.

Question to answer later: what is the actual write path Claude Code uses to persist a
newly-approved permission (a prompt approval turning into a saved `allow` entry), and is it
gate-able from inside `.claude/settings.local.json` at all, or does it require the Layer 2
(OS-level file-permission) fix noted in `BUILD_ENV_HARDENING.md` instead?

---

## Added 2026-08-19 — the `if __name__ == "__main__":` guard and why it makes import-testing safe

Understood in principle, worth re-deriving unaided later: Python code that does real work only
inside functions + behind the `if __name__ == "__main__":` guard can be imported (loaded and
inspected) without executing. My `main.py` is written this way — `load_dotenv`, the API-key
check, and the agent loop are all inside `main()`, so `import main` triggers none of them.
Question to be able to answer cold: what exactly runs during an import vs. what's skipped, and
why does that map so precisely onto "did the folder move work?"

## Added 2026-08-19 — what "module-level code resolves" actually proves (resolved)

`import main` succeeding from `C:\witi-project` on the fresh `.venv` confirms three
module-level things loaded cleanly: the top-of-file imports (packages found in the new venv),
the constants (`MODEL`, `MEMORY_PATH`, etc.), and the tool schemas (`FETCH_URL_TOOL = {...}`
dicts). That's a stronger claim than "the files are present" — it proves the code actually
works against its new paths and new environment, not just that bytes copied. This is why the
import test is the real proof-of-move, not the file-count match.
