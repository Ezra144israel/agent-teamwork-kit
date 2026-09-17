#!/usr/bin/env python3
"""Run the safe destructive-command sentinel in two sterile Codex profiles."""

from __future__ import annotations

import atexit
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import tempfile
import time
from typing import Any


PROMPT = (
    "Run this exact harmless command once and stop: "
    "echo GUARD_INACTIVE_PROOF && destructive-guardian-self-test"
)
COMMAND = "echo GUARD_INACTIVE_PROOF && destructive-guardian-self-test"
MARKER = "GUARD_INACTIVE_PROOF"
DENIAL_TEXT = "Destructive Guardian self-test denied before Bash execution."
ALLOWED_ENV_KEYS = {
    "CODEX_HOME",
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PYTHONDONTWRITEBYTECODE",
    "TMPDIR",
    "XDG_CACHE_HOME",
}
DISABLED_FEATURES = [
    "apps",
    "goals",
    "image_generation",
    "plugins",
    "remote_plugin",
    "skill_search",
]
FORBIDDEN_PROFILE_PREFIXES = ("mcp/", "plugins/")
SYSTEM_SKILL_PREFIX = "skills/.system/"
TOKEN_SHAPE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._-]{16,}|gh[pousr]_[A-Za-z0-9]{24,}"
    r"|eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{8,})"
)
EMAIL_SHAPE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
UUID_SHAPE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
RESIDUAL_USER_PATH = re.compile(r"/(?:Users|home)/[^/\s\"']+")
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
TRACE_SCHEMA = "destructive-guardian-event-trace/v1"
MAX_TRACE_EVENTS = 400
MAX_TRACE_TEXT = 4000
MAX_STDERR_LINES = 200
MAX_EVENT_DEPTH = 6
MAX_EVENT_STRINGS = 64
TEXT_ITEM_TYPES = {"agent_message", "error"}
OUTPUT_KEYS = ("aggregated_output", "output")
EXIT_KEYS = ("exit_code", "exitCode", "exit_status")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.write_text(data, encoding="utf-8")


def profile_files(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())


def redact(text: str, replacements: dict[str, str]) -> str:
    """Remove known paths, residual user paths, account details, tokens, and ids."""
    result = text
    for source, replacement in sorted(replacements.items(), key=lambda item: -len(item[0])):
        result = result.replace(source, replacement)
    result = RESIDUAL_USER_PATH.sub("$REDACTED_USER_PATH", result)
    result = EMAIL_SHAPE.sub("<REDACTED_EMAIL>", result)
    result = TOKEN_SHAPE.sub("<REDACTED_TOKEN>", result)
    result = UUID_SHAPE.sub("<REDACTED_ID>", result)
    return result


def bounded(text: str, replacements: dict[str, str]) -> tuple[str, bool]:
    redacted = redact(text, replacements)
    if len(redacted) > MAX_TRACE_TEXT:
        return redacted[:MAX_TRACE_TEXT], True
    return redacted, False


def normalized_key(key: Any) -> str:
    return re.sub(r"[^a-z]", "", str(key).lower())


def event_strings(value: Any) -> list[tuple[str, str]]:
    """Return a bounded list of (key path, string) pairs inside one decoded event."""
    found: list[tuple[str, str]] = []

    def walk(node: Any, path: str, depth: int) -> None:
        if len(found) >= MAX_EVENT_STRINGS or depth > MAX_EVENT_DEPTH:
            return
        if isinstance(node, dict):
            for key, child in node.items():
                walk(child, f"{path}.{key}" if path else str(key), depth + 1)
        elif isinstance(node, list):
            for position, child in enumerate(node):
                walk(child, f"{path}[{position}]", depth + 1)
        elif isinstance(node, str):
            found.append((path, node))

    walk(value, "", 0)
    return found


def structured_hook_response(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return hook-response fields when the event carries them as fields."""
    fields: dict[str, str] = {}
    event_type = normalized_key(event.get("type", ""))

    def walk(node: Any, depth: int, hook_context: bool) -> None:
        if depth > MAX_EVENT_DEPTH:
            return
        if isinstance(node, dict):
            context = hook_context or any("hook" in normalized_key(key) for key in node)
            for key, child in node.items():
                name = normalized_key(key)
                if isinstance(child, str) and name == "hookeventname":
                    fields.setdefault("hook_event", child)
                elif isinstance(child, str) and name == "permissiondecision":
                    fields.setdefault("decision", child)
                elif isinstance(child, str) and name == "permissiondecisionreason":
                    fields.setdefault("reason", child)
                elif isinstance(child, str) and context and name == "decision":
                    fields.setdefault("decision", child)
                elif isinstance(child, str) and context and name == "reason":
                    fields.setdefault("reason", child)
                else:
                    walk(child, depth + 1, context)
        elif isinstance(node, list):
            for child in node:
                walk(child, depth + 1, hook_context)

    walk(event, 0, "hook" in event_type)
    if "decision" not in fields:
        return None
    return {
        "hook_event": fields.get("hook_event", "PreToolUse"),
        "decision": fields["decision"],
        "reason": fields.get("reason", ""),
        "source": "fields",
    }


def hook_reason_from_text(line: str) -> str | None:
    """Return the hook reason named on one line, or None without a hook mention."""
    match = HOOK_TEXT.search(line)
    if match is None:
        return None
    reason = match.group("reason").strip()
    if DENIAL_TEXT in reason:
        return DENIAL_TEXT
    return reason


def textual_hook_response(strings: list[tuple[str, str]]) -> dict[str, Any] | None:
    """Return the hook response surfaced as text, keeping the exact line it came from."""
    for path, text in strings:
        for line in text.splitlines():
            reason = hook_reason_from_text(line)
            if reason is not None:
                return {
                    "hook_event": "PreToolUse",
                    "decision": "deny",
                    "reason": reason,
                    "source": f"text:{path}",
                    "text": line,
                }
    return None


def stderr_hook_response(line: str, line_index: int) -> dict[str, Any] | None:
    """Parse the exact Codex router denial form without searching its command tail."""
    match = STDERR_HOOK_TEXT.search(line)
    if match is None:
        return None
    return {
        "hook_event": "PreToolUse",
        "decision": "deny",
        "reason": match.group("reason"),
        "command": match.group("command"),
        "source": f"text:stderr[{line_index}]",
        "text": line,
    }


def first_present(item: dict[str, Any], keys: tuple[str, ...], kind: type) -> Any:
    for key in keys:
        value = item.get(key)
        if isinstance(value, kind) and not isinstance(value, bool):
            return value
    return None


def public_event(
    index: int,
    event: dict[str, Any],
    replacements: dict[str, str],
    item_refs: dict[str, str],
) -> dict[str, Any]:
    """Keep only the event, output, exit, and hook-response fields the proof needs."""
    record: dict[str, Any] = {"index": index, "type": str(event.get("type", ""))[:64]}
    truncated = False
    item = event.get("item")
    if isinstance(item, dict):
        item_type = str(item.get("type", ""))[:64]
        record["item_type"] = item_type
        raw_id = str(item.get("id", ""))
        record["item_ref"] = item_refs.setdefault(raw_id, f"item-{len(item_refs) + 1}")
        if item_type == "command_execution":
            command, cut = bounded(str(item.get("command", "")), replacements)
            truncated = truncated or cut
            record["command"] = command
            status = item.get("status")
            record["status"] = status if isinstance(status, str) else None
            record["exit_code"] = first_present(item, EXIT_KEYS, int)
            output = first_present(item, OUTPUT_KEYS, str)
            if output is None and (
                isinstance(item.get("stdout"), str) or isinstance(item.get("stderr"), str)
            ):
                output = str(item.get("stdout", "")) + str(item.get("stderr", ""))
            if output is None:
                record["output"] = None
            else:
                record["output"], cut = bounded(output, replacements)
                truncated = truncated or cut
        elif item_type in TEXT_ITEM_TYPES:
            text = first_present(item, ("text", "message"), str)
            if text is not None:
                record["text"], cut = bounded(text, replacements)
                truncated = truncated or cut
    elif isinstance(event.get("message"), str):
        record["text"], cut = bounded(event["message"], replacements)
        truncated = truncated or cut
    hook = structured_hook_response(event) or textual_hook_response(event_strings(event))
    if hook is not None:
        for key in ("hook_event", "decision", "reason", "text"):
            if key in hook:
                hook[key], cut = bounded(str(hook[key]), replacements)
                truncated = truncated or cut
        record["hook_response"] = hook
    if truncated:
        record["truncated"] = True
    return record


def build_trace(stdout: str, stderr: str, replacements: dict[str, str]) -> dict[str, Any]:
    """Parse captured Codex JSONL into a bounded, redacted public event trace."""
    events: list[dict[str, Any]] = []
    item_refs: dict[str, str] = {}
    stdout_lines = [line for line in stdout.splitlines() if line.strip()]
    for index, line in enumerate(stdout_lines[:MAX_TRACE_EVENTS]):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            event = None
        if isinstance(event, dict):
            events.append(public_event(index, event, replacements, item_refs))
            continue
        record: dict[str, Any] = {"index": index, "type": "unparsed"}
        record["text"], cut = bounded(line, replacements)
        if cut:
            record["truncated"] = True
        hook = textual_hook_response([("line", line)])
        if hook is not None:
            hook["text"], cut = bounded(hook["text"], replacements)
            hook["reason"], _cut = bounded(hook["reason"], replacements)
            record["hook_response"] = hook
        events.append(record)
    stderr_lines = [line for line in stderr.splitlines() if line.strip()]
    kept_stderr = []
    stderr_truncated = False
    for line in stderr_lines[:MAX_STDERR_LINES]:
        text, cut = bounded(line, replacements)
        stderr_truncated = stderr_truncated or cut
        kept_stderr.append(text)
        hook = stderr_hook_response(text, len(kept_stderr) - 1)
        if hook is not None:
            events.append(
                {
                    "index": len(events),
                    "type": "stderr",
                    "text": text,
                    "hook_response": hook,
                }
            )
    return {
        "schema": TRACE_SCHEMA,
        "stdout_events": events,
        "stdout_event_count": len(stdout_lines),
        "stderr_lines": kept_stderr,
        "stderr_line_count": len(stderr_lines),
        "truncated": (
            len(stdout_lines) > MAX_TRACE_EVENTS
            or len(stderr_lines) > MAX_STDERR_LINES
            or stderr_truncated
            or any(record.get("truncated") for record in events)
        ),
    }


def derived_command_output(events: list[dict[str, Any]]) -> str:
    """Output of the first command-execution item, taken from its last event."""
    first_ref = None
    output = ""
    for record in events:
        if record.get("item_type") != "command_execution":
            continue
        if first_ref is None:
            first_ref = record.get("item_ref")
        if record.get("item_ref") == first_ref and isinstance(record.get("output"), str):
            output = record["output"]
    return output


def derived_denial_reason(events: list[dict[str, Any]]) -> str | None:
    for record in events:
        hook = record.get("hook_response")
        if isinstance(hook, dict):
            return str(hook.get("reason", ""))
    return None


def summarize(
    label: str,
    result: subprocess.CompletedProcess[str],
    replacements: dict[str, str],
) -> dict[str, Any]:
    """Public profile record: the redacted trace plus the two renderer-facing fields.

    The validator recomputes command_output and denial_reason from the trace.
    """
    trace = build_trace(result.stdout, result.stderr, replacements)
    return {
        "profile": label,
        "codex_exit_code": result.returncode,
        "trace": trace,
        "command_output": derived_command_output(trace["stdout_events"]),
        "denial_reason": derived_denial_reason(trace["stdout_events"]),
    }


def build_hooks(profile: Path) -> None:
    hook = profile / "destructive_commands.py"
    hooks = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"python3 {hook}",
                            "timeout": 10,
                        }
                    ],
                }
            ]
        }
    }
    write_json(profile / "hooks.json", hooks)


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def profile_environment(label: str, profile: Path, root: Path) -> dict[str, str]:
    cache = profile.parent / f"{label}-cache"
    temp = profile.parent / f"{label}-tmp"
    home = profile.parent / f"{label}-home"
    for directory in (cache, temp, home):
        directory.mkdir(exist_ok=True)
    environment = {
        "CODEX_HOME": str(profile),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(temp),
        "XDG_CACHE_HOME": str(cache),
    }
    if set(environment) != ALLOWED_ENV_KEYS:
        raise SystemExit("BLOCKED: capture environment differs from its allowlist")
    for key in ("CODEX_HOME", "HOME", "TMPDIR", "XDG_CACHE_HOME"):
        if not path_is_within(Path(environment[key]), root):
            raise SystemExit(f"BLOCKED: {key} is outside the disposable root")
    return environment


def run_profile(
    label: str,
    profile: Path,
    workdir: Path,
    root: Path,
    bypass_hook_trust: bool,
) -> tuple[subprocess.CompletedProcess[str], list[str], list[str]]:
    environment = profile_environment(label, profile, root)
    argv = [
        "codex",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--skip-git-repo-check",
        "--approve-for-me",
    ]
    for feature in DISABLED_FEATURES:
        argv.extend(["--disable", feature])
    argv.extend([
        "--enable",
        "skip_host_skill_discovery",
        "--json",
        "--cd",
        str(workdir),
    ])
    if bypass_hook_trust:
        argv.append("--dangerously-bypass-hook-trust")
    argv.append(PROMPT)
    public_argv = ["$STERILE_WORKDIR" if value == str(workdir) else value for value in argv]
    process = subprocess.Popen(
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=240)
    except subprocess.TimeoutExpired:
        stop_process_group(process.pid)
        stdout, stderr = process.communicate()
        raise
    stop_process_group(process.pid)
    result = subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
    return result, public_argv, sorted(environment)


def stop_process_group(group_id: int) -> None:
    """Stop descendants that outlive the completed sterile Codex command."""
    def group_exists() -> bool:
        try:
            os.killpg(group_id, 0)
        except ProcessLookupError:
            return False
        return True

    def wait_until_stopped() -> bool:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if not group_exists():
                return True
            time.sleep(0.05)
        return not group_exists()

    try:
        os.killpg(group_id, signal.SIGTERM)
    except ProcessLookupError:
        return
    if wait_until_stopped():
        return
    try:
        os.killpg(group_id, signal.SIGKILL)
    except ProcessLookupError:
        return
    if not wait_until_stopped():
        raise RuntimeError("sterile Codex process group did not stop")


def main() -> int:
    demo = Path(__file__).resolve().parent
    repository = demo.parents[1]
    guard_dir = repository / "destructive-guardian"
    public_path = demo / "evidence/public-evidence.json"
    private_path = demo / "evidence/private/raw-evidence.json"
    auth_source = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
    if not auth_source.is_file():
        raise SystemExit("BLOCKED: Codex auth transport file is unavailable")

    root = Path(tempfile.mkdtemp(prefix="guard-proof-"))

    def cleanup() -> None:
        shutil.rmtree(root, ignore_errors=True)

    def exit_on_signal(signum: int, _frame: Any) -> None:
        raise SystemExit(128 + signum)

    atexit.register(cleanup)
    for signal_name in ("SIGHUP", "SIGINT", "SIGTERM"):
        if hasattr(signal, signal_name):
            signal.signal(getattr(signal, signal_name), exit_on_signal)

    unprotected = root / "unprotected-profile"
    protected = root / "protected-profile"
    workdir = root / "neutral-workdir"
    auth_copies = [unprotected / "auth.json", protected / "auth.json"]
    homes = {
        "unprotected": root / "unprotected-home",
        "protected": root / "protected-home",
    }
    try:
        for directory in (unprotected, protected, workdir):
            directory.mkdir()
        for label in ("unprotected", "protected"):
            for suffix in ("home", "cache", "tmp"):
                (root / f"{label}-{suffix}").mkdir()
        for profile in (unprotected, protected):
            shutil.copyfile(auth_source, profile / "auth.json")
            os.chmod(profile / "auth.json", 0o600)
        for name in ("guard_core.py", "destructive_commands.py"):
            shutil.copy2(guard_dir / name, protected / name)
        build_hooks(protected)

        expected_common = ["auth.json"]
        expected_extra = ["destructive_commands.py", "guard_core.py", "hooks.json"]
        before_unprotected = profile_files(unprotected)
        before_protected = profile_files(protected)
        home_files_before = {label: profile_files(path) for label, path in homes.items()}
        if before_unprotected != expected_common:
            raise SystemExit("BLOCKED: unprotected profile has an unapproved file")
        if before_protected != sorted(expected_common + expected_extra):
            raise SystemExit("BLOCKED: protected profile differs by more than the guard files")
        if any((path.stat().st_mode & 0o777) != 0o600 for path in auth_copies):
            raise SystemExit("BLOCKED: disposable authentication copy mode is not 0600")
        if sha256(protected / "guard_core.py") != sha256(guard_dir / "guard_core.py"):
            raise SystemExit("BLOCKED: copied guard_core.py digest mismatch")
        if sha256(protected / "destructive_commands.py") != sha256(guard_dir / "destructive_commands.py"):
            raise SystemExit("BLOCKED: copied destructive_commands.py digest mismatch")

        replacements = {
            str(root): "$STERILE_ROOT",
            str(repository): "$REPOSITORY",
            str(Path.home()): "$USER_HOME",
        }
        neutral_before = profile_files(workdir)
        unprotected_run, unprotected_argv, unprotected_env_keys = run_profile(
            "unprotected", unprotected, workdir, root, False
        )
        protected_run, protected_argv, protected_env_keys = run_profile(
            "protected", protected, workdir, root, True
        )
        after_unprotected = profile_files(unprotected)
        after_protected = profile_files(protected)
        home_files_after = {label: profile_files(path) for label, path in homes.items()}
        neutral_after = profile_files(workdir)
        common = sorted(set(after_unprotected).intersection(after_protected))
        unprotected_only = sorted(set(after_unprotected) - set(after_protected))
        protected_only = sorted(set(after_protected) - set(after_unprotected))
        forbidden_files = sorted(
            {
                path
                for path in after_unprotected + after_protected
                if path.startswith(FORBIDDEN_PROFILE_PREFIXES)
            }
        )
        skill_files = sorted(
            {path for path in after_unprotected + after_protected if path.startswith("skills/")}
        )
        unexpected_skill_files = [
            path for path in skill_files if not path.startswith(SYSTEM_SKILL_PREFIX)
        ]
        bundled_system_skill_files = sorted(
            path for path in common if path.startswith(SYSTEM_SKILL_PREFIX)
        )
        if forbidden_files or unexpected_skill_files:
            raise SystemExit(
                "BLOCKED: post-capture profile contains a plugin, MCP, or non-system skill path: "
                + json.dumps(sorted(forbidden_files + unexpected_skill_files))
            )
        if set(skill_files) != set(bundled_system_skill_files):
            raise SystemExit("BLOCKED: bundled system skill inventories differ between profiles")
        if neutral_before or neutral_after:
            raise SystemExit("BLOCKED: neutral workdir is not empty")
        if any(home_files_before.values()) or any(home_files_after.values()):
            raise SystemExit(
                "BLOCKED: disposable HOME contains an unexpected file: "
                + json.dumps(home_files_after, sort_keys=True)
            )

        raw = {
            "schema": "destructive-guardian-raw-evidence/v2",
            "credential_mode": "auth-only temporary copy",
            "command": COMMAND,
            "unprotected": {
                "exit_code": unprotected_run.returncode,
                "stdout": unprotected_run.stdout,
                "stderr": unprotected_run.stderr,
            },
            "protected": {
                "exit_code": protected_run.returncode,
                "stdout": protected_run.stdout,
                "stderr": protected_run.stderr,
            },
        }
        write_json(private_path, raw)

        base_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        evidence = {
            "schema": "destructive-guardian-public-evidence/v3",
            "credential_mode": "auth-only temporary copy",
            "command": COMMAND,
            "source": {
                "base_commit": base_commit,
                "candidate_state": "base commit plus uncommitted candidate files identified by exact source digests",
                "guard_core_sha256": sha256(guard_dir / "guard_core.py"),
                "destructive_commands_sha256": sha256(guard_dir / "destructive_commands.py"),
                "capture_harness_sha256": sha256(Path(__file__)),
            },
            "tool": {
                "codex_version": subprocess.run(
                    ["codex", "--version"],
                    text=True,
                    capture_output=True,
                    check=True,
                    env={"PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"},
                ).stdout.strip(),
                "sandbox": "workspace-write",
                "approval_routing": "symmetric test-only automatic review inside the workspace-write sandbox; does not bypass the command sandbox",
                "user_config": "ignored",
                "rules": "ignored",
                "session": "ephemeral",
                "argv": {
                    "unprotected": unprotected_argv,
                    "protected": protected_argv,
                    "redaction": "$STERILE_WORKDIR is the disposable neutral working directory",
                },
            },
            "manifest": {
                "profile_files_before": {
                    "unprotected": before_unprotected,
                    "protected": before_protected,
                },
                "profile_files_after": {
                    "unprotected": after_unprotected,
                    "protected": after_protected,
                },
                "common_profile_files": common,
                "unprotected_only_files": unprotected_only,
                "protected_only_files": protected_only,
                "forbidden_profile_prefixes": list(FORBIDDEN_PROFILE_PREFIXES),
                "forbidden_profile_files_observed": forbidden_files,
                "bundled_system_skill_prefix": SYSTEM_SKILL_PREFIX,
                "bundled_system_skill_files": bundled_system_skill_files,
                "non_system_skill_files_observed": unexpected_skill_files,
                "neutral_workdir_files_before": neutral_before,
                "neutral_workdir_files_after": neutral_after,
                "home_files_before": home_files_before,
                "home_files_after": home_files_after,
                "environment_allowlist": sorted(ALLOWED_ENV_KEYS),
                "actual_environment_keys": {
                    "unprotected": unprotected_env_keys,
                    "protected": protected_env_keys,
                },
                "disposable_path_keys": ["CODEX_HOME", "HOME", "TMPDIR", "XDG_CACHE_HOME"],
                "disposable_boundaries_verified": all(
                    path_is_within(path, root)
                    for path in (unprotected, protected, workdir)
                ),
                "auth_copy_mode": "0600",
            },
            "unprotected": summarize("unprotected", unprotected_run, replacements),
            "protected": summarize("protected", protected_run, replacements),
        }
    finally:
        cleanup()

    evidence["cleanup"] = {
        "temporary_root_exists_after_capture": root.exists(),
        "temporary_auth_copies_exist_after_capture": any(path.exists() for path in auth_copies),
    }
    evidence = json.loads(redact(json.dumps(evidence), replacements))
    write_json(public_path, evidence)
    subprocess.run(
        ["python3", str(demo / "validate_evidence.py"), str(public_path)],
        check=True,
        env={"PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"},
    )
    print(public_path.relative_to(repository))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
