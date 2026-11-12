# simulate-user

> Simulate user reactions, UI/UX critiques, next prompts, and design decisions to cut down development round-trips before presenting work.

Built for **Claude Code**, **OpenAI Codex**, and **Google Antigravity**.

When you write code or design interfaces with an AI agent, you spend significant time reviewing drafts, spotting obvious mobile overflow or stale buttons, testing negative cancel paths, and typing out the same predictable feedback. `simulate-user` turns the mechanism behind predictive ghost-text into an autonomous pre-flight critic: an isolated model simulates your instincts, catches design flaws and regressions, and refines work before you ever look.

Read the background post: [Simulating my own brain to cut down on development time. How I reverse engineered the Codex predictive text.](https://danielyakobian.com/blog/predictive-agent-qa.html)

---

## Quickstart

### 1. Install the skill

Clone the repository and symlink it into your agent's skills directory:

```bash
git clone https://github.com/danielyaa5/simulate-user.git ~/Developer/simulate-user

# For Claude Code:
mkdir -p ~/.claude/skills
ln -s ~/Developer/simulate-user ~/.claude/skills/simulate-user

# For OpenAI Codex:
mkdir -p ~/.agents/skills
ln -s ~/Developer/simulate-user ~/.agents/skills/simulate-user

# For Google Antigravity:
mkdir -p ~/.gemini/config/skills
ln -s ~/Developer/simulate-user ~/.gemini/config/skills/simulate-user
```

### 2. Set up your personal profile

Copy the starter profile template to `~/.config/simulate-user/`:

```bash
mkdir -p ~/.config/simulate-user
cp ~/Developer/simulate-user/references/voice-and-thinking.example.md ~/.config/simulate-user/voice-and-thinking.md
```

Edit `~/.config/simulate-user/voice-and-thinking.md` with your own preferences: your communication style, design tokens, negative testing instincts (e.g. testing cancel/abort paths, zero unrequested desktop window focus theft), and sensitive actions that must always halt for human confirmation.

### 3. Mine your local session transcripts

Extract your real human feedback transitions from your past local agent sessions (Claude Code, Codex, or Antigravity):

```bash
python3 scripts/mine_transcripts.py --engine all --limit 30 --output ~/.config/simulate-user/my_mined_seeds.json
```

---

## How it works

### Core mechanics

1. **Isolated external critic:** Never let the agent that wrote the code or designed the layout grade its own work. The simulation runs in a tool-disabled fork or isolated subagent with ~99% prompt cache hits.
2. **Two-level design and UI/UX critique:**
   - **Routine polish (Automated):** Consolidate split action buttons, eliminate dead controls after state changes, cut redundant confirmation prompts, fix cramped mobile spacing (375px/320px) and dark mode contrast, and enforce paying-customer fairness.
   - **High-level taste choices (`needs_real_user`):** When overall visual direction is open, the agent prepares 2–3 distinct options (A/B/C at desktop and mobile widths) and halts for your selection rather than guessing.
3. **Codex-style abstention (`status: "abstain"`):** Prevents nagging busywork. When the candidate is solid and verified, the simulator returns `status: "abstain"` (`prediction: null`) and allows the turn to complete cleanly.
4. **Hard safety boundaries (`status: "needs_real_user"`):** Halts immediately on outbound messages (email/SMS/posts), payments/billing, physical actuation, destructive data deletion, or public releases.
5. **Passive calibration:** Logs `hit`, `edited`, or `overridden` outcomes to track simulator precision over time.

---

## Operating modes & CLI

### Mode 1: QA fast-path (`qa_loop`)

Assemble a cache-stable prompt to evaluate candidate code or diffs:

```bash
python3 scripts/build_prompt.py build --mode qa_loop --context-file candidate_diff.txt
```

Validate critic JSON output:

```bash
python3 scripts/build_prompt.py validate --input-file critic_output.json
```

Expected schema:
```json
{
  "mode": "qa_loop",
  "status": "abstain" | "pushback" | "needs_real_user",
  "prediction": "the cancel button is hidden on 375px mobile screens" | null,
  "instinct_category": "untested_ui" | "ui_design_critique" | "regression_risk" | null,
  "severity": "blocker" | "niggle" | null,
  "suggested_verification_action": "node tests/mobile.cjs http://localhost:4173",
  "reasoning": "Mobile viewport clips secondary action bar."
}
```

### Mode 2: General simulation (`general`)

Predict next prompt, steer workflow decisions, or critique design proposals:

```bash
python3 scripts/build_prompt.py build --mode general --context-file proposed_plan.md
```

---

## Calibration & Stats

Record real outcomes to learn from prediction misses:

```bash
# Record an outcome
python3 scripts/calibrate.py record \
  --mode qa_loop \
  --category untested_ui \
  --predicted "cancel button broken" \
  --actual "the cancel button doesn't work during export" \
  --outcome hit

# View accuracy stats
python3 scripts/calibrate.py stats
```

---

## Running tests

The test suite has zero external dependencies:

```bash
python3 -B -m unittest discover -s tests
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
