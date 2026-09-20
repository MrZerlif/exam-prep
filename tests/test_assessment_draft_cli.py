import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import main


class AssessmentDraftCliTests(unittest.TestCase):
    def test_draft_then_finalize(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            materials = root / "materials"
            materials.mkdir()
            (materials / "hw2.md").write_text("Задача 1\nCompute x", encoding="utf-8")
            solution = materials / "hw2_resheniya.md"
            solution.write_text("Решение 1\nx=2", encoding="utf-8")
            draft_path = root / "draft.json"
            final_path = root / "mint.json"
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(["draft-assessments", str(materials), "--out", str(draft_path)]))
            draft = json.loads(draft_path.read_text(encoding="utf-8"))
            self.assertIsNone(draft["assessments"][0]["target_id"])
            target_map = root / "targets.json"
            target_map.write_text(json.dumps({draft["assessments"][0]["question_id"]: "target-x"}), encoding="utf-8")
            with redirect_stdout(output):
                self.assertEqual(0, main(["finalize-assessment-draft", str(draft_path), "--target-map", str(target_map), "--out", str(final_path)]))
            package = json.loads(final_path.read_text(encoding="utf-8"))
            self.assertEqual("target-x", package["assessments"][0]["target_id"])

    def test_draft_detects_and_extracts_mixed_language_sources(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            materials = root / "materials"
            materials.mkdir()
            (materials / "german.txt").write_text(
                "Aufgabe 1\nDie Aufgabe ist zu berechnen.\n",
                encoding="utf-8",
            )
            (materials / "german_lösung.txt").write_text(
                "Lösung 1\nDie Lösung ist x=2.\n",
                encoding="utf-8",
            )
            (materials / "english.txt").write_text(
                "Task 1\nThe task is to compute.\n",
                encoding="utf-8",
            )
            (materials / "english_solution.txt").write_text(
                "Solution 1\nThe solution is x=2.\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(["--workspace", str(root), "init", "--language", "ru"]))
                self.assertEqual(
                    0,
                    main(
                        [
                            "--workspace",
                            str(root),
                            "draft-assessments",
                            str(materials),
                            "--out",
                            str(root / "draft.json"),
                        ]
                    ),
                )
            draft = json.loads((root / "draft.json").read_text(encoding="utf-8"))
            self.assertEqual(2, len(draft["assessments"]))
            self.assertEqual(
                {"Die Lösung ist x=2.", "The solution is x=2."},
                {item["rubric"]["reference_answer"] for item in draft["assessments"]},
            )


class DraftExpectedTotalPointsTests(unittest.TestCase):
    """The course's own point total is what extraction verifies against."""

    def draft_with_expected_total(self, expected_total):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            materials = root / "materials"
            materials.mkdir()
            (materials / "klausur.txt").write_text(
                "\n".join(
                    f"Aufgabe {index}) Berechnen Sie den Grenzwert. ({points} Punkte)"
                    for index, points in zip(range(1, 5), (10, 10, 15, 25))
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(["--workspace", str(root), "init", "--language", "de"]))
                course_path = root / ".exam-prep" / "course.json"
                course = json.loads(course_path.read_text(encoding="utf-8"))
                course["exam"]["expected_total_points"] = expected_total
                course_path.write_text(json.dumps(course), encoding="utf-8")
                self.assertEqual(
                    0,
                    main([
                        "--workspace", str(root), "draft-assessments", str(materials),
                        "--out", str(root / "draft.json"),
                    ]),
                )
            draft = json.loads((root / "draft.json").read_text(encoding="utf-8"))
            return [
                issue
                for item in draft["assessments"]
                for issue in item["issues"]
                if issue["kind"] == "low_confidence_question"
            ]

    def test_matching_course_total_leaves_points_unflagged(self):
        self.assertEqual([], self.draft_with_expected_total(60))

    def test_mismatched_course_total_is_flagged(self):
        self.assertTrue(self.draft_with_expected_total(100))


class DraftLectureExerciseFlagTests(unittest.TestCase):
    def draft(self, *extra):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            materials = root / "materials"
            materials.mkdir()
            (materials / "lekciya.md").write_text(
                "\n".join((
                    "1. Непрерывность",
                    "Оглавление",
                    "Задача 1. Найдите производную функции f(x) = x^2 в точке x = 3. (2 балла)",
                )),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(["--workspace", str(root), "init", "--language", "ru"]))
                self.assertEqual(
                    0,
                    main([
                        "--workspace", str(root), "draft-assessments", str(materials),
                        "--out", str(root / "draft.json"), *extra,
                    ]),
                )
            return json.loads((root / "draft.json").read_text(encoding="utf-8"))["assessments"]

    def test_lecture_exercises_are_absent_by_default(self):
        self.assertEqual([], self.draft())

    def test_flag_extracts_lecture_exercises_as_practice(self):
        assessments = self.draft("--include-lecture-exercises")
        self.assertEqual(1, len(assessments))
        self.assertEqual("practice", assessments[0]["purpose"])
        self.assertIn("производную", assessments[0]["prompt"])


if __name__ == "__main__":
    unittest.main()
