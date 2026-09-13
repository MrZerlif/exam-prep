from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
SKILL_ROOT = ROOT / "skill" / "exam-prep"


class SkillContractTests(unittest.TestCase):
    def test_skill_contract_has_valid_frontmatter_and_is_concise(self):
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: exam-prep\n"))
        self.assertLess(len(text.splitlines()), 220)

    def test_skill_mentions_engine_owned_evidence_boundary(self):
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("LLM produces structured observation", text)
        self.assertIn("deterministic state engine", text)
        self.assertIn("observations.jsonl", text)
        self.assertIn("record-observation", text)

    def test_skill_links_operational_references(self):
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for reference in (
            "references/pedagogy.md",
            "references/exam-optimizer.md",
            "references/verification.md",
            "references/source-of-truth.md",
        ):
            self.assertIn(reference, text)


if __name__ == "__main__":
    unittest.main()
