#!/usr/bin/env python3
"""Check that the public skill package is complete and self-contained."""

from pathlib import Path
from urllib.parse import unquote, urlsplit
import json
import re
import sys


SKILLS = (
    "thinking",
    "teamwork",
    "better-coding",
    "plans",
    "test-the-test",
    "ship-or-fix",
)

SKILL_FILES = {
    "skills/thinking/SKILL.md",
    "skills/thinking/references/decomposition-and-delegation.md",
    "skills/thinking/references/escalation-and-retries.md",
    "skills/thinking/references/failure-patterns.md",
    "skills/thinking/references/find-a-way.md",
    "skills/teamwork/SKILL.md",
    "skills/better-coding/SKILL.md",
    "skills/plans/SKILL.md",
    "skills/plans/references/blueprint.md",
    "skills/test-the-test/SKILL.md",
    "skills/test-the-test/reference/objective-integrity.md",
    "skills/ship-or-fix/SKILL.md",
}

ROOT_ENTRIES = {
    ".claude-plugin",
    ".git",
    ".github",
    "AGENTS.md",
    "CLAUDE.md",
    "INSTALL.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "STANDING-SOURCE-AND-ADAPTER-CONTRACT.md",
    "activation",
    "assets",
    "change-guardian",
    "demo",
    "destructive-guardian",
    "docs",
    "plugin.json",
    "security",
    "skills",
    "tools",
}

PUBLIC_REPOSITORY = "https://github.com/Ezra144israel/agent-teamwork-kit"
PLUGIN_FILES = ("plugin.json", ".claude-plugin/plugin.json")
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)")
SKILL_PATH = re.compile(r"(?<![A-Za-z0-9.-])skills/([a-z][a-z0-9-]+)(?:/|\b)")
FRONTMATTER_NAME = re.compile(r"\A---\n(?:.*\n)*?name:\s*([a-z][a-z0-9-]+)\s*$", re.MULTILINE)
EXTERNAL_LOCAL_PATH = re.compile(
    r"(?:/" r"Users/[^/\s'\"]+|/" r"home/[^/\s'\"]+|[A-Za-z]:\\" r"Users\\[^\\\s'\"]+|\.\." r"/|--source" r"-root\b|\bsource" r"_root\b)",
    re.IGNORECASE,
)
TEXT_SUFFIXES = {".html", ".json", ".md", ".mjs", ".py", ".sh", ".yml", ".yaml"}
SKIP_PARTS = {".git", "__pycache__", "target"}


def _read_text(path, problems):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        problems.append(f"public-package: missing or unreadable text file: {path.name}")
        return ""


def _relative_files(root, directory):
    base = root / directory
    if not base.is_dir():
        return set()
    return {
        path.relative_to(root).as_posix()
        for path in base.rglob("*")
        if path.is_file() and not any(part in SKIP_PARTS for part in path.parts)
    }


def _public_text_files(root):
    candidates = [
        root / "README.md",
        root / "INSTALL.md",
        root / "STANDING-SOURCE-AND-ADAPTER-CONTRACT.md",
    ]
    for directory in ("activation", "docs", "skills"):
        base = root / directory
        if base.is_dir():
            candidates.extend(path for path in base.rglob("*") if path.is_file())
    return sorted(path for path in candidates if path.suffix.lower() in TEXT_SUFFIXES)


def _active_program_files(root):
    candidates = []
    for directory in ("tools", "activation", ".github"):
        base = root / directory
        if base.is_dir():
            candidates.extend(path for path in base.rglob("*") if path.is_file())
    return sorted(
        path
        for path in candidates
        if path.suffix.lower() in TEXT_SUFFIXES
        and not path.name.startswith("test_")
        and not any(part in SKIP_PARTS for part in path.parts)
    )


def check_skill_files(root, problems):
    actual = _relative_files(root, "skills")
    if actual != SKILL_FILES:
        missing = sorted(SKILL_FILES - actual)
        extra = sorted(actual - SKILL_FILES)
        if missing:
            problems.append("public-package: missing skill files: " + ", ".join(missing))
        if extra:
            problems.append("public-package: unexpected skill files: " + ", ".join(extra))

    for name in SKILLS:
        path = root / "skills" / name / "SKILL.md"
        text = _read_text(path, problems)
        match = FRONTMATTER_NAME.search(text)
        if not match or match.group(1) != name:
            problems.append(f"public-package: frontmatter name does not match directory: {name}")


def check_root_and_archives(root, problems):
    actual = {path.name for path in root.iterdir()}
    extra = sorted(actual - ROOT_ENTRIES)
    if extra:
        problems.append("public-package: unexpected repository root entries: " + ", ".join(extra))
    archives = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*.zip")
        if not any(part in SKIP_PARTS for part in path.parts)
    )
    if archives:
        problems.append("public-package: release archives are not source members: " + ", ".join(archives))


def check_plugins(root, problems):
    manifests = []
    for relative in PLUGIN_FILES:
        try:
            manifests.append(json.loads((root / relative).read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError):
            problems.append(f"public-package: invalid plugin manifest: {relative}")
    try:
        marketplace = json.loads((root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        marketplace_plugin = marketplace["plugins"][0]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, IndexError, TypeError):
        problems.append("public-package: invalid marketplace manifest")
        marketplace_plugin = {}

    versions = [value.get("version") for value in manifests] + [marketplace_plugin.get("version")]
    if len(set(versions)) != 1 or not versions[0]:
        problems.append("public-package: plugin versions must agree")

    descriptions = [value.get("description", "") for value in manifests] + [
        marketplace.get("description", "") if "marketplace" in locals() else "",
        marketplace_plugin.get("description", ""),
    ]
    if any("six-skill instruction layer" not in value.lower() for value in descriptions):
        problems.append("public-package: every plugin description must declare the six-skill Instruction Layer")
    if any(value.get("repository") != PUBLIC_REPOSITORY for value in manifests):
        problems.append("public-package: plugin repository declarations must name this public repository")
    if marketplace_plugin.get("source") != "./":
        problems.append("public-package: marketplace plugin source must resolve inside this repository")


def _table_names(text, heading):
    start = text.find(heading)
    if start < 0:
        return []
    end = text.find("\n## ", start + len(heading))
    section = text[start:] if end < 0 else text[start:end]
    return [
        match.group(1)
        for match in re.finditer(r"^\|\s*`([a-z][a-z0-9-]+)`\s*\|", section, re.MULTILINE)
    ]


def check_declared_skills(root, problems):
    contract = _read_text(root / "STANDING-SOURCE-AND-ADAPTER-CONTRACT.md", problems)
    if _table_names(contract, "## Skill distribution") != list(SKILLS):
        problems.append("public-package: source contract rows must equal the six skills in package order")

    router = _read_text(root / "activation/ROUTER.example.md", problems)
    if _table_names(router, "# Skill router") != list(SKILLS):
        problems.append("public-package: activation router rows must equal the six skills in package order")

    required_claims = {
        "README.md": ("skills-6-blue.svg", "These six skills", "full six-skill package"),
        "INSTALL.md": ("Instruction Layer** is six", "plugin installs only the six"),
        "STANDING-SOURCE-AND-ADAPTER-CONTRACT.md": ("six-skill", "No skill absent from this table"),
        "activation/README.md": ("six-skill Instruction Layer", "repo's six skills"),
        "docs/index.html": ("Six skills tell coding agents", "plugin installs only the six"),
        "docs/security.html": ("Exact six-skill distribution",),
    }
    for relative, phrases in required_claims.items():
        text = _read_text(root / relative, problems)
        for phrase in phrases:
            if phrase not in text:
                problems.append(f"public-package: six-skill declaration missing from {relative}: {phrase}")
        if re.search(r"\beight(?:-| )skills?\b", text, re.IGNORECASE):
            problems.append(f"public-package: stale skill count in {relative}")


def check_references(root, problems):
    for path in _public_text_files(root):
        text = _read_text(path, problems)
        relative = path.relative_to(root).as_posix()
        for skill in SKILL_PATH.findall(text):
            if skill not in SKILLS:
                problems.append(f"public-package: reference to a skill outside the package in {relative}")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip("<>")
            split = urlsplit(target)
            if split.scheme or target.startswith("//") or target.startswith("#"):
                continue
            if not split.path:
                continue
            decoded = unquote(split.path)
            if Path(decoded).is_absolute():
                problems.append(f"public-package: absolute local link in {relative}")
                continue
            resolved = (path.parent / decoded).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                problems.append(f"public-package: local link escapes the repository in {relative}")
                continue
            if not resolved.exists():
                problems.append(f"public-package: broken local link in {relative}: {target}")


def check_active_dependencies(root, problems):
    for path in _active_program_files(root):
        text = _read_text(path, problems)
        if EXTERNAL_LOCAL_PATH.search(text):
            relative = path.relative_to(root).as_posix()
            problems.append(f"public-package: active tooling has an external local dependency: {relative}")


def check_package(root):
    root = Path(root).resolve()
    problems = []
    if not root.is_dir():
        return ["public-package: root is not a directory"]
    check_root_and_archives(root, problems)
    check_skill_files(root, problems)
    check_plugins(root, problems)
    check_declared_skills(root, problems)
    check_references(root, problems)
    check_active_dependencies(root, problems)
    return sorted(set(problems))


def main(argv=None):
    argv = list(argv or [])
    root = Path(argv[0]).resolve() if argv else Path(__file__).resolve().parents[1]
    problems = check_package(root)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print("public-package: OK (6 skills, local references, plugins, docs, no archives or external local dependencies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
