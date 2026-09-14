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
failed until the 2026-09-14 fix below; it works now. `rust/rust-toolchain.toml` pins Rust 1.88,
which rustup installed, and `maturin develop` builds `openjarvis_rust`; rebuild
it after every `uv sync`, which removes it. Test results are below.

## Follow-up fixes

- Trace redaction (`traces/redaction.py`): for confirmation-gated tools, saved
  traces keep argument names but redact values and results, and base64 data and
  very long strings are dropped for every tool. Live event subscribers still get
  the full data.
- The REST approve/deny endpoints return 409 for anything not pending, and the
  desktop approvals bell refreshes when a decision is rejected (`9c0c125c`).

## Issues found on Linux (2026-09-13, fixed 2026-09-14)

- **`desktop` couldn't install on Linux with Python 3.12 or newer.**
  openWakeWord 0.6.0 requires `tflite-runtime` on Linux, whose wheels stop at
  Python 3.11. Fixed with the combined guards Liam chose on 2026-09-14: the
  backend passes `inference_framework="onnx"` (tflite only for a `.tflite`
  keyword), `desktop` marks openwakeword
  `sys_platform != 'linux' or python_version < '3.12'`, and `[tool.uv]`
  `override-dependencies` drops `tflite-runtime`. Verified on Python 3.12.13:
  `uv sync` with `desktop` and `wake-word` installs openwakeword and
  onnxruntime but not tflite; a pip dry run of `.[desktop]` resolves without
  openwakeword; a pip dry run of `.[wake-word]` still fails on
  `tflite-runtime`, as `pyproject.toml` documents. openWakeWord hasn't loaded
  a real model yet, because downloading `hey_jarvis` waits for Liam's OK.
- **Lint:** the I001 error in
  `tests/security/test_capability_confirmation_floor.py` is fixed.
  `ruff check` and `ruff format --check` pass, and `tests/speech` plus the
  confirmation-floor test pass (91 passed, 6 skipped).
- **`uv.lock`** is regenerated with the override. It still lists
  `tflite-runtime` 2.14.0, but only behind the never-true marker, so
  `uv export` and `uv sync --all-extras --dry-run` never install it.

## Linux test results (2026-09-14)

Full suite with `pytest -n auto` (the `make test` command) on Python 3.12.13.
Logs and JUnit files are in `/home/liam/Projects/logs/jarvis/`.

- Branch `275215d6` plus the fixes below: 8,821 passed, 6 failed, 73 skipped.
- Baseline `6e42464c`, where the branch leaves `upstream/main`, run in a git
  worktree at `/home/liam/Projects/scratch/jarvis-baseline-6e42464c`: 8,579
  passed, 5 failed, 69 skipped.
- The 5 failures on both are `tests/evals/comparison/test_subprocess_runner.py`,
  which reads `/sys/class/powercap/intel-rapl:0/energy_uj`. Only root can read
  it on this machine, so it's the environment, not the code.
- The `511 == 448` and `438 == 384` mismatches from the Windows run didn't
  appear on Linux.
- `uv sync` removes the `maturin develop` build of `openjarvis_rust`, which
  turned most of the first run into `ModuleNotFoundError`. Rebuild it after
  every `uv sync`.

Fixed during the run:

- `record_decision`, an upstream proactive tool, approves or denies queued
  actions and can save "always approve" rules, but it didn't require
  confirmation. The confirmation-floor test caught it, and it now has
  `requires_confirmation=True`.
- The branch's server changes read `app_config.security`, which broke six
  upstream tests whose fake configs had no `security`. The fixtures in
  `tests/server/test_managed_agent_resolved_tools.py` and
  `tests/server/test_deep_research_tools_wiring.py` now include it, with a
  1-second approval timeout.
- Nine of the branch's Hyper-V tests failed only in the full parallel run,
  because `tests/tools/test_tool_registration.py` reloads every
  `openjarvis.tools` module and replaces `HyperVError` with a new class. The
  tests now reach it through the live module.

Still failing, waiting for Liam: `test_create_agent`. The branch made
`agent_spawn` require confirmation, and `POST /v1/agents` runs it with no
confirmation callback, so the route now returns 400 ("requires confirmation but
no confirmation callback is available"). `agent_kill` was already gated
upstream, so `DELETE /v1/agents/{id}` has the same limit. See open decision 5
in the plan.

## Linux live tests (2026-09-14)

- `notify` works on KDE Wayland. plyer falls back to `notify-send` because the
  Python `dbus` package isn't in `.venv` (it prints a warning), and an empty
  title is rejected. Log:
  `/home/liam/Projects/logs/jarvis/phase3-notify-20260914-0739.log`.
- The web approvals bell can't run yet: `node` and `npm` aren't installed
  (open decision 6 in the plan). The REST side is tested with `curl` instead.

## Next steps

The approved plan (2026-09-14) lives in
[`docs/wake-word-approval-hardening-plan.md`](docs/wake-word-approval-hardening-plan.md):
phases and units, open decisions for Liam, and the decision log. Update it as
units finish or decisions change, and keep this file's status sections current.
