# Component decisions

## Rust enforcement core

Rust owns contract and envelope parsing, Git and repository identity, SHA-256
identity, path classification, policy evaluation, command execution, and
receipt generation and verification. These paths process untrusted data and
must behave the same on every supported surface. Rust provides memory-safe
parsing, one compiled executable, predictable exit codes, and a reusable core
for later guards.

## JSON contracts and envelopes

JSON is the wire format because Claude Code, Codex, and Antigravity already use
JSON hook envelopes. `serde` and `serde_json` provide strict typed parsing. The
contract parser rejects unknown fields instead of silently ignoring a spelling
error.

## SHA-256

The `sha2` crate owns content identity. A standard cryptographic digest is less
risky than a new in-project hash and is available on every Rust target in the
release plan.

## Git executable

The guard calls the repository's `git` executable. It does not reimplement Git
index, ignore, symlink, or submodule behavior. Tests exercise this real route in
disposable repositories.

## Non-Rust components

The candidate has no runtime component in another language. GitHub Actions YAML
and shell commands in the packaging guide are release orchestration, not policy
or enforcement. They use the platform's native packaging tools and never parse
or decide a containment result.
