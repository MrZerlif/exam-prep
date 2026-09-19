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

    def test_vendor_attribution_and_derived_headers_exist(self):
        self.assertIn("ZeKaiNie", (ROOT / "skill" / "exam-prep" / "vendor" / "exam-cram-coach" / "README.md").read_text(encoding="utf-8"))
        for name in ("extractor.py", "chapters.py", "questions.py", "figures.py"):
            text = (ROOT / "skill" / "exam-prep" / "scripts" / "exam_prep_adapters" / "local_materials" / name).read_text(encoding="utf-8")
            self.assertIn("ZeKaiNie", text)


if __name__ == "__main__":
    unittest.main()
