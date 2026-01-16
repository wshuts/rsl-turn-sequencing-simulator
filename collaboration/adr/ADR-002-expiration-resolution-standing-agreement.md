# ADR: Expiration Resolution – Standing Agreement

## Status

**Accepted**

## Context

The engine models effects whose expiration semantics differ by timing. Some effects (e.g., poison-style damage-over-time) resolve at the **beginning of a turn**, while others (e.g., debuff duration loss such as Decrease Speed) resolve at the **end of a turn**.

During Slice C of the *Guarded, Deterministic Mastery Proc Resolution on Effect Expiration* epic, it became clear that supporting this domain truth requires a precise and shared contract between production code and tests. In particular, dependency injection (DI) must preserve **identical semantics** across environments while allowing deterministic control during testing.

This document records the resolved design so that future slices do not reopen or accidentally drift from it.

---

## Confirmed State of the World

### Two-Phase Expiration Model (Intentional)

The engine supports **two explicit expiration phases**:

* **BEGIN_TURN**

  * Used for poison-style and similar effects
  * Occurs before the actor’s actions for the turn

* **END_TURN**

  * Used for debuff duration expiry (e.g., Decrease Speed)
  * Occurs after the actor’s actions for the turn

Both phases are first-class and intentional parts of the model.

---

### Dependency Injection (Restored and Tightened)

* A **single expiration resolver interface** is used by both production and test code
* The resolver is **phase-aware**
* The resolver has **identical semantics** in all environments

The engine remains authoritative; DI is used to control *resolution*, not to invent behavior.

---

### Naming Alignment

* Vocabulary now reflects intent
* “Resolve expirations” is used instead of “inject expirations”
* Names describe *what* happens (resolution) rather than *how* it is overridden (injection)

This aligns the codebase with the conceptual model and reduces ambiguity.

---

## Standing Agreement: Expiration Resolution

The following principles are locked for this epic and future work:

1. The engine resolves effect expirations via a **single, phase-aware expiration resolver dependency**.
2. The resolver is called **exactly once per expiration phase** (`BEGIN_TURN`, `END_TURN`).
3. The resolver may select which **existing effect instances** expire at that phase, but **must not invent state**.
4. Both production and test code use the **same resolver interface and semantics**.

These four statements fully define the expiration-resolution philosophy.

---

## Why This Matters for the Epic

### Slice C — Proc Gating & Validation

With the phase-aware model, the engine can now cleanly answer:

> Which expirations occurred, and in which phase?

This enables strict, deterministic validation of mastery proc requests.

---

### Slice D — Mastery Proc Emission

Proc timing can now be specified unambiguously, for example:

* Emit procs **after all END_TURN expirations**, or
* Emit procs **after both phases**

No hacks, no hidden assumptions.

---

### Slice E — Ordering Tests

Event ordering can be asserted:

* Within a single phase, or
* Across phases, if required

The ordering contract is now explicit and testable.

---

## Consequence

With this agreement recorded:

* The two-call expiration pattern is intentional and correct
* Dependency injection is properly scoped and authoritative
* Future slices can build on this foundation without conceptual rework
