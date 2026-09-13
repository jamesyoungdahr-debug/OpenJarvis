# Handoff — Wake-word + Approval Hardening / New Tools

Working branch: `feat/wake-word-and-approval-hardening`
Pushed to remote `fork` (`https://github.com/jamesyoungdahr-debug/OpenJarvis`,
a fork of `open-jarvis/OpenJarvis`, which remains `origin`, read-only for us).

This file exists so a fresh session (possibly on a different machine) can
pick this work back up without re-deriving context. Delete it once both
efforts below have shipped and this branch is merged/closed out.

## Environment notes (read first)

This development machine does **not** have `uv`, a project venv, or the
Rust/PyO3 extension (`openjarvis_rust`) built. Full `make test`/`uv sync`
could not be run here. Verification instead used:
- A secondary Python 3.12 install at
  `C:\Users\Liam\AppData\Local\Programs\Python\Python312\python.exe`, which
  happens to already have `click`/`rich`/`pydantic` (enough for most of
  `tests/`), plus `numpy`, `pyyaml`, `tomlkit`, `ruff` installed into it
  ad hoc during this work.
- Run tests via: `$env:PYTHONPATH = "C:\projects\Open Jarvis\src"; pytest <path> -v`
  (PowerShell), or the equivalent with `PYTHONPATH` exported in bash.
- Lint via: that same Python's `-m ruff check` / `-m ruff format --check`.
- Any test requiring `tests/security/` or `tests/cli/` transitively imports
  the whole `openjarvis.cli`/`openjarvis` package tree via
  `tests/conftest.py` and `cli/__init__.py` — this pulled in `tomlkit` and
  `pyyaml` as the only two extra installs actually needed so far.
- One pre-existing, unrelated test failure appears whenever the full
  `tests/cli/test_chat_cmd.py` suite runs:
  `TestChatAgents::test_tool_agent_uses_configured_policy_rate_and_identity`
  fails with `ModuleNotFoundError: No module named 'openjarvis_rust'` — this
  is an environment gap (needs `maturin develop`), not a regression from
  this work. Confirmed present before any of these changes too.
- **Before continuing on a machine with a real `uv` environment**: run
  `uv sync --extra dev --extra desktop` (or similar) and re-run everything
  below via `make test`/`pytest` properly — the lighter verification path
  above is a substitute, not a replacement.

Desktop app (Tauri) build: works on this machine (Rust toolchain via
rustup, VS Build Tools already present). `npm run tauri build` in
`frontend/` produces working `.msi`/NSIS installers. A real bug was found
and fixed there too (see "Also fixed" below).

## Effort 1 — Wake-word detection (`jarvis chat --wake`): DONE, tested, not yet merged

Fully implemented and verified per the plan that was in
`C:\Users\Liam\.claude\plans\agile-percolating-meadow.md` (local-machine
path, may not exist on a different machine — see condensed summary below).

**What it does**: `jarvis chat --wake` waits for a wake word (default
`hey_jarvis`, via openWakeWord — offline, no API key) before recording,
instead of the existing press-Enter-to-speak flow. `--wake` implies
`--voice`.

**Files added**:
- `src/openjarvis/speech/_wake_stubs.py` — `WakeWordBackend` ABC, `WakeDetection` dataclass
- `src/openjarvis/speech/openwakeword_backend.py` — concrete openWakeWord backend
- `src/openjarvis/speech/wake_word_io.py` — the new continuous-listening loop
- `tests/speech/test_wake_stubs.py`, `test_openwakeword_backend.py`, `test_wake_word_io.py`

**Files edited**:
- `src/openjarvis/core/registry.py` — new `WakeWordRegistry`
- `src/openjarvis/core/config.py` — `SpeechConfig.wake_word` / `wake_word_backend` / `wake_word_sensitivity`
- `src/openjarvis/speech/_discovery.py` — new `get_wake_word_backend()`
- `src/openjarvis/speech/__init__.py` — registers `openwakeword_backend`
- `src/openjarvis/cli/_voice_chat.py` — `VoiceSession.get_wake_backend()`, new `wait_for_wake()`
- `src/openjarvis/cli/chat_cmd.py` — new `--wake` flag, REPL wiring
- `pyproject.toml` — new `wake-word` extra (`openwakeword`, `onnxruntime`, `numpy`, `sounddevice`); also added to `desktop` extra
- `tests/conftest.py` — `WakeWordRegistry` added to the autouse registry-clear fixture

**Test status**: all new + touched tests pass (112/113 across
`tests/speech/` + `tests/cli/test_chat_cmd.py`; the 1 failure is the
pre-existing `openjarvis_rust` gap noted above, unrelated).

**Not done**: real end-to-end smoke test with a live mic (needs
`pip install -e '.[wake-word]'` + a working mic on a machine with a real
env). Daemon/always-on and desktop-overlay integration were explicitly
scoped out of that plan as future work.

## Also fixed — Windows desktop app blank console-window bug

Unrelated to either effort above, found while smoke-testing the built
Windows installer: `frontend/src-tauri/src/lib.rs` spawns `uv`/`ollama`/
`git`/`where` as console-subsystem children without suppressing the
console window, so Windows pops up a blank `cmd.exe` window for each.
Fixed with a new `hide_console_window()` helper (sets
`CREATE_NO_WINDOW`/`0x08000000` via `creation_flags` on Windows, no-op
elsewhere) called at every spawn site. Rebuilt and confirmed no more blank
windows appear; `cargo test --release` in `frontend/src-tauri` still passes
(47/47). This is a Rust-side change (`frontend/src-tauri/src/lib.rs`) —
already included in the working tree / this commit.

## Effort 2 — Approval hardening + new tools: IN PROGRESS

Full plan (condensed here; the authoritative version is the local plan file
at `C:\Users\Liam\.claude\plans\agile-percolating-meadow.md` on the
machine that ran this — if unavailable, this section plus the unit list
below should be enough to reconstruct it).

### Why

`ToolExecutor` (`src/openjarvis/tools/_stubs.py`) only really asks a human
when a tool sets `requires_confirmation=True` AND a real callback is wired.
Today only `jarvis chat` wires a real one; the HTTP server, the desktop app
(a thin HTTP client to the server), `jarvis ask`, and `jarvis agent ask`'s
default all pass `lambda _prompt: True` — i.e. they lie that a human
approved something. Also, only 3 tools set `requires_confirmation=True` at
all, missing several equally dangerous ones. A working, persistent,
cross-process `ApprovalStore` + REST API already exists but was never wired
into the generic confirmation gate — only into the proactive agent's own
queue.

### Units — status

| # | What | Status |
|---|------|--------|
| U1 | `src/openjarvis/security/approval_callback.py` (shared queued confirm-callback, `NEVER_REMEMBER_TOOLS`) | **Done, tested** (8/8 pass, `tests/security/test_approval_callback.py`) |
| U2 | `SecurityConfig.approval_timeout_seconds` / `approval_poll_interval_seconds` (`core/config.py`) | **Done, tested** |
| U3 | Flip `requires_confirmation=True` on 6 tools: `docker_shell_exec`, `file_write`, `apply_patch`, `agent_spawn` (not send/list), `execute_pending_actions`, `channel_send` | **Done, tested** (86/86 pass across the 6 touched tool test files + new `test_docker_shell_exec.py`) |
| U3b | Cross-cutting regression guard `tests/security/test_capability_confirmation_floor.py` (any tool requiring `SYSTEM_ADMIN`/`CHANNEL_SEND` capability must also require confirmation) | **Written but BROKEN — see "Known issue" below, needs a fix before it's real coverage** |
| U4 | Rewire 4 `lambda _prompt: True` sites in `src/openjarvis/server/agent_manager_routes.py` → `make_queued_confirm_callback(...)` | **Not started** |
| U5 | Rewire 2 sites in `src/openjarvis/cli/ask.py` | **Not started** |
| U6 | `src/openjarvis/cli/agent_cmd.py` `--yes` path → audited auto-approve (still instant, but records an approved row) | **Not started** |
| U7 | New `jarvis approvals` CLI command (`src/openjarvis/cli/approvals_cmd.py`, register in `cli/__init__.py`) | **Not started** |
| U8 | `src/openjarvis/tools/notify.py` (plyer-based desktop notification tool) + test | **Not started** |
| U9 | `src/openjarvis/tools/clipboard.py` (pyperclip-based, `mode: read\|write`, both require confirmation) + test | **Not started** |
| U10 | `src/openjarvis/tools/send_email.py` (SMTP + Gmail via `connectors/google_auth.call_with_refresh`) + `SendEmailToolConfig` + credentials entry + test | **Not started** |
| U11 | `src/openjarvis/tools/hyperv_query.py` (read-only Hyper-V listing, Windows-only, no confirmation needed) + test | **Not started** |
| U12 | `src/openjarvis/tools/hyperv_admin.py` (state-changing Hyper-V, always confirms) + test | **Not started** |
| U13 | `src/openjarvis/tools/computer_use.py` (pyautogui-based, always confirms, in `NEVER_REMEMBER_TOOLS`) + test | **Not started** |
| Wave 4 | Doc updates to `docs/user-guide/system-access.md` (confirmation table, warning callouts, remove the "no computer use" claim, document `jarvis approvals`) | **Not started** |

Full per-unit specs (exact `ToolSpec` shapes, capability entries, test case
lists, design-decision rationale for why e.g. Hyper-V is split into two
tools by risk tier, why `computer_use`/`hyperv_admin` never honor
remembered "always approve") are in the local plan file referenced above.
If that file is gone, the summary table here plus reading
`src/openjarvis/security/approval_callback.py` (already built, has the
`NEVER_REMEMBER_TOOLS` set already anticipating `computer_use`/
`hyperv_admin` by name) should be enough to reconstruct intent for U4
onward — each remaining unit is a fairly mechanical, well-precedented
addition following patterns already established elsewhere in
`src/openjarvis/tools/` (see `weather.py`, `apple_calendar.py`,
`docker_shell_exec.py`, `channels/email_channel.py`,
`connectors/google_auth.py` as the concrete style/reuse templates named in
the original plan).

### Known issue — fix before trusting U3b's test

`tests/security/test_capability_confirmation_floor.py` currently shows all
9 parametrized cases as **SKIPPED**, not passing — this is a bug in the
test itself, not a real "not registered" gap. Root cause: the module-level
`import openjarvis.tools` at the top of the test file runs once at
collection time, but `tests/conftest.py`'s autouse `_clean_registries`
fixture clears `ToolRegistry` before every test runs — by the time the
test body executes, `ToolRegistry.contains(tool_name)` is `False` for
everything, so every case hits the `pytest.skip(...)` branch instead of
actually asserting anything.

Fix (not yet applied): mirror `tests/tools/test_weather.py`'s
`importlib.reload(...)` pattern, but for the whole `openjarvis.tools`
package rather than one submodule — add an autouse fixture in this test
file that does something like:
```python
@pytest.fixture(autouse=True)
def _reregister_tools():
    import importlib
    import openjarvis.tools as tools_pkg
    importlib.reload(tools_pkg)
```
placed so it runs *after* `_clean_registries` (fixture ordering: autouse
fixtures from `conftest.py` run before autouse fixtures defined in the test
module itself, so this should already order correctly — verify with a
single `-v` run once added). Re-run
`pytest tests/security/test_capability_confirmation_floor.py -v` afterward
and confirm all 9 cases show `PASSED`, not `SKIPPED`, before considering
U3 done.

## Recommended next steps for a fresh session

1. Fix the `test_capability_confirmation_floor.py` registration bug above.
2. Continue with U4 (`server/agent_manager_routes.py`) through U13 in
   order, each following the "spec precisely → hand off to local model via
   `run_coding_task`/`edit_file` → review the diff → test → iterate"
   workflow already used for U1–U3 (see this branch's commit for the exact
   pattern/style to match).
3. Wave 4 docs last.
4. Once everything passes, get a real `uv`/Rust environment and re-run the
   full suite + the manual smoke-test checklist from the original plan
   (7 numbered scenarios covering `jarvis chat` regression, server-side
   blocking approval via `jarvis approvals`, `--yes` auditing, and each new
   tool including the Hyper-V/computer-use platform/elevation/permission-
   memory edge cases).
5. Open a PR from this fork/branch against `open-jarvis/OpenJarvis` `main`
   once both efforts are complete and green.
