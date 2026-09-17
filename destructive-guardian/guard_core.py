#!/usr/bin/env python3
"""Surface-independent matching logic for the Destructive Guardian.

This module knows nothing about any agent, hook protocol, or payload shape.
It takes a shell command string and returns a denial reason, or None.
Everything surface-specific lives in destructive_commands.py.

Keeping the split clean is the point: porting the guard to a new agent means
writing an envelope adapter, never touching this file.
"""

# SCOPE (accepted limitations — this is a targeted denylist, NOT a shell sandbox):
#   Guards only: recursive+force `rm` of / , /System(+descendants), all of
#   /Users(+globs), and the current $HOME; `diskutil erase*/partition*`; `mkfs*`;
#   and the self-test sentinel. Every other destructive operation is out of scope
#   by design and intentionally allowed — e.g. dd to a device, `find … -delete`,
#   newfs_*, `chmod/chown -R` on system roots, `> /dev/disk*`, and deletion of
#   /Library, /Applications, /usr, /etc.
#   This is not a faithful Bash parser. The documented simple-command grammar
#   is allowed; unsupported executable or protected-target expansion is denied
#   when it can hide a covered operation. Syntax outside the covered operations
#   remains outside this guard's decision.

import fnmatch
import os
import posixpath
import re
import shlex


ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", re.DOTALL)
BRACED_PARAMETER = re.compile(r"\$\{[^{}]+\}")
BRACED_DEFAULT = re.compile(
    r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::?[-=])([^{}]*)\}"
)
SIMPLE_PARAMETER = re.compile(
    r"\$(?:([A-Za-z_][A-Za-z0-9_]*)|\{([A-Za-z_][A-Za-z0-9_]*)\})"
)
GLOB_MAGIC = re.compile(r"[*?\[]")

RM_REASON = (
    "Never recursively force-delete the root filesystem, the current home "
    "directory, all user directories, or /System paths."
)
DISKUTIL_REASON = "Never erase or repartition a disk."
MKFS_REASON = "Never format a filesystem."
SELF_TEST_REASON = "Destructive Guardian self-test denied before Bash execution."
INSPECTION_LIMIT_REASON = (
    "Nested shell command exceeds the destructive-command inspection limit."
)
DYNAMIC_COMMAND_REASON = "Dynamic nested shell command cannot be safely inspected."
UNSUPPORTED_SYNTAX_REASON = (
    "Shell syntax that can hide a covered destructive command cannot be safely inspected."
)
AMBIGUOUS_DIRECTORY_REASON = (
    "A recursive forced deletion after a dynamic directory change cannot be safely inspected."
)

SELF_TEST_SENTINEL = "destructive-guardian-self-test"

# PROTECTED_ROOTS: the root itself is protected, and so is any glob under it
# (`/Users/*`), but a named descendant is allowed — `rm -rf /Users/you/project`
# is your own project, and that is what backups are for.
#
# SEALED_ROOTS: every descendant is protected, named or not. `/System/Library`
# is denied outright.
#
# The two are deliberately not symmetric. On Linux you would likely add "/home"
# to PROTECTED_ROOTS and "/etc", "/usr", "/boot" to SEALED_ROOTS — then add
# matching cases to test_guard_core.py and rerun before trusting it.
PROTECTED_ROOTS = ("/Users", "/System")
SEALED_ROOTS = ("/System",)

SHELL_EXECUTABLES = {"bash", "dash", "ksh", "sh", "zsh"}
SHELL_OPTIONS_WITH_VALUE = {"-O", "-o", "--init-file", "--rcfile"}
MAX_NESTED_COMMAND_DEPTH = 8
TIME_OPTIONS_WITH_VALUE = {"-f", "-o", "--format", "--output"}
NICE_OPTIONS_WITH_VALUE = {"-n", "--adjustment"}
EXEC_OPTIONS_WITH_VALUE = {"-a"}

SUDO_OPTIONS_WITH_VALUE = {
    "-C",
    "-D",
    "-g",
    "-h",
    "-p",
    "-R",
    "-T",
    "-t",
    "-u",
    "--chdir",
    "--close-from",
    "--group",
    "--host",
    "--other-user",
    "--prompt",
    "--role",
    "--type",
    "--user",
}
ENV_OPTIONS_WITH_VALUE = {"-C", "-u", "--chdir", "--unset"}


def split_segments(command):
    """Split only on unquoted top-level shell separators.

    The scanner is intentionally smaller than Bash. It preserves quoted nested
    scripts as one simple-command argument and reports lexical errors to the
    caller instead of silently dropping a fragment.
    """
    segments = []
    current = []
    preceding_separator = None
    quote = None
    escaped = False
    parenthesis_depth = 0
    index = 0
    while index < len(command):
        char = command[index]
        if escaped:
            current.append(char)
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            current.append(char)
            escaped = True
            index += 1
            continue
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
            index += 1
            continue
        if char == "(":
            parenthesis_depth += 1
            current.append(char)
            index += 1
            continue
        if char == ")" and parenthesis_depth:
            parenthesis_depth -= 1
            current.append(char)
            index += 1
            continue
        separator = None
        if parenthesis_depth == 0:
            if command.startswith(("&&", "||"), index):
                separator = command[index : index + 2]
            elif char in ";|&\r\n":
                separator = char
        if separator is not None:
            segment = "".join(current).strip()
            if segment:
                segments.append((segment, preceding_separator))
            current = []
            preceding_separator = separator
            index += len(separator)
            continue
        current.append(char)
        index += 1
    segment = "".join(current).strip()
    if segment:
        segments.append((segment, preceding_separator))
    return segments, quote is not None or escaped


def contains_covered_word(command):
    return bool(re.search(r"(^|[^A-Za-z0-9_.-])(rm|diskutil|mkfs(?:\.[^\s;|]+)?)(?=$|\s|[;|(){}])", command))


CONTROL_FLOW_PREFIX = re.compile(
    r"(?:if|then|elif|else|fi|for|while|until|do|done|case|esac|select)\b"
)
# Bash `!` pipeline negation, `coproc`, and both function declaration forms
# (`name() { ...; }` and `function name { ...; }`). Each puts a reserved word
# where the simple-command matcher expects the executable, so a covered
# operation behind it is denied instead of parsed.
FUNCTION_OR_PIPELINE_PREFIX = re.compile(
    r"!|coproc\b|function\b|[A-Za-z_][A-Za-z0-9_]*\s*\(\s*\)\s*\{"
)


def unsupported_compound(command):
    if not contains_covered_word(command):
        return False
    stripped = command.lstrip()
    return bool(
        stripped.startswith(("(", "{"))
        or CONTROL_FLOW_PREFIX.match(stripped)
        or FUNCTION_OR_PIPELINE_PREFIX.match(stripped)
    )


def balanced_parenthesized_body(command, open_index):
    depth = 0
    quote = None
    escaped = False
    for index in range(open_index, len(command)):
        char = command[index]
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return command[open_index + 1 : index], index, False
    return command[open_index + 1 :], len(command), True


def backtick_body(command, open_index):
    escaped = False
    for index in range(open_index + 1, len(command)):
        char = command[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == "`":
            return command[open_index + 1 : index], index, False
    return command[open_index + 1 :], len(command), True


def tokens_start_with_covered_executable(tokens):
    remaining, _assignments = strip_wrappers(tokens)
    if not remaining:
        return False
    executable = posixpath.basename(remaining[0]).lower()
    return (
        executable in {"rm", "diskutil"}
        or executable == "mkfs"
        or executable.startswith("mkfs.")
    )


def text_has_covered_operation(text):
    """Parse literal shell text and find a covered executable at command position."""
    segments, lexical_error = split_segments(text)
    for segment, _separator in segments:
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            return contains_covered_word(segment)
        if tokens_start_with_covered_executable(tokens):
            return True
    return lexical_error and contains_covered_word(text)


def tokens_contain_covered_literal(tokens):
    remaining, _assignments = strip_wrappers(tokens)
    if not remaining:
        return False
    return any(text_has_covered_operation(token) for token in remaining[1:])


def split_active_here_string(segment):
    quote = None
    escaped = False
    index = 0
    while index < len(segment):
        char = segment[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote:
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if segment.startswith("<<<", index):
            return segment[:index].strip(), segment[index + 3 :].strip()
        index += 1
    return None


def nested_body_denial(body, depth, inherited_assignments=None, cwd=None):
    """Inspect literal nested shell text with the same bounded classifier."""
    if depth >= MAX_NESTED_COMMAND_DEPTH:
        return INSPECTION_LIMIT_REASON
    if text_has_covered_operation(body):
        return UNSUPPORTED_SYNTAX_REASON
    nested_reason = denial_reason(
        body,
        depth + 1,
        inherited_assignments,
        cwd=cwd,
    )
    if nested_reason == INSPECTION_LIMIT_REASON:
        return nested_reason
    return UNSUPPORTED_SYNTAX_REASON if nested_reason else None


def substitution_denial(command, depth, inherited_assignments=None, cwd=None):
    """Return a reason when active substitution syntax hides a covered operation."""
    quote = None
    escaped = False
    index = 0
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote == "'":
            if char == "'":
                quote = None
            index += 1
            continue
        if char == "'" and quote is None:
            quote = "'"
            index += 1
            continue
        if char == '"':
            quote = None if quote == '"' else '"'
            index += 1
            continue
        if char == "`":
            body, end, malformed = backtick_body(command, index)
            reason = nested_body_denial(body, depth, inherited_assignments, cwd)
            if reason:
                return reason
            if malformed:
                return None
            index = end + 1
            continue
        marker = command[index : index + 2]
        active = marker == "$(" or (quote is None and marker in {"<(", ">("})
        if active:
            body, end, malformed = balanced_parenthesized_body(command, index + 1)
            reason = nested_body_denial(body, depth, inherited_assignments, cwd)
            if reason:
                return reason
            if malformed:
                return None
            index = end + 1
            continue
        index += 1
    return None


def is_shell_interpreter(tokens):
    remaining, _assignments = strip_wrappers(tokens)
    return bool(
        remaining
        and posixpath.basename(remaining[0]).lower() in SHELL_EXECUTABLES
    )


def has_dynamic_word_syntax(token):
    return bool(
        "$" in token
        or "`" in token
        or re.search(r"[?*\[]", token)
        or re.search(r"\{[^{}]*[,][^{}]*\}", token)
        or "<(" in token
        or ">(" in token
    )


def has_unsupported_target_syntax(token):
    if SIMPLE_PARAMETER.fullmatch(token):
        return False
    return bool(
        "$" in token
        or "`" in token
        or re.search(r"\{[^{}]*[,][^{}]*\}", token)
        or "<(" in token
        or ">(" in token
    )


def has_unsupported_executable_syntax(token):
    if SIMPLE_PARAMETER.fullmatch(token):
        return False
    return has_dynamic_word_syntax(token)


def consume_wrapper_options(tokens, options_with_value):
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return tokens[index + 1 :]
        if not token.startswith("-") or token == "-":
            break

        option_name = token.split("=", 1)[0]
        if option_name in options_with_value and "=" not in token:
            index += 2
        else:
            index += 1
    return tokens[index:]


def consume_env_options(tokens):
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return tokens[index + 1 :]
        if token in {"-S", "--split-string"}:
            if index + 1 >= len(tokens):
                return []
            try:
                split_tokens = shlex.split(tokens[index + 1], posix=True)
            except ValueError:
                return []
            return split_tokens + tokens[index + 2 :]
        if token.startswith("--split-string="):
            try:
                split_tokens = shlex.split(token.split("=", 1)[1], posix=True)
            except ValueError:
                return []
            return split_tokens + tokens[index + 1 :]
        if token.startswith("-S") and token != "-S":
            try:
                split_tokens = shlex.split(token[2:], posix=True)
            except ValueError:
                return []
            return split_tokens + tokens[index + 1 :]
        if not token.startswith("-") or token == "-":
            break

        option_name = token.split("=", 1)[0]
        if option_name in ENV_OPTIONS_WITH_VALUE and "=" not in token:
            index += 2
        else:
            index += 1
    return tokens[index:]


def consume_command_options(tokens):
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return tokens[index + 1 :]
        if not token.startswith("-") or token == "-":
            break
        flags = token[1:]
        if "v" in flags or "V" in flags:
            return []
        if any(flag != "p" for flag in flags):
            return []
        index += 1
    return tokens[index:]


def strip_wrappers(tokens, inherited_assignments=None):
    remaining = list(tokens)
    assignments = dict(inherited_assignments or {})
    while remaining:
        if ASSIGNMENT.match(remaining[0]):
            name, value = remaining[0].split("=", 1)
            assignments[name] = value
            remaining = remaining[1:]
            continue

        executable = posixpath.basename(remaining[0]).lower()
        if executable == "sudo":
            remaining = consume_wrapper_options(remaining, SUDO_OPTIONS_WITH_VALUE)
            continue

        if executable == "env":
            remaining = consume_env_options(remaining)
            continue

        if executable == "command":
            remaining = consume_command_options(remaining)
            continue

        if executable == "exec":
            remaining = consume_wrapper_options(remaining, EXEC_OPTIONS_WITH_VALUE)
            continue

        if executable == "nohup":
            remaining = consume_wrapper_options(remaining, set())
            continue

        # To trust additional wrapper commands of your own (loggers,
        # launchers), add clauses here following the pattern above.

        if executable == "time":
            remaining = consume_wrapper_options(remaining, TIME_OPTIONS_WITH_VALUE)
            continue

        if executable == "nice":
            remaining = consume_wrapper_options(remaining, NICE_OPTIONS_WITH_VALUE)
            continue

        break
    return remaining, assignments


def expand_known_parameters(value, assignments):
    def replacement(match):
        name = match.group(1) or match.group(2)
        if name in assignments:
            return assignments[name]
        return os.environ.get(name, match.group(0))

    return SIMPLE_PARAMETER.sub(replacement, value)


def split_expanded_token(token, assignments):
    expanded = expand_known_parameters(token, assignments)
    if expanded == token or not re.search(r"\s", expanded):
        return [expanded]
    try:
        words = shlex.split(expanded, posix=True)
    except ValueError:
        return [expanded]
    return words or [""]


def prepare_tokens(tokens, inherited_assignments=None):
    remaining, assignments = strip_wrappers(tokens, inherited_assignments)
    if not remaining:
        return [], assignments

    command_words = split_expanded_token(remaining[0], assignments)
    remaining = command_words + remaining[1:]
    remaining, assignments = strip_wrappers(remaining, assignments)
    if not remaining:
        return [], assignments

    executable = posixpath.basename(remaining[0]).lower()
    preserve_argument_words = executable in SHELL_EXECUTABLES or executable == "eval"
    expanded = [remaining[0]]
    for token in remaining[1:]:
        if preserve_argument_words:
            expanded.append(expand_known_parameters(token, assignments))
        else:
            expanded.extend(split_expanded_token(token, assignments))
    return expanded, assignments


def normalized_target(target):
    expanded = os.path.expandvars(os.path.expanduser(target))
    normalized = posixpath.normpath(expanded)
    if normalized.startswith("//"):
        return "/" + normalized.lstrip("/")
    return normalized


def target_candidates(target):
    candidates = {target}
    without_parameters = BRACED_PARAMETER.sub("", target)
    candidates.add(SIMPLE_PARAMETER.sub("", without_parameters))

    for match in BRACED_DEFAULT.finditer(target):
        with_default = target[: match.start()] + match.group(1) + target[match.end() :]
        without_braces = BRACED_PARAMETER.sub("", with_default)
        candidates.add(SIMPLE_PARAMETER.sub("", without_braces))

    return candidates


def is_protected_rm_target(target, cwd=None):
    home = posixpath.normpath(os.path.expanduser("~"))
    protected = {"/", home} | set(PROTECTED_ROOTS)

    # shlex preserves the leading dollar but not Bash ANSI-C quote markers.
    if target.startswith(("$/", "$\\")):
        return True
    if "$(" in target or "`" in target:
        return True

    for candidate in target_candidates(target):
        normalized = normalized_target(candidate)
        if cwd and not normalized.startswith("/"):
            normalized = posixpath.normpath(posixpath.join(cwd, normalized))
        if normalized == "/*" or normalized in protected:
            return True
        if normalized.startswith("/") and any(
            fnmatch.fnmatchcase(path, normalized) for path in protected
        ):
            return True
        if any(normalized.startswith(root + "/") for root in SEALED_ROOTS):
            return True
        if any(
            normalized.startswith(root + "/")
            and GLOB_MAGIC.search(normalized[len(root) + 1 :])
            for root in PROTECTED_ROOTS
        ):
            return True
    return False


def self_test_denial(tokens):
    if tokens == [SELF_TEST_SENTINEL]:
        return SELF_TEST_REASON
    return None


def rm_denial(tokens, raw_segment="", cwd=None, cwd_ambiguous=False):
    if not tokens or posixpath.basename(tokens[0]).lower() != "rm":
        return None

    recursive = False
    force = False
    targets = []
    parsing_options = True

    for token in tokens[1:]:
        if parsing_options and token == "--":
            parsing_options = False
            continue

        if parsing_options and token.startswith("--"):
            option = token.split("=", 1)[0]
            recursive = recursive or option == "--recursive"
            force = force or option == "--force"
            continue

        if parsing_options and token.startswith("-") and token != "-":
            flags = token[1:]
            recursive = recursive or "r" in flags or "R" in flags
            force = force or "f" in flags
            continue

        targets.append(token)

    if recursive and force:
        # Bash ANSI-C quoting is not decoded by shlex. Fail closed for the
        # entire quoting class only after this segment resolves to destructive rm.
        if "$'" in raw_segment:
            return RM_REASON
        if cwd_ambiguous and any(not normalized_target(target).startswith("/") for target in targets):
            return AMBIGUOUS_DIRECTORY_REASON
        if any(
            has_unsupported_target_syntax(target)
            for target in targets
        ):
            return UNSUPPORTED_SYNTAX_REASON
        if any(is_protected_rm_target(target, cwd) for target in targets):
            return RM_REASON
    return None


def diskutil_denial(tokens):
    if not tokens or posixpath.basename(tokens[0]).lower() != "diskutil":
        return None
    if len(tokens) > 1 and tokens[1].lower() in {
        "erasedisk",
        "erasevolume",
        "partitiondisk",
    }:
        return DISKUTIL_REASON
    return None


def mkfs_denial(tokens):
    if not tokens:
        return None
    executable = posixpath.basename(tokens[0]).lower()
    if executable == "mkfs" or executable.startswith("mkfs."):
        return MKFS_REASON
    return None


def nested_command(tokens):
    if not tokens:
        return None

    executable = posixpath.basename(tokens[0]).lower()
    if executable == "eval" and len(tokens) > 1:
        return " ".join(tokens[1:])
    if executable not in SHELL_EXECUTABLES:
        return None

    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return None
        if token in SHELL_OPTIONS_WITH_VALUE:
            index += 2
            continue
        if any(token.startswith(option + "=") for option in SHELL_OPTIONS_WITH_VALUE):
            index += 1
            continue
        if not token.startswith("-") or token == "-":
            return None
        if not token.startswith("--") and "c" in token[1:]:
            return tokens[index + 1] if index + 1 < len(tokens) else None
        index += 1
    return None


def directory_change(tokens):
    """Return a static directory target, or None for an ambiguous directory change."""
    if not tokens:
        return False, None
    remaining = tokens
    executable = posixpath.basename(remaining[0]).lower()
    if executable == "builtin":
        remaining = remaining[1:]
        if not remaining:
            return False, None
        executable = posixpath.basename(remaining[0]).lower()
    if executable not in {"cd", "pushd", "popd"}:
        return False, None
    if executable == "popd":
        return True, None
    if (
        len(remaining) != 2
        or has_dynamic_word_syntax(remaining[1])
        or remaining[1] == "-"
        or (executable == "pushd" and remaining[1].startswith(("+", "-")))
    ):
        return True, None
    return True, remaining[1]


def denial_reason(command, depth=0, inherited_assignments=None, cwd=None):
    """Return a denial reason string for `command`, or None to allow it."""
    reason = substitution_denial(command, depth, inherited_assignments, cwd)
    if reason:
        return reason
    if unsupported_compound(command):
        return UNSUPPORTED_SYNTAX_REASON
    segments, lexical_error = split_segments(command)
    if lexical_error and contains_covered_word(command):
        return UNSUPPORTED_SYNTAX_REASON
    active_assignments = dict(inherited_assignments or {})
    active_cwd = posixpath.normpath(cwd) if cwd else None
    cwd_ambiguous = False
    pipeline_contains_covered = False
    for segment, preceding_separator in segments:
        if preceding_separator != "|":
            pipeline_contains_covered = False
        if unsupported_compound(segment):
            return UNSUPPORTED_SYNTAX_REASON
        try:
            raw_tokens = shlex.split(segment, posix=True)
        except ValueError:
            if contains_covered_word(segment):
                return UNSUPPORTED_SYNTAX_REASON
            continue

        here_string = split_active_here_string(segment)
        if here_string is not None:
            interpreter_text, input_text = here_string
            try:
                interpreter_tokens = shlex.split(interpreter_text, posix=True)
                input_tokens = shlex.split(input_text, posix=True)
            except ValueError:
                if contains_covered_word(segment):
                    return UNSUPPORTED_SYNTAX_REASON
            else:
                if is_shell_interpreter(interpreter_tokens):
                    reason = nested_body_denial(
                        " ".join(input_tokens),
                        depth,
                        active_assignments,
                        active_cwd,
                    )
                    if reason:
                        return reason

        if (
            preceding_separator == "|"
            and pipeline_contains_covered
            and is_shell_interpreter(raw_tokens)
        ):
            return UNSUPPORTED_SYNTAX_REASON
        pipeline_contains_covered = (
            pipeline_contains_covered
            or contains_covered_word(segment)
            or tokens_contain_covered_literal(raw_tokens)
        )
        tokens = raw_tokens

        tokens, segment_assignments = prepare_tokens(tokens, active_assignments)
        if not tokens:
            active_assignments = segment_assignments
            continue
        executable_word = tokens[0]
        if has_unsupported_executable_syntax(executable_word):
            return DYNAMIC_COMMAND_REASON

        changed_directory, directory_target = directory_change(tokens)
        if changed_directory:
            if directory_target is None:
                cwd_ambiguous = True
                active_cwd = None
            elif directory_target.startswith("/"):
                active_cwd = posixpath.normpath(directory_target)
                cwd_ambiguous = False
            elif active_cwd:
                active_cwd = posixpath.normpath(
                    posixpath.join(active_cwd, directory_target)
                )
            else:
                cwd_ambiguous = True
            active_assignments = segment_assignments
            continue

        reason = rm_denial(tokens, segment, active_cwd, cwd_ambiguous)
        if reason:
            return reason
        for matcher in (self_test_denial, diskutil_denial, mkfs_denial):
            reason = matcher(tokens)
            if reason:
                return reason

        nested = nested_command(tokens)
        if nested is not None:
            if depth >= MAX_NESTED_COMMAND_DEPTH:
                return INSPECTION_LIMIT_REASON
            if SIMPLE_PARAMETER.search(nested) or "$(" in nested or "`" in nested:
                return DYNAMIC_COMMAND_REASON
            reason = denial_reason(
                nested,
                depth + 1,
                segment_assignments,
                cwd=active_cwd,
            )
            if reason:
                return reason
    return None
