# Plan: wake word, approval hardening and new tools

- **Date:** 2026-09-14
- **Status:** approved by Liam on 2026-09-14. Phase 1 is done except loading a
  real openWakeWord model, and Phase 2 is done except `test_create_agent`. Phase
  3 is done except the tests that need Liam's decisions (clipboard,
  `computer_use`, `send_email` and the bell UI).
- **Branch:** `feat/wake-word-and-approval-hardening` in
  `/home/liam/Projects/jarvis` (the Strix Halo). Cold-start notes are in
  `HANDOFF.md`.

Local models write every edit through the `local-llm` scheduler, Claude reviews
each diff, and nothing is pushed unless Liam asks. Write long logs to
`/home/liam/Projects/logs/jarvis/`, never a session scratchpad, which a session
restart wipes. After each phase, commit locally and make a verified backup: on
Linux a full git bundle in `/home/liam/Projects/backups/jarvis`, named
`jarvis-<YYYYMMDD-HHMM>-<short commit>.bundle`; on Windows sync
`C:\projects\Open Jarvis Backup`.

## Phase 1: finish the paused fix

- [x] Remove the extra blank line in
  `tests/security/test_capability_confirmation_floor.py`.
- [x] Run `uv lock`. `tflite-runtime` stays listed in `uv.lock`, but only behind
  the never-true marker, so it never installs.
- [x] Prove the fix on Linux with Python 3.12: `uv sync` with `--extra desktop`
  added installs; `uv sync --extra wake-word` installs openwakeword without
  tflite; a pip dry run of `.[desktop]` in a throwaway venv skips openwakeword.
- [x] Run `ruff check`, `ruff format --check` and `pytest tests/speech` (91
  passed, 6 skipped, with the confirmation-floor test).
- [x] Add a `CHANGELOG.md` Fixed entry and a `FORK_CHANGES.md` entry saying why,
  then update `HANDOFF.md` and this plan.

## Phase 2: full test suite on Linux

- [x] Run `make test` in the background, logging to
  `/home/liam/Projects/logs/jarvis/`.
- [x] Sort failures into environment problems and real bugs, and trace the
  `511 == 448` and `438 == 384` mismatches (they didn't appear on Linux).
- [x] Redo the regression comparison against `6e42464c`, where this branch
  leaves `upstream/main`. The old baseline `5588bfcf` is the branch's first
  commit and already has changes. Use a separate git worktree with its own
  `.venv`, and run `tests/tools`, `tests/security`, `tests/cli`, `tests/core`
  and `tests/server` on both.
- [x] Hand real bugs to local models one unit at a time: `record_decision`
  confirmation, the `security` test fixtures and the Hyper-V test reloads.
- [x] `test_create_agent`: fixed. The agent admin routes auto-approve
  `agent_spawn` and `agent_kill` with an audit record (decision 5).

## Phase 3: live tests on Linux (KDE on Wayland)

Already done on Windows: the approval queue through the real
`jarvis approvals` command (approve, timeout, deny, and refusing to
re-approve), `notify`, `clipboard`, `computer_use` screenshots,
`hyperv_query`, `hyperv_admin` rejecting an unknown VM and a wildcard, and
`jarvis ask` against a real LM Studio model (approved and timed-out calls).

- [x] `jarvis agents ask --yes` writing an approved row: works. `file_write` ran,
  and `approvals.db` got one `approved` row with source `cli.agent_ask` and
  `auto_approved` true (4080 lease, throwaway `OPENJARVIS_HOME`).
- [x] Approvals REST flow behind the bell: works. A streamed managed-agent chat
  queued `file_write`, approve returned 200 and wrote the file, and a second
  approve or a deny returned 409.
- [x] Approvals bell UI: tested on Windows, which has Node (decision 6).
  Approving from the bell wrote `approved`, and approving a request already
  approved elsewhere returned 409 and the bell refreshed.
- [x] `notify`: works. plyer falls back to `notify-send` because python-dbus
  isn't in `.venv`, and an empty title is rejected.
- [x] `clipboard`: not tested on Linux; it was already live-tested on Windows
  (decision 2).
- [x] `computer_use` pointer and keyboard: tested on Windows (decision 3). The
  pointer moved 40 px and back, Shift was pressed, and an off-screen point was
  rejected.
- [ ] `send_email` over SMTP and Gmail: waits for Liam to set up a test account
  (decision 4). Claude never creates accounts or enters credentials.

## Phase 4: deferred

- [ ] `jarvis chat --wake` with a microphone. The Z13's built-in digital mic has
  no Linux driver yet (kernel: "No matching ASoC machine driver found" for
  `acp70`), and its "Internal Microphone" input is only noise. Liam will fix
  the mic later; use a USB mic or Windows until then.
- [x] On Windows: `hyperv_admin` state changes on a throwaway VM. All nine
  steps worked after a fix for PowerShell warnings on stdout (see HANDOFF.md).
- [ ] On Windows: the desktop app's approvals bell. The web frontend's bell was
  tested instead (decision 6).

## Phase 5: pull request (only when Liam asks)

- [ ] Rebase on the latest `upstream/main` and rerun the tests.
- [ ] Final pass on the docs, `CHANGELOG.md` and `FORK_CHANGES.md`.
- [ ] Keep `HANDOFF.md` and this plan out of the pull request.
- [ ] Push to the fork (`origin` on Linux, `fork` on Windows), then open the
  pull request to `open-jarvis/OpenJarvis`.

## Resolved decisions

Liam delegated these to Claude on 2026-09-14.

1. openWakeWord model: yes, on Windows in a throwaway venv. It downloaded
   `hey_jarvis` and loaded on ONNX.
2. `wl-clipboard`: not installed. `clipboard` was already live-tested on
   Windows.
3. `computer_use`: yes, gently on Windows (a small pointer move and back, and a
   Shift press). No clicks or typing into apps.
4. SMTP test account: waits for Liam. Claude doesn't create accounts or enter
   credentials.
5. `POST /v1/agents`: auto-approve the agent admin tools with an audit record,
   since the API caller is making the call directly (`b9762443`).
6. Node on Linux: not installed. The bell UI was tested on Windows, which has
   Node.
7. The `faster-whisper-base` cache: kept, since the desktop speech feature uses
   it. Not reported upstream, which would be a public post.

## Decisions

- 2026-09-13: Work continues on Liam's fork. In the Linux checkout `origin` is
  the fork and `upstream` is `open-jarvis/OpenJarvis`.
- 2026-09-13: The toolchain comes from Arch packages (`uv`, `rustup`, `ruff`).
- 2026-09-13: Live tests on Linux cover only what Linux can run; the Hyper-V and
  Windows desktop tests stay on Windows.
- 2026-09-13: The wake-word test waits until Liam fixes the Z13 mic.
- 2026-09-14: The openwakeword fix combines the guards: onnx in the backend,
  openwakeword skipped in `desktop` on Linux with Python 3.12+, and a uv
  override that drops `tflite-runtime`.
- 2026-09-14: Liam paused that fix before `uv lock`, the tests and the commit.
- 2026-09-14: The branch was pushed to the fork at Liam's request, with no tag
  or release.
- 2026-09-14: Liam approved this plan, and it moved from `HANDOFF.md` into this
  file under the "Saving plans" rule.
- 2026-09-14: Liam handed over for the night: work through the plan without
  him, log after every change, and push nothing.
- 2026-09-14: `uv.lock` keeps `tflite-runtime` behind the override's never-true
  marker. Accepted, since uv never installs it.
- 2026-09-14: `record_decision` now requires confirmation, since an agent could
  otherwise approve its own queued action.
- 2026-09-14: `POST /v1/agents` stays as it is until Liam decides (open
  decision 5).
- 2026-09-14: With no Node on this machine, the approvals REST flow is tested
  with `curl`, and the bell UI waits for Liam (open decision 6).
- 2026-09-14: Liam asked to push the branch to the fork after the overnight
  run. No tag, release or pull request.
- 2026-09-14: A Windows review found the scheduled proactive agent could no
  longer run already-approved actions or notify the user. Liam chose to let its
  own two internal steps auto-approve with an audit record, while tool calls
  the model makes stay gated.
- 2026-09-14: Liam delegated the seven open decisions to Claude. The outcomes
  are under "Resolved decisions", and the Windows live tests for decisions 1, 3
  and 6 passed.
- 2026-09-14: Liam allowed Claude to create a throwaway Hyper-V VM for the
  `hyperv_admin` live test, skipped the SMTP and microphone tests for now, and
  asked to push the branch.
