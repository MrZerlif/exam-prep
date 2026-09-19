import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.provenance import provenance_label


class ProvenanceAxisTests(unittest.TestCase):
    def test_source_requires_a_locator(self):
        self.assertEqual("[SOURCE]", provenance_label(source_refs=[{"source_id": "s1", "locator": "p.1"}]))
        self.assertEqual("[SUPPLEMENT]", provenance_label(source_refs=[{"source_id": "s1"}], supplement=True))

    def test_generated_origin_always_wins(self):
        self.assertEqual("[GENERATED]", provenance_label(source_refs=[{"source_id": "s1", "locator": "p.1"}], origin="model_generated"))
        self.assertEqual("[GENERATED]", provenance_label(source_refs=[]))


if __name__ == "__main__":
    unittest.main()
