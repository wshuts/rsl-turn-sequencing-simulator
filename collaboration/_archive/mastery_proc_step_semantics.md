# Mastery Proc Scheduling — Step Semantics & Engine Evidence

## Purpose

This document records the clarified semantics, empirical evidence, and architectural conclusions regarding **Mastery Proc scheduling** in the RSL Turn Sequencing Simulator.

The goal is to eliminate ambiguity around the term **“step”**, document how the engine currently behaves, and provide a stable foundation for refactoring the mastery proc requester and its consumption logic.

This document is authoritative for collaboration and future work.

---

## Working Agreement

- Development is **test-first**; production code may change to satisfy tests.
- **User-facing semantics are authoritative**; engine counters are implementation details.
- Ambiguous terms must be explicitly disambiguated and named.
- No battle spec schema redesign unless strictly required.

---

## Canonical Definitions

### User-Facing Concept

**`step` (battle spec)**  
A **1-based index of a specific champion’s skill activation sequence**.

Properties:
- Scoped **per champion**
- Increments **only when that champion uses a skill**
- Not global
- Not derivable by the user from engine internals
- This definition is the reason `turn_overrides` are nested under each champion in the battle spec

---

### Engine Concepts (Validated from `events_out.json`)

#### `tick`
- Global simulation heartbeat / loop iteration
- Shared across all actors
- Not user-facing

#### `seq`
- **1-based ordinal index of events emitted within a single tick**
- Resets to `1` at the start of every tick
- Maximum value varies per tick depending on how many events occur
- Exists solely to preserve deterministic ordering within a tick

**Empirically validated facts:**
- `seq` is always ≥ 1
- `seq` always resets at a new tick
- `seq` has no meaning across ticks
- `seq` is not a timeline and must not be used for scheduling

---

## Proven Invariants from Event Output

From inspection of `events_out.json`:

- Multiple events occur within a single tick (TURN_START, SKILL_CONSUMED, EFFECT_* events, etc.).
- `seq` increments once per emitted event within the tick.
- Ticks with more effects produce higher max `seq` values.
- There is **no explicit user-facing step or skill sequence index** in the current event output.
- `turn_counter` appears in some effect events and corresponds to a **global turn count**, not a per-champion skill index.

---

## Critical Observation (Root Cause Indicator)

When examining the mastery proc requester builder in the current baseline:

- Two proc requests appeared under the same numeric `step` (e.g., step 6),
  - one for **Mikage**
  - one for **Mithrala**

However, in real gameplay:
- Mikage’s 6th skill activation and Mithrala’s 6th skill activation occur at **different ticks, turns, and game states**.

**Conclusion:**  
A global `step → list[requests]` structure is semantically invalid if `step` is defined as a per-champion skill sequence index.

---

## Architectural Implications

### Why Champion-Scoped Data Is Required

Because user-facing `step` is per champion:

- `on_step` data **must** be nested under each champion
- Two champions may legitimately both have `on_step[6]` with no temporal relationship
- Grouping requests by global step destroys meaning and causes lookup failures

This nesting is not cosmetic — it is semantically required.

---

## Required Translation Layer

The engine **must translate runtime state** into the user’s coordinate system.

### Translation Contract

At runtime, the engine always knows:
- which champion is acting
- when that champion consumes a skill

Therefore the engine can compute:

(champion_name, skill_sequence_step)

This pair is the **only valid lookup key** for mastery proc requests.

---

## Recommended Internal Schedule Shape

Internally (engine-facing), the requester should be structured as:

schedule[champion_name][skill_sequence_step] -> list[MasteryProcRequest]

Consumption API should resemble:

consume(champion_name, skill_sequence_step)

Not:
- consume(step)
- consume(turn_counter)
- consume(tick)
- consume(seq)

---

## Observability Requirements

To make scheduling authorable and debuggable:

- Events related to scheduling (at minimum `SKILL_CONSUMED` and `MASTERY_PROC`) should expose:
  - champion
  - skill_sequence_step (1-based, user-facing)

Engine internals (`tick`, `seq`, `turn_counter`) may remain for debugging but are **not part of the user contract**.

---

## Summary of Key Conclusions

- `seq` is a per-tick ordering index and nothing more.
- `tick` is an engine heartbeat, not a user coordinate.
- User-facing `step` is a **per-champion, 1-based skill activation index**.
- Grouping proc requests by global step is incorrect.
- A translator from engine runtime → `(champion, skill_sequence_step)` is required.
- The current absence of `MASTERY_PROC` events in CLI runs is consistent with this mismatch.

---

## Next Actions (Agreed Direction)

1. Refactor mastery proc requester builder to be **champion-scoped**.
2. Change engine lookup to use `(champion, skill_sequence_step)`.
3. Expose `skill_sequence_step` in relevant events.
4. Update CLI integration tests to assert against this contract.

---

## Status

This document captures **validated evidence and agreed semantics**  
and should be treated as a stable reference going forward.
