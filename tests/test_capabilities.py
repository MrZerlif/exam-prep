import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import main  # noqa: E402
from exam_prep_lib.capabilities import (  # noqa: E402
    AssessmentCapability,
    CapabilityRegistry,
    MASTERY_DIMENSIONS,
    capability_dimension_issues,
)
from exam_prep_lib.reducer import TASK_DIMENSIONS, reduce_learning_state  # noqa: E402


class CapabilityRegistryTests(unittest.TestCase):
    def test_unknown_registered_dimension_is_reported(self):
        syllabus = {
            "assessment_capabilities": {
                "custom": {"affected_dimensions": ["knowledge"]}
            }
        }
        self.assertEqual(
            ["capability 'custom' has unknown affected dimension 'knowledge'"],
            capability_dimension_issues(syllabus),
        )

    def test_scalar_affected_dimensions_is_rejected(self):
        syllabus = {
            "assessment_capabilities": {
                "custom": {"affected_dimensions": "conceptual"}
            }
        }
        issues = capability_dimension_issues(syllabus)
        self.assertTrue(any("must be an array" in issue for issue in issues))

    def test_open_capability_without_descriptor_remains_allowed(self):
        syllabus = {
            "learning_targets": [
                {"target_id": "t1", "capability_ids": ["proof:short"]}
            ]
        }
        self.assertEqual([], capability_dimension_issues(syllabus))

    def test_mastery_dimensions_are_the_canonical_runtime_keys(self):
        self.assertEqual(
            ("conceptual", "procedural", "recall", "transfer", "speed"),
            MASTERY_DIMENSIONS,
        )

    def test_from_syllabus_reports_rejected_descriptors_instead_of_silently_dropping(self):
        syllabus = {
            "assessment_capabilities": {
                "custom": {"affected_dimensions": ["knowledge"]}
            }
        }
        registry = CapabilityRegistry.from_syllabus(syllabus)
        self.assertEqual(
            ["capability 'custom' has unknown affected dimension 'knowledge'"],
            list(registry.rejected_descriptors()),
        )
        self.assertFalse(registry.resolve("custom").capability.is_registered)

    def test_from_syllabus_rejected_descriptors_is_empty_for_a_clean_syllabus(self):
        syllabus = {
            "assessment_capabilities": {
                "custom": {"affected_dimensions": ["conceptual"]}
            }
        }
        registry = CapabilityRegistry.from_syllabus(syllabus)
        self.assertEqual((), registry.rejected_descriptors())
        self.assertTrue(registry.resolve("custom").capability.is_registered)
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


    def test_invalid_descriptor_is_non_promoting_like_an_unknown_capability(self):
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {
                    "target_id": "limits",
                    "prerequisites": [],
                    "capability_ids": ["broken:custom"],
                }
            ],
            "assessment_capabilities": {
                "broken:custom": {"affected_dimensions": ["knowledge"]}
            },
        }
        event = {
            "schema_version": 2,
            "observation_id": "obs-invalid-descriptor",
            "target_id": "limits",
            "task_id": "limits-task",
            "capability_id": "broken:custom",
            "task_type": "open_activity",
            "outcome": "correct",
            "assistance": {"levels_revealed": []},
        }

        result = reduce_learning_state({}, syllabus, [event], {})

        state = result["targets"]["limits"]
        self.assertEqual(0, state["evidence"]["independent_successes"])
        self.assertEqual(0, state["evidence_maturity"]["demonstrated"]["count"])
        self.assertEqual("unseen", state["mastery_status"])
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

    def test_status_shows_rejected_capability_descriptors_as_diagnostics(self):
        # A bad syllabus can reach the workspace outside `load-syllabus`
        # (which already guards its own entry point) - e.g. a hand-edited
        # state file. `status` must still surface the problem instead of
        # silently building a registry that drops the capability.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def run_cli(*args):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(["--workspace", str(root), *args])
                self.assertEqual(code, 0, output.getvalue())
                return json.loads(output.getvalue())

            run_cli("init")
            state_syllabus_path = root / ".exam-prep" / "syllabus.json"
            syllabus = json.loads(state_syllabus_path.read_text(encoding="utf-8"))
            syllabus["assessment_capabilities"] = {
                "custom": {"affected_dimensions": ["knowledge"]}
            }
            state_syllabus_path.write_text(json.dumps(syllabus), encoding="utf-8")

            result = run_cli("status")
            self.assertIn(
                "capability 'custom' has unknown affected dimension 'knowledge'",
                result["capability_diagnostics"],
            )

    def test_status_shows_unmapped_capability_events_after_record_observation(self):
        # Pins the full path end to end: an observation against a capability
        # the syllabus never declared is accepted (not rejected at input),
        # does not move mastery, and is visible in `status` as an unmapped
        # counter rather than silently disappearing. The reducer-level half
        # of this is already covered by test_unknown_capability_does_not_change_mastery;
        # this closes the loop through the actual CLI/store round trip.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            syllabus = {
                "schema_version": 2,
                "learning_targets": [
                    {"target_id": "limits", "title": "Limits", "prerequisites": []}
                ],
            }
            syllabus_path = root / "syllabus.json"
            syllabus_path.write_text(json.dumps(syllabus), encoding="utf-8")
            proposal = {
                "schema_version": 2,
                "observation_id": "obs-unmapped-1",
                "target_id": "limits",
                "task_id": "task-1",
                "capability_id": "provider:mystery",
                "task_type": "open_activity",
                "outcome": "correct",
                "assistance": {
                    "requested": False,
                    "levels_revealed": [],
                    "scaffold_types": [],
                    "partial_transformation_shown": False,
                    "full_solution_viewed": False,
                },
                "error_tags": [],
                "diagnostic_confidence": "high",
                "source_refs": ["teacher:worksheet-1"],
            }
            proposal_path = root / "proposal.json"
            proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

            def run_cli(*args):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(["--workspace", str(root), *args])
                self.assertEqual(code, 0, output.getvalue())
                return json.loads(output.getvalue())

            run_cli("init")
            run_cli("load-syllabus", str(syllabus_path))
            run_cli("record-observation", str(proposal_path))
            status = run_cli("status")

            target_state = status["targets"]["targets"]["limits"]
            self.assertEqual(0.0, target_state["mastery"]["conceptual"])
            self.assertEqual(0, target_state["evidence"]["independent_successes"])
            self.assertEqual(
                ["provider:mystery"], status["targets"]["unmapped_capability_events"]
            )

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

    def test_twenty_successful_delayed_recalls_on_tickets_grant_no_transfer_mastery(self):
        # 2.2's acceptance criterion, verbatim: delayed recall of a
        # memorized ticket is recall, not novel transfer. The old mapping
        # (recall, transfer) silently overstated readiness for exactly the
        # ticket-list scenario this whole phase exists to support.
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {"target_id": "ticket-3", "prerequisites": [], "capability_ids": ["delayed_recall"]}
            ],
        }
        events = [
            {
                "schema_version": 2,
                "observation_id": f"delayed-{index}",
                "target_id": "ticket-3",
                "task_id": f"delayed-task-{index}",
                "capability_id": "delayed_recall",
                "task_type": "delayed_recall",
                "outcome": "correct",
                "assistance": {"levels_revealed": []},
            }
            for index in range(20)
        ]
        result = reduce_learning_state({}, syllabus, events, {})
        state = result["targets"]["ticket-3"]
        self.assertEqual(0, state["evidence"]["transfer_successes"])
        self.assertEqual(0.0, state["mastery"]["transfer"])
        # Recall credit and retention signalling must survive the fix -
        # only the transfer over-credit is being removed.
        self.assertEqual(20, state["evidence"]["delayed_recall_successes"])
        self.assertGreater(state["mastery"]["recall"], 0.8)
        self.assertEqual(20, state["evidence_maturity"]["retained"]["count"])

    def test_delayed_transfer_capability_grants_transfer_mastery(self):
        # The transfer credit delayed_recall used to grant by default is
        # still available - just opt-in, via a capability named for what it
        # actually demonstrates.
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {"target_id": "ticket-4", "prerequisites": [], "capability_ids": ["delayed_transfer"]}
            ],
        }
        events = [
            {
                "schema_version": 2,
                "observation_id": f"delayed-transfer-{index}",
                "target_id": "ticket-4",
                "task_id": f"delayed-transfer-task-{index}",
                "capability_id": "delayed_transfer",
                "task_type": "delayed_transfer",
                "outcome": "correct",
                "assistance": {"levels_revealed": []},
            }
            for index in range(12)
        ]
        result = reduce_learning_state({}, syllabus, events, {})
        state = result["targets"]["ticket-4"]
        self.assertEqual(12, state["evidence"]["transfer_successes"])
        self.assertGreater(state["mastery"]["transfer"], 0.5)
        self.assertEqual(12, state["evidence_maturity"]["retained"]["count"])
        self.assertEqual(12, state["evidence_maturity"]["transferred"]["count"])

    def test_task_dimensions_and_default_capability_registry_agree(self):
        # The trap this phase calls out by name: delayed_recall's dimension
        # mapping is duplicated in reducer.TASK_DIMENSIONS (legacy v1
        # task_type lookup) and capabilities.CapabilityRegistry.with_defaults
        # (v2 capability lookup). Nothing forces them to move together -
        # this walks every TASK_DIMENSIONS entry against the live default
        # registry (public API, not a re-typed copy) so a future edit to
        # only one side fails here instead of silently reintroducing a
        # v1/v2 semantics gap.
        registry = CapabilityRegistry.with_defaults()
        for task_type, dimensions in TASK_DIMENSIONS.items():
            with self.subTest(task_type=task_type):
                resolution = registry.resolve(task_type)
                self.assertTrue(
                    resolution.capability.is_registered,
                    f"{task_type!r} is in TASK_DIMENSIONS but not registered as a default capability",
                )
                self.assertEqual(dimensions, resolution.capability.affected_dimensions)

    def test_independent_delayed_recall_counts_as_exam_success_for_ticket_list(self):
        # 2.3: for a ticket-list oral exam, the exam *is* independently
        # reproducing the ticket from memory - counts_as_exam_success must
        # derive this from the blueprint, not only from a hardcoded
        # "exam_problem" id.
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {"target_id": "ticket-5", "prerequisites": [], "capability_ids": ["delayed_recall"]}
            ],
        }
        event = {
            "schema_version": 2,
            "observation_id": "ticket-exam-success",
            "target_id": "ticket-5",
            "task_id": "delayed-task",
            "capability_id": "delayed_recall",
            "task_type": "delayed_recall",
            "outcome": "correct",
            "assistance": {"levels_revealed": []},
        }
        course = {"exam": {"question_model": "ticket_list"}}
        result = reduce_learning_state(course, syllabus, [event], {})
        self.assertEqual(1, result["targets"]["ticket-5"]["evidence"]["exam_successes"])

    def test_hinted_delayed_recall_does_not_count_as_exam_success(self):
        # Open question from the 2.3 review: exam success must require
        # independence, not just outcome=="correct" - the same
        # assistance-band distinction 8.1a makes for "task done". A ticket
        # reproduced with a hint (H1+) is not yet what an unaided oral exam
        # demands.
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {"target_id": "ticket-5b", "prerequisites": [], "capability_ids": ["delayed_recall"]}
            ],
        }
        course = {"exam": {"question_model": "ticket_list"}}
        independent_event = {
            "schema_version": 2,
            "observation_id": "ticket-independent",
            "target_id": "ticket-5b",
            "task_id": "delayed-task-independent",
            "capability_id": "delayed_recall",
            "task_type": "delayed_recall",
            "outcome": "correct",
            "assistance": {"levels_revealed": []},
        }
        hinted_event = {
            **independent_event,
            "observation_id": "ticket-hinted",
            "task_id": "delayed-task-hinted",
            "assistance": {"levels_revealed": ["H1"]},
        }
        independent_result = reduce_learning_state(course, syllabus, [independent_event], {})
        hinted_result = reduce_learning_state(course, syllabus, [hinted_event], {})
        self.assertEqual(
            1, independent_result["targets"]["ticket-5b"]["evidence"]["exam_successes"]
        )
        self.assertEqual(
            0, hinted_result["targets"]["ticket-5b"]["evidence"]["exam_successes"]
        )

    def test_delayed_recall_does_not_count_as_exam_success_without_ticket_list(self):
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {"target_id": "ticket-6", "prerequisites": [], "capability_ids": ["delayed_recall"]}
            ],
        }
        event = {
            "schema_version": 2,
            "observation_id": "no-ticket-model",
            "target_id": "ticket-6",
            "task_id": "delayed-task",
            "capability_id": "delayed_recall",
            "task_type": "delayed_recall",
            "outcome": "correct",
            "assistance": {"levels_revealed": []},
        }
        for course in ({}, {"exam": {"question_model": "problem_set"}}):
            with self.subTest(course=course):
                result = reduce_learning_state(course, syllabus, [event], {})
                self.assertEqual(0, result["targets"]["ticket-6"]["evidence"]["exam_successes"])


if __name__ == "__main__":
    unittest.main()