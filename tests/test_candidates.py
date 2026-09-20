import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_adapters.local_materials.candidates import score
from exam_prep_adapters.local_materials.labels import segment
from exam_prep_lib.lexicon import load


class CandidateScoringTests(unittest.TestCase):
    def test_ru_calibration_fixtures_have_expected_buckets(self):
        root = Path(__file__).parent / "fixtures" / "calibration"
        problem_set = score(
            segment((root / "problem_set_ru.txt").read_text(encoding="utf-8")),
            source=SimpleNamespace(kind="homework"),
            lexicon=load("ru"),
        )
        lecture = score(
            segment((root / "lecture_ru.txt").read_text(encoding="utf-8")),
            source=SimpleNamespace(kind="lecture"),
            lexicon=load("ru"),
        )
        mixed = score(
            segment((root / "mixed_ru.txt").read_text(encoding="utf-8")),
            source=SimpleNamespace(kind="homework"),
            lexicon=load("ru"),
        )
        self.assertEqual(12, sum(item.bucket == "accept" for item in problem_set))
        self.assertEqual(0, sum(item.bucket == "review" for item in problem_set))
        self.assertEqual(0, sum(item.bucket == "accept" for item in lecture))
        self.assertEqual(5, sum(item.bucket == "accept" for item in mixed))
        self.assertEqual(1, sum(item.bucket == "reject" for item in mixed))

    def test_numeric_problem_set_is_accepted(self):
        text = "\n".join(f"{number}) Compute x for problem {number}" for number in range(1, 13))
        candidates = score(segment(text), source=SimpleNamespace(kind="homework"), lexicon=load("en"))
        self.assertEqual(12, len(candidates))
        self.assertTrue(all(item.bucket == "accept" for item in candidates))

    def test_hierarchical_lecture_toc_is_rejected(self):
        text = "1.1 Introduction\n1.2 Limits\n1.3 Derivatives\n2.1 Integrals\n2.2 Series\n"
        candidates = score(segment(text), source=SimpleNamespace(kind="lecture"), lexicon=load("en"))
        self.assertTrue(candidates)
        self.assertFalse(any(item.bucket == "accept" for item in candidates))
        self.assertTrue(all("global_hierarchy" in item.signals for item in candidates))

    def test_mixed_theory_and_tasks_keeps_task_candidates(self):
        text = "1.1 Definitions\nLong prose about the topic and its context.\n\n1) Compute x\n2) Compute y\n3) Compute z\n"
        candidates = score(segment(text), source=SimpleNamespace(kind="homework"), lexicon=load("en"))
        accepted = [item for item in candidates if item.bucket == "accept"]
        self.assertEqual(["1", "2", "3"], [item.segment.label.raw for item in accepted])

    def test_letter_segments_are_not_question_candidates(self):
        candidates = score(segment("1) Compute x\nA) one\nB) two\n"), source=SimpleNamespace(kind="homework"), lexicon=load("en"))
        self.assertEqual(["1"], [item.segment.label.raw for item in candidates])


if __name__ == "__main__":
    unittest.main()
