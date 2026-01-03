# RSL Turn Sequencing Simulator — Backlog

This backlog tracks **engine correctness first**, followed by **observability**, then **player-aligned reporting**.
All reporting is strictly observational and derived from the ordered event stream.

**Rules**
1. Only **one ACTIVE NEXT STEP** at any time
2. Tests gate every behavior change (when code is involved)
3. The backlog is **not history** — completed items are removed (Git has the record)

---

## ACTIVE NEXT STEP (ONE ONLY)

### Formalize the Minimal User Input Schema (JIT input, v0)
Define and document the **minimum** user-provided input needed to drive the simulator *today*, plus an optional extension for Mythical champions.

**Deliverable (doc + example config)**
- Boss:
  - `name`
  - `speed`
- Team actors:
  - `name`
  - `speed`

**Optional extension (form-capable / Mythical)**
- `form_start`
- `speed_by_form` (e.g., `{ alt: 280, base: 255 }`)
- `metamorph` as an **active skill** entry with:
  - `cooldown_turns`

**Success criteria**
- A user can supply a tiny config (boss + 5 speeds) and get useful sequencing output.
- Mythical champions do **not** require duplicate actors in input; form support is additive and optional.

---

## EPIC D — User Harness & CLI (Executable Module)

> Goal: establish a clear, user-facing entrypoint so the system can be evaluated through real usage.
> This EPIC introduces **no new engine truth** and does not modify event semantics unless explicitly required.

### D1. Executable Entry Point (CLI)
- Provide a canonical executable entrypoint (example):
  - `python -m rsl_turn_sequencing ...`
- `--help` must explain:
  - expected input
  - what the tool outputs
  - supported options
- Avoid a proliferation of ad-hoc scripts as the primary interface

### D2. Input Contract — Structured Event Stream (v0)
- Define and document the accepted event-stream input format (if applicable)
- Validate input deterministically
- Provide at least one reference sample input file

### D3. Text Report Output (v0)
- Produce a readable text report that helps a human understand the sequencing
- Preserve observability-first: report is derived from events, not from hidden state

### D4. README — User Onboarding (v0)
- Describe:
  - what the tool does / does not do
  - how to run it
  - how to provide minimal input (links to the schema + sample)
  - how to interpret the output

---

## CHECKPOINT — JIT User Input & Mythical Metamorph Modeling

These are modeling decisions locked while comparing the simulator’s needs to real user tools (HellHades / DeadwoodJedi).

### DECISIONS LOCKED
- **Minimum viable user input (current stage)**:
  - Boss: **name + speed**
  - Team: **one actor per champion + speed**
- **Speed-only input** is sufficient to generate meaningful turn-sequencing output now.
- **Mythical champions are a single actor with multiple forms** (not duplicated actors).
- **Metamorph is an active skill**:
  - chosen on the actor’s turn
  - consumes the turn like any other active skill
  - cooldown measured in **actor turns**
- **Cooldowns decrement at TURN_END** of the actor’s turns.
- **Form changes (including speed swaps)** take effect starting the **next tick after the turn** (boundary-consistent semantics).
- External tools may represent mythicals as separate entries for UX convenience, but the engine model remains **one actor + form state**.

### OPEN QUESTIONS (Optional, parked until we implement skill selection)
- On metamorph, do **non-metamorph cooldowns persist unchanged**, or do any reset rules apply?
- Do form-specific skills share cooldown lineage or behave independently?
- Are there real RSL cases that require **immediate speed-change semantics** instead of “next tick”?

---

## Parking Lot (Not Active)

- Full active-skill selection engine (priority resolution / rotation logic)
- Skill delays at battle start
- Separate cooldown tables per form
- Cooldown reset vs persistence rules across form swap
- UI duplication of forms (DeadwoodJedi-style convenience)
- Damage, debuff, shield, ACC/RES modeling
- Interactive or conditional skill choice
- Sidebar & visualization UX
- Policy-layer AI decisions
