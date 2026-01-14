# EPIC: Guarded, Deterministic Mastery Proc Resolution on Effect Expiration

## Epic Intent

Introduce **engine-side validation and sequencing guarantees** for deterministic mastery proc requests (e.g., *Rapid Response*), such that:

- User-provided proc requests remain **deterministic inputs**
- The engine remains the **authority on causality**
- Mastery procs are emitted **only** when real, qualifying effect expirations occur
- Event ordering emitted to the event sink is **explicitly enforced and testable**

This Epic closes the gap between *control-plane determinism* and *rules-plane correctness*.

---

## Problem Statement

Currently, the engine accepts deterministic mastery proc requests (holder, mastery, count, step) to bypass probabilistic RNG. This mechanism works well for reproducibility.

However, without engine-side guarding:
- Proc requests could be honored without a corresponding qualifying event
- The engine cannot enforce correctness of ownership (placer vs recipient)
- Event ordering (expiration → proc → turn end) is not contractually enforced

This Epic establishes the engine as the **gatekeeper of proc validity and sequencing**.

---

## Core Requirements (Epic-Level)

1. **Causality Guarding**
   - Mastery procs requested by the user MUST only be emitted when real qualifying effect expirations occur.

2. **Ownership Validation**
   - The engine MUST validate:
     - who placed the effect
     - who owned the effect
     - the effect kind (BUFF vs DEBUFF)
     - that the mastery holder matches the placer

3. **Count Validation**
   - The number of requested mastery procs MUST match the number of qualifying expirations (strict mode).

4. **Event Ordering Enforcement**
   - The engine MUST emit events in a deterministic, enforced order:
     1. EFFECT_EXPIRED
     2. MASTERY_PROC (caused by expiration)
     3. TURN_END (or equivalent tick/turn boundary)

5. **Deterministic Failure Surface**
   - Invalid proc requests MUST fail deterministically (error or explicit rejection signal).

---

## Slice Breakdown

---

## SLICE 1 — Effect Expiration Attribution

### Goal
Ensure the engine can **attribute each expired effect instance** with sufficient metadata for later validation.

### Requirements
- Each effect instance MUST carry:
  - `instance_id`
  - `owner` (entity that had the effect)
  - `placed_by` (entity that applied the effect)
  - `effect_kind` (BUFF / DEBUFF)
- On expiration, the engine MUST emit:
  - `EFFECT_EXPIRED` with full attribution payload

### Definition of Done
- Effect expiration events are emitted with complete, inspectable ownership metadata.
- No mastery logic is introduced yet.

---

## SLICE 2 — Qualifying Expiration Detection (Rules Plane)

### Goal
Teach the engine to **identify qualifying expirations** for Rapid Response without emitting procs.

### Requirements
- During the expiration phase of a step:
  - The engine MUST collect qualifying expirations where:
    - effect_kind == BUFF
    - placed_by == mastery holder
- Qualifying expirations MUST be counted and scoped to the current step.

### Definition of Done
- The engine can deterministically compute:
  - “How many Rapid Response–qualifying expirations occurred in this step?”
- No proc requests are consumed yet.

---

## SLICE 3 — Proc Request Gating & Validation (Control Plane Guard)

### Goal
Bind deterministic proc requests to **real qualifying expirations**.

### Requirements
For each proc request `(holder, mastery, count, step)`:

- Let `Q` = number of qualifying expirations detected for that holder in the step.
- The engine MUST enforce:
  - `count == Q` (strict mode)
- If validation fails:
  - The engine MUST NOT emit any `MASTERY_PROC`
  - The engine MUST fail deterministically (exception or rejection event)

### Definition of Done
- Proc requests are consumed only when validated.
- Invalid requests are rejected deterministically.
- No event ordering changes yet.

---

## SLICE 4 — Mastery Proc Emission (Post-Expiration)

### Goal
Emit mastery proc events **as a consequence of expiration**, not as free-standing actions.

### Requirements
- When validation passes:
  - Emit exactly `count` `MASTERY_PROC` events
  - Each proc MUST be causally linked to expiration (same step context)
- Mastery proc emission MUST occur **after all expirations are processed**.

### Definition of Done
- Proc emission is causally correct and count-accurate.
- No proc can appear before its triggering expiration.

---

## SLICE 5 — Event Sequence Enforcement & Testing

### Goal
Make event ordering a **first-class, test-enforced contract**.

### Required Event Order (within a single step / turn)

1. `EFFECT_EXPIRED`
2. `MASTERY_PROC` (triggered by expiration)
3. `TURN_END` (or final tick/turn boundary event)

### Requirements
- Sequence numbers MUST be strictly increasing.
- `MASTERY_PROC` MUST NOT appear:
  - before any qualifying `EFFECT_EXPIRED`
  - after the turn/tick end boundary
- Tests MUST assert ordering, not just presence.

### Definition of Done
- At least one acceptance test asserts:
  - correct ordering of EFFECT_EXPIRED → MASTERY_PROC → TURN_END
- Misordering causes deterministic test failure.

---

## Non-Goals (Explicit)

- No probabilistic RNG modeling
- No Monte Carlo simulation
- No support for non-expiration-triggered masteries in this Epic
- No UI/log formatting changes

---

## Outcome

After this Epic:
- Deterministic mastery proc requests are **safe, guarded, and correct**
- The engine—not the user—owns causality
- Event sequencing becomes a **stable contract**, not an emergent side-effect
- Expiration-driven masteries (starting with Rapid Response) are fully modelable, testable, and debuggable

---
