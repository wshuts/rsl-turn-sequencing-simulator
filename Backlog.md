# RSL Turn Sequencing Simulator — Backlog

This backlog tracks **engine correctness first**, followed by **observability**, then **player-aligned reporting**.
Only one item should ever be marked **ACTIVE NEXT STEP** at a time.

---

## EPIC A — Core Timing & Effect Semantics (Engine Truth)

### A1. Duration-based Decrease SPD (Next-tick expiration)
- [ ] Represent Decrease SPD debuff with:
  - magnitude (e.g., 0.7)
  - remaining tick duration
- [ ] Decrement duration at a **single, consistent tick boundary**
- [ ] While active:
  - affects effective speed during tick fill
- [ ] On expiration or cleanse:
  - effective speed changes **starting next tick**
- [ ] Validation:
  - reproduces still-frame baseline where two champions
    are slowed for several ticks, then cleansed
- [ ] Tests assert:
  - tick-by-tick effective speed
  - correct expiration timing
  - no retroactive tick effects

**Acceptance Criteria**
- No ambiguity about when speed changes take effect
- Cleanse never alters an already-computed tick

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

---

## EPIC B — Formal Event / Trace Model (Observability Backbone)

### B1. Define and Emit Structured Events  **← ACTIVE NEXT STEP**
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

---

## EPIC C — Boss-Centric Reporting & Shield Observability

### C1. Boss-relative Frame Grouping
- [ ] Implement reporting layer that groups events into
  **Boss Turn Frames**
- [ ] Frames labeled relative to boss actions:
  - “Boss Turn #N”
- [ ] Decoupled from absolute tick / turn counters

**Acceptance Criteria**
- Output aligns with player mental model
- Boss becomes the primary temporal anchor

---

### C2. Shield Start-of-Turn / End-of-Turn State in Trace
- [ ] Engine-level representation of shield state
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
- [ ] Derive Turn Rows from trace events:
  - TURN_START → TURN_END
- [ ] Capture boss shield value:
  - PRE  = at row start
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

---

## Sequencing Rules
1. EPIC B unblocks EPIC C
2. EPIC A correctness precedes UI/reporting
3. Only **one ACTIVE NEXT STEP** at any time
4. Tests gate every item

---

## Parking Lot (Not Active)
- Skill pinning by Boss Frame
- Cooldown reservation / hold semantics
- Sidebar & visualization UX
- Policy-layer AI decisions

