# Manual exploit of vuln B2 — send_digest/fetch_url denial text leaked the allow-list

## Discovery
Found live during an approval-gate practice run of the real agent, not through a
planned attack: the model attempted `send_digest` to `owner@example.com` — a stale
placeholder address it had picked up from old memory entries, not the account's real
address. `check_policy` denied the call (via `run_tool`'s dispatch path), and the
reason text returned to the model, verbatim, was:
```
Denied by policy: send_digest.recipient = 'owner@example.com' not in allow-list (['[REDACTED-OWNER-ADDRESS]'])
```
`[REDACTED-OWNER-ADDRESS]` stands in for the real account address that the policy
allow-lists and that leaked into this denial text, while `owner@example.com` above is
only the stale placeholder the model itself had tried to send to. The model then
offered to retry the send using the leaked address.

## Classification
**CWE-209 — Generation of Error Message Containing Sensitive Information**, and
**OWASP LLM02 — Sensitive Information Disclosure** (per the OWASP Top 10 for LLM
Applications). This is **not credential disclosure** -- no password, API key, or
token was exposed. What leaked was **security configuration**: the contents of an
access-control allow-list, disclosed through the tool's own error/denial path.

## Impact
Anyone able to influence what the model does with a tool result -- directly, or
indirectly via prompt injection in a fetched page or inbox message -- can trigger
denials on purpose and read the policy back out of the "why denied" text:
candidate hosts, path prefixes, or recipient addresses, one probe at a time, with no
elevated access required. This is reconnaissance against the access-control
configuration itself, using the tool's own refusal as the oracle.

## Before / after code
From the actual fix commit (`git show 3bcf1e8 -- main.py`):

**Before:**
```python
def run_tool(name: str, tool_input: dict) -> str:
    allowed, reason = check_policy(name, tool_input)
    if not allowed:
        print(f"[POLICY DENY] {name}({tool_input}) -> {reason}")
        return f"Denied by policy: {reason}"
```
```python
def send_digest(recipient: str, subject: str, body: str) -> str:
    allowed = (TOOL_POLICY or {}).get("tools", {}).get("send_digest", {}).get("args", {}).get("recipient")
    if not allowed:
        return "Denied by policy: no recipient allow-list configured for send_digest."
    allowed_values = allowed if isinstance(allowed, list) else [allowed]
    if recipient not in allowed_values:
        return f"Denied by policy: recipient '{recipient}' not in allow-list for send_digest ({allowed_values})."
```
```python
def check_policy(name: str, tool_input: dict) -> tuple[bool, str]:
    """Check a proposed tool call against TOOL_POLICY. Returns (allowed, reason)."""
    rule = TOOL_POLICY.get("tools", {}).get(name)
```
```python
        if not allowed:
            raise urllib.error.HTTPError(newurl, code, f"Redirect blocked by policy: {reason}", headers, fp)
```

**After:**
```python
def run_tool(name: str, tool_input: dict) -> str:
    allowed, reason = check_policy(name, tool_input)
    if not allowed:
        print(f"[POLICY DENY] {name}({tool_input}) -> {reason}")
        return "Denied by policy: this action is not permitted."
```
```python
def send_digest(recipient: str, subject: str, body: str) -> str:
    allowed = (TOOL_POLICY or {}).get("tools", {}).get("send_digest", {}).get("args", {}).get("recipient")
    if not allowed:
        print(f"[POLICY DENY] send_digest(recipient={recipient!r}) -> no recipient allow-list configured for send_digest")
        return "Denied by policy: this action is not permitted."
    allowed_values = allowed if isinstance(allowed, list) else [allowed]
    if recipient not in allowed_values:
        print(f"[POLICY DENY] send_digest(recipient={recipient!r}) -> recipient '{recipient}' not in allow-list for send_digest ({allowed_values})")
        return "Denied by policy: this action is not permitted."
```
```python
def check_policy(name: str, tool_input: dict) -> tuple[bool, str]:
    """Check a proposed tool call against TOOL_POLICY. Returns (allowed, reason)."""
    if TOOL_POLICY is None:
        return False, "no policy loaded"

    rule = TOOL_POLICY.get("tools", {}).get(name)
```
```python
class _RedirectPolicyDenied(urllib.error.HTTPError):
    """Raised by _PolicyRedirectHandler when a redirect target fails the policy check."""

# ...
        if not allowed:
            raise _RedirectPolicyDenied(newurl, code, f"Redirect blocked by policy: {reason}", headers, fp)
```
Four changes, one root cause: every place a denial reason could become a **tool
result** now returns the fixed generic string
`"Denied by policy: this action is not permitted."` and prints the detail to the
terminal only; `check_policy` fails closed instead of crashing when no policy is
loaded; and a dedicated `_RedirectPolicyDenied` exception type lets `fetch_url` tell
a policy-blocked redirect apart from a genuine transport error, so that path's denial
text is generic too, instead of leaking through `fetch_url`'s
`except Exception as exc: return f"Error fetching {url}: {exc}"` catch-all.

## Proof
`attacks/verify_generic_denials.py` — 9/9 PASS, log at
`attacks/verify_generic_denials_log.txt`. Covers: policy denial via `run_tool` for
`send_digest`/`fetch_url` (host and path), the two direct-call in-function guards,
the redirect-denial path specifically, `TOOL_POLICY = None` failing closed with no
exception, and an explicit check that the detailed reason still reaches the
terminal via `print()` even though the tool result is generic.

**The leak had already been recorded in a committed log without anyone noticing.**
`attacks/verify_a_untrusted_wrap_log.txt`, line 2, before this fix (commit
`4b25761`, the version immediately preceding the fix commit `3bcf1e8`):
```
[PASS] disallowed host -> Denied by policy, unwrapped: result="Denied by policy: host 'evil-exfil.example' not in allow-list for fetch_url (['claude.com', 'www.anthropic.com'])"
```
Same line, after this fix (commit `3bcf1e8`):
```
[PASS] disallowed host -> Denied by policy, unwrapped: result='Denied by policy: this action is not permitted.'
```
The test correctly asserted "a denial happened, and it's unwrapped" both times --
it never asserted anything about the *content* of the denial, so the leak sat
committed to git, passing every run, until this was found live rather than by
re-reading old test output.

## Live confirmation
`attacks/LIVE_V2_RESULTS.md`, the inbox run
(`live_v2_inbox_20260917T092103Z_log.txt`): the model attempted four `fetch_url`
calls to hosts outside the allow-list during that run, and every one of them came
back as only `"Denied by policy: this action is not permitted."` -- no host, path,
or recipient value in any of the four.

## Limits
This fixes what the **model** sees, not what a human watching the terminal sees --
`[POLICY DENY] ...` lines with the full detail are printed by design, for the
operator. If that terminal output itself is captured somewhere an untrusted party
can read it (a shared log, a screen share, a misconfigured log-shipping pipeline),
the same information is still there. The fix narrows the leak to one channel
(model-facing tool results); it does not claim the detail is secret everywhere.

## Summary
**What was built:** a fix, found live rather than planned, that stops every
policy-denial code path in `main.py` from returning its detailed reason (host
allow-list, path prefixes, recipient address) as a tool result. **The issue:** four
separate denial paths -- `run_tool`'s dispatch-level denial, `fetch_url`'s and
`send_digest`'s in-function guards, and a denied redirect's exception message --
all leaked the same class of security-configuration detail to the model, and one
instance of this had been sitting, unnoticed, in a committed log. **The fix:** every
model-facing denial now returns a single fixed generic string, the detail moved to a
terminal-only `print()`, a dedicated exception type closes the redirect-specific
leak path, and `check_policy` fails closed instead of crashing when no policy is
loaded -- proven by `verify_generic_denials.py` (9/9) and confirmed live in
`attacks/LIVE_V2_RESULTS.md`.
