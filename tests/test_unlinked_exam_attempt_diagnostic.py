"""Roadmap 10.10: an exam-phase attempt on a ticket's target that carries no
assessment_id binds to nothing, and used to do so in silence - the cost only
surfaced at end-session, when the mock was over and nothing could be re-linked.

Per invariant 3 the gap now speaks at record-observation time, while the next
attempt can still be recorded correctly, and is totalled again at end-session.
It is a diagnostic, never a refusal: the observation is recorded either way and
the event stays in the canonical log.
"""

import contextlib
import io
import json
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
        },
        {
            "target_id": "off-pool-target",
            "title": "Not covered by the mock",
            "prerequisites": [],
            "importance": 0.5,
            "frequency": 0.5,
            "expected_points": 5,
            "estimated_learning_minutes": 15,
            "source_refs": ["teacher:worksheet-1"],
        },
    ],
}

INDEPENDENT = {
    "requested": False,
    "levels_revealed": [],
    "scaffold_types": [],
    "partial_transformation_shown": False,
    "full_solution_viewed": False,
}


def spec(assessment_id, prompt):
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
        "purpose": "mock",
    }


def proposal(observation_id, *, target_id="tickets-course", assessment_id=None, outcome="correct"):
    payload = {
        "schema_version": 2,
        "observation_id": observation_id,
        "target_id": target_id,
        "task_id": f"task-{observation_id}",
        "capability_id": "delayed_recall",
        "task_type": "delayed_recall",
        "outcome": outcome,
        "assistance": dict(INDEPENDENT),
        "error_tags": [],
        "diagnostic_confidence": "high",
        "source_refs": [],
    }
    if assessment_id is not None:
        payload["assessment_id"] = assessment_id
    return payload


class UnlinkedExamAttemptDiagnosticTests(unittest.TestCase):
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

    def ready(self, pool_size=2):
        self.cli("init")
        self.cli("load-syllabus", str(self.write("syllabus.json", SYLLABUS)))
        batch = {
            "assessments": [
                spec(f"ticket-{i}", f"State theorem number {i}.") for i in range(1, pool_size + 1)
            ]
        }
        self.cli("mint-assessments", str(self.write("batch.json", batch)))
        self.cli(
            "update-exam-blueprint",
            str(self.write("patch.json", {"question_count": pool_size, "per_question_minutes": 10})),
        )

    def record(self, payload):
        return self.cli("record-observation", str(self.write(f"{payload['observation_id']}.json", payload)))

    def observations(self):
        raw = (self.root / ".exam-prep" / "observations.jsonl").read_text(encoding="utf-8")
        return [json.loads(line) for line in raw.splitlines() if line.strip()]

    def test_unlinked_exam_attempt_is_diagnosed_immediately_and_still_recorded(self):
        self.ready()
        self.cli("exam")
        result = self.record(proposal("obs-1"))

        self.assertTrue(result["appended"])
        self.assertEqual("not_assessment", result["event"]["assessment_integrity"])

        diagnostics = result["diagnostics"]
        self.assertEqual(1, len(diagnostics))
        self.assertEqual("exam_attempt_not_linked_to_ticket", diagnostics[0]["code"])
        self.assertEqual("tickets-course", diagnostics[0]["target_id"])
        self.assertEqual("obs-1", diagnostics[0]["observation_id"])
        self.assertEqual(["ticket-1", "ticket-2"], sorted(diagnostics[0]["candidate_assessment_ids"]))
        self.assertIn("assessment_id", diagnostics[0]["detail"])

        # Diagnostic, not refusal: the evidence survives in the canonical log.
        self.assertEqual(["obs-1"], [event["observation_id"] for event in self.observations()])

    def test_a_linked_attempt_is_not_diagnosed(self):
        self.ready()
        self.cli("exam")
        result = self.record(proposal("obs-1", assessment_id="ticket-1"))
        self.assertNotIn("diagnostics", result)
        self.assertEqual("frozen_attempt", result["event"]["assessment_integrity"])

    def test_no_diagnostic_outside_an_exam_phase(self):
        self.ready()
        self.cli("start")
        result = self.record(proposal("obs-1"))
        self.assertNotIn("diagnostics", result)
        self.assertEqual("not_assessment", result["event"]["assessment_integrity"])

    def test_no_diagnostic_for_a_target_the_mock_does_not_cover(self):
        self.ready()
        self.cli("exam")
        result = self.record(proposal("obs-1", target_id="off-pool-target"))
        self.assertNotIn("diagnostics", result)

    def test_candidates_narrow_as_tickets_get_linked(self):
        self.ready()
        self.cli("exam")
        self.record(proposal("obs-1", assessment_id="ticket-1"))
        result = self.record(proposal("obs-2"))
        self.assertEqual(["ticket-2"], result["diagnostics"][0]["candidate_assessment_ids"])

    def test_no_diagnostic_once_every_ticket_for_the_target_is_linked(self):
        self.ready()
        self.cli("exam")
        self.record(proposal("obs-1", assessment_id="ticket-1"))
        self.record(proposal("obs-2", assessment_id="ticket-2"))
        result = self.record(proposal("obs-3"))
        self.assertNotIn("diagnostics", result)

    def test_end_session_summarizes_unlinked_attempts(self):
        self.ready()
        self.cli("exam")
        self.record(proposal("obs-linked", assessment_id="ticket-1"))
        self.record(proposal("obs-unlinked"))

        post_mortem = self.cli("end-session")["summary"]["post_mortem"]
        self.assertEqual(
            ["obs-unlinked"],
            [item["observation_id"] for item in post_mortem["unlinked_attempts"]],
        )
        self.assertEqual("tickets-course", post_mortem["unlinked_attempts"][0]["target_id"])
        self.assertEqual("correct", post_mortem["unlinked_attempts"][0]["outcome"])
        self.assertEqual(1, post_mortem["attempted"])

    def test_end_session_summary_is_empty_when_every_attempt_was_linked(self):
        self.ready()
        self.cli("exam")
        self.record(proposal("obs-1", assessment_id="ticket-1"))
        post_mortem = self.cli("end-session")["summary"]["post_mortem"]
        self.assertEqual([], post_mortem["unlinked_attempts"])

    def test_study_work_earlier_in_the_same_session_is_not_reported_as_unlinked(self):
        """start -> study -> exam keeps one session_id, so without an anchor the
        pre-exam attempt would be reported as a missed ticket link it never was."""

        self.ready()
        self.cli("start")
        self.record(proposal("obs-study"))
        self.cli("exam")
        self.record(proposal("obs-during-exam"))

        post_mortem = self.cli("end-session")["summary"]["post_mortem"]
        self.assertEqual(
            ["obs-during-exam"],
            [item["observation_id"] for item in post_mortem["unlinked_attempts"]],
        )

    def test_mock_anchor_is_cleared_when_the_session_closes(self):
        self.ready()
        self.cli("exam")
        self.assertIsNotNone(self.cli("status")["session"]["mock_started_at"])
        ended = self.cli("end-session")
        self.assertIsNone(ended["session"]["mock_started_at"])


if __name__ == "__main__":
    unittest.main()
