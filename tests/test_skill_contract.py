from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class SkillContractRedTest(unittest.TestCase):
    def test_skill_entrypoint_is_not_implemented_before_green_phase(self):
        self.assertFalse((ROOT / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
