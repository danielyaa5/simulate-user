#!/usr/bin/env python3
"""Unit test suite for simulate-user skill.

Runs with: python3 -B -m unittest discover -s tests
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

TEST_DIR = Path(__file__).resolve().parent
SKILL_DIR = TEST_DIR.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
SEEDS_DIR = SKILL_DIR / "seeds"

sys.path.insert(0, str(SCRIPTS_DIR))
from build_prompt import build_prompt, load_seeds, validate_output
from calibrate import compute_stats, export_candidates, record_outcome
from mine_transcripts import clean_user_reply, is_system_noise


class TestSimulateUserSeeds(unittest.TestCase):
    """Verify that all seed files parse cleanly, adhere to schema, and contain abstain examples."""

    def test_seed_manifest_and_files(self):
        index_path = SEEDS_DIR / "index.json"
        self.assertTrue(index_path.is_file(), "index.json must exist in seeds/")
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertIn("categories", index_data)

        total_entries = 0
        abstain_count = 0

        for cat_name, meta in index_data["categories"].items():
            seed_file = SEEDS_DIR / meta["file"]
            self.assertTrue(seed_file.is_file(), f"Seed file {seed_file} must exist")
            entries = json.loads(seed_file.read_text(encoding="utf-8"))
            self.assertIsInstance(entries, list, f"{seed_file.name} must be a list of seed entries")
            self.assertGreater(len(entries), 0, f"{seed_file.name} must not be empty")

            for entry in entries:
                total_entries += 1
                for field in ("id", "category", "source", "assistant_state", "instinct", "is_abstain"):
                    self.assertIn(field, entry, f"Missing {field} in {entry.get('id')}")
                if entry["is_abstain"]:
                    abstain_count += 1
                    self.assertIsNone(entry["user_reply"], f"Abstain entry {entry['id']} must have null user_reply")
                else:
                    self.assertIsNotNone(entry["user_reply"], f"Non-abstain entry {entry['id']} must have a string user_reply")

        self.assertGreaterEqual(total_entries, 20, "Must contain at least 20 starter seed examples")
        self.assertGreaterEqual(abstain_count, 4, "Must contain positive abstain calibration examples")


class TestBuildPrompt(unittest.TestCase):
    """Verify deterministic static prefix ordering and mode/category selection."""

    def test_static_prefix_ordering(self):
        context = "User asks to review changed UI layout and verify mobile responsiveness."
        prompt = build_prompt(mode="qa_loop", context=context)

        pos_profile = prompt.find("### STATIC REFERENCE: User's Voice & Thinking Profile")
        pos_seeds = prompt.find("### FEW-SHOT GROUND TRUTH EXAMPLES")
        pos_schema = prompt.find("### EVALUATION INSTRUCTIONS & SCHEMA")
        pos_candidate = prompt.find("### CANDIDATE FOR EVALUATION (DYNAMIC INPUT)")

        self.assertNotEqual(pos_profile, -1)
        self.assertNotEqual(pos_seeds, -1)
        self.assertNotEqual(pos_schema, -1)
        self.assertNotEqual(pos_candidate, -1)

        # Enforce deterministic order for prefix caching:
        # Profile -> Seeds -> Schema -> Candidate
        self.assertLess(pos_profile, pos_seeds)
        self.assertLess(pos_seeds, pos_schema)
        self.assertLess(pos_schema, pos_candidate)
        self.assertIn(context, prompt[pos_candidate:])

    def test_mode_selection_and_seeds(self):
        qa_seeds = load_seeds(mode="qa_loop")
        self.assertTrue(all(s["category"] == "qa_verification" for s in qa_seeds))

        general_seeds = load_seeds(mode="general")
        self.assertTrue(any(s["category"] == "ux_friction" for s in general_seeds))
        self.assertTrue(any(s["category"] == "scope_planning" for s in general_seeds))
        self.assertTrue(any(s["category"] == "ui_ux_design" for s in general_seeds))
        self.assertTrue(any(s["category"] == "momentum_execution" for s in general_seeds))


class TestValidateOutput(unittest.TestCase):
    """Verify schema checking and safety gating in validate_output."""

    def test_valid_qa_pushback(self):
        payload = json.dumps({
            "mode": "qa_loop",
            "status": "pushback",
            "prediction": "the cancel buttons dont work during export",
            "instinct_category": "untested_ui",
            "severity": "blocker",
            "suggested_verification_action": "Test cancel button during active run",
            "reasoning": "Negative state tests are mandatory."
        })
        valid, msg = validate_output(payload)
        self.assertTrue(valid, msg)

    def test_valid_qa_abstain(self):
        payload = json.dumps({
            "mode": "qa_loop",
            "status": "abstain",
            "prediction": None,
            "instinct_category": None,
            "severity": None,
            "suggested_verification_action": None,
            "reasoning": "All unit tests pass and cancel path is verified clean."
        })
        valid, msg = validate_output(payload)
        self.assertTrue(valid, msg)

    def test_valid_qa_needs_real_user(self):
        payload = json.dumps({
            "mode": "qa_loop",
            "status": "needs_real_user",
            "prediction": None,
            "instinct_category": None,
            "severity": None,
            "suggested_verification_action": None,
            "reasoning": "Requires real user decision on visual branding direction."
        })
        valid, msg = validate_output(payload)
        self.assertTrue(valid, msg)

    def test_valid_general_suggest(self):
        payload = json.dumps({
            "mode": "general",
            "status": "suggest",
            "prediction": "combine this into 1 button that executes immediately in the terminal",
            "confidence": 0.88,
            "instinct_category": "ui_ux_design",
            "reasoning": "User prefers consolidating fragmented actions."
        })
        valid, msg = validate_output(payload)
        self.assertTrue(valid, msg)

    def test_invalid_abstain_with_prediction(self):
        payload = json.dumps({
            "mode": "qa_loop",
            "status": "abstain",
            "prediction": "I think this is okay",
            "reasoning": "Invalid non-null prediction."
        })
        valid, msg = validate_output(payload)
        self.assertFalse(valid)
        self.assertIn("prediction must be null", msg)

    def test_safety_gate_violations(self):
        # Email simulated without needs_real_user
        payload_email = json.dumps({
            "mode": "general",
            "status": "suggest",
            "prediction": "Send email to customer confirming the refund",
            "confidence": 0.9,
            "instinct_category": "ux_friction",
            "reasoning": "Email customer."
        })
        valid, msg = validate_output(payload_email)
        self.assertFalse(valid)
        self.assertIn("outbound communication", msg)

        # Destructive delete simulated without needs_real_user
        payload_delete = json.dumps({
            "mode": "qa_loop",
            "status": "pushback",
            "prediction": "Run rm -rf / to wipe disk",
            "suggested_verification_action": "rm -rf /",
            "reasoning": "Destructive."
        })
        valid, msg = validate_output(payload_delete)
        self.assertFalse(valid)
        self.assertIn("destructive deletion", msg)


class TestCalibrate(unittest.TestCase):
    """Verify outcome recording, summary statistics, and candidate filtering."""

    def test_record_and_compute_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "calibration.jsonl"
            record_outcome(log_path, "qa_loop", "untested_ui", "cancel broken", "the cancel buttons dont work", "hit", "Exact match")
            record_outcome(log_path, "general", "momentum_execution", "go", "go, only caveat do 60s timeout", "edited", "Parameter tweak")
            record_outcome(log_path, "general", "scope_planning", "ask 5 questions", "Work in smaller steps", "overridden", "Rejected questionnaire")

            stats = compute_stats(log_path)
            self.assertEqual(stats["total"], 3)
            self.assertEqual(stats["hits"], 1)
            self.assertEqual(stats["edited"], 1)
            self.assertEqual(stats["overridden"], 1)
            self.assertEqual(stats["hit_rate_pct"], 33.3)
            self.assertEqual(stats["override_rate_pct"], 33.3)

            candidates = export_candidates(log_path, min_outcome="misses")
            self.assertEqual(len(candidates), 2)


class TestMineTranscripts(unittest.TestCase):
    """Verify noise filtering and synthetic transcript parsing."""

    def test_noise_detection(self):
        self.assertTrue(is_system_noise("<SYSTEM_MESSAGE> You are an agent </SYSTEM_MESSAGE>"))
        self.assertTrue(is_system_noise("<INSTRUCTIONS> Do this </INSTRUCTIONS>"))
        self.assertTrue(is_system_noise("[Message] timestamp=2026-11-11T22:00:00Z sender=abc priority=HIGH"))
        self.assertTrue(is_system_noise("<bash-input> ls -la </bash-input>"))
        self.assertTrue(is_system_noise("<local-command-stdout> ok </local-command-stdout>"))
        self.assertFalse(is_system_noise("the cancel buttons dont work"))
        self.assertFalse(is_system_noise("Work in smaller steps"))

    def test_clean_user_reply(self):
        wrapped = """
        <USER_REQUEST>
        can you combine this in 1 button
        </USER_REQUEST>
        <ADDITIONAL_METADATA>
        The current local time is: 2026-10-18T16:50:17-07:00.
        </ADDITIONAL_METADATA>
        """
        cleaned = clean_user_reply(wrapped)
        self.assertEqual(cleaned, "can you combine this in 1 button")


if __name__ == "__main__":
    unittest.main()
