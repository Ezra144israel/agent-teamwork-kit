---
name: ship-or-fix
description: "Oracle-frozen Builder and independent-Judge convergence cycle. Load ONLY when the operator explicitly sets Governance Dial G2 for the task, or explicitly names this skill or an active work unit already running it. Never auto-activate on task class, such as security, auth, or payments. If a task seems to warrant G2 and the operator has not said so, ask first. Not for ordinary governed implementation, analysis, review-only, or documentation work."
---

# Ship or Fix

## Progressive activation and mutual exclusion

Use the smallest production-completion level that fits the task:

- **Level 0, ordinary work:** factual answers, analysis, diagnosis,
  review-only work, formatting, generated refreshes, and non-executable
  documentation use proportional verification only.
- **Level 1, governed completion:** material production code or configuration
  changes use the existing `teamwork` Builder and independent final
  Reviewer path. Do not load or claim `ship-or-fix` at this level.
- **Level 2, Ship or Fix:** load this skill ONLY per the Governance
  Dial in `teamwork`: a direct operator
  instruction setting G2 for the current or named work unit, a direct
  imperative naming this skill for the work unit, or a resumed work unit
  whose durable `governance_level` record is already G2. Task class alone,
  including security, privacy, authentication, authorization, payments,
  destructive operations, irreversible migration, cross-system authority, or
  production publication, NEVER auto-activates this level; those tasks
  default to Level 1 with its integrity floor. If this level seems warranted
  and the operator has not set it, ask once (one line: risk at the current
  level, cost of this level); an unanswered question changes nothing and
  creates no stop. Discussion, quotation, or questions about this skill
  activate nothing.

The operator may explicitly stop this skill at any time; lowering is a
prospective operator transition that preserves produced evidence. If risk
classification is uncertain, perform the smallest read-only check needed to
frame the dial question; do not load the full skill merely to classify the
task. This skill never grants commit, publication, installation, deployment,
account, or product-Done authority.

Exactly one completion workflow may be enabled for a task, and the frozen
Outcome Contract names it. If another self-review or repair-loop workflow
appears enabled beside this skill, stop before candidate work and return
`RECONVERGE`.

`SHIP` means the implementation is independently `ACCEPTED` against the frozen
Outcome Contract and acceptance oracle. It is not merely ready for another
review. It is also not operator verification, product Done, or authority for a
later irreversible action.

## Responsibilities

Use existing governed seats. These are work-unit responsibilities, not new
authority-bearing seats.

- **Contract Owner**: normally the Orchestrator. Defines the outcome, authority,
  public seam, applicable production properties, exclusions, predicates, and
  proposed acceptance oracle. Never judges the artifact it assembled and never
  supplies the only scope-completeness or sensitivity challenge.
- **Scope Enumerator and Sensitivity Verifier**: independent of the Contract
  Owner, Builder, evaluator author, and Oracle Certifier. It produces the
  production-surface enumeration from pinned mechanical commands and
  authoritative repository sources. It also verifies Certifier-authored
  mutations through the frozen mechanical sensitivity harness; it never authors
  the predicate or mutation it verifies.
- **Oracle Certifier**: normally the Pressure-Tester and independent of the
  Contract Owner, Builder, and Scope Enumerator. Before a candidate exists, it
  attacks scope and sensitivity, authors at least one adversarial mutation per
  predicate that the Contract Owner did not supply, verifies identities and
  dominance, and either rejects the subject or certifies the frozen oracle. It
  does not certify its own mutations. It also adjudicates route families during
  repair and may not serve as Cycle Judge or Ship Judge.
- **Builder**: changes only the authorized implementation subject. It may run
  tests and return evidence, but never edits the frozen oracle, never contributes
  a candidate-authored test to acceptance, and never issues `SHIP`.
- **Cycle Judge**: a Reviewer independent of the Builder, Contract Owner, Scope
  Enumerator, and Oracle Certifier. It runs the complete frozen oracle, inspects
  the candidate and every repair delta, and maintains the cause and progress
  ledger. It returns `FIX`, `RECONVERGE`, `BLOCKED`, or
  `COLD_CHECK_PENDING`.
- **Ship Judge**: a Reviewer independent of the Builder, Contract Owner, Scope
  Enumerator, and Oracle Certifier, in a fresh session that did not observe the
  repair history and is not the Cycle Judge for this candidate. It receives only
  the frozen contract, certified oracle, final candidate, and identity-bound
  receipts. It alone may return `SHIP`.

One person or session may not occupy responsibilities that would certify its
own assembled or previously certified artifact. A Pressure-Tester may later
judge a revised subject that incorporates its findings because the revised
subject is the Contract Owner's new artifact, not the Pressure-Tester return.

The cold Ship Judge remains required until the measurable sunset rule under
Qualification is separately satisfied and accepted. If no eligible fresh Ship
Judge is available, return `BLOCKED` with the exact eligibility gap and reopen
condition; never substitute a repair-exposed Judge.

Distinct sessions may fill them only when the independence graph above permits;
no session may cross a stated exclusion. The Outcome Contract records the
minimum sufficient assignment and explains why this Level 2 control
is proportionate to the change risk.

At ORACLE_FREEZE, apply the current `test-the-test` guidance to public-seam,
failure-path, and durable-evidence design. At CYCLE_JUDGE and SHIP_JUDGE, apply
the judging-seat rules in `teamwork`. Pin both dependency identities in
the Outcome Contract; they grant no additional authority.

## Freeze the oracle before the candidate exists

Before Builder execution, seal a digest-pinned Outcome Contract and acceptance
oracle. Record:

- baseline and candidate identity rules;
- authorized implementation paths, protected paths, and a complete path
  classifier, including explicit rules for authorized new implementation paths;
- frozen evaluator and fixture paths, exact test allowlists, commands, tool
  versions, configuration, environment receipt, and expected outputs;
- the frozen mechanical sensitivity harness, including its exact path, command,
  tool version, inputs, outputs, and digest;
- every applicable production property, stable predicate ID, exact predicate,
  decisive evidence, evidence locator, public seam, and Contract-Owner-proposed
  failure mutation;
- the frozen cause-class and route-family taxonomies used to normalize failures
  and repair routes;
- every excluded property and the reason it is inapplicable;
- the independent production-surface enumeration and its receipt;
- authority boundaries, recovery, and true stops; and
- any externally imposed attempt, time, usage, or budget ceiling already owned
  by a higher-authority contract.

The Oracle Certifier verifies the oracle before it judges any candidate:

1. **Behavior sensitivity.** For every predicate, the Oracle Certifier authors
   at least one representative adversarial mutation that the Contract Owner did
   not supply. The independent Scope Enumerator, acting as Sensitivity Verifier,
   runs a frozen deterministic harness. The receipt passes only when the
   unmutated baseline passes, the mutation is proven reachable through the
   declared public seam, the protected behavior changes, and the frozen predicate
   fails. Exact inputs and outputs are pinned. The mutation author has no
   discretionary certification step.
2. **Scope sensitivity.** Scope is generated independently of the predicate and
   evaluator search lists. The receipt pins command, tool version, inputs, and
   output. Code subjects use authoritative build and deploy manifests, package
   entrypoints, public exports, module graphs, and tracked production-source
   discovery as applicable. Documentation, configuration, and repositories with
   no usable module graph use tracked-file discovery plus governing registries,
   indexes, routers, public entrypoints, and reference and consumer searches. If
   these cannot enumerate the affected surface, the independent Scope Enumerator
   assembles the set and the limitation remains explicit.
3. **Set agreement.** The receipt records the independently enumerated set and
   the evaluated set. Missing governed members fail closed.
4. **Public reachability.** The real entrypoint or caller reaches the behavior;
   source presence and isolated fixtures alone are insufficient.
5. **Absence discipline.** Zero matches prove absence only when coverage and
   sensitivity are independently established.

Candidate-authored or candidate-modified tests are never part of the acceptance
oracle. They may be supplementary Builder evidence only. Frozen test selection
uses an exact pre-candidate allowlist. Every allowlisted test's dynamic
dependencies, discovered members, registries, globs, directory walks, generated
inputs, and predicate denominators are also frozen and compared for exact set
equality; both added and missing members fail closed. A command whose acceptance
result can change through Builder-controlled discovery is not a valid oracle. A
candidate test may enter a later oracle only through a newly sealed subject and
independent certification.

Any path, fixture, configuration, or tool that contributes to a frozen
predicate is oracle-owned and protected. Any changed or new path that matches
no frozen classification is `UNCLASSIFIED`; judgment stops and returns
`RECONVERGE` before its output can contribute to acceptance.

## Production properties

Apply every property whose normal trigger fires. Repository security,
data-integrity, migration, registry-critical, privacy, or other hard gates are
additional required properties and cannot be weakened here.

1. **Behavioral completeness.** Required behavior passes at an observable
   public seam.
2. **Regression preservation.** Protected behavior remains intact.
3. **Failure behavior.** Invalid, unsupported, denied, and dependency-failure
   paths fail safely and observably without false success.
4. **Public integration.** The real entrypoint reaches the changed behavior.
5. **Change containment.** Only authorized implementation paths change; no
   unrelated churn or evaluator mutation is disguised as implementation.
6. **Maintainable shape.** Repository-owned deterministic checks for
   complexity, concentration, duplication, growth, and dependency shape pass
   their baseline-relative bounds. Absolute ceilings require existing
   repository authority.
7. **Evidence integrity.** Evidence is current, reproducible, candidate-bound,
   scope-complete, sensitive to failure, and independently interpretable.

## State machine

External verdicts are exactly `SHIP`, `FIX`, `RECONVERGE`, and `BLOCKED`.
`COLD_CHECK_PENDING` is an internal status, not an external verdict.

```text
OPEN
  -> ORACLE_FREEZE

ORACLE_FREEZE
  -> BUILD              only after certification and digest sealing
  -> RECONVERGE         when the contract, oracle, scope, sensitivity, role
                         independence, or identity cannot be certified
  -> BLOCKED            only when a true authority, safety, privacy, access,
                         essential-evidence, or irreversible-action stop
                         prevents certification

BUILD
  -> CYCLE_JUDGE        when the Builder returns the candidate and evidence
  -> RECONVERGE         when Builder work reveals an invalid contract or oracle
  -> BLOCKED            when a non-candidate environment, authority, safety,
                         privacy, access, essential-evidence, or irreversible
                         stop prevents further work

CYCLE_JUDGE
  -> MODEL_CHECKPOINT   before FIX when the third distinct objective-lineage
                         cause since the previous checkpoint is certified
  -> FIX                when the subject and oracle remain valid and a concrete
                         authorized implementation correction exists
  -> RECONVERGE         when outcome, scope, route, oracle, authority,
                         applicability, identity, or locked constraints are wrong
  -> BLOCKED            only at a true stop; candidate-caused failure is FIX or
                         RECONVERGE, never BLOCKED
  -> COLD_CHECK_PENDING when every frozen predicate passes

MODEL_CHECKPOINT
  -> FIX                on CONTINUE with a concrete next ledger delta
  -> RECONVERGE         when the subject or oracle model is invalid
  -> BLOCKED            only at a true stop or authority boundary

FIX
  -> BUILD
  -> CYCLE_JUDGE        with the same Cycle Judge and complete frozen oracle

COLD_CHECK_PENDING
  -> SHIP               only when an eligible fresh Ship Judge passes the
                         complete oracle
  -> FIX                when the Ship Judge finds an in-scope implementation defect
  -> RECONVERGE         when the Ship Judge finds a contract or oracle defect
  -> BLOCKED            when no eligible cold Judge or another true-stop
                         dependency is available
```

If the Ship Judge returns `FIX`, it becomes repair-exposed and may serve as the
Cycle Judge for that cause. A later terminal check requires another eligible
fresh-context Ship Judge. A candidate-caused environment or dependency failure
is `FIX`; a verified external environment failure that prevents decisive
evidence may be `BLOCKED` with an exact reopen condition.

An oracle defect discovered after BUILD preserves the candidate and receipts as
recoverable evidence but returns `RECONVERGE`, changes every oracle-dependent
green to `UNKNOWN`, and forbids acceptance under that subject. A new Contract
Owner may explicitly carry the implementation into a newly sealed subject; no
work is silently trusted or discarded.

## Repair cycle

For every `FIX`:

1. The Cycle Judge returns one complete finding set inside its declared search
   boundary. Each finding names the stable predicate ID, canonical evidence
   locator, frozen failure class, mechanically derived cause ID, evidence,
   required correction outcome, and exact recheck. The Judge does not prescribe
   reversible implementation method.
2. Before another action runs, the Judge records the expected
   `KEEP` / `DROP` / `UNKNOWN` ledger delta. A step that cannot change the ledger
   does not run.
3. The Builder proposes a route and family ID. The Oracle Certifier, not the
   Cycle Judge, checks it against the frozen route-family taxonomy before
   execution. A renamed command, wrapper, or syntactic variation is the same
   family. An unclassifiable route returns to the Contract Owner before it runs.
4. The Builder repairs the implementation inside the frozen scope.
5. A mechanical diff classification labels every changed path
   `IMPLEMENTATION`, `ORACLE`, `FIXTURE`, or `UNCLASSIFIED` against the frozen
   map and rules.
6. Any `ORACLE`, frozen `FIXTURE`, or `UNCLASSIFIED` change returns
   `RECONVERGE`. Every property previously green under the superseded or
   untrusted oracle becomes `UNKNOWN`; no stale green carries forward.
7. Before judgment, the Cycle Judge re-hashes the contract, oracle, fixtures,
   frozen mechanical sensitivity harness, enumeration, classifier, and tools
   against their pins. A mismatch returns `RECONVERGE` before tests run.
8. The same Cycle Judge inspects the repair delta, reruns the complete frozen
   oracle, rechecks prior failures, and looks for repair-introduced defects.

Derive cause identity mechanically:

```text
CAUSE_ID = SHA256(
  PREDICATE_ID || CANONICAL_EVIDENCE_LOCATOR || FAILURE_CLASS
)
```

All three inputs are frozen semantic IDs before candidate work and are scoped to
the operator-approved objective lineage, not one oracle version. A failure that
does not match the taxonomy is `UNCLASSIFIED_CAUSE` and returns `RECONVERGE`;
changing oracle, subject, prose, session, or Judge cannot mint a new cause ID.

`PREDICATE_ID` and `CANONICAL_EVIDENCE_LOCATOR` are objective-lineage-stable
semantic IDs. The locator identifies the public seam and observation channel and
never uses a transient line number, timestamp, output ordering, temp path, or
repair-sensitive formatting. Every reconverged subject carries the complete
cause, route-family, checkpoint, and counter history. Its cause-lineage receipt
maps updated source clauses and oracle checks to the unchanged semantic IDs. A
genuinely changed production property requires an explicit new predicate and
new-cause justification independently checked by the Oracle Certifier. The
Certifier challenges the taxonomy for both false splits and false merges before
sealing it.

There is no numerical repair, artifact-version, token, or time ceiling created
by this skill. Externally owned ceilings remain binding and never reset when a
route or session changes.

At the third distinct certified objective-lineage cause since the previous
checkpoint, CYCLE_JUDGE enters `MODEL_CHECKPOINT` before another BUILD. The
Contract Owner and Oracle Certifier re-check outcome, scope, root-cause model,
oracle sensitivity, and authority. They record `CONTINUE`, `RECONVERGE`, or
`BLOCKED` with evidence. `CONTINUE` is not acceptance and requires a concrete
next ledger delta. The scheduling count restarts only after the receipt; it does
not erase causes, route-family history, reconvergence lineage, external counters,
or evidence. This is an automatic model-integrity checkpoint, not a repair cap
or an operator approval gate.

## Find a Way and cause-based termination

Invoke `thinking`'s `references/find-a-way.md` by its pinned
identity and apply the whole reference: guard, trigger, KEEP/DROP/UNKNOWN
salvage, cheapest discriminating experiment, route-family diversity, progress,
counter accounting, terminal, and authority limits.

For this workflow, the standing trigger keys on the objective-lineage-stable
cause ID: when that same cause survives one meaningful correction, Find a Way
fires. The Oracle Certifier adjudicates route-family difference. When two
certified families die on the same cause, do not open a third and do not reset
through reconvergence. Return the cause exactly as the pinned reference requires:
either a true stop or an authority proposal. The workflow mapping is `BLOCKED`;
an authority proposal carries `CONTEXT IMPACT: AUTHORITY_STOP` and the exact
operator decision needed to open a different authorized work unit.

Persistence never expands authority, scope, spend, access, or irreversibility.

## Judge returns

Every Judge return begins with candidate, baseline, contract, oracle,
enumeration, classifier, tool, environment, role-eligibility, and ledger
identities plus the declared search boundary.

For each property:

```text
PROPERTY:
PREDICATE ID:
PREDICATE:
ORACLE IDENTITY:
INDEPENDENT SCOPE ENUMERATION:
OBSERVED EVIDENCE:
CERTIFIER-AUTHORED SENSITIVITY RECEIPT:
VERDICT EFFECT:
```

For `FIX`, also return:

```text
CAUSE ID:
CAUSE-ID INPUTS:
EXACT GAP:
WHY IT MATTERS:
REQUIRED CORRECTION OUTCOME:
EXPECTED LEDGER DELTA:
ROUTE FAMILY CLAIM / CERTIFIER DISPOSITION:
EXACT RECHECK:
```

For `RECONVERGE`, name the invalid contract or oracle assumption, invalidate
dependent greens, preserve recoverable candidate evidence, close the current
subject, and state the minimum new subject and its review gate.

For `BLOCKED`, name the true stop, evidence, preserved assets, lawful
alternatives, and exact reopen condition. A candidate-caused failure is not
`BLOCKED`.

For `SHIP`, record complete final-state evidence and state explicitly:

```text
SHIP = INDEPENDENT IMPLEMENTATION ACCEPTANCE
PRODUCT DONE: NOT CLAIMED
COMMIT / PUBLICATION / INSTALLATION / DEPLOYMENT AUTHORITY: NOT GRANTED
OWNER VERIFICATION: STILL SEPARATE
```

## Qualification design and cold-control sunset

The 32-case, 96-judgment qualification is not complete. Its design is not a
per-task gate.

The qualification corpus contains at least 32 interleaved whole cases:

- 8 clean candidates whose expected terminal verdict is `SHIP`;
- 14 defect candidates, two independently assembled injections for each
  production property P1-P7; and
- 10 process attacks covering frozen-oracle mutation, candidate-test and dynamic
  discovery infiltration, incomplete self-declared scope, evidence tampering,
  unconditional verdict behavior, progressive multi-repair, zero-delta churn,
  two-family same-cause exhaustion, cause-lineage reset, and role or cold-Judge
  unavailability.

Run each sealed case in exactly three fresh Judge contexts: 96 primary judgments,
with no discretionary reruns. A whole case passes by majority only when both its
terminal verdict and required state transitions match the hidden expectation.
Qualification requires all 32 whole-case majorities correct and at least 92 of
96 primary judgments individually exact, the smallest whole-judgment count that
meets a predeclared 95% individual-accuracy floor.

Any primary judgment that returns `SHIP` for a known defect, changed oracle,
tampered channel, or missing governed member triggers exactly two predeclared
fresh-context confirmation judgments on that same sealed case. If either
confirmation also false-ships, qualification fails. Both confirmations count in
the published measurement; there are no further retries.

Measure Cycle-Judge versus Ship-Judge detection on every terminal pair. The cold
Ship Judge cannot be retired during initial qualification. A later sunset
subject requires at least 149 independently scored paired terminal judgments:
at least 99 defect candidates and 50 clean candidates. Warm judgments must match
all sealed expectations. Among the 99 or more defect pairs, zero defects may be
detected only by the cold Judge; that criterion is exactly the one-sided 95%
Clopper-Pearson upper bound of at most 3% for a zero-event cold-only detection
rate with defect candidates as the denominator. Clean-case false-positive rates
must not worsen without the cold control. The analysis and retirement amendment
require independent acceptance. Any missed threshold keeps the cold control in
force.
