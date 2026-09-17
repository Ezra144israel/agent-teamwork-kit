# Security policy

## Report a vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do not
include live credentials, personal data, or a destructive proof of concept. A
minimal safe reproduction is enough.

If private reporting is unavailable, open a public issue that asks for a private
contact route. Do not put the vulnerability details in that issue.

## What the automated checks cover

The [Security checks workflow](.github/workflows/security.yml) runs on pull
requests, every push, manual requests, and a weekly schedule. For the
revision under test, it checks:

- the exact six-skill Instruction Layer and its progressive reference files;
- repository file modes, symlinks, submodules, and executable files;
- an exact allowlist for binary and generated media files;
- hidden bidirectional, zero-width, and unexpected control characters in text;
- plugin manifests and declared hook, MCP, install, and activation surfaces;
- external resource loads in the static Pages site;
- high-signal credential patterns without printing a matched value;
- the sterile demo evidence, media manifest, Pages links, and accessibility
  controls;
- Python tests, distribution tests, Rust formatting, Clippy, locked Rust tests,
  and `cargo-audit 0.22.2`.

The checker has safe temporary mutants for each repository rule. These mutants
prove that a failing example makes the check fail without changing the working
repository.

## What a green result does not prove

A green `Security checks` result means only that the named checks passed for
that revision. It does not mean that the repository is malware-free. It is not
a complete security audit. It does not prove that a guard is installed, wired,
or active in a live account. It does not prove safe live wiring. It does not
guarantee behavior after installation.

The plugin installs only the six **Instruction Layer** skills. It does not
install, wire, or activate either **Enforcement Layer** guard. Live wiring needs
its own sterile-profile proof on each host surface.

## Threat model and boundaries

The checks focus on accidental package growth, hidden executable behavior,
unsafe repository metadata, leaked credentials, unapproved binary bytes,
external page loads, and drift between public evidence and generated media.

The Destructive Guardian is a narrow pre-execution denylist, not a Bash
sandbox. The Change Guardian proves one observed repository state, not
the intent or quality of the contract. Read each guard README for its exact
supported grammar and remaining limits.

The final acceptance path still requires an independent Reviewer. Publication
and installation remain operator actions.
