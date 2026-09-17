#!/usr/bin/env python3
"""Envelope tests: does the hook read each surface's payload and answer in that
surface's deny shape?

The matching logic is not retested here — test_guard_core.py owns that. These
tests use one obviously-destructive command and one obviously-safe one, and care
only about the wire format on each side.
"""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


HOOK = Path(__file__).with_name("destructive_commands.py")
CORE = Path(__file__).with_name("guard_core.py")

spec = importlib.util.spec_from_file_location("guard_core", CORE)
guard_core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard_core)

BLOCKED = "sudo rm -rf /System"
SAFE = "git status"

def _claude_deny_shape(out):
    block = out["hookSpecificOutput"]
    return (
        block["hookEventName"] == "PreToolUse"
        and block["permissionDecision"] == "deny"
        and bool(block["permissionDecisionReason"])
    )


# name -> (payload builder, deny-shape assertion, expected exit code on deny)
ENVELOPES = {
    "claude": (
        lambda command: {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
        },
        _claude_deny_shape,
        0,
    ),
    "antigravity": (
        lambda command: {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": command, "Cwd": "/tmp"},
            },
            "stepIdx": 0,
            "conversationId": "test",
        },
        lambda out: out["decision"] == "deny" and bool(out["reason"]),
        0,
    ),
}


def invoke(raw_input, env=None):
    merged = dict(os.environ)
    merged.pop("DESTRUCTIVE_GUARDIAN_ENVELOPE", None)
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=raw_input,
        text=True,
        capture_output=True,
        check=False,
        env=merged,
    )


class EnvelopeTests(unittest.TestCase):
    def test_each_envelope_denies_in_its_own_shape(self):
        for name, (build, is_deny, _code) in ENVELOPES.items():
            with self.subTest(envelope=name):
                result = invoke(json.dumps(build(BLOCKED)))
                self.assertEqual(result.stderr, "")
                self.assertTrue(result.stdout.strip(), "expected a deny payload")
                self.assertTrue(is_deny(json.loads(result.stdout)))

    def test_each_envelope_uses_its_own_deny_exit_code(self):
        # Both current surfaces block on the JSON and expect 0, but the code is
        # asserted per envelope because not every agent behaves that way. A
        # wrong code is the silent failure: correct denial text, command runs
        # anyway.
        for name, (build, _is_deny, expected_code) in ENVELOPES.items():
            with self.subTest(envelope=name):
                result = invoke(json.dumps(build(BLOCKED)))
                self.assertEqual(result.returncode, expected_code)

    def test_each_envelope_stays_silent_on_safe_commands(self):
        for name, (build, _is_deny, _code) in ENVELOPES.items():
            with self.subTest(envelope=name):
                result = invoke(json.dumps(build(SAFE)))
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")

    def test_forced_envelope_overrides_detection(self):
        # An Antigravity-shaped payload forced to the claude envelope finds no
        # tool_input, so it must fail open rather than guess at a deny format
        # the caller would not understand.
        payload = json.dumps(ENVELOPES["antigravity"][0](BLOCKED))
        result = invoke(payload, env={"DESTRUCTIVE_GUARDIAN_ENVELOPE": "claude"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

        # Forced to its own envelope it denies as normal.
        result = invoke(payload, env={"DESTRUCTIVE_GUARDIAN_ENVELOPE": "antigravity"})
        self.assertEqual(json.loads(result.stdout)["decision"], "deny")

    def test_claude_envelope_accepts_a_command_list(self):
        payload = json.dumps(
            {"tool_input": {"command": ["git status", BLOCKED]}}
        )
        result = invoke(payload)
        output = json.loads(result.stdout)
        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecision"], "deny"
        )

    def test_unrecognized_and_malformed_payloads_fail_open(self):
        cases = {
            "invalid-json": "not-json",
            "null": "null",
            "empty-object": "{}",
            "unknown-envelope": '{"someOtherAgent": {"cmd": "rm -rf /"}}',
            "missing-command": '{"tool_input": {}}',
            "wrong-command-type": '{"tool_input": {"command": 42}}',
            "antigravity-no-args": '{"toolCall": {"name": "run_command"}}',
            "bare-command-key": '{"command": "rm -rf /"}',
        }
        for name, raw_input in cases.items():
            with self.subTest(name=name):
                result = invoke(raw_input)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")

    def test_sentinel_denies_on_every_envelope(self):
        for name, (build, _is_deny, _code) in ENVELOPES.items():
            with self.subTest(envelope=name):
                result = invoke(
                    json.dumps(build(guard_core.SELF_TEST_SENTINEL))
                )
                self.assertTrue(result.stdout.strip())
                self.assertIn(
                    guard_core.SELF_TEST_REASON,
                    result.stdout,
                )

    def test_claude_envelope_binds_trusted_cwd(self):
        payload = ENVELOPES["claude"][0]("cd /Users && rm -rf *")
        payload["cwd"] = "/tmp"
        result = invoke(json.dumps(payload))
        self.assertEqual(
            json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )

    def test_antigravity_envelope_binds_trusted_cwd(self):
        payload = ENVELOPES["antigravity"][0]("rm -rf *")
        payload["toolCall"]["args"]["Cwd"] = "/Users"
        result = invoke(json.dumps(payload))
        self.assertEqual(json.loads(result.stdout)["decision"], "deny")



if __name__ == "__main__":
    unittest.main()
