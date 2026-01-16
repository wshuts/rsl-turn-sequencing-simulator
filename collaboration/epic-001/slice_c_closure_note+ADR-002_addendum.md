# Slice C Closure Note

**Epic:** Guarded Deterministic Mastery Proc Resolution on Effect Expiration  
**Slice:** C  
**Status:** ✅ **COMPLETE**  
**Date:** 2026-01-15

---

## Scope Recap

Slice C set out to:

- Enforce **guarded mastery proc resolution** tied to *actual qualifying effect expirations*
- Ensure **deterministic ordering** of expiration → mastery proc → turn end
- Align engine semantics with **observed in-game behavior**
- Remove ambiguous or legacy execution paths

All objectives have been met and validated.

---

## Final Behavioral Guarantees (Locked)

### 1. Guarded Resolution
- Mastery proc requests are honored **only** when the number of qualifying expirations exactly matches the requested proc count.
- Mismatches result in an explicit `MASTERY_PROC_REJECTED` event.

### 2. Phase-Aware Expiration Handling
- Effect expirations are resolved via an injected resolver at explicit engine phases (`TURN_START` / `TURN_END`), per ADR-002.
- Mastery proc resolution occurs **after all expirations** in the resolution window and **before `TURN_END`**.

### 3. Deterministic Event Ordering
Within a single turn/tick:

1. `EFFECT_EXPIRED` (all qualifying expirations)  
2. `MASTERY_PROC` (if guard conditions pass)  
3. `TURN_END`

This ordering is enforced by tests and treated as a standing contract.

### 4. Single Authoritative Proc Path
- All legacy or unused mastery-proc emission helpers have been removed.
- There is exactly **one** guarded resolution pathway in the engine.

---

## Aggregation Semantics — Canonical Decision

### Observation (Authoritative Evidence)

Direct in-game observation shows mastery procs aggregate:

> The UI displays **“Boost Turn Meter x2”** as a *single event* when two qualifying expirations occur in the same resolution window.

This is captured in gameplay footage (Turn Count ~81) and reflects live *Raid: Shadow Legends* behavior.

### Locked Engine Interpretation

**Multiple qualifying expirations within the same resolution window SHALL:**

- Resolve into **one aggregated mastery proc**
- Emit **a single `MASTERY_PROC` event**
- Carry a **multiplicity (`count`) field**
- Apply the effect **once**, scaled by `count`

### Explicit Non-Goals (Now Forbidden)

The engine **must not**:

- Emit multiple sequential mastery proc events for the same resolution window
- Attempt to simulate per-proc animation or sequencing
- Fan-out aggregated procs into individual effect applications

This behavior is now **canon**.

---

## ADR-002 Addendum

**Title:** Aggregated Mastery Proc Resolution Semantics  
**Status:** Accepted  
**Applies To:** All mastery procs driven by effect expiration

### Addendum Text

> When multiple mastery-proc-qualifying effect expirations occur within the same resolution window, the engine SHALL emit a single aggregated mastery proc event with a multiplicity count. This mirrors observed in-game behavior (e.g., “Boost Turn Meter x2”) and prevents artificial sequencing that does not exist in the source system.

---

## Outcome

Slice C is **closed**, **clean**, and **defensible**:

- Behavior matches live game evidence
- Tests enforce ordering and guard conditions
- Architecture is simplified and unambiguous
- Aggregation semantics are formally locked

**Slice D may proceed without revisiting Slice C assumptions.**
