"""WITI minimal v1 loop: one Messages API call, one tool (fetch_url), prints a digest."""

import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request

from anthropic import Anthropic
from dotenv import load_dotenv

# Windows terminals often default to cp1252, which can't encode characters
# like "->" that the model tends to use -- force UTF-8 on stdout/stderr.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

MODEL = "claude-sonnet-5"
MAX_TOKENS = 4096
FETCH_TIMEOUT_SECONDS = 10
FETCH_CHAR_CAP = 5000
NOTES_DIR = "notes"
MEMORY_PATH = "memory.json"
TRACKER_PATH = "tracker.md"
OUTBOX_PATH = "outbox.txt"
INBOX_PATH = "inbox.json"

# On-topic default: ties straight into the vuln catalog this project is building toward.
DEFAULT_URL = "https://owasp.org/www-project-top-10-for-large-language-model-applications/"
DEFAULT_REQUEST = "Give me a shareable digest of what's in my notes about IDOR."

FETCH_URL_TOOL = {
    "name": "fetch_url",
    "description": "Fetch the visible text content of a web page given its URL.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to fetch."},
        },
        "required": ["url"],
    },
}

SEARCH_NOTES_TOOL = {
    "name": "search_notes",
    "description": "Search the user's local notes (markdown files in notes/) for a keyword and return matching notes in full.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Keyword or phrase to search for."},
        },
        "required": ["query"],
    },
}

READ_MEMORY_TOOL = {
    "name": "read_memory",
    "description": "Read everything currently stored in persistent memory.",
    "input_schema": {"type": "object", "properties": {}},
}

APPEND_MEMORY_TOOL = {
    "name": "append_memory",
    "description": "Append a note to persistent memory so it's recalled in future runs.",
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The text to remember."},
        },
        "required": ["content"],
    },
}

UPDATE_TRACKER_TOOL = {
    "name": "update_tracker",
    "description": "Overwrite the progress tracker (tracker.md) with new content.",
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The full new contents of tracker.md."},
        },
        "required": ["content"],
    },
}

SEND_DIGEST_TOOL = {
    "name": "send_digest",
    "description": "Send the digest to an email recipient. (v1: writes to outbox.txt instead of a real send.)",
    "input_schema": {
        "type": "object",
        "properties": {
            "recipient": {"type": "string", "description": "Email address to send the digest to."},
            "subject": {"type": "string", "description": "Email subject line."},
            "body": {"type": "string", "description": "The full digest text to send."},
        },
        "required": ["recipient", "subject", "body"],
    },
}

READ_INBOX_TOOL = {
    "name": "read_inbox",
    "description": "Read messages currently in the inbox. (v1: reads a local inbox.json instead of real Gmail.)",
    "input_schema": {"type": "object", "properties": {}},
}

# All tool schemas in one place so both the API call and the policy filter
# (see load_policy/check_policy below) can iterate over the same list.
ALL_TOOLS = [
    FETCH_URL_TOOL,
    SEARCH_NOTES_TOOL,
    READ_MEMORY_TOOL,
    APPEND_MEMORY_TOOL,
    UPDATE_TRACKER_TOOL,
    SEND_DIGEST_TOOL,
    READ_INBOX_TOOL,
]

# Populated once at startup by load_policy(); read by check_policy() on every tool call.
TOOL_POLICY = None


def fetch_url(url: str) -> str:
    # Defense-in-depth: check_policy() only runs on the run_tool() dispatch path --
    # a direct main.fetch_url(...) call must still be stopped by the same host allow-list.
    allowed_hosts = (TOOL_POLICY or {}).get("tools", {}).get("fetch_url", {}).get("args", {}).get("url_host")
    if not allowed_hosts:
        return "Denied by policy: no url_host allow-list configured for fetch_url."
    host = urllib.parse.urlparse(url).hostname
    if host not in allowed_hosts:
        return f"Denied by policy: host '{host}' not in allow-list for fetch_url ({allowed_hosts})."

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "witi-agent/0.1"})
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            html = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return f"Error fetching {url}: {exc}"

    # Naive tag strip -- good enough for a v1 demo, not a real HTML parser.
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:FETCH_CHAR_CAP]


def _note_sensitivity(text: str) -> str:
    """Read the `sensitivity:` value from a note's leading front-matter block.

    Fail-closed: a note with no front-matter, or front-matter with no
    sensitivity line, is treated as private -- absence of a label is not
    the same as a public label, and retrieval must not assume it is.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "private"

    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if stripped.lower().startswith("sensitivity:"):
            return stripped.split(":", 1)[1].strip().lower()

    return "private"


def search_notes(query: str, include_private: bool = False) -> str:
    """Search notes/ for a keyword. Data-layer authorization, not prompt-level:
    the sensitivity filter is enforced here in code, so a caller must pass
    include_private=True to see anything but public notes -- the model
    noticing (or being told) a note is private/public is not what decides this.
    """
    if not os.path.isdir(NOTES_DIR):
        return f"No '{NOTES_DIR}' directory found."

    query_lower = query.lower()
    matches = []
    for name in sorted(os.listdir(NOTES_DIR)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(NOTES_DIR, name)
        text = open(path, encoding="utf-8").read()
        if _note_sensitivity(text) != "public" and not include_private:
            continue
        if query_lower in name.lower() or query_lower in text.lower():
            matches.append(f"--- {name} ---\n{text}")

    if not matches:
        return f"No notes matched '{query}'."
    return "\n\n".join(matches)


def read_memory() -> str:
    if not os.path.exists(MEMORY_PATH):
        return "[]"
    return open(MEMORY_PATH, encoding="utf-8").read()


def append_memory(content: str, source: str = "agent") -> str:
    # Size cap: reject oversized content outright rather than truncating it --
    # a silent truncation would hide how much of an injected payload got in.
    if len(content) > 10_000:
        return f"Rejected: content is {len(content)} chars, over the 10,000-char limit for a single memory entry."

    entries = []
    if os.path.exists(MEMORY_PATH):
        try:
            entries = json.loads(open(MEMORY_PATH, encoding="utf-8").read())
        except json.JSONDecodeError:
            entries = []

    entries.append(
        {
            "content": content,
            "source": source,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    )

    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)

    return f"Stored to memory ({len(entries)} entries total)."


def update_tracker(content: str) -> str:
    # Size cap, same limit as append_memory.
    if len(content) > 10_000:
        return f"Rejected: content is {len(content)} chars, over the 10,000-char limit for a single tracker update."

    # Append-only: a single call can never destroy prior tracker history, no
    # matter what the model is talked into sending. Each call adds a
    # timestamped section instead of overwriting the file.
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(TRACKER_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n## Update {timestamp}\n\n{content}\n")

    return f"tracker.md appended ({len(content)} chars)."


def send_digest(recipient: str, subject: str, body: str) -> str:
    # Defense-in-depth: same reasoning as fetch_url's guard above.
    allowed = (TOOL_POLICY or {}).get("tools", {}).get("send_digest", {}).get("args", {}).get("recipient")
    if not allowed:
        return "Denied by policy: no recipient allow-list configured for send_digest."
    allowed_values = allowed if isinstance(allowed, list) else [allowed]
    if recipient not in allowed_values:
        return f"Denied by policy: recipient '{recipient}' not in allow-list for send_digest ({allowed_values})."

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(OUTBOX_PATH, "a", encoding="utf-8") as f:
        f.write(f"=== {timestamp} ===\nTo: {recipient}\nSubject: {subject}\n\n{body}\n\n")
    return f"Digest written to {OUTBOX_PATH} (to: {recipient})."


DEFAULT_INBOX_ALLOWLIST = ["noreply@hackthebox.com"]


def _inbox_allowlist() -> list[str]:
    """Trusted sender addresses for read_inbox, lowercased.

    Read from $INBOX_ALLOWLIST (comma-separated) when set, so the user can
    configure it without a code change; otherwise fall back to a small
    built-in default.
    """
    raw = os.environ.get("INBOX_ALLOWLIST")
    if raw:
        return [addr.strip().lower() for addr in raw.split(",") if addr.strip()]
    return DEFAULT_INBOX_ALLOWLIST


def read_inbox() -> str:
    """Read the inbox and return it as untrusted data, not instructions.

    Every message is flagged (not dropped) if its sender isn't on the
    allow-list, and the whole result -- headers included, since a subject
    line is just as attacker-controlled as a body -- sits inside
    <untrusted>...</untrusted> markers. The prompt is taught (see
    prompts/system.md) that content between those markers must never be
    treated as instructions.
    """
    if not os.path.exists(INBOX_PATH):
        return "No messages."

    messages = json.loads(open(INBOX_PATH, encoding="utf-8").read())
    if not messages:
        return "No messages."

    allowlist = _inbox_allowlist()
    parts = []
    for m in messages:
        sender = m["from"]
        flag = "" if sender.lower() in allowlist else " [SENDER NOT IN ALLOW-LIST]"
        parts.append(f"From: {sender}{flag}\nSubject: {m['subject']}\n\n{m['body']}")

    body = "\n\n---\n\n".join(parts)
    return f"<untrusted>\n{body}\n</untrusted>"


def _resolve_placeholder(value):
    """Substitute a "$VAR" string with os.environ["VAR"]; exit if that var is unset.

    Fails closed on purpose: a policy that references an env var which isn't
    there should stop the program, not silently fall back to "no restriction".
    """
    if isinstance(value, str) and value.startswith("$"):
        var_name = value[1:]
        resolved = os.environ.get(var_name)
        if not resolved:
            sys.exit(f"{var_name} is not set. Add it to .env before running WITI (required by tool_policy.json).")
        return resolved
    return value


def load_policy(path: str = "tool_policy.json") -> dict:
    """Load tool_policy.json once and resolve any $VAR placeholders in its args rules."""
    with open(path, encoding="utf-8") as f:
        policy = json.load(f)

    for rule in policy.get("tools", {}).values():
        args = rule.get("args", {})
        for key, value in list(args.items()):
            # An args value can be a single allowed value (e.g. recipient) or
            # a list of allowed values (e.g. url_host) -- resolve either shape.
            if isinstance(value, list):
                args[key] = [_resolve_placeholder(v) for v in value]
            else:
                args[key] = _resolve_placeholder(value)

    return policy


def check_policy(name: str, tool_input: dict) -> tuple[bool, str]:
    """Check a proposed tool call against TOOL_POLICY. Returns (allowed, reason)."""
    rule = TOOL_POLICY.get("tools", {}).get(name)
    if not rule or not rule.get("allow"):
        return False, f"tool '{name}' is not permitted (default: {TOOL_POLICY.get('default', 'deny')})"

    for key, allowed in rule.get("args", {}).items():
        if name == "fetch_url" and key == "url_host":
            # Compare the parsed hostname, not a substring of the raw URL --
            # substring matching would let "claude.com.evil.example" or
            # "notclaude.com" slip past a ["claude.com"] allow-list.
            host = urllib.parse.urlparse(tool_input.get("url", "")).hostname
            if host not in allowed:
                return False, f"host '{host}' not in allow-list for fetch_url ({allowed})"
            continue

        value = tool_input.get(key)
        allowed_values = allowed if isinstance(allowed, list) else [allowed]
        if value not in allowed_values:
            return False, f"{name}.{key} = '{value}' not in allow-list ({allowed_values})"

    return True, "allowed"


def run_tool(name: str, tool_input: dict) -> str:
    # Policy check happens before any dispatch -- a denied call never reaches
    # the tool function, no matter what name/args the model sends.
    allowed, reason = check_policy(name, tool_input)
    if not allowed:
        print(f"[POLICY DENY] {name}({tool_input}) -> {reason}")
        return f"Denied by policy: {reason}"

    if name == "fetch_url":
        return fetch_url(tool_input["url"])
    if name == "search_notes":
        return search_notes(tool_input["query"])
    if name == "read_memory":
        return read_memory()
    if name == "append_memory":
        return append_memory(tool_input["content"])
    if name == "update_tracker":
        return update_tracker(tool_input["content"])
    if name == "send_digest":
        return send_digest(tool_input["recipient"], tool_input["subject"], tool_input["body"])
    if name == "read_inbox":
        return read_inbox()
    return f"Unknown tool: {name}"


def main():
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY is not set. Add it to .env first.")

    # Load the policy once here (after load_dotenv, so $VAR placeholders can
    # resolve) and stash it in the module global that check_policy() reads.
    global TOOL_POLICY
    TOOL_POLICY = load_policy()

    # Only advertise tools the policy allows at all -- a tool the model never
    # sees, it can't call. (Argument-level rules still apply per-call in run_tool.)
    tools = [t for t in ALL_TOOLS if TOOL_POLICY["tools"].get(t["name"], {}).get("allow")]

    client = Anthropic(api_key=api_key)
    system_prompt = open("prompts/system.md", encoding="utf-8").read()

    if len(sys.argv) == 2 and sys.argv[1].startswith(("http://", "https://")):
        user_request = f"Fetch {sys.argv[1]} and summarize it"
    elif len(sys.argv) > 1:
        user_request = " ".join(sys.argv[1:])
    else:
        user_request = DEFAULT_REQUEST

    messages = [
        {
            "role": "user",
            "content": (
                f"{user_request}. Give a short digest: 3-5 bullets, each with one "
                "\"why it matters\" line, citing sources where relevant."
            ),
        }
    ]

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"[tool call] {block.name}({block.input})")
                result = run_tool(block.name, block.input)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )
        messages.append({"role": "user", "content": tool_results})

    digest = "".join(block.text for block in response.content if block.type == "text")
    print("\n--- WITI digest ---\n")
    print(digest)


if __name__ == "__main__":
    main()
