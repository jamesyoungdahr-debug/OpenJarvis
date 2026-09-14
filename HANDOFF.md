# Handoff — Wake-word + Approval Hardening / New Tools

Working branch: `feat/wake-word-and-approval-hardening`, pushed to the fork
(`https://github.com/jamesyoungdahr-debug/OpenJarvis`, a fork of
`open-jarvis/OpenJarvis`). In the Linux checkout at `/home/liam/Projects/jarvis`
the fork is remote `origin` and `open-jarvis/OpenJarvis` is remote `upstream`,
which is read-only for us. The earlier Windows checkout named them `fork` and
`origin`.

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

The Windows machine has no `uv` environment and no built `openjarvis_rust`
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

Linux (`/home/liam/Projects/jarvis`, the Strix Halo, set up 2026-09-13): the
system Python is 3.14, which the project doesn't support (`>=3.10,<3.14`).
`uv`, `rustup` and `ruff` come from Arch's `extra` repo. `uv sync --extra dev
--extra framework-comparison --extra server` (the same extras as `make setup`
and CI) works and builds `.venv` on Python 3.12.13. `uv sync --extra desktop`
fails; see "Open issues" below. `rust/rust-toolchain.toml` pins Rust 1.88,
which rustup installed, and `maturin develop` builds `openjarvis_rust`. The
first full pytest run was cut off by a session restart and left no results.

## Follow-up fixes

- Trace redaction (`traces/redaction.py`): for confirmation-gated tools, saved
  traces keep argument names but redact values and results, and base64 data and
  very long strings are dropped for every tool. Live event subscribers still get
  the full data.
- The REST approve/deny endpoints return 409 for anything not pending, and the
  desktop approvals bell refreshes when a decision is rejected (`9c0c125c`).

## Open issues found on Linux (2026-09-13)

- **`desktop` can't install on Linux with Python 3.12 or newer.** This branch
  added `openwakeword>=0.6` to the `desktop` extra. On Linux, openwakeword
  0.6.0 (the latest release) requires `tflite-runtime`, whose newest wheels
  stop at Python 3.11. That breaks `uv sync --extra desktop`,
  `scripts/quickstart.sh` and the desktop app's own `uv sync` in
  `frontend/src-tauri/src/lib.rs`. Linux CI (`ci.yml`) doesn't install
  `desktop`, so it won't catch this. `speech/openwakeword_backend.py` never
  passes `inference_framework`, so openWakeWord defaults to tflite and only
  falls back to onnx when `tflite_runtime` fails to import, which is why it
  worked on Windows. On 2026-09-14 Liam chose to combine the guards. The edits
  are on disk, uncommitted and untested, and their diffs match the specs: the
  backend passes `inference_framework="onnx"` (tflite only when the keyword
  ends in `.tflite`), with two new tests in
  `tests/speech/test_openwakeword_backend.py`; `desktop` marks openwakeword
  `sys_platform != 'linux' or python_version < '3.12'`; and a new `[tool.uv]`
  section sets `override-dependencies = ["tflite-runtime; sys_platform ==
  'never'"]`. Liam stopped the work before `uv lock`, the test run and the
  commit.
- **One lint error.** `ruff check` reports I001 (unsorted import block) in
  `tests/security/test_capability_confirmation_floor.py`. `ruff format
  --check` is clean. A fix moving the two `openjarvis` imports below
  `import openjarvis.tools` is on disk, uncommitted, but it left two blank
  lines after `import pytest`; remove one, then rerun `ruff check`.
- **`uv.lock` is out of date.** `uv sync` regenerated it (+203/-1 lines, the
  branch's new dependencies such as openwakeword, plyer, pyautogui and
  tflite-runtime). The change is left uncommitted. Rerun `uv lock` after the
  `pyproject.toml` fix above so tflite-runtime drops out, then commit it.

## Next steps (plan approved by Liam, 2026-09-14)

Local models write every edit through the `local-llm` scheduler, Claude reviews
each diff, and nothing is pushed unless Liam asks. Write long logs to
`/home/liam/Projects/logs/jarvis/`, never a session scratchpad, which a session
restart wipes. After each phase, commit locally and make a verified backup: on
Linux a full git bundle in `/home/liam/Projects/backups/jarvis`, named
`jarvis-<YYYYMMDD-HHMM>-<short commit>.bundle`; on Windows sync
`C:\projects\Open Jarvis Backup`.

### Phase 1: finish the paused fix

1. Remove the extra blank line in
   `tests/security/test_capability_confirmation_floor.py`.
2. Run `uv lock` and confirm `tflite-runtime` is gone from `uv.lock`.
3. Prove the fix on Linux with Python 3.12: `uv sync` with `--extra desktop`
   added installs; `uv sync --extra wake-word` installs openwakeword without
   tflite; a pip dry run of `.[desktop]` in a throwaway venv skips openwakeword.
4. Run `ruff check`, `ruff format --check` and `pytest tests/speech`.
5. Add a `CHANGELOG.md` Fixed entry and a `FORK_CHANGES.md` entry saying why,
   then update this file.

### Phase 2: full test suite on Linux

1. Run `make test` in the background, logging to
   `/home/liam/Projects/logs/jarvis/`.
2. Sort failures into environment problems and real bugs, and trace the
   `511 == 448` and `438 == 384` mismatches.
3. Redo the regression comparison against `6e42464c`, where this branch leaves
   `upstream/main`. The old baseline `5588bfcf` is the branch's first commit and
   already has changes. Use a separate git worktree with its own `.venv`, and
   run `tests/tools`, `tests/security`, `tests/cli`, `tests/core` and
   `tests/server` on both.
4. Hand real bugs to local models one unit at a time.

### Phase 3: live tests on Linux (KDE on Wayland)

Already done on Windows: the approval queue through the real
`jarvis approvals` command (approve, timeout, deny, and refusing to
re-approve), `notify`, `clipboard`, `computer_use` screenshots,
`hyperv_query`, `hyperv_admin` rejecting an unknown VM and a wildcard, and
`jarvis ask` against a real LM Studio model (approved and timed-out calls).

- `jarvis agents ask --yes` writing an approved row: take a scheduler lease,
  point jarvis only at the model the lease names, and release it afterwards.
- Approvals bell: run `jarvis serve` and the web frontend (`vite`), approve a
  gated tool from the bell, and check that a second decision returns 409.
- `notify`: should work, since `notify-send` is present.
- `clipboard`: needs `wl-clipboard`, which isn't installed. Liam decides.
- `computer_use` pointer and keyboard actions: pyautogui mostly fails on
  Wayland. Ask Liam first, since it moves his mouse, and record what happens.
- `send_email` over SMTP and Gmail: needs an account Liam sets up. Claude never
  enters credentials.

### Phase 4: deferred

- `jarvis chat --wake` with a microphone. Deferred on Linux: the Z13's
  built-in digital mic has no driver yet (kernel: "No matching ASoC machine
  driver found" for `acp70`), and its "Internal Microphone" input is only
  noise. Liam will fix the mic later; use a USB mic or Windows until then.
- On Windows: `hyperv_admin` state changes on a disposable VM, and the Windows
  desktop app's approvals bell.

### Phase 5: pull request (only when Liam asks)

1. Rebase on the latest `upstream/main` and rerun the tests.
2. Final pass on the docs, `CHANGELOG.md` and `FORK_CHANGES.md`.
3. Push to the fork (`origin` on Linux, `fork` on Windows), then open the pull
   request to `open-jarvis/OpenJarvis`.

### Open decisions for Liam

1. May `openwakeword` download its `hey_jarvis` onnx model to prove it loads
   without tflite?
2. Install `wl-clipboard`, or leave `clipboard` for Windows?
3. May `computer_use` move the pointer and type on this desktop?
4. Set up a test SMTP account now, or later?
