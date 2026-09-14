import json
import unittest
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL_ROOT = ROOT / "skill" / "exam-prep"
sys.path.insert(0, str(SKILL_ROOT / "scripts"))


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

    def test_course_template_matches_runtime_policies(self):
        from exam_prep_lib.defaults import default_course

        template = json.loads(
            (SKILL_ROOT / "templates" / "course.json").read_text(encoding="utf-8")
        )
        runtime = default_course()
        self.assertEqual(template["scheduler"], runtime["scheduler"])
        self.assertEqual(template["source_policy"], runtime["source_policy"])

    def test_config_recurring_session_threshold_matches_runtime(self):
        from exam_prep_lib.defaults import DEFAULT_RECURRING_MISTAKE_POLICY

        config = json.loads(
            (SKILL_ROOT / "config" / "config.template.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            DEFAULT_RECURRING_MISTAKE_POLICY["min_sessions"],
            config["scheduler"]["recurring_mistake_sessions"],
        )
    def test_templates_contain_no_runtime_observations(self):
        for path in (SKILL_ROOT / "templates").glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("observations", data)
            self.assertNotIn("priority_score", json.dumps(data))

    def test_readme_documents_onboarding_and_recovery(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        for term in ("install", "init", "syllabus", "status", "review", "mock exam", "state", "recovery"):
            self.assertIn(term, readme)

    def test_default_learner_has_no_practice_mode_bias(self):
        # 2.4: preferred_practice_modes defaulted to ["problem_solving"],
        # steering every fresh learner toward practical/problem-solving
        # pedagogy regardless of blueprint (e.g. a ticket_list exam has no
        # "problems" at all). Nothing in the runtime reads this field today
        # (grep confirms it), so there is no blueprint to derive it from yet
        # - it stays empty until something does.
        from exam_prep_lib.defaults import default_learner

        learner = default_learner("2026-01-01T00:00:00+00:00")
        self.assertEqual([], learner["preferences"]["preferred_practice_modes"])

    def test_default_course_template_is_subject_neutral(self):
        course = json.loads(
            (SKILL_ROOT / "templates" / "course.json").read_text(encoding="utf-8")
        )
        self.assertEqual(2, course["schema_version"])
        self.assertEqual("exam-prep", course["product_id"])
        self.assertEqual("example-exam", course["course_id"])
        self.assertEqual("Exam preparation", course["title"])


if __name__ == "__main__":
    unittest.main()
