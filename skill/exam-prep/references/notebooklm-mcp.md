# Optional NotebookLM MCP integration (P2)

NotebookLM MCP is optional. Core exam-prep operation must work when no
NotebookLM capability is available or when the host call fails.

The integration belongs to the agent host, not the deterministic Python CLI:

1. The agent skill detects whether the current host exposes NotebookLM MCP
   capabilities.
2. The host invokes the available capability without assuming a vendor tool
   name, transport, server package, or authentication mechanism.
3. The host normalizes returned citations, excerpts, locators, authority, and
   provider status into a SourceEvidenceEnvelope.
4. The host passes that JSON to the exam-prep ingest-source-evidence command.

Provider evidence is provenance input only. NotebookLM must never own,
overwrite, or become the source of canonical learner state. A failed or absent
capability produces an unavailable/failed envelope and the local
SourceProvider remains usable.
