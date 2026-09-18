# WITI — Walk-It-Talk-It

**An LLM agent built vulnerable on purpose, attacked, and hardened with code-level
controls — developed inside a purpose-built, network-fenced build environment that
treats the coding agent itself as an adversary.**

WITI is a Claude-powered agent with seven tools: web fetch, notes search, persistent
memory, a progress tracker, an inbox reader, and a digest sender. It shipped with eight
deliberate vulnerabilities (A–H) — indirect prompt injection, data exfiltration,
excessive agency, stored injection, missing data-layer authorization, system-prompt
leakage. Each was demonstrated against the unmodified code, then closed with controls
enforced **in code, not in the prompt**: host/path and recipient allow-lists,
`<untrusted>` data boundaries with marker-breakout neutralization, a deterministic
human-approval gate, GATHER/ACT capability separation, and sensitivity-based retrieval
filtering. A ninth issue — policy denials leaking the allow-list back to the model
(CWE-209) — was found during live testing and fixed. **69 deterministic checks** back
the fixes, and the whole vulnerable and hardened states are both tagged in git so you
can check out either one.

---

### Reviewing this in five minutes? Do these four things.

1. **Read the story:**
   [`docs/walkthrough.md`](docs/walkthrough.md) — one attack chain from injection to fix
   to the flaw I found in my own fix.
2. **Read one write-up end to end:**
   [`attacks/MANUAL_VULN_B2_verbose_denial.md`](attacks/MANUAL_VULN_B2_verbose_denial.md)
   — a v2 control that leaked the very allow-list it was protecting, found live, with the
   leak already sitting unnoticed in a committed, *passing* test log.
3. **Run the proofs:** `python attacks/run_all_verify.py` — eight scripts, no model call,
   no network, no real state touched.
4. **Diff the project against itself:** `git checkout v1-vulnerable-full` vs
   `git checkout v2-hardened-full`.

---

## At a glance

| | |
|---|---|
| Deliberate vulnerabilities built, exploited, and patched | **8** (A–H) |
| Additional vulnerabilities found in my *own* v2 controls | **1** (B2, CWE-209) |
| Deterministic proof scripts / assertions | **8 scripts, 69 checks** |
| Live runs against the real agent, real API, real approval gate | **4** (3 conclusive, 1 inconclusive — recorded as such) |
| Build-environment hardening layers | **4**, with **10** documented findings |
| Git tags for direct before/after checkout | `v1-vulnerable-full`, `v2-hardened-full` |
| Standards mapped | OWASP Top 10 for LLM Applications; OWASP Top 10 for Agentic Applications |

## Why this project exists

Reading about agent security teaches you the vocabulary. Building an agent, attacking it,
and discovering that half your controls don't do what you thought teaches you the
engineering. WITI is the second thing.

Every capability was built weak on purpose (v1), exploited, then hardened (v2), with the
before state frozen in git before any patching started — because a before/after claim you
can't check out is a story, not evidence.

## The method — and why it's the point

**A model refusing an attack is a fact about behavior, not a fix.**

The flagship exploit — a hidden instruction on a fetched page telling the agent to email
private notes to an attacker — was **refused by the model three times**, on code with
literally zero defenses. That non-result set the project's standard:

- **Structural evidence over behavioral evidence.** Most proofs here call the vulnerable
  function directly, with no model in the loop, and show the code itself has no check.
  That result is true on every run, for every model, regardless of what any model decides.
- **Verify at the enforcement layer, never from narration.** When the coding agent claimed
  its permissions had blocked it from reading `.env`, that claim was false — I'd removed
  those rules. Controls get tested with probes that have no opinion of their own.
- **Prove the control discriminates.** Every proof shows the gate saying *no* to the
  attacker **and** *yes* to the legitimate case. A gate that denies everything is an
  outage, not a boundary.
- **Say what the control doesn't cover.** See [Known limitations](#known-limitations) —
  written before anyone asked.

## Before / after, by vulnerability

| # | Weakness (v1) | Fix (v2) | Verify | Write-up |
|---|---|---|---|---|
| A | `fetch_url` had no domain allow-list and no boundary between fetched data and instructions. | Host+path allow-list enforced in code at two independent points; redirects re-checked at every hop; successful output wrapped in `<untrusted>...</untrusted>` markers. | `verify_ab_patch.py`, `verify_path_and_redirect.py`, `verify_a_untrusted_wrap.py`, `verify_marker_breakout.py`, `verify_generic_denials.py` | [`attacks/MANUAL_VULN_A.md`](attacks/MANUAL_VULN_A.md) |
| B | `send_digest`'s recipient was fully caller-controlled — no fixed address, no allow-list. | Recipient checked against a config-defined allow-list (`$OWNER_EMAIL`) at two independent points; a mismatch denies the send. | `verify_ab_patch.py`, `verify_generic_denials.py` | [`attacks/MANUAL_VULN_B.md`](attacks/MANUAL_VULN_B.md) |
| B2 | The v2 policy-denial text itself leaked the allow-list (host, path, recipient) back to the model — found live, not planned. | Every denial returns a fixed generic string to the model; the detail prints to the terminal only; `check_policy` fails closed. | `verify_generic_denials.py` | [`attacks/MANUAL_VULN_B2_verbose_denial.md`](attacks/MANUAL_VULN_B2_verbose_denial.md) |
| C | `append_memory` had no size cap or provenance; `update_tracker` fully overwrote the file on every call. | `append_memory` size-capped (rejects, never truncates) with a `source` field; `update_tracker` append-only, so no destructive code path exists; `read_memory` output wrapped in `<untrusted>` markers. | `verify_v2_cdegh.py` | [`attacks/MANUAL_VULN_C.md`](attacks/MANUAL_VULN_C.md) |
| D | Every tool call the model made executed immediately — no approval step of any kind. | A deterministic, code-level approval gate pauses before `append_memory`/`update_tracker`/`send_digest`; anything but an exact `y` denies. | `verify_v2_cdegh.py` | [`attacks/MANUAL_VULN_DG.md`](attacks/MANUAL_VULN_DG.md) |
| E | `search_notes` had no concept of note sensitivity — it returned full contents on any substring match. | Reads a `sensitivity` front-matter field, defaults to public-only, fails closed on unlabeled notes; `include_private=True` has no path through the tool's API schema. | `verify_v2_cdegh.py` | [`attacks/MANUAL_VULN_E.md`](attacks/MANUAL_VULN_E.md) |
| F | A fake secret sat directly in the system prompt behind a `#` comment and an "internal only" label. | The secret was deleted outright — nothing to relocate, since it was fake. | `verify_f_no_secret.py` | [`attacks/MANUAL_VULN_F.md`](attacks/MANUAL_VULN_F.md) |
| G | The full 7-tool list was passed on every call, regardless of phase — no separation between reading untrusted content and acting. | The loop is split into a GATHER phase (read-only tools only) and an ACT phase (send/write tools only), so the phase that reads untrusted content holds no send/write tool. | `verify_v2_cdegh.py` | [`attacks/MANUAL_VULN_DG.md`](attacks/MANUAL_VULN_DG.md) |
| H | `read_inbox` returned raw message bodies with no untrusted-content boundary. | Output wrapped in `<untrusted>` markers (headers included, since a subject line is as attacker-controlled as a body); unknown senders flagged, not silently trusted or dropped. | `verify_v2_cdegh.py`, `verify_marker_breakout.py` | [`attacks/MANUAL_VULN_H.md`](attacks/MANUAL_VULN_H.md) |

![fetch_url returning a page whose hidden display:none block contains an injected SYSTEM OVERRIDE instruction, inline with the ordinary text and with no untrusted-data boundary](attacks/screenshots/vuln_A_fetch_url_run.png)

*Vuln A in v1: `fetch_url` called directly, no model involved. The `SYSTEM OVERRIDE`
sentence was invisible on the rendered page and comes back indistinguishable from
legitimate content. Both v1 captures predate the environment migration, so they
show the project's original path — evidence is kept as captured rather than
re-staged.*

Terminal captures for the other v1 exploits are in
[`attacks/screenshots/`](attacks/screenshots/).

## Findings: where my own controls were wrong

The patches are the deliverable. These are the part I'd actually want to be judged on —
each one is a control I had written, believed in, and then caught failing.

| Finding | What I believed | What was true |
|---|---|---|
| **Denial text as an oracle** (CWE-209, [write-up](attacks/MANUAL_VULN_B2_verbose_denial.md)) | The allow-list protected the send path. | The *refusal message* handed the allow-listed value back to the model, which offered to retry with it. Anyone able to trigger denials could read the policy back out, one probe at a time — and the leak was already in a committed test log that passed every run, because the test asserted *that* a denial happened, never *what it said*. |
| **Narration is not enforcement** ([Finding 2](BUILD_ENV_HARDENING.md)) | The coding agent was blocked from reading `.env` — it said so. | I had removed those rules. The refusal was model judgment, and the transcript's "Read 1 file" line immediately before it would have read as a successful silent block. Re-tested with a probe (`curl`) that has no disposition to refuse. |
| **The rule named the wrong mechanism** ([Finding 3](BUILD_ENV_HARDENING.md)) | Deny rules on the Edit/Write tools stopped the agent loosening its own permissions. | The permission file grew anyway — the agent persists permissions through its own internal write path, which is neither tool. The rule did exactly what it said and missed entirely. |
| **A causal claim is as unverifiable as a narration** ([Finding 4](BUILD_ENV_HARDENING.md)) | A new rule appearing while Edit/Write were denied meant the boundary was bypassed again. | *I* had hand-edited it, as a human, under a different OS identity. The agent couldn't see who acted, and was about to write that false conclusion into the very document about not recording unsupported conclusions. |
| **Write-deny ≠ protected** ([Finding 10](BUILD_ENV_HARDENING.md)) | ACL-locked control files couldn't be tampered with. | Write was denied; **delete was not.** The restricted account could delete the policy file and rename its parent folder, replacing a locked file wholesale. Test the attacker's goal, not the one operation you assume represents it. |
| **A passing check isn't a proving check** | My exploit verifier reported the exfiltration succeeded. | The model had *mentioned* the attacker's address while explaining it refused to use it, and a substring test called that a hit. Fixed to parse the actual `To:` line. The same defensive-echo trap reappeared later in a different checker. |
| **Hand-counted numbers rot** | A "21/21 passing" claim in my own docs. | The suite had 19 cases; it only reached 21 later by coincidence, which is why nobody noticed. Every script now computes and prints its own `passed/total` from real results. |

![Terminal showing the agent responding to a bare "say ok" request by auto-firing send_digest, update_tracker and append_memory back to back with no approval prompt](attacks/screenshots/vuln_DG_run3_sayok_autofired_writes.png)

*Vulns D and G in v1: the request was `"Say ok"`. The agent auto-fired a send and two
destructive writes, unprompted and ungated. Two earlier runs of the identical code did
nothing dangerous at all — which is the point. Safety that varies run to run isn't a
control.*

## Build environment — the second threat model

WITI's own vulnerabilities are one threat model, where the attacker is anyone who can get
text into the running agent. The environment used to *build* WITI is a separate one, where
the attacker is **the coding agent itself** — via prompt injection, a bug, or an upstream
compromise. It had read access to secrets, write access to its own permission file, and
unrestricted network egress.

Four layers, each built because the previous one failed in an instructive way:

1. **Permission harness** — deny rules on the coding agent's own tooling. Findings 1–4 came
   out of trying to verify them, and concluded that a control bound to a *tool name* can't
   bind to an *actor*.
2. **OS identity + file locks** — a restricted Windows account with `icacls` deny rules on
   the control files and secrets. Verified at the enforcement layer against a **live,
   separately-installed coding agent**, refused by the OS before any tool-permission logic
   ran.
3. **Two-VM Hyper-V sandbox** — a builder VM with no internet route of its own, and a
   dual-homed gateway VM as its only path out. The egress rules live *outside* the machine
   they contain, so a compromised builder can't edit what constrains it.
4. **Network fence** — hand-written nftables on the gateway: default-drop forward chain,
   IPv6 dropped too, and exactly one allow rule (Anthropic's published range, tcp/443).
   Proven two-sided: the same request times out before the rule and returns a normal HTTP
   response after, while everything else still times out.

Details and verification transcripts:
[`docs/build-environment.md`](docs/build-environment.md) (diagram + summary),
[`BUILD_ENV_HARDENING.md`](BUILD_ENV_HARDENING.md) (all ten findings),
[`infra/gateway/nftables.conf`](infra/gateway/nftables.conf) (the exported ruleset).

These are two different identities in two different places — `witi-agent` on the host is
file-locked with no network fence; `builderadmin` on the builder VM is network-fenced with
no file locks. Not the same protection twice, and the README says so rather than letting a
diagram imply it.

## Live runs

[`attacks/LIVE_V2_RESULTS.md`](attacks/LIVE_V2_RESULTS.md) records four runs of the real,
unmodified `main()` against both attack scenarios (inbox injection; web-page injection with
an in-memory-only allow-list bypass), with a real interactive approval gate. Three were
conclusive; one was **inconclusive** — a bypass bug meant the payload never reached the
model — which is recorded as such and produced the harness's best feature: a precondition
asserting the attack payload was actually delivered before any verdict is trusted.

Each run is a single data point, not proof. A model declining to comply, or an operator
declining to approve, on one occasion says nothing about the next payload. **The structural
controls in the table above are the claim; the live runs are context.**

## Verify it yourself

Requires Python 3.10+ (the codebase uses `X | None` type hints); developed against 3.14.

```
python -m venv .venv
.venv\Scripts\activate        # Windows; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
copy .env.example .env        # Windows; cp on macOS/Linux
```

Fill in `ANTHROPIC_API_KEY` and `OWNER_EMAIL` in `.env` — both are required, and `main.py`
exits at startup if either is missing (the latter resolved via `tool_policy.json`'s
`$OWNER_EMAIL` placeholder, so a real address never sits in a committed file).

Run the agent:
```
python main.py
```

Run every proof:
```
python attacks/run_all_verify.py
```

Prints a per-script `passed/total` plus an overall total (currently `69/69 PASS`). That
count is computed from the scripts' own output on each run — **read it from your own run
rather than trusting this number**, since it drifts as scripts are added. Every script is
deterministic: no model call, no network, and no real WITI state file (`memory.json`,
`tracker.md`, `outbox.txt`, `inbox.json`, `notes/`) is read or written — each is isolated
to a temp directory where it needs one. Static config (`tool_policy.json`,
`prompts/system.md`) is read from the real repo, since that's what's under test.

By design, `send_digest` writes to a local `outbox.txt` rather than a live mailbox, so the
exfiltration path can be attacked safely without sending real mail.

## Repo map

```
main.py                  the agent: loop + all 7 tools (v2/hardened)
prompts/system.md        system prompt (no secrets — that was vuln F)
tool_policy.json         the allow-list config the policy engine enforces
attacks/
  MANUAL_VULN_*.md       per-vulnerability write-ups: v1 code, exploit, v2 fix
  verify_*.py            8 deterministic proof scripts (+ committed logs)
  run_all_verify.py      runs all eight, prints computed totals
  live_v2_harness.py     live runs against the real main() (real API, real gate)
  LIVE_V2_RESULTS.md     the four live runs, including the inconclusive one
  screenshots/           terminal captures for the v1 exploits
docs/walkthrough.md          the narrative: one attack chain, start to finish
docs/build-environment.md    build-env diagram, per-layer verification, limitations
BUILD_ENV_HARDENING.md       the four layers and all ten findings, in full
VULN_CATALOG.md              the A–H catalogue + unbuilt extensions + OWASP mapping
AGENT_SYSTEM_PROMPT.md       original design doc: weakness → exploit → patch → principle
STATUS.md                    session-by-session project history
```

## Standards mapping

**OWASP Top 10 for LLM Applications**
- Prompt injection (direct / indirect) → A, H
- Sensitive information disclosure / system-prompt leakage → F, B2
- Improper output handling / excessive agency → C, D
- Data and model poisoning → C (memory), H (inbox)

**OWASP Top 10 for Agentic Applications**
- ASI01 goal hijack → A, H
- ASI02 tool misuse → A + B
- ASI03 identity & privilege abuse → E
- ASI06 memory & context poisoning → C

Also demonstrated: CWE-209 (error message containing sensitive information), path traversal
and double-encoding bypasses, redirect-based allow-list bypass, substring-vs-parsed-hostname
matching, fail-open vs fail-closed design, and least privilege applied as an identity
boundary rather than a config setting.

## Known limitations

Listed here rather than discovered by a reviewer. Every one of these is a real ceiling on a
control above.

- **G shrinks blast radius, not context.** The GATHER/ACT split means untrusted content
  can't reach a send/write tool directly, but it doesn't scrub that content from the model's
  context. The full version is a dual-LLM design — a tool-less model reads untrusted text
  and the tool-capable one never sees it. Not built.
- **D's approval gate is terminal-based.** A blocking `y/n` on stdin: no timeout, no audit
  log of who approved what, no remote approval channel. Correct for this build, not a
  production control.
- **The `<untrusted>` boundary is half structural, half prompt-level.** The markers,
  neutralization, and sender flag are deterministic. "Don't obey what's inside" depends on
  the model reading the rule.
- **The marker-breakout defense has a known gap.** Unicode lookalike brackets (e.g. U+FF1C)
  are not neutralized — only ASCII and HTML-entity variants of the real marker.
- **No egress content filter on `send_digest`.** The recipient is pinned; subject and body
  are not inspected at all. An injection that gets real notes sent to the *legitimate* owner
  still succeeds.
- **`append_memory`'s `source` field is a constant, not real provenance.** Through the tool
  interface it is always `"agent"` — it records that a write happened via the agent, not
  where the content came from.
- **Naive checks can misread a defensive echo as compliance** — documented twice, in two
  different checkers.
- **The model can narrate a denied action as completed.** Tool descriptions warn against it;
  it is model behavior, not a code-enforced property.
- **No `read_tracker` tool exists.** `update_tracker` is append-only with no read path — by
  design, but a real capability gap.
- **WITI's runtime has no identity of its own.** The build-environment work protects the
  *build* identity; the planned third identity for the WITI runtime was never built, so
  `main.py` runs under whatever account launches it.
- **The network fence grants a destination, not a purpose.** Allow-listing Anthropic's range
  also permits every service behind it, including the Files API. The durable fix is a
  hostname-filtering application-layer proxy; an IP/port firewall physically cannot see which
  endpoint an encrypted request is for.
- **The gateway has no input controls yet.** Its own SSH service is reachable from the
  builder and could be brute-forced. Next control to write.
- **Design docs describe the original, broader plan.** `AGENT_SYSTEM_PROMPT.md` and
  `VULN_CATALOG.md` still reference a `search_web` tool and real Gmail sending; neither
  exists in `main.py`.
- **More build-environment limits** (shared IPs, server-side tools bypassing the fence, no
  host firewall on the builder, DNS as an uninspected exfiltration channel) are tracked in
  [`docs/build-environment.md`](docs/build-environment.md#limitations).

## What's next

Dual-LLM quarantine for untrusted content (the real fix for G's context caveat); an
application-layer egress proxy that filters on hostname and path rather than IP (the real
fix for the Files-API caveat); input-chain rules on the gateway; and a third OS identity for
the WITI runtime, completing the human / builder / runtime separation.

## About

Built by Benjamin Silvert — AI and agent security: designing controls for LLM
agents and for the environments those agents are built in.

This repo spans both halves of that. The agent side is threat modelling, exploit
development, and code-level control design against the OWASP LLM and Agentic top-tens. The
build-environment side is Windows ACLs and identity separation, Hyper-V, virtual
networking, hand-written nftables egress control, and package-signature verification —
each layer verified at the enforcement layer rather than accepted from a config file or a
model's own account of itself.

silvert.ben@gmail.com — happy to walk through any finding above,
especially the ones where I was wrong.