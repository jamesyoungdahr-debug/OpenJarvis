# Handoff — Wake-word + Approval Hardening / New Tools

Working branch: `feat/wake-word-and-approval-hardening`, pushed to remote
`fork` (`https://github.com/jamesyoungdahr-debug/OpenJarvis`, a fork of
`open-jarvis/OpenJarvis`, which stays `origin` and is read-only for us).

This file lets a fresh session pick the work up without re-deriving context.
Delete it once this branch is merged or closed.

## Status

Both efforts are implemented and unit-tested. Nothing is merged. What's left is
a full-environment test run, manual smoke tests, and the PR (see "Next steps").

### Effort 1 — Wake-word detection (`jarvis chat --wake`): done

`jarvis chat --wake` waits for a wake word (default `hey_jarvis`, via
openWakeWord, offline) before recording. Commit `5588bfcf`. Not yet
smoke-tested with a live microphone.

Also in `5588bfcf`: the Windows desktop app no longer pops blank console
windows when it spawns `uv`, `ollama`, `git` or `where`.

### Effort 2 — Approval hardening + new tools: done

| Unit | What | Commit |
|------|------|--------|
| U1-U3 | Shared queued confirm callback, approval timeout config, confirmation turned on for 6 tools | `5588bfcf` |
| U3b | Fixed the confirmation-floor regression test (it skipped every case); dropped `system:admin` from read-only `channel_list`/`channel_status` | `31072d76` |
| U4 | Server and desktop tool confirmations queue in ApprovalStore instead of auto-approving; SSE tool calls run off the event loop | `45909d47` |
| U5 | `jarvis ask` confirmations queue in ApprovalStore | `2628bd58` |
| U6 | `jarvis agents ask --yes` records every auto-approval and never auto-approves `computer_use`/`hyperv_admin` | `3c75f047` |
| U7 | `jarvis approvals list/approve/deny` (acts on pending actions only) | `13ca3899` |
| U8 | `notify` tool (plyer) | `b6b4cdbe` |
| U9 | `clipboard` tool (pyperclip), always confirms, `system:admin` | `9d9b7bb9` |
| U10 | `send_email` tool (SMTP, or Gmail via the Google connector), always confirms | `031f4571` |
| U11 | `hyperv_query` tool plus the shared `tools/_hyperv.py` PowerShell runner | `3a6776e8` |
| U12 | `hyperv_admin` tool, always confirms, never remembered | `d8492840` |
| U13 | `computer_use` tool (pyautogui), always confirms, never remembered | `549b3ed7` |
| Wave 4 | `docs/user-guide/system-access.md` updated for all of the above | committed with this file |

## Decisions worth knowing

- `channel_list` and `channel_status` no longer require `system:admin`,
  because they are read-only. To reverse this, restore the entries in
  `security/capabilities.py`; they would then also need
  `requires_confirmation=True` to pass the floor test.
- The Hyper-V tools pass caller data to PowerShell only as
  `OPENJARVIS_HYPERV_*` environment variables. `hyperv_admin` selects the VM
  with an exact `-eq` name match, never `-Name`, so a wildcard can't select
  every VM.
- `computer_use` saves screenshots to a temp file and returns only the path.
  Tool results reach the model as text, so the agent can't see screenshots.
- New extras: `notify` and `clipboard` (both also added to `desktop`), and
  `computer-use` (deliberately not in `desktop`). `uv.lock` was not
  regenerated; CI's `uv sync` refreshes it.

## Environment notes

This machine has no `uv` environment and no built `openjarvis_rust`
extension. Verification used
`C:\Users\Liam\AppData\Local\Programs\Python\Python312\python.exe` with
`PYTHONPATH` set to the repo's `src`, plus ruff from the same Python.

These failures pre-date this work and come from the environment, not the code:

- anything that imports `openjarvis_rust` (scanners, rate limiter, capability
  policy, `test_security_wiring`, and 26 failures in `test_capabilities.py`
  that no unit changed)
- `tests/security/test_subprocess_sandbox.py`: `os.setsid` and `os.killpg`
  don't exist on Windows
- `tests/tools/test_web_search.py`: `ddgs` and `tavily` aren't installed
- `tests/tools/test_http_request.py`: `respx` isn't installed
- `tests/core/test_credentials.py::test_file_permissions`: fails on Windows
- `tests/tools/test_tool_timeout.py::test_repeated_timeouts_use_bounded_workers`:
  passes alone, flaky under load

A full-suite run also showed a few assertion mismatches (`511 == 448`,
`438 == 384`) that were never traced to a test. Pin those down before the PR.

Local model routing: the 4090 (`lmstudio-bridge`) was loaded with only a
17,920-token context, too small for `run_coding_task` on large files. Large
edits went to the 4080 Super (`lmstudio-4080super`, 92,672 tokens).

## Known issues outside this branch's scope

- Tool arguments and result metadata are persisted into traces
  (`ToolExecutor`, then `TraceCollector._on_tool_end`, then the trace store).
  That stores email bodies, clipboard text, typed text and `browser_screenshot`
  base64 images. Flagged as a separate task.
- The REST approve/deny endpoints in `server/approval_routes.py` will flip an
  already-resolved action. `jarvis approvals` refuses to.

## Next steps

1. On a machine with `uv`: run `uv sync --extra dev --extra desktop`, build the
   Rust extension, run `make test`, and trace the unexplained assertion
   mismatches above.
2. Manual smoke tests. None of these have run against the real thing yet:
   - `jarvis chat --wake` with a microphone
   - a confirmation-gated tool from the desktop app, approved once from the bell
     and once from `jarvis approvals`
   - `jarvis ask` timing out with no decision
   - `jarvis agents ask --yes` writing an approved row
   - `notify`, `clipboard`, `send_email` (SMTP and Gmail) and `computer_use`
   - `hyperv_admin` on a disposable VM (only not-found and wildcard rejection
     were exercised; `hyperv_query` was run for real)
3. Open a PR from `fork/feat/wake-word-and-approval-hardening` against
   `open-jarvis/OpenJarvis` `main`.
