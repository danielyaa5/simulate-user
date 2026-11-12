#!/usr/bin/env python3
"""Build cache-stable simulation prompts and validate critic outputs for simulate-user.

Zero external dependencies. Python 3.9+.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
SEEDS_DIR = SKILL_DIR / "seeds"
DEFAULT_EXAMPLE_PROFILE = SKILL_DIR / "references" / "voice-and-thinking.example.md"
USER_CONFIG_PROFILE = Path.home() / ".config" / "simulate-user" / "voice-and-thinking.md"

GATED_ACTION_PATTERNS = [
    (re.compile(r"\b(send|draft and send|emailing|texting|imessage|beeper)\b.*?\b(email|sms|message|post|tweet)\b", re.I), "outbound communication"),
    (re.compile(r"\b(buy|purchase|charge|checkout|credit card|pay \$|refund)\b", re.I), "financial transaction"),
    (re.compile(r"\b(start print|heat bed|extrude|nozzle heating|home axes|bambu print|run cnc)\b", re.I), "physical hardware actuation"),
    (re.compile(r"\b(rm -rf /|drop database|delete account|wipe disk|format apfs|drop table)\b", re.I), "destructive deletion"),
    (re.compile(r"\b(submit to app store|npm publish|pypi upload|release to public|git push --tags)\b", re.I), "public release submission"),
]


def load_profile(custom_path: str = None) -> str:
    if custom_path:
        p = Path(custom_path)
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()

    env_path = os.environ.get("SIMULATE_USER_PROFILE")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()

    if USER_CONFIG_PROFILE.is_file():
        return USER_CONFIG_PROFILE.read_text(encoding="utf-8").strip()

    if DEFAULT_EXAMPLE_PROFILE.is_file():
        return DEFAULT_EXAMPLE_PROFILE.read_text(encoding="utf-8").strip()

    return "Developer Voice and Thinking Profile (Default / Unconfigured)"


def load_seeds(mode: str, categories: list = None) -> list:
    index_file = SEEDS_DIR / "index.json"
    if not index_file.is_file():
        return []
    try:
        index_data = json.loads(index_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    cat_map = index_data.get("categories", {})
    selected_files = []
    for cat_name, meta in cat_map.items():
        if categories and cat_name not in categories:
            continue
        if not categories and meta.get("mode") != mode and mode == "qa_loop" and cat_name != "qa_verification":
            continue
        file_path = SEEDS_DIR / meta.get("file", f"{cat_name}.json")
        if file_path.is_file():
            selected_files.append(file_path)

    seeds = []
    for sf in selected_files:
        try:
            entries = json.loads(sf.read_text(encoding="utf-8"))
            if isinstance(entries, list):
                seeds.extend(entries)
        except Exception:
            continue
    return seeds


def build_prompt(mode: str, context: str, categories: list = None, profile_path: str = None) -> str:
    profile = load_profile(profile_path)
    seeds = load_seeds(mode, categories)
    seeds_json = json.dumps(seeds, indent=2)

    if mode == "qa_loop":
        schema_desc = """
Respond ONLY with a JSON object matching this schema:
{
  "mode": "qa_loop",
  "status": "abstain" | "pushback" | "needs_real_user",
  "prediction": string | null,
  "instinct_category": "untested_ui" | "regression_risk" | "missing_preventative" | "left_open_state" | "focus_stealing" | "rule_regression" | "friction" | "scope_bloat" | "ui_design_critique" | null,
  "severity": "blocker" | "niggle" | null,
  "suggested_verification_action": string | null,
  "reasoning": string
}
Rules:
- If the candidate passes all checks and is verified clean, status="abstain", prediction=null.
- If the user would spot an issue (broken cancel, stale control, focus theft, mobile clipping, repeat bug), status="pushback" with exact prediction and concrete suggested_verification_action.
- If gated actions (outbound messaging, billing, physical actuation, destructive wipe) or open subjective taste ties are present, status="needs_real_user" and prediction=null.
"""
    else:
        schema_desc = """
Respond ONLY with a JSON object matching this schema:
{
  "mode": "general",
  "status": "suggest" | "abstain" | "needs_real_user",
  "prediction": string | null,
  "confidence": number between 0.0 and 1.0,
  "instinct_category": "ui_ux_design" | "ux_friction" | "scope_planning" | "momentum_execution" | "customer_fairness" | "hardware_routing" | "quota_routing" | "likeness" | null,
  "reasoning": string
}
Rules:
- If predicting the user's next prompt, design critique, or trade-off decision, status="suggest".
- If no clear continuation or confidence < 0.6, status="abstain", prediction=null.
- If gated actions (outbound messaging, billing, physical actuation, destructive wipe) or open subjective taste ties are present, status="needs_real_user" and prediction=null.
"""

    prompt = f"""You are an isolated external critic evaluating work for the user.
Your job is to simulate their authentic reactions, pushback, next moves, UI/UX critiques, or QA tests using their established decision patterns.
Do NOT invent nitpicks if the work is verified and solid. When satisfied or uncertain, ABSTAIN.

### STATIC REFERENCE: User's Voice & Thinking Profile
{profile}

### FEW-SHOT GROUND TRUTH EXAMPLES
{seeds_json}

### EVALUATION INSTRUCTIONS & SCHEMA
{schema_desc}

### CANDIDATE FOR EVALUATION (DYNAMIC INPUT)
{context.strip()}
"""
    return prompt


def validate_output(payload_str: str) -> tuple[bool, str]:
    cleaned = payload_str.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except Exception as e:
        return False, f"JSON decode error: {e}"

    if not isinstance(data, dict):
        return False, "Payload must be a JSON object."

    mode = data.get("mode")
    if mode not in ("qa_loop", "general"):
        return False, f"Invalid or missing mode: {mode}"

    status = data.get("status")
    if mode == "qa_loop":
        if status not in ("abstain", "pushback", "needs_real_user"):
            return False, f"Invalid qa_loop status: {status}"
        for req in ("mode", "status", "prediction", "reasoning"):
            if req not in data:
                return False, f"Missing required field in qa_loop: {req}"
        if status in ("abstain", "needs_real_user") and data.get("prediction") is not None:
            return False, f"prediction must be null when status is {status}"
        if status == "pushback" and not data.get("prediction"):
            return False, "prediction must be a non-empty string when status is pushback"
    else:
        if status not in ("suggest", "abstain", "needs_real_user"):
            return False, f"Invalid general status: {status}"
        for req in ("mode", "status", "prediction", "confidence", "reasoning"):
            if req not in data:
                return False, f"Missing required field in general: {req}"
        if status in ("abstain", "needs_real_user") and data.get("prediction") is not None:
            return False, f"prediction must be null when status is {status}"
        if status == "suggest" and not data.get("prediction"):
            return False, "prediction must be a non-empty string when status is suggest"
        conf = data.get("confidence")
        if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
            return False, f"confidence must be a number between 0.0 and 1.0, got {conf}"

    # Safety Gate Check: Ensure simulator never gives simulated approval to gated actions
    pred_text = str(data.get("prediction") or "") + " " + str(data.get("suggested_verification_action") or "")
    if status != "needs_real_user":
        for pat, action_desc in GATED_ACTION_PATTERNS:
            if pat.search(pred_text):
                return False, f"Safety violation: Simulated output touches {action_desc} without status='needs_real_user'."

    return True, "Valid"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    build_p = subparsers.add_parser("build", help="Build cache-stable simulation prompt")
    build_p.add_argument("--mode", choices=["qa_loop", "general"], default="qa_loop", help="Operating mode")
    build_p.add_argument("--category", action="append", dest="categories", help="Specific seed category to include")
    build_p.add_argument("--profile", help="Path to custom voice-and-thinking profile markdown file")
    build_p.add_argument("--context-file", help="Path to file containing candidate summary/diff")

    val_p = subparsers.add_parser("validate", help="Validate critic JSON output against schema and safety gates")
    val_p.add_argument("--input-file", help="Path to JSON file to validate (defaults to stdin)")

    args = parser.parse_args()

    if args.command == "validate":
        if args.input_file:
            content = Path(args.input_file).read_text(encoding="utf-8")
        else:
            content = sys.stdin.read()
        valid, msg = validate_output(content)
        if valid:
            print(f"OK: {msg}")
            sys.exit(0)
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
            sys.exit(1)
    else:
        mode = getattr(args, "mode", "qa_loop")
        categories = getattr(args, "categories", None)
        profile_path = getattr(args, "profile", None)
        context_file = getattr(args, "context_file", None)
        if context_file:
            context = Path(context_file).read_text(encoding="utf-8")
        elif not sys.stdin.isatty():
            context = sys.stdin.read()
        else:
            context = "Candidate deliverable ready for evaluation."

        prompt = build_prompt(mode, context, categories, profile_path)
        print(prompt)


if __name__ == "__main__":
    main()
