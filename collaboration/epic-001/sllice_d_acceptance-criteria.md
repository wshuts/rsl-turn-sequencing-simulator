# Slice D — Acceptance Criteria  
**Epic:** Guarded Deterministic Mastery Proc Resolution on Effect Expiration  
**Slice:** D  
**Status:** Locked (field names finalized)  
**Depends On:** Slice C (Closed)

---

## Locked Assumptions (Non-Negotiable)

Slice D **inherits** the following Slice C guarantees and MUST NOT alter them:

1. Mastery procs are resolved **only after qualifying effect expirations**.
2. Resolution is **guarded**: requested proc count MUST equal qualifying expiration count.
3. Multiple qualifying expirations in the same resolution window resolve into:
   - **One aggregated `MASTERY_PROC` event**
   - With a **`count` field**
4. Event ordering within a turn/tick is locked:
   1. `EFFECT_EXPIRED`
   2. `MASTERY_PROC` (or `MASTERY_PROC_REJECTED`)
   3. `TURN_END`

Slice D acceptance criteria may **observe**, **annotate**, or **validate** this behavior — but MUST NOT redefine it.

---

## Slice D Goal

Improve **observability, traceability, and diagnostic clarity** of mastery proc resolution **without changing functional behavior**.

---

## Acceptance Criteria

### D1 — Aggregated Proc Transparency

**Given**
- A mastery proc request with `count = N`
- Exactly `N` qualifying effect expirations occur in the same resolution window

**When**
- Mastery proc resolution is performed

**Then**
- Exactly **one** `MASTERY_PROC` event is emitted
- The event includes:
  - `holder`
  - `mastery`
  - `count = N`
- No additional mastery proc events are emitted for this resolution window

**And**
- Effect-plane application reflects the aggregated count (e.g., TM increased by `N × value`)

---

### D2 — Explicit Causal Attribution (Diagnostic)

**Given**
- A mastery proc resolves successfully with `count = N`

**Then**
- The emitted `MASTERY_PROC` event includes **causal metadata** sufficient to explain *why* `count = N`

**Minimum required diagnostic fields (exact naming locked):**
- `qualifying_expiration_count`
- `resolution_phase` = `"EventType.TURN_END"` (exact string)
- `resolution_step` (derived from skill/turn cursor)

**Notes**
- Individual expiration instance IDs MAY be included but are **not required**
- This metadata is **non-functional** and does not affect gameplay logic

---

### D3 — Rejection Diagnostics Are Explicit and Non-Ambiguous

**Given**
- A mastery proc request with `count = N`
- The number of qualifying expirations is `M ≠ N`

**When**
- Mastery proc resolution is attempted

**Then**
- Exactly one `MASTERY_PROC_REJECTED` event is emitted
- The event MUST include:
  - `requested_count = N`
  - `qualifying_expiration_count = M`
  - `mastery`
  - `holder`

**And**
- No `MASTERY_PROC` event is emitted
- Turn execution continues normally

---

### D4 — No Silent Failure Modes

**Given**
- A mastery proc request exists for a turn

**Then**
- Resolution MUST result in exactly one of:
  - `MASTERY_PROC`
  - `MASTERY_PROC_REJECTED`

**Forbidden**
- Silent drops
- Implicit resolution
- Debug-only logging without an emitted event

---

### D5 — Ordering Contract Is Preserved (Regression Guard)

**Given**
- Any mastery proc resolution (success or rejection)

**Then**
- Event ordering within the turn/tick MUST remain:

1. All `EFFECT_EXPIRED`
2. One of:
   - `MASTERY_PROC`
   - `MASTERY_PROC_REJECTED`
3. `TURN_END`

This criterion exists to prevent regressions during Slice D instrumentation.

---

### D6 — Multi-Mastery Isolation

**Given**
- Multiple mastery proc requests for different masteries and/or holders
- Each mastery has independent qualifying expirations

**Then**
- Each mastery is resolved independently
- Aggregation applies **per mastery, per holder**
- Diagnostic metadata correctly reflects each mastery’s own qualifying expirations

---

## Explicit Non-Goals (Slice D Will NOT)

- Change aggregation semantics
- Introduce per-proc event fan-out
- Alter effect-plane math
- Introduce UI concepts into engine logic
- Add new mastery types

---

## Slice D Completion Criteria

Slice D is considered **DONE** when:

- All acceptance criteria above are enforced by tests
- No Slice C tests are modified except to assert new diagnostic fields
- No functional gameplay behavior changes are observed
- Aggregated mastery proc semantics remain intact and provable

---
