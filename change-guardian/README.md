# Enforcement Layer: Change Guardian

The Instruction Layer tells agents how to work. `better-coding` helps
an agent choose the smallest useful change. This Enforcement Layer guard checks
the part that should not depend on judgment. It verifies that the final
repository state stayed inside an exact, sealed change contract.

The skill owns maintainability. The guard owns containment.

## What it proves

The Rust core binds a contract to one repository, branch, HEAD, and possibly
dirty baseline. It compares the final index and working tree with that baseline,
then classifies every added, deleted, or modified path as implementation, test,
evaluator, dependency, generated, or unclassified.

It handles tracked, staged, unstaged, untracked non-ignored files, symlinks, and
submodule pointers. Every initialized submodule must be clean before a snapshot
or receipt is accepted. This includes tracked and non-ignored untracked changes
inside an initialized nested submodule. A rename is reported as a deletion plus
an addition.
Wherever they appear, `.gitignore`, `.gitattributes`, and `.gitmodules` need
exact full-path rules. Symlink and submodule changes need their entry kinds
named. Dependency and generated paths need their matching classes. Test
suppression is checked in the named Rust, Python, JavaScript/TypeScript, Go,
Java/JUnit, and Ruby/RSpec ecosystems from the contract. A changed test-looking
path outside those declarations stops for human classification.

Ignored files are outside the state identity by design. Git decides whether a
file is ignored. A change to any `.gitignore` path remains protected.

## Files

| File | Purpose |
|---|---|
| `src/lib.rs` | Repository identity, contract, classification, receipt, and envelope core |
| `src/main.rs` | The single command-line and hook entry point |
| `contract.example.json` | Unsealed contract example. Copy it outside the candidate write scope before editing. |
| `COMPONENT-DECISIONS.md` | Benefit-based language and dependency decisions |
| `PACKAGING.md` | Source-only packaging boundary, planned targets, and measurement plan |
| `tests/` | Public-seam tests using disposable real Git repositories |

## Contract lifecycle

Keep the contract and receipt outside the agent's permitted repository write
scope. Start from `contract.example.json`, reduce it to the actual task, then
seal the baseline once:

```text
change-guardian seal --contract /evidence/contract.json --repository /work/repo
```

The seal writes repository identity, baseline state, suppression counts, and a
SHA-256 contract hash into the contract. A second seal is rejected.

Check containment without running tests:

```text
change-guardian check --contract /evidence/contract.json --repository /work/repo
```

Exit `0` means contained. Exit `10` means the JSON result contains violations.
Parse, file, Git, and contract failures exit `2`.

Run one command already sealed in `verification_commands` and write a receipt:

```text
change-guardian verify --contract /evidence/contract.json --receipt /evidence/receipt.json --repository /work/repo -- cargo test --all-targets
```

The guard checks containment before and after the command. One post-command
observation supplies both the containment decision and the receipt state. Test
file suppression counts and digests come from the same captured file bytes.
The receipt binds the repository, branch, contract hash, final state hash,
exact command, exit status, and exact stdout/stderr digest. Raw command output
is not copied into the receipt.

Stdout and stderr are drained concurrently. One combined counter stops at 16
MiB while the child runs. Output at the exact limit keeps the existing framed
digest. The next byte kills and reaps the direct child and no receipt is
written. Spawn failure, output-limit termination, child failure, and normal
empty output remain distinct results. Consumers recompute current state:

```text
change-guardian check-receipt --contract /evidence/contract.json --receipt /evidence/receipt.json --repository /work/repo
```

A replaced contract, changed branch, different repository, later edit, reused
receipt, or nonzero verification result is rejected. The receipt records command
output identity but does not authenticate or independently reproduce the output.
A receipt binds one post-command observation. It does not prove that an
arbitrary verification command read those exact bytes. A stronger test-to-byte
claim needs external quiescence or an exclusive writer across the command and
observation.
A changed receipt is rejected when its integrity hash no longer matches. A
writer who can replace both `output_digest` and the unkeyed `receipt_hash` is
outside this integrity claim.

## Agent envelopes

`envelope` reads one JSON object on standard input. It accepts the public
Claude Code/Codex shape with `tool_input` and `cwd`, and the public Antigravity
shape with `toolCall.args` and `toolCall.args.Cwd`. The same Rust policy runs for
all three surfaces. A violation is returned in each existing public guard's deny
shape and in `changeContainmentGuard` details.

```text
change-guardian envelope --contract /evidence/contract.json
```

These adapters are tested offline. This candidate does not claim that every
product invokes a post-change hook at the needed time. Live dispatch must be
proved in a disposable profile before a surface is called supported.

## Honest limits

The guard does not decide whether code is readable, whether an abstraction was
necessary, whether a test is useful, or whether the contract expresses the
right outcome. A broad contract can faithfully prove a weak boundary. The
author of the contract, an independent reviewer, and the operator still own
those decisions.

The guard does not observe repository-external Git exclude sources such as
`.git/info/exclude`, `core.excludesFile`, or global exclude files.

The contract and receipt hashes are integrity identities, not signatures. If an
agent can rewrite the contract, receipt, and acceptance process, this tool does
not create an independent authority boundary. Store evidence outside its write
scope.

The guard observes state when invoked. It is not a daemon and does not watch
future edits. A valid receipt becomes stale after any bound state changes.

The verification command has no wall-clock timeout in this version. Output
growth is bounded, but duration is not. Killing the direct child on an output
limit does not guarantee descendant cleanup on every platform.

Git and verification executables are selected through `PATH`, and child
processes inherit the current environment. Reopen executable pinning when the
subject under test can change `PATH` or that environment. Reopen process-group
cleanup and a wall-clock timeout before claiming bounded duration or descendant
termination.

Ignored files remain outside the state identity. An initialized submodule must
be clean, but ignored inner files are outside this check unless Git reports
them. A missing or malformed submodule status or HEAD fails closed.

## Install boundary

Version 4 is source-only. It contains no published binaries. The plugin does not
install this guard. Cloning, building, or testing this directory activates
nothing. The binary does not edit Claude Code, Codex, Antigravity, shell, Git,
or account settings. Build instructions are in `PACKAGING.md`. Copying a
reviewed binary and wiring an agent hook are separate manual actions.
