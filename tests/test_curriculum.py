import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.curriculum import (  # noqa: E402
    CurriculumValidationError,
    apply_curriculum_proposal,
    build_syllabus_from_proposal,
    validate_curriculum_proposal,
)
from exam_prep_lib.storage import StudyStore  # noqa: E402
from exam_prep import load_state  # noqa: E402


def valid_proposal():
    return {
        "schema_version": 1,
        "proposal_id": "proposal-1",
        "source_refs": [
            {
                "source_id": "teacher:week-1",
                "authority": "teacher_material",
                "locator": "page 2",
            }
        ],
        "learning_targets": [
            {
                "target_id": "limits",
                "title": "Limits",
                "prerequisites": [],
                "capability_ids": ["independent_problem"],
                "exam_question_ids": ["q1"],
                "source_refs": ["teacher:week-1"],
            },
            {
                "target_id": "derivatives",
                "title": "Derivatives",
                "prerequisites": ["limits"],
                "capability_ids": ["independent_problem"],
                "exam_question_ids": ["q2"],
                "source_refs": ["teacher:week-1"],
            },
        ],
        "assessment_capabilities": [],
        "exam_questions": [
            {
                "question_id": "q1",
                "target_ids": ["limits"],
                "capability_ids": ["independent_problem"],
            },
            {
                "question_id": "q2",
                "target_ids": ["derivatives"],
                "capability_ids": ["independent_problem"],
            },
        ],
    }


class CurriculumTests(unittest.TestCase):
    def assert_invalid(self, proposal, fragment):
        with self.assertRaises(CurriculumValidationError) as caught:
            validate_curriculum_proposal(proposal)
        self.assertTrue(any(fragment in issue for issue in caught.exception.issues))

    def test_valid_target_graph_and_exam_mapping_builds_syllabus(self):
        proposal = valid_proposal()
        catalog = [
            {
                "source_id": "teacher:week-1",
                "authority": "teacher_material",
                "provider_id": "local",
            }
        ]
        validated = validate_curriculum_proposal(
            proposal, verified_source_catalog=catalog
        )
        syllabus = build_syllabus_from_proposal(
            validated, verified_source_catalog=catalog
        )
        self.assertEqual(2, len(syllabus["learning_targets"]))
        derivatives = next(item for item in syllabus["learning_targets"] if item["target_id"] == "derivatives")
        self.assertEqual(["limits"], derivatives["prerequisites"])
        self.assertEqual(["q2"], derivatives["exam_question_ids"])
        self.assertTrue(syllabus["source_coverage"]["targets_without_sources"] == [])

    def test_proposal_cannot_self_authorize_a_source(self):
        validated = validate_curriculum_proposal(valid_proposal())
        self.assertIn(
            "teacher:week-1",
            " ".join(validated["validation"]["coverage_gaps"]),
        )

    def test_verified_catalog_recognizes_sources_and_wins_authority_conflicts(self):
        proposal = valid_proposal()
        catalog = [
            {
                "source_id": "teacher:week-1",
                "authority": "official_exam_list",
                "provider_id": "trusted-provider",
                "version": "2026",
            }
        ]
        validated = validate_curriculum_proposal(
            proposal, verified_source_catalog=catalog
        )
        self.assertFalse(
            any(
                "teacher:week-1" in gap
                for gap in validated["validation"]["coverage_gaps"]
            )
        )
        self.assertTrue(
            any("authority" in warning for warning in validated["validation"]["warnings"])
        )
        syllabus = build_syllabus_from_proposal(
            validated, verified_source_catalog=catalog
        )
        self.assertEqual(
            "official_exam_list", syllabus["source_refs"][0]["authority"]
        )

    def test_apply_curriculum_uses_local_manifest_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = StudyStore.for_exam_prep(root)
            manifest = root / ".exam-prep" / "sources.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "sources": [
                            {
                                "source_id": "teacher:week-1",
                                "authority": "official_exam_list",
                                "provider_id": "local",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = apply_curriculum_proposal(store, valid_proposal())
            self.assertFalse(result.report.coverage_gaps)
            self.assertEqual(
                "official_exam_list", result.syllabus["source_refs"][0]["authority"]
            )

    def test_apply_curriculum_recognizes_ingested_notebooklm_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = StudyStore.for_exam_prep(root)
            source_id = "notebook:week-1"
            proposal = valid_proposal()
            proposal["source_refs"] = [
                {"source_id": source_id, "authority": "teacher_material"}
            ]
            for target in proposal["learning_targets"]:
                target["source_refs"] = [source_id]
            store.append_source_evidence(
                {
                    "evidence_id": "notebook-evidence",
                    "provider_id": "notebooklm-mcp",
                    "status": "ok",
                    "source_ref": {
                        "source_id": source_id,
                        "authority": "general_reference",
                        "provider_id": "notebooklm-mcp",
                    },
                }
            )
            result = apply_curriculum_proposal(store, proposal)
            self.assertFalse(result.report.coverage_gaps)
            self.assertEqual(
                "general_reference", result.syllabus["source_refs"][0]["authority"]
            )

    def test_apply_curriculum_preserves_unresolved_coverage_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            proposal = valid_proposal()
            proposal["source_refs"] = [
                {"source_id": "missing:source", "authority": "teacher_material"}
            ]
            for target in proposal["learning_targets"]:
                target["source_refs"] = ["missing:source"]
            result = apply_curriculum_proposal(store, proposal)
            self.assertTrue(
                any("missing:source" in gap for gap in result.report.coverage_gaps)
            )
            self.assertIn(
                "missing:source",
                result.syllabus["source_coverage"]["unknown_source_refs"],
            )

    def test_missing_prerequisite_is_rejected(self):
        proposal = valid_proposal()
        proposal["learning_targets"][1]["prerequisites"] = ["missing"]
        self.assert_invalid(proposal, "unknown prerequisite")

    def test_prerequisite_cycle_is_rejected(self):
        proposal = valid_proposal()
        proposal["learning_targets"][0]["prerequisites"] = ["derivatives"]
        self.assert_invalid(proposal, "cycle")

    def test_unknown_source_ref_is_a_coverage_gap(self):
        proposal = valid_proposal()
        proposal["learning_targets"][0]["source_refs"] = ["missing:source"]
        validated = validate_curriculum_proposal(proposal)
        self.assertFalse(validated["validation"]["errors"])
        self.assertTrue(validated["validation"]["coverage_gaps"])

    def test_open_capability_id_is_accepted_without_mastery_mapping(self):
        proposal = valid_proposal()
        proposal["learning_targets"][0]["capability_ids"] = ["proof:short"]
        validated = validate_curriculum_proposal(proposal)
        self.assertFalse(validated["validation"]["errors"])
        self.assertTrue(any("proof:short" in warning for warning in validated["validation"]["warnings"]))

        proposal["assessment_capabilities"] = [
            {
                "capability_id": "proof:short",
                "affected_dimensions": ["conceptual"],
                "response_type": "free_text",
                "review_kind": "proof",
                "evidence_requirements": ["independent"],
            }
        ]
        validate_curriculum_proposal(proposal)

    def test_exam_question_mapping_is_error_but_coverage_gaps_are_diagnostics(self):
        proposal = valid_proposal()
        proposal["exam_questions"][0]["target_ids"] = ["missing"]
        self.assert_invalid(proposal, "exam question")

        proposal = valid_proposal()
        proposal["learning_targets"][0]["source_refs"] = []
        validated = validate_curriculum_proposal(proposal)
        self.assertTrue(validated["validation"]["coverage_gaps"])

    def test_curriculum_updates_are_incremental_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            first = apply_curriculum_proposal(store, valid_proposal())
            targets = json.loads(
                (store.state_path / "targets.json").read_text(encoding="utf-8")
            )
            self.assertIn("mastery", targets["targets"]["limits"])
            self.assertIn("evidence_maturity", targets["targets"]["limits"])
            self.assertTrue((store.state_path / "current.json").exists())
            self.assertEqual(1, len(list(store.revisions_path.glob("[0-9]*"))))
            repeat = apply_curriculum_proposal(store, valid_proposal())
            self.assertTrue(first.changed)
            self.assertFalse(repeat.changed)
            self.assertEqual(1, len(list(store.revisions_path.glob("[0-9]*"))))

            proposal = valid_proposal()
            proposal["proposal_id"] = "proposal-2"
            proposal["learning_targets"].append(
                {
                    "target_id": "integrals",
                    "title": "Integrals",
                    "prerequisites": ["derivatives"],
                    "capability_ids": ["independent_problem"],
                    "exam_question_ids": [],
                    "source_refs": ["teacher:week-1"],
                }
            )
            updated = apply_curriculum_proposal(store, proposal)
            self.assertTrue(updated.changed)
            self.assertEqual(3, len(updated.syllabus["learning_targets"]))
            repeat_updated = apply_curriculum_proposal(store, proposal)
            self.assertFalse(repeat_updated.changed)

    def test_apply_curriculum_preserves_existing_evidence_without_corrective_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StudyStore.for_exam_prep(Path(tmp))
            apply_curriculum_proposal(store, valid_proposal())
            store.append_observation(
                {
                    "schema_version": 2,
                    "observation_id": "limits-practice",
                    "target_id": "limits",
                    "task_id": "limits-task",
                    "capability_id": "independent_problem",
                    "task_type": "independent_problem",
                    "outcome": "correct",
                    "assistance": {"levels_revealed": []},
                    "error_tags": [],
                    "diagnostic_confidence": "high",
                    "source_refs": [],
                },
                "session-1",
                "2026-09-13T12:00:00+00:00",
                None,
                None,
            )
            proposal = valid_proposal()
            proposal["proposal_id"] = "proposal-2"
            proposal["learning_targets"].append(
                {
                    "target_id": "integrals",
                    "title": "Integrals",
                    "prerequisites": ["derivatives"],
                    "capability_ids": ["independent_problem"],
                    "exam_question_ids": [],
                    "source_refs": ["teacher:week-1"],
                }
            )
            result = apply_curriculum_proposal(store, proposal)
            self.assertTrue(result.changed)
            before_load = len(list(store.revisions_path.glob("[0-9]*")))
            _, _, _, _, derived, _ = load_state(store)
            after_load = len(list(store.revisions_path.glob("[0-9]*")))
            self.assertEqual(before_load, after_load)
            self.assertEqual(
                1, derived["targets"]["limits"]["evidence"]["independent_successes"]
            )


if __name__ == "__main__":
    unittest.main()
