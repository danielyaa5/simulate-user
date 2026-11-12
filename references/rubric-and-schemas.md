# Rubric, Schemas, and Prompt Templates for `simulate-user`

This reference documents the JSON schemas, system prompt templates, and decision heuristics used by the `simulate-user` skill.

---

## 1. Operating Modes & JSON Schemas

### Mode A: `qa_loop` (Fast-Path for App, UI, Script, and Fix Verification)

Designed to run right before presenting completed work, a UI screen, an app build, or a bug fix to prevent builder blindness.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "SimulateUserQALoopOutput",
  "type": "object",
  "properties": {
    "mode": {
      "type": "string",
      "enum": ["qa_loop"]
    },
    "status": {
      "type": "string",
      "enum": ["abstain", "pushback", "needs_real_user"],
      "description": "'abstain' when output is solid and ready to ship; 'pushback' when the user would spot a flaw; 'needs_real_user' if a safety boundary or taste tie is hit."
    },
    "prediction": {
      "type": ["string", "null"],
      "description": "Simulated user complaint or reaction. Must be null if status is 'abstain' or 'needs_real_user'."
    },
    "instinct_category": {
      "type": ["string", "null"],
      "enum": [
        "untested_ui",
        "regression_risk",
        "missing_preventative",
        "left_open_state",
        "focus_stealing",
        "rule_regression",
        "friction",
        "scope_bloat",
        null
      ]
    },
    "severity": {
      "type": ["string", "null"],
      "enum": ["blocker", "niggle", null]
    },
    "suggested_verification_action": {
      "type": ["string", "null"],
      "description": "Concrete verification command or test check before shipping."
    },
    "reasoning": {
      "type": "string",
      "description": "Internal model rationale referencing the user's verified patterns."
    }
  },
  "required": ["mode", "status", "prediction", "reasoning"],
  "additionalProperties": false
}
```

### Mode B: `general` (Prompt Prediction, Scope, Trade-offs & Likeness)

Designed for predicting the user's next turn, evaluating workflow decisions, comparing 2–3 options, or writing in their likeness when explicitly requested.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "SimulateUserGeneralOutput",
  "type": "object",
  "properties": {
    "mode": {
      "type": "string",
      "enum": ["general"]
    },
    "status": {
      "type": "string",
      "enum": ["suggest", "abstain", "needs_real_user"],
      "description": "'suggest' when predicting a likely next prompt or direction; 'abstain' when confidence is low or no pushback is expected; 'needs_real_user' when hitting gated actions."
    },
    "prediction": {
      "type": ["string", "null"],
      "description": "The simulated text, prompt, or feedback. Must be null if status is 'abstain' or 'needs_real_user'."
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "Confidence score from 0.0 to 1.0."
    },
    "instinct_category": {
      "type": ["string", "null"],
      "enum": [
        "scope_planning",
        "ux_friction",
        "momentum_execution",
        "customer_fairness",
        "hardware_routing",
        "quota_routing",
        "likeness",
        null
      ]
    },
    "reasoning": {
      "type": "string",
      "description": "Internal justification grounded in the user's voice and thinking profile."
    }
  },
  "required": ["mode", "status", "prediction", "confidence", "reasoning"],
  "additionalProperties": false
}
```

---

## 2. Hard Safety & Taste Boundaries (`needs_real_user`)

The simulator **must immediately halt and return `status: "needs_real_user"`** whenever a proposed turn or candidate involves:

1. **Outbound Communications:** Email, SMS, messaging app chats, support tickets, public forum posts, or tweets.
2. **Legal & Financial Commitments:** Agreements, contracts, purchasing, payments, subscription cancellations, or billing changes.
3. **Physical Hardware Actuation:** Starting a 3D print, heating a bed, running CNC/lasers, opening gates, or physical robotic movements.
4. **Destructive Data Deletion:** Irreversible deletion of user files, databases, or cloud resources.
5. **Public Releases:** Publishing packages to npm/PyPI, submitting to app stores, or making public Git tags/releases.
6. **Pure Subjective Taste Ties:** When choosing between two equally sound creative or aesthetic directions where no prior preference exists.

---

## 3. Prefix-Cache Friendly System Prompt Template

To maximize prompt caching across repeated cycles, static profile notes and seeds are placed deterministically at the top of the prompt. Dynamic inputs (diffs, candidates, recent turns) are appended at the bottom.

```text
You are an isolated external critic evaluating work for the user.
Your job is to simulate their authentic reactions, pushback, next moves, or QA tests using established decision patterns.
Do NOT invent nitpicks if the work is verified and solid. When satisfied or uncertain, ABSTAIN.

### STATIC REFERENCE: User's Voice & Thinking Profile
{profile_text}

### FEW-SHOT GROUND TRUTH EXAMPLES ({category})
{seeds_json}

### EVALUATION INSTRUCTIONS & SCHEMA
{schema_desc}

### CANDIDATE FOR EVALUATION (DYNAMIC INPUT)
{dynamic_context}
```

---

## 4. Core Decision Heuristics Checklist

When simulating pushback, check against these verified behaviors:

- **Cancel & Abort Paths:** Does cancel work immediately during active long-running jobs? Are temp files and background tasks cleaned up?
- **Stale Post-Action State:** After an item is deleted or action is finished, are old action buttons (Delete, Open, Retry) disabled or removed immediately?
- **Zero Focus Stealing:** Are background browser checks using headless or inactive background tabs? Did any command steal foreground window focus?
- **Preventative Hardening:** Does this fix prevent all instances of the bug, or is it just an ad-hoc band-aid?
- **Friction Elimination:** Are terminal commands offered with 1-click execution rather than requiring manual copy-paste? Are unnecessary confirmation prompts removed?
- **Incremental Steps:** Does this break progress into concrete, verifiable baby steps rather than an upfront multi-question questionnaire?
- **Coordinator Availability:** Is the primary chat staying interactive and responsive, delegating heavy reads and planning to subagents?
- **Physical Clarity:** For physical hardware or configuration steps, are direct answers provided first before technical explanations?
