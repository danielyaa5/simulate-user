---
name: simulate-user
description: "Simulate user reactions, design and UI/UX critiques, next prompt, scope decisions, and developer likeness, cutting down development time across the entire loop with an optimized fast-path for adversarial QA pushback and verification checks."
---

# Simulate User: UI/UX & design critique, decision simulation & adversarial QA

Predict the user's reactions, next prompt, UI/UX critiques, design/scope trade-offs, and likeness when requested, using their verified decision patterns from `~/.config/simulate-user/voice-and-thinking.md` (or local profile) and seed bank.

The simulator cuts down human round-trip development time across the full product loop: making routine design calls, tightening layout and interaction hierarchy, pruning UI friction, steering architecture trade-offs, and running adversarial QA verification cycles before the user ever looks.

## Core mechanics

1. **Isolated external critic (no builder blindness):** Never let the same agent turn that wrote code, copy, or designed a layout grade its own work inline. Run simulation turns in an isolated inspection subagent or via `scripts/build_prompt.py` with tools disabled.
2. **Two-level design and UI/UX critique:**
   - **Routine polish & friction elimination (Automated):** Consolidate split actions into 1-click execution, remove dead/stale controls after state changes, eliminate unnecessary confirmation prompts, fix cramped mobile spacing/overflow (375px/320px) and dark mode contrast, anchor pricing/flows to paying-customer fairness, and keep established house tokens and chosen visual targets intact. The simulator catches and fixes these across multiple rapid cycles without wasting the user's time.
   - **High-level visual direction choices (`needs_real_user`):** When the overall visual direction is open, prepare 2–3 distinct rendered options (A/B/C at desktop + mobile widths with 1 recommended direction) and halt for the user's taste pick rather than guessing.
3. **Codex-style abstention (`status: "abstain"`):** Do not invent nitpicks when work is solid and verified. When satisfied or uncertain, return `status: "abstain"` (`prediction: null`) and ship cleanly.
4. **Hard safety & taste gate (`status: "needs_real_user"`):** Immediately halt simulation and ask the real user whenever work hits:
   - Any sensitive action gate: outbound messages (email/SMS/posts), agreements, purchases/billing, physical hardware actuation, destructive data deletion, or public releases.
   - Pure subjective taste ties between sound alternatives, or unstated personal facts.
5. **Strict labeling & voice boundary:** Simulated dialogue must always be clearly labeled (`[Simulated User]`). Imagined replies never establish actual consent or approval, and never leak into ordinary assistant writing style.
6. **Passive calibration:** When the real user replies, record `hit`, `edited`, or `overridden` outcomes via `scripts/calibrate.py record` so the seed bank learns from real blind spots.

## Model & effort routing

- **Routine scripts, copy/UI tweaks, and small localized fixes:** Use fast, lightweight models (`flash` or `medium`).
- **Multi-file UX flows, high-stakes architecture, or ambiguous product trade-offs:** Reserve top-tier reasoning models (`high` / `xhigh`).
- **No double-stacking:** When an independent cross-model QA reviewer is already running on the same diff, fold the user's adversarial pushback checklist into that single review pass rather than spawning two separate heavy critic agents back-to-back.

---

## Operating modes

### Mode 1: QA fast-path (`qa_loop`)

Run before presenting an app build, UI screen, script, or bug fix to catch flaws before the user sees them:

1. **Assemble prompt:** Run `python3 scripts/build_prompt.py build --mode qa_loop --context-file <candidate_diff_or_summary>`.
2. **Run critic:** Dispatch to an isolated subagent or critic model.
3. **Validate output:** Pipe critic JSON to `python3 scripts/build_prompt.py validate`.
4. **Act on pushback:**
   - If `status == "pushback"`: Treat the predicted complaint as an active defect. Execute the `suggested_verification_action` (check cancel/abort buttons, verify post-action state, test focus isolation, verify repeat-bug prevention), fix the issue, and re-verify.
   - If `status == "abstain"`: All checks pass; present the completed work.
   - If `status == "needs_real_user"`: Surface the decision or gate to the real user.

### Mode 2: General simulation (`general`)

Use when the user explicitly asks to simulate a conversation, predict their next move, evaluate workflow decisions, or write in their likeness:

1. **Assemble prompt:** Run `python3 scripts/build_prompt.py build --mode general --context-file <context_file>`.
2. **Evaluate continuation:** High confidence (>0.6) yields `status: "suggest"`; low confidence or gated actions yield `status: "abstain"` or `status: "needs_real_user"`.
3. **Multi-round iteration:** Compare 2–3 finished options rather than prematurely collapsing to one speculative direction.

---

## Tooling & scripts

- **Build prompt:**
  ```bash
  python3 scripts/build_prompt.py build --mode qa_loop --context-file <diff.txt>
  ```
- **Validate output:**
  ```bash
  python3 scripts/build_prompt.py validate --input-file <critic_output.json>
  ```
- **Record calibration outcome:**
  ```bash
  python3 scripts/calibrate.py record --mode qa_loop --category untested_ui --predicted "cancel broken" --actual "the cancel buttons dont work" --outcome hit
  ```
- **View calibration stats:**
  ```bash
  python3 scripts/calibrate.py stats
  ```
- **Mine local transcripts for candidate seeds:**
  ```bash
  python3 scripts/mine_transcripts.py --limit 20
  ```

---

## References & seed manifest

- Schemas, templates & rubric: [references/rubric-and-schemas.md](references/rubric-and-schemas.md)
- Voice & thinking starter profile: [references/voice-and-thinking.example.md](references/voice-and-thinking.example.md)
- Ground-truth seed manifest: [seeds/index.json](seeds/index.json)
  - UI/UX & design critique seeds: [seeds/ui_ux_design.json](seeds/ui_ux_design.json)
  - QA verification seeds: [seeds/qa_verification.json](seeds/qa_verification.json)
  - UX & friction seeds: [seeds/ux_friction.json](seeds/ux_friction.json)
  - Scope & planning seeds: [seeds/scope_planning.json](seeds/scope_planning.json)
  - Momentum & execution seeds: [seeds/momentum_execution.json](seeds/momentum_execution.json)
