"""Runs all eight attacks/verify_*.py scripts as subprocesses, reports one line per
script (name, passed/total, exit code) plus an overall total, and exits non-zero if
any script failed. No model call, no network -- each script already handles that.

Run: python attacks/run_all_verify.py
"""

import os
import re
import subprocess
import sys

ATTACKS_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

SCRIPTS = [
    "verify_ab_patch.py",
    "verify_a_untrusted_wrap.py",
    "verify_path_and_redirect.py",
    "verify_marker_breakout.py",
    "verify_generic_denials.py",
    "verify_tool_descriptions.py",
    "verify_v2_cdegh.py",
    "verify_f_no_secret.py",
]

SUMMARY_RE = re.compile(r"^(\d+)/(\d+) PASS$")


def main():
    overall_passed = 0
    overall_total = 0
    any_failed = False

    for name in SCRIPTS:
        path = os.path.join(ATTACKS_DIR, name)
        result = subprocess.run([PYTHON, path], capture_output=True, text=True)

        match = None
        for line in reversed(result.stdout.splitlines()):
            match = SUMMARY_RE.match(line.strip())
            if match:
                break

        exit_code = result.returncode
        if exit_code != 0:
            any_failed = True

        if match:
            passed, total = int(match.group(1)), int(match.group(2))
            overall_passed += passed
            overall_total += total
            print(f"{name}: {passed}/{total} PASS, exit={exit_code}")
        else:
            any_failed = True
            print(f"{name}: NO SUMMARY LINE FOUND, exit={exit_code}")
            if result.stderr.strip():
                print(f"  stderr: {result.stderr.strip().splitlines()[-1]}")

    print(f"\nOVERALL: {overall_passed}/{overall_total} PASS")
    if any_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
