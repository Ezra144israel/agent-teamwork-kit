#!/usr/bin/env python3
"""Validate public demo evidence from its redacted event trace.

Every chronology result is derived from the ordered trace that the capture
harness stored, never from a summary field. The two renderer-facing fields
(`command_output` and `denial_reason`) are recomputed from the trace and must
match, so a forged summary is rejected.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any


SCHEMA = "destructive-guardian-public-evidence/v3"
TRACE_SCHEMA = "destructive-guardian-event-trace/v1"
COMMAND = "echo GUARD_INACTIVE_PROOF && destructive-guardian-self-test"
MARKER = "GUARD_INACTIVE_PROOF"
SENTINEL = "destructive-guardian-self-test"
DENIAL_TEXT = "Destructive Guardian self-test denied before Bash execution."
MISSING_SENTINEL = re.compile(r"(?:command not found|not found|No such file)", re.IGNORECASE)
HOOK_TEXT = re.compile(
    r"(?:blocked by PreToolUse hook|PreToolUse hook (?:blocked|denied)[^:\n]*)[:\s-]*(?P<reason>[^\n]*)",
    re.IGNORECASE,
)
STDERR_HOOK_TEXT = re.compile(
    r"Command blocked by PreToolUse hook: (?P<reason>"
    + re.escape(DENIAL_TEXT)
    + r")\. Command: (?P<command>"
    + re.escape(COMMAND)
    + r")$"
)
TOKEN_SHAPE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._-]{16,}|gh[pousr]_[A-Za-z0-9]{24,}"
    r"|eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{8,})"
)
LOCAL_PATH = re.compile(r"/(?:Users|home)/[^/\s\"]+")
EMAIL_SHAPE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ACCOUNT_KEY = re.compile(r"\"[A-Za-z_]*(?:account|email|user_?id)[A-Za-z_]*\"\s*:", re.IGNORECASE)
BASE_COMMIT = re.compile(r"[0-9a-f]{40}")
ENVIRONMENT_KEYS = [
    "CODEX_HOME",
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PYTHONDONTWRITEBYTECODE",
    "TMPDIR",
    "XDG_CACHE_HOME",
]
PROMPT = (
    "Run this exact harmless command once and stop: "
    "echo GUARD_INACTIVE_PROOF && destructive-guardian-self-test"
)
DISABLED_FEATURES = [
    "apps",
    "goals",
    "image_generation",
    "plugins",
    "remote_plugin",
    "skill_search",
]
PROFILE_KEYS = {"profile", "codex_exit_code", "trace", "command_output", "denial_reason"}


def expected_argv(protected: bool) -> list[str]:
    result = [
        "codex",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--skip-git-repo-check",
        "--approve-for-me",
    ]
    for feature in DISABLED_FEATURES:
        result.extend(["--disable", feature])
    result.extend(["--enable", "skip_host_skill_discovery", "--json", "--cd", "$STERILE_WORKDIR"])
    if protected:
        result.append("--dangerously-bypass-hook-trust")
    result.append(PROMPT)
    return result


def privacy_problems(raw: str) -> list[str]:
    """Reject private-shaped text anywhere in the public file without echoing it."""
    problems = []
    if TOKEN_SHAPE.search(raw):
        problems.append("privacy: token-shaped text")
    if LOCAL_PATH.search(raw):
        problems.append("privacy: local user path")
    if EMAIL_SHAPE.search(raw) or ACCOUNT_KEY.search(raw):
        problems.append("privacy: account detail")
    return problems


def hook_reason_from_text(line: str) -> str | None:
    match = HOOK_TEXT.search(line)
    if match is None:
        return None
    reason = match.group("reason").strip()
    if DENIAL_TEXT in reason:
        return DENIAL_TEXT
    return reason


def stderr_hook_fields(line: str) -> tuple[str, str] | None:
    match = STDERR_HOOK_TEXT.search(line)
    if match is None:
        return None
    return match.group("reason"), match.group("command")


def hook_responses(events: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    found = []
    for record in events:
        hook = record.get("hook_response")
        if isinstance(hook, dict):
            found.append((int(record["index"]), hook))
    return found


def command_executions(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Ordered command-execution events grouped by item reference."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in events:
        if record.get("item_type") == "command_execution":
            grouped.setdefault(str(record.get("item_ref")), []).append(record)
    return grouped


def derived_command_output(events: list[dict[str, Any]]) -> str:
    output = ""
    for group in command_executions(events).values():
        for record in group:
            if isinstance(record.get("output"), str):
                output = record["output"]
        break
    return output


def derived_denial_reason(events: list[dict[str, Any]]) -> str | None:
    responses = hook_responses(events)
    if not responses:
        return None
    return str(responses[0][1].get("reason", ""))


def trace_form_problems(label: str, profile: Any) -> list[str]:
    problems = []
    if not isinstance(profile, dict):
        return [f"trace form: {label} profile record missing"]
    if profile.get("profile") != label:
        problems.append(f"trace form: {label} profile label mismatch")
    if set(profile) != PROFILE_KEYS:
        problems.append(f"trace form: {label} profile carries fields outside the trace contract")
    exit_code = profile.get("codex_exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        problems.append(f"trace form: {label} codex exit code missing")
    trace = profile.get("trace")
    if not isinstance(trace, dict):
        problems.append(f"trace form: {label} event trace missing")
        return problems
    if trace.get("schema") != TRACE_SCHEMA:
        problems.append(f"trace form: {label} trace schema mismatch")
    events = trace.get("stdout_events")
    if not isinstance(events, list) or not events:
        problems.append(f"trace form: {label} stdout events missing")
        return problems
    for position, record in enumerate(events):
        if not isinstance(record, dict) or record.get("index") != position or not isinstance(record.get("type"), str):
            problems.append(f"trace form: {label} event order or type is malformed")
            break
        hook = record.get("hook_response")
        if hook is not None and (
            not isinstance(hook, dict)
            or not all(isinstance(hook.get(key), str) for key in ("hook_event", "decision", "reason", "source"))
        ):
            problems.append(f"trace form: {label} hook response fields are malformed")
            break
    if not isinstance(trace.get("stderr_lines"), list) or not all(
        isinstance(line, str) for line in trace.get("stderr_lines", [])
    ):
        problems.append(f"trace form: {label} stderr lines are malformed")
    if trace.get("truncated") is not False:
        problems.append(f"trace form: {label} trace is truncated")
    return problems


def hook_response_problems(label: str, index: int, hook: dict[str, Any]) -> list[str]:
    """A hook response must be a PreToolUse deny whose exact reason its own text supports."""
    problems = []
    if hook.get("hook_event") != "PreToolUse" or hook.get("decision") != "deny":
        problems.append(f"{label}: hook response at event {index} is not a PreToolUse deny")
    if hook.get("reason") != DENIAL_TEXT:
        problems.append(f"{label}: hook reason mismatch at event {index}")
    source = str(hook.get("source", ""))
    if source.startswith("text:stderr["):
        fields = stderr_hook_fields(str(hook.get("text", "")))
        if fields != (hook.get("reason"), hook.get("command")):
            problems.append(f"{label}: stderr hook response text does not support its fields at event {index}")
        if hook.get("command") != COMMAND:
            problems.append(f"{label}: blocked command mismatch at event {index}")
    elif source.startswith("text:"):
        if hook_reason_from_text(str(hook.get("text", ""))) != hook.get("reason"):
            problems.append(f"{label}: hook response text does not support its fields at event {index}")
    elif source != "fields":
        problems.append(f"{label}: hook response source is unknown at event {index}")
    return problems


def unprotected_problems(profile: dict[str, Any]) -> list[str]:
    label = "unprotected chronology"
    problems = []
    events = profile["trace"]["stdout_events"]
    if hook_responses(events):
        problems.append(f"{label}: hook response present without a guard")
    groups = command_executions(events)
    if not groups:
        problems.append(f"{label}: no command execution item")
        return problems
    if len(groups) != 1:
        problems.append(f"{label}: more than one command execution item")
    for group in groups.values():
        if any(COMMAND not in str(record.get("command", "")) for record in group):
            problems.append(f"{label}: unexpected command executed")
    final = list(groups.values())[0][-1]
    exit_code = final.get("exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        problems.append(f"{label}: command exit code missing")
    elif exit_code == 0:
        problems.append(f"{label}: command exit code is zero although the sentinel is missing")
    output = final.get("output")
    if not isinstance(output, str):
        problems.append(f"{label}: command output missing")
        return problems
    marker_at = output.find(MARKER)
    failure = MISSING_SENTINEL.search(output)
    if marker_at < 0:
        problems.append(f"{label}: marker missing from command output")
    if failure is None or SENTINEL not in output:
        problems.append(f"{label}: missing-sentinel failure absent")
    if marker_at >= 0 and failure is not None and marker_at > failure.start():
        problems.append(f"{label}: marker printed after the failure")
    return problems


def protected_problems(profile: dict[str, Any]) -> list[str]:
    label = "protected denial chronology"
    problems = []
    trace = profile["trace"]
    events = trace["stdout_events"]
    executions = [record for record in events if record.get("item_type") == "command_execution"]
    responses = hook_responses(events)
    if executions:
        problems.append(f"{label}: command execution item present")
    if not responses:
        problems.append(f"{label}: PreToolUse hook response missing")
    else:
        if len(responses) != 1:
            problems.append(f"{label}: more than one PreToolUse hook response")
        first_index, first_hook = responses[0]
        problems.extend(hook_response_problems(label, first_index, first_hook))
        source = str(first_hook.get("source", ""))
        match = re.fullmatch(r"text:stderr\[(\d+)\]", source)
        if match is not None:
            stderr_index = int(match.group(1))
            stderr_lines = trace["stderr_lines"]
            if (
                stderr_index >= len(stderr_lines)
                or first_hook.get("text") != stderr_lines[stderr_index]
            ):
                problems.append(f"{label}: stderr hook response is not bound to its source line")
        if any(int(record["index"]) < first_index for record in executions):
            problems.append(f"{label}: denial recorded after execution")
    outputs = [record.get("output") for record in events if isinstance(record.get("output"), str)]
    # A hook denial diagnostic can quote the blocked command. Only command-item
    # output proves that the marker reached the shell.
    if any(MARKER in output for output in outputs):
        problems.append(f"{label}: marker appeared in output")
    return problems


def forged_summary_problems(label: str, profile: dict[str, Any]) -> list[str]:
    events = profile["trace"]["stdout_events"]
    problems = []
    if profile.get("command_output") != derived_command_output(events):
        problems.append(f"forged summary: {label} command_output differs from the trace")
    if profile.get("denial_reason") != derived_denial_reason(events):
        problems.append(f"forged summary: {label} denial_reason differs from the trace")
    return problems


def profile_problems(evidence: dict[str, Any]) -> list[str]:
    """Every chronology and summary result, derived only from the stored traces."""
    problems = []
    for label, checker in (("unprotected", unprotected_problems), ("protected", protected_problems)):
        profile = evidence.get(label)
        form = trace_form_problems(label, profile)
        if form:
            problems.extend(form)
            continue
        problems.extend(checker(profile))
        problems.extend(forged_summary_problems(label, profile))
    return problems


def manifest_problems(evidence: dict[str, Any]) -> list[str]:
    problems = []
    if evidence.get("schema") != SCHEMA:
        problems.append("schema")
    if evidence.get("credential_mode") != "auth-only temporary copy":
        problems.append("credential mode")
    if evidence.get("command") != COMMAND:
        problems.append("command")
    source = evidence.get("source", {})
    if not BASE_COMMIT.fullmatch(str(source.get("base_commit", ""))):
        problems.append("base commit identity")
    if "repository_commit" in source:
        problems.append("candidate mislabeled as a repository commit")
    if source.get("candidate_state") != "base commit plus uncommitted candidate files identified by exact source digests":
        problems.append("candidate state")
    tool = evidence.get("tool", {})
    argv = tool.get("argv", {})
    if argv.get("unprotected") != expected_argv(False):
        problems.append("unprotected argv")
    if argv.get("protected") != expected_argv(True):
        problems.append("protected argv")
    if tool.get("approval_routing") != "symmetric test-only automatic review inside the workspace-write sandbox; does not bypass the command sandbox":
        problems.append("approval routing disclosure")
    manifest = evidence.get("manifest", {})
    expected_unprotected = ["auth.json"]
    expected_protected = ["auth.json", "destructive_commands.py", "guard_core.py", "hooks.json"]
    before = manifest.get("profile_files_before", {})
    after = manifest.get("profile_files_after", {})
    if before.get("unprotected") != expected_unprotected:
        problems.append("pre-capture unprotected inventory")
    if before.get("protected") != expected_protected:
        problems.append("pre-capture protected inventory")
    if not all(isinstance(value, list) and value == sorted(set(value)) for value in after.values()):
        problems.append("post-capture inventory form")
    after_unprotected = set(after.get("unprotected", []))
    after_protected = set(after.get("protected", []))
    if manifest.get("common_profile_files") != sorted(after_unprotected & after_protected):
        problems.append("computed common profile files")
    if manifest.get("unprotected_only_files") != sorted(after_unprotected - after_protected):
        problems.append("computed unprotected profile files")
    if manifest.get("protected_only_files") != sorted(after_protected - after_unprotected):
        problems.append("computed protected profile files")
    if manifest.get("forbidden_profile_prefixes") != ["mcp/", "plugins/"]:
        problems.append("forbidden profile prefix policy")
    if manifest.get("forbidden_profile_files_observed") != []:
        problems.append("plugin or MCP profile path")
    if manifest.get("bundled_system_skill_prefix") != "skills/.system/":
        problems.append("bundled system skill prefix")
    bundled_skills = manifest.get("bundled_system_skill_files", [])
    if (
        not bundled_skills
        or bundled_skills != sorted(set(bundled_skills))
        or any(not path.startswith("skills/.system/") for path in bundled_skills)
        or set(bundled_skills) != {path for path in after_unprotected & after_protected if path.startswith("skills/")}
    ):
        problems.append("bundled system skill inventory")
    if manifest.get("non_system_skill_files_observed") != []:
        problems.append("non-system skill profile path")
    if manifest.get("neutral_workdir_files_before") != [] or manifest.get("neutral_workdir_files_after") != []:
        problems.append("neutral workdir inventory")
    empty_homes = {"protected": [], "unprotected": []}
    if manifest.get("home_files_before") != empty_homes or manifest.get("home_files_after") != empty_homes:
        problems.append("disposable HOME inventory")
    if manifest.get("environment_allowlist") != ENVIRONMENT_KEYS:
        problems.append("environment allowlist")
    if manifest.get("actual_environment_keys") != {
        "protected": ENVIRONMENT_KEYS,
        "unprotected": ENVIRONMENT_KEYS,
    }:
        problems.append("actual environment keys")
    if manifest.get("disposable_path_keys") != ["CODEX_HOME", "HOME", "TMPDIR", "XDG_CACHE_HOME"]:
        problems.append("disposable path keys")
    if manifest.get("disposable_boundaries_verified") is not True:
        problems.append("disposable boundary")
    if manifest.get("auth_copy_mode") != "0600":
        problems.append("authentication copy mode")
    cleanup = evidence.get("cleanup", {})
    if cleanup.get("temporary_root_exists_after_capture") is not False:
        problems.append("temporary root cleanup")
    if cleanup.get("temporary_auth_copies_exist_after_capture") is not False:
        problems.append("temporary authentication cleanup")
    return problems


def validate_evidence(raw: str) -> list[str]:
    problems = privacy_problems(raw)
    try:
        evidence = json.loads(raw)
    except json.JSONDecodeError:
        return problems + ["invalid JSON"]
    if not isinstance(evidence, dict):
        return problems + ["evidence is not an object"]
    problems.extend(manifest_problems(evidence))
    problems.extend(profile_problems(evidence))
    return problems


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_evidence.py PUBLIC_EVIDENCE_JSON")
    problems = validate_evidence(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if problems:
        for problem in problems:
            print(f"evidence validation failed: {problem}", file=sys.stderr)
        return 1
    print("public evidence valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
