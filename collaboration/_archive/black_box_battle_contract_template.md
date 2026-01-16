# Black-box Battle Contract: <scenario_name>
Date captured: <YYYY-MM-DD>
Evidence source: screen captures (single battle)
Purpose: derive acceptance requirements for engine event emission + state evolution

## 1. Scenario Inputs (what the user supplies)
### Battle Spec
- File: <path>
- Boss actor: <name>
- Champions: <list>
- Stop conditions: <boss_turns / ticks / row-index-start>
- Determinism controls:
  - mastery proc requests:
    - holder: <name>
    - mastery: <id>
    - count: <n>
    - declared location: <entity-scoped path>
  - other overrides: <turn overrides, forced rolls, etc.>

### Observability Surface (what the engine must expose)
- Event sink output: <events_out.json>
- Required event types:
  - TURN_START_BOOKMARK
  - EFFECT_APPLIED
  - EFFECT_EXPIRED
  - MASTERY_PROC
  - TURN_END_BOOKMARK
  - (optional if already exists) DAMAGE_APPLIED / SHIELD_HIT / TM_CHANGED / etc.

## 2. Evidence Facts (from screenshots)
> Each fact must be anchored to a turn/step boundary.

### Fact F1
- Anchor: Turn <N>, Step <K> (or "immediately after X visible action")
- Observation: <what screen shows>
- Interpreted state assertion:
  - `<field>` == `<value>`
- Notes: <why this mapping is valid>

### Fact F2
...

## 3. Black-box Acceptance Requirements
### R1 — Turn boundary event ordering
**Given** the engine begins processing a turn  
**When** a turn is executed  
**Then** the event sink must contain events in this relative order:

1. TURN_START_BOOKMARK
2. <start-turn housekeeping events, if any>
3. <triggered start-turn processing events, if any>
4. `<action resolution events>`
5. <effect duration decrement / expiration events>
6. `<proc events that are caused by expirations>`
7. TURN_END_BOOKMARK

**And** this ordering must hold within the same tick/step grouping when applicable.

### R2 — Effect expiration produces mastery proc (qualifying condition)
**Given** an effect instance E exists on owner O and expires at end-of-turn  
**When** the engine emits EFFECT_EXPIRED for E  
**Then** the engine must immediately emit MASTERY_PROC events that are causally attributed to that expiration,
subject to validation rules in R3–R5.

### R3 — Engine validates ownership and placement
**Given** a user requests a mastery proc for holder H with mastery M  
**When** an effect expiration occurs  
**Then** the engine must only emit the mastery proc if:
- the *expired effect owner* matches the qualifying rule for mastery M
- the *effect placer* (if relevant) matches the qualifying rule for mastery M
- the *proc holder* is the correct actor per mastery M definition

**And** if any validation fails, the proc request is ignored (or rejected) deterministically.

### R4 — Count reconciliation: requested procs must match qualifying expirations
**Given** the user requests count = C procs for (H, M) on a step  
**When** the engine processes expirations for that step  
**Then** emitted procs count MUST equal the number of qualifying expirations Q,
and the engine must enforce:

- emitted_count = min(C, Q)  (or emitted_count = Q if requests are declarative-not-prescriptive)
- no “extra” procs may be emitted beyond qualifying expirations
- if C > Q, the engine must not “invent” procs to satisfy C

(Choose one policy and lock it as part of the contract.)

### R5 — Event ordering within the expiration→proc chain
**Given** an effect expires and triggers a proc  
**Then** within the same step/tick group:
- EFFECT_EXPIRED must appear before the corresponding MASTERY_PROC
- MASTERY_PROC must appear before TURN_END_BOOKMARK
- if multiple expirations occur, procs must be emitted in the same relative sequence as expirations

### R6 — State assertions derived from events (ties back to screenshot facts)
For each Evidence Fact Fx:
- **Given** the pre-state at the anchor boundary
- **When** events for that boundary are applied
- **Then** the derived state must match Fx assertions:
  - `<field>` == `<value>`
  - `<field>` changed by `<delta>`
  - etc.

## 4. Test Cases (Gherkin-style outlines)
### TC1 — Expiration triggers validated proc and ordering
**Given** battle spec <...>  
**When** running `python -m rsl_turn_sequencing run ...`  
**Then** events contain:
- a TURN_START_BOOKMARK for turn N
- an EFFECT_EXPIRED for instance_id <...>
- a MASTERY_PROC for holder H mastery M count 1
- a TURN_END_BOOKMARK for turn N
**And** ordering satisfies R1 and R5.

### TC2 — Proc request ignored when no qualifying expiration
...

### TC3 — Count reconciliation across multiple expirations
...

## 5. Appendix: Field-level event expectations
For each event type, list the minimal payload fields the test asserts.
- EFFECT_EXPIRED: { instance_id, owner, placed_by, effect_id, step, tick, seq }
- MASTERY_PROC: { holder, mastery, count, step, tick, seq, reason/trigger_instance_id }
- TURN_*_BOOKMARK: { turn_index, active_actor, step/tick, seq }
