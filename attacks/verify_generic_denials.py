"""Deterministic proof that policy denials returned to the model are generic
(CWE-209 fix), while the detailed reason still reaches the human via print(),
and that check_policy() fails closed instead of crashing when TOOL_POLICY is
None.

Calls main.run_tool(...) / main.fetch_url(...) / main.send_digest(...) /
main.check_policy(...) / main._PolicyRedirectHandler directly -- the real,
unmodified v2 code, not a re-implementation of it. builtins.input is
monkeypatched to raise if called at all, proving policy denial happens
before request_approval()'s human-approval gate ever runs. No model call,
no network, no outbox write (every case here denies before send_digest's
file write).

Run: python attacks/verify_generic_denials.py
"""

import contextlib
import io
import os
import sys
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

import main  # noqa: E402  (reuse the real, unmodified policy/tool code)

ATTACKS_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(ATTACKS_DIR, "verify_generic_denials_log.txt")

ATTACKER_EMAIL = "attacker@evil-exfil.example"
ATTACKER_URL = "http://evil-exfil.example/steal"
ALLOWED_URL = "https://claude.com/blog"
GENERIC = "Denied by policy: this action is not permitted."
REDACTED_OWNER_EMAIL = "owner@example.com"

_input_should_not_be_called = mock.patch(
    "builtins.input",
    side_effect=AssertionError(
        "input() was called -- a policy denial must short-circuit before "
        "request_approval()'s human-approval gate, never reach it"
    ),
)


def run_case(lines, label, check_fn, redact=None):
    ok, detail = check_fn()
    outcome = "PASS" if ok else "FAIL"
    line = f"[{outcome}] {label}: {detail}"
    print(line)
    if redact:
        line = line.replace(redact, REDACTED_OWNER_EMAIL)
    lines.append(line)


def main_():
    load_dotenv()  # resolves $OWNER_EMAIL for tool_policy.json before load_policy()

    owner_email = os.environ.get("OWNER_EMAIL")
    if not owner_email:
        sys.exit("OWNER_EMAIL is not set. Add it to .env before running this script.")

    main.TOOL_POLICY = main.load_policy()

    outbox_before = open(main.OUTBOX_PATH, encoding="utf-8").read() if os.path.exists(main.OUTBOX_PATH) else ""

    lines = []

    with _input_should_not_be_called:

        # --- Case 1: run_tool send_digest, disallowed recipient ------------
        result1 = main.run_tool("send_digest", {"recipient": ATTACKER_EMAIL, "subject": "x", "body": "x"})

        def check_case1():
            generic = result1 == GENERIC
            no_leak = owner_email not in result1
            return generic and no_leak, f"result={result1!r} generic={generic} owner_email_absent={no_leak}"

        run_case(lines, "run_tool send_digest disallowed recipient -> generic, no leak", check_case1, redact=owner_email)

        # --- Case 2: run_tool fetch_url, disallowed host --------------------
        result2 = main.run_tool("fetch_url", {"url": ATTACKER_URL})

        def check_case2():
            generic = result2 == GENERIC
            no_leak = "claude.com" not in result2 and "www.anthropic.com" not in result2
            return generic and no_leak, f"result={result2!r} generic={generic} allowlist_hosts_absent={no_leak}"

        run_case(lines, "run_tool fetch_url disallowed host -> generic, no leak", check_case2)

        # --- Case 3: run_tool fetch_url, allowed host, disallowed path ------
        result3 = main.run_tool("fetch_url", {"url": "https://claude.com/admin"})

        def check_case3():
            generic = result3 == GENERIC
            no_leak = "/blog" not in result3 and "/news" not in result3
            return generic and no_leak, f"result={result3!r} generic={generic} allowlist_paths_absent={no_leak}"

        run_case(lines, "run_tool fetch_url allowed host + disallowed path -> generic, no leak", check_case3)

        # --- Case 4: direct fetch_url / send_digest, bypassing run_tool -----
        result4a = main.fetch_url(ATTACKER_URL)
        result4b = main.send_digest(ATTACKER_EMAIL, "x", "x")
        outbox_after_case4 = open(main.OUTBOX_PATH, encoding="utf-8").read() if os.path.exists(main.OUTBOX_PATH) else ""

        def check_case4():
            generic_a = result4a == GENERIC
            generic_b = result4b == GENERIC
            no_leak = (
                "claude.com" not in result4a
                and "www.anthropic.com" not in result4a
                and owner_email not in result4b
            )
            outbox_untouched = outbox_after_case4 == outbox_before
            ok = generic_a and generic_b and no_leak and outbox_untouched
            return ok, (
                f"fetch_url_result={result4a!r} send_digest_result={result4b!r} "
                f"generic_a={generic_a} generic_b={generic_b} no_leak={no_leak} "
                f"outbox_untouched={outbox_untouched}"
            )

        run_case(lines, "direct fetch_url/send_digest (bypassing run_tool) -> generic, no leak, no outbox write", check_case4, redact=owner_email)

        # --- Case 5: denied redirect -----------------------------------------
        # Produce the exception from the real handler (not hand-written), the
        # same way verify_path_and_redirect.py does, so this proves there was
        # real allow-list detail available to leak before asserting fetch_url
        # hides it.
        handler = main._PolicyRedirectHandler()
        req = urllib.request.Request(ALLOWED_URL)
        try:
            handler.redirect_request(req, fp=None, code=302, msg="Found", headers=None, newurl=ATTACKER_URL)
            redirect_exc = None
        except main._RedirectPolicyDenied as exc:
            redirect_exc = exc

        def check_case5_setup():
            got_exc = redirect_exc is not None
            has_detail = got_exc and (
                "claude.com" in redirect_exc.reason or "www.anthropic.com" in redirect_exc.reason
            )
            return got_exc and has_detail, (
                f"raised={got_exc} detailed_reason={redirect_exc.reason if got_exc else None!r} "
                f"has_allowlist_host={has_detail}"
            )

        run_case(lines, "redirect_request() raises _RedirectPolicyDenied carrying real allow-list detail", check_case5_setup)

        with mock.patch("urllib.request.urlopen", side_effect=redirect_exc):
            result5 = main.fetch_url(ALLOWED_URL)

        def check_case5():
            generic = result5 == GENERIC
            no_leak = "claude.com" not in result5 and "www.anthropic.com" not in result5
            return generic and no_leak, f"result={result5!r} generic={generic} allowlist_hosts_absent={no_leak}"

        run_case(lines, "fetch_url denied redirect -> generic, no leak (despite real detail existing)", check_case5)

        # --- Case 6: TOOL_POLICY is None -> fails closed, no crash ----------
        saved_policy = main.TOOL_POLICY
        try:
            main.TOOL_POLICY = None
            try:
                result6 = main.run_tool("fetch_url", {"url": ALLOWED_URL})
                crashed = False
            except Exception as exc:  # noqa: BLE001 -- exactly what we're checking didn't happen
                result6 = None
                crashed = True
                crash_detail = repr(exc)
        finally:
            main.TOOL_POLICY = saved_policy

        def check_case6():
            no_crash = not crashed
            is_denial = (not crashed) and isinstance(result6, str) and result6.startswith("Denied by policy")
            ok = no_crash and is_denial
            detail = f"no_crash={no_crash} result={result6!r}" if no_crash else f"no_crash={no_crash} exception={crash_detail}"
            return ok, detail

        run_case(lines, "TOOL_POLICY=None -> run_tool denies cleanly, no exception", check_case6)

        # --- Case 7: detailed reason still reaches the terminal -------------
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            result7 = main.run_tool("send_digest", {"recipient": ATTACKER_EMAIL, "subject": "x", "body": "x"})
        printed = captured.getvalue()

        def check_case7():
            model_result_generic = result7 == GENERIC
            terminal_has_detail = "[POLICY DENY]" in printed and ATTACKER_EMAIL in printed and "not in allow-list" in printed
            ok = model_result_generic and terminal_has_detail
            return ok, f"model_result_generic={model_result_generic} terminal_has_detail={terminal_has_detail}"

        run_case(lines, "detailed reason prints to terminal even though model-facing result is generic", check_case7)

    # --- Case 8: log scrub self-check (belt-and-suspenders grep-confirm) ---
    def check_case8():
        ok = all(owner_email not in line for line in lines)
        return ok, f"owner_email_absent_from_all_logged_lines={ok}"

    run_case(lines, "owner email never appears unredacted in logged lines", check_case8)

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    with open(LOG_PATH, encoding="utf-8") as f:
        logged_text = f.read()
    if owner_email in logged_text:
        print(f"[FAIL] post-write grep-confirm: real OWNER_EMAIL found in {LOG_PATH}")
        sys.exit(1)

    if any(line.startswith("[FAIL]") for line in lines):
        sys.exit(1)


if __name__ == "__main__":
    main_()
