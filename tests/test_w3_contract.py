import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL_ROOT = ROOT / "skill" / "exam-prep"
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from exam_prep_lib.verifier_registry import verify_request  # noqa: E402


def _read(relative: str) -> str:
    return " ".join(
        (SKILL_ROOT / relative).read_text(encoding="utf-8").casefold().split()
    )


class W3ContractTests(unittest.TestCase):
    def test_skill_is_a_short_turn_recipe_with_answer_before_service_work(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(re.findall(r"\S+", skill)), 600)
        self.assertRegex(
            " ".join(skill.casefold().split()),
            r"(answer|explanation).{0,180}(next task|next exercise).{0,180}(before|then).{0,80}(command|record)",
        )
        self.assertIn("one observation per block or target", skill.casefold())

    def test_block_practice_and_low_overhead_recording_are_defined(self):
        skill = _read("SKILL.md")
        pedagogy = _read("references/pedagogy.md")
        self.assertIn("3–8", skill)
        self.assertIn("record-batch", skill)
        self.assertIn("--compact", skill)
        self.assertIn("only when timing matters", skill)
        self.assertIn("one observation per block or target", pedagogy)
        self.assertIn("not per arithmetic step", pedagogy)

    def test_forgotten_steps_unfamiliar_topics_and_solution_requests_have_distinct_paths(self):
        pedagogy = _read("references/pedagogy.md")
        self.assertIn("forgotten familiar step", pedagogy)
        self.assertIn("smallest targeted hint", pedagogy)
        self.assertIn("unfamiliar topic", pedagogy)
        self.assertIn("separate worked example", pedagogy)
        self.assertIn("offer a check or practice afterward", pedagogy)
        self.assertIn("learner may skip it or stop", pedagogy)
        self.assertIn('record that target exposure with `record-observation`', pedagogy)
        self.assertIn('outcome: "solution_seen"', pedagogy)
        self.assertIn("without inventing a response", pedagogy)
        self.assertIn("solution_seen", pedagogy)
        self.assertIn("just show", pedagogy)
        self.assertIn("does not require a diagnostic start", pedagogy)
        self.assertIn("end-session --stopped", pedagogy)
        for obsolete in (
            "immediately show the model answer in full",
            "only pre-attempt route to the solution",
            "ask for a start or brief answer structure first",
            "one failed start",
            "preserve attempt-first outside the diagnostic exit",
        ):
            self.assertNotIn(obsolete, pedagogy)
        self.assertIn("exam mode", pedagogy)
        self.assertIn("no unsolicited hints", pedagogy)
        self.assertIn("does not raise mastery", pedagogy)
        self.assertIn("ticket_list", pedagogy)

    def test_input_interpretation_uses_unclear_and_supersession(self):
        pedagogy = _read("references/pedagogy.md")
        self.assertIn("last explicit version", pedagogy)
        self.assertIn("unclear", pedagogy)
        self.assertIn("ask one focused clarification", pedagogy)
        self.assertIn("read the photo before evaluating", pedagogy)
        self.assertIn("reconstruct the learner's steps", pedagogy)
        self.assertIn("supersedes_observation_id", pedagogy)

    def test_course_start_and_exam_ticket_slots_are_planned_and_visible(self):
        skill = _read("SKILL.md")
        optimizer = _read("references/exam-optimizer.md")
        self.assertIn("triage", skill)
        self.assertIn("triage is optional", optimizer)
        self.assertIn("accept a partial", optimizer)
        self.assertIn("skip triage", optimizer)
        self.assertIn("plan", skill)
        self.assertIn("coverage", optimizer)
        self.assertIn("after the first practice block", optimizer)
        self.assertIn("whenever the budget changes", optimizer)
        self.assertIn("total questions", optimizer)
        self.assertIn("topics started", optimizer)
        self.assertNotIn("show the learner total questions on the exam, completed", optimizer)
        self.assertIn("required pace", optimizer)
        self.assertIn("ticket_slots", optimizer)
        self.assertIn("theory", optimizer)
        self.assertIn("problem ladder", optimizer)

    def test_formulations_bank_supports_source_based_delayed_recall(self):
        pedagogy = _read("references/pedagogy.md")
        materials = _read("references/materials.md")
        for phrase in ("question", "exact wording", "read-aloud", "source", "page"):
            self.assertIn(phrase, materials)
        self.assertIn("definitions.md", materials)
        self.assertIn("without looking", pedagogy)
        self.assertIn("reading does not count as retention", pedagogy)
        self.assertIn("delayed", pedagogy)

    def test_verification_reference_contains_minimal_working_json_examples(self):
        verification = (SKILL_ROOT / "references" / "verification.md").read_text(
            encoding="utf-8"
        )
        examples = re.findall(r"```json\s*(\{.*?\})\s*```", verification, re.S)
        requests = [json.loads(example) for example in examples]
        by_kind = {request.get("kind"): request for request in requests}
        self.assertIn("derivative", by_kind)
        self.assertIn("antiderivative", by_kind)
        for kind in ("derivative", "antiderivative"):
            with self.subTest(kind=kind):
                result = verify_request(by_kind[kind])
                self.assertEqual("passed", result["status"])


if __name__ == "__main__":
    unittest.main()
