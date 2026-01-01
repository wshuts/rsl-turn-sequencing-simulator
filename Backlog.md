# RSL Turn Sequencing Simulator — Backlog

This backlog tracks **engine correctness first**, followed by **observability**, then **player-aligned reporting**.
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

**Status:** ▶️ ACTIVE NEXT STEP

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

