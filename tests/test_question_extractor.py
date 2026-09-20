import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_adapters.local_materials.extractor import ExtractedPage, ExtractedSource
from exam_prep_adapters.local_materials.questions import extract_questions, source_question_issues
from exam_prep_lib.assessment_draft import build_draft


def source(path: str, kind: str, text: str) -> ExtractedSource:
    return ExtractedSource(path, kind, (ExtractedPage(1, text),), path, None, None)


class QuestionExtractorTests(unittest.TestCase):
    def test_lecture_source_yields_no_questions(self):
        questions = extract_questions(
            (source("lecture.md", "lecture", "1.1 Introduction\nExplain limits\n1.2 Limits\nExplain continuity"),)
        )
        self.assertEqual((), questions)

    def test_other_source_requires_opt_in_and_marks_issue(self):
        material = source("unknown.md", "other", "Question 1\nCompute x")
        self.assertEqual((), extract_questions((material,)))
        questions = extract_questions((material,), include_unclassified=True)
        self.assertEqual(1, len(questions))
        self.assertTrue(any(issue.kind == "unclassified_source" for issue in questions[0].issues))

    def test_matches_solution_by_label_and_options_are_preserved(self):
        questions = extract_questions(
            (
                source("hw2.md", "homework", "Задача 1.3.10 (2 балла)\nCompute x\nA) one\nB) two"),
                source("hw2_resheniya.md", "solution", "Решение 1.3.10\nx = 2"),
            )
        )
        self.assertEqual(1, len(questions))
        self.assertEqual("1.3.10", questions[0].label)
        self.assertEqual(("one", "two"), questions[0].options)
        self.assertEqual("x = 2", questions[0].reference_answer)
        self.assertEqual(2, questions[0].points)

    def test_missing_solution_is_an_issue_and_hash_is_deterministic(self):
        first = extract_questions((source("hw.md", "homework", "Задача 1\nFind y"),))[0]
        second = extract_questions((source("hw.md", "homework", "Задача 1\nFind y"),))[0]
        self.assertIsNone(first.reference_answer)
        self.assertEqual([], first.expected_evidence)
        self.assertTrue(any(issue.kind == "missing_answer" for issue in first.issues))
        self.assertEqual(first.question_id, second.question_id)

    def test_exam_question_kind_is_exam(self):
        question = extract_questions((source("exam.pdf", "exam", "Вопрос 2\nExplain limit"),))[0]
        self.assertEqual("exam", question.kind)

    def test_solution_labels_do_not_cross_pair_between_files(self):
        questions = extract_questions(
            (
                source("hw_a.md", "homework", "Задача 1\nFind a"),
                source("hw_b.md", "homework", "Задача 1\nFind b"),
                source("hw_a_resheniya.md", "solution", "Решение 1\na = 1"),
                source("hw_b_resheniya.md", "solution", "Решение 1\nb = 2"),
            )
        )
        answers = {question.prompt: question.reference_answer for question in questions}
        self.assertEqual({"Find a": "a = 1", "Find b": "b = 2"}, answers)


class ExtractionAnomalyScopeTests(unittest.TestCase):
    """The prose ratio only signals a parser failure where prose is expected."""

    def test_compact_problem_set_is_not_anomalous(self):
        material = source(
            "hw.md",
            "homework",
            "\n".join(f"{index}) Найдите предел a_n." for index in range(1, 13)),
        )
        self.assertEqual((), source_question_issues(material))

    def test_compact_exam_is_not_anomalous(self):
        material = source(
            "exam.md",
            "exam",
            "\n".join(
                f"{index}) Berechnen Sie. ({points} Punkte)"
                for index, points in zip(range(1, 5), (10, 10, 15, 25))
            ),
        )
        self.assertEqual((), source_question_issues(material, "de"))

    def test_short_prose_source_is_not_anomalous(self):
        # Few segments make the ratio meaningless: a textbook page whose only
        # label is its chapter heading is one segment out of one, which is a
        # perfect ratio and tells us nothing about the parser.
        material = source(
            "Stewart_Calculus.txt",
            "other",
            "Глава 1. Пределы и непрерывность функций одной переменной.\n"
            "Предел последовательности определяется следующим образом.\n"
            "Функция называется непрерывной в точке, если предел совпадает со значением.\n"
            "Теорема о промежуточном значении утверждает существование корня.\n",
        )
        self.assertEqual(
            [],
            [issue.kind for issue in source_question_issues(material, "ru", language_confidence=1.0)],
        )

    def test_dense_other_source_still_blocks(self):
        material = source(
            "unknown.md",
            "other",
            "\n".join(f"{index}) Найдите предел a_n." for index in range(1, 13)),
        )
        issues = source_question_issues(material)
        self.assertTrue(
            any(issue.kind == "extraction_anomaly" and issue.severity == "blocking" for issue in issues)
        )


class ExpectedTotalPointsTests(unittest.TestCase):
    """Point totals are only verified against a total the course actually set."""

    def exam(self) -> ExtractedSource:
        return source(
            "exam.md",
            "exam",
            "\n".join(
                f"{index}) Berechnen Sie. ({points} Punkte)"
                for index, points in zip(range(1, 5), (10, 10, 15, 25))
            ),
        )

    def points_issues(self, **kwargs) -> list[str]:
        questions = extract_questions((self.exam(),), language="de", **kwargs)
        return [
            issue.detail
            for question in questions
            for issue in question.issues
            if issue.kind == "low_confidence_question"
        ]

    def test_points_without_expected_total_are_not_penalised(self):
        self.assertEqual([], self.points_issues())

    def test_points_matching_expected_total_get_full_weight(self):
        self.assertEqual([], self.points_issues(expected_total_points=60))

    def test_points_mismatch_is_info_only(self):
        questions = extract_questions(
            (self.exam(),), language="de", expected_total_points=100
        )
        mismatches = [
            issue
            for question in questions
            for issue in question.issues
            if issue.kind == "low_confidence_question"
        ]
        self.assertTrue(mismatches)
        self.assertEqual({"info"}, {issue.severity for issue in mismatches})


LECTURE_WITH_EXERCISES = "\n".join((
    "1. Непрерывность",
    "Оглавление",
    "2. Производная",
    "Задача 1. Найдите производную функции f(x) = x^2 в точке x = 3. (2 балла)",
    "Задача 2. Найдите предел последовательности a_n = 1/n при n к бесконечности. (2 балла)",
))


class UnclassifiedSourceConfidenceTests(unittest.TestCase):
    """unclassified_source means "the lexicon is short of words", not
    "the taxonomy has no slot for a textbook"."""

    def textbook(self) -> ExtractedSource:
        return source(
            "Stewart_Calculus.txt",
            "other",
            "Глава 1. Пределы и непрерывность.\n"
            "Предел последовательности определяется следующим образом.\n"
            "Функция называется непрерывной в точке, если предел совпадает со значением.\n",
        )

    def kinds(self, confidence):
        return [
            issue.kind
            for issue in source_question_issues(
                self.textbook(), "ru", language_confidence=confidence
            )
        ]

    def test_confidently_detected_language_does_not_flag_unclassified(self):
        self.assertNotIn("unclassified_source", self.kinds(1.0))

    def test_uncertain_language_still_flags_unclassified(self):
        self.assertIn("unclassified_source", self.kinds(0.62))

    def test_unknown_confidence_still_flags_unclassified(self):
        self.assertIn("unclassified_source", self.kinds(None))


class LectureExerciseOptInTests(unittest.TestCase):
    """Lecture exercises are real practice material, behind an explicit flag."""

    def lecture(self) -> ExtractedSource:
        return source("lecture.md", "lecture", LECTURE_WITH_EXERCISES)

    def test_lecture_exercises_need_flag(self):
        self.assertEqual((), extract_questions((self.lecture(),)))

    def test_lecture_exercises_are_extracted_behind_the_flag(self):
        questions = extract_questions((self.lecture(),), include_lecture_exercises=True)
        self.assertTrue(questions)

    def test_lecture_exercises_accept_only(self):
        questions = extract_questions((self.lecture(),), include_lecture_exercises=True)
        prompts = " ".join(question.prompt for question in questions)
        self.assertNotIn("Оглавление", prompts)

    def test_lecture_question_is_marked_with_its_origin(self):
        questions = extract_questions((self.lecture(),), include_lecture_exercises=True)
        for question in questions:
            origin = [
                issue for issue in question.issues
                if issue.kind == "low_confidence_question" and "lecture.md" in issue.detail
            ]
            self.assertTrue(origin, question.prompt)
            self.assertEqual({"info"}, {issue.severity for issue in origin})

    def test_lecture_question_never_mock(self):
        questions = extract_questions((self.lecture(),), include_lecture_exercises=True)
        draft = build_draft(questions, holdout_ratio=1.0)
        self.assertTrue(draft["assessments"])
        self.assertEqual(
            {"practice"}, {item["purpose"] for item in draft["assessments"]}
        )

    def test_unclassified_opt_in_is_unchanged_by_the_lecture_flag(self):
        material = source("unknown.md", "other", "Question 1\nCompute x")
        self.assertEqual((), extract_questions((material,), include_lecture_exercises=True))
        self.assertEqual(
            1, len(extract_questions((material,), include_unclassified=True))
        )


if __name__ == "__main__":
    unittest.main()
