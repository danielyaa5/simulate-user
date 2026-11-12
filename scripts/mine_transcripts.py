#!/usr/bin/env python3
"""Mine real (assistant_tail -> user_reply) transitions from local transcripts.

Scans local Antigravity, Claude Code, and Codex session logs to surface
human feedback pairs for seed curation and simulation calibration.
Zero external dependencies. Python 3.9+.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

HOME = Path.home()
ANTIGRAVITY_DIR = HOME / ".gemini" / "antigravity" / "brain"
CLAUDE_DIR = HOME / ".claude" / "projects"
CODEX_DIR = HOME / ".codex" / "sessions"

SYSTEM_NOISE_PATTERNS = [
    re.compile(r"^<SYSTEM_MESSAGE>", re.I),
    re.compile(r"^<INSTRUCTIONS>", re.I),
    re.compile(r"^\[Message\]\s+timestamp=", re.I),
    re.compile(r"^<bash-input>", re.I),
    re.compile(r"^<local-command-stdout>", re.I),
    re.compile(r"^<agent-notification>", re.I),
    re.compile(r"^\[Request interrupted by user", re.I),
]


def is_system_noise(text: str) -> bool:
    if not text or not text.strip():
        return True
    stripped = text.strip()
    for pat in SYSTEM_NOISE_PATTERNS:
        if pat.search(stripped):
            return True
    return False


def clean_text(text: str, max_chars: int = 4000) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"```[\s\S]*?```", "[code block]", cleaned)
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "... [truncated]"
    return cleaned


def clean_user_reply(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"<ADDITIONAL_METADATA>[\s\S]*?</ADDITIONAL_METADATA>", "", cleaned, flags=re.I).strip()
    m = re.search(r"<USER_REQUEST>([\s\S]*?)</USER_REQUEST>", cleaned, flags=re.I)
    if m:
        cleaned = m.group(1).strip()
    return cleaned


def mine_antigravity(limit: int = 50) -> list:
    pairs = []
    if not ANTIGRAVITY_DIR.is_dir():
        return pairs

    for conv_dir in ANTIGRAVITY_DIR.glob("*"):
        log_file = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
        if not log_file.is_file():
            continue
        try:
            last_assistant = None
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        step = json.loads(line)
                    except Exception:
                        continue
                    source = step.get("source")
                    step_type = step.get("type")
                    content = step.get("content", "")

                    if source == "MODEL" or step_type == "PLANNER_RESPONSE":
                        if content and not is_system_noise(content):
                            last_assistant = content
                    elif source == "USER_EXPLICIT" or step_type == "USER_INPUT":
                        if content and not is_system_noise(content):
                            if last_assistant:
                                pairs.append({
                                    "engine": "antigravity",
                                    "session": conv_dir.name,
                                    "assistant_tail": clean_text(last_assistant),
                                    "user_reply": clean_user_reply(content)
                                })
                                last_assistant = None
                                if len(pairs) >= limit:
                                    return pairs
        except Exception:
            continue
    return pairs


def mine_claude(limit: int = 50) -> list:
    pairs = []
    if not CLAUDE_DIR.is_dir():
        return pairs

    for project_dir in CLAUDE_DIR.glob("*"):
        for log_file in project_dir.glob("*.jsonl"):
            try:
                last_assistant = None
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            msg = json.loads(line)
                        except Exception:
                            continue
                        role = msg.get("role") or msg.get("type")
                        content = ""
                        raw_c = msg.get("content") or msg.get("message", {}).get("content")
                        if isinstance(raw_c, str):
                            content = raw_c
                        elif isinstance(raw_c, list):
                            text_parts = [b.get("text", "") for b in raw_c if isinstance(b, dict) and b.get("type") == "text"]
                            content = " ".join(text_parts)

                        if role in ("assistant", "MODEL"):
                            if content and not is_system_noise(content):
                                last_assistant = content
                        elif role in ("user", "human"):
                            if content and not is_system_noise(content):
                                if last_assistant:
                                    pairs.append({
                                        "engine": "claude",
                                        "session": log_file.stem,
                                        "assistant_tail": clean_text(last_assistant),
                                        "user_reply": clean_user_reply(content)
                                    })
                                    last_assistant = None
                                    if len(pairs) >= limit:
                                        return pairs
            except Exception:
                continue
    return pairs


def mine_codex(limit: int = 50) -> list:
    pairs = []
    if not CODEX_DIR.is_dir():
        return pairs

    for log_file in CODEX_DIR.glob("**/*.jsonl"):
        try:
            last_assistant = None
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        turn = json.loads(line)
                    except Exception:
                        continue
                    role = turn.get("role")
                    content = ""
                    raw_c = turn.get("content")
                    if isinstance(raw_c, str):
                        content = raw_c
                    elif isinstance(raw_c, list):
                        parts = []
                        for p in raw_c:
                            if isinstance(p, dict) and p.get("type") in ("text", "user.text"):
                                parts.append(p.get("text", ""))
                            elif isinstance(p, str):
                                parts.append(p)
                        content = " ".join(parts)

                    if role == "assistant":
                        if content and not is_system_noise(content):
                            last_assistant = content
                    elif role == "user":
                        prov = turn.get("provenance", {})
                        if isinstance(prov, dict) and prov.get("type") == "system":
                            continue
                        if content and not is_system_noise(content):
                            if last_assistant:
                                pairs.append({
                                    "engine": "codex",
                                    "session": log_file.stem,
                                    "assistant_tail": clean_text(last_assistant),
                                    "user_reply": clean_user_reply(content)
                                })
                                last_assistant = None
                                if len(pairs) >= limit:
                                    return pairs
        except Exception:
            continue
    return pairs


def mine_all(engine: str = "all", limit: int = 30) -> list:
    results = []
    if engine in ("antigravity", "all"):
        results.extend(mine_antigravity(limit=limit))
    if engine in ("claude", "all") and len(results) < limit:
        results.extend(mine_claude(limit=limit - len(results)))
    if engine in ("codex", "all") and len(results) < limit:
        results.extend(mine_codex(limit=limit - len(results)))
    return results[:limit]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["antigravity", "claude", "codex", "all"], default="all", help="Target engine transcripts")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of transition pairs to output")
    parser.add_argument("--output", help="Save results to JSON file instead of printing")

    args = parser.parse_args()
    pairs = mine_all(engine=args.engine, limit=args.limit)

    if args.output:
        Path(args.output).write_text(json.dumps(pairs, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Mined {len(pairs)} transitions to {args.output}")
    else:
        print(json.dumps(pairs, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
