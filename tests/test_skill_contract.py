import argparse
import re
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
SKILL_ROOT = ROOT / "skill" / "exam-prep"
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from exam_prep import _parser  # noqa: E402


def _registered_commands() -> list[str]:
    for action in _parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return sorted(action.choices.keys())
    return []


def _mentions_command(text: str, command: str) -> bool:
    escaped = re.escape(command)
    return bool(
        re.search(rf"`{escaped}(?![a-z-])", text)
        or re.search(rf"exam_prep\.py\s+{escaped}(?![a-z-])", text)
    )


class SkillContractTests(unittest.TestCase):
    def test_skill_contract_has_valid_frontmatter_and_is_concise(self):
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: exam-prep\n"))
        self.assertLess(len(text.splitlines()), 220)
        required_phrases = (
            "status", "initialized", "validate-curriculum", "apply-curriculum",
            "record-observation", "observations.jsonl", "attempt-first", "full solution",
            "references/pedagogy.md", "references/exam-optimizer.md",
            "references/verification.md", "references/source-of-truth.md",
            "references/notebooklm-mcp.md",
        )
        for phrase in required_phrases:
            self.assertIn(phrase, text)
        word_count = len(re.findall(r"\S+", text))
        self.assertGreater(word_count, 0)
        self.assertLessEqual(word_count, 700)

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

    def test_skill_selects_track_by_question_model_instead_of_one_ladder(self):
        # 2.1: the old unconditional "Use short cycles: intuition, worked
        # example, faded scaffold, guided problem, independent problem,
        # transfer, exam problem, delayed recall" sentence forced a
        # practice-problem ladder onto every exam format, including
        # ticket_list ones with no problems at all. SKILL.md must select a
        # track by question_model and defer the stages themselves to
        # pedagogy.md, not hardcode the ladder inline.
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("question_model", text)
        self.assertIn("ticket_list", text)
        self.assertNotIn(
            "Use short cycles: intuition, worked example, faded scaffold, "
            "guided problem, independent problem, transfer, exam problem, "
            "delayed recall",
            text,
        )

    def test_pedagogy_defines_both_tracks(self):
        text = (SKILL_ROOT / "references" / "pedagogy.md").read_text(encoding="utf-8")
        self.assertIn("ticket_list", text)
        self.assertIn("problem_set", text)
        self.assertIn("intuition", text)
        self.assertIn("unprompted reproduction", text)

    def test_every_parser_command_is_documented_in_skill_or_a_linked_reference(self):
        # 9.1: same class as the engine_fields meta-test - a command the
        # tutor is never told about is a command it will never call, no
        # matter how correct the underlying implementation is. Reads the
        # live argparse command list (not a re-typed copy) so a future
        # command added to _parser() without documentation fails here
        # instead of silently shipping unreachable.
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        referenced_paths = sorted(set(re.findall(r"references/[\w-]+\.md", skill_text)))
        self.assertTrue(referenced_paths, "SKILL.md should link at least one reference")
        combined_text = skill_text
        for relative_path in referenced_paths:
            combined_text += "\n" + (SKILL_ROOT / relative_path).read_text(encoding="utf-8")

        commands = _registered_commands()
        self.assertTrue(commands, "could not read the command list from _parser()")
        undocumented = [
            command for command in commands if not _mentions_command(combined_text, command)
        ]
        self.assertEqual(
            [],
            undocumented,
            f"commands missing from SKILL.md and its linked references: {undocumented}",
        )


if __name__ == "__main__":
    unittest.main()
