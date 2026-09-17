#!/usr/bin/env python3
"""Repository-wide, fail-closed checks for the public package surface."""

from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys

from validate_site import validate_site


def load_evidence_validator():
    """The demo validator owns every trace-derived and privacy rule for the evidence."""
    path = Path(__file__).resolve().parents[1] / "demo/destructive-guardian/validate_evidence.py"
    spec = importlib.util.spec_from_file_location("validate_evidence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evidence_validator = load_evidence_validator()


CANONICAL_SKILLS = [
    "thinking",
    "teamwork",
    "better-coding",
    "plans",
    "test-the-test",
    "ship-or-fix",
]
PROGRESSIVE_REFERENCES = [
    "skills/thinking/references/escalation-and-retries.md",
    "skills/thinking/references/decomposition-and-delegation.md",
    "skills/thinking/references/failure-patterns.md",
    "skills/thinking/references/find-a-way.md",
    "skills/plans/references/blueprint.md",
    "skills/test-the-test/reference/objective-integrity.md",
]
EXECUTABLE_SURFACES = {
    "activation/session-router.example.sh",
    "destructive-guardian/destructive_commands.py",
    "destructive-guardian/guard_core.py",
    "demo/destructive-guardian/build_media.py",
    "demo/destructive-guardian/render_media.m",
    "demo/destructive-guardian/run_capture.py",
    "demo/destructive-guardian/validate_evidence.py",
}
SKIP_PARTS = {".git", "target", "__pycache__"}
BINARY_EXTENSIONS = {".mp4", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".wasm"}
PLUGIN_BEHAVIOR_KEYS = {"hooks", "hook", "mcp", "mcpservers", "commands", "agents"}
HIGH_SIGNAL_CREDENTIALS = [
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{24,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"Bearer[ \t]+[A-Za-z0-9._-]{24,}", re.IGNORECASE),
]
HIDDEN_CODEPOINTS = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A)) | {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF}


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            value.update(chunk)
    return value.hexdigest()


def git_proves_ancestor(root, base_commit):
    try:
        exists = subprocess.run(
            ["git", "cat-file", "-e", f"{base_commit}^{{commit}}"],
            cwd=root,
            capture_output=True,
            check=False,
        )
        if exists.returncode != 0:
            return False
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", base_commit, "HEAD"],
            cwd=root,
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return ancestry.returncode == 0


def repository_files(root):
    for path in sorted(Path(root).rglob("*")):
        relative = path.relative_to(root)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        if relative.parts[:4] == ("demo", "destructive-guardian", "evidence", "private"):
            continue
        if path.is_file() or path.is_symlink():
            yield path, relative.as_posix()


def nested_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key).lower()
            yield from nested_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_keys(child)


def check_distribution(root, problems):
    skills = sorted(
        path.parent.name
        for path in (root / "skills").glob("*/SKILL.md")
    )
    if skills != sorted(CANONICAL_SKILLS):
        problems.append("distribution: package must contain exactly the canonical six skills")
    for relative in PROGRESSIVE_REFERENCES:
        if not (root / relative).is_file():
            problems.append(f"distribution: missing progressive reference: {relative}")


def check_git_and_modes(root, files, problems, check_git):
    for path, relative in files:
        if path.is_symlink():
            problems.append(f"git-surface: symlink is not allowed: {relative}")
            continue
        if path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            problems.append(f"git-surface: executable file mode is not allowed: {relative}")
    gitmodules = root / ".gitmodules"
    if gitmodules.exists() and gitmodules.read_text(encoding="utf-8").strip():
        problems.append("git-surface: submodules are not allowed in this package")
    if not check_git or not (root / ".git").exists():
        return
    result = subprocess.run(
        ["git", "ls-files", "--stage", "-z"], cwd=root, capture_output=True, check=False
    )
    if result.returncode != 0:
        problems.append("git-surface: cannot read committed Git modes")
        return
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode = metadata.split(b" ", 1)[0].decode("ascii")
            relative = raw_path.decode("utf-8")
        except (ValueError, UnicodeError):
            problems.append("git-surface: malformed Git index record")
            continue
        if mode == "120000":
            problems.append(f"git-surface: committed symlink is not allowed: {relative}")
        elif mode == "160000":
            problems.append(f"git-surface: committed submodule is not allowed: {relative}")
        elif mode != "100644":
            problems.append(f"git-surface: unexpected committed mode {mode}: {relative}")


def load_allowlist(root, problems):
    path = root / "security/media-allowlist.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema") != "repository-media-allowlist/v1" or not isinstance(value.get("files"), dict):
            raise ValueError
        return value["files"]
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        problems.append("media: invalid media allowlist")
        return {}


def check_media(root, files, allowlist, problems):
    seen_binary = set()
    for path, relative in files:
        if path.is_symlink():
            continue
        sample = path.read_bytes()[:8192]
        binary = path.suffix.lower() in BINARY_EXTENSIONS or b"\0" in sample
        if binary:
            seen_binary.add(relative)
            if relative not in allowlist:
                problems.append(f"media: unapproved binary file: {relative}")
    for relative, expected in sorted(allowlist.items()):
        path = root / relative
        if not path.is_file():
            problems.append(f"media: allowlisted file is missing: {relative}")
        elif not re.fullmatch(r"[0-9a-f]{64}", str(expected)) or digest(path) != expected:
            problems.append(f"media: allowlisted hash mismatch: {relative}")
def check_text_and_credentials(root, files, allowlist, problems):
    for path, relative in files:
        if path.is_symlink() or relative in allowlist and path.suffix.lower() in BINARY_EXTENSIONS:
            continue
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"text: non-UTF-8 file is not approved as binary: {relative}")
            continue
        if any((ord(char) < 32 and char not in "\t\n\r") or ord(char) == 127 or ord(char) in HIDDEN_CODEPOINTS for char in text):
            problems.append(f"text: hidden or unexpected control character: {relative}")
        if any(pattern.search(raw) for pattern in HIGH_SIGNAL_CREDENTIALS):
            problems.append(f"credentials: high-signal credential pattern: {relative}")


def check_plugin_and_execution(root, files, problems):
    for relative in ("plugin.json", ".claude-plugin/plugin.json"):
        try:
            value = json.loads((root / relative).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            problems.append(f"plugin: invalid manifest: {relative}")
            continue
        if PLUGIN_BEHAVIOR_KEYS.intersection(nested_keys(value)):
            problems.append(f"plugin: executable behavior is not allowed in manifest: {relative}")
        if "installs skills only" not in value.get("description", "").lower():
            problems.append(f"plugin: skills-only boundary is missing: {relative}")
    executable_extensions = {".py", ".sh", ".js", ".mjs", ".ts", ".rs", ".m"}
    for path, relative in files:
        lower = relative.lower()
        behavior_named = any(term in lower for term in ("hook", "mcp", "install", "activation"))
        if behavior_named and path.suffix.lower() in executable_extensions and relative not in EXECUTABLE_SURFACES:
            problems.append(f"plugin: unapproved executable behavior surface: {relative}")
    for relative in EXECUTABLE_SURFACES:
        if not (root / relative).is_file():
            problems.append(f"plugin: declared executable surface is missing: {relative}")


def check_evidence(root, problems):
    evidence_path = root / "demo/destructive-guardian/evidence/public-evidence.json"
    try:
        raw = evidence_path.read_text(encoding="utf-8")
        evidence = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        problems.append("evidence: public evidence is invalid JSON")
        return
    problems.extend(f"evidence: {problem}" for problem in evidence_validator.privacy_problems(raw))
    if evidence.get("schema") != evidence_validator.SCHEMA:
        problems.append("evidence: public evidence schema changed")
    source = evidence.get("source", {})
    if not re.fullmatch(r"[0-9a-f]{40}", str(source.get("base_commit", ""))):
        problems.append("evidence: base commit identity is invalid")
    if "repository_commit" in source or source.get("candidate_state") != "base commit plus uncommitted candidate files identified by exact source digests":
        problems.append("evidence: candidate state identity is dishonest")
    if (root / ".git").exists() and not git_proves_ancestor(root, str(source.get("base_commit", ""))):
        problems.append("evidence: base commit is not an ancestor of candidate HEAD")
    prompt = (
        "Run this exact harmless command once and stop: "
        "echo GUARD_INACTIVE_PROOF && destructive-guardian-self-test"
    )
    argv_prefix = [
        "codex", "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
        "--skip-git-repo-check", "--approve-for-me",
    ]
    for feature in ("apps", "goals", "image_generation", "plugins", "remote_plugin", "skill_search"):
        argv_prefix.extend(["--disable", feature])
    argv_prefix.extend(["--enable", "skip_host_skill_discovery", "--json", "--cd", "$STERILE_WORKDIR"])
    argv = evidence.get("tool", {}).get("argv", {})
    if argv.get("unprotected") != argv_prefix + [prompt]:
        problems.append("evidence: unprotected argv changed")
    if argv.get("protected") != argv_prefix + ["--dangerously-bypass-hook-trust", prompt]:
        problems.append("evidence: protected argv changed")
    if evidence.get("tool", {}).get("approval_routing") != "symmetric test-only automatic review inside the workspace-write sandbox; does not bypass the command sandbox":
        problems.append("evidence: approval routing disclosure changed")
    codex_version = str(evidence.get("tool", {}).get("codex_version", ""))
    version_match = re.fullmatch(r"codex-cli ([0-9]+\.[0-9]+\.[0-9]+)", codex_version)
    if version_match is None:
        problems.append("evidence: Codex version identity is invalid")
    else:
        expected_version = version_match.group(1)
        for relative in ("destructive-guardian/README.md", "docs/index.html"):
            try:
                public_text = (root / relative).read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                problems.append(f"evidence: public Codex version file is missing: {relative}")
                continue
            public_versions = set(
                re.findall(r"\bCodex ([0-9]+\.[0-9]+\.[0-9]+)\b", public_text)
            )
            if public_versions != {expected_version}:
                problems.append(f"evidence: public Codex version mismatch: {relative}")
    manifest = evidence.get("manifest", {})
    expected_unprotected = ["auth.json"]
    expected_protected = ["auth.json", "destructive_commands.py", "guard_core.py", "hooks.json"]
    before = manifest.get("profile_files_before", {})
    after = manifest.get("profile_files_after", {})
    if before.get("unprotected") != expected_unprotected or before.get("protected") != expected_protected:
        problems.append("evidence: pre-capture profile inventory changed")
    after_unprotected = set(after.get("unprotected", []))
    after_protected = set(after.get("protected", []))
    if (
        manifest.get("common_profile_files") != sorted(after_unprotected & after_protected)
        or manifest.get("unprotected_only_files") != sorted(after_unprotected - after_protected)
        or manifest.get("protected_only_files") != sorted(after_protected - after_unprotected)
    ):
        problems.append("evidence: computed post-capture inventory changed")
    bundled_skills = manifest.get("bundled_system_skill_files", [])
    if (
        manifest.get("forbidden_profile_prefixes") != ["mcp/", "plugins/"]
        or manifest.get("forbidden_profile_files_observed") != []
        or manifest.get("bundled_system_skill_prefix") != "skills/.system/"
        or not bundled_skills
        or any(not path.startswith("skills/.system/") for path in bundled_skills)
        or set(bundled_skills) != {path for path in after_unprotected & after_protected if path.startswith("skills/")}
        or manifest.get("non_system_skill_files_observed") != []
    ):
        problems.append("evidence: plugin, MCP, or non-system skill profile path observed")
    environment_keys = ["CODEX_HOME", "HOME", "LANG", "LC_ALL", "PATH", "PYTHONDONTWRITEBYTECODE", "TMPDIR", "XDG_CACHE_HOME"]
    if manifest.get("environment_allowlist") != environment_keys or manifest.get("actual_environment_keys") != {
        "protected": environment_keys,
        "unprotected": environment_keys,
    }:
        problems.append("evidence: capture environment changed")
    if (
        manifest.get("neutral_workdir_files_before") != []
        or manifest.get("neutral_workdir_files_after") != []
        or manifest.get("home_files_before") != {"protected": [], "unprotected": []}
        or manifest.get("home_files_after") != {"protected": [], "unprotected": []}
        or manifest.get("disposable_boundaries_verified") is not True
        or manifest.get("auth_copy_mode") != "0600"
    ):
        problems.append("evidence: sterile profile boundary failed")
    cleanup = evidence.get("cleanup", {})
    if cleanup.get("temporary_root_exists_after_capture") is not False or cleanup.get("temporary_auth_copies_exist_after_capture") is not False:
        problems.append("evidence: disposable profile cleanup failed")
    problems.extend(f"evidence: {problem}" for problem in evidence_validator.profile_problems(evidence))
    sources = {
        "guard_core_sha256": root / "destructive-guardian/guard_core.py",
        "destructive_commands_sha256": root / "destructive-guardian/destructive_commands.py",
        "capture_harness_sha256": root / "demo/destructive-guardian/run_capture.py",
    }
    for field, path in sources.items():
        if evidence.get("source", {}).get(field) != digest(path):
            problems.append(f"evidence: source digest mismatch: {field}")

    artifact_path = root / "assets/destructive-guardian/artifact-manifest.json"
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        problems.append("evidence: artifact manifest is invalid")
        return
    if artifact.get("source_evidence", {}).get("sha256") != digest(evidence_path):
        problems.append("evidence: artifact source evidence mismatch")
    renderer = root / artifact.get("renderer", {}).get("path", "missing")
    if not renderer.is_file() or artifact.get("renderer", {}).get("sha256") != digest(renderer):
        problems.append("evidence: renderer identity mismatch")
    elif "rendered asset must not contain an audio track" not in renderer.read_text(encoding="utf-8"):
        problems.append("evidence: renderer audio rejection is missing")
    expected_video = {
        "destructive-guardian-16x9.mp4": [1280, 720],
        "destructive-guardian-9x16.mp4": [720, 1280],
    }
    for name, entry in artifact.get("files", {}).items():
        path = artifact_path.parent / name
        if not path.is_file() or entry.get("sha256") != digest(path) or entry.get("bytes") != path.stat().st_size:
            problems.append(f"evidence: artifact file identity mismatch: {name}")
            continue
        pages_copy = root / "docs/assets/destructive-guardian" / name
        if not pages_copy.is_file() or digest(pages_copy) != entry.get("sha256"):
            problems.append(f"evidence: Pages media copy mismatch: {name}")
        if name in expected_video and (
            entry.get("dimensions") != expected_video[name]
            or entry.get("duration_seconds") != 28
            or entry.get("frame_rate") != 30
            or entry.get("audio_tracks") != 0
            or entry.get("video_tracks") != 1
            or not re.fullmatch(r"fnv1a64:[0-9a-f]{16}", str(entry.get("semantic_frame_hash")))
        ):
            problems.append(f"evidence: video metadata mismatch: {name}")
    if set(artifact.get("files", {})) != {
        "destructive-guardian-16x9.mp4",
        "destructive-guardian-9x16.mp4",
        "destructive-guardian-poster.png",
        "destructive-guardian-transcript.md",
        "destructive-guardian.vtt",
    }:
        problems.append("evidence: artifact file set changed")


def check_policy(root, problems):
    required = {
        "SECURITY.md": ["malware-free", "complete security audit", "safe live wiring", "independent Reviewer"],
        "README.md": ["Security checks", ".github/workflows/security.yml", "SECURITY.md"],
        "docs/index.html": ["security.html", "Instruction Layer", "Enforcement Layer"],
        "docs/security.html": ["malware-free", "complete audit coverage", "safe live wiring"],
    }
    for relative, phrases in required.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            problems.append(f"policy: required file is missing: {relative}")
            continue
        for phrase in phrases:
            if phrase not in text:
                problems.append(f"policy: required coverage is missing in {relative}: {phrase}")


def check_workflow(root, problems):
    path = root / ".github/workflows/security.yml"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        problems.append("workflow: security workflow is missing")
        return
    required = [
        "name: Security checks",
        "pull_request:",
        "push:",
        "workflow_dispatch:",
        "schedule:",
        "contents: read",
        "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd",
        "fetch-depth: 0",
        "rustup toolchain install 1.98.0",
        "cargo clippy --locked --all-targets -- -D warnings",
        "cargo test --locked --all-targets",
        "cargo-audit --version 0.22.2 --locked",
        "cargo audit --file Cargo.lock",
        "python3 -m unittest tools/test_check_public_package.py -v",
        "python3 tools/check_public_package.py",
        "python3 tools/repository_security_check.py",
        "python3 tools/check_guard_mutant.py",
        "python3 -m unittest discover -s demo/destructive-guardian -p 'test_*.py' -v",
    ]
    for phrase in required:
        if phrase not in text:
            problems.append(f"workflow: required pinned step is missing: {phrase}")
    if re.search(r"^\s+paths:\s*$", text, re.MULTILINE):
        problems.append("workflow: push must cover every tracked file")
    uses = re.findall(r"^\s*uses:\s*(\S+)", text, re.MULTILINE)
    if uses != ["actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd"]:
        problems.append("workflow: only the pinned checkout action is allowed")


def check_repository(root, check_git=True):
    root = Path(root).resolve()
    problems = []
    files = list(repository_files(root))
    check_distribution(root, problems)
    check_git_and_modes(root, files, problems, check_git)
    allowlist = load_allowlist(root, problems)
    check_media(root, files, allowlist, problems)
    check_text_and_credentials(root, files, allowlist, problems)
    check_plugin_and_execution(root, files, problems)
    check_evidence(root, problems)
    check_policy(root, problems)
    check_workflow(root, problems)
    problems.extend(validate_site(root))
    return sorted(set(problems))


def main(argv=None):
    argv = list(argv or [])
    root = Path(argv[0]).resolve() if argv else Path(__file__).resolve().parents[1]
    problems = check_repository(root, check_git="--skip-git" not in argv)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print("repository-security: OK (distribution, Git surface, media, text, plugin, site, evidence, policy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
