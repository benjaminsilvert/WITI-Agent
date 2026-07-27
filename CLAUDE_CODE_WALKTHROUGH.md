# Building WITI in Claude Code — step by step

*You have the Claude desktop app and you'll pay for API usage. You've never used Claude Code. This walks you from zero to a working, deliberately-vulnerable WITI agent you can then harden. Let Claude Code write the actual Python — your job is to drive it, approve steps, and understand what it produces.*

---

## Part 0 — One-time setup (do this first)

1. **Confirm your subscription.** Claude Code runs on a paid Claude plan (Pro or Max). You already have the desktop app, so you're set.
2. **Get an Anthropic API key for the agent** (separate from your Claude subscription — this is the per-use part you pay for):
   - Go to console.anthropic.com, sign in, open **API Keys**, create a key, copy it (starts with `sk-ant-...`).
   - Under **Billing**, add a small amount of credit (a few dollars is plenty).
3. **Get a Gmail sending credential** (you'll only need this when you reach the send step, not on day one):
   - Simplest route — an **app password**: in your Google Account, turn on 2-Step Verification, then create an App Password for "Mail" and save it. You'll send via SMTP using your Gmail address + that app password.
   - More secure/scoped route — **Gmail API OAuth** (send-only scope). You can start with the app password and switch later; that switch is itself vuln L (over-broad scopes) to study.
4. **Git (Windows only):** if you're on Windows, install Git for Windows first. Most Macs already have Git. (The desktop app isn't available on Linux.)

---

## Part 0.5 — Put the files in place (important)

Nothing exists on your computer yet — the files I gave you are just downloads in the chat until you place them. There is no folder anywhere until you make one.

5. **Download** the four project files from this chat: `CLAUDE.md`, `AGENT_SYSTEM_PROMPT.md`, `VULN_CATALOG.md`, `CLAUDE_CODE_WALKTHROUGH.md`.
6. **Create an empty folder** called `witi-agent` somewhere easy to find (your Desktop is fine).
7. **Move all four files into that folder.** That folder is your project. Claude Code will only read/write here once you point a session at it (next part), and it asks permission before creating or editing anything.

---

## Part 1 — Get oriented in Claude Code (basics)

8. Open the desktop app and click the **Code** tab.
9. Click **+ New session** (or press **Cmd/Ctrl+N**). The first time, you'll be asked to log in — do that.
10. When prompted, point the session at the **`witi-agent` folder** you made in Part 0.5.
11. Look around — the desktop app gives you, in one window:
    - the **chat** (where you talk to Claude Code),
    - an **integrated terminal** (toggle with **Ctrl+`**) for running commands,
    - a **file editor** and a **diff viewer** to review changes,
    - a **side chat** — ask questions ("what is SMTP?", "why is this a risk?") **without derailing** your main build thread. This is the answer to "do I have to leave to ask questions?" — you don't.
12. Two habits to learn now:
    - **Plan mode (Shift+Tab):** makes Claude propose a plan before it changes anything. Use it for every non-trivial step.
    - **Approve before it acts:** Claude Code asks permission before editing files or running commands. Read what it's about to do, then approve.

---

## Part 2 — Load the plan (basics)

13. Confirm the four files are sitting in the folder (from Part 0.5).
14. In the chat, say: *"Read CLAUDE.md, AGENT_SYSTEM_PROMPT.md, and VULN_CATALOG.md, then explain the WITI project and the build order back to me in your own words. Don't write any code yet."*
15. Confirm it understood the **critical rule**: when you ask for a v1/vulnerable build, it must NOT auto-add security. If it glosses over that, remind it.

---

## Part 3 — Scaffold the minimal v1 (basics -> intermediate)

16. Ask: *"Using plan mode, scaffold a minimal Python project: a virtual environment, install `anthropic` and `python-dotenv`, a `.env` for ANTHROPIC_API_KEY (git-ignored), and a `main.py` that calls the Messages API with tool use, exposing a single `fetch_url` tool, then prints a short digest. Show me the plan before implementing."*
17. Review the plan, approve it, let it build. When it creates `.env`, open it in the editor and paste your key: `ANTHROPIC_API_KEY=sk-ant-...`
18. In the integrated terminal, run it (Claude Code will give the exact command, usually `python main.py` inside the venv). If it errors, paste the error back into the chat and let Claude Code fix it — this back-and-forth is normal and is how you learn.
19. Once it runs and prints a digest, commit: *"initialize git and commit this as 'minimal v1'."*

---

## Part 4 — Add the functionalities one at a time (intermediate)

Do these **one per session**, committing after each. For each, say something like: *"Add the `search_notes` tool per AGENT_SYSTEM_PROMPT.md, v1 (vulnerable) version — do not add the security controls yet. Plan first."*

20. `search_notes` — reads local markdown in `notes/` (start with keyword matching; no vector DB yet).
21. `read_memory` / `append_memory` — persists progress to `memory.json`.
22. `update_tracker` — writes to `tracker.md`. Build it around WITI's **four-quadrant schema** (see CLAUDE.md): Web App Security and AI Security, each split into Theory and Action. For each Action item, record the **source platform** and distinguish **HTB Academy** (modules / job-role paths) from **HTB Labs** (boxes) — alongside **PortSwigger** labs and your build/break/patch progress on WITI itself. Each item carries a source, a status, and a date.
23. `send_digest` via **Gmail**. Start safe: have it "send" by writing the digest to `outbox.txt` first, so you can test without emailing anyone. Then switch to a real Gmail send over SMTP using your address + app password (both read from `.env`). *(Later, swapping to Gmail API OAuth is itself vuln L to explore.)*

After each, run it and skim the code in the editor so you understand what was added.

### Part 4b (optional but high value) — Read the inbox
24. Add a read-only `read_inbox` tool (Gmail) so WITI can factor your inbox into the digest. This is the richest new attack surface. Build the v1 version (agent treats inbox text as instructions), keep it for the exploit in Part 5, then patch per vuln H (inbox is untrusted data; no send/write from inbox content; sender allow-list; human approval).

---

## Part 5 — Bake in the flagship vulnerability, then harden (intermediate — the main event)

25. **Bake it in:** *"Build the flagship vulnerability from AGENT_SYSTEM_PROMPT.md sections A+B: fetched content is treated as instructions, no domain allow-list, and send_digest lets the model choose recipient and content. Keep it vulnerable."*
26. **Exploit it:** *"Create `attacks/exfil_demo.py`: a local test page with hidden text instructing WITI to put my private notes into the digest and email them to an attacker-controlled address. Run it and show me the agent getting exploited."* Watch it happen — log/screenshot this; it's your demo.
27. **Harden to v2:** *"Now apply the section A+B patches: wrap fetched content as untrusted data, add a domain allow-list, fix the recipient in config, add an egress filter, and add the human-in-the-loop approval gate in code. Re-run the attack and show it failing."*
28. Commit both states clearly ("v1 exploitable" and "v2 hardened"). Write three sentences: what you built, the issue, the fix. That's your interview story (and an AI-security "walk it" entry in your tracker).
29. Repeat 25-28 for the other functionalities (C-H) as time allows.

---

## Part 6 — Working tips

- **/clear vs /exit:** `/clear` wipes the conversation but keeps you in the session (use it between unrelated tasks so context stays clean); `/exit` closes Claude Code.
- **Keep CLAUDE.md alive:** every time Claude Code does something wrong and you correct it, ask it to add a one-line rule to CLAUDE.md so it won't repeat the mistake.
- **Small steps beat big ones.** One capability, run it, commit, next. Long sessions drift.
- **Ask it to teach you.** "Explain this file line by line," "why is this the secure choice," "what would an attacker try here." You're prepping for an interview, not just shipping code.
- **Where to ask what:** build/debug/"explain this code" -> Claude Code's side chat. Interview strategy / "how does this map to what your interviewer wants" -> your prep **project** here, which holds your transcripts and game plan.
- **When you have a v1-vs-v2 demo you're proud of,** remember your interviewer invited you to share what you build — that write-up is exactly the artifact they asked for.
