"""Deterministic proof that vuln F's planted secret is gone from prompts/system.md.
No model call, no network -- a plain file read and a few substring checks.

Run: python attacks/verify_f_no_secret.py
"""

import os
import sys

ATTACKS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(ATTACKS_DIR)
SYSTEM_PROMPT_PATH = os.path.join(REPO_ROOT, "prompts", "system.md")
LOG_PATH = os.path.join(ATTACKS_DIR, "verify_f_no_secret_log.txt")


def run_case(lines, label, ok, detail):
    outcome = "PASS" if ok else "FAIL"
    line = f"[{outcome}] {label}: {detail}"
    print(line)
    lines.append(line)


def main_():
    lines = []

    # Presence checks first -- an empty or missing file would vacuously pass the
    # two absence checks below, so those alone aren't proof of anything.
    exists = os.path.exists(SYSTEM_PROMPT_PATH)
    run_case(lines, "prompts/system.md exists", exists, f"exists={exists}")

    text = open(SYSTEM_PROMPT_PATH, encoding="utf-8").read() if exists else ""

    ok = exists and "WITI" in text
    run_case(lines, "prompts/system.md contains 'WITI' (file is not empty/missing)", ok, f"present={ok}")

    ok = "INTERNAL_OPS_KEY" not in text
    run_case(lines, "prompts/system.md does not contain 'INTERNAL_OPS_KEY'", ok, f"absent={ok}")

    ok = "sk-demo" not in text
    run_case(lines, "prompts/system.md does not contain 'sk-demo'", ok, f"absent={ok}")

    passed = sum(1 for line in lines if line.startswith("[PASS]"))
    total = len(lines)
    summary = f"{passed}/{total} PASS"
    print(summary)
    lines.append(summary)

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    if any(line.startswith("[FAIL]") for line in lines):
        sys.exit(1)


if __name__ == "__main__":
    main_()
