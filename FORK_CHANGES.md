# Why this fork adds what it adds

This fork (`jamesyoungdahr-debug/OpenJarvis`) carries changes on the
`feat/wake-word-and-approval-hardening` branch that aren't in
`open-jarvis/OpenJarvis`. For each change, this file explains why it was added
and what goal it serves. For what changed in each commit, see `git log`. For
how to use the features, see `docs/user-guide/system-access.md`.

Nothing here has been proposed upstream yet. A pull request waits until every
feature has been tested live, not just in unit tests.

## The overall goal

Make OpenJarvis a local assistant that can act on your own computer (send a
notification, use the clipboard, send email, manage virtual machines, drive the
desktop, and start listening when you say its name) while every risky action
stays visible to you, needs your approval, and leaves a record.

The two halves depend on each other. More capable tools are only safe to enable
if approvals actually work, and when this work started they mostly didn't.

## Approvals that actually ask

### Why

OpenJarvis tools can mark themselves `requires_confirmation`, meaning a person
should approve each call. In practice only `jarvis chat` asked anyone.
`jarvis ask`, the HTTP server, the desktop app (a client of that server) and
`jarvis agents ask` all passed a callback that always answered yes, so a
dangerous tool call ran and was treated as approved without anyone seeing it.
Several tools that can do real damage, such as `file_write`, `apply_patch` and
`channel_send`, weren't marked as needing confirmation at all.

An approval queue (`ApprovalStore`, with REST endpoints and a desktop
approvals bell) already existed, but only the proactive agent used it.

### What was added, and the goal of each part

- **Confirmation turned on for `docker_shell_exec`, `file_write`,
  `apply_patch`, `agent_spawn`, `execute_pending_actions` and `channel_send`.**
  Why: each can change files, start agents, send messages or run commands.
  Goal: you see those actions before they happen.
- **A regression test for the confirmation floor.** Why: nothing stopped a new
  tool that needs `system:admin` or `channel:send` permission from skipping
  confirmation, and the existing test silently skipped every case because of a
  registry-reset bug. Goal: the gap can't quietly reopen when someone adds a
  tool.
- **`channel_list` and `channel_status` no longer need `system:admin`.** Why:
  they only read, and the admin tag would have forced an approval prompt just to
  list channels. Goal: approvals stay reserved for actions that matter, so
  people don't learn to click through them.
- **Queued approvals for the HTTP server, desktop app and `jarvis ask`.** Why:
  these entry points auto-approved everything. Goal: a risky call waits until
  you approve or deny it, and is denied after a timeout (five minutes by
  default). Streaming chat tool calls also moved off the server's event loop,
  because a call waiting there would freeze the whole server, including the
  endpoint needed to approve it.
- **Audited `jarvis agents ask --yes`.** Why: `--yes` exists so scripts can run
  unattended, but its approvals left no trace. Goal: scripts keep working, and
  every auto-approval is written to the approval log. If the record can't be
  written, the call is denied.
- **`jarvis approvals list/approve/deny`.** Why: approving used to require the
  REST API or the desktop app, so someone running `jarvis ask` in a terminal
  couldn't answer. Goal: approve or deny from the same terminal. It only changes
  pending requests, so a denied or expired one can't be flipped to approved.
- **The approval API only changes pending requests.** Why: the REST approve and
  deny endpoints behind the desktop approvals bell would flip a request that was
  already denied, approved or expired, so a denied tool call could be approved
  later. Goal: every way of deciding follows the same rule as `jarvis approvals`.
  The bell refreshes its list when a decision is rejected.
- **`computer_use` and `hyperv_admin` always need a fresh decision.** Why:
  they're the highest-risk tools here, with full desktop control and the ability
  to power off virtual machines. Goal: a one-time or stale approval never
  becomes standing access. A remembered "always approve" doesn't apply to them,
  and `--yes` refuses them.
- **`record_decision` asks too.** Why: this upstream proactive tool approves or
  denies any queued action and can save an "always approve" rule, but it never
  asked anyone, so an agent could approve its own queued action. The
  confirmation-floor test caught it on Linux. Goal: approving a queued action
  is always a person's decision.
- **The proactive agent's own steps are approved and recorded.** Why: once
  `execute_pending_actions` and `channel_send` required confirmation, a
  scheduled proactive run had no one to ask, so it could neither run actions a
  person had already approved nor send its notification, and it still marked
  those requests as notified. Goal: already-approved work still happens and
  reaches the user, with an audit record for each step, while anything the
  model tries on its own still needs a person.
- **Agent admin API calls are approved and recorded.** Why: once `agent_spawn`
  and `agent_kill` required confirmation, `POST /v1/agents` and
  `DELETE /v1/agents/{id}` always returned 400, because a direct API call had no
  way to answer. Queueing a second approval would leave the request hanging.
  Goal: someone calling the admin API can still create and stop agents, every
  such approval is recorded, and the capability and rate-limit checks still
  decide who may call it.

## New tools

Each tool is only usable once you enable it, and the risky ones always ask
first.

### `notify`

Why: long-running tasks had no way to get your attention after you'd switched
to something else. Goal: an agent can tell you a task finished or needs input.
It only shows text, so it needs no approval.

### `clipboard`

Why: moving text between the assistant and other apps meant copying and pasting
by hand. Goal: an agent can read what you copied, or hand you text ready to
paste. Clipboards often hold passwords, so every call needs approval and admin
permission.

### `send_email`

Why: agents had no tool for sending email; only the email messaging channel
could send. Goal: an agent can send an email for you, over SMTP or through the
Gmail sign-in the Google connector already has. Email is hard to take back, so
every send needs approval, and recipients must be plain addresses so no extra
headers or hidden recipients can be slipped in.

### `hyperv_query`

Why: an agent helping with a home lab or development VMs couldn't see what was
running. Goal: list virtual machines and their state. It's read-only, so it
needs no approval.

### `hyperv_admin`

Why: seeing VMs isn't enough to manage them. Goal: an agent can start, stop,
save, restart, pause, resume or checkpoint one VM, with your approval. VM names
reach PowerShell only as environment variables, never as code. The VM is
matched by exact name because Hyper-V's `-Name` parameter accepts wildcards, and
`*` would otherwise act on every VM.

### `computer_use`

Why: some tasks only exist in desktop apps that have no API. Goal: an agent can
move the pointer, click, type, press keys and take screenshots, with your
approval on every call. Screenshots are saved to a file and only the path is
returned, because tool output is stored in traces. The model can't see
screenshots through this tool yet, so it acts on coordinates it already knows.

### Optional installs

The libraries these tools need (`plyer`, `pyperclip`, `pyautogui`) are optional
extras. `computer-use` is deliberately left out of the `desktop` extra, so input
automation is always an explicit install.

## Keeping sensitive data out of traces

Why: OpenJarvis saves every tool call to its trace database. That included the
arguments and results of confirmation-gated tools, so email bodies, typed text
and clipboard contents were written to disk, along with full base64 browser
screenshots. Goal: traces stay useful for debugging and learning without storing
private data. For tools that require confirmation, the saved trace keeps
argument names but replaces their values and the result with `[redacted]`. For
every tool, base64 image data and very long strings are left out. Live views of
tool calls still show the full data; only what gets saved is redacted.

## Wake word

Why: voice chat required pressing Enter before every turn. Goal: say "hey
jarvis" and start talking, hands-free. It uses openWakeWord, which runs offline
and needs no API key, in keeping with OpenJarvis being local-first.

## Wake word on Linux with current Python

Why: the `desktop` extra added openWakeWord, which requires `tflite-runtime` on
Linux, and `tflite-runtime` has no wheels past Python 3.11. On Linux with
Python 3.12 or newer that broke every `desktop` install, including
`scripts/quickstart.sh` and the desktop app's own `uv sync`. The backend also
never chose an inference framework, so openWakeWord defaulted to tflite and
only fell back to ONNX because tflite was missing. Goal: `desktop` installs
everywhere, and the wake word still works on current Python when the
`wake-word` extra is installed with uv. The backend now asks for ONNX (tflite
only for a custom `.tflite` model), `desktop` skips openWakeWord on Linux with
Python 3.12+, and uv drops `tflite-runtime` with an override. A pip install of
the `wake-word` extra on Linux with Python 3.12+ still fails, and
`pyproject.toml` says so.

## Windows desktop app fix

Why: on Windows, the desktop app opened a blank console window each time it
started a helper process (`uv`, `ollama`, `git`, `where`). Goal: the app runs
without stray windows popping up.

## Documentation

Why: `docs/user-guide/system-access.md` described the old behaviour. It said
most entry points auto-approved and that there was no computer use. Goal: the
docs match what the code does, so nobody enables a tool based on outdated safety
claims.

## Testing status

Every change has unit tests. Live-tested so far, on Windows:

- the approval queue, approved and denied through the real `jarvis approvals`
  command, including refusing to approve a request that had already timed out
  and been denied
- `notify`, `clipboard` (read and write), and `computer_use` screenshots
- `hyperv_query` against real Hyper-V, and `hyperv_admin` rejecting an unknown
  VM and a wildcard name
- `jarvis ask` with a real local model (LM Studio on the RTX 4090): an approved
  `file_write` wrote the file, and an unanswered one timed out and wrote nothing

Still to test live before any pull request: the wake word with a microphone,
approvals from the desktop app, `--yes` audit records,
`send_email` over SMTP and Gmail, `computer_use` pointer and keyboard actions,
and `hyperv_admin` state changes on a disposable VM.
