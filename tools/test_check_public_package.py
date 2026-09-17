#!/usr/bin/env python3
"""Failure controls for the public package isolation check."""

from pathlib import Path
import json
import shutil
import tempfile
import unittest

from tools.check_public_package import check_package


ROOT = Path(__file__).resolve().parents[1]


class PublicPackageCheckTest(unittest.TestCase):
    def setUp(self):
        self.owner = tempfile.TemporaryDirectory(prefix="public-package-")
        self.root = Path(self.owner.name) / "repo"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns(".git", "__pycache__", "target"))

    def tearDown(self):
        self.owner.cleanup()

    def assert_problem(self, fragment):
        problems = check_package(self.root)
        self.assertTrue(any(fragment in problem for problem in problems), problems)

    def test_live_package_is_green(self):
        self.assertEqual(check_package(self.root), [])

    def test_missing_public_skill_fails(self):
        shutil.rmtree(self.root / "skills/thinking")
        self.assert_problem("missing skill files")

    def test_unlisted_skill_fails(self):
        name = "external" + "-policy"
        path = self.root / "skills" / name
        path.mkdir()
        (path / "SKILL.md").write_text(f"---\nname: {name}\ndescription: fixture\n---\n", encoding="utf-8")
        self.assert_problem("unexpected skill files")

    def test_nonmember_skill_reference_fails(self):
        path = self.root / "README.md"
        name = "fixture" + "-policy"
        path.write_text(
            path.read_text(encoding="utf-8") + f"\nSee skills/{name}/SKILL.md.\n",
            encoding="utf-8",
        )
        self.assert_problem("reference to a skill outside the package")

    def test_missing_child_reference_fails(self):
        (self.root / "skills/test-the-test/reference/objective-integrity.md").unlink()
        self.assert_problem("missing skill files")

    def test_plugin_count_drift_fails(self):
        path = self.root / "plugin.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["description"] = value["description"].replace("Six-skill", "Seven-skill")
        path.write_text(json.dumps(value), encoding="utf-8")
        self.assert_problem("every plugin description")

    def test_archive_fails(self):
        (self.root / "release.zip").write_bytes(b"synthetic archive")
        self.assert_problem("release archives")

    def test_unexpected_root_directory_fails(self):
        (self.root / "distribution").mkdir()
        self.assert_problem("unexpected repository root entries")

    def test_local_link_escape_fails(self):
        path = self.root / "README.md"
        owner = "AcmeCorp" + "/internal-control-plane"
        path.write_text(path.read_text(encoding="utf-8") + f"\n[policy](../{owner}/policy.md)\n", encoding="utf-8")
        self.assert_problem("local link escapes")

    def test_active_external_source_root_fails(self):
        path = self.root / "tools/external_loader.py"
        owner = "AcmeCorp" + "/internal-control-plane"
        path.write_text(f"source_root = '../{owner}'\n", encoding="utf-8")
        self.assert_problem("external local dependency")


if __name__ == "__main__":
    unittest.main()
