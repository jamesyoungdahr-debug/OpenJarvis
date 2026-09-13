# Why this fork adds what it adds

This fork (`jamesyoungdahr-debug/OpenJarvis`) carries changes on the
`feat/wake-word-and-approval-hardening` branch that aren't in
`open-jarvis/OpenJarvis` yet. This file explains the reason behind each one.
For what changed in each commit, see `git log`. For how to use the features,
see `docs/user-guide/system-access.md`.

## The main problem: confirmations weren't really confirmations

OpenJarvis tools can mark themselves `requires_confirmation`, meaning a person
should approve each call. In practice only `jarvis chat` asked anyone.
`jarvis ask`, the HTTP server, the desktop app (a client of that server) and
`jarvis agents ask` all passed a callback that always answered yes. A
dangerous tool call ran and was treated as approved without anyone seeing it.
Several tools that can do real damage, such as `file_write`, `apply_patch` and
`channel_send`, weren't marked as needing confirmation at all.

An approval queue (`ApprovalStore`, with REST endpoints and a desktop
approvals bell) already existed, but only the proactive agent used it. Most of
this fork's security work connects that queue to the normal confirmation path.

### Confirmation turned on for dangerous tools

`docker_shell_exec`, `file_write`, `apply_patch`, `agent_spawn`,
`execute_pending_actions` and `channel_send` now require confirmation. Each
can change files, start agents, send messages or run commands, which is
exactly the kind of action a person should see first.

A regression test now fails if any tool that needs `system:admin` or
`channel:send` permission doesn't also require confirmation. That stops the
same gap from reopening when someone adds a tool. The test originally skipped
every case because of a registry-reset bug, which is fixed.

`channel_list` and `channel_status` lost their `system:admin` requirement.
They only read, and keeping the admin tag would have forced an approval prompt
just to list channels.

### Real approvals everywhere

- **HTTP server and desktop app:** tool calls that need confirmation now wait
  in the approval queue until someone approves or denies them, and are denied
  after a timeout (five minutes by default). Tool calls in the streaming chat
  path moved off the server's event loop. A call waiting for approval there
  would otherwise freeze the whole server, including the endpoint needed to
  approve it.
- **`jarvis ask`:** uses the same queued approval, for the same reason.
- **`jarvis agents ask --yes`:** still approves instantly, since that's what
  `--yes` is for in scripts, but every approval is now written to the approval
  log so there's a record. If the record can't be written, the call is denied
  rather than approved silently.
- **`jarvis approvals list/approve/deny`:** approving used to require the REST
  API or the desktop app, so someone running `jarvis ask` in a terminal had no
  way to answer from that terminal. It only changes pending requests, so a
  denied or expired one can't be flipped to approved later.

### Some tools always need a fresh decision

`computer_use` and `hyperv_admin` are the highest-risk tools here: full
desktop control, and the ability to power off virtual machines. A remembered
"always approve" never applies to them, and `--yes` refuses them. A one-time or
stale approval shouldn't become standing access to either.

## New tools

These let an assistant act on the local machine. Each is only usable once
enabled, and the risky ones always ask first.

- **`notify`:** shows a desktop notification, so a long-running task can tell
  you it finished or needs attention. It only displays text, so it needs no
  approval.
- **`clipboard`:** reads or replaces clipboard text, for handing text between
  the assistant and other apps. Clipboards often hold passwords, so every call
  needs approval and admin permission.
- **`send_email`:** sends plain-text email over SMTP or through the Gmail
  sign-in the Google connector already has. Email sent on your behalf is hard
  to take back, so every send needs approval. Recipients must be plain
  addresses, which blocks injecting extra headers or hidden recipients.
- **`hyperv_query`:** lists Hyper-V virtual machines and their state. It's
  read-only, so it needs no approval.
- **`hyperv_admin`:** starts, stops, saves, restarts, pauses, resumes or
  checkpoints one VM. VM names reach PowerShell only as environment variables,
  never as code. The VM is matched by exact name because Hyper-V's `-Name`
  parameter accepts wildcards, and `*` would otherwise act on every VM.
- **`computer_use`:** moves the pointer, clicks, types and takes screenshots.
  Screenshots are saved to a file and only the path is returned, because tool
  output is stored in traces and the model can't see images from tools anyway.

The libraries these need (`plyer`, `pyperclip`, `pyautogui`) are optional
extras. `computer-use` is deliberately left out of the `desktop` extra, so
input automation is always an explicit install.

## Wake word

`jarvis chat --wake` waits for "hey jarvis" before listening, instead of
needing Enter pressed for each turn. It uses openWakeWord, which runs offline
and needs no API key, so it fits OpenJarvis's local-first design.

## Windows desktop app fix

On Windows, the desktop app opened a blank console window every time it
started a helper process (`uv`, `ollama`, `git`, `where`). Those processes now
start without a window.

## Documentation

`docs/user-guide/system-access.md` described the old behaviour: only three
tools confirmed, most entry points auto-approved, and it said there was no
computer use. It now matches what the code does.
