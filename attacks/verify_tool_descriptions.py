"""Deterministic proof that main.py's tool-schema description strings match current
v2 behavior (no v1/overwrite drift) and never leak a TOOL_POLICY value.

Calls main.load_policy() (a local file read, no network) and inspects the plain
main.ALL_TOOLS list of dicts directly -- no model call, no tool dispatch.

Unlike every other verify_*.py script, this one's run_case() never interpolates a
raw policy value (including OWNER_EMAIL) into any printed or logged string, pass or
fail -- a failure names which field and which policy key leaked into it, never the
value itself.

Run: python attacks/verify_tool_descriptions.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

import main  # noqa: E402  (reuse the real, unmodified tool schemas/policy loader)

ATTACKS_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(ATTACKS_DIR, "verify_tool_descriptions_log.txt")


def run_case(lines, label, ok, detail):
    outcome = "PASS" if ok else "FAIL"
    line = f"[{outcome}] {label}: {detail}"
    print(line)
    lines.append(line)


def _all_description_fields():
    """Yield (field_label, text) for every tool description and property description."""
    for tool in main.ALL_TOOLS:
        yield f"{tool['name']}.description", tool["description"]
        for prop_name, prop in tool.get("input_schema", {}).get("properties", {}).items():
            if "description" in prop:
                yield f"{tool['name']}.{prop_name}.description", prop["description"]


def _tool(name):
    return next(t for t in main.ALL_TOOLS if t["name"] == name)


def main_():
    load_dotenv()  # resolves $OWNER_EMAIL for tool_policy.json before load_policy()

    owner_email = os.environ.get("OWNER_EMAIL")
    if not owner_email:
        sys.exit("OWNER_EMAIL is not set. Add it to .env before running this script.")

    main.TOOL_POLICY = main.load_policy()

    lines = []
    fields = list(_all_description_fields())

    # --- Case 1: update_tracker no longer says "overwrite" -------------------
    ut_desc = main.UPDATE_TRACKER_TOOL["description"]
    ok = "overwrite" not in ut_desc.lower()
    run_case(lines, "update_tracker description doesn't say 'overwrite'", ok, f"absent={ok}")

    # --- Case 2: update_tracker content param doesn't say "full" -------------
    ut_content_desc = main.UPDATE_TRACKER_TOOL["input_schema"]["properties"]["content"]["description"]
    ok = "full" not in ut_content_desc.lower()
    run_case(lines, "update_tracker content param doesn't say 'full'", ok, f"absent={ok}")

    # --- Case 3: no description anywhere says "v1" ----------------------------
    v1_hits = [label for label, text in fields if "v1" in text.lower()]
    ok = not v1_hits
    run_case(lines, "no description contains 'v1'", ok, f"fields_with_v1={v1_hits}")

    # --- Case 4: no description leaks a TOOL_POLICY value ---------------------
    fetch_args = main.TOOL_POLICY["tools"]["fetch_url"]["args"]
    hosts = fetch_args.get("url_host", [])
    prefixes = [p for plist in fetch_args.get("url_path_prefix", {}).values() for p in plist]
    recipient = main.TOOL_POLICY["tools"]["send_digest"]["args"].get("recipient")
    recipients = recipient if isinstance(recipient, list) else [recipient]

    forbidden = {
        "fetch_url.url_host": hosts,
        "fetch_url.url_path_prefix": prefixes,
        "send_digest.recipient": recipients,
    }

    leaks = []  # (field_label, policy_key) pairs only -- never the leaked value itself
    for field_label, text in fields:
        for policy_key, values in forbidden.items():
            for value in values:
                if value and value in text:
                    leaks.append((field_label, policy_key))

    ok = not leaks
    run_case(lines, "no description leaks a TOOL_POLICY value", ok, f"leaked_fields={leaks}")

    # --- Case 5: update_tracker positively says "append" (an empty/absent ----
    # description would pass cases 1-2 vacuously; this proves real content) ---
    ok = "append" in ut_desc.lower()
    run_case(lines, "update_tracker description says 'append'", ok, f"present={ok}")

    # --- Case 6: the three approval-gated tools mention human denial ---------
    denial_mentioned = {
        name: "denied by a human" in _tool(name)["description"].lower()
        for name in ("append_memory", "update_tracker", "send_digest")
    }
    ok = all(denial_mentioned.values())
    run_case(lines, "append_memory/update_tracker/send_digest mention human denial", ok, f"{denial_mentioned}")

    # --- Case 7: fetch_url and read_inbox mention the <untrusted> boundary ---
    untrusted_mentioned = {
        name: "<untrusted>" in _tool(name)["description"]
        for name in ("fetch_url", "read_inbox")
    }
    ok = all(untrusted_mentioned.values())
    run_case(lines, "fetch_url/read_inbox descriptions contain '<untrusted>'", ok, f"{untrusted_mentioned}")

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # Belt-and-suspenders: the saved log must never contain the real owner email,
    # even though no case above should ever have printed/logged it in the first place.
    with open(LOG_PATH, encoding="utf-8") as f:
        logged_text = f.read()
    if owner_email in logged_text:
        print("[FAIL] post-write grep-confirm: real OWNER_EMAIL found in the log")
        sys.exit(1)

    if any(line.startswith("[FAIL]") for line in lines):
        sys.exit(1)


if __name__ == "__main__":
    main_()
