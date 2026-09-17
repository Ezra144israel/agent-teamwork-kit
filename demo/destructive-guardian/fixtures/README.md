# Synthetic capture fixtures

These files are synthetic. No Codex process produced them. They model the
`codex exec --json` event lines that the capture harness parses so the trace
builder and the evidence validator can be tested without a live capture.

Placeholders in double braces are filled in by the tests with synthetic values
that the redaction step must remove. The tests build those values from
fragments so no private-shaped string sits in the repository.

| File | Models |
|---|---|
| `synthetic-unprotected.jsonl` | The unprotected profile: one command execution that prints the marker and then fails on the missing sentinel. |
| `synthetic-protected.jsonl` | The protected profile: a PreToolUse denial surfaced as text with no command execution. |
| `synthetic-stderr.txt` | Standard error lines that carry paths, an account detail, a token, and a session id. |

The live capture in Phase 2 proves the real event shape. These fixtures prove
only that the parser, redaction, and validator behave as specified.
