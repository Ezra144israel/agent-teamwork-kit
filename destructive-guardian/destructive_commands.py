#!/usr/bin/env python3
"""Deny a small set of catastrophic Bash commands before your agent executes them.

This file is the surface adapter: it reads whatever payload shape the calling
agent sends, asks guard_core for a verdict, and writes that verdict back in the
shape that agent understands. The matching logic lives in guard_core.py and is
identical on every surface.

Supported envelopes are detected automatically from the payload:

  claude       Claude Code and Codex   tool_input.command            exit 0
  antigravity  Antigravity             toolCall.args.CommandLine     exit 0

Only surfaces confirmed working in a live session are listed. Others have been
implemented and removed again pending confirmation; see the git history.

Set DESTRUCTIVE_GUARDIAN_ENVELOPE to one of those names to skip detection.

Adding a surface means adding one entry to ENVELOPES below. Nothing in
guard_core.py should need to change.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path


# Loaded by path so the hook works regardless of cwd or sys.path. A missing
# guard_core.py raises loudly and on purpose: a guard that silently degrades to
# a no-op is worse than one that visibly fails, because you would go on
# believing you were protected.
_CORE_PATH = Path(__file__).with_name("guard_core.py")
_spec = importlib.util.spec_from_file_location("guard_core", _CORE_PATH)
guard_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard_core)


def _as_command_list(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return None


def _claude_extract(payload):
    """Claude Code and Codex: {"tool_input": {"command": ...}}"""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    return _as_command_list(tool_input.get("command"))


def _claude_render(reason):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _antigravity_extract(payload):
    """Antigravity PreToolUse: {"toolCall": {"args": {"CommandLine": ...}}}"""
    tool_call = payload.get("toolCall")
    if not isinstance(tool_call, dict):
        return None
    args = tool_call.get("args")
    if not isinstance(args, dict):
        return None
    return _as_command_list(args.get("CommandLine"))


def _antigravity_render(reason):
    return {"decision": "deny", "reason": reason}


# (name, extract, render, deny_exit_code)
#
# Order matters: most specific envelope first, so a payload that could satisfy
# two extractors is claimed by the narrower one.
#
# The deny exit code is part of each surface's contract rather than an
# implementation detail. Both surfaces here block on the JSON alone and want 0,
# but not every agent does — some treat a zero exit as "hook had no opinion" and
# run the command regardless of what the JSON said. Keep it per-envelope so that
# difference stays visible instead of being buried in a shared return.
ENVELOPES = (
    ("antigravity", _antigravity_extract, _antigravity_render, 0),
    ("claude", _claude_extract, _claude_render, 0),
)


def detect_envelope(payload):
    """Return (name, commands, render, deny_exit_code) for the first match."""
    forced = os.environ.get("DESTRUCTIVE_GUARDIAN_ENVELOPE")
    candidates = ENVELOPES
    if forced:
        candidates = tuple(item for item in ENVELOPES if item[0] == forced)

    for name, extract, render, deny_exit_code in candidates:
        commands = extract(payload)
        if commands is not None:
            return name, commands, render, deny_exit_code
    return None, [], None, 0


def trusted_cwd(payload, envelope_name):
    if envelope_name == "claude":
        value = payload.get("cwd")
    elif envelope_name == "antigravity":
        value = payload.get("toolCall", {}).get("args", {}).get("Cwd")
    else:
        value = None
    return value if isinstance(value, str) and value.startswith("/") else None


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, UnicodeError):
        return 0
    if not isinstance(payload, dict):
        return 0

    name, commands, render, deny_exit_code = detect_envelope(payload)
    if render is None:
        return 0

    for command in commands:
        reason = guard_core.denial_reason(command, cwd=trusted_cwd(payload, name))
        if reason:
            json.dump(render(reason), sys.stdout)
            sys.stdout.write("\n")
            return deny_exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
