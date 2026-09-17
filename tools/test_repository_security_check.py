#!/usr/bin/env python3
"""Safe temporary red controls for every repository security rule."""

from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from repository_security_check import check_repository, digest  # noqa: E402

DEMO = TOOLS.parent / "demo/destructive-guardian"
EVIDENCE = "demo/destructive-guardian/evidence/public-evidence.json"
ARTIFACT_MANIFEST = "assets/destructive-guardian/artifact-manifest.json"
SOURCE_DIGESTS = {
    "guard_core_sha256": "destructive-guardian/guard_core.py",
    "destructive_commands_sha256": "destructive-guardian/destructive_commands.py",
    "capture_harness_sha256": "demo/destructive-guardian/run_capture.py",
}


def load_demo_module(name):
    spec = importlib.util.spec_from_file_location(name, DEMO / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_capture = load_demo_module("run_capture")
evidence_validator = load_demo_module("validate_evidence")


def ignore_copy(directory, names):
    ignored = {name for name in names if name in {".git", ".codex", "target", "__pycache__"}}
    if Path(directory).as_posix().endswith("demo/destructive-guardian/evidence"):
        ignored.add("private")
    return ignored


class RepositorySecurityMutants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TOOLS.parent
        cls.pristine_owner = tempfile.TemporaryDirectory(prefix="repository-security-pristine-")
        cls.pristine = Path(cls.pristine_owner.name) / "repo"
        shutil.copytree(cls.source, cls.pristine, ignore=ignore_copy)

    @classmethod
    def tearDownClass(cls):
        cls.pristine_owner.cleanup()

    def setUp(self):
        self.owner = tempfile.TemporaryDirectory(prefix="repository-security-mutant-")
        self.root = Path(self.owner.name) / "repo"
        shutil.copytree(self.pristine, self.root)

    def tearDown(self):
        self.owner.cleanup()

    def problems(self):
        return check_repository(self.root, check_git=False)

    def synthetic_profile(self, label):
        """Build a v3 profile from the synthetic JSONL fixture through the real harness parser."""
        stdout = (DEMO / "fixtures" / f"synthetic-{label}.jsonl").read_text(encoding="utf-8")
        stderr = (DEMO / "fixtures" / "synthetic-stderr.txt").read_text(encoding="utf-8")
        for placeholder in ("{{STERILE_ROOT}}", "{{USER_HOME}}", "{{EMAIL}}", "{{TOKEN}}", "{{THREAD_ID}}"):
            stdout = stdout.replace(placeholder, "synthetic")
            stderr = stderr.replace(placeholder, "synthetic")
        result = subprocess.CompletedProcess(["synthetic"], 0, stdout, stderr)
        return run_capture.summarize(label, result, {})

    def install_synthetic_evidence(self, mutate=None):
        """Install trace-shaped evidence bound to this copy's sources and artifact manifest."""
        evidence_path = self.root / EVIDENCE
        value = json.loads(evidence_path.read_text(encoding="utf-8"))
        value["schema"] = evidence_validator.SCHEMA
        value["unprotected"] = self.synthetic_profile("unprotected")
        value["protected"] = self.synthetic_profile("protected")
        for field, relative in SOURCE_DIGESTS.items():
            value["source"][field] = digest(self.root / relative)
        if mutate is not None:
            mutate(value)
        evidence_path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest_path = self.root / ARTIFACT_MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source_evidence"]["sha256"] = digest(evidence_path)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def assert_rule(self, prefix):
        problems = self.problems()
        self.assertTrue(any(problem.startswith(prefix) for problem in problems), problems)

    def test_clean_fixture_is_green(self):
        self.assertEqual(self.problems(), [])

    def test_extra_skill_fails_distribution(self):
        path = self.root / "skills/extra"
        path.mkdir()
        (path / "SKILL.md").write_text("---\nname: extra\n---\n", encoding="utf-8")
        self.assert_rule("distribution:")

    def test_missing_progressive_reference_fails_distribution(self):
        (self.root / "skills/thinking/references/find-a-way.md").unlink()
        self.assert_rule("distribution:")

    def test_executable_mode_fails_git_surface(self):
        path = self.root / "README.md"
        os.chmod(path, 0o755)
        self.assert_rule("git-surface: executable")

    def test_symlink_fails_git_surface(self):
        os.symlink("README.md", self.root / "readme-link")
        self.assert_rule("git-surface: symlink")

    def test_submodule_declaration_fails_git_surface(self):
        (self.root / ".gitmodules").write_text('[submodule "x"]\npath=x\nurl=../x\n', encoding="utf-8")
        self.assert_rule("git-surface: submodules")

    def test_unapproved_binary_fails_media(self):
        (self.root / "unapproved.bin").write_bytes(b"safe-mutant\0bytes")
        self.assert_rule("media: unapproved binary")

    def test_media_hash_drift_fails_media(self):
        path = self.root / "security/media-allowlist.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        key = "assets/social-preview.png"
        value["files"][key] = "0" * 64
        path.write_text(json.dumps(value), encoding="utf-8")
        self.assert_rule("media: allowlisted hash mismatch")

    def test_hidden_bidi_character_fails_text(self):
        (self.root / "hidden.txt").write_text("safe\u202emutant\n", encoding="utf-8")
        self.assert_rule("text: hidden")

    def test_manifest_hook_key_fails_plugin_boundary(self):
        path = self.root / "plugin.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["hooks"] = {"PreToolUse": []}
        path.write_text(json.dumps(value), encoding="utf-8")
        self.assert_rule("plugin: executable behavior")

    def test_unapproved_hook_program_fails_plugin_boundary(self):
        path = self.root / "hooks"
        path.mkdir()
        (path / "new.py").write_text("print('safe mutant')\n", encoding="utf-8")
        self.assert_rule("plugin: unapproved executable")

    def test_external_page_resource_fails_site(self):
        path = self.root / "docs/index.html"
        text = path.read_text(encoding="utf-8").replace(
            "</head>", '<script src="https://example.invalid/mutant.js"></script>\n</head>'
        )
        path.write_text(text, encoding="utf-8")
        self.assert_rule("site: external resource")

    def test_synthetic_credential_shape_fails_without_echoing_value(self):
        value = "AKIA" + "ABCDEFGHIJKLMNOP"
        (self.root / "synthetic.txt").write_text(value, encoding="utf-8")
        problems = self.problems()
        self.assertTrue(any(problem.startswith("credentials:") for problem in problems), problems)
        self.assertFalse(any(value in problem for problem in problems))

    def test_synthetic_trace_evidence_is_green(self):
        self.install_synthetic_evidence()
        self.assertEqual(self.problems(), [])

    def test_evidence_chronology_mutant_fails(self):
        def reorder(value):
            events = value["protected"]["trace"]["stdout_events"]
            execution = json.loads(json.dumps(value["unprotected"]["trace"]["stdout_events"][3]))
            events.insert(2, execution)
            for position, record in enumerate(events):
                record["index"] = position
            value["protected"]["command_output"] = execution["output"]

        self.install_synthetic_evidence(reorder)
        problems = self.problems()
        self.assertIn("evidence: protected denial chronology: denial recorded after execution", problems)
        self.assertIn("evidence: protected denial chronology: command execution item present", problems)

    def test_evidence_forged_summary_mutant_fails(self):
        def forge(value):
            value["unprotected"]["command_output"] = "GUARD_INACTIVE_PROOF\nforged\n"

        self.install_synthetic_evidence(forge)
        self.assert_rule("evidence: forged summary: unprotected command_output")

    def test_evidence_missing_hook_response_mutant_fails(self):
        def strip_hook(value):
            for record in value["protected"]["trace"]["stdout_events"]:
                record.pop("hook_response", None)
            value["protected"]["denial_reason"] = None

        self.install_synthetic_evidence(strip_hook)
        self.assert_rule("evidence: protected denial chronology: PreToolUse hook response missing")

    def test_evidence_private_shaped_text_mutant_fails(self):
        def leak(value):
            value["protected"]["trace"]["stderr_lines"].append("account " + "synthetic" + "@" + "example.invalid")

        self.install_synthetic_evidence(leak)
        self.assert_rule("evidence: privacy: account detail")

    def test_evidence_candidate_identity_mutant_fails(self):
        path = self.root / "demo/destructive-guardian/evidence/public-evidence.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["source"]["repository_commit"] = value["source"].pop("base_commit")
        path.write_text(json.dumps(value), encoding="utf-8")
        self.assert_rule("evidence: candidate state identity")

    def test_evidence_argv_mutant_fails(self):
        path = self.root / "demo/destructive-guardian/evidence/public-evidence.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["tool"]["argv"]["unprotected"].insert(-1, "--approve-for-me")
        path.write_text(json.dumps(value), encoding="utf-8")
        self.assert_rule("evidence: unprotected argv")

    def test_evidence_cleanup_mutant_fails(self):
        path = self.root / "demo/destructive-guardian/evidence/public-evidence.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["cleanup"]["temporary_auth_copies_exist_after_capture"] = True
        path.write_text(json.dumps(value), encoding="utf-8")
        self.assert_rule("evidence: disposable profile cleanup")

    def test_evidence_computed_home_inventory_mutant_fails(self):
        path = self.root / "demo/destructive-guardian/evidence/public-evidence.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["manifest"]["home_files_after"]["protected"] = [".personal-config"]
        path.write_text(json.dumps(value), encoding="utf-8")
        self.assert_rule("evidence: sterile profile boundary")

    def test_evidence_remote_skill_inventory_mutant_fails(self):
        path = self.root / "demo/destructive-guardian/evidence/public-evidence.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["manifest"]["profile_files_after"]["protected"].append("skills/personal/SKILL.md")
        value["manifest"]["profile_files_after"]["protected"].sort()
        value["manifest"]["protected_only_files"].append("skills/personal/SKILL.md")
        value["manifest"]["protected_only_files"].sort()
        value["manifest"]["non_system_skill_files_observed"] = ["skills/personal/SKILL.md"]
        path.write_text(json.dumps(value), encoding="utf-8")
        self.assert_rule("evidence: plugin, MCP, or non-system skill")

    def test_public_codex_version_mutant_fails(self):
        evidence_path = self.root / "demo/destructive-guardian/evidence/public-evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        version = evidence["tool"]["codex_version"].removeprefix("codex-cli ")
        path = self.root / "destructive-guardian/README.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                f"Codex {version}",
                "Codex 0.0.0",
            ),
            encoding="utf-8",
        )
        self.assert_rule("evidence: public Codex version")

    def test_artifact_manifest_mutant_fails(self):
        path = self.root / "assets/destructive-guardian/artifact-manifest.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["files"]["destructive-guardian-16x9.mp4"]["duration_seconds"] = 49
        path.write_text(json.dumps(value), encoding="utf-8")
        self.assert_rule("evidence: video metadata mismatch")

    def test_semantic_frame_hash_mutant_fails(self):
        path = self.root / "assets/destructive-guardian/artifact-manifest.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        del value["files"]["destructive-guardian-16x9.mp4"]["semantic_frame_hash"]
        path.write_text(json.dumps(value), encoding="utf-8")
        self.assert_rule("evidence: video metadata mismatch")

    def test_renderer_audio_rejection_mutant_fails(self):
        path = self.root / "demo/destructive-guardian/render_media.m"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "rendered asset must not contain an audio track",
                "mutant removed audio rejection",
            ),
            encoding="utf-8",
        )
        manifest_path = self.root / "assets/destructive-guardian/artifact-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["renderer"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assert_rule("evidence: renderer audio rejection")

    def test_security_coverage_link_mutant_fails(self):
        path = self.root / "docs/index.html"
        path.write_text(path.read_text(encoding="utf-8").replace("security.html", "missing.html"), encoding="utf-8")
        self.assert_rule("policy:")

    def test_workflow_pin_mutant_fails(self):
        path = self.root / ".github/workflows/security.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd",
                "actions/checkout@untrusted-mutant",
            ),
            encoding="utf-8",
        )
        self.assert_rule("workflow:")

    def test_workflow_shallow_checkout_mutant_fails(self):
        path = self.root / ".github/workflows/security.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace("fetch-depth: 0", "fetch-depth: 1"),
            encoding="utf-8",
        )
        self.assert_rule("workflow: required pinned step is missing: fetch-depth: 0")

    def test_workflow_push_path_filter_mutant_fails(self):
        path = self.root / ".github/workflows/security.yml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "  push:\n",
                "  push:\n    paths:\n      - README.md\n",
            ),
            encoding="utf-8",
        )
        self.assert_rule("workflow: push must cover")


class RepositorySecurityGitHistory(unittest.TestCase):
    def setUp(self):
        self.owner = tempfile.TemporaryDirectory(prefix="repository-security-git-")
        self.root = Path(self.owner.name) / "repo"
        subprocess.run(
            ["git", "clone", "--quiet", "--no-hardlinks", "--local", str(TOOLS.parent), str(self.root)],
            check=True,
        )
        for path in self.root.iterdir():
            if path.name == ".git":
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        for source in TOOLS.parent.iterdir():
            if source.name in {".git", "__pycache__", "target"}:
                continue
            destination = self.root / source.name
            if source.is_dir():
                shutil.copytree(
                    source,
                    destination,
                    ignore=shutil.ignore_patterns("__pycache__", "target"),
                )
            else:
                shutil.copy2(source, destination)
        subprocess.run(["git", "config", "user.name", "Repository Security Test"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "security-test@example.invalid"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "add", "-A"],
            cwd=self.root,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "--quiet", "--allow-empty", "-m", "candidate descendant"],
            cwd=self.root,
            check=True,
        )

    def tearDown(self):
        self.owner.cleanup()

    def test_evidence_base_accepts_published_descendant(self):
        self.assertEqual(check_repository(self.root), [])

    def test_evidence_base_rejects_unrelated_commit(self):
        tree = subprocess.run(
            ["git", "write-tree"], cwd=self.root, text=True, capture_output=True, check=True
        ).stdout.strip()
        unrelated = subprocess.run(
            ["git", "commit-tree", tree, "-m", "unrelated base"],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        evidence_path = self.root / EVIDENCE
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["source"]["base_commit"] = unrelated
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest_path = self.root / ARTIFACT_MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source_evidence"]["sha256"] = digest(evidence_path)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        self.assertEqual(
            check_repository(self.root),
            ["evidence: base commit is not an ancestor of candidate HEAD"],
        )


if __name__ == "__main__":
    unittest.main()
