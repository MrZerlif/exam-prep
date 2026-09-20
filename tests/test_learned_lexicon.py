import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep import main
from exam_prep_lib.schema_validation import SchemaError


class LearnedLexiconTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.materials = self.root / "materials"
        self.materials.mkdir()
        self.proposal = self.root / "learned.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--workspace", str(self.root), *args])
        self.assertEqual(0, code, output.getvalue())
        return json.loads(output.getvalue())

    def write_proposal(self, value):
        self.proposal.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def test_unclassified_material_index_is_bounded_and_not_envelope(self):
        self.run_cli("init")
        for index in range(35):
            (self.materials / f"tentamen-{index}.txt").write_text(
                "Opgave 1\nOpgave 2\nOpgave 3\n", encoding="utf-8"
            )
        result = self.run_cli("ingest-materials", str(self.materials))
        summary = result["index"]["unclassified"]
        self.assertLessEqual(len(summary["file_stems"]), 20)
        self.assertLessEqual(len(summary["repeated_heads"]), 20)
        self.assertLessEqual(len(summary["unit_candidates"]), 20)
        self.assertTrue(all(len(value) <= 160 for values in summary.values() if isinstance(values, list) for value in values))
        self.assertNotIn("unclassified", result.get("envelope", {}))
        persisted = json.loads((self.root / ".exam-prep" / "material_index.json").read_text(encoding="utf-8"))
        self.assertIn("unclassified", persisted)

    def test_apply_rejects_classifications_questions_and_scores(self):
        self.run_cli("init")
        for invalid in (
            {"classification": {"file": "exam"}},
            {"questions": []},
            {"scores": {"x": 1}},
        ):
            with self.subTest(invalid=invalid):
                self.write_proposal({"schema_version": 1, "language": "nl", "slots": {"kind.exam": ["tentamen"]}, **invalid})
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SchemaError):
                        main(["--workspace", str(self.root), "apply-lexicon", str(self.proposal)])
        self.assertFalse((self.root / ".exam-prep" / "lexicons").exists())

    def test_apply_is_idempotent_and_dry_run_does_not_write(self):
        self.run_cli("init")
        payload = {
            "schema_version": 1,
            "language": "nl",
            "slots": {
                "kind.exam": ["tentamen"],
                "kind.solution": ["uitwerking"],
                "unit.points": ["punten"],
            },
        }
        self.write_proposal(payload)
        dry = self.run_cli("apply-lexicon", str(self.proposal), "--dry-run")
        self.assertTrue(dry["dry_run"])
        learned_path = self.root / ".exam-prep" / "lexicons" / "learned-nl.json"
        self.assertFalse(learned_path.exists())
        self.run_cli("apply-lexicon", str(self.proposal))
        first = learned_path.read_bytes()
        self.run_cli("apply-lexicon", str(self.proposal))
        self.assertEqual(first, learned_path.read_bytes())

    def test_overlay_is_used_on_reingest_and_survives_rebuild(self):
        self.run_cli("init")
        payload = {
            "schema_version": 1,
            "language": "nl",
            "slots": {
                "kind.exam": ["tentamen"],
                "kind.solution": ["uitwerking"],
                "unit.points": ["punten"],
            },
        }
        self.write_proposal(payload)
        self.run_cli("apply-lexicon", str(self.proposal))
        (self.materials / "tentamen-2024.txt").write_text("Tentamen 1\n", encoding="utf-8")
        (self.materials / "uitwerking-2024.txt").write_text("Uitwerking 1\n", encoding="utf-8")
        first = self.run_cli("ingest-materials", str(self.materials))
        self.assertEqual("nl", first["language"]["value"])
        kinds = {entry["relative_path"]: entry["kind"] for entry in first["index"]["entries"]}
        self.assertEqual("exam", kinds["tentamen-2024.txt"])
        self.assertEqual("solution", kinds["uitwerking-2024.txt"])
        index_path = self.root / ".exam-prep" / "material_index.json"
        before = index_path.read_bytes()
        self.run_cli("ingest-materials", str(self.materials))
        self.assertEqual(before, index_path.read_bytes())
        learned_path = self.root / ".exam-prep" / "lexicons" / "learned-nl.json"
        learned_before = learned_path.read_bytes()
        self.run_cli("rebuild")
        self.assertEqual(learned_before, learned_path.read_bytes())

        draft_path = self.root / "draft.json"
        self.run_cli(
            "draft-assessments",
            str(self.materials),
            "--out",
            str(draft_path),
        )
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        self.assertEqual(1, len(draft["assessments"]))

        self.run_cli("hydrate-source", "tentamen-2024.txt", "--materials-dir", str(self.materials))
        evidence_path = self.root / ".exam-prep" / "source_evidence.jsonl"
        evidence = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual("nl", evidence[-1]["source_ref"]["location"]["language"])

    def test_validate_reports_learned_overlay(self):
        self.run_cli("init")
        self.write_proposal({"schema_version": 1, "language": "nl", "slots": {"kind.exam": ["tentamen"]}})
        self.run_cli("apply-lexicon", str(self.proposal))
        report = self.run_cli("validate")
        self.assertIn("nl", report["learned_lexicons"])
        self.assertEqual("ok", next(item["status"] for item in report["checks"] if item["name"] == "learned_lexicons"))


if __name__ == "__main__":
    unittest.main()
