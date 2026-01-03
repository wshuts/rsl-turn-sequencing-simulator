# RSL Turn Sequencing Simulator — Backlog

This backlog tracks **engine correctness first**, followed by **observability**, then **player-aligned reporting**.
All reporting is strictly observational and derived from the ordered event stream.
Only one item should ever be marked **ACTIVE NEXT STEP** at a time.

---

## EPIC A — Core Timing & Effect Semantics (Engine Truth) ✅ COMPLETE

> Epic A establishes **engine truth** for turn ordering, effect triggering,
> duration decrement, expiration semantics, and extra turns.
> All timing boundaries are now explicit, test-locked, and intentional.

### A1. Duration-based Decrease SPD (TURN_END expiration)

- [x] Represent Decrease SPD debuff with:
    - magnitude (e.g., 0.7)
    - remaining **turn** duration
- [x] Decrement duration at a **single, consistent event boundary**:
    - `TURN_END` of the affected actor
- [x] While active:
    - affects effective speed during turn meter fill
- [ ] On cleanse:
    - effective speed changes starting **next fill cycle** *(explicitly out of scope for A1)*
- [x] Validation:
    - tests prove Decrease SPD applies and expires correctly
      relative to TURN_END
- [x] Tests assert:
    - effective speed while active
    - correct expiration timing
    - no retroactive effect on completed turns

**Acceptance Criteria**

- Effect lifetime is governed by turn events, not ticks
- Battle clock is responsible only for turn ordering
- No ambiguity about when Decrease SPD expires
  **Status:** ✅ DONE

---

### A2. TURN_START–Triggered Effects (Poison as Canonical)

- [ ] Introduce triggerable effect type:
    - triggers at TURN_START
    - applies its effect (e.g., damage)
    - decrements duration at the same boundary
- [ ] Implement **Poison** as the only effect
- [ ] Tests prove:
    - trigger fires exactly at TURN_START
    - duration decrements correctly
    - effect works during extra turns (no fill)
- [ ] Explicitly out of scope:
    - UI
    - cleanse handling
    - multiple effect types

**Acceptance Criteria**

- TURN_START is a first-class timing boundary
- Extra turns do not advance tick-based durations
  **Status:** ✅ DONE

---

## EPIC B — Formal Event / Trace Model (Observability Backbone) ✅ COMPLETE

### B1. Define and Emit Structured Events

- [ ] Replace ad-hoc prints with structured event objects
- [ ] Event types include (minimum):
    - TICK_ADVANCE
    - TURN_GRANTED
    - TURN_START
    - EFFECT_TRIGGERED
    - ACTION_RESOLVED
    - BUFF_EXPIRED / DEBUFF_EXPIRED
    - TURN_END
- [ ] Events are:
    - ordered
    - replayable
    - deterministic
- [ ] Tests assert:
    - event order
    - event payload correctness
    - absence of side-channel prints

**Acceptance Criteria**

- Simulator output can be fully reconstructed from events
- Tests validate behavior without relying on visuals or logs

**Status:** ✅ DONE

---

## EPIC C — Boss-Centric Reporting & Shield Observability ✅ COMPLETE

### C1. Boss-relative Frame Grouping

- [x] Implement reporting layer that groups events into
  **Boss Turn Frames**
- [ ] Frames labeled relative to boss actions:
    - “Boss Turn #N”
- [ ] Decoupled from absolute tick / turn counters

**Acceptance Criteria**

- Output aligns with player mental model
- Boss becomes the primary temporal anchor

---

### C2. Shield Start-of-Turn / End-of-Turn State in Trace

- [x] Engine-level representation of shield state
- [ ] Trace expresses transitions:
    - Shield: UP → BROKEN (or equivalent)
- [ ] Shield state captured at:
    - turn start
    - turn end
- [ ] No UI polish yet

**Acceptance Criteria**

- Shield behavior is inspectable without screenshots
- Provides foundation for later UI + skill logic

---

### C3. Boss Turn Frames with PRE/POST Shield Indicators

- [x] Derive Turn Rows from trace events:
    - TURN_START → TURN_END
- [ ] Capture boss shield value:
    - PRE = at row start
    - POST = at row resolution
- [ ] Group rows into Boss Turn Frames where:
    - boss row is last
    - frame closes just before next tick fill
- [ ] Render trace rows as:
    - `[PRE] Actor  Skill  [POST]`

**Acceptance Criteria**

- Matches demonstrated UI mental model
- Shield changes are visible before and after every action
- Reporting layer only (engine already correct)

**Status:** ✅ COMPLETE

---

**ACTIVE NEXT STEP:** _None — Epic C complete_

---

## EPIC D — User Harness & CLI (Executable Module) ✅ COMPLETE

> Epic D establishes a **clear, user-facing entrypoint** so the system can be
> evaluated through real usage. This EPIC introduces **no new engine logic**
> and does not modify event semantics or reporting rules.

### D1. Executable Module with Clear Command-Line Interface

- [x] Provide a canonical executable entrypoint:
    - `python -m rsl_turn_sequencing ...`
    - *(optional later)* installed console command via project metadata
- [x] CLI provides discoverability via `--help` and a runnable v0 demo mode
- [x] CLI must clearly document:
    - expected input (demo or structured event stream)
    - generated output
    - supported options
- [x] Avoid a proliferation of ad-hoc scripts as the primary interface

**Acceptance Criteria**

- A fresh clone can be run via a single obvious command
- `--help` explains purpose and usage without reading source code
- CLI execution does not depend on tests or debug harnesses

**Status:** ✅ DONE

---

### D2. Input Contract — Structured Event Stream (v0)

- [ ] Define and document the accepted input format
    - ordered structured event stream (authoritative)
- [ ] Provide at least one sample input suitable for user evaluation
- [ ] Validate required fields and ordering at load time

**Acceptance Criteria**

- User can answer “What do I feed it?” unambiguously
- Input is treated as the single source of truth

---

### D3. Text-Based Report Output (Boss Turn Frames v0)

- [x] Render Boss Turn Frames as the primary reporting unit
- [x] Render Turn Rows:
    - exactly one per actor turn
    - `TURN_START → TURN_END`
- [x] Include boss shield snapshots:
    - PRE at `TURN_START`
    - POST at `TURN_END`

**Acceptance Criteria**

- User can read the output and reconstruct what happened
- Shield state never requires inference from damage numbers

**Status:** ✅ DONE (v0 text report)

---

### D4. README — User Onboarding (v0)  **← ACTIVE NEXT STEP**

- [ ] Describe what the tool does and does not do
- [ ] Provide Quick Start instructions for the CLI
- [ ] Explain how to interpret the output at a high level

**Acceptance Criteria**

- A new user can run the tool in under two minutes
- First friction points are about report usefulness, not setup

---

## WORKFLOW — Patch Protocol (Non-blocking)

- Fresh ZIP uploads are the canonical baseline when collaborating via patches.
- Normalize line endings via `.gitattributes` to prevent CRLF/LF-driven hunk mismatch.
- Keep patches **single-purpose** (one intent per patch).
- Reject **no-op diffs** (lines where `-` and `+` are identical) because they create fragile hunks and can lead to partial application / dropped lines.

---

## Sequencing Rules

1. EPIC B unblocks EPIC C
2. EPIC A correctness precedes UI/reporting
3. Only **one ACTIVE NEXT STEP** at any time
4. Tests gate every item

---

## Checkpoint — JIT User Input & Mythical Metamorph Modeling

This checkpoint captures **input-contract and modeling decisions** discovered
while evaluating real user tools (HellHades, DeadwoodJedi) against the simulator’s
current engine capabilities.

### DECISIONS LOCKED

- **Minimum viable user input (current stage)**:
  - Boss: **name + speed**
  - Team: **one actor per champion + speed**
- **Speed-only input** is sufficient to generate meaningful turn-sequencing output.
- **Mythical champions** are modeled as **a single actor with multiple forms**,
  not as duplicated actors.
- **Metamorph is an active skill**, not a passive toggle:
  - Selected on the actor’s turn
  - Consumes the turn like any other active skill
  - Governed by cooldown measured in **actor turns**
- **Cooldowns decrement at TURN_END** of the actor’s turns.
- **Form changes (including speed swaps)** take effect starting the
  **next tick after the turn**, consistent with existing boundary semantics.
- External tools may represent mythicals as multiple entries for UX convenience,
  but the engine model remains **one actor + form state**.

### ACTIVE NEXT STEP (ONE ONLY)

- **Formalize the minimal user input schema**:
  - Boss: `name`, `speed`
  - Actor: `name`, `speed`
  - Optional extension for form-capable actors:
    - `form_start`
    - `speed_by_form`
    - `metamorph` as an active skill entry with `cooldown_turns`

### PARKING LOT (NOT ACTIVE)

- Full active-skill selection engine (priority resolution / rotation logic)
- Skill delays at battle start
- Separate cooldown tables per form
- Cooldown reset vs persistence rules across form swap
- UI duplication of forms (DeadwoodJedi-style convenience)
- Damage, debuff, shield, ACC/RES modeling
- Interactive or conditional skill choice

### OPEN QUESTIONS (OPTIONAL)

- When metamorph is used, do **non-metamorph cooldowns persist unchanged**?
- Do form-specific skills share cooldown lineage or behave independently?
- Are there real RSL cases that require **immediate speed-change semantics**
  instead of “next tick” application?

---

## Parking Lot (Not Active)

- Skill pinning by Boss Frame
- Cooldown reservation / hold semantics
- Sidebar & visualization UX
- Policy-layer AI decisions

