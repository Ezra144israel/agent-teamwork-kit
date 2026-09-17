# Version 4 source-only packaging

Version 4 contains source code only. It has no published binaries or supported
native targets. Cloning or building it does not install, wire, or activate the
guard.

## Planned release targets

Build and test each target on its native GitHub-hosted runner before listing it
as supported:

| Platform | Rust target | Artifact |
|---|---|---|
| Linux x86-64 | `x86_64-unknown-linux-gnu` | `change-guardian-linux-x86_64` |
| Linux ARM64 | `aarch64-unknown-linux-gnu` | `change-guardian-linux-aarch64` |
| macOS Intel | `x86_64-apple-darwin` | `change-guardian-macos-x86_64` |
| macOS Apple silicon | `aarch64-apple-darwin` | `change-guardian-macos-aarch64` |
| Windows x86-64 | `x86_64-pc-windows-msvc` | `change-guardian-windows-x86_64.exe` |

These rows are a future test plan. They are not current support claims. No row
is supported in version 4.

## Release automation

The release workflow should run only after a separate publication approval. For
each matrix row it must:

1. check out the accepted source identity.
2. install the pinned Rust toolchain and target.
3. run `cargo fmt --check`, `cargo test --all-targets`, and
   `cargo build --locked --release` on the native runner.
4. rename the single executable to the artifact name above.
5. produce a SHA-256 checksum with `sha256sum` or `shasum -a 256`.
6. upload the executable and checksum as workflow artifacts.
7. stop before creating a GitHub release until publication has its own gate.

The workflow must use `Cargo.lock` and fail if it changes. It must never run an
installer or edit an agent profile.

## Single-file installation

After a user verifies the checksum, installation is a copy of one executable to
a user-selected hook directory. Wiring that path into an agent's settings is a
separate manual action. The repository does not choose that directory and the
binary does not edit settings.

## Startup measurement

Measure a release binary, not `cargo run`. On each supported target, use a clean
disposable repository and run 30 warm invocations of:

```text
change-guardian check --contract /absolute/read-only/contract.json --repository /absolute/disposable/repo
```

Record median and p95 wall time, maximum resident memory, repository file count,
Git version, operating system, CPU, and binary size. Measure a clean state and a
1,000-file changed state. Do not claim a target until its measurements and
functional tests are attached to the release candidate.

## Dependency footprint

Runtime crates are `serde`, `serde_json`, and `sha2`, plus their locked
transitive dependencies. `tempfile` is test-only. The executable shells out only
to `git` and to the exact verification command sealed in the contract. It makes
no network calls.
