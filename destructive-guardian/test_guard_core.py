#!/usr/bin/env python3
"""Regression tests for the surface-independent matching logic.

These call guard_core.denial_reason() directly. No agent, no payload, no
subprocess — if a case here fails, the guard is wrong on every surface at once.
Envelope handling is tested separately in test_adapters.py.
"""

import importlib.util
from pathlib import Path
import shlex
import unittest


CORE = Path(__file__).with_name("guard_core.py")
spec = importlib.util.spec_from_file_location("guard_core", CORE)
guard_core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard_core)

# Built from inert fragments so no test string is ever a runnable shell line.
COVERED = " ".join(("rm", "-rf", "/"))

BLOCKED_COMMANDS = {
    "sentinel": guard_core.SELF_TEST_SENTINEL,
    "rm-short": "rm -rf /",
    "rm-reordered-short": "rm -fr /*",
    "rm-split-flags": "rm -r -f ~",
    "rm-reversed-split": "rm -f -r $HOME",
    "rm-long": "rm --recursive --force /Users",
    "rm-reordered-long": "rm --force --recursive /System",
    "rm-double-slash": "rm -rf //",
    "rm-traversal": "rm -rf /tmp/..",
    "rm-unset-absolute": "rm -rf /$GUARD_HOOK_DEFINITELY_UNSET",
    "rm-default-absolute": "rm -rf ${GUARD_HOOK_DEFINITELY_UNSET:-/Users}",
    "rm-empty-assignment": "EMPTY= rm -rf /$EMPTY",
    "rm-command-substitution": "rm -rf $(printf /)",
    "rm-users-glob": "rm -rf /U*sers",
    "rm-system-glob": "rm -rf /System/*",
    "rm-system-descendant": "rm -rf /System/Library",
    "rm-ansi-users": "rm -rf $'/Users'",
    "rm-ansi-concatenated-system": "rm -rf $'/Sys''tem'",
    "rm-ansi-hex-users": r"rm -rf $'\x2fUsers'",
    "rm-ansi-embedded-users": r"rm -rf /Use$'\x72's",
    "rm-ansi-adjacent-embedded-users": r"rm -rf /Use$'\x72'$'\x73'",
    "rm-ansi-embedded-system": r"rm -rf /Sys$'\x74'em",
    "rm-ansi-traversal-users": r"rm -rf /Users$'\x2f'..$'\x2f'Users",
    "rm-ansi-sudo-wrapper": r"sudo rm -fr /Use$'\x72's",
    "rm-ansi-reordered-long": r"rm --force --recursive /Sys$'\x74'em",
    "rm-ansi-bash-nested": r'''bash -c "rm -rf /Use$'\x72's"''',
    "rm-ansi-eval-nested": r'''eval "rm -rf /Use$'\x72's"''',
    "sudo": "sudo -u root rm -rf /System",
    "env": "env FOO=bar rm -rf /",
    "env-split": "env -S \"bash -c 'rm -rf /'\"",
    "env-long-split": "env --split-string=\"bash -c 'rm -rf /'\"",
    "assignment": "FOO=bar rm -rf /",
    "command-wrapper": "command rm -rf /",
    "command-path-wrapper": "command -p rm -rf /",
    "nohup-wrapper": "nohup rm -rf /",
    "nohup-separator-wrapper": "nohup -- rm -rf /",
    "exec-wrapper": "exec rm -rf /",
    "exec-argv-wrapper": "exec -a cleanup rm -rf /",
    "nice-wrapper": "nice -n 5 rm -rf /Users",
    "time-wrapper": "time -p rm -rf /System",
    "semicolon": "echo ok; rm -rf /",
    "and": "true && sudo rm -fr /",
    "or": "false || env X=1 rm --force --recursive /System",
    "pipe": "echo ok | rm -rf /",
    "newline": "echo ok\nrm -rf /",
    "bash": "bash -c 'rm -rf /'",
    "bash-options": "bash -O extglob -c 'rm -rf /'",
    "sh": "sh -c 'rm -rf /System'",
    "zsh": "zsh -fc 'rm -rf /Users'",
    "dash": "dash -c 'rm -rf /'",
    "ksh": "ksh -c 'rm -rf /'",
    "eval": "eval 'rm -rf /'",
    "assigned-bash": "CMD='rm -rf /' bash -c \"$CMD\"",
    "assigned-direct": "CMD='rm -rf /' $CMD",
    "persisted-assignment": "CMD='rm -rf /'; $CMD",
    "expanded-target-list": "TARGET='/ /tmp/build' rm -rf $TARGET",
    "diskutil-erase-disk": "diskutil eraseDisk APFS Empty disk4",
    "diskutil-erase-volume": "sudo diskutil eraseVolume APFS Empty disk4s1",
    "diskutil-partition": "diskutil partitionDisk disk4 1 GPT APFS Empty 100%",
    "mkfs": "mkfs /dev/disk4",
    "mkfs-variant": "env X=1 mkfs.ext4 /dev/disk4",
    "quoted-nested-separator": r'''bash -c 'echo ok; rm -rf "$HOME"' ''',
    "substring-target": r'''rm -rf "${HOME:0}"''',
    "alternate-target": r'''rm -rf "${HOME:+/}"''',
    "brace-target": "rm -rf /{Users,System}",
    "ansi-executable": r"$'\\x72\\x6d' -rf /",
    "parameter-executable": r"x=xrm; ${x:1} -rf /",
    "command-substitution-executable": r"$(printf '%s' rm) -rf $HOME",
    "interpreter-pipe": r'''printf 'rm -rf "$HOME"' | bash''',
    "interpreter-here-string": r'''bash <<< 'rm -rf "$HOME"' ''',
    "subshell": r'''(rm -rf "$HOME")''',
    "function": r'''wipe() { rm -rf "$HOME"; }; wipe''',
    "control-flow": r'''if true; then rm -rf "$HOME"; fi''',
    "async-list": "echo hi & rm -rf /",
    "prefixed-subshell": "echo ok; (rm -rf /)",
    "prefixed-control-flow": "true && while :; do rm -rf /; done",
    "path-shell-pipe": "printf 'rm -rf /' | /bin/bash",
    "env-shell-pipe": "printf 'rm -rf /' | env bash",
    "argument-command-substitution": "echo $(rm -rf /)",
    "assignment-command-substitution": "x=$(rm -rf /)",
    "input-process-substitution": "cat <(rm -rf /)",
    "output-process-substitution": "cat >(rm -rf /)",
    "backtick-substitution": "echo `rm -rf /`",
    "unmatched-bracket-semicolon": "echo a[b ; rm -rf /",
    "unmatched-brace-semicolon": "echo a{b ; rm -rf /",
    "unmatched-bracket-and-if": "echo a[b && rm -rf /",
    "unmatched-bracket-newline": "echo a[b\nrm -rf /",
    "quoted-executable-dollar-substitution": 'echo $("rm" -rf /)',
    "single-quoted-executable-dollar-substitution": "echo $('rm' -rf /)",
    "quoted-executable-backticks": 'echo `"rm" -rf /`',
    "quoted-executable-process-substitution": 'cat <("rm" -rf /)',
    "quoted-executable-piped-to-shell": "printf '\"rm\" -rf /' | bash",
    "tight-here-string": "bash <<<'rm -rf /'",
    "attached-here-string": "bash<<<'rm -rf /'",
    "attached-sh-here-string": "sh<<<'rm -rf /'",
    "pushd-changes-directory": "pushd /Users && rm -rf *",
    "builtin-cd-changes-directory": "builtin cd /Users && rm -rf *",
    "popd-makes-directory-ambiguous": "popd && rm -rf build",
    "wrapped-builtin-cd-changes-directory": "command builtin cd /Users && rm -rf *",
    "nested-eval-dollar-substitution": "echo $(eval rm -rf /)",
    "nested-bash-dollar-substitution": "echo $(bash -c 'rm -rf /')",
    "nested-bash-backtick-substitution": "echo `bash -c 'rm -rf /'`",
    "nested-bash-process-substitution": "cat <(bash -c 'rm -rf /')",
    "nested-subshell-dollar-substitution": "echo $( (rm -rf /) )",
    "nested-control-flow-dollar-substitution": "echo $(if true; then rm -rf /; fi)",
    "nested-eval-here-string": "bash <<<'eval rm -rf /'",
    "nested-bash-here-string": "bash<<<'bash -c \"rm -rf /\"'",
    "negation-prefix": f"! {COVERED}",
    "negation-prefix-after-and": f"true && ! {COVERED}",
    "negation-prefix-subshell": f"! ({COVERED})",
    "coproc-prefix": f"coproc {COVERED}",
    "coproc-named-group": f"coproc wipe {{ {COVERED}; }}",
    "function-keyword": f"function wipe {{ {COVERED}; }}; wipe",
    "function-keyword-parenthesized": f"function wipe () {{ {COVERED}; }}; wipe",
    "function-spaced-parentheses": f"wipe ( ) {{ {COVERED}; }}; wipe",
    "nested-negation-bash": f"bash -c '! {COVERED}'",
    "nested-coproc-dollar-substitution": f"echo $(coproc {COVERED})",
    "nested-function-here-string": f"bash <<<'function wipe {{ {COVERED}; }}; wipe'",
}

SAFE_COMMANDS = {
    "ls": "ls",
    "git-status": "git status",
    "bare-star": "rm -rf *",
    "dot-star": "rm -rf ./*",
    "log-glob": "rm -rf *.log",
    "node-modules": "rm -rf ./node_modules",
    "tmp-build": "rm -rf /tmp/build",
    "home-project": "rm -rf ~/project",
    "specific-other-user-project": "rm -rf /Users/example/project",
    "recursive-only": "rm -r /",
    "force-only": "rm -f /",
    "diskutil-list": "diskutil list",
    "echo-mkfs": "echo mkfs /dev/disk4",
    "bash-safe": "bash -c 'git status'",
    "bash-safe-home": "bash -c 'echo $HOME'",
    "nested-safe-rm": "bash -c 'rm -rf ./node_modules'",
    "bash-option-safe": "bash -O extglob -c 'echo ok'",
    "env-split-safe": "env -S \"bash -c 'echo ok'\"",
    "eval-safe": "eval 'echo ok'",
    "command-query-safe": "command -v rm",
    "nice-safe": "nice -n 5 git status",
    "time-safe": "time -p git status",
    "safe-variable-target": "rm -rf $BUILD_DIR",
    "safe-assigned-targets": "TARGET='/tmp/a /tmp/b' rm -rf $TARGET",
    "nonpersistent-assignment": "CMD='rm -rf /' echo ok; $CMD",
    "unparseable-ordinary": "echo 'unterminated",
    "ansi-echo": r"echo $'\n'",
    "ansi-rm-recursive-only": r"rm -r /Use$'\x72's",
    "ansi-rm-force-only": r"rm -f /Use$'\x72's",
    "quoted-ampersand": "echo 'safe & rm -rf /'",
    "double-quoted-ampersand": 'echo "safe & still text"',
    "noncovered-async-list": "echo hi & git status",
    "noncovered-prefixed-subshell": "echo ok; (git status)",
    "noncovered-shell-pipe": "printf 'echo safe' | /bin/bash",
    "benign-command-substitution": "echo $(printf safe)",
    "quoted-command-substitution": "echo '$(rm -rf /)'",
    "ordinary-unmatched-bracket": "echo a[b",
    "ordinary-unmatched-brace": "echo a{b",
    "quoted-benign-substitution-executable": 'echo $("printf" safe)',
    "quoted-benign-executable-piped-to-shell": "printf '\"echo\" safe' | bash",
    "tight-safe-here-string": "bash<<<'echo safe'",
    "safe-pushd-directory": "pushd /tmp && rm -rf build",
    "safe-builtin-cd-directory": "builtin cd /tmp && rm -rf build",
    "safe-popd-absolute-target": "popd && rm -rf /tmp/build",
    "nested-safe-bash-substitution": "echo $(bash -c 'git status')",
    "nested-safe-eval-here-string": "bash<<<'eval echo safe'",
    "safe-negation": "! true",
    "safe-negation-grep": "! grep -q needle notes.txt",
    "safe-coproc": "coproc printf safe",
    "safe-coproc-named-group": "coproc worker { printf safe; }",
    "safe-function-keyword": "function okay { printf safe; }; okay",
    "safe-function-keyword-parenthesized": "function okay () { printf safe; }; okay",
    "safe-function-spaced-parentheses": "okay ( ) { printf safe; }; okay",
    "safe-nested-negation-bash": "bash -c '! true'",
}


class GuardCoreTests(unittest.TestCase):
    def test_blocked_commands_are_denied(self):
        for name, command in BLOCKED_COMMANDS.items():
            with self.subTest(name=name):
                self.assertIsNotNone(guard_core.denial_reason(command))

    def test_safe_commands_are_allowed(self):
        for name, command in SAFE_COMMANDS.items():
            with self.subTest(name=name):
                self.assertIsNone(guard_core.denial_reason(command))

    def test_nested_command_depth_is_bounded(self):
        nested = "rm -rf /"
        for _ in range(guard_core.MAX_NESTED_COMMAND_DEPTH + 2):
            nested = "bash -c " + shlex.quote(nested)
        self.assertEqual(
            guard_core.denial_reason(nested),
            guard_core.INSPECTION_LIMIT_REASON,
        )

    def test_nested_substitution_depth_is_bounded(self):
        nested = "rm -rf /"
        for _ in range(guard_core.MAX_NESTED_COMMAND_DEPTH + 2):
            nested = f"echo $({nested})"
        self.assertEqual(
            guard_core.denial_reason(nested),
            guard_core.INSPECTION_LIMIT_REASON,
        )

    def test_rm_reason_matches_declared_coverage(self):
        self.assertEqual(
            guard_core.denial_reason("rm -rf /System/Library"),
            guard_core.RM_REASON,
        )
        self.assertNotIn("macOS system files", guard_core.RM_REASON)

    def test_protected_and_sealed_roots_are_not_symmetric(self):
        # SEALED_ROOTS protect every descendant, named or not.
        for root in guard_core.SEALED_ROOTS:
            with self.subTest(root=root, kind="sealed"):
                self.assertIsNotNone(
                    guard_core.denial_reason(f"rm -rf {root}/anything")
                )

        # PROTECTED_ROOTS that are not sealed protect the root and globs under
        # it, but allow a named descendant — that is your own project.
        for root in guard_core.PROTECTED_ROOTS:
            if root in guard_core.SEALED_ROOTS:
                continue
            with self.subTest(root=root, kind="protected"):
                self.assertIsNotNone(guard_core.denial_reason(f"rm -rf {root}"))
                self.assertIsNotNone(guard_core.denial_reason(f"rm -rf {root}/*"))
                self.assertIsNone(
                    guard_core.denial_reason(f"rm -rf {root}/someone/project")
                )

    def test_self_test_sentinel_is_denied_with_its_own_reason(self):
        self.assertEqual(
            guard_core.denial_reason(guard_core.SELF_TEST_SENTINEL),
            guard_core.SELF_TEST_REASON,
        )

    def test_static_cwd_changes_bind_relative_targets(self):
        self.assertIsNotNone(
            guard_core.denial_reason("cd / && rm -rf System", cwd="/tmp")
        )
        self.assertIsNotNone(
            guard_core.denial_reason("cd /Users && rm -rf *", cwd="/tmp")
        )
        self.assertIsNone(
            guard_core.denial_reason("cd /tmp && rm -rf build", cwd="/tmp")
        )

    def test_dynamic_cwd_denies_later_recursive_forced_rm(self):
        self.assertIsNotNone(
            guard_core.denial_reason("cd \"$TARGET\" && rm -rf build", cwd="/tmp")
        )


if __name__ == "__main__":
    unittest.main()
