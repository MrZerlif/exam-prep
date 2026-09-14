import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.source_provider import (  # noqa: E402
    LocalSourceProvider,
    ProviderStatus,
    build_verified_source_catalog,
    compute_source_coverage,
    normalize_source_evidence,
)


class SourceProviderTests(unittest.TestCase):
    def test_local_fallback_reads_structured_manifest_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / ".exam-prep" / "sources.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "sources": [
                            {
                                "source_id": "teacher:week-1",
                                "authority": "teacher_material",
                                "locator": "week-1.pdf#page=2",
                                "title": "Week 1 notes",
                                "tags": ["limits"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            provider = LocalSourceProvider(root)
            self.assertEqual(ProviderStatus("local", True, None), provider.health())
            self.assertEqual(["teacher:week-1"], [ref.source_id for ref in provider.list_sources()])
            self.assertEqual(
                ["teacher:week-1"],
                [item.source_ref.source_id for item in provider.retrieve("limits")],
            )

    def test_root_level_source_manifest_is_not_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sources.json").write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "source_id": "root-only",
                                "authority": "teacher_material",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            provider = LocalSourceProvider(root)
            self.assertEqual([], provider.list_sources())

    def test_minimal_and_notebooklm_source_refs_are_accepted_without_inference(self):
        minimal = normalize_source_evidence(
            {
                "provider_id": "local",
                "status": "ok",
                "evidence": [{"source_ref": {"source_id": "s1"}}],
            }
        )
        self.assertEqual("unknown", minimal.evidence[0].source_ref.authority)

        notebooklm = normalize_source_evidence(
            {
                "provider_id": "notebooklm-mcp",
                "status": "ok",
                "evidence": [
                    {
                        "source_ref": {
                            "source_id": "s1",
                            "provider": "notebooklm-mcp",
                            "location": {"page": 1},
                        }
                    }
                ],
            }
        )
        ref = notebooklm.evidence[0].source_ref
        self.assertEqual("unknown", ref.authority)
        self.assertEqual({"page": 1}, ref.location)
        self.assertEqual("", ref.locator)

    def test_missing_provider_result_becomes_graceful_envelope(self):
        envelope = normalize_source_evidence(
            {
                "provider_id": "not-installed",
                "status": "unavailable",
                "diagnostics": ["NotebookLM MCP capability not available"],
                "evidence": [],
            }
        )
        self.assertEqual("unavailable", envelope.status)
        self.assertEqual([], envelope.evidence)
        self.assertTrue(envelope.diagnostics)

    def test_structured_source_location_and_complete_envelope_metadata_survive_normalization(self):
        envelope = normalize_source_evidence(
            {
                "envelope_id": "env-1",
                "provider_id": "recorded-host",
                "status": "ok",
                "retrieved_at": "2026-09-13T12:00:00+00:00",
                "capabilities_used": ["search", "citation"],
                "retrieval_id": "retrieval-1",
                "evidence": [
                    {
                        "source_ref": {
                            "source_id": "teacher:week-1",
                            "authority": "teacher_material",
                            "provider_id": "recorded-host",
                            "version": "v2",
                            "location": {"page": 3, "heading": "Limits"},
                        },
                        "excerpt": "A limit describes...",
                        "retrieval_id": "citation-1",
                        "confidence": 0.8,
                    }
                ],
            }
        )
        mapping = envelope.to_mapping()
        self.assertEqual("env-1", mapping["envelope_id"])
        self.assertEqual(["search", "citation"], mapping["capabilities_used"])
        ref = mapping["evidence"][0]["source_ref"]
        self.assertEqual("v2", ref["version"])
        self.assertEqual({"page": 3, "heading": "Limits"}, ref["location"])
        self.assertEqual("citation-1", mapping["evidence"][0]["retrieval_id"])

    def test_null_capabilities_used_becomes_empty_array(self):
        envelope = normalize_source_evidence({
            "provider_id": "missing",
            "status": "unavailable",
            "evidence": [],
            "diagnostics": [],
            "capabilities_used": None,
        })
        self.assertEqual([], envelope.capabilities_used)

    def test_scalar_capabilities_used_becomes_diagnostic(self):
        envelope = normalize_source_evidence({
            "provider_id": "provider",
            "status": "failed",
            "evidence": [],
            "capabilities_used": "search",
        })
        self.assertEqual([], envelope.capabilities_used)
        self.assertTrue(any("capabilities_used" in item for item in envelope.diagnostics))

    def test_non_object_envelope_is_graceful_failure(self):
        envelope = normalize_source_evidence(["not", "an", "object"])
        self.assertEqual("failed", envelope.status)
        self.assertEqual([], envelope.evidence)

    def test_invalid_unit_numbers_become_diagnostics(self):
        for field, value in (
            ("relevance", True),
            ("relevance", "0.5"),
            ("confidence", -0.1),
            ("confidence", 1.1),
        ):
            with self.subTest(field=field, value=value):
                envelope = normalize_source_evidence({
                    "provider_id": "provider",
                    "status": "ok",
                    "evidence": [{
                        "source_ref": {"source_id": "s1"},
                        field: value,
                    }],
                })
                self.assertIsNone(getattr(envelope.evidence[0], field))
                self.assertTrue(any(field in item for item in envelope.diagnostics))
    def test_teacher_material_outranks_official_list_regardless_of_order(self):
        official = {
            "source_id": "same",
            "authority": "official_exam_list",
        }
        teacher = {
            "source_id": "same",
            "authority": "teacher_material",
        }

        for values in ([official, teacher], [teacher, official]):
            with self.subTest(values=values):
                catalog = build_verified_source_catalog(values)
                self.assertEqual("teacher_material", catalog["same"].authority)
    def test_coverage_gaps_are_explicit_and_unknown_refs_are_reported(self):
        gaps = compute_source_coverage(
            {
                "concepts": {
                    "limits": {"source_refs": ["teacher:week-1"]},
                    "derivatives": {"source_refs": []},
                }
            },
            available_source_ids={"teacher:week-1"},
        )
        self.assertEqual(["derivatives"], gaps["targets_without_sources"])
        self.assertEqual([], gaps["unknown_source_refs"])

        gaps = compute_source_coverage(
            {"concepts": {"limits": {"source_refs": ["missing:source"]}}},
            available_source_ids={"teacher:week-1"},
        )
        self.assertEqual(["missing:source"], gaps["unknown_source_refs"])


if __name__ == "__main__":
    unittest.main()
