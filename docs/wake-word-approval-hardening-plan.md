# Plan: wake word, approval hardening and new tools

- **Date:** 2026-09-14
- **Status:** approved by Liam on 2026-09-14. Phase 1 is done except loading a
  real openWakeWord model, and Phase 2 is done except `test_create_agent`; both
  wait for Liam. Phase 3 is next.
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
- [ ] `test_create_agent` still fails: `POST /v1/agents` can't run the now
  gated `agent_spawn` (open decision 5).

## Phase 3: live tests on Linux (KDE on Wayland)

Already done on Windows: the approval queue through the real
`jarvis approvals` command (approve, timeout, deny, and refusing to
re-approve), `notify`, `clipboard`, `computer_use` screenshots,
`hyperv_query`, `hyperv_admin` rejecting an unknown VM and a wildcard, and
`jarvis ask` against a real LM Studio model (approved and timed-out calls).

- [ ] `jarvis agents ask --yes` writing an approved row: take a scheduler lease,
  point jarvis only at the model the lease names, and release it afterwards.
- [ ] Approvals bell: run `jarvis serve` and the web frontend (`vite`), approve
  a gated tool from the bell, and check that a second decision returns 409.
- [ ] `notify`: should work, since `notify-send` is present.
- [ ] `clipboard`: needs `wl-clipboard`, which isn't installed. Liam decides.
- [ ] `computer_use` pointer and keyboard actions: pyautogui mostly fails on
  Wayland. Ask Liam first, since it moves his mouse, and record what happens.
- [ ] `send_email` over SMTP and Gmail: needs an account Liam sets up. Claude
  never enters credentials.

## Phase 4: deferred

- [ ] `jarvis chat --wake` with a microphone. The Z13's built-in digital mic has
  no Linux driver yet (kernel: "No matching ASoC machine driver found" for
  `acp70`), and its "Internal Microphone" input is only noise. Liam will fix
  the mic later; use a USB mic or Windows until then.
- [ ] On Windows: `hyperv_admin` state changes on a disposable VM, and the
  Windows desktop app's approvals bell.

## Phase 5: pull request (only when Liam asks)

- [ ] Rebase on the latest `upstream/main` and rerun the tests.
- [ ] Final pass on the docs, `CHANGELOG.md` and `FORK_CHANGES.md`.
- [ ] Keep `HANDOFF.md` and this plan out of the pull request.
- [ ] Push to the fork (`origin` on Linux, `fork` on Windows), then open the
  pull request to `open-jarvis/OpenJarvis`.

## Open decisions for Liam

1. May `openwakeword` download its `hey_jarvis` onnx model to prove it loads
   without tflite?
2. Install `wl-clipboard`, or leave `clipboard` for Windows?
3. May `computer_use` move the pointer and type on this desktop?
4. Set up a test SMTP account now, or later?
5. `POST /v1/agents` returns 400 because `agent_spawn` now needs confirmation.
   Queue an approval for REST admin calls (it would show in the bell),
   auto-approve them with an audit row since the caller is already
   capability-gated, or accept the 400 and update the test?

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
