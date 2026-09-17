# WITI — Walk-It-Talk-It

WITI is a deliberately vulnerable AI agent: a small Claude-powered assistant (web
fetch, notes search, persistent memory, a progress tracker, an inbox reader, and an
email-digest sender) built with eight intentional vulnerabilities (A–H), then
exploited against its own unmodified code, then hardened. Every claim below —
weakness, fix, and proof — is backed by a script or transcript in `attacks/`, not
narrative alone.

## Before / after, by vulnerability

| # | Weakness (v1) | Fix (v2) | Verify | Write-up |
|---|---|---|---|---|
| A | `fetch_url` had no domain allow-list and no boundary between fetched data and instructions. | Host+path allow-list enforced in code at two independent points; successful output wrapped in `<untrusted>...</untrusted>` markers. | `verify_ab_patch.py`, `verify_path_and_redirect.py`, `verify_a_untrusted_wrap.py`, `verify_marker_breakout.py`, `verify_generic_denials.py` | [`attacks/MANUAL_VULN_A.md`](attacks/MANUAL_VULN_A.md) |
| B | `send_digest`'s recipient was fully caller-controlled — no fixed address, no allow-list. | Recipient checked against a config-defined allow-list (`$OWNER_EMAIL`) at two independent points; a mismatch denies the send. | `verify_ab_patch.py`, `verify_generic_denials.py` | [`attacks/MANUAL_VULN_B.md`](attacks/MANUAL_VULN_B.md) |
| B2 | The v2 policy-denial text itself leaked the allow-list (host, path, recipient) back to the model — found live, not planned. | Every denial now returns a fixed generic string to the model; the detail prints to the terminal only; `check_policy` fails closed. | `verify_generic_denials.py` | [`attacks/MANUAL_VULN_B2_verbose_denial.md`](attacks/MANUAL_VULN_B2_verbose_denial.md) |
| C | `append_memory` had no size cap or provenance; `update_tracker` fully overwrote the file on every call. | `append_memory` size-capped with a `source` field; `update_tracker` append-only; `read_memory` now wraps output in `<untrusted>` markers too. | `verify_v2_cdegh.py` | [`attacks/MANUAL_VULN_C.md`](attacks/MANUAL_VULN_C.md) |
| D | Every tool call the model made executed immediately — no approval step of any kind. | A deterministic, code-level approval gate pauses before `append_memory`/`update_tracker`/`send_digest`; anything but an exact `y` denies. | `verify_v2_cdegh.py` | [`attacks/MANUAL_VULN_DG.md`](attacks/MANUAL_VULN_DG.md) |
| E | `search_notes` had no concept of note sensitivity — it returned full contents on any substring match. | Reads a `sensitivity` front-matter field, defaults to public-only, fails closed on unlabeled notes; `include_private=True` has no path through the tool's API schema. | `verify_v2_cdegh.py` | [`attacks/MANUAL_VULN_E.md`](attacks/MANUAL_VULN_E.md) |
| F | A fake secret sat directly in the system prompt behind a `#` comment and an "internal only" label. | The secret was deleted outright — nothing to relocate, since it was fake. | `verify_f_no_secret.py` | [`attacks/MANUAL_VULN_F.md`](attacks/MANUAL_VULN_F.md) |
| G | The full 7-tool list was passed on every call, regardless of phase — no separation between reading untrusted content and acting. | The loop is split into a GATHER phase (read-only tools only) and an ACT phase (send/write tools only). | `verify_v2_cdegh.py` | [`attacks/MANUAL_VULN_DG.md`](attacks/MANUAL_VULN_DG.md) |
| H | `read_inbox` returned raw message bodies with no untrusted-content boundary. | Output wrapped in `<untrusted>` markers; senders not on an allow-list are flagged, not silently trusted (still included, not dropped). | `verify_v2_cdegh.py`, `verify_marker_breakout.py` | [`attacks/MANUAL_VULN_H.md`](attacks/MANUAL_VULN_H.md) |

## How to verify

```
python attacks/run_all_verify.py
```

Runs all eight deterministic scripts and prints a per-script `passed/total` line
plus an overall total (currently `69/69 PASS`). That count is computed by the
script from its own subprocess output each time it runs — read it from your own
run rather than trusting this number, since it will drift as scripts are added.
Every script here is deterministic: no model call, no network, and no real WITI
state file (`memory.json`, `tracker.md`, `outbox.txt`, `inbox.json`, `notes/`) is
read or written — each is isolated to a temp directory where the test needs one.
Static config (`tool_policy.json`, `prompts/system.md`) is read from the real repo,
since that's what's under test.

## Build environment

WITI's own vulnerabilities (above) are one threat model; the environment used to
*build* WITI is a separate one, with its own hardening: a coding-agent permission
harness, OS-level file locks on a restricted build identity, and a two-VM
network-fenced sandbox for that identity's own Claude Code install. See
[`docs/build-environment.md`](docs/build-environment.md) for a summary with a
diagram, [`BUILD_ENV_HARDENING.md`](BUILD_ENV_HARDENING.md) for the full findings
and verification transcripts, and
[`infra/gateway/nftables.conf`](infra/gateway/nftables.conf) for the exported
firewall ruleset itself.

## Live runs

[`attacks/LIVE_V2_RESULTS.md`](attacks/LIVE_V2_RESULTS.md) records four runs of the
real, unmodified `main()` against both attack scenarios (inbox injection, web-page
injection with an in-memory-only allow-list bypass), with a real interactive
approval gate. As that document says of itself: each run is a single data point,
not proof — a model declining to comply (or an operator declining to approve) on
one occasion says nothing about the next payload or the next approval decision. The
structural controls in the table above are what's meant to hold regardless of any
single run's outcome.

## Known limitations

- **Naive checks can misread a defensive echo as compliance.** A model quoting or
  flagging an attacker's address while explaining that it declined to use it can
  trip a plain substring check — verification needs to check what a value was
  *used as*, not just whether it appears in the output.
- **The model narrating a denied action as completed.** A tool call blocked by the
  approval gate or the policy layer could still be described to the user as done;
  the approval-gated tools' own descriptions were updated to warn against this, but
  it's a model-behavior risk, not something enforced in code.
- **No `read_tracker` tool exists.** `update_tracker` is append-only and there is
  no way for the model to read the tracker's current contents back — by design,
  but worth naming as a real capability gap, not an oversight.
- **The `<untrusted>` marker-breakout defense has a known gap.** Unicode
  lookalike brackets (e.g. U+FF1C) are not neutralized, only ASCII and
  HTML-entity variants of the real marker.
- **G shrinks blast radius, not context.** Splitting the run into GATHER/ACT
  phases means untrusted content can no longer reach a send/write tool directly,
  but it doesn't scrub that content from the model's context — a fetched page or
  inbox message is still sitting there during the GATHER phase.
- **No egress content filter on `send_digest`.** The recipient is pinned to an
  allow-list; the subject and body are not inspected at all. An injected
  instruction that gets the agent to email real notes or other sensitive content
  to the legitimate owner would still succeed.
- **Build-environment limitations** (shared IPs, server-side tools bypassing the
  network fence, no host firewall on the builder, DNS as an uninspected
  exfiltration channel, and more) are tracked in
  [`docs/build-environment.md`](docs/build-environment.md#limitations) rather than
  repeated here.
