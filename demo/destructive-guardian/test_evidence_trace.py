#!/usr/bin/env python3
"""Red-capable tests for the public event trace and the trace-derived validator.

The fixtures are synthetic JSONL. No test starts Codex, sends anything to a
network service, or runs a shell command.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest


DEMO = Path(__file__).resolve().parent
FIXTURES = DEMO / "fixtures"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, DEMO / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_capture = load("run_capture")
validate_evidence = load("validate_evidence")

# Synthetic private-shaped values, assembled from fragments so the repository
# itself never contains a path, address, token, or id of that shape.
STERILE_ROOT = "/private/tmp/guard-proof-synthetic"
USER_HOME = "/" + "Users" + "/synthetic-account"
EMAIL = "synthetic" + "@" + "example.invalid"
TOKEN = "sk" + "-" + "synthetic0123456789abcdef"
THREAD_ID = "-".join(("01234567", "89ab", "cdef", "0123", "456789abcdef"))
REPOSITORY = "/private/tmp/synthetic-repository"
REPLACEMENTS = {
    STERILE_ROOT: "$STERILE_ROOT",
    REPOSITORY: "$REPOSITORY",
    USER_HOME: "$USER_HOME",
}
SUBSTITUTIONS = {
    "{{STERILE_ROOT}}": STERILE_ROOT,
    "{{USER_HOME}}": USER_HOME,
    "{{EMAIL}}": EMAIL,
    "{{TOKEN}}": TOKEN,
    "{{THREAD_ID}}": THREAD_ID,
}
SYSTEM_SKILLS = [
    "skills/.system/.codex-system-skills.marker",
    "skills/.system/review-agent/SKILL.md",
]


def fixture(name: str) -> str:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    for placeholder, value in SUBSTITUTIONS.items():
        text = text.replace(placeholder, value)
    return text


def synthetic_result(stdout_name: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        ["synthetic"], 0, fixture(stdout_name), fixture("synthetic-stderr.txt")
    )


def synthetic_profile(label: str) -> dict:
    return run_capture.summarize(label, synthetic_result(f"synthetic-{label}.jsonl"), REPLACEMENTS)


def synthetic_evidence() -> dict:
    common = ["auth.json", "config.toml", *SYSTEM_SKILLS]
    protected_extra = ["destructive_commands.py", "guard_core.py", "hooks.json"]
    environment = list(validate_evidence.ENVIRONMENT_KEYS)
    return {
        "schema": validate_evidence.SCHEMA,
        "credential_mode": "auth-only temporary copy",
        "command": validate_evidence.COMMAND,
        "source": {
            "base_commit": "0" * 40,
            "candidate_state": "base commit plus uncommitted candidate files identified by exact source digests",
            "guard_core_sha256": "0" * 64,
            "destructive_commands_sha256": "0" * 64,
            "capture_harness_sha256": "0" * 64,
        },
        "tool": {
            "codex_version": "codex-cli 0.0.0",
            "sandbox": "workspace-write",
            "approval_routing": "symmetric test-only automatic review inside the workspace-write sandbox; does not bypass the command sandbox",
            "user_config": "ignored",
            "rules": "ignored",
            "session": "ephemeral",
            "argv": {
                "unprotected": validate_evidence.expected_argv(False),
                "protected": validate_evidence.expected_argv(True),
                "redaction": "$STERILE_WORKDIR is the disposable neutral working directory",
            },
        },
        "manifest": {
            "profile_files_before": {
                "unprotected": ["auth.json"],
                "protected": sorted(["auth.json", *protected_extra]),
            },
            "profile_files_after": {
                "unprotected": sorted(common),
                "protected": sorted(common + protected_extra),
            },
            "common_profile_files": sorted(common),
            "unprotected_only_files": [],
            "protected_only_files": sorted(protected_extra),
            "forbidden_profile_prefixes": ["mcp/", "plugins/"],
            "forbidden_profile_files_observed": [],
            "bundled_system_skill_prefix": "skills/.system/",
            "bundled_system_skill_files": sorted(SYSTEM_SKILLS),
            "non_system_skill_files_observed": [],
            "neutral_workdir_files_before": [],
            "neutral_workdir_files_after": [],
            "home_files_before": {"protected": [], "unprotected": []},
            "home_files_after": {"protected": [], "unprotected": []},
            "environment_allowlist": environment,
            "actual_environment_keys": {"protected": environment, "unprotected": environment},
            "disposable_path_keys": ["CODEX_HOME", "HOME", "TMPDIR", "XDG_CACHE_HOME"],
            "disposable_boundaries_verified": True,
            "auth_copy_mode": "0600",
        },
        "unprotected": synthetic_profile("unprotected"),
        "protected": synthetic_profile("protected"),
        "cleanup": {
            "temporary_root_exists_after_capture": False,
            "temporary_auth_copies_exist_after_capture": False,
        },
    }


def problems_for(evidence: dict) -> list:
    return validate_evidence.validate_evidence(json.dumps(evidence, indent=2, sort_keys=True))


def events_of(profile: dict) -> list:
    return profile["trace"]["stdout_events"]


class TraceBuilderTests(unittest.TestCase):
    def test_trace_redacts_paths_accounts_tokens_and_ids(self):
        for label in ("unprotected", "protected"):
            with self.subTest(label=label):
                raw = json.dumps(synthetic_profile(label))
                for secret in (STERILE_ROOT, USER_HOME, EMAIL, TOKEN, THREAD_ID):
                    self.assertNotIn(secret, raw)
                self.assertIn("$STERILE_ROOT", raw)
                self.assertIn("<REDACTED_EMAIL>", raw)
                self.assertIn("<REDACTED_TOKEN>", raw)
                self.assertIn("<REDACTED_ID>", raw)
                self.assertEqual(validate_evidence.privacy_problems(raw), [])

    def test_trace_keeps_command_execution_fields_in_order(self):
        events = events_of(synthetic_profile("unprotected"))
        self.assertEqual([record["index"] for record in events], list(range(len(events))))
        executions = [record for record in events if record.get("item_type") == "command_execution"]
        self.assertEqual(len(executions), 2)
        self.assertEqual({record["item_ref"] for record in executions}, {"item-1"})
        started, completed = executions
        self.assertEqual(started["type"], "item.started")
        self.assertIsNone(started["exit_code"])
        self.assertEqual(completed["type"], "item.completed")
        self.assertIn(validate_evidence.COMMAND, completed["command"])
        self.assertEqual(completed["exit_code"], 127)
        self.assertEqual(completed["status"], "completed")
        self.assertTrue(completed["output"].startswith(validate_evidence.MARKER))
        self.assertNotIn("hook_response", completed)

    def test_trace_records_hook_response_from_text_with_its_source_line(self):
        events = events_of(synthetic_profile("protected"))
        responses = [(record["index"], record["hook_response"]) for record in events if "hook_response" in record]
        self.assertEqual([index for index, _hook in responses], [2])
        first = responses[0][1]
        self.assertEqual(first["hook_event"], "PreToolUse")
        self.assertEqual(first["decision"], "deny")
        self.assertEqual(first["reason"], validate_evidence.DENIAL_TEXT)
        self.assertEqual(first["source"], "text:item.message")
        self.assertIn("blocked by PreToolUse hook", first["text"])
        self.assertFalse(any(record.get("item_type") == "command_execution" for record in events))

    def test_trace_records_structured_hook_response_fields(self):
        event = {
            "type": "hook.completed",
            "hook": {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": validate_evidence.DENIAL_TEXT,
                }
            },
        }
        record = run_capture.public_event(0, event, REPLACEMENTS, {})
        self.assertEqual(
            record["hook_response"],
            {
                "hook_event": "PreToolUse",
                "decision": "deny",
                "reason": validate_evidence.DENIAL_TEXT,
                "source": "fields",
            },
        )

    def test_trace_records_live_hook_denial_from_stderr_without_execution(self):
        stderr = (
            "ERROR router: Command blocked by PreToolUse hook: "
            f"{validate_evidence.DENIAL_TEXT}. Command: "
            f"echo {validate_evidence.MARKER} && destructive-guardian-self-test\n"
        )
        trace = run_capture.build_trace(
            '{"type":"thread.started"}\n', stderr, REPLACEMENTS
        )
        responses = [
            record["hook_response"]
            for record in trace["stdout_events"]
            if "hook_response" in record
        ]
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["source"], "text:stderr[0]")
        self.assertEqual(responses[0]["reason"], validate_evidence.DENIAL_TEXT)
        self.assertEqual(responses[0]["command"], validate_evidence.COMMAND)
        self.assertFalse(
            any(
                record.get("item_type") == "command_execution"
                for record in trace["stdout_events"]
            )
        )

    def test_validator_does_not_treat_marker_in_denial_stderr_as_execution(self):
        evidence = synthetic_evidence()
        protected = evidence["protected"]
        stderr = (
            "ERROR router: Command blocked by PreToolUse hook: "
            f"{validate_evidence.DENIAL_TEXT}. Command: "
            f"echo {validate_evidence.MARKER} && destructive-guardian-self-test\n"
        )
        protected.update(
            run_capture.summarize(
                "protected",
                subprocess.CompletedProcess(["synthetic"], 0, "", stderr),
                REPLACEMENTS,
            )
        )
        problems = validate_evidence.protected_problems(protected)
        self.assertEqual(problems, [])

    def test_validator_rejects_expected_reason_hidden_in_wrong_command(self):
        stderr = (
            "ERROR router: Command blocked by PreToolUse hook: Different reason. Command: "
            f"echo {validate_evidence.DENIAL_TEXT}\n"
        )
        protected = run_capture.summarize(
            "protected",
            subprocess.CompletedProcess(["synthetic"], 0, "", stderr),
            REPLACEMENTS,
        )
        problems = validate_evidence.protected_problems(protected)
        self.assertTrue(any("PreToolUse hook response missing" in problem for problem in problems), problems)

    def test_validator_rejects_wrong_blocked_command(self):
        stderr = (
            "ERROR router: Command blocked by PreToolUse hook: "
            f"{validate_evidence.DENIAL_TEXT}. Command: printf safe\n"
        )
        protected = run_capture.summarize(
            "protected",
            subprocess.CompletedProcess(["synthetic"], 0, "", stderr),
            REPLACEMENTS,
        )
        problems = validate_evidence.protected_problems(protected)
        self.assertTrue(any("PreToolUse hook response missing" in problem for problem in problems), problems)

    def test_trace_rejects_malformed_router_suffix(self):
        stderr = (
            "ERROR router: Command blocked by PreToolUse hook: "
            f"{validate_evidence.DENIAL_TEXT}. Command: "
            f"{validate_evidence.COMMAND} trailing-text\n"
        )
        protected = run_capture.summarize(
            "protected",
            subprocess.CompletedProcess(["synthetic"], 0, "", stderr),
            REPLACEMENTS,
        )
        problems = validate_evidence.protected_problems(protected)
        self.assertTrue(any("PreToolUse hook response missing" in problem for problem in problems), problems)

    def test_trace_keeps_only_type_for_unrelated_events(self):
        events = events_of(synthetic_profile("unprotected"))
        by_type = {record["type"]: record for record in events}
        self.assertEqual(set(by_type["turn.completed"]), {"index", "type"})
        self.assertEqual(set(by_type["thread.started"]), {"index", "type"})

    def test_trace_keeps_unparsed_lines_redacted(self):
        stdout = fixture("synthetic-unprotected.jsonl") + f"plain text {STERILE_ROOT}\n"
        trace = run_capture.build_trace(stdout, "", REPLACEMENTS)
        last = trace["stdout_events"][-1]
        self.assertEqual(last["type"], "unparsed")
        self.assertEqual(last["text"], "plain text $STERILE_ROOT")
        self.assertFalse(trace["truncated"])

    def test_trace_marks_truncation(self):
        long_line = json.dumps({"type": "item.completed", "item": {"id": "x", "type": "agent_message", "text": "a" * 5000}})
        trace = run_capture.build_trace(long_line + "\n", "", REPLACEMENTS)
        self.assertTrue(trace["truncated"])
        self.assertTrue(trace["stdout_events"][0]["truncated"])


class TraceValidatorTests(unittest.TestCase):
    def setUp(self):
        self.evidence = synthetic_evidence()

    def assert_problem(self, evidence: dict, phrase: str):
        problems = problems_for(evidence)
        self.assertTrue(any(phrase in problem for problem in problems), problems)

    def test_synthetic_trace_evidence_is_valid(self):
        self.assertEqual(problems_for(self.evidence), [])

    def test_v2_style_summary_without_trace_is_rejected(self):
        for label in ("unprotected", "protected"):
            self.evidence[label] = {
                "profile": label,
                "codex_exit_code": 0,
                "command_execution_observed": label == "unprotected",
                "command_output": "GUARD_INACTIVE_PROOF\n",
                "marker_in_command_output": label == "unprotected",
                "missing_sentinel_failure_observed": label == "unprotected",
                "pre_tool_use_denial_observed": label == "protected",
                "denial_reason": validate_evidence.DENIAL_TEXT if label == "protected" else None,
            }
        self.assert_problem(self.evidence, "trace form: unprotected profile carries fields outside")
        self.assert_problem(self.evidence, "trace form: protected event trace missing")

    def test_forged_unprotected_output_is_rejected(self):
        self.evidence["unprotected"]["command_output"] = "GUARD_INACTIVE_PROOF\nforged\n"
        self.assert_problem(self.evidence, "forged summary: unprotected command_output differs from the trace")

    def test_forged_protected_denial_reason_is_rejected(self):
        self.evidence["protected"]["denial_reason"] = "forged reason"
        self.assert_problem(self.evidence, "forged summary: protected denial_reason differs from the trace")

    def test_forged_unprotected_denial_reason_is_rejected(self):
        self.evidence["unprotected"]["denial_reason"] = validate_evidence.DENIAL_TEXT
        self.assert_problem(self.evidence, "forged summary: unprotected denial_reason differs from the trace")

    def test_forged_hook_fields_without_supporting_text_are_rejected(self):
        events = events_of(self.evidence["protected"])
        events[2]["hook_response"]["text"] = "Tool call completed normally."
        self.assert_problem(self.evidence, "hook response text does not support its fields")

    def test_hook_reason_mismatch_is_rejected(self):
        events = events_of(self.evidence["protected"])
        for record in events:
            hook = record.get("hook_response")
            if hook:
                hook["reason"] = "Some other reason."
                hook["text"] = "blocked by PreToolUse hook: Some other reason."
        self.evidence["protected"]["denial_reason"] = "Some other reason."
        self.assert_problem(self.evidence, "protected denial chronology: hook reason mismatch")

    def test_hook_allow_decision_is_rejected(self):
        events = events_of(self.evidence["protected"])
        events[2]["hook_response"]["decision"] = "allow"
        self.assert_problem(self.evidence, "is not a PreToolUse deny")

    def test_missing_hook_response_is_rejected(self):
        events = events_of(self.evidence["protected"])
        for record in events:
            record.pop("hook_response", None)
        self.evidence["protected"]["denial_reason"] = None
        self.assert_problem(self.evidence, "protected denial chronology: PreToolUse hook response missing")

    def test_duplicate_stderr_hook_response_is_rejected(self):
        events = events_of(self.evidence["protected"])
        duplicate = copy.deepcopy(events[2])
        duplicate["index"] = len(events)
        events.append(duplicate)
        self.assert_problem(self.evidence, "protected denial chronology: more than one PreToolUse hook response")

    def test_stderr_hook_source_line_mismatch_is_rejected(self):
        stderr = (
            "ERROR router: Command blocked by PreToolUse hook: "
            f"{validate_evidence.DENIAL_TEXT}. Command: {validate_evidence.COMMAND}"
        )
        protected = run_capture.summarize(
            "protected",
            subprocess.CompletedProcess(["synthetic"], 0, "", stderr),
            REPLACEMENTS,
        )
        protected["trace"]["stderr_lines"][0] = "different source line"
        evidence = synthetic_evidence()
        evidence["protected"] = protected
        self.assertTrue(
            any("stderr hook response is not bound to its source line" in problem for problem in problems_for(evidence))
        )

    def test_protected_execution_after_denial_is_rejected(self):
        events = events_of(self.evidence["protected"])
        execution = copy.deepcopy(events_of(self.evidence["unprotected"])[3])
        execution["index"] = len(events)
        execution["output"] = "harmless\n"
        events.append(execution)
        self.evidence["protected"]["command_output"] = "harmless\n"
        problems = problems_for(self.evidence)
        self.assertIn("protected denial chronology: command execution item present", problems)
        self.assertNotIn("protected denial chronology: denial recorded after execution", problems)

    def test_denial_recorded_after_execution_is_rejected(self):
        events = events_of(self.evidence["protected"])
        execution = copy.deepcopy(events_of(self.evidence["unprotected"])[3])
        events.insert(2, execution)
        for position, record in enumerate(events):
            record["index"] = position
        self.evidence["protected"]["command_output"] = execution["output"]
        problems = problems_for(self.evidence)
        self.assertIn("protected denial chronology: denial recorded after execution", problems)
        self.assertIn("protected denial chronology: command execution item present", problems)
        self.assertIn("protected denial chronology: marker appeared in output", problems)

    def test_marker_after_failure_is_rejected(self):
        events = events_of(self.evidence["unprotected"])
        reordered = "zsh:1: command not found: destructive-guardian-self-test\nGUARD_INACTIVE_PROOF\n"
        events[3]["output"] = reordered
        self.evidence["unprotected"]["command_output"] = reordered
        self.assert_problem(self.evidence, "unprotected chronology: marker printed after the failure")

    def test_missing_marker_is_rejected(self):
        events = events_of(self.evidence["unprotected"])
        output = "zsh:1: command not found: destructive-guardian-self-test\n"
        events[3]["output"] = output
        self.evidence["unprotected"]["command_output"] = output
        self.assert_problem(self.evidence, "unprotected chronology: marker missing from command output")

    def test_zero_exit_without_failure_is_rejected(self):
        events = events_of(self.evidence["unprotected"])
        events[3]["exit_code"] = 0
        self.assert_problem(self.evidence, "unprotected chronology: command exit code is zero")

    def test_unexpected_unprotected_command_is_rejected(self):
        events = events_of(self.evidence["unprotected"])
        extra = copy.deepcopy(events[3])
        extra["index"] = len(events)
        extra["item_ref"] = "item-9"
        extra["command"] = "/bin/zsh -lc 'ls'"
        events.append(extra)
        problems = problems_for(self.evidence)
        self.assertIn("unprotected chronology: more than one command execution item", problems)
        self.assertIn("unprotected chronology: unexpected command executed", problems)

    def test_hook_response_in_unprotected_run_is_rejected(self):
        events = events_of(self.evidence["unprotected"])
        events[4]["hook_response"] = copy.deepcopy(events_of(self.evidence["protected"])[2]["hook_response"])
        self.evidence["unprotected"]["denial_reason"] = validate_evidence.DENIAL_TEXT
        self.assert_problem(self.evidence, "unprotected chronology: hook response present without a guard")

    def test_leaked_local_path_is_rejected(self):
        self.evidence["protected"]["trace"]["stderr_lines"].append(f"config at {USER_HOME}/.codex/config.toml")
        self.assert_problem(self.evidence, "privacy: local user path")

    def test_leaked_account_detail_is_rejected(self):
        self.evidence["protected"]["trace"]["stderr_lines"].append(f"account {EMAIL}")
        self.assert_problem(self.evidence, "privacy: account detail")

    def test_account_key_is_rejected(self):
        self.evidence["tool"]["account_id"] = "synthetic"
        self.assert_problem(self.evidence, "privacy: account detail")

    def test_token_shaped_data_is_rejected(self):
        self.evidence["unprotected"]["trace"]["stderr_lines"].append(f"authorization {TOKEN}")
        self.assert_problem(self.evidence, "privacy: token-shaped text")

    def test_truncated_trace_is_rejected(self):
        self.evidence["unprotected"]["trace"]["truncated"] = True
        self.assert_problem(self.evidence, "trace form: unprotected trace is truncated")


if __name__ == "__main__":
    unittest.main()
