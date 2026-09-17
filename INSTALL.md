# Install and use agent-teamwork-kit

Package version 4.2.1.

Version 4 has two separate install routes. The **Instruction Layer** is six
plain-markdown skill packages. The **Enforcement Layer** is two standalone
guards that you install and wire yourself.

The plugin installs only the six Instruction Layer skills. It does not install,
wire, or activate either Enforcement Layer guard. Cloning the repository also
activates nothing.

## Instruction Layer

Each skill is a `SKILL.md` file with optional reference files. The skills work
on any agent surface that can read markdown instructions. The install path
differs by surface.

**Folder names are already canonical.** Each folder under `skills/` matches the
`name:` in its frontmatter, so copy it across as-is, with no renaming step.

**Respect the installation units.** In package order:

- `thinking` works alone.
- `teamwork` requires `thinking`.
- `better-coding` works alone.
- `plans` works alone.
- `test-the-test` works alone.
- `ship-or-fix` requires `teamwork`, `thinking`,
  and `test-the-test`.

Installing a skill without its required companions leaves it honest but
partially inoperative (for example, G2 work is unavailable without
`ship-or-fix`'s companions present).

---

### Before you install: check for conflicts with your existing setup

These skills are opinionated. If your environment already carries
instructions, such as a `CLAUDE.md`, an `AGENTS.md`, custom rules, other
installed skills, or project instructions, some of them may contradict what
these skills mandate (who may commit, when tests are written, how reviews
conclude, when the agent asks versus proceeds). An undetected conflict shows up
later as confusing agent behavior, and it will look like the skills are
broken when the real problem is two rulebooks disagreeing.

Two minutes of checking prevents that:

1. **Claude Code users:** run `/doctor` first to confirm your installation
   and settings are healthy before adding anything.
2. **Everyone:** before installing, have your agent read the skill files
   against your existing configuration and report contradictions. A
   paste-ready prompt:

```
Read the SKILL.md files in <path to this repo> but do not install or apply
them yet. Then read my existing configuration, including CLAUDE.md, AGENTS.md,
project instructions, rules files, and currently installed skills. List every
place where these skills would contradict, duplicate, or override something
I already have, especially rules about committing and pushing, test
ordering, review and approval, when to ask me versus proceed, and output
format. For each conflict, tell me which side you would obey and why. Do
not resolve anything. Just report.
```

3. **Decide the precedence yourself.** For each conflict, either remove your
   old rule, adapt the skill text, or write one line in your top-level
   instructions naming which source wins. An explicit precedence line beats
   two silently competing rules every time.

If the report comes back empty, install with confidence. If it doesn't,
you've just saved yourself a debugging session that would have been blamed
on the wrong thing.

---

### Claude Code (CLI)

Skills live as folders on disk. Claude Code discovers them automatically,
with no configuration or upload step.

Personal (all your projects):

```
mkdir -p ~/.claude/skills
cp -r skills/thinking ~/.claude/skills/thinking
cp -r skills/teamwork ~/.claude/skills/teamwork
cp -r skills/better-coding ~/.claude/skills/better-coding
cp -r skills/plans ~/.claude/skills/plans
cp -r skills/test-the-test ~/.claude/skills/test-the-test
cp -r skills/ship-or-fix ~/.claude/skills/ship-or-fix
```

Copy only the units you want. See the installation units above.

Per-project (checked into one repo, applies only there): use
`.claude/skills/` at the repo root instead of `~/.claude/skills/`.

Verify: start a session and ask "what skills do you have available?" The
installed names should appear. Reference files under `references/` and
`reference/` load automatically when their trigger fires. Do not flatten them.

### Claude web / desktop (claude.ai)

Requires a paid plan (Pro, Max, Team, or Enterprise) with code execution /
file creation enabled.

1. Zip each skill folder individually, with `SKILL.md` at the top level of
   the folder inside the zip (for example `teamwork/SKILL.md`).
2. Go to **Settings → Features** (naming varies slightly by plan. Look for
   Skills under Features or Capabilities).
3. Upload each zip. Skills are per-user, so each team member uploads their
   own copy.

Verify: in a new chat, ask Claude to list its available skills.

### Claude API

Upload each skill as a zip via the Skills API (`/v1/skills`) with the
`skills-2025-10-02` beta header, enable the code execution tool, and pass the
returned `skill_id` in the `container` parameter of your requests. API skills
are workspace-wide but separate from claude.ai uploads. The two surfaces do
not sync.

### Codex (OpenAI)

Codex discovers skills from `SKILL.md` folders, in priority order:

- Repo-level: `.agents/skills/` (working directory, parents, or repo root)
- User-level: `~/.agents/skills/`
- Admin-level: `/etc/codex/skills/`

```
mkdir -p ~/.agents/skills
cp -r skills/thinking ~/.agents/skills/thinking
cp -r skills/teamwork ~/.agents/skills/teamwork
```

(Add the other units the same way as needed.)

Invoke explicitly with `$teamwork` (or the `/skills` command), or
let Codex select a skill implicitly when a task matches its description. You
can also reference the skills from your `AGENTS.md` (for example "load
`teamwork` before any multi-agent or review work") so they activate
by default.

### ChatGPT (web) and assistants without native skill support

No native `SKILL.md` mechanism. Attach the `SKILL.md` files you want to a
Project and add instruction lines such as: "Before any multi-step or review
work, read and apply the attached teamwork and thinking
files. When a fixed, authorized result needs an implementation decision, read
and keep the change minimum-sufficient. After a change, use an independent
Reviewer for the final state."

There is no automatic triggering on these surfaces, so tell the assistant
when to apply a skill, or bind it in the project instructions.

### Other agents (Cursor, VS Code agents, custom frameworks)

Anything that accepts a system prompt, rules file, or context file can run
these: point the agent at the skill files at session start, or paste the
files you need into the rules/system layer. The skills are plain
instructions, with no runtime and no dependencies.

---

## Enforcement Layer

The guards are separate from every plugin and skill-copy route above. Read each
guard's README before wiring it. The READMEs are the source of truth for support,
limits, configuration, and live checks.

### Destructive Guardian

The [Destructive Guardian](destructive-guardian/) is a Python
pre-execution hook. Copy its two Python files to your hook directory, add the
documented hook entry, and run its safe sentinel in a fresh session. It uses the
Python standard library and installs no packages.

### Change Guardian

The [Change Guardian](change-guardian/) is Rust source only in
version 4. No prebuilt binary or supported native target ships with this
release. Build it locally with a Rust toolchain:

```text
cargo build --manifest-path change-guardian/Cargo.toml --release --locked
```

Building does not install or activate the guard. Review the binary, copy it to
a directory you choose, then wire that exact path into your agent settings as a
separate manual action. The guard never edits agent settings.

## Instruction Layer activation: two modes

Installing puts the files where the agent can find them. On most surfaces the
agent still decides *whether* to load a skill by matching your request
against its description.

1. **Manual invoke (default).** Invoke by name, or rely on description
   matching. It needs no setup and works everywhere.
2. **Progressive loading (optional).** Wire a standing instruction or a small
   session router so the right skill loads on the right trigger every
   session. Full worked examples (a SessionStart hook, a router table, and
   the `CLAUDE.md` → `AGENTS.md` shim pattern) live in
   [activation/](activation/). They are example files. Nothing in this repo
   activates by cloning or installing. Activation begins only after you copy
   and wire an example yourself.

**The load receipt (all surfaces).** Whatever wiring you use, have the agent
state which skills it applied, in the first line of its first real response.
That one line makes activation verifiable instead of assumed. If the receipt
is missing or wrong, the wiring broke and you know immediately, before any
work was done under the wrong rules.

---

## Use the Instruction Layer

### What each one is for

- **Thinking**: the working method for a single agent. A
  five-stage loop (frame, ground, converge, execute, verify), anti-drift
  re-anchoring, and honesty mechanics (mark every claim verified, inferred,
  or unknown. Never present a guess in a confident register). Load it for
  any nontrivial task, with or without the constitution.
- **Teamwork**: the constitution. Defines four seats (Orchestrator,
  Pressure-Tester, Builder, Reviewer), a G0/G1/G2 governance dial, five
  non-negotiable gates (ground before drafting, converge before building,
  dispatch a full outcome contract, independent final-state review, done =
  owner-verified), role integrity (whoever assembled it doesn't approve it),
  and commit posture (workers never commit or push). Load it for any work
  that touches a repo, produces an artifact someone else consumes, or
  involves more than one agent.
- **Better Coding**: use after the outcome, acceptance evidence,
  scope, and authority are fixed. It compares implementation routes, selects
  the smallest ownership seam, and declines speculative concepts.
- **Plans**: planning discipline. A compact Plan Capsule,
  safe restoration of prior plan state, and a strict FINAL/GO separation: a
  settled plan never authorizes execution by itself.
- **Test the Test**: behavioral test evidence through public seams,
  mandatory failure-path coverage, fixture-versus-deployed divergence, and
  objective-integrity guidance for load-bearing tests and evaluators.
- **Ship or Fix**: the maximum-assurance convergence cycle. The
  acceptance oracle is frozen and certified before the candidate exists.
  Independent judges run it. A cold, fresh-context judge issues the final
  `SHIP`. Loads only on your explicit decision, never on task class alone.

### Recommended load order

Start with `thinking`. It stands alone. Add `teamwork`
(with `thinking`) when work needs governance or seat separation.
Load `better-coding` only after the outcome, acceptance evidence,
scope, and authority are fixed. Use `test-the-test` when tests are
written or reviewed. Load `ship-or-fix` only when you explicitly choose
maximum assurance. Independent review follows the change under
`teamwork`.

### Things to know

- **Skills are instructions, not enforcement.** They shape behavior. They
  don't technically prevent an agent from committing or approving. Pair them
  with real permissions (branch protection, read-only tokens) for anything
  that matters.
- **Progressive loading is intentional.** Reference files load only when
  their trigger fires (a failure, a delegation, an escalation). Do not paste
  them all into context up front. The structure exists to protect the
  context budget.
- **Adapt the vocabulary, keep the mechanisms.** Seat names, verdict labels,
  and return formats are conventions. Rename freely. The load-bearing parts
  are the separations: author ≠ approver, builder ≠ certifier, claim ≠
  verified claim.
- **Narrow the triggers to your workload.** The skill descriptions are
  deliberately broad (`thinking` offers to load on every
  nontrivial task). If you run a large skill inventory or a
  non-engineering workload, edit the `description:` frontmatter so it
  fires where you want it, for example "research, money decisions, and
  pre-publish checks", instead of everywhere. Narrowing a trigger is
  use, not misuse. The mechanisms do not change, only when they load.
- **Model-agnostic.** These run on any capable model. They were developed
  and are used daily across multiple vendors' models simultaneously.
