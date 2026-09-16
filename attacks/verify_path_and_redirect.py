"""Deterministic proof of the v2 fetch_url hardening: host+path allow-listing
(not just host) and redirect-target re-checking.

Path cases call main.check_policy(...) directly, the same chokepoint
verify_ab_patch.py exercises -- no side effects, no network.

Redirect cases call main._PolicyRedirectHandler().redirect_request(...)
directly, bypassing urlopen()/opener machinery entirely -- also no network.
redirect_request() is the exact method urllib invokes on every 3xx hop, so
calling it directly exercises the real enforcement code, not a re-implementation
of it.

Run: python attacks/verify_path_and_redirect.py
"""

import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

import main  # noqa: E402  (reuse the real, unmodified policy code)

ATTACKS_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(ATTACKS_DIR, "verify_path_and_redirect_log.txt")

ATTACKER_URL = "http://evil-exfil.example/steal"


def run_case(lines, label, name, tool_input, expect_allowed):
    allowed, reason = main.check_policy(name, tool_input)
    verdict = "ALLOWED" if allowed else "DENIED"
    expected = "ALLOWED" if expect_allowed else "DENIED"
    outcome = "PASS" if allowed == expect_allowed else "FAIL"
    line = f"[{outcome}] {label}: {name}({tool_input}) -> {verdict} ({reason}) [expected {expected}]"
    print(line)
    lines.append(line)


def run_redirect_case(lines, label, newurl, expect_allowed):
    handler = main._PolicyRedirectHandler()
    # A minimal real Request -- redirect_request() only reads its method,
    # which defaults to GET for a Request built with no `data`.
    req = urllib.request.Request("https://claude.com/blog")
    try:
        result = handler.redirect_request(req, fp=None, code=302, msg="Found", headers=None, newurl=newurl)
        allowed = True
        detail = f"-> allowed, got {type(result).__name__}"
    except urllib.error.HTTPError as exc:
        allowed = False
        detail = f"-> blocked, HTTPError({exc.reason})"

    expected = "ALLOWED" if expect_allowed else "DENIED"
    verdict = "ALLOWED" if allowed else "DENIED"
    outcome = "PASS" if allowed == expect_allowed else "FAIL"
    line = f"[{outcome}] {label}: redirect to {newurl} {detail} [expected {expected}]"
    print(line)
    lines.append(line)


def main_():
    load_dotenv()  # resolves $OWNER_EMAIL for tool_policy.json before load_policy()

    main.TOOL_POLICY = main.load_policy()

    lines = []

    run_case(
        lines, "allowed path", "fetch_url",
        {"url": "https://claude.com/blog"},
        expect_allowed=True,
    )
    run_case(
        lines, "allowed subpath", "fetch_url",
        {"url": "https://claude.com/blog/post-1"},
        expect_allowed=True,
    )
    run_case(
        lines, "lookalike prefix (/newsletter vs /news)", "fetch_url",
        {"url": "https://www.anthropic.com/newsletter"},
        expect_allowed=False,
    )
    run_case(
        lines, "literal .. segment", "fetch_url",
        {"url": "https://claude.com/blog/../secret"},
        expect_allowed=False,
    )
    run_case(
        lines, "percent-encoded .. segment (%2e%2e)", "fetch_url",
        {"url": "https://claude.com/blog/%2e%2e/secret"},
        expect_allowed=False,
    )
    run_case(
        lines, "double-percent-encoded .. segment (%252e%252e)", "fetch_url",
        {"url": "https://claude.com/blog/%252e%252e/secret"},
        expect_allowed=False,
    )
    run_case(
        lines, "disallowed host entirely", "fetch_url",
        {"url": ATTACKER_URL},
        expect_allowed=False,
    )

    run_redirect_case(
        lines, "redirect to disallowed host",
        ATTACKER_URL,
        expect_allowed=False,
    )
    run_redirect_case(
        lines, "redirect to disallowed path on an allowed host",
        "https://claude.com/admin",
        expect_allowed=False,
    )
    run_redirect_case(
        lines, "redirect to an allowed target",
        "https://claude.com/blog/other",
        expect_allowed=True,
    )
    run_redirect_case(
        lines, "redirect to double-percent-encoded .. segment",
        "https://claude.com/blog/%252e%252e/secret",
        expect_allowed=False,
    )

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    if any(line.startswith("[FAIL]") for line in lines):
        sys.exit(1)


if __name__ == "__main__":
    main_()
