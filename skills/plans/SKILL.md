---
name: plans
description: Use for planning, roadmaps, design, architecture, sequencing, or before consequential work when no current FINAL plan plus GO covers it. Fire before changes to data or schemas, credentials or auth, production or releases, repository or source-home boundaries, irreversible work, or materially costly mistakes. Re-enter when that scope appears mid-task or when restoring prior plan state. Skip factual answers, trivial reversible one-step work, and authorized Builder or Reviewer execution under a current FINAL blueprint plus GO unless a reopen condition fires.
---

# Plans

Keep a compact Plan Capsule, not the planning transcript, for material work.

## Plan Capsule

```text
PLAN <id>: DRAFT | CHALLENGE-READY | FINAL
AS OF <latest operator instruction accounted for>
DEPTH: LIGHT | STANDARD | DEEP

ASKED
<operator's words that define the outcome>

GOAL
<accepted restatement>

DELIVERABLE
<what will exist>

PLAN
1. <step with a checkable completion condition>
2. <step with a checkable completion condition>

DONE
<smallest observable acceptance condition>
```

Add `SOURCE HOME`, `BOUNDARIES`, or `OPEN` only when they carry load-bearing information.

Copy `ASKED` from the operator. A continuation (`proceed`, `yes`) keeps `ASKED` and advances `AS OF`. A changed outcome replaces `ASKED`, updates the plan, and is read back.

## Readback

Show the full current capsule when a load-bearing part of the plan changes, before challenge, on restore, and before final closeout. Append only applicable temporary sections:

```text
CHANGED
- <changed plan state>

ADDED
- <new agent-added scope or requirement>

DROPPED
- <operator-requested item that disappeared or changed meaning>
```

Do not persist those temporary sections after the operator has seen them.

## Depth and challenge

- `LIGHT`: bounded, familiar, reversible work. No challenge by default.
- `STANDARD`: several meaningful decisions or moderate uncertainty. Challenge when a load-bearing question remains, the operator asks, or error cost warrants it.
- `DEEP`: architecture, broad blast radius, authority, safety, recovery, migration, expensive error, or major uncertainty. Challenge by default unless the operator skips it.

Raise depth when stakes rise. Read back every depth change.

## Restore

Before continuing restored planning or execution:

1. Reproduce the latest complete capsule.
2. Verify that `AS OF` includes the current operator instruction.
3. Show the capsule readback before any mutation or execution.

If the capsule is complete, exact, and current, continue after the readback. Do not ask for another confirmation only because a session boundary occurred.

If state is incomplete, stale, conflicting, uncertain, or cannot reproduce the complete capsule exactly, mark `RESTORED: UNVERIFIED`, show the reconstruction, and hold for operator confirmation. A FINAL blueprint plus GO is not an exact restore when the complete capsule cannot be reproduced.

## Final and GO

Ask: `Is this the plan?`

When the operator settles the plan, respond exactly:

`Plan is FINAL. Execution waits for your GO.`

`FINAL` never authorizes execution. Execute only after a later, separate, explicit `GO`.

## Downstream blueprint

When a FINAL plan is handed to a Builder or Reviewer, read `references/blueprint.md`. Reopen planning before changing the objective, deliverable, source home, load-bearing boundary, acceptance condition, or plan currency.
