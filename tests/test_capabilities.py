import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "math-study" / "scripts"))

from math_study_lib.capabilities import (  # noqa: E402
    AssessmentCapability,
    CapabilityRegistry,
)
from math_study_lib.reducer import reduce_learning_state  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
