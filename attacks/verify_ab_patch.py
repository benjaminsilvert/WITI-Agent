"""Deterministic proof that the tool-policy chokepoint blocks vuln A/B inputs.

Calls main.check_policy(...) directly -- not the bare tool functions (fetch_url,
send_digest), which are unchanged and would happily run if called straight,
bypassing the gate entirely. check_policy() is the actual enforcement point
run_tool() consults before dispatch, and it has no side effects (no email
send, no outbox write, no network request), so this script makes none either.

Run: python attacks/verify_ab_patch.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

import main  # noqa: E402  (reuse the real, unmodified policy-loading/check code)

ATTACKS_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(ATTACKS_DIR, "verify_ab_patch_log.txt")

ATTACKER_EMAIL = "attacker@evil-exfil.example"
ATTACKER_URL = "http://evil-exfil.example/steal"
ALLOWED_URL = "https://claude.com/"
REDACTED_OWNER_EMAIL = "owner@example.com"


def run_case(lines, label, name, tool_input, expect_allowed, redact=None):
    # check_policy always runs against the real tool_input/$OWNER_EMAIL --
    # `redact` only swaps the real address out of the text we print/log.
    allowed, reason = main.check_policy(name, tool_input)
    verdict = "ALLOWED" if allowed else "DENIED"
    expected = "ALLOWED" if expect_allowed else "DENIED"
    outcome = "PASS" if allowed == expect_allowed else "FAIL"
    line = f"[{outcome}] {label}: {name}({tool_input}) -> {verdict} ({reason}) [expected {expected}]"
    print(line)
    if redact:
        line = line.replace(redact, REDACTED_OWNER_EMAIL)
    lines.append(line)


def main_():
    load_dotenv()  # resolves $OWNER_EMAIL for tool_policy.json before load_policy()

    main.TOOL_POLICY = main.load_policy()

    owner_email = os.environ.get("OWNER_EMAIL")
    if not owner_email:
        sys.exit("OWNER_EMAIL is not set. Add it to .env before running this script.")

    lines = []

    run_case(
        lines, "A: send_digest to attacker address", "send_digest",
        {"recipient": ATTACKER_EMAIL, "subject": "x", "body": "x"},
        expect_allowed=False,
        redact=owner_email,
    )
    run_case(
        lines, "A: send_digest to owner address", "send_digest",
        {"recipient": owner_email, "subject": "x", "body": "x"},
        expect_allowed=True,
        redact=owner_email,
    )
    run_case(
        lines, "B: fetch_url to non-allow-listed host", "fetch_url",
        {"url": ATTACKER_URL},
        expect_allowed=False,
    )
    run_case(
        lines, "B: fetch_url to allow-listed host", "fetch_url",
        {"url": ALLOWED_URL},
        expect_allowed=True,
    )

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    if any(line.startswith("[FAIL]") for line in lines):
        sys.exit(1)


if __name__ == "__main__":
    main_()
