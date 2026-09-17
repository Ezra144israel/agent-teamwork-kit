# Find a Way

Load this when a trigger below fires. It helps the seat find the shortest lawful route toward
the unchanged objective. It does not change authority, scope, acceptance
evidence, or stop conditions.

## Triggers

Load this reference when:

- the operator says `find a way`, `solve it another way`, `unblock this`, or an
  equivalent;
- a diagnosed and meaningfully corrected route fails while no true stop
  applies;
- a Pressure-Tester encounters any blocking finding;
- a Reviewer encounters any blocking finding; or
- a Pressure-Tester or Reviewer has a non-blocking finding and can identify a
  lawful solution worth returning.

Do not load it to create activity when a judging seat has no finding. Use a
proportionate pass for a small non-blocking issue. Do not invent alternatives
when no useful alternative exists.

## Re-anchor

Restate the unchanged:

- objective and constraints;
- acceptance evidence;
- authority and scope;
- budget and binding retry, attempt, cycle, time or cost limits; and
- true stops and operator decisions.

Never solve a method failure by weakening a locked goal, acceptance predicate,
safety boundary, privacy boundary, or authority limit.

## 1. Salvage first

Record the ledger before choosing another route.

```text
KEEP:
- verified working parts
- useful learning
- evidence worth carrying forward

DROP:
- disproven assumptions
- mechanisms shown not to work

UNKNOWN:
- untested or unresolved layers
```

If a dropped assumption supported a `KEEP` item, move that item back to
`UNKNOWN`. A failed route is evidence; it is not permission to discard the
objective.

## 2. Audit the boundary

Separate `LOCKED` from `ASSUMED METHOD`.

`LOCKED` includes authority, safety, privacy, acceptance evidence, budget,
binding retry, attempt, cycle, time or cost limits, operator decisions, and
hard stops. A default review or process threshold is not `LOCKED`;
teamwork's cycle reassessment rule classifies it.

`ASSUMED METHOD` includes the tool, mechanism, order, representation,
decomposition, and implementation route. Replace an assumed method when it
fails. Preserve locked conditions.

## 3. Create route diversity

When uncertainty remains, identify at least two lawful routes from genuinely
different families. Useful families include:

- correct the premise;
- change the mechanism;
- decompose or reorder;
- change the representation;
- transfer a proven technique;
- repair the environment;
- seek lawful counsel;
- ask the boundary owner; or
- build a missing capability when separately authorized.

Renaming the same mechanism is not route diversity. If the issue is small and
non-blocking, a single obvious lawful route is enough; do not add ceremony for
its own sake.

## 4. Run the cheapest discriminating probe

When the seat has authority for a read-only or otherwise non-mutating check,
state what observation would separate the routes and run the cheapest useful
test. Do not end in brainstorming when a lawful probe can answer the question.

A judging seat may inspect lawful sources, run authorized non-mutating checks,
compare routes, identify root cause, and propose environment repair. It may
not edit the reviewed artifact, implement a fix, mutate shared state, commit,
push, publish, deploy, approve, widen scope, grant authority, or weaken the
objective or acceptance evidence.

## 5. Require ledger progress

Every probe must do at least one of the following:

- add a `KEEP`;
- add a `DROP`;
- reduce or split `UNKNOWN`;
- open a genuinely new route; or
- establish a true stop.

Do not repeat a route without changed evidence. Preserve `KEEP`, identify
`DROP`, isolate `UNKNOWN`, and state the probe result in the return.

## 6. Consolidate root causes

When several symptoms die on the same verified cause, return that cause as the
blocker. Do not inflate one root into several independent findings or optimize
for rejection count. Give the owning seat enough evidence to repair the
complete defect class.

## 7. Handle a true stop

Hold the affected operation when authority is missing, safety or privacy
blocks it, essential evidence cannot be trusted, scope must change, an
irreversible choice needs the operator, or an explicit retry, attempt, cycle, time or cost limit that binds under
teamwork's cycle reassessment rule is exhausted. Classify default review/process
thresholds through teamwork's cycle reassessment rule before treating
a count as exhausted authority. Keep independent authorized work moving.

Return the exact blocker, preserved `KEEP`, failed routes, lawful alternatives,
and what unlocks continuation. Name an authority proposal and re-entry
condition when authority is the only missing piece. Do not collapse the result
into "impossible."

## 8. Apply it in judging seats

Pressure-Testers and Reviewers use this reference to improve the quality of
their return while preserving independent judgment. They are adversarial toward
defects and cooperative toward the shared outcome.

Pressure-Testers do not rewrite the packet they judge. Reviewers do not
implement the Builder repair they judge. Advice is not authorship.

For each blocking finding, return the root defect class, grounded evidence,
`KEEP`, `DROP`, `UNKNOWN`, the lawful route or routes, the cheapest useful
probe and result when one exists, the recommended remedy, real alternatives,
the close or unlock condition, and the shortest `PASS SHAPE` or `ACCEPTED
SHAPE`. A substantive defect may still correctly produce `FAIL` or
`NEEDS_REVISION`.

For a solvable non-blocking finding, use a proportionate pass and return the
smallest lawful solution. Do not bounce it to the Orchestrator merely because
the judging seat cannot implement it.

## 9. Close the search

When a route is verified and the problem is solved, close the finite route
search. If no lawful route exists or essential evidence cannot be trusted,
use the true-stop format instead.
