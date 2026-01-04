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

### A1 — Form-Capable / Mythical Champion Semantics

This section records modeling decisions for champions with multiple forms
(e.g. Mythical champions using Metamorph).

**Conceptual model**

- A Mythical champion is represented as a **single actor**
- The actor may have multiple **forms**
- Form changes do **not** create a new actor

**Form-capable input (JIT schema fields)**

- `form_start`
- `speed_by_form` (e.g. `{ alt: 280, base: 255 }`)
- `metamorph` modeled as an **active skill** with:
    - `cooldown_turns`

**Metamorph as an active skill**

- Metamorph is a selectable **active skill**
- Using Metamorph:
    - is chosen on the actor’s turn
    - consumes the turn
    - immediately switches the actor’s form
    - may grant an extra turn

**Cooldown semantics**

- Cooldown is set to its **maximum value immediately on use**
- Cooldown decrements at **TURN_START** of the actor’s subsequent turns
- Skill availability is evaluated:
    - after TURN_START decrement
    - before action selection

**Turn and speed effects**

- Form changes take effect immediately during the turn Metamorph is used
- Any granted extra turn uses the new form and skill set
- Any speed changes affect **subsequent turn-meter fill**, not retroactively

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

**Locked mechanics (Fyro / Divine Shield boss)**

- Boss shield is a **hit-count shield**:
    - Each **hit instance** against the boss reduces shield strength by **1**
    - Shield breaks when reduced to **0**
- Shield **resets to full at boss TURN_START**
    - Stage 10 shield strength: **21**
- While shield is active:
    - Boss receives **no debuffs** and is unaffected by other skill effects
    - Boss damage taken is reduced (damage math out of scope for v0)
- Boss has **2 active skills** (A1/A2) and uses **priority + cooldowns**:
    - **A2 preferred** if available; otherwise use A1
    - Cooldowns follow engine semantics (set to max on use; decrement at TURN_START)
- Boss TURN_START passive behavior (when shield is active):
    - Performs an **automatic AoE attack (1 hit)** before normal action selection
    - Heals at TURN_START (logged as event; magnitude out of scope for v0)
- Boss reaction while shield is active:
    - When attacked, applies an **on-hit retaliation** to the attacker **per hit**
    - (For v0, log the reaction events; do not model champion death yet)
- Boss immunities relevant to v0 sequencing:
    - Boss is immune to **Turn Meter decrease** effects (ignore TM decrease events targeting boss)

**Data foundation required (JIT inputs)**

- Extend actor metadata to include:
    - `faction` (required for faction-gated join attacks, e.g., Mikage A1)
- Represent action resolution as an event sequence that can emit hit instances:
    - `attack(hits, target_mode)`
    - `join_attack(selector, skill=default)`
    - `extra_turn(granted=true/false)`
    - `change_form(to=base/alt)`
    - `apply_buff(...)` / `apply_debuff(...)` (logged; does not affect shield points directly)
- Blessings that affect shield tracking are modeled as **event injectors**:
    - Example: Phantom Touch → conditional extra **damage/hit instance** event (test-forced, not RNG)
    - Faultless Defense → reaction damage event during boss turn (counts-as-hit TBD; log as damage event)

**Deterministic ordering (composition-driven)**

- Ally attacks and counterattacks resolve in **team slot order**.
- Canonical slot order for this composition:
    1) Mikage
    2) Mithrala
    3) Martyr
    4) Tomb Lord
    5) Coldheart
- Rationale: later-slot A1 debuffs (Tomb Lord / Coldheart) should have opportunity to land
  after shield breaks mid-sequence.

**Shield-break mid-sequence rule (v0)**

- If shield reaches 0 during a multi-hit / join-attack sequence:
    - Remaining hits in that same sequence still occur
    - Shield points do not go below 0
    - Post-break hits are considered against an “open” boss (effect application out of scope for v0)

**Planned tests (v0)**

- Mikage A1 join gating:
    - Given **no Shadowkin allies** in composition, Mikage base A1 produces **no join attacker**
    - Requires `faction` modeled for each actor
- Imperial Decree expansion ordering:
    - Default-skill team-up executes in the canonical **team slot order**
    - Produces expected hit-instance count from A1 profiles (and optional forced blessing injectors)
- Boss shield reset:
    - Shield points reset to full at **boss TURN_START**, before TURN_START passive AoE attack
- Boss action selection:
    - A2 is chosen when off cooldown; otherwise A1

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
- Damage modeling (full formulas), debuff resolution, ACC/RES modeling
- Interactive or conditional skill choice
- UI / visualization layers
- Policy-layer AI decisions
