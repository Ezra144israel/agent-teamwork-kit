# Escalation, retries, and knowing when to stop

Read this when a step comes back wrong, a tool call fails, or confidence is degrading across attempts.

## Escalation sense

Know when to stop. If confidence is degrading, with repeated failed attempts, mounting unverified assumptions, or results that contradict the model in your head, do not push through on momentum. Stop, summarize the state honestly as verified, inferred, or unknown, name what you tried and why it failed, and hand back to the operator with the decision that is actually theirs to make.

## The retry ladder

When a step comes back wrong:

1. **Diagnose first.** Read the actual output: exit code, error text, unexpected shape.
2. **Default to one corrected retry.** Narrower scope, corrected premise, better input. The retry must differ from the original attempt in a way that could plausibly change the outcome.
3. **Risky or irreversible actions get zero automatic retries.** Escalate instead.
4. **Additional retries beyond one** are justified only when the failure is plausibly transient AND each attempt changes the method or yields new evidence. Repeating the same failure class without new information is a loop and must stop.
5. **Escalate with the specific blocker:** what was tried, what happened, what is needed.

## Side-effect safety

Before retrying anything with side effects, establish whether the first attempt actually happened. A retry of a succeeded-but-unconfirmed step is a duplicate, not a retry. Re-sending a message, re-submitting a mutation, or re-writing an immutable artifact can double-execute.

When the tool's result is ambiguous about whether the effect landed, checking the resulting state is mandatory before any retry.

## Failure classification

Before reporting a failure, classify it. The class determines who owns the next move:

| Class | Signature | Next move |
|---|---|---|
| Transient | network, rate limit, timeout, flake | one corrected retry, then escalate |
| Environmental | missing dependency, wrong path, no permission, unmounted surface | fix the environment or report the missing access; do not retry blind |
| Premise error | the thing you were told exists doesn't, or behaves differently | stop, correct the premise, re-ground; tell the operator their premise was wrong |
| Scope error | completing this requires authority or files you were not given | `BLOCKED` or `RECONVERGENCE_REQUIRED` per the governing contract; never widen silently |
| Genuine defect | the work is wrong | repair, re-verify the affected checks, and re-run the gates the repair could have disturbed |

Never report a failure without naming which of these it is. "It didn't work" is not a classification.

## Pre-existing versus introduced

When a full battery or build fails during work you did not scope, compare against a clean run of the same command in the same environment before classifying the failure as pre-existing. An assumed-pre-existing failure that was actually introduced is one of the most expensive errors available, because it ships.
