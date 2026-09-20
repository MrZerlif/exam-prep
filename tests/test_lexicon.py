import sys
import unittest
import json
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1] / "skill" / "exam-prep" / "scripts"))

from exam_prep_lib.defaults import VERB_SLOT_TO_CAPABILITY, VERB_SLOT_TO_QTYPE
from exam_prep_lib.lexicon import LEXICON_SLOTS, load, validate
from exam_prep_lib.schema_validation import load_schema, validate_document
from exam_prep_lib.semantics import best_slot, match
from exam_prep_adapters.local_materials.questions import _qtype
from exam_prep_lib.assessment_draft import _capability


class LexiconTests(unittest.TestCase):
    def test_ru_and_en_lexicons_are_available_and_complete(self):
        self.assertEqual(("de", "en", "es", "fr", "it", "ja", "pl", "pt", "ru", "tr", "uk", "zh"), load_available())
        schema = load_schema("lexicon.schema.json")
        for language in load_available():
            lexicon = load(language)
            self.assertEqual(set(LEXICON_SLOTS), set(lexicon.by_slot))
            self.assertTrue(all(lexicon.by_slot[slot] for slot in LEXICON_SLOTS))
            raw = json.loads((Path(__file__).parents[1] / "skill" / "exam-prep" / "config" / "lexicons" / f"{language}.json").read_text(encoding="utf-8"))
            validate_document(raw, schema)

    def test_duplicate_without_weights_is_an_error(self):
        raw = valid_raw()
        raw["slots"]["kind.exam"] = ["same"]
        raw["slots"]["kind.homework"] = ["same"]
        with self.assertRaises(ValueError):
            validate(raw)

    def test_duplicate_with_explicit_weights_is_a_warning(self):
        raw = valid_raw()
        raw["slots"]["kind.exam"] = [{"token": "same", "weight": 0.3}]
        raw["slots"]["kind.homework"] = [{"token": "same", "weight": 0.5}]
        warnings = validate(raw)
        self.assertTrue(any("ambiguous_lexicon_token" in warning for warning in warnings))

    def test_semantics_matches_exact_then_loose_and_resolves_overlap_by_weight(self):
        english = load("en")
        exact = match("verb.definition", "Define the limit", english)
        self.assertIsNotNone(exact)
        self.assertTrue(exact.exact)
        loose = match("verb.definition", "défine the limit", english)
        self.assertIsNotNone(loose)
        self.assertFalse(loose.exact)
        self.assertEqual("kind.homework", best_slot("kind.", "Exercise 2", english).slot)

    def test_one_verb_match_drives_qtype_and_capability(self):
        english = load("en")
        result = best_slot("verb.", "Prove the statement", english)
        self.assertIsNotNone(result)
        self.assertEqual("proof", VERB_SLOT_TO_QTYPE[result.slot])
        self.assertEqual("independent_problem", VERB_SLOT_TO_CAPABILITY[result.slot])
        question = SimpleNamespace(kind="homework", prompt="Prove the statement")
        self.assertEqual("proof", _qtype(question.prompt, "en"))
        self.assertEqual("independent_problem", _capability(question, "en"))


def load_available():
    from exam_prep_lib.lexicon import available

    return available()


def valid_raw():
    return {
        "schema_version": 1,
        "language": "xx",
        "word_boundaries": True,
        "normalization": {"fold": {}, "strip_marks": True},
        "slots": {slot: [slot.replace(".", "-")] for slot in LEXICON_SLOTS},
    }


if __name__ == "__main__":
    unittest.main()
