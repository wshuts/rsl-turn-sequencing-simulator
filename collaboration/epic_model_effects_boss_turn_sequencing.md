# Epic: Model Effects that Impact BOSS Turn Sequencing

## Epic Intent

### Required Model Improvements

- Accurately track the **shield state of the boss** during each turn.
- Permit champions to **place debuffs on the boss** only when the boss shield is in the **open state**.
- Specifically **place a Decrease Speed debuff** on the boss and model its effects.

The acceptance criteria in this document validate these required model improvements.

---

## Driving Acceptance Observation (Black-Box)

### Scenario: Boss Turn #5 — Frame Turn Ordering

**Frame definition**

A **Boss Turn frame** is the ordered sequence of actions that:
- begins immediately after the boss completes its previous action, and
- terminates when the boss performs its next action.

The ordering of actions *within* this frame is the subject of this observation.

**Observed in-game behavior (Boss Turn #5 frame)**

After the following action resolves within the frame:

```
87: Mikage {B_A2}
```

the next actions observed within the same frame are:

```
88: Mithrala {A2}
89: Fire Knight {A1}
```

**Observed facts**
- The frame does not immediately terminate with a boss action after Mikage.
- At least one champion action occurs within the frame before the boss acts.
- The frame terminates when the boss performs `{A1}`.

This ordering is verified by gameplay screenshots and is treated as authoritative.

---

## Locked Acceptance Requirement

### Requirement: Boss Turn #5 Frame Ordering

**Given**
- Boss Turn #5 frame is in progress.
- The engine has just resolved Mikage’s `{B_A2}` within that frame.

**When**
- All slices of this Epic are implemented and passing.

**Then**
- The next emitted actions within the same frame must be:
  ```
  88: Mithrala {A2}
  89: Fire Knight {A1}
  ```

**Definition of Done**
- This acceptance test fails on current `main`.
- Passes when all Epic slices are complete.

---

## Why the Current Engine Fails This Requirement

The current engine does not yet model the effects required to produce the observed ordering:

- Boss shield state is not tracked.
- Debuff placement on the boss is not gated by shield state.
- Speed-altering debuffs on the boss are not modeled.

As a result, the boss acts earlier than observed in real gameplay.

---

## Epic Scope

### In Scope
- Boss shield state tracking.
- Debuff placement conditional on boss shield state.
- Modeling of Decrease Speed effects on the boss.
- Action ordering derived from modeled effects.

### Out of Scope
- Exact replication of in-game turn meter math.
- Champion-specific or boss-specific special cases.
- Any logic that forces a specific champion to act.

---

## Slice Breakdown

### Slice 1 — Boss Shield State Tracking

**Goal**
Track whether the boss shield is **open or closed** at all times.

**Responsibilities**
- Maintain shield state across turns.
- Use shield state as a gating condition for later mechanics.

---

### Slice 2 — Debuff Placement Gated by Shield State

**Goal**
Allow champions to place debuffs on the boss **only when the shield is open**.

**Responsibilities**
- Block debuff placement attempts while the shield is closed.
- Permit debuff placement when the shield is open.

---

### Slice 3 — Decrease Speed Debuff Modeling

**Goal**
Model the effects of a **Decrease Speed** debuff applied to the boss.

**Responsibilities**
- Apply Decrease Speed when placed.
- Track its duration.
- Reduce the boss’s effective speed while active.
- Allow speed reduction to influence action ordering.

---

### Slice 4 — Ordering Validation

**Goal**
Validate that modeled effects produce the observed ordering.

**Responsibilities**
- Ensure debuff placement precedes its effects.
- Ensure speed changes influence readiness before next action selection.
- Validate ordering via acceptance tests.

---

## Epic Completion Criteria

- Boss shield state is accurately tracked.
- Debuffs are only placed when the shield is open.
- Decrease Speed affects boss action timing.
- Boss Turn #5 frame ordering matches observed gameplay.
- Screenshot-derived observations can be encoded as black-box acceptance tests.
