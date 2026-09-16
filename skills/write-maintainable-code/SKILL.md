---
name: write-maintainable-code
description: "Evaluate minimum-sufficient implementation routes and enforce the selected route for a fixed, authorized outcome. Use after outcome, scope, authority, and acceptance evidence are fixed. Do not choose outcomes, set acceptance, adjudicate governance, grade finished work, design tests alone, conduct security audits, or perform unrelated cleanup."
---

# Write maintainable code

Use the fewest concepts that satisfy the approved result and its acceptance
evidence. Minimize maintenance burden, not raw line count.

## Keep the ownership boundary

- `reasoning-doctrine` owns the stage, outcome, scope, evidence, route
  recommendation, hard stops, and the transition to execution.
- `governed-operator` owns authority, seats, formal contracts, verdicts,
  publication, and Done.
- This skill owns route comparison, ownership seams, concept control,
  readability, and implementation verification.

If outcome, acceptance evidence, or authority is unresolved, return to its
owner. Apply this lens only to the selected route and safe slice. A finished
change needs independent review.

## Compare routes before adding code

1. Restate the fixed result and acceptance evidence without reopening them.
2. Inspect current code and reuse candidates. Compare current behavior,
   configuration, reuse, adaptation, replacement, new code, deletion,
   documentation, and no-code routes. If the current evidence already passes,
   make no change.
3. Compare the strongest simpler alternative. Choose a route only when the
   fixed acceptance evidence can prove it.
4. Name the smallest ownership seam and the concepts the selected route
   needs. Give each new responsibility a concrete reason tied to the accepted
   outcome. Name tempting concepts the result does not need.

Choose reuse when it is the better total solution. Existing code alone is no
reason to require reuse or reject new code. Compare simplicity, safety,
clarity, coupling, and maintenance cost. Existing tools, frameworks, vendor
implementations, standards, protocols, and delivery systems are options.
Building a capability, connection, protocol, or delivery mechanism remains
valid when it is the better lawful solution. Neither reuse nor custom work
wins without evidence.

For an implementation return or an engineering proposal required by
`governed-operator`, name the inspected source and reuse candidates, what to
reuse, adapt, replace, or build and why,
the strongest simpler alternative, necessary new responsibilities, material
placement and dependency choices, verification and meaningful negative cases,
and unresolved prerequisites or decisions that could change implementation.
Keep this evidence short. That owner decides when a proposal is required and
how it returns. This skill creates no proposal or approval gate.

When routes satisfy different checks and the current evidence does not identify
the applicable check, return that gap to whoever owns the outcome and
acceptance evidence. Do not create a second implementation brief or return
schema.

## Bound the implementation

Decline a dependency, layer, abstraction, state, endpoint, migration, generic
helper, or compatibility path whose only reason is hypothetical reuse or an
unselected future. Prefer readable, explicit, testable code over dense code. A
longer implementation is smaller when it carries fewer concepts or less
maintenance risk.

Treat file size as a signal, not a diagnosis. Extract a bounded seam only when
the extraction lowers verified current risk. Remove only code made obsolete by
the selected change. Report unrelated cleanup instead of doing it.

For external calls, choose the failure path deliberately: timeout, retry,
idempotency, partial failure, and secret handling where they apply. Load
project security or infrastructure detail for those boundaries.

## Verification and repair discipline

Before editing, inspect the repository status and the complete target diff.
Separate defects introduced by the selected change from pre-existing defects.
Pre-existing issues stay out of scope unless the operator expands the contract.

Match verification to the fixed acceptance evidence. Before returning, inspect
the final diff and status again, then run the required repository gates.
Advisory or judgment-heavy measurement must not become a mandatory deployment
gate. After each repair, run the narrowest relevant focused recheck. Never
weaken assertions, remove coverage, suppress errors, or change expected
behavior to obtain a green result.

Stop when the selected acceptance evidence passes. Do not add cleanup or
future-proofing after that point.

For tasks that need mechanical containment, the optional Enforcement Layer
[`change-containment-guard`](../../change-containment-guard/) can seal allowed
change classes and bind verification to the exact final repository state. It
does not replace this Instruction Layer skill's maintainability judgment or
independent review.

With `governed-operator` active, return the route, seam, declined concepts,
verification, and residual risk in its Builder judgment record.
