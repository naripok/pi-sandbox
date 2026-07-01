# Agent Environment Reference

> This document is injected into your system prompt so you know what your sandbox can and cannot do. Treat it as reference material to know about constraints or capabilities inside the sandbox environment.

You are running inside a **rootless Podman container** (Arch Linux).

## Filesystem

| Path               | Access     | Description                                                     |
| ------------------ | ---------- | --------------------------------------------------------------- |
| `/workspace`       | Read-write | Project directory (bind-mounted from host). Your working dir.   |
| `/home/pi`         | Read-write | Persistent volume — survives across runs. Tools, sessions, etc. |
| `/home/pi/.local/` | Read-write | User-level package installs (`npm`, `pip`, `uv`).               |
| `/pi-source`       | Read-only  | Host's `~/.pi/agent/` — global skills and settings.             |
| `/tmp`             | Read-write | Ephemeral tmpfs. Lost when container exits.                     |
| `/` (rootfs)       | Read-only  | Base image. Cannot write to `/usr`, `/etc`, `/bin`, etc.        |

**Not accessible:** other project directories, host SSH keys, host dotfiles, host home, Docker/Podman sockets.

## Identity & Security

- Runs as `pi` (UID 1000). No root, no capabilities (`--cap-drop=ALL`), no-new-privileges enforced.
- Separate PID and network namespaces. No setuid/setgid binaries.
- npm lifecycle scripts disabled by default (`ignore-scripts=true`). Opt-in with `--ignore-scripts=false`.

## Installed Tools

**Languages:** Node.js, npm, Python, pip, uv
**System:** bash, git, gcc, make, rsync, fd, ripgrep, ast-grep, openssh, which
**Agent:** pi (pi-coding-agent CLI)

**Package installs:** `npm install -g` → `~/.local/`, `pip install --user` → `~/.local/`. No pacman (root required).

## Per-Project System Dependencies

If the project needs system-level packages not available via npm/pip/uv:

1. Create `.pi-packages` in the project root (one package per line, `#` for comments).
2. The user must approve packages on their next sandbox session.
3. On approval, the image rebuilds with those packages.

After writing `.pi-packages`, tell the user: "I've added packages to `.pi-packages`. Re-enter the sandbox to approve and rebuild."

## Network

- Outbound access allowed (HTTP, git, package installs, etc.). DNS works.
- Inbound blocked — no port forwarding, no host service access on `localhost`.
- Env vars from host `~/.env` are forwarded (API keys, etc.). Check `env` to see what's available.

## Resources

4 CPU cores, 8 GB memory, 1024 PIDs.

## Persistence

- `/workspace` and `/home/pi` persist across runs.
- On each start, host config (`/pi-source`) is rsynced into `~/.pi-agent-data/`, preserving `sessions/`, `*.lock` files, and container-created files.

## Shell

- Bash, `PATH` includes `~/.local/bin`. `PYTHONUSERBASE` and `NPM_CONFIG_PREFIX` point to `~/.local`.

## Troubleshooting

| Problem                             | Solution                                                    |
| ----------------------------------- | ----------------------------------------------------------- |
| Command not found                   | `pip install --user` or `npm install -g`                    |
| Permission denied writing to `/usr` | Rootfs is read-only. Write to `~/.local/` or `/workspace`.  |
| npm fails on native modules         | `npm install --ignore-scripts=false`                        |
| Cannot reach host on localhost      | Separate network namespace — host services aren't reachable |

## Agent Behavior

Now, continue with your regular agent behavior as instructed in your system prompt, keeping in mind the limitations and capabilities of this sandbox.
