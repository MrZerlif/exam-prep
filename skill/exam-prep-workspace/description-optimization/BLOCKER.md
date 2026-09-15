# Description-optimization measurement: BLOCKED (authentication)

## What was requested
Generate 20 trigger-eval queries (done — see `trigger-eval-set.json`, 9 should-trigger /
11 should-not-trigger, close-miss negatives per the brief), run `scripts/run_loop.py`
from skill-creator, and report `best_description` plus train/test scores. Not applied
to SKILL.md regardless of outcome, per instructions.

## What happened
`run_loop.py` (and the `run_eval.py` / `improve_description.py` it calls) invoke the
standalone `claude` CLI as a subprocess to probe triggering. On this machine that
subprocess run hit three separate problems, in order:

1. **`subprocess.Popen(["claude", ...])` fails with `WinError 2` on native Windows
   Python.** npm installs `claude` as `claude.cmd`/`claude.ps1`, not a bare `.exe`;
   Win32 `CreateProcess` (which Python's `subprocess` calls directly when
   `shell=False`) only auto-appends `.exe`, not the full `PATHEXT` list, so it never
   finds the command shim. **Fixed** by resolving the binary with `shutil.which("claude")`
   before building the `cmd` list, in both `run_eval.py` and `improve_description.py`.
2. **`select.select([process.stdout], ...)` fails with `WinError 10038`** ("operation
   attempted on something that is not a socket") — `select.select()` on Windows only
   supports sockets, never pipes/files, so the manual non-blocking-read loop in
   `run_eval.py:run_single_query` could never work on Windows at all. **Fixed** by
   replacing it with a background reader thread feeding a `queue.Queue`, polled with
   `queue.get(timeout=1.0)` instead of `select`.
3. **`Path.write_text(...)` crashes with `UnicodeEncodeError` ('charmap' codec)**
   when the generated HTML report contains a non-ASCII character (a '✗'), because
   `write_text` without an explicit encoding uses the Windows console's default
   codepage (cp1251 here), not UTF-8. **Fixed** by adding `encoding="utf-8"` to every
   `write_text(...)` call in `run_loop.py` and `generate_report.py`.

All three fixes were applied directly to skill-creator's own vendored scripts at
`...\skills-plugin\...\skills\skill-creator\scripts\` — **not** to anything in this
exam-prep repository, so they don't touch the audited skill and aren't part of this
branch's diff. They're recorded here so the fixes aren't lost and so a future run in
this same environment doesn't have to rediscover them.

With all three fixed, `run_eval.py` ran cleanly (no crashes) end-to-end across all
20 queries — but returned **`trigger_rate: 0.0` for every single query, including the
most unambiguous should-trigger ones** (see `blocked-diagnostic-evidence/sanity-run.json`).
That result is not real trigger-detection data. Manually reproducing one probe call
directly confirmed why:

```
$ claude -p "say hi" --output-format json
...,"is_error":true,...,"result":"Not logged in · Please run /login",...

$ claude auth status
{"loggedIn": false, "authMethod": "none", ...}
```

**The standalone `claude` CLI on PATH in this environment (`C:\Users\lfyzer\AppData\Roaming\npm\claude`)
is not authenticated**, and no `ANTHROPIC_API_KEY` is set in the environment either.
It is a separate installation from whatever credentials power this Claude Code
Desktop session, so nested `claude -p` subprocess calls fail authentication on every
single call — deterministically, silently (no crash, no exception), and identically
for should-trigger and should-not-trigger queries alike. That is exactly the pattern
in `blocked-diagnostic-evidence/sanity-run.json`: every query returns `trigger_rate: 0.0`,
so should-trigger queries all "fail" and should-not-trigger queries all "pass" — an
artifact of the auth failure, not a measurement of the skill's description.

## What this means for the report
No `best_description` and no real train/test trigger scores can be reported. Reporting
the 0%/100% numbers above as if they were real would be actively misleading, so they
are quarantined in `blocked-diagnostic-evidence/` rather than presented as results.

## How to unblock (for the user, not something I attempted myself)
Run `claude /login` in an interactive terminal on this machine (or set
`ANTHROPIC_API_KEY` in the environment `run_loop.py` inherits), then re-run:

```bash
python -m scripts.run_loop \
  --eval-set "<repo>/skill/exam-prep-workspace/description-optimization/trigger-eval-set.json" \
  --skill-path "<repo>/skill/exam-prep" \
  --model claude-sonnet-5 \
  --max-iterations 3 --num-workers 5 --timeout 45 --verbose \
  --results-dir "<repo>/skill/exam-prep-workspace/description-optimization/run-loop-out"
```
from the skill-creator directory, with `PYTHONUTF8=1` set (belt-and-suspenders on top
of the `write_text` fix). This does not require touching SKILL.md — the loop only
proposes a `best_description`; applying it is a separate, deliberate step.
