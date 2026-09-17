#!/usr/bin/env python3
"""Prove independent safe mutants are rejected without changing the candidate."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


MUTATIONS = (
    (
        "separator scanner",
        '        if char == "(":\n',
        '        if char in "({[":\n',
        1,
        "unmatched-bracket-semicolon",
    ),
    (
        "substitution detection",
        "        if active:\n",
        "        if False and active:\n",
        1,
        "quoted-executable-dollar-substitution",
    ),
    (
        "nested body recursion",
        "    nested_reason = denial_reason(\n",
        "    return None\n    nested_reason = denial_reason(\n",
        1,
        "nested-eval-dollar-substitution",
    ),
    (
        "interpreter input",
        "            or tokens_contain_covered_literal(raw_tokens)\n",
        "            or False\n",
        1,
        "quoted-executable-piped-to-shell",
    ),
    (
        "compound command",
        "        if unsupported_compound(segment):\n",
        "        if False and unsupported_compound(segment):\n",
        1,
        "prefixed-control-flow",
    ),
    (
        "directory state",
        "        changed_directory, directory_target = directory_change(tokens)\n",
        "        changed_directory, directory_target = False, None\n",
        1,
        "pushd-changes-directory",
    ),
    (
        "prefix and function grammar",
        "        or FUNCTION_OR_PIPELINE_PREFIX.match(stripped)\n",
        "        or False\n",
        1,
        "negation-prefix",
    ),
)


def copy_suite(source: Path, target: Path) -> None:
    for name in (
        "guard_core.py",
        "destructive_commands.py",
        "test_guard_core.py",
        "test_adapters.py",
    ):
        shutil.copyfile(source / name, target / name)


def check_mutant(source: Path, mutation) -> None:
    name, needle, replacement, expected_count, expected_failure = mutation
    with tempfile.TemporaryDirectory(prefix="destructive-guard-mutant-") as directory:
        target = Path(directory)
        copy_suite(source, target)
        core = target / "guard_core.py"
        text = core.read_text(encoding="utf-8")
        if text.count(needle) != expected_count:
            raise SystemExit(f"guard-mutant: {name} mutation seam changed")
        core.write_text(text.replace(needle, replacement), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                str(target),
                "-p",
                "test_*.py",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        output = result.stdout + result.stderr
        if result.returncode == 0:
            raise SystemExit(f"guard-mutant: {name} unsafe mutant passed")
        if expected_failure not in output:
            raise SystemExit(
                f"guard-mutant: {name} failed outside its intended behavior case"
            )


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / "destructive-guardian"
    for mutation in MUTATIONS:
        check_mutant(source, mutation)
    names = ", ".join(mutation[0] for mutation in MUTATIONS)
    print(f"guard-mutant: {len(MUTATIONS)} expected reds observed ({names})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
