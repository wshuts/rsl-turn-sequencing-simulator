# Mini‑Epic: Engine‑Owned BUFF Expiration + User‑Declared Mastery Procs (Rapid Response Bridge)

## Purpose
We want **Rapid Response** to remain gated by real engine causality:

> **(Engine)** A **BUFF placed by Mikage expires**  
> **AND**  
> **(User)** A **mastery proc request exists** for that step  
> **→ Emit `MASTERY_PROC`** and apply Rapid Response effect deterministically.

This preserves the domain truth:
- **Mastery procs are nondeterministic** in real life → user must be able to declare them.
- **BUFF placement/expiration is deterministic** → engine must own it.
- No user-facing “expiration override” input is required (nor desired) for the product surface.

## Current State (Baseline)
- The engine contains logic that consults `mastery_proc_requester` only inside an expiration path:
  - “If a BUFF placed by Mikage expires AND a deterministic proc request exists for this step, emit `MASTERY_PROC`.”
- In the current project state, a Mikage-placed BUFF expiration is not reliably reachable via a normal CLI run (it is reachable via developer/test seams or handcrafted state).
- Result: Rapid Response can be proven in slice tests, but not promoted cleanly to CLI integration/acceptance testing yet.

## Target State (Definition of Done)
1. The engine can **place** at least one Mikage BUFF with a duration.
2. The engine **decrements duration** on a defined boundary and **expires** that BUFF deterministically.
3. On expiration, the engine emits `EFFECT_EXPIRED` (or equivalent) and consults `mastery_proc_requester` for step-based proc requests.
4. When the user declares a Rapid Response proc for that step, the engine emits `MASTERY_PROC` and the effect plane applies the Rapid Response turn meter increase:
   - `ΔTM = TM_GATE * 0.10 * count` (for Mikage rapid_response procs)

## Non‑Goals
- Full buff/debuff system across all champions.
- Complex targeting, stacking, refresh rules, or interaction rules.
- User-provided expiration controls.
- Broad mastery framework beyond Rapid Response consumption.

---

# Slice Breakdown (TDD: RED → GREEN → REFACTOR)

## Slice 1 — BUFF Data Model Exists and Is Serializable in Events
**One sentence**: Introduce a minimal BUFF representation on `Actor` with `EffectInstance` fields required for expiration and event emission.

### Scope
- `Actor.active_effects: list[EffectInstance]` exists.
- `EffectInstance` includes (minimum):
  - `instance_id: str`
  - `effect_kind: Literal["BUFF"]`
  - `effect_id: str`
  - `owner: str` (actor id/name)
  - `placed_by: str` (e.g., "Mikage")
  - `duration_turns: int`

### Test(s)
- Unit test asserts:
  - Creating an actor with an active BUFF instance is possible.
  - Event payload for “effect applied”/“effect expired” can include these fields without breaking event sink / formatting.

### Notes
- No placement or expiration behavior yet; this is purely “state exists and is safe to carry.”

---

## Slice 2 — Engine Places a Single Mikage BUFF in a Deterministic Way
**One sentence**: When a specific Mikage skill resolves, the engine places exactly one BUFF with a known duration onto a known target (self is acceptable).

### Scope
- Choose one Mikage skill already in your sim flow (or add the smallest hook) that triggers BUFF placement.
- Placement rules (minimal):
  - BUFF is added to target’s `active_effects` with `duration_turns = 1` (or 2 if you prefer).
  - Emit `EFFECT_APPLIED` (or equivalent) with the BUFF’s identity + duration.

### Test(s)
- Engine slice test (not CLI) that runs a single step where Mikage uses that skill and asserts:
  - One BUFF instance is present with expected fields.
  - `EFFECT_APPLIED` event is emitted with expected payload.

### Notes
- Keep it Mikage-only to avoid widening scope.

---

## Slice 3 — Engine Decrements BUFF Duration at a Single Boundary
**One sentence**: Decrement `duration_turns` for BUFFs at a clearly-defined boundary (recommend: BUFF owner’s `TURN_END`).

### Scope
- At the chosen boundary:
  - `duration_turns -= 1` for BUFFs on the relevant actor.
- Do not expire yet; just decrement.

### Test(s)
- Slice test runs two turns/steps (or one full boundary cycle) and asserts:
  - Duration decreased as expected.
  - No expiration event emitted yet (if duration was > 1), or duration reaches 0 (if duration was 1).

---

## Slice 4 — Engine Expires BUFFs and Emits `EFFECT_EXPIRED`
**One sentence**: When BUFF `duration_turns` reaches 0, remove it and emit `EFFECT_EXPIRED` with `placed_by` intact.

### Scope
- On boundary handling:
  - If duration hits 0 → remove instance and emit expiration event.
- No mastery proc behavior required yet.

### Test(s)
- Slice test asserts:
  - BUFF is removed from actor state.
  - `EFFECT_EXPIRED` is emitted with instance_id / placed_by / owner / effect_id.

---

## Slice 5 — Expiration + User Proc Request Emits `MASTERY_PROC`
**One sentence**: When a Mikage-placed BUFF expires and the user provides a matching proc request for that step, emit `MASTERY_PROC` with the requested payload.

### Scope
- Use existing `_maybe_emit_mastery_proc_for_expiration(...)` path.
- Gating rules:
  - `effect_kind == "BUFF"`
  - `placed_by == "Mikage"`
- Emit `MASTERY_PROC` only when proc request exists for current step.

### Test(s)
- Slice test arranges:
  - Mikage places BUFF with duration 1.
  - `mastery_proc_requester` returns a proc request for the expiration step.
- Asserts:
  - `MASTERY_PROC` is emitted with correct holder/mastery/count.
  - Ordering around expiration matches your established event ordering contract (if locked).

---

## Slice 6 — Rapid Response Effect Plane Applies Deterministic TM Increase
**One sentence**: Consume `MASTERY_PROC` for Mikage rapid_response and increase Mikage `turn_meter` by `TM_GATE * 0.10 * count`.

### Scope
- Locate where `MASTERY_PROC` events are consumed.
- Implement Rapid Response effect in that consumption site.

### Test(s)
- Existing `tests/test_rapid_response_effect_plane.py` goes GREEN.
- Include a unit test that verifies non-matching procs do nothing.

---

# Promotion to CLI Integration Testing

## CLI Integration Test 1 — Wiring + Causality
**Goal**: Prove user input can declare proc requests, and the engine can naturally expire a Mikage BUFF to trigger the AND condition.

### Evidence to assert
- The run reaches a step where:
  - Mikage places a BUFF
  - The BUFF expires later
  - The user declared a proc request at that expiration step
- Prefer an event dump (`MASTERY_PROC`, `EFFECT_EXPIRED`) rather than fragile frame text matching.
- If event dump doesn’t exist, add the smallest stable diagnostic output for tests.

## CLI Integration Test 2 — Effect Visible
**Goal**: Prove Rapid Response changes turn meter and impacts subsequent turn order (or is visible in a trace).

---

# Open Questions (to Lock Before Implementation)
1. **Duration semantics**: Does “1 turn” mean expire at end of the same turn, or after the next owner turn end?
2. **Boundary**: Which boundary decrements BUFF duration? (Recommended: BUFF owner’s `TURN_END` for first pass.)
3. **Event names**: Confirm canonical names (`EFFECT_APPLIED`, `EFFECT_EXPIRED`, `MASTERY_PROC`) used in the repo.
4. **Proc request semantics**: Does `count` represent multiple independent procs in one step, or a multiplier for one effect application? (Rapid Response math suggests multiplier.)

---

# Deliverables
- Slice tests (unit/slice level) for BUFF state, placement, decrement, expiration, proc emission gating, and Rapid Response effect.
- Only after slices are GREEN: add CLI integration tests driven by a battle spec fixture.
