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

## A — Engine Semantics

> Core timing and sequencing rules of the engine.  
> This area is considered **stable** unless new mechanics require extension.

(No active items)

---

## B — Event & Trace Model

> Structured, deterministic event stream used for observability and reporting.

(No active items)

---

## C — Reporting & Boss-Centric Views

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
