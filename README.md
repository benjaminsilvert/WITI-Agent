# WITI

## TL;DR

WITI is a security research project. I built an AI agent with seven tools, planted eight weaknesses in it, attacked each one, and then hardened it.

The agent's features are deliberately minimal. Each tool does just enough to create a real attack surface, which keeps the focus on how agents can fail and how to secure them. Even with that little functionality, there was a lot to break and a lot to fix.

The project has two parts:

- **Securing the agent.** The weaknesses sit in its tools, its main loop and its system prompt. The main attack chain turns a hidden instruction on a web page into the leak of private notes, the same attack class as EchoLeak (CVE-2025-32711). I demonstrated each weakness and fixed it in code, then found a ninth problem in one of my own fixes: the refusal message leaked the allow-list it was protecting.
- **Securing the build environment.** Building WITI with Claude Code made me realize that the coding agent could also become an adversary, through prompt injection, a bug, or a compromised update. So I built and tested two ways to contain a coding agent: a separate Windows account with locked files, and a VM sandbox behind a firewall.

The main lesson of the project: security controls for agents need to be enforced deterministically, in the harness and the environment around it, where the model can't reach them. A model’s behavior can change from run to run. In WITI, I sent the same harmless prompt three times. The model gave a plain reply the first two times, and on the third it made destructive writes on its own. A control in code gives the same answer every time, so that’s where the rules belong.

This held for the coding assistant too: its own permission rules could be sidestepped, so the real limits had to live in the operating system and the network.

Every attack and every fix is checked by automated Python scripts, runnable in one command.

---

*The rest of this page goes into more detail.*

## How the attack surface grew

Each tool I added gave an attacker something new.

IDs: LLM = OWASP Top 10 for LLM Applications; ASI = OWASP Top 10 for Agentic
Applications.

| Added | What it gave an attacker | Weakness (v1) | Fix (v2) |
|---|---|---|---|
| `fetch_url` | A way to get text into the agent from any web page | **[VULN A](attacks/VULN_A.md): Indirect prompt injection** (LLM01, ASI01). No limit on which sites; no boundary between fetched data and instructions | Allow-list of sites and paths, rechecked on redirects; fetched text marked as untrusted |
| `search_notes` | Private data worth stealing | **[VULN E](attacks/VULN_E.md): Sensitive data disclosure** (LLM02, ASI03). No concept of public or private notes; any match returned the full note | Public/private labels added; search returns public notes only; unlabeled notes treated as private (fail closed) |
| `read_memory`, `append_memory`, `update_tracker` | Persistence between runs, and a way to destroy data | **[VULN C](attacks/VULN_C.md): Memory poisoning and excessive agency** (LLM04, LLM06, ASI06, ASI02). Memory had no size limit; every tracker update overwrote the whole file | Memory writes size-limited and approval-gated; memory marked untrusted when the agent reads it back; tracker limited to append-only |
| `send_digest` | A way to send data out | **[VULN B](attacks/VULN_B.md): Data exfiltration** (LLM06, ASI02). The agent could pick any recipient | Recipient checked against an allow-list set from `OWNER_EMAIL` in `.env` |
| My fix for VULN B | A way to read the allow-list back out | **[VULN B2](attacks/VULN_B2.md): Error message leaks config** (CWE-209, LLM02). Denials told the agent which address was allowed | Denial messages standardized and sanitized |
| `read_inbox` | A second way in, without the victim visiting anything | **[VULN H](attacks/VULN_H.md): Zero-click indirect prompt injection** (LLM01, ASI01). Message text came back looking like instructions | Marked untrusted; unknown senders flagged |
| Main loop | No one to stop a hijacked agent | **[VULN D](attacks/VULN_DG.md): No human-in-the-loop** (LLM06). Actions ran with no approval | Approval prompt before any write or send |
| Main loop | Send and write tools available while reading untrusted text | **[VULN G](attacks/VULN_DG.md): Excessive agency** (LLM06, ASI02). Every tool was available at every step | Reading and acting split into separate phases |
| System prompt | A secret the model could simply repeat | **[VULN F](attacks/VULN_F.md): System prompt leakage** (LLM07). A fake secret was sitting in it | Deleted |

### The main attack chain

1. An attacker hides an instruction on a web page, where a human visitor wouldn't see it.
2. I ask WITI to summarize that page. `fetch_url` brings the hidden instruction back
   looking like any other text (VULN A).
3. The agent follows it and searches my notes, which returns the private ones too (VULN E).
4. It sends them to the attacker with `send_digest` (VULN B).
5. Nothing stops it: there's no approval prompt (VULN D), and the send tool is available
   while the agent is reading the page (VULN G).

The same chain works through the inbox (VULN H), without the victim visiting anything.

In v2, every step has its own control: the page must be on the allow-list and comes back
marked as untrusted, search returns only public notes, sends only go to the owner, every
send needs my approval, and the phase that reads the page has no send tool.

[Full step-by-step walkthrough](docs/walkthrough.md)

It's a simplified version of EchoLeak (CVE-2025-32711), a 2025 vulnerability in
Microsoft 365 Copilot where a single crafted email could make Copilot leak the
user's data to an attacker. It relied on the same three ingredients. The
difference is that EchoLeak had to get past Copilot's defenses, and WITI v1 had
none. ([Aim Labs' write-up](https://www.catonetworks.com/blog/breaking-down-echoleak/))

![fetch_url returning a page with a hidden SYSTEM OVERRIDE instruction mixed in with the normal text](attacks/screenshots/vuln_A_fetch_url_run_annotated.png)

*VULN A in v1: `fetch_url` called directly, with no model involved. The hidden
`SYSTEM OVERRIDE` text comes back mixed in with the normal page text.*

### The bug in my own fix

During a live test, a send to a blocked address was denied, but the denial message told
the model which address *was* allowed, and the model offered to retry with it. Anyone who
can trigger denials could read my access rules back out, one attempt at a time. This is a
known bug class (CWE-209: error messages that reveal sensitive information). Now every
denial returns the same generic message to the model, and the details go only to my
terminal.

[Full write-up](attacks/VULN_B2.md)

## Why I didn't rely on live attacks

When I ran the main attack against the real model (a hidden instruction on a web
page telling the agent to send my private notes to an attacker), the model
refused three times, even though the code had no defenses at all. That doesn't
make the code safe. Another model or another prompt could behave differently.

In another test I sent the same request ("Say ok") to the same code three times.
Only one run did something dangerous: it sent a digest and made two destructive
writes without being asked.

![The agent responding to "say ok" by firing send_digest, update_tracker and append_memory with no approval prompt](attacks/screenshots/vuln_DG_run3_sayok_autofired_writes_annotated.png)

*VULNs D and G in v1: asked only to "Say ok," the agent sent a digest and made
two destructive writes with no approval prompt.*

So most of my proofs call the vulnerable function directly and show that the
code has no check. That result doesn't depend on what the model decides.

## How I tested it

- **Proof scripts:** 8 scripts, 69 checks. Run them all with
  `python attacks/run_all_verify.py`. They don't call a model or use the
  network, and they work on temporary copies of the agent's data files.
- **Live runs:** 4 runs of the real agent against the real API, with me answering
  the approval prompts. Three gave a clear result. One didn't, because of a bug
  in my test harness. These are examples, not proof.
  ([results](attacks/LIVE_V2_RESULTS.md))
- **Before and after:** `git checkout v1-vulnerable-full` and
  `git checkout v2-hardened-full`.

## Securing the build environment

Claude Code is third-party software that had access to my secrets, read untrusted
content from the web, and could make network requests. That's the same combination
as WITI, which makes it a supply-chain risk (LLM03, ASI04). So I treated it as a
possible adversary and tried to contain it, moving to a stronger control each time
the last one fell short.

1. **Claude Code's own permission file.** I started with the obvious control: deny
   rules in `.claude/settings.local.json`. A rule blocking `curl` worked, but the same
   request through PowerShell's `Invoke-WebRequest` wasn't blocked at all. I blocked
   that too, but PowerShell has other names for the same command and can reach the
   network without any command name. Blocking commands one name at a time was a
   losing game, so I moved the control below the agent.
2. **A separate Windows account** (`witi-agent`) with file permissions that block it
   from changing its own controls or reading secrets. I tested it against a second
   copy of Claude Code running under that account. Windows refused it before Claude
   Code's own permission checks even ran.
3. **A two-VM sandbox** in Hyper-V. The builder VM has no internet access of its
   own. All its traffic goes through a gateway VM running a firewall I wrote in
   nftables, which blocks everything except Anthropic's API. The firewall lives on a
   separate machine, outside the builder's control.

The account and the sandbox were never combined. The Claude Code that built WITI ran
under my normal account, outside both of them.

This part produced ten findings. One example: a file the restricted account couldn't
edit, it could still delete and replace.

Details: [`BUILD_ENV_HARDENING.md`](BUILD_ENV_HARDENING.md) and
[`docs/build-environment.md`](docs/build-environment.md).

## What I learned

1. **Control the environment, not the tool names.** A rule that names a command loses
   to the next command that does the same thing. Identity and network controls don't
   care what the command is called.
2. **A refusal isn't a fix.** The model refused my main attack three times on code with
   no defenses. The hole was still there, and a more gullible model would walk
   straight through it.
3. **A control the agent can reach is a control it can turn off.** That's why the
   firewall runs on a separate VM instead of inside the machine it contains.
4. **The strongest control is a capability the agent never has.** A rule that blocks
   an action can be routed around. A tool that doesn't exist can't be.
5. **Plan for blast radius.** Once an agent can run code, you can't list everything it
   might do. Containment, and cutting outbound traffic above all, makes a bad action
   not matter.
6. **Check the control, not what the agent says about it.** Claude Code told me its
   settings blocked it from reading `.env`. I had already removed those rules. It had
   just decided not to.
7. **Find the chokepoint.** One policy check on every tool call broke several attack
   chains at once, so I fixed the chain rather than each symptom.
8. **A passing test only proves what it tests.** The VULN B2 leak sat in a committed
   test log that passed every run, because the test checked that a denial happened,
   not what it said.

## What isn't fixed

- Untrusted text is marked, but whether the model ignores instructions inside it
  still depends on the model. The full fix would have a separate model with no
  tools read untrusted content (Simon Willison's dual-LLM pattern). I didn't
  build it.
- `send_digest` checks who the message goes to, but not what's in it.
- The approval prompt is a `y/n` in the terminal, with no timeout or log.
- The untrusted-text markers can be faked with lookalike Unicode characters.
- The firewall allows Anthropic's whole address range, which includes services
  other than the API.
- The gateway VM never got rules for traffic aimed at itself, so its login service
  (SSH) was reachable from the builder. In principle, a compromised builder could
  brute-force that login and rewrite the firewall meant to contain it.
- More build-environment limits are listed in
  [`docs/build-environment.md`](docs/build-environment.md#limitations).

## Who did what

I worked with two AI tools. A Claude chat acted as a tutor and reviewer: it
helped me plan each step and reviewed the results I brought back. Claude Code
wrote the Python code, the tests, and the write-ups in `attacks/` and `docs/`.

I decided what to build and which fixes to accept, ran every attack and live
test, approved or denied each action during live runs, reviewed the changes,
and edited the policy and secrets files by hand. I set up the Windows account,
both VMs, and the firewall myself. Some findings came from my own tests. Others
came from Claude reviewing output I brought back.

## Repo map

```
main.py                      the agent: main loop and all 7 tools (v2)
prompts/system.md            system prompt
tool_policy.json             allow-list config the code enforces
attacks/VULN_*.md            one write-up per weakness: v1 code, exploit, v2 fix
attacks/verify_*.py          the 8 proof scripts
attacks/run_all_verify.py    runs all proofs and prints the totals
attacks/LIVE_V2_RESULTS.md   the 4 live runs
attacks/screenshots/         terminal captures of the v1 exploits
docs/walkthrough.md          one attack chain, start to finish
docs/build-environment.md    build-environment diagram and limitations
BUILD_ENV_HARDENING.md       all ten build-environment findings
infra/gateway/nftables.conf  the gateway firewall rules
```

## Setup

Requires Python 3.10+.

```
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env        # macOS/Linux: cp
```

Fill in `ANTHROPIC_API_KEY` and `OWNER_EMAIL` in `.env`. The proof scripts also
need `OWNER_EMAIL`.

```
python main.py                     # run the agent
python attacks/run_all_verify.py   # run the proofs
```

## Contact

Benjamin Silvert, silvert.ben@gmail.com