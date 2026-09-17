# Decomposition, delegation, and integration

Read this when work is being split into steps for another executor, a subagent, or a dispatch.

## Delegable decomposition

Decompose large work so that each step could be completed by a weaker executor than you:

- one clear objective per step;
- an acceptance test per step, stated **before** the step runs;
- each result checked against its test before anything builds on it.

If a step cannot be given a single objective and an acceptance test, it is not yet a step. Decompose further, or name it explicitly as a judgment call that stays with you.

## The integration rule

Decompose only across clean interfaces; keep tightly coupled or judgment-heavy work together. Do not permit parallel mutation of shared state without explicit ownership boundaries. One owner integrates the outputs and verifies the combined result. Individually passing pieces whose assembly was never tested are not a passing whole.

## Subagent delegation

- **Delegate the reading, keep the conclusion.** A subagent sweeping many files or one very large file should return findings and `file:line` citations, never source dumps. A distilled return of roughly 1,000 to 2,000 tokens is the target shape.
- **A subagent report is not grounding.** Any load-bearing claim it returns is re-verified at the named lines before it enters an artifact. Their narration is a lead, not a source.
- **Give it the same contract discipline you would give a dispatch:** objective, scope, what not to touch, what evidence to return, and the exact return shape. A vague subagent prompt produces a vague report you then cannot verify cheaply.
- **Parallel subagents need disjoint surfaces.**
- **Declare the selection rule before spawning, not after seeing results.** First pass, rank all, or best of. Choosing the rule once the returns are in is how a preferred answer gets selected and called a finding.
- **Route bulk reads, never the grounding read.** Delegation after grounding is sound. Delegating the grounding itself moves the state change into the wrong agent, and the seat that acts on it never ran its own grounding gate.

## What a step's contract must carry

Whether the executor is a subagent, another seat, or a future you:

1. **Outcome.** The real result, not the activity.
2. **Scope.** The minimum sufficient surface, enumerated.
3. **Authority boundaries.** Explicit do-nots, and what is out of bounds even if it looks necessary.
4. **Acceptance evidence.** What proof will be accepted, named in advance.
5. **Method ownership.** Reversible, testable in-scope choices default to the executor; lock a method only for safety, privacy, authority, or irreversibility, and state the basis.
6. **True hard stops.** The conditions that mean stop and return, distinguished from ordinary obstacles that mean adapt and report.
7. **Return.** The exact handback shape and the publication posture (what the executor may and may not do with the result).

## Judging a return

- Verify the load-bearing claims in source, not in the report.
- Check what is absent as carefully as what is present: an unmentioned file, an unrun gate, a silently narrowed lens.
- A return that reports only success is a return that has not been checked adversarially. Ask what it would have looked like if the work were wrong.
