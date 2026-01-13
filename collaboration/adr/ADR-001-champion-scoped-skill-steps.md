# ADR-001: Champion-Scoped Skill Sequence Steps for Mastery Proc Scheduling

## Status
Accepted

## Context

The battle spec allows users to schedule **Mastery Proc requests** using a field named `step`, nested under each champion.

During CLI integration testing, scheduled mastery procs were never emitted in real runs, despite appearing correctly constructed in tests. Investigation revealed ambiguity and overload in the term **“step”**, alongside multiple internal engine counters (`tick`, `seq`, `turn_counter`) with different semantics.

Empirical inspection of `events_out.json` showed:
- `tick` is a global simulation heartbeat.
- `seq` is a 1-based ordering index of events within a tick and resets every tick.
- Neither `tick` nor `seq` corresponds to a user-facing notion of step.
- A global grouping of proc requests by numeric step caused unrelated champions’ schedules (e.g., Mikage step 6 and Mithrala step 6) to be combined incorrectly.

A detailed analysis and evidence are captured in:
- `collaboration/mastery_proc_step_semantics.md`

## Decision

The engine will interpret user-facing **`step`** as:

> A **1-based index of a specific champion’s skill activation sequence**.

Accordingly:
- Mastery Proc scheduling is **champion-scoped**, not global.
- The engine will maintain a per-champion `skill_sequence_step` counter that increments only when that champion consumes a skill.
- Mastery Proc requests will be stored and consumed using the key:
  `(champion_name, skill_sequence_step)`
- Internal counters (`tick`, `seq`, `turn_counter`) will not be used for mastery proc scheduling.

## Consequences

- The mastery proc requester builder must be refactored to be **champion-first**, not step-first.
- The engine must translate runtime state into `(champion, skill_sequence_step)` before consulting the requester.
- Relevant events (e.g., `SKILL_CONSUMED`, `MASTERY_PROC`) should expose `skill_sequence_step` for observability and debugging.
- This change aligns engine behavior with user expectations and eliminates silent scheduling failures in CLI runs.

## Notes

This decision formalizes existing battle spec intent and resolves semantic drift introduced by organically grown engine counters. It prioritizes user-facing correctness over internal convenience.
