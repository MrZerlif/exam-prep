import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ReleaseArtifactTests(unittest.TestCase):
    def test_version_matches_skill_metadata(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        skill = (ROOT / "skill" / "exam-prep" / "SKILL.md").read_text(encoding="utf-8")
        match = re.search(r"metadata:\s+version:\s+[\"']([^\"']+)[\"']", skill)
        self.assertIsNotNone(match)
        self.assertEqual(version, match.group(1))

    def test_release_workflow_does_not_package_tests(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertNotIn("tests ", workflow)
        self.assertIn("skill/exam-prep/scripts", workflow)

if __name__ == "__main__":
    unittest.main()
