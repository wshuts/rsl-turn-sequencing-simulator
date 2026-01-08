# Slice Request — TDD Collaboration Contract

## 1. Purpose

This document defines a **single slice of work** in the *RSL Turn Sequencing Simulator* using **strict test-driven development (TDD)**.

A *slice* is the smallest vertical unit of behavior that:

- Can be validated by a test  
- Can be delivered in one change  
- Leaves the system in a stable, shippable state  

Only the slice described in this document is in scope.

---

## 2. Standing Working Agreement

The following rules are mandatory:

1. **One baseline, one change, one delivery**
2. **TDD only**
   - Prove the test fails on the baseline  
   - Modify production code  
   - Prove the test now passes  
3. **No speculative implementation**
4. **Prefer complete file replacement**
   - If files are large, use **complete function replacement**
   - No Git-style diff hunks unless explicitly requested
5. **Tests must mirror existing reference tests**
   - Same Arrange / Act / Assert structure  
   - Same CLI or engine entry points
6. **Out-of-scope work is not permitted**
   - Even if it seems “obvious” or “easy”

---

## 3. Baseline

- Repository state: **clean**
- Tests: **48 passing, 1 failing**
- Relevant files (initial focus):
  - `rsl_turn_sequencing/engine.py`

No other assumptions should be made about the system.

---

## 4. Slice Definition

### Slice Name

**Slice 1 — Injectable Expiration Event Seam**

### Goal (Explicit)

Introduce a **minimal, injectable buff/debuff expiration event seam** that:

1. Allows a scripted **expiration event** to be injected at a specific step, tick, or turn boundary.
2. Makes the expiration event **observable** in simulation output (frame or state).
3. Enables deterministic testing of *“an expiration occurred here.”*

This slice exists solely to make **expiration events real and testable**.

---

## 5. Test Requirements

- Add **one new test** or minimally extend an existing test.
- The test must:
  - Inject an expiration event at a known step
  - Assert that the expiration is visible in the resulting frame or state
- Assertions must be minimal:
  - Presence
  - Correctness of actor and effect identity
- The test must:
  - Fail on the baseline
  - Pass after the change

---

## 6. Explicitly Out of Scope

The following are **not** to be implemented in this slice:

- Mastery proc logic
- Turn meter mutation
- Buff/debuff duration tracking
- Start-turn vs end-turn expiration rules
- Damage, shields, poisons, or stat changes

These will be addressed in later slices.

---

## 7. Forward Compatibility Constraint

The expiration event seam introduced here **must be reusable** later when:

- Real buff/debuff durations expire naturally
- Mastery effects trigger from expiration

The same event pathway should be usable **without refactoring tests written for this slice**.

---

## 8. Expected Delivery

- Required changes to `rsl_turn_sequencing` source files
- Delivered as:
  - Complete file replacement **or**
  - Complete function replacement

No partial artifacts.

---

## 9. Completion Criteria

This slice is complete when:

- All tests pass
- The new expiration event is visible and testable
- No unrelated behavior has changed
