"""Roadmap 10.6: an attempt on a mock ticket binds to that ticket only
through `assessment_id`. `task_id` is required on every proposal and never
binds, so an otherwise-correct attempt that names the ticket in `task_id`
alone is recorded as detached evidence and the mock grades as unattempted.

That behavior is deliberate (`assessment_id` is an optional, non-engine-owned
field of observation-proposal-v2), which makes it a contract rather than a
defect - and a contract nothing told the tutor about until it was documented
in SKILL.md and references/commands.md. test_mock_exam_blueprint.py already
covered the mechanism working, but its helper always supplies `assessment_id`,
so nothing covered the contract being discoverable or the cost of missing it.
"""

import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skill" / "exam-prep"
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from exam_prep import main  # noqa: E402


SYLLABUS = {
    "schema_version": 2,
    "learning_targets": [
        {
            "target_id": "tickets-course",
            "title": "Ticket topics",
            "prerequisites": [],
            "importance": 0.9,
            "frequency": 0.8,
            "expected_points": 10,
            "estimated_learning_minutes": 25,
            "source_refs": ["teacher:worksheet-1"],
        }
    ],
}

INDEPENDENT = {
    "requested": False,
    "levels_revealed": [],
    "scaffold_types": [],
    "partial_transformation_shown": False,
    "full_solution_viewed": False,
}

HINTED = {
    "requested": True,
    "levels_revealed": ["H1", "H2"],
    "scaffold_types": ["prompt"],
    "partial_transformation_shown": False,
    "full_solution_viewed": False,
}


def spec(assessment_id, prompt, purpose="mock"):
    return {
        "assessment_id": assessment_id,
        "target_id": "tickets-course",
        "capability_id": "delayed_recall",
        "prompt": prompt,
        "rubric": {"correct": 1},
        "expected_evidence": ["independent_work"],
        "source_refs": [
            {"source_id": "teacher:tickets", "authority": "teacher_material", "locator": "ticket list"}
        ],
        "difficulty": 0.4,
        "question_version": 1,
        "rubric_version": 1,
        "purpose": purpose,
    }


def proposal(observation_id, *, task_id, assessment_id=None, outcome="correct", assistance=None):
    payload = {
        "schema_version": 2,
        "observation_id": observation_id,
        "target_id": "tickets-course",
        "task_id": task_id,
        "capability_id": "delayed_recall",
        "task_type": "delayed_recall",
        "outcome": outcome,
        "assistance": dict(assistance or INDEPENDENT),
        "error_tags": [],
        "diagnostic_confidence": "high",
        "source_refs": [],
    }
    if assessment_id is not None:
        payload["assessment_id"] = assessment_id
    return payload


class MockTicketBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        self.assertEqual(code, 0, output.getvalue())
        return json.loads(output.getvalue())

    def write(self, name, payload):
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def exam_in_progress(self, pool_size=2, **blueprint):
        self.cli("init")
        self.cli("load-syllabus", str(self.write("syllabus.json", SYLLABUS)))
        batch = {
            "assessments": [
                spec(f"ticket-{i}", f"State theorem number {i}.") for i in range(1, pool_size + 1)
            ]
        }
        self.cli("mint-assessments", str(self.write("batch.json", batch)))
        self.cli("update-exam-blueprint", str(self.write("patch.json", blueprint)))
        return self.cli("exam")

    def record(self, payload):
        return self.cli("record-observation", str(self.write(f"{payload['observation_id']}.json", payload)))

    def test_full_cycle_with_assessment_id_gives_an_attempted_scored_post_mortem(self):
        """The acceptance criterion: exam -> record-observation on a ticket ->
        end-session yields attempted: true and a meaningful score."""

        self.exam_in_progress(pool_size=2, question_count=2, per_question_minutes=10)
        self.record(proposal("obs-1", task_id="recite-1", assessment_id="ticket-1"))
        self.record(proposal("obs-2", task_id="recite-2", assessment_id="ticket-2"))

        post_mortem = self.cli("end-session")["summary"]["post_mortem"]
        self.assertEqual(2, post_mortem["total_questions"])
        self.assertEqual(2, post_mortem["attempted"])
        self.assertEqual(2, post_mortem["correct_independent"])
        self.assertEqual(1.0, post_mortem["score"])
        for question in post_mortem["questions"]:
            self.assertTrue(question["attempted"])
            self.assertEqual("correct", question["outcome"])
            self.assertEqual("tickets-course", question["target_id"])

    def test_assessment_id_is_what_binds_and_task_id_is_not(self):
        """Reproduces the manual finding: naming the ticket in task_id alone
        records detached evidence and grades the mock as unattempted."""

        self.exam_in_progress(pool_size=2, question_count=2, per_question_minutes=10)
        detached = self.record(proposal("obs-1", task_id="ticket-1"))
        self.assertEqual("not_assessment", detached["event"]["assessment_integrity"])
        self.assertNotIn("assessment_purpose", detached["event"])

        post_mortem = self.cli("end-session")["summary"]["post_mortem"]
        self.assertEqual(0, post_mortem["attempted"])
        self.assertEqual(0.0, post_mortem["score"])
        for question in post_mortem["questions"]:
            self.assertFalse(question["attempted"])

    def test_bound_attempt_is_tagged_with_the_frozen_contract(self):
        self.exam_in_progress(pool_size=1, question_count=1, per_question_minutes=10)
        bound = self.record(proposal("obs-1", task_id="recite-1", assessment_id="ticket-1"))
        event = bound["event"]
        self.assertEqual("frozen_attempt", event["assessment_integrity"])
        self.assertEqual("mock", event["assessment_purpose"])
        self.assertTrue(event["assessment_spec_hash"])

    def test_score_counts_independent_successes_not_merely_correct_ones(self):
        """Both tickets answered correctly, one after H1/H2 hints: the hinted
        one is `correct` but its band is `guided`, so the score is 0.5."""

        self.exam_in_progress(pool_size=2, question_count=2, per_question_minutes=10)
        self.record(proposal("obs-1", task_id="recite-1", assessment_id="ticket-1"))
        self.record(
            proposal("obs-2", task_id="recite-2", assessment_id="ticket-2", assistance=HINTED)
        )

        post_mortem = self.cli("end-session")["summary"]["post_mortem"]
        by_id = {question["assessment_id"]: question for question in post_mortem["questions"]}
        self.assertEqual("independent", by_id["ticket-1"]["assistance_band"])
        self.assertEqual("guided", by_id["ticket-2"]["assistance_band"])
        self.assertEqual("correct", by_id["ticket-2"]["outcome"])

        self.assertEqual(2, post_mortem["attempted"])
        self.assertEqual(1, post_mortem["correct_independent"])
        self.assertEqual(0.5, post_mortem["score"])

    def test_a_mistyped_link_fails_loudly_instead_of_recording_detached_evidence(self):
        self.exam_in_progress(pool_size=1, question_count=1, per_question_minutes=10)
        payload = proposal("obs-1", task_id="recite-1", assessment_id="ticket-404")
        path = self.write("obs-1.json", payload)
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):
                main(["--workspace", str(self.root), "record-observation", str(path)])

    def test_the_assessment_id_contract_is_documented_where_the_tutor_reads(self):
        """The guard for this whole class: the mechanism worked all along, but
        nothing routed the tutor to it, so a live run recorded a mock with no
        link and no test noticed. SKILL.md must raise it, and a reference it
        links must carry the detail."""

        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("assessment_id", skill)
        self.assertTrue(
            re.search(r"assessment_id.*bind", skill)
            or re.search(r"bind.*assessment_id", skill),
            "SKILL.md mentions assessment_id without saying it is what binds an attempt",
        )

        commands = (SKILL_ROOT / "references" / "commands.md").read_text(encoding="utf-8")
        self.assertIn("assessment_id", commands)
        self.assertIn("task_id", commands)
        self.assertIn("not_assessment", commands)


if __name__ == "__main__":
    unittest.main()
