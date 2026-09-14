import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.capabilities import (  # noqa: E402
    AssessmentCapability,
    CapabilityRegistry,
)
from exam_prep_lib.reducer import reduce_learning_state  # noqa: E402


class CapabilityRegistryTests(unittest.TestCase):
    def test_unknown_capability_is_recordable_but_non_promoting(self):
        registry = CapabilityRegistry.with_defaults()
        resolution = registry.resolve("provider:new_capability")
        self.assertFalse(resolution.capability.is_registered)
        self.assertEqual((), resolution.capability.affected_dimensions)
        self.assertIsNone(resolution.capability.verifier_id)
        self.assertTrue(resolution.warning)

    def test_registered_capability_can_define_explicit_evidence_mapping(self):
        registry = CapabilityRegistry()
        registry.register(
            AssessmentCapability(
                capability_id="proof:short",
                affected_dimensions=("conceptual", "transfer"),
                response_type="free_text",
                review_kind="proof",
                evidence_requirements=("independent",),
            )
        )
        resolved = registry.resolve("proof:short")
        self.assertTrue(resolved.capability.is_registered)
        self.assertEqual(("conceptual", "transfer"), resolved.capability.affected_dimensions)

    def test_unknown_capability_does_not_change_mastery(self):
        syllabus = {"concepts": {"limits": {"prerequisites": []}}}
        event = {
            "observation_id": "obs-unknown-capability",
            "concept_id": "limits",
            "capability_id": "provider:unknown",
            "task_type": "transfer",
            "outcome": "correct",
            "assistance": {"levels_revealed": []},
        }
        result = reduce_learning_state({}, syllabus, [event], {})
        state = result["concepts"]["limits"]
        self.assertEqual(0.0, state["mastery"]["conceptual"])
        self.assertEqual(0.0, state["mastery"]["transfer"])
        self.assertEqual(["provider:unknown"], result["unmapped_capability_events"])

    def test_custom_transfer_capability_drives_counters_maturity_and_status(self):
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {
                    "target_id": "source-analysis",
                    "prerequisites": [],
                    "capability_ids": ["source_interpretation"],
                }
            ],
            "assessment_capabilities": {
                "source_interpretation": {
                    "affected_dimensions": ["transfer"],
                    "review_kind": "source_interpretation",
                    "evidence_requirements": ["independent", "transfer"],
                }
            },
        }
        events = [
            {
                "schema_version": 2,
                "observation_id": f"source-analysis-{index}",
                "target_id": "source-analysis",
                "task_id": f"source-task-{index}",
                "capability_id": "source_interpretation",
                "task_type": "open_activity",
                "outcome": "correct",
                "assistance": {"levels_revealed": []},
            }
            for index in range(12)
        ]
        result = reduce_learning_state({}, syllabus, events, {})
        state = result["targets"]["source-analysis"]
        self.assertEqual(12, state["evidence"]["transfer_successes"])
        self.assertEqual(12, state["evidence_maturity"]["transferred"]["count"])
        self.assertGreater(state["mastery"]["transfer"], 0.85)
        self.assertEqual("mastered", state["mastery_status"])

    def test_exposed_custom_transfer_cannot_count_as_transfer_success(self):
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {
                    "target_id": "target",
                    "prerequisites": [],
                    "capability_ids": ["transfer:scenario"],
                }
            ],
            "assessment_capabilities": {
                "transfer:scenario": {
                    "affected_dimensions": ["transfer"],
                    "evidence_requirements": ["transfer"],
                }
            },
        }
        result = reduce_learning_state(
            {},
            syllabus,
            [
                {
                    "schema_version": 2,
                    "observation_id": "exposed-transfer",
                    "target_id": "target",
                    "task_id": "task",
                    "capability_id": "transfer:scenario",
                    "task_type": "open_activity",
                    "outcome": "correct",
                    "assessment_integrity": "explicit_exposure",
                    "assistance": {"levels_revealed": ["H5"]},
                }
            ],
            {},
        )
        state = result["targets"]["target"]
        self.assertEqual(0, state["evidence"]["transfer_successes"])
        self.assertEqual(0, state["evidence_maturity"]["transferred"]["count"])

    def test_legacy_exam_problem_keeps_legacy_counter_mapping(self):
        result = reduce_learning_state(
            {},
            {"schema_version": 1, "concepts": {"target": {"prerequisites": []}}},
            [
                {
                    "schema_version": 1,
                    "observation_id": "legacy-exam",
                    "concept_id": "target",
                    "task_id": "exam-task",
                    "task_type": "exam_problem",
                    "outcome": "correct",
                    "assistance": {"levels_revealed": []},
                }
            ],
            {},
        )
        evidence = result["concepts"]["target"]["evidence"]
        self.assertEqual(0, evidence["transfer_successes"])
        self.assertEqual(1, evidence["exam_successes"])


if __name__ == "__main__":
    unittest.main()
