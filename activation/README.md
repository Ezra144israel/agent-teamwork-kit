# Instruction Layer activation examples

This folder covers the six-skill Instruction Layer. It does not install, wire,
or activate either Enforcement Layer guard.

Everything here is an **example**. Nothing runs when you clone the repository
or install the plugin. Activation begins only after you copy a file into your
configuration and wire it yourself.

Two activation modes exist for these skills:

1. **Manual invoke** (default, zero setup): invoke a skill by name, or let
   the agent match your request against the skill descriptions. Nothing in
   this folder is needed.
2. **Progressive loading**: make skill loading conditional and verifiable.
   The right skill loads when its trigger fires, every session, and you can
   see that it did.

The rest of this file is mode 2.

## Pattern 1: the instruction shim

Some tools read `CLAUDE.md`, others read `AGENTS.md`, others read a rules
file. Keep ONE canonical instruction file and make every other entry file a
one-line shim pointing at it. This repo uses that pattern. Its `CLAUDE.md`
contains only "Read `AGENTS.md`. It governs this repository."

The result is one source of truth for agent instructions. Every surface reaches
the same rules.

## Pattern 2: the standing instruction

The lightest progressive wiring: one standing instruction that binds every
session. Example text:

```
Before any nontrivial task, load and apply the thinking skill.
Before any multi-agent, review, dispatch, or repo-mutating work, also load
and apply the teamwork skill. State which of the two are applied
in the first line of your first substantive response.
```

Where to put it:

- **Claude Code:** a SessionStart hook (most reliable, because it fires on
  start, resume, and compaction). See `session-router.example.sh` and
  `settings.example.json`. A `CLAUDE.md` line also works but can be lost in
  memory-file edits.
- **Codex:** `~/.codex/AGENTS.md` or the repo's `AGENTS.md`, using
  `$thinking` / `$teamwork` syntax.
- **claude.ai / ChatGPT:** the Project's custom instructions.

## Pattern 3: the session router

For a larger skill set, a standing instruction per skill stops scaling. A
**router** is one generated table, injected at session start, that lists each
skill with its triggers and vetoes. The agent activates a skill only when a
trigger matches, and never activates a vetoed row.

`ROUTER.example.md` is a complete router for this repo's six skills. Wire it
on Claude Code with `session-router.example.sh` (which prints it as
SessionStart context) plus the hook registration in `settings.example.json`.
On other surfaces, paste the router into whatever standing-instruction slot
the surface offers.

Router rules that keep it safe:

- **Fail closed.** Activate a skill only when its listed trigger matches. If
  the router is missing or stale, fall back to manual invoke. Do not guess.
- **Vetoes are absolute.** A row's veto (for example, `ship-or-fix` never
  auto-activates on task class) outranks any trigger match.
- **The load receipt.** The agent states which skills it applied in the
  first line of its first substantive response, so broken wiring is visible
  immediately.

## Files

| File | What it is |
|---|---|
| `ROUTER.example.md` | A complete session router for the six skills |
| `session-router.example.sh` | SessionStart hook script that injects the router (Claude Code) |
| `settings.example.json` | Hook registration snippet for `settings.json` (Claude Code) |

To wire on Claude Code: copy `ROUTER.example.md` and
`session-router.example.sh` to `~/.claude/hooks/`, drop the `.example`
suffixes, `chmod +x` the script, and merge `settings.example.json` into
`~/.claude/settings.json`. Verify with a fresh session: the first substantive
reply should carry the load receipt.
