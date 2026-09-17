# Optional NotebookLM MCP integration (P2)

NotebookLM MCP is optional. Core exam-prep operation must work when no
NotebookLM capability is available or when the host call fails.

## Consent and data boundary

Connector availability is not consent. Default to local, read-only operation.
Get explicit user confirmation separately before:

1. installation or setup of a provider;
2. authentication or cookie access;
3. sending course material, notes, prompts, or excerpts to the provider;
4. any external write, including `source_add`.

Before requesting confirmation, name the material that will leave the local
workspace, name the destination notebook/account, and state whether the action
is authentication, a read, or a write. Approval for one material/destination
pair does not authorize another, and approval to query existing sources does
not authorize upload. If confirmation is absent or declined, keep using the
local SourceProvider path.

The integration belongs to the agent host, not the deterministic Python CLI:

1. The agent skill detects whether the current host exposes NotebookLM MCP
   capabilities.
2. After the consent gate above, the host invokes the approved capability
   without assuming a vendor tool name, transport, server package, or
   authentication mechanism.
3. The host normalizes returned citations, excerpts, locators, authority, and
   provider status into a SourceEvidenceEnvelope.
4. The host passes that JSON to the exam-prep ingest-source-evidence command.

Provider evidence is provenance input only. NotebookLM must never own,
overwrite, or become the source of canonical learner state. A failed or absent
capability produces an unavailable/failed envelope and the local
SourceProvider remains usable.

## Status: experimental, never exercised end-to-end

Zero of the five audited with_skill scenario runs had a NotebookLM host
attached, so this whole integration path - the paragraph above and
everything below it - has no observed behavior on record. Treat it as
experimental until a real run exercises it.

## Recommended implementation

`jacob-bd/gemini-notebook-mcp-cli` (package and binary name
`notebooklm-mcp-cli` - Google renamed NotebookLM to Gemini Notebook in
2026, the repository followed, the package/binary names did not):

~~~bash
uv tool install notebooklm-mcp-cli
nlm setup add claude-code
nlm login
~~~

`uv` is an install-time tool for a human running this setup, not a runtime
dependency of the exam-prep CLI - `scripts/` stays stdlib-only either way.

Four of its tools are relevant here: `notebook_list`, `notebook_query`,
`source_get_content`, `source_add`. The rest of its surface (podcast/video
generation, quizzes, flashcards, collections management) is out of scope
for step 2 above - the host should not expose them as exam-prep sources.
Tool/feature counts and specific figures for this package drift by
release; check the upstream repository for the current numbers rather than
trusting a count restated here.

## Upstream caveats (read before relying on this for anything graded)

- It reaches internal, undocumented Google endpoints, not a published API,
  and the upstream project itself warns these can change without notice.
- Authentication is a Google account's own browser cookies, extracted from
  a managed browser session (Chrome DevTools Protocol, or an isolated
  Firefox profile) - not a scoped API credential. Whatever this tool can
  do, it does as that Google account. Cookies last roughly 2-4 weeks and
  need `nlm auth refresh`.
- Usage is metered on a rolling ~5-hour window plus a weekly cap, both
  upstream-owned and outside the exam-prep engine's control.
- Citation/locator format is not documented by the upstream project;
  treat every field it returns as best-effort, not a contract.

## Video sources

Only public YouTube videos with subtitles import, and only the text
transcript - no timestamp data comes back. A `source_add`'d video's
`location` is therefore a text-fragment locator (`span`/`locator` in
`source-ref.schema.json`), never a `timestamp`. Do not add a `timestamp`
field to `location`: the schema's `additionalProperties: true` on that
object would accept it silently, so this is the only guard against a
locator implying a level of citation precision (a point in the video) the
data never actually had.

## Boundary: NotebookLM-generated quizzes and flashcards are not assessments

NotebookLM's own quizzes and flashcards keep their own mastery model with
no documented export. They do not know `ExamBlueprint`, are not wired to
`verifier_registry`, carry no `spec_hash`, and give no hold-out guarantee
- importing them directly as `FrozenAssessment`s would silently bypass
every integrity mechanism `references/exam-optimizer.md` and
`references/verification.md` describe. The only path for a NotebookLM-
sourced question to become gradeable practice is the normal curriculum
one: draft it into a `curriculum-proposal`, `validate-curriculum`,
`apply-curriculum`, then `mint-assessments` - the same as any other
question, regardless of where it was drafted.

Nothing above changes core operation: without this integration, or with it
failing or absent, exam-prep works exactly as if it did not exist.
