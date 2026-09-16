"""Deterministic proof that fetch_url wraps its fetched-page output in
<untrusted>...</untrusted> markers, applied after FETCH_CHAR_CAP truncation,
and that fetch_url's own messages (policy denial, fetch error) stay unwrapped.

Calls main.fetch_url(...) directly with urllib.request.urlopen monkeypatched
to return canned HTML -- no real network request is made. The host allow-list
guard (check_policy / the in-function TOOL_POLICY read) is exercised as-is,
unmodified.

Run: python attacks/verify_a_untrusted_wrap.py
"""

import io
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

import main  # noqa: E402  (reuse the real, unmodified fetch_url code)

ATTACKS_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(ATTACKS_DIR, "verify_a_untrusted_wrap_log.txt")

ALLOWED_URL = "https://claude.com/blog"
DENIED_URL = "http://evil-exfil.example/steal"


class _FakeResponse:
    """Stand-in for the object urllib.request.urlopen()'s context manager yields."""

    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def run_case(lines, label, check_fn):
    ok, detail = check_fn()
    outcome = "PASS" if ok else "FAIL"
    line = f"[{outcome}] {label}: {detail}"
    print(line)
    lines.append(line)


def main_():
    load_dotenv()  # resolves $OWNER_EMAIL / allow-lists for tool_policy.json before load_policy()

    main.TOOL_POLICY = main.load_policy()

    lines = []

    # Case 1: allowed host, stubbed success -- result must be wrapped, must
    # include the source URL, and the closing marker must survive truncation
    # (the stub page is deliberately longer than FETCH_CHAR_CAP).
    huge_page = b"<html><body>" + (b"PAGE-CONTENT " * (main.FETCH_CHAR_CAP // 10)) + b"</body></html>"
    with mock.patch("urllib.request.urlopen", return_value=_FakeResponse(huge_page)):
        result = main.fetch_url(ALLOWED_URL)

    def check_case1():
        starts_ok = result.startswith("<untrusted>\n")
        ends_ok = result.endswith("</untrusted>")
        has_source = f"Source: {ALLOWED_URL}" in result
        # exactly one closing marker, and it's the last thing in the string --
        # proves the wrapper was applied AFTER truncation, not before.
        one_close = result.count("</untrusted>") == 1
        ok = starts_ok and ends_ok and has_source and one_close
        return ok, (
            f"starts_with_open={starts_ok} ends_with_close={ends_ok} "
            f"has_source_line={has_source} exactly_one_close_marker={one_close} "
            f"len={len(result)}"
        )

    run_case(lines, "allowed host + stubbed success -> wrapped with source + intact closing marker", check_case1)

    # Case 2: disallowed host -- policy denial string, must stay unwrapped.
    result_denied = main.fetch_url(DENIED_URL)

    def check_case2():
        ok = result_denied.startswith("Denied by policy") and "<untrusted>" not in result_denied
        return ok, f"result={result_denied!r}"

    run_case(lines, "disallowed host -> Denied by policy, unwrapped", check_case2)

    # Case 3: allowed host, stubbed exception -- fetch-error string, must stay unwrapped.
    with mock.patch("urllib.request.urlopen", side_effect=OSError("stubbed network failure")):
        result_error = main.fetch_url(ALLOWED_URL)

    def check_case3():
        ok = result_error.startswith(f"Error fetching {ALLOWED_URL}") and "<untrusted>" not in result_error
        return ok, f"result={result_error!r}"

    run_case(lines, "stubbed fetch exception -> Error fetching, unwrapped", check_case3)

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    if any(line.startswith("[FAIL]") for line in lines):
        sys.exit(1)


if __name__ == "__main__":
    main_()
