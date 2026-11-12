#!/usr/bin/env python3
"""Passive calibration logger and analyzer for simulate-user.

Records simulation outcomes against real user turns and tracks precision.
Zero external dependencies. Python 3.9+.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

DEFAULT_LOG_PATH = Path.home() / ".config" / "simulate-user" / "calibration.jsonl"


def get_default_log_path() -> Path:
    env_log = os.environ.get("SIMULATE_USER_CALIBRATION_LOG")
    if env_log:
        return Path(env_log)
    return DEFAULT_LOG_PATH


def record_outcome(
    log_path: Path,
    mode: str,
    category: str,
    predicted: str,
    actual: str,
    outcome: str,
    lesson: str = ""
) -> dict:
    if outcome not in ("hit", "edited", "overridden"):
        raise ValueError(f"Invalid outcome: {outcome}. Must be 'hit', 'edited', or 'overridden'.")

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "category": category,
        "predicted": predicted,
        "actual_user_reply": actual,
        "outcome": outcome,
        "lesson": lesson
    }

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


def compute_stats(log_path: Path) -> dict:
    if not log_path.is_file():
        return {"total": 0, "hits": 0, "edited": 0, "overridden": 0, "categories": {}}

    total = 0
    hits = 0
    edited = 0
    overridden = 0
    cat_stats = {}

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            total += 1
            out = row.get("outcome")
            cat = row.get("category", "unknown")

            if out == "hit":
                hits += 1
            elif out == "edited":
                edited += 1
            elif out == "overridden":
                overridden += 1

            if cat not in cat_stats:
                cat_stats[cat] = {"total": 0, "hit": 0, "edited": 0, "overridden": 0}
            cat_stats[cat]["total"] += 1
            if out in cat_stats[cat]:
                cat_stats[cat][out] += 1

    hit_rate = (hits / total * 100) if total else 0.0
    edit_rate = (edited / total * 100) if total else 0.0
    override_rate = (overridden / total * 100) if total else 0.0

    return {
        "total": total,
        "hits": hits,
        "edited": edited,
        "overridden": overridden,
        "hit_rate_pct": round(hit_rate, 1),
        "edited_rate_pct": round(edit_rate, 1),
        "override_rate_pct": round(override_rate, 1),
        "categories": cat_stats
    }


def export_candidates(log_path: Path, min_outcome: str = "overridden") -> list:
    if not log_path.is_file():
        return []
    candidates = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if min_outcome == "all" or row.get("outcome") == min_outcome or (min_outcome == "misses" and row.get("outcome") in ("edited", "overridden")):
                candidates.append(row)
    return candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-file", help="Override path to calibration JSONL file")
    subparsers = parser.add_subparsers(dest="command")

    rec_p = subparsers.add_parser("record", help="Record simulation calibration outcome")
    rec_p.add_argument("--mode", choices=["qa_loop", "general"], required=True, help="Operating mode")
    rec_p.add_argument("--category", required=True, help="Category name (e.g. ui_ux_design, untested_ui, scope_planning)")
    rec_p.add_argument("--predicted", required=True, help="What was predicted")
    rec_p.add_argument("--actual", required=True, help="What user actually said or did")
    rec_p.add_argument("--outcome", choices=["hit", "edited", "overridden"], required=True, help="Outcome type")
    rec_p.add_argument("--lesson", default="", help="Optional takeaway or lesson")

    subparsers.add_parser("stats", help="Compute calibration summary stats")

    exp_p = subparsers.add_parser("export-candidates", help="Export high-signal misses for seed promotion")
    exp_p.add_argument("--filter", choices=["all", "misses", "overridden", "edited"], default="misses", help="Filter criteria")

    args = parser.parse_args()
    log_path = Path(args.log_file) if args.log_file else get_default_log_path()

    if args.command == "record":
        entry = record_outcome(
            log_path=log_path,
            mode=args.mode,
            category=args.category,
            predicted=args.predicted,
            actual=args.actual,
            outcome=args.outcome,
            lesson=args.lesson
        )
        print(f"Recorded outcome: {entry['outcome']} ({entry['mode']}/{entry['category']}) -> {log_path}")
    elif args.command == "stats":
        stats = compute_stats(log_path)
        print(json.dumps(stats, indent=2))
    elif args.command == "export-candidates":
        cands = export_candidates(log_path, min_outcome=args.filter)
        print(json.dumps(cands, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
