import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL_ROOT = ROOT / "skill" / "exam-prep"


class FixtureTests(unittest.TestCase):
    def test_all_package_json_fixtures_parse(self):
        paths = [
            SKILL_ROOT / "config" / "config.template.json",
            SKILL_ROOT / "examples" / "example-syllabus.json",
            SKILL_ROOT / "templates" / "course.json",
            SKILL_ROOT / "templates" / "learner.json",
            SKILL_ROOT / "templates" / "session.json",
            SKILL_ROOT / "templates" / "current.json",
            SKILL_ROOT / "examples" / "observation-proposal.json",
            SKILL_ROOT / "examples" / "assessment.json",
            SKILL_ROOT / "examples" / "source-evidence-envelope.json",
            SKILL_ROOT / "examples" / "session-summary.json",
            SKILL_ROOT / "examples" / "mock-exam.json",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)

    def test_example_syllabus_has_dependency_graph_and_provenance(self):
        syllabus = json.loads(
            (SKILL_ROOT / "examples" / "example-syllabus.json").read_text(encoding="utf-8")
        )
        self.assertTrue(any(item.get("prerequisites") for item in syllabus["learning_targets"]))
        self.assertTrue(all(item.get("source_refs") for item in syllabus["learning_targets"]))

    def test_templates_contain_no_runtime_observations(self):
        for path in (SKILL_ROOT / "templates").glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("observations", data)
            self.assertNotIn("priority_score", json.dumps(data))

    def test_readme_documents_onboarding_and_recovery(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        for term in ("install", "init", "syllabus", "status", "review", "mock exam", "state", "recovery"):
            self.assertIn(term, readme)


if __name__ == "__main__":
    unittest.main()
