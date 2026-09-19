import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_adapters.local_materials.extractor import ExtractedPage, ExtractedSource
from exam_prep_adapters.local_materials.questions import extract_questions


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


if __name__ == "__main__":
    unittest.main()
