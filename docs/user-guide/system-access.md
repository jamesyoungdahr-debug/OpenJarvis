# System Access

How to give an agent access to the machine it runs on, and where the real
limits are.

!!! warning
    `shell_exec` runs arbitrary commands as your user. There is no command
    allowlist, no denylist, and no sandbox unless you turn one on. An agent
    holding this tool can do anything you can do from a terminal.

!!! warning
    `computer_use` controls your mouse and keyboard, and `hyperv_admin` can power
    off virtual machines. Both ask for approval on every call, and a remembered
    "always approve" never applies to them. Only enable them for agents you
    trust with your desktop.

---

## Start here: you probably have no tools enabled

If the agent tells you it can't run commands or read files, that's usually not
a permissions problem. It means no tools were enabled in the first place.

Tools come from `tools.enabled`, falling back to `agent.tools`. Both default to
empty, and an empty value builds the agent with **zero tools**. Nothing is
enabled by default.

First check whether you have a config file at all:

```bash
cat ~/.openjarvis/config.toml
```

If it isn't there, that's your answer. Create it:

```toml
[engine]
default = "ollama"

[intelligence]
default_model = "qwen3.5:9b"

[agent]
default_agent = "orchestrator"

[tools]
enabled = ["shell_exec", "file_read", "file_write", "think"]
```

There's a fuller version at
`configs/openjarvis/examples/full-system-access.toml`.

Then confirm the list actually resolved:

```bash
python -c "from openjarvis.core.config import load_config; print(load_config().tools.enabled)"
```

---

## What the tools reach

| Tool | Scope |
|------|-------|
| `shell_exec` | Any command, as your user. 30s default timeout, 300s max, output capped at 100 KB per stream. |
| `file_read` | Any readable path. 1 MB cap. |
| `file_write` | Any writable path. 10 MB cap, can create parent directories. |
| `apply_patch` | Applies unified diffs to any path. |
| `code_interpreter` | Python in a subprocess, behind a coarse pattern blocklist. |
| `send_email` | Sends plain-text email over SMTP or through the Google connector's Gmail sign-in. 10 recipients by default (`[tools.send_email].max_recipients`, hard limit 50). |
| `clipboard` | Reads or replaces the system clipboard text. 100,000 character cap. |
| `notify` | Shows a desktop notification. Title up to 64 characters, message up to 256. |
| `computer_use` | Moves the pointer, clicks, scrolls, types, presses keys and saves screenshots on the local desktop. |
| `hyperv_query` | Lists Hyper-V virtual machines. Windows only, read-only. |
| `hyperv_admin` | Starts, stops, turns off, saves, restarts, pauses, resumes or checkpoints one Hyper-V VM. Windows only. |

`file_read` and `file_write` take an `allowed_dirs` argument that limits them to
a set of directories, but no config key populates it. When it's empty every path
is allowed. If you want a filesystem jail today, use the container sandbox
instead of relying on these tools to enforce one.

### Sensitive filenames

`file_read` and `file_write` refuse names matching a short glob list: `.env`,
`*.pem`, `id_rsa`, `credentials.*` and a dozen or so others. It matches on the
filename only, not the path or the contents, and only those two tools consult
it. `shell_exec`, `apply_patch` and `code_interpreter` skip it entirely, so
`cat ~/.ssh/id_rsa` through `shell_exec` works fine. Treat it as protection
against fat fingers, not as a security boundary.

---

## Confirmation behaviour

These tools ask for approval before every call: `shell_exec`, `file_write`,
`apply_patch`, `git_commit`, `docker_shell_exec`, `agent_spawn`, `agent_kill`,
`channel_send`, `execute_pending_actions`, `send_email`, `clipboard`,
`hyperv_admin` and `computer_use`.

How you give that approval depends on how you launched the agent:

| Entry point | Behaviour |
|-------------|-----------|
| `jarvis chat` | Prompts in the terminal before each call. |
| `jarvis ask` | Queues the call and waits for a decision. |
| `jarvis agents ask` | Approves instantly and records each approval in the approval log. `computer_use` and `hyperv_admin` are refused instead. Pass `--no-yes` to be prompted in the terminal. |
| HTTP server, desktop app | Queues the call and waits for a decision. |
| Embedded via `SystemBuilder` | No callback is wired, so these tools fail closed. |

That last row catches people out. If `shell_exec` returns "requires
confirmation but no confirmation callback is available", you're constructing the
agent yourself and need to pass a `confirm_callback`.

### Approving queued calls

A queued call waits in the approval store until you decide. Approve or deny it
from any of these:

- `jarvis approvals list`, then `jarvis approvals approve <id>` or
  `jarvis approvals deny <id>`
- the approvals bell in the desktop app
- `POST /v1/approvals/{id}/approve` or `POST /v1/approvals/{id}/deny`

`jarvis approvals` only changes calls that are still pending, so it won't
approve a call you already denied.

If nobody decides in time, the call is denied. The wait is five minutes by
default:

```toml
[security]
approval_timeout_seconds = 300
approval_poll_interval_seconds = 1.0
```

A timed-out call stays in the queue, but approving it afterwards doesn't rerun
the tool.

A remembered "always approve" or "always deny" decision for an agent and tool
skips the queue. `computer_use` and `hyperv_admin` ignore remembered decisions:
every call waits for a fresh one.

!!! note "`enforce_tool_confirmation` doesn't do anything"
    The config loader accepts `security.enforce_tool_confirmation`, but nothing
    on the tool execution path reads it. Setting it won't change confirmation
    behaviour anywhere. Use the table above instead.

---

## macOS: Full Disk Access

On macOS the operating system is the real boundary, not the config. Shell
access and ordinary file access start working as soon as you enable the tools.
TCC-protected data does not: Messages, Mail, Photos, Safari history, Contacts
and Calendar all stay locked, and no config key will change that.

Grant Full Disk Access to whichever process hosts the backend. Child processes
inherit it:

| How you run OpenJarvis | Grant access to |
|------------------------|-----------------|
| CLI (`jarvis ask`, `jarvis chat`) | Your terminal (Terminal, iTerm, Warp) |
| Desktop app | `OpenJarvis.app`, which spawns `jarvis serve` beneath it |
| launchd (`deploy/launchd/com.openjarvis.plist`) | The `jarvis` binary, as its own entry |

System Settings, then Privacy & Security, then Full Disk Access, then **+**.

A launchd daemon gets its own TCC context, so granting access to Terminal does
nothing for it. Add `/usr/local/bin/jarvis` separately.

To check whether the grant took:

```bash
head -c 16 ~/Library/Messages/chat.db >/dev/null 2>&1 \
  && echo "granted" || echo "denied"
```

Restart the host process after you change the setting.

### Driving Mac apps

AppleScript works through `shell_exec`:

```
osascript -e 'tell application "Music" to play'
```

macOS asks for Automation permission once per target app, the first time you
touch it.

---

## Desktop control

`computer_use` drives the local desktop through pyautogui. It isn't installed
by default:

```bash
pip install 'openjarvis[computer-use]'
```

It can move the pointer, click, double-click, scroll, type, press a key or a
key combination, and take a screenshot. Every call asks for approval, and
moving the pointer into a screen corner aborts the action.

Screenshots are saved to a temporary PNG and the tool returns only the file
path. Tool results reach the model as text, so the agent can't look at a
screenshot and work out where to click. It acts on coordinates you or the model
already know.

On macOS, grant Accessibility (for input) and Screen Recording (for
screenshots) to the process that hosts the backend, the same way as Full Disk
Access above.

The `click` and `type` actions in the browser tools are separate. They're
Playwright, scoped to a browser page rather than the desktop.

---

## Narrowing access

Access widens and narrows through `tools.enabled`. Drop entries to take
capabilities away. That list is the whole grant.

Two stronger isolation options exist. Both are off by default:

```toml
[sandbox]
enabled = true          # run tools inside a container
runtime = "docker"

[security.capabilities]
enabled = true          # RBAC over declared tool capabilities
policy_path = "~/.openjarvis/policy.yaml"
```

!!! note "Capabilities are open by default even once enabled"
    `CapabilityPolicy` is built with `default_deny=False` and no config key
    exposes that flag, so an agent with no explicit policy entry gets every
    capability. Write entries for every agent you mean to restrict.

For anything untrusted, reach for `docker_shell_exec` and
`code_interpreter_docker` rather than the host-side versions.

---

## See also

- [Security](security.md) for scanners, the audit log and guardrails
- [Tools](tools.md) for the full registry
- [Code Assistant](code-assistant.md) for a narrower shell-enabled setup
- [External MCP Servers](mcp-external-servers.md) for capabilities OpenJarvis doesn't ship
