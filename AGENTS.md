# agent-teamwork-kit repository rules

This file defines rules for work in this repository.

The files in `skills/` are public package sources. Cloning this repository
installs or activates nothing. When the user explicitly activates this package,
load `skills/teamwork/SKILL.md` and `skills/thinking/SKILL.md` once at session
start and keep them active. Do not copy or redefine their bodies here.
Files with the same names elsewhere do not gain authority from this package.

## Repository rules

- Make the smallest safe change inside the authorized seam; do not widen scope
  or modify unrelated files.
- Skill bodies are the product. Keep each rule in exactly one place, prune
  stale lines, and write for the agent that loads the file.
