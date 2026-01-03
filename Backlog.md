# RSL Turn Sequencing Simulator — Backlog

This backlog tracks **current and future work only**.  
Completed work is intentionally removed; Git history is the record.

**Rules**
1. Only **one ACTIVE NEXT STEP** at any time
2. Lettered sections (A, B, C, D…) define **work areas**
3. Numbered items (D1, D2, …) preserve **lineage and context**
4. Anything not actively worked belongs in **Parking Lot**
5. Tests gate behavior changes whenever code is involved

---

## ACTIVE NEXT STEP (ONE ONLY)

**C1 — Boss Shield State Tracking (v0)**  
Track and report the boss’s shield count and open/closed state at well-defined turn boundaries.

---

## A — Engine Semantics (Locked)

> Core timing and sequencing rules of the engine.  
> This area is considered **stable** unless new mechanics require extension.

(No active items)

---

## B — Event & Trace Model (Locked)

> Structured, deterministic event stream used for observability and reporting.

(No active items)

---

## C — Reporting & Boss-Centric Views (Locked)

> Human-readable views derived strictly from the event stream.

### C1 — Boss Shield State Tracking (v0) ← ACTIVE

**Goal**  
Make the boss’s shield state observable and trustworthy.

**Scope (v0)**
- Track boss shield:
  - numeric value
  - open vs closed state
- Capture shield state:
  - at TURN_START (pre)
  - at TURN_END (post)
- Associate shield snapshots with each actor’s turn
- Ensure behavior matches in-game sequencing

**Constraints**
- Derived strictly from the event stream
- No damage formulas beyond shield increment/decrement
- No debuff, ACC/RES, or AI logic

---

## D — User Interaction & Input

> How a human runs the tool, provides input, and understands output.

### D1 — Executable Entry Point (CLI)
- Provide a canonical executable entry point (e.g. `python -m rsl_turn_sequencing`)
- `--help` must clearly explain:
  - what the tool does
  - expected inputs
  - produced outputs
- Avoid a proliferation of ad-hoc scripts as the primary interface

---

### D2 — Minimal User Input Schema (JIT Input) ← ACTIVE
### D2 — Minimal User Input Schema (JIT Input) ← COMPLETE

**Goal**  
Allow a user to describe a battle with minimal friction and still obtain meaningful sequencing output.

**Required (v0)**
- Boss:
  - `name`
  - `speed`
- Team actors:
  - `name`
  - `speed`

**Optional extension — Form-capable / Mythical champions**
- `form_start`
- `speed_by_form` (e.g. `{ alt: 280, base: 255 }`)
- `metamorph` modeled as an **active skill** with:
  - `cooldown_turns`

**Modeling decisions (locked)**
- Mythical champions are a **single actor with multiple forms**
- Metamorph is an **active skill**:
  - chosen on the actor’s turn
  - consumes the turn
  - cooldown measured in **actor turns**
- Cooldown semantics:
  - Cooldown is set to its **maximum value immediately when a skill is used**
  - Cooldowns **decrement at TURN_START** of the actor’s subsequent turns
  - Skill availability is evaluated **after TURN_START decrement and before action selection**
- Form changes take effect immediately during the turn in which Metamorph is used.
- Any granted extra turn uses the new form and skill set.
- Any speed changes will affect subsequent turn-meter fill.

---

### D3 — Text-Based Report Output (v0)
- Produce a readable, text-based report
- Output must be fully derivable from the event stream
- Focus on clarity over formatting polish

---

### D4 — README / User Onboarding (v0)
- Explain:
  - what the tool does and does not do
  - how to run it
  - how to provide minimal input
  - how to interpret the output

---

## Parking Lot (Not Active)

Items acknowledged but intentionally out of scope for current work:

- Skill priority / rotation AI
- Skill delays at battle start
- Cooldown reset vs persistence rules across form swap
- Separate cooldown tables per form
- Damage, debuff, shield, ACC/RES modeling
- Interactive or conditional skill choice
- UI / visualization layers
- Policy-layer AI decisions
