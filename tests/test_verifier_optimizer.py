import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import main  # noqa: E402
from exam_prep_lib.capabilities import (  # noqa: E402
    AssessmentCapability,
    CapabilityRegistry,
)
from exam_prep_lib.optimizer import rank_source_aware_targets  # noqa: E402
from exam_prep_lib.scheduler import compute_priority  # noqa: E402
from exam_prep_lib.verifier_registry import (  # noqa: E402
    VerifierRegistry,
    verify_request,
)


class VerifierAndOptimizerTests(unittest.TestCase):
    def test_verifier_resolution_is_optional_and_unknown_is_unavailable(self):
        registry = VerifierRegistry()
        registry.register("always-pass", lambda request: {"status": "verified"})
        self.assertEqual({"status": "verified"}, registry.verify("always-pass", {}))
        self.assertIsNone(registry.resolve("missing"))
        self.assertEqual(
            {"status": "unavailable", "reason": "no verifier registered"},
            registry.verify("missing", {}),
        )

    def test_default_calculation_capability_resolves_numerical_verifier(self):
        capability = CapabilityRegistry.with_defaults().resolve("calculation").capability
        self.assertEqual("math.numerical", capability.verifier_id)
        result = verify_request(
            {
                "capability_id": "calculation",
                "kind": "derivative",
                "expression": "x**2",
                "derivative": "2*x",
                "samples": [0.5, 1.5],
                "tolerance": 1e-4,
            }
        )
        self.assertEqual("passed", result["status"])

    def test_cli_verification_uses_capability_and_rejects_unknown_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            request_path = Path(tmp) / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "capability_id": "provider:unknown",
                        "kind": "derivative",
                        "expression": "x**2",
                        "derivative": "2*x",
                    }
                ),
                encoding="utf-8",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["--workspace", tmp, "init"]))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--workspace", tmp, "verify", str(request_path)])
            self.assertEqual(0, code)
            self.assertEqual("unavailable", json.loads(output.getvalue())["status"])

    def test_cli_verify_uses_shared_defaults_and_rejects_bad_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["--workspace", tmp, "init"]))
            request_path = Path(tmp) / "request.json"
            request_path.write_text(
                json.dumps({"kind": "derivative", "expression": "abs(x)", "derivative": "1"}),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(0, main(["--workspace", tmp, "verify", str(request_path)]))
            payload = json.loads(output.getvalue())
            self.assertEqual("failed", payload["status"])
            self.assertEqual(1e-4, payload["checks"]["finite_difference"]["tolerance"])

            request_path.write_text(
                json.dumps({"kind": "derivative", "expression": "x**2", "derivative": "2*x", "tolerance": "abc"}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                main(["--workspace", tmp, "verify", str(request_path)])

    def test_numerical_verifier_names_missing_fields(self):
        with self.assertRaisesRegex(ValueError, "derivative"):
            verify_request({"kind": "derivative", "expression": "x**2"})

    def test_source_aware_optimizer_exposes_coverage_and_authority(self):
        ranked = rank_source_aware_targets(
            {
                "concepts": {
                    "limits": {
                        "importance": 0.9,
                        "frequency": 0.9,
                        "expected_points": 10,
                        "source_refs": [
                            {
                                "source_id": "teacher:week-1",
                                "authority": "teacher_material",
                            }
                        ],
                    },
                    "derivatives": {
                        "importance": 0.8,
                        "frequency": 0.8,
                        "expected_points": 8,
                        "source_refs": [],
                    },
                }
            },
            {"limits": {"mastery": {"conceptual": 0.1}}, "derivatives": {}},
            {"limits": {}, "derivatives": {}},
            {},
            datetime.now(timezone.utc),
            25,
            available_source_ids={"teacher:week-1"},
        )
        self.assertEqual("derivatives", ranked[0]["target_id"])
        self.assertTrue(ranked[0]["coverage_gap"])
        self.assertEqual("limits", ranked[1]["target_id"])
        self.assertEqual(6, ranked[1]["source_authority_rank"])

    def test_optimizer_uses_capability_required_mastery_dimensions(self):
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {
                    "target_id": "oral-target",
                    "prerequisites": [],
                    "capability_ids": ["oral_definition"],
                    "importance": 0.8,
                    "frequency": 0.8,
                    "expected_points": 8,
                }
            ],
            "assessment_capabilities": {
                "oral_definition": {"affected_dimensions": ["conceptual"]}
            },
        }
        priority = compute_priority(
            "oral-target",
            syllabus,
            {
                "oral-target": {
                    "mastery": {
                        "conceptual": 0.2,
                        "procedural": 0.95,
                        "recall": 0.95,
                        "transfer": 0.95,
                    }
                }
            },
            {},
            {},
            datetime.now(timezone.utc),
            25,
        )
        self.assertEqual(["conceptual"], priority["required_mastery_dimensions"])
        self.assertAlmostEqual(0.8, priority["mastery_gap"])

    def test_prerequisite_unlock_value_lifts_shared_foundation(self):
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {
                    "target_id": "foundation",
                    "prerequisites": [],
                    "importance": 0.2,
                    "frequency": 0.2,
                    "expected_points": 2,
                },
                {
                    "target_id": "advanced-a",
                    "prerequisites": ["foundation"],
                    "importance": 0.95,
                    "frequency": 0.95,
                    "expected_points": 10,
                },
                {
                    "target_id": "advanced-b",
                    "prerequisites": ["foundation"],
                    "importance": 0.9,
                    "frequency": 0.9,
                    "expected_points": 10,
                },
            ],
        }
        priority = compute_priority(
            "foundation",
            syllabus,
            {"foundation": {"mastery": {"conceptual": 0.2}}},
            {},
            {},
            datetime.now(timezone.utc),
            25,
        )
        self.assertGreater(priority["prerequisite_unlock_value"], 1.0)

    def test_orthogonal_evidence_facets_change_confidence_without_replacing_mastery(self):
        syllabus = {
            "schema_version": 2,
            "learning_targets": [
                {
                    "target_id": "transfer-target",
                    "prerequisites": [],
                    "capability_ids": ["transfer-capability"],
                    "importance": 0.8,
                    "frequency": 0.8,
                    "expected_points": 8,
                }
            ],
            "assessment_capabilities": {
                "transfer-capability": {
                    "affected_dimensions": ["transfer"],
                    "evidence_requirements": ["retained", "transfer"],
                }
            },
        }
        state = {
            "mastery": {
                "conceptual": 0.4,
                "procedural": 0.4,
                "recall": 0.4,
                "transfer": 0.4,
            },
            "evidence_maturity": {
                "demonstrated": {"count": 1},
                "retained": {"count": 0},
                "transferred": {"count": 1},
            },
        }
        mature = {
            **state,
            "evidence_maturity": {
                "demonstrated": {"count": 1},
                "retained": {"count": 2},
                "transferred": {"count": 2},
            },
        }
        early_priority = compute_priority(
            "transfer-target",
            syllabus,
            {"transfer-target": state},
            {},
            {},
            datetime.now(timezone.utc),
            25,
        )
        mature_priority = compute_priority(
            "transfer-target",
            syllabus,
            {"transfer-target": mature},
            {},
            {},
            datetime.now(timezone.utc),
            25,
        )
        self.assertEqual(0.0, early_priority["evidence_confidence"]["retained"])
        self.assertEqual(1.0, mature_priority["evidence_confidence"]["retained"])
        self.assertGreater(
            mature_priority["evidence_factor"], early_priority["evidence_factor"]
        )
        self.assertEqual(early_priority["mastery_gap"], mature_priority["mastery_gap"])


if __name__ == "__main__":
    unittest.main()
