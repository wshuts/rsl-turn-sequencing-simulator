# Next Slice — Rapid Response (Proc Dynamics Only)

## Epic Context

The long-term epic goal is to bring the acceptance test  
`test_acceptance_mikage_is_first_actor_in_boss_turn_5` to passing.

This requires correctly modeling **Mikage’s Rapid Response mastery**, which accelerates her turn order via turn meter
gains.

Recent groundwork has established:

- Deterministic effect expiration via an injected expiration seam
- Support for extra turns with correct TURN_START / TURN_END boundaries
- Structured EFFECT_EXPIRED events that preserve `placed_by`
- A stable event sink model for observing (not creating) events

This foundation is now sufficient to begin testing Rapid Response.

---

## Slice (One Sentence)

When a **BUFF** placed by **Mikage** expires and a deterministic **Rapid Response** proc request exists for that step,
emit a **MASTERY_PROC** event with payload  
`{ holder: "Mikage", mastery: "rapid_response", count: 1 }`.

---

## Scope (Locked)

This slice focuses **only on proc dynamics**, not effects.

### In Scope

- Asserting that Rapid Response procs
- Asserting that the proc payload is correct

### Explicitly Out of Scope

- Turn meter modification
- Probability / RNG
- Actor ordering changes
- CLI parsing or integration

---

## What Will Be Tested

### When

- A **BUFF** effect placed by Mikage expires
- A deterministic proc request exists for Rapid Response

### Then

- A mastery proc event is emitted

---

## Assertions for This Slice

The test should assert:

- A mastery proc event exists (e.g., `MASTERY_PROC`)
- Event payload includes:
    - `holder == "Mikage"`
    - `mastery == "rapid_response"`
    - `count == 1`

### Optional (Non-blocking)

- The proc occurs in the correct turn boundary (TURN_START / TURN_END)
- The proc aligns temporally with the triggering EFFECT_EXPIRED event

---

## Determinism Strategy

Use user-shaped proc request data, injected **in-memory** (not via CLI), mirroring the future battle spec shape:

```json
{
  "turn_overrides": {
    "proc_request": {
      "on_step": {
        "4": {
          "mastery_procs": [
            {
              "holder": "Mikage",
              "mastery": "rapid_response",
              "count": 1
            }
          ]
        }
      }
    }
  }
}
```

This keeps the test future-aligned with CLI usage while avoiding integration complexity.

---

## Rationale

Separating **“did the mastery fire?”** from **“what did it do?”**:

- Keeps the slice small and deterministic
- Prevents conflating mastery correctness with numeric tuning
- Makes downstream failures easier to diagnose

This slice establishes the **control plane** for Rapid Response.  
The next slice will implement its **effect plane**.

<!-- END OF FILE -->
