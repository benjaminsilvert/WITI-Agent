"""WITI minimal v1 loop: one Messages API call, one tool (fetch_url), prints a digest."""

import datetime
import json
import os
import re
import sys
import urllib.error
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

# The three irreversible actions (writes + a send) -- reads are not gated.
CONSEQUENTIAL_TOOLS = {"append_memory", "update_tracker", "send_digest"}

# Capability separation (vuln G): which tools each phase of main() is allowed to see.
GATHER_TOOL_NAMES = {"fetch_url", "read_inbox", "search_notes", "read_memory"}
ACT_TOOL_NAMES = {"append_memory", "update_tracker", "send_digest"}


def _normalize_path(raw_path: str) -> str | None:
    """Percent-decode a URL path once and reject '..' segments or a leftover '%'.

    Decoding first is what stops a lookalike like '%2e%2e' from sailing
    through as an opaque string that doesn't look like '..' until decoded.
    A '%' still present after that one decode means the input was encoded
    more than once (e.g. '%252e%252e' decodes to '%2e%2e', not '..') --
    rather than loop decoding to chase that, we reject outright.
    Returns None (reject) rather than a "safe" fallback if '..' or a leftover
    '%' is found -- fail closed, same as the rest of this file's policy checks.
    """
    decoded = urllib.parse.unquote(raw_path)
    if "%" in decoded:
        return None
    if any(segment == ".." for segment in decoded.split("/")):
        return None
    return decoded


def _path_allowed(path: str, prefixes: list[str]) -> bool:
    """True if path equals one of prefixes, or is a subpath of one.

    The "+ '/'" is what stops '/newsletter' from matching an allow-listed
    prefix of '/news' -- a bare str.startswith('/news') would let it through
    since '/newsletter' does start with the characters '/news'.
    """
    return any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes)


def _fetch_url_policy_check(url: str) -> tuple[bool, str]:
    """The one check fetch_url() applies to a URL, whether it's the URL the
    caller asked for or a redirect target fetch_url followed partway through
    (see _PolicyRedirectHandler below) -- both go through this same function
    so a redirect can never see looser rules than the original request did.
    """
    policy_args = (TOOL_POLICY or {}).get("tools", {}).get("fetch_url", {}).get("args", {})
    allowed_hosts = policy_args.get("url_host")
    path_prefixes_by_host = policy_args.get("url_path_prefix")
    if not allowed_hosts or not path_prefixes_by_host:
        return False, "no url_host/url_path_prefix allow-list configured for fetch_url"

    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    if host not in allowed_hosts:
        return False, f"host '{host}' not in allow-list for fetch_url ({allowed_hosts})"

    # Fail closed: a host present in url_host but missing from
    # url_path_prefix has no allowed paths, rather than defaulting to "all".
    prefixes = path_prefixes_by_host.get(host)
    if not prefixes:
        return False, f"host '{host}' has no url_path_prefix entry (fail-closed) for fetch_url"

    norm_path = _normalize_path(parsed.path)
    if norm_path is None:
        return False, f"path '{parsed.path}' rejected (contains '..' or invalid encoding) for fetch_url"
    if not _path_allowed(norm_path, prefixes):
        return False, f"path '{norm_path}' not in url_path_prefix allow-list for host '{host}' ({prefixes})"

    return True, "allowed"


class _PolicyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-applies fetch_url's host+path allow-list to every redirect target.

    Without this, urlopen() follows 3xx redirects on its own with no policy
    check -- an allowed URL could 302 to an attacker host/path and fetch_url
    would return that response as if it had come from the allowed source.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # newurl is already the absolute, resolved redirect target -- urllib
        # has already joined a relative Location header against the original
        # URL by the time this method is called.
        allowed, reason = _fetch_url_policy_check(newurl)
        if not allowed:
            # Raising here aborts the redirect; the exception propagates out
            # of urlopen(), where fetch_url()'s `except Exception` below
            # catches it, so the caller just sees an "Error fetching" message.
            raise urllib.error.HTTPError(newurl, code, f"Redirect blocked by policy: {reason}", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Installs our handler into the default opener that a plain
# urllib.request.urlopen(...) call uses internally -- so fetch_url()'s
# urlopen() call below needs no changes, but every redirect hop it follows
# now runs through _PolicyRedirectHandler first.
urllib.request.install_opener(urllib.request.build_opener(_PolicyRedirectHandler()))


# --- Marker-breakout defense (STATUS.md §20 caveat) --------------------------
#
# The <untrusted>...</untrusted> wrapper only works as a trust boundary if the
# TEXT INSIDE it can never contain something that *looks like* a real marker.
# Otherwise a fetched page or an inbox message could smuggle in its own fake
# "</untrusted>" and trick a careless reader (human or model) into thinking
# the untrusted section ended early, with attacker text after it treated as
# if it were outside the boundary (or a fake "<untrusted>" making trusted-looking
# text seem to start a *new* untrusted section). _neutralize_markers() finds
# every spelling of the open or close marker -- real angle brackets, HTML-entity
# angle brackets, mixed case, extra spaces -- and replaces each one with the
# harmless literal text "[removed marker]" before the text is ever wrapped.
#
# _ANGLE_OPEN matches anything that could render or be read as a literal "<":
#   <            the real character
#   &lt;?        the named HTML entity "&lt;", with the ";" made optional (";?")
#                because "&lt" without a semicolon is still treated as "<" by
#                real HTML parsers, so we have to catch it too
#   &#0*60;?     the decimal numeric entity for "<" (character code 60).
#                "0*" means "zero or more '0' characters", so this matches
#                &#60;, &#060;, &#0060; and so on -- entities are allowed to
#                have extra leading zeros and still mean the same character.
#                ";?" again makes the trailing semicolon optional.
#   &#x0*3c;?    the hexadecimal numeric entity for "<" (0x3c = 60 decimal),
#                same "0*" leading-zero and ";?" optional-semicolon reasoning.
# _ANGLE_CLOSE is the same idea for ">" (character code 62 / 0x3e).
# "(?:...)" around each list of alternatives is a *non-capturing* group -- it
# just groups the "or"s together without creating a numbered capture group we
# don't need.
_ANGLE_OPEN = r"(?:<|&lt;?|&#0*60;?|&#x0*3c;?)"
_ANGLE_CLOSE = r"(?:>|&gt;?|&#0*62;?|&#x0*3e;?)"

# The full marker pattern, built from the two pieces above:
#   _ANGLE_OPEN   an opening angle bracket (or a lookalike)
#   \s*           optional whitespace right after it
#   /?            an optional "/" -- present for a CLOSING marker
#                 (</untrusted>), absent for an OPENING one (<untrusted>).
#                 This single pattern deliberately matches both, since either
#                 one breaking the wrapper is a problem.
#   \s*           optional whitespace after the "/"
#   untrusted     the literal word "untrusted"
#   \s*           optional whitespace before the closing bracket
#   _ANGLE_CLOSE  a closing angle bracket (or a lookalike)
# re.IGNORECASE makes every letter above match regardless of case, so this
# one pattern also covers </UNTRUSTED>, <Untrusted>, &LT;/untrusted&GT;, etc.
_UNTRUSTED_MARKER_RE = re.compile(
    _ANGLE_OPEN + r"\s*/?\s*untrusted\s*" + _ANGLE_CLOSE,
    re.IGNORECASE,
)


def _neutralize_markers(text: str) -> str:
    """Replace every open/close <untrusted> marker lookalike in text with a harmless string.

    Called on fetched-page text, the fetched URL, and inbox sender/subject/body
    BEFORE any of it is placed inside a real <untrusted>...</untrusted> wrapper,
    so nothing untrusted can forge a boundary of its own.
    """
    return _UNTRUSTED_MARKER_RE.sub("[removed marker]", text)


def fetch_url(url: str) -> str:
    # Defense-in-depth: check_policy() only runs on the run_tool() dispatch path --
    # a direct main.fetch_url(...) call must still be stopped by the same host+path
    # allow-list.
    allowed, reason = _fetch_url_policy_check(url)
    if not allowed:
        return f"Denied by policy: {reason}"

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
    # Neutralize marker lookalikes BEFORE the char cap, so the cap stays the
    # final length limit and can't cut a "[removed marker]" replacement in half.
    text = _neutralize_markers(text)
    text = text[:FETCH_CHAR_CAP]
    safe_url = _neutralize_markers(url)
    return f"<untrusted>\nSource: {safe_url}\n\n{text}\n</untrusted>"


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
        # The allow-list check runs on the RAW sender, before neutralization --
        # a message can't dodge the flag by hiding a marker lookalike in its
        # From address, and neutralization must never change who counts as
        # "on the allow-list".
        flag = "" if sender.lower() in allowlist else " [SENDER NOT IN ALLOW-LIST]"
        safe_sender = _neutralize_markers(sender)
        safe_subject = _neutralize_markers(m["subject"])
        safe_body = _neutralize_markers(m["body"])
        parts.append(f"From: {safe_sender}{flag}\nSubject: {safe_subject}\n\n{safe_body}")

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

        if name == "fetch_url" and key == "url_path_prefix":
            # Delegate to the single source of truth for fetch_url's
            # host+path check (also used by fetch_url() itself and by
            # _PolicyRedirectHandler) instead of re-implementing path
            # matching here.
            allowed_path, reason = _fetch_url_policy_check(tool_input.get("url", ""))
            if not allowed_path:
                return False, reason
            continue

        value = tool_input.get(key)
        allowed_values = allowed if isinstance(allowed, list) else [allowed]
        if value not in allowed_values:
            return False, f"{name}.{key} = '{value}' not in allow-list ({allowed_values})"

    return True, "allowed"


def request_approval(name: str, tool_input: dict) -> bool:
    # A deterministic, code-level gate -- not a prompt instruction -- so an injected
    # instruction can talk the model into requesting a consequential action, but cannot
    # talk this check into approving it.
    print(f"\n[APPROVAL REQUIRED] {name}({tool_input})")
    answer = input("Allow this action? [y/N]: ").strip().lower()
    if answer == "y":
        return True
    print(f"[DENIED BY HUMAN] {name}({tool_input})")
    return False


def run_tool(name: str, tool_input: dict) -> str:
    # Policy check happens before any dispatch -- a denied call never reaches
    # the tool function, no matter what name/args the model sends.
    allowed, reason = check_policy(name, tool_input)
    if not allowed:
        print(f"[POLICY DENY] {name}({tool_input}) -> {reason}")
        return f"Denied by policy: {reason}"

    if name in CONSEQUENTIAL_TOOLS and not request_approval(name, tool_input):
        return f"Denied by human: {name} was not approved."

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


def run_phase(client, system_prompt, messages, tools):
    # Capability separation (vuln G) is enforced here: each phase only ever sees the
    # tool list it's called with -- an architectural boundary, not a prompt instruction
    # the model (or injected content it read) could talk its way around.
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
            return response

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"[tool call] {block.name}({block.input})")
                result = run_tool(block.name, block.input)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )
        messages.append({"role": "user", "content": tool_results})


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
    # Each phase is further restricted to its own tool names (see GATHER_TOOL_NAMES /
    # ACT_TOOL_NAMES above) -- the gather phase never even sees a send/write tool.
    gather_tools = [
        t for t in ALL_TOOLS
        if TOOL_POLICY["tools"].get(t["name"], {}).get("allow") and t["name"] in GATHER_TOOL_NAMES
    ]
    act_tools = [
        t for t in ALL_TOOLS
        if TOOL_POLICY["tools"].get(t["name"], {}).get("allow") and t["name"] in ACT_TOOL_NAMES
    ]

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

    print("\n=== PHASE 1: GATHER (read-only tools) ===")
    run_phase(client, system_prompt, messages, gather_tools)

    messages.append(
        {
            "role": "user",
            "content": (
                "Gathering is complete. You now have only action tools available. Act "
                "solely on the information already gathered above to carry out whatever "
                "the original request requires (e.g. send the digest, update the "
                "tracker/memory). Do not ask to fetch or read anything further. If no "
                "action is needed, just say so."
            ),
        }
    )

    print("\n=== PHASE 2: ACT (send/write tools) ===")
    response = run_phase(client, system_prompt, messages, act_tools)

    digest = "".join(block.text for block in response.content if block.type == "text")
    print("\n--- WITI digest ---\n")
    print(digest)


if __name__ == "__main__":
    main()
