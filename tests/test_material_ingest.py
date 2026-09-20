import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_adapters.local_materials.extractor import ExtractedPage, ExtractedSource
from exam_prep_adapters.local_materials.ingest import build_envelope
from exam_prep_lib.provenance import AUTHORITY_RANKS
from exam_prep_lib.schema_validation import load_schema, validate_document


class MaterialIngestTests(unittest.TestCase):
    def test_envelope_uses_page_hash_and_safe_default_authority(self):
        source = ExtractedSource(
            "ekzamen_2024.pdf",
            "exam",
            (ExtractedPage(17, "Question 1\nCompute x"),),
            "file-hash",
            "pypdf",
            "3.0",
        )
        envelope = build_envelope((source,))
        payload = envelope.to_mapping()
        validate_document(payload, load_schema("source-evidence.schema.json"))
        evidence = payload["evidence"][0]
        self.assertEqual("general_reference", evidence["source_ref"]["authority"])
        self.assertIn("#p17", evidence["source_ref"]["source_id"])
        self.assertIn("configuration_hash", evidence["source_ref"]["location"])
        self.assertEqual("scored", evidence["source_ref"]["location"]["extraction"]["mode"])
        self.assertTrue(evidence["source_ref"]["location"]["extraction"]["candidates"])
        self.assertIn(evidence["source_ref"]["authority"], AUTHORITY_RANKS)

    def test_override_can_promote_an_exam_source(self):
        source = ExtractedSource("past.pdf", "exam", (ExtractedPage(1, "Q"),), "hash", None, None)
        authority = {"past.pdf": "official_exam_list"}
        envelope = build_envelope((source,), authority_map=authority)
        self.assertEqual("official_exam_list", envelope.evidence[0].source_ref.authority)


if __name__ == "__main__":
    unittest.main()
