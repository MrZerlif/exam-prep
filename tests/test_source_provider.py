import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "math-study" / "scripts"))

from math_study_lib.source_provider import (  # noqa: E402
    LocalSourceProvider,
    ProviderStatus,
    compute_source_coverage,
    normalize_source_evidence,
)


class SourceProviderTests(unittest.TestCase):
    def test_local_fallback_reads_structured_manifest_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sources.json").write_text(
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
