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
        self.assertIn("\ndescription: Use when ", text.split("---", 2)[1])
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
        self.assertLessEqual(word_count, 500)

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

    def test_commands_reference_carries_the_full_observation_proposal_contract(self):
        # Audit finding 1: SKILL.md listed 7 of the 11 required fields and
        # nothing pointed at schemas/ or examples/, so a proposal built from
        # the prose alone failed on the first record-observation. The field
        # list is read from the schema and the constant, never re-typed, so
        # a newly required field fails here instead of shipping a doc that
        # quietly omits it.
        import json

        from exam_prep_lib.schema_validation import ENGINE_OWNED_PROPOSAL_FIELDS

        commands = (SKILL_ROOT / "references" / "commands.md").read_text(encoding="utf-8")
        schema = json.loads(
            (SKILL_ROOT / "schemas" / "observation-proposal-v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        missing_required = [
            field for field in schema["required"] if f"`{field}`" not in commands
        ]
        self.assertEqual(
            [], missing_required, "commands.md omits required proposal fields"
        )
        missing_engine_owned = [
            field
            for field in sorted(ENGINE_OWNED_PROPOSAL_FIELDS)
            if f"`{field}`" not in commands
        ]
        self.assertEqual(
            [], missing_engine_owned, "commands.md omits engine-owned rejected fields"
        )
        self.assertIn("examples/observation-proposal.json", commands)

    def test_commands_reference_documents_the_entrypoint_and_workspace_order(self):
        # Audit finding 4: every command was written bare (status, init)
        # and the workspace precedence lived only in READMEs the tutor never
        # loads - so a run could silently start a second empty course in the
        # wrong directory. The env var names are read out of the resolver, so
        # a new one cannot be added without documenting it.
        import inspect

        from exam_prep_lib import workspace as workspace_module

        commands = (SKILL_ROOT / "references" / "commands.md").read_text(encoding="utf-8")
        self.assertIn("scripts/exam_prep.py", commands)
        self.assertIn("--workspace", commands)
        source = inspect.getsource(workspace_module.resolve_workspace)
        env_names = re.findall(r'"([A-Z_]*WORKSPACE[A-Z_]*|[A-Z_]*PROJECT_ROOT)"', source)
        self.assertTrue(env_names, "could not read env var names from resolve_workspace")
        for name in env_names:
            self.assertIn(name, commands, f"commands.md does not document {name}")

    def test_skill_names_the_entrypoint_and_points_at_the_proposal_schema(self):
        # Audit findings 1 and 4 at the level the tutor reads first: SKILL.md
        # said "Run status first" without ever naming the script, and
        # described the observation payload as a prose field list missing
        # four required fields. Both are now one pointer each; the detail
        # lives in references/commands.md.
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("scripts/exam_prep.py", text)
        self.assertIn("--workspace", text)
        self.assertIn("schemas/observation-proposal-v2.schema.json", text)
        self.assertIn("examples/observation-proposal.json", text)

    def test_status_docs_match_the_public_payload_and_name_the_metadata_escape_hatch(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").casefold()
        commands = (SKILL_ROOT / "references" / "commands.md").read_text(
            encoding="utf-8"
        ).casefold()
        # The SKILL.md side is now covered by
        # test_status_keys_named_in_the_skill_exist_in_the_live_payload, which
        # compares backticked key names against a real status response instead
        # of matching a prose substring. What stays here is the audit-3 guard:
        # neither document may claim status returns the syllabus document.
        self.assertIn("course, session, targets", commands)
        for text in (skill, commands):
            self.assertNotIn("course, syllabus, session", text)
        self.assertIn("roadmap", skill)
        self.assertIn("full target metadata", commands)

    def test_verifier_scope_is_named_exactly(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        commands = (SKILL_ROOT / "references" / "commands.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Derivative/antiderivative checks", skill)
        self.assertIn("derivative/antiderivative answer check", commands)
        self.assertNotIn("Numeric/symbolic answer checks", skill)
        self.assertNotIn("numeric/symbolic answer check", commands)

    def test_verbatim_definitions_changes_the_pedagogy_contract(self):
        pedagogy = (SKILL_ROOT / "references" / "pedagogy.md").read_text(
            encoding="utf-8"
        ).casefold()
        self.assertIn("exam.verbatim_definitions", pedagogy)
        self.assertIn("when true", pedagogy)
        self.assertIn("verbatim", pedagogy)


    def _live_status_keys(self) -> set[str]:
        """Top-level keys the engine actually returns, not a re-typed list."""
        import contextlib
        import io
        import json as json_module
        import tempfile

        from exam_prep import main

        syllabus = SKILL_ROOT / "examples" / "mathematics-regression-syllabus.json"
        with tempfile.TemporaryDirectory() as temp_dir:

            def cli(*args):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(["--workspace", temp_dir, *args])
                self.assertEqual(code, 0, output.getvalue())
                return json_module.loads(output.getvalue())

            cli("init")
            cli("load-syllabus", str(syllabus))
            cli("start")
            return set(cli("status"))

    def test_status_keys_named_in_the_skill_exist_in_the_live_payload(self):
        # Audit finding 3, second pass: the prose list ("course, session,
        # targets, review queue, recurring mistakes, diagnostics") reads like
        # a key list but is not one - recurring mistakes nest per target and
        # "diagnostics" is three separate keys. Backticked names are compared
        # against a real status response, so a rename in the engine fails here
        # instead of sending the tutor after a key that does not exist.
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        sentence = re.search(r"read compact `status`:(.+?)\.\s", text, re.S)
        self.assertIsNotNone(sentence, "SKILL.md no longer names the status payload")
        named = re.findall(r"`([a-z_*]+)`", sentence.group(1))
        self.assertTrue(
            named, "SKILL.md describes the status payload in prose, not as key names"
        )
        live = self._live_status_keys()
        unknown = []
        for name in named:
            if name.startswith("*"):
                if not any(key.endswith(name.lstrip("*")) for key in live):
                    unknown.append(name)
            elif name not in live:
                unknown.append(name)
        self.assertEqual(
            [],
            unknown,
            f"SKILL.md names status keys the engine does not return: {unknown}; "
            f"live keys: {sorted(live)}",
        )

    def test_skill_tells_the_tutor_to_close_the_session(self):
        # The resume instruction reads last_session_summary, which only
        # end-session writes, but SKILL.md never mentioned the command - so a
        # tutor that never opens commands.md accumulates one session forever
        # and the exam post-mortem is never produced.
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("end-session", text)

    def test_skill_states_the_silent_next_minutes_default(self):
        # next --minutes has a default, so an omitted budget does not fail -
        # it silently invents one, which contradicts exam-optimizer.md's rule
        # that a stated budget is never rounded up. Read from the live parser
        # so a changed default fails here instead of drifting out of the doc.
        default = None
        for action in _parser()._actions:
            if isinstance(action, argparse._SubParsersAction):
                for option in action.choices["next"]._actions:
                    if "--minutes" in getattr(option, "option_strings", []):
                        default = option.default
        self.assertIsNotNone(default, "could not read the next --minutes default")
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("--minutes", text)
        self.assertIn(
            str(default),
            text,
            "SKILL.md does not state the budget assumed when --minutes is omitted",
        )

    def test_pre_init_contract_is_documented_where_the_tutor_reads_commands(self):
        # workspace_not_initialized is a real engine response that survived in
        # neither SKILL.md nor any reference, so a tutor calling a stateful
        # command too early reads an undocumented status and cannot tell a
        # normal refusal from a failure. The allowlist is read from the guard.
        import inspect

        from exam_prep import main

        source = inspect.getsource(main)
        guard = re.search(
            r"initialization_state != \"initialized\" and args\.command not in \{(.+?)\}",
            source,
            re.S,
        )
        self.assertIsNotNone(guard, "could not read the pre-init allowlist from main()")
        allowed = re.findall(r'"([a-z-]+)"', guard.group(1))
        self.assertTrue(allowed, "pre-init allowlist parsed empty")
        commands = (SKILL_ROOT / "references" / "commands.md").read_text(encoding="utf-8")
        self.assertIn("workspace_not_initialized", commands)
        missing = [name for name in allowed if not _mentions_command(commands, name)]
        self.assertEqual(
            [],
            missing,
            f"commands.md does not name the commands allowed before init: {missing}",
        )


if __name__ == "__main__":
    unittest.main()
