<!-- Session skill router. Schema: skill-router/v1. Inject at session start. -->
# Skill router

> Fail closed: activate a skill only when a trigger below matches. Vetoes are
> absolute and outrank any trigger match. If this router is missing or stale,
> fall back to manual invoke. State which skills are applied in the first
> line of the first substantive response.

| Skill | Trigger | Vetoes |
|---|---|---|
| `thinking` | any nontrivial task: analysis, planning, implementation, debugging, document work, review, multi-stage work | trivial factual answer; simple formatting |
| `teamwork` | work that touches shared state, spans agents or seats, or involves planning, architecture, code or config change, review, dispatch, or a canonical record | quick factual question; trivial one-off answer |
| `better-coding` | implementation, once outcome, scope, authority, and acceptance evidence are all fixed | any of the four facts unresolved; diagnosis-only, review-only, or documentation-only work |
| `plans` | planning, roadmap, design, architecture, or sequencing work with no current FINAL plan plus GO; before schema, credential, production, repository-boundary, or irreversible changes; restoring prior plan state | factual answers; trivial reversible one-step work; authorized execution under a current FINAL blueprint plus GO |
| `test-the-test` | tests are written, test coverage is reviewed, behavioral test quality is assessed, or high-risk behavior needs test evidence | none |
| `ship-or-fix` | the operator explicitly sets maximum assurance (G2) for the task, names this skill, or resumes a work unit already recorded at G2 | NEVER auto-activate on task class (security, auth, payments, migrations, production); if G2 seems warranted and the operator has not said so, ask once |

Before `better-coding` loads, state the four facts in one block:

```text
BUILDER GATE
RESULT: <fixed intended result>
SCOPE: <fixed authorized mutation boundary>
AUTHORITY: <fixed applicable authority>
EVIDENCE: <fixed observable acceptance evidence>
```

If one field is missing, unknown, or disputed, the skill does not load.
