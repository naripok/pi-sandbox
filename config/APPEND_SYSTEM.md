# Agent Environment Reference

You are running inside a **rootless Podman container** (Arch Linux) providing an isolated development environment. This document describes what you can and cannot do.

---

## Filesystem Layout

| Path                | Access    | Description                                          |
|---------------------|-----------|------------------------------------------------------|
| `/workspace`        | Read-write| The project directory (bind-mounted from host). Your working directory. |
| `/home/pi`          | Read-write| Persistent volume — survives across container runs. Use for installed tools, sessions, config. |
| `/home/pi/.local/`  | Read-write| User-level package installs (`npm`, `pip`, `uv`). |
| `/home/pi/.pi-agent-data/` | Read-write | Agent config, synced from host. Contains `sessions/`, skills, and this file. |
| `/pi-source`        | Read-only | Host's `~/.pi/agent/` — global skills and settings. You can read but not modify. |
| `/tmp`              | Read-write| Ephemeral tmpfs. Lost when container exits. |
| `/` (rootfs)        | Read-only | The Arch Linux base image. You cannot write to `/usr`, `/etc`, `/bin`, etc. |

### What Does NOT Exist

You **cannot** access:
- Other project directories — only `/workspace` is mounted
- Host SSH keys, dotfiles, or system config
- Host home directory
- `/var/run/docker.sock` or `/var/run/podman/podman.sock`

---

## Identity & Privileges

- **User**: `pi` (UID 1000)
- **Root**: No. Even though the image defines a root user, all capabilities are dropped (`--cap-drop=ALL`). Running as root in the container gives no additional privileges.
- **Setuid binaries**: Stripped. No setuid/setgid binaries exist in the image.
- **Privilege escalation**: Blocked by `--security-opt=no-new-privileges`. `NoNewPrivs` is enforced by the kernel.
- **Capabilities**: All dropped (`CapEff=0`).

---

## Installed Tools

### Languages & Runtimes

| Tool         | Available  | Notes                                     |
|--------------|------------|-------------------------------------------|
| Node.js      | ✅         | Via pacman                                |
| npm          | ✅         | Global installs go to `~/.local/`         |
| Python       | ✅         | Via pacman                                |
| pip          | ✅         | Via `python-pip` pacman package           |
| uv           | ✅         | Fast Python package manager               |

### System Tools

| Tool         | Available  | Notes                                     |
|--------------|------------|-------------------------------------------|
| bash         | ✅         | Default shell                             |
| git          | ✅         |                                           |
| gcc          | ✅         | C compiler                                |
| make         | ✅         |                                           |
| rsync        | ✅         |                                           |
| fd           | ✅         | Fast file finder (fd-find)                |
| ripgrep      | ✅         | Fast text search (rg)                     |
| ast-grep     | ✅         | AST-based code search and rewrite         |
| openssh      | ✅         | ssh client available                      |

### Agent Tools

| Tool         | Available  | Notes                                     |
|--------------|------------|-------------------------------------------|
| pi           | ✅         | pi-coding-agent CLI (global npm install)  |

### Package Managers

| Manager      | Install Command                              | Destination               |
|--------------|----------------------------------------------|---------------------------|
| npm (global) | `npm install -g <package>`                   | `~/.local/lib/node_modules/` |
| npm (local)  | `npm install <package>` (in /workspace)      | `/workspace/node_modules/` |
| pip (user)   | `pip install --user <package>`               | `~/.local/`               |
| uv           | `uv pip install --user <package>`            | `~/.local/`               |
| uv (venv)    | `uv venv` then `uv pip install <package>`    | venv directory            |
| pacman       | ❌ No — root is not available and pacman requires it. Use `pip`/`uv` or `npm` instead. |

> **Note**: npm lifecycle scripts (`postinstall`, `preinstall`, etc.) are **disabled by default** (`npm config set ignore-scripts true`). This prevents compromised packages from executing arbitrary code. To opt-in: `npm install --ignore-scripts=false`.

---

## Network

- **Network mode**: `slirp4netns` — you have outbound network access in a separate network namespace.
- **Outbound**: You can make HTTP requests, install packages, push git, call LLM APIs, etc.
- **Inbound**: The container is not reachable from the host or external network on any port. No port forwarding is configured.
- **DNS**: Works for outbound resolution.
- **Host access**: You cannot reach host services on `localhost` or `127.0.0.1` (separate network namespace).

### Environment Variables

API keys and other secrets are forwarded from the host's `~/.env` file. Common variables:
- `OPENROUTER_API_KEY`
- `VLLM_API_KEY`
- Any other variable defined in the host's `~/.env`

> Check `env` or `printenv` to see what's available.

---

## Resource Limits

| Resource   | Limit    | Notes                          |
|------------|----------|--------------------------------|
| CPU        | 4 cores  | `--cpus 4`                     |
| Memory     | 8 GB     | `--memory 8g`                  |
| PIDs       | 1024     | `--pids-limit 1024`            |

---

## Persistence

### What Survives Across Runs

| Item                               | Location                                  | Persists? |
|------------------------------------|-------------------------------------------|-----------|
| Files in `/workspace`              | Host filesystem (bind mount)              | ✅ Yes    |
| Tools installed in `~/.local/`     | Persistent volume                         | ✅ Yes    |
| npm global packages                | `~/.local/lib/node_modules/`              | ✅ Yes    |
| Agent sessions                     | `~/.pi-agent-data/sessions/`             | ✅ Yes    |
| Shell config (`~/.bashrc`)         | Persistent volume                         | ✅ Yes    |
| Files in `/tmp`                    | tmpfs (ephemeral)                         | ❌ No     |
| Root filesystem modifications      | Read-only rootfs                          | ❌ No     |

### What Gets Synced on Every Start

The entrypoint rsyncs files from `/pi-source` (host config) into `~/.pi-agent-data/`:
- New or updated skills
- Updated `AGENTS.md`
- New or changed settings files

**Not synced** (preserved from volume):
- `sessions/` — to avoid overwriting runtime state
- `*.lock` files
- Any files created inside the container

---

## Security Model (Summary)

| Threat                          | Mitigation                                   |
|---------------------------------|----------------------------------------------|
| Reading other projects          | Only `/workspace` is mounted                 |
| Modifying host config           | `/pi-source` is read-only                    |
| Modifying system files          | Root filesystem is read-only                 |
| Privilege escalation            | `--cap-drop=ALL`, `--security-opt=no-new-privileges` |
| setuid exploits                 | All setuid bits stripped from the image      |
| Host process visibility         | Separate PID namespace                       |
| Container runtime escape        | `--cap-drop=ALL` + rootless (user namespaces) |
| Malicious npm scripts           | `ignore-scripts=true` by default             |

### Limitations to Be Aware Of

- **Network exfiltration**: Outbound network is allowed. A compromised package could exfiltrate project data from `/workspace`. This is the main weakness of container isolation vs. VM isolation.
- **Volume persistence**: If a malicious file ends up in the persistent volume, it survives across runs. Use `run.sh --reset` for a clean slate.
- **Rootless escape**: A full container escape yields only the host user's unprivileged permissions.

---

## Shell Configuration

- **Shell**: `/bin/bash`
- **Prompt**: `[\u@pi-agent \W]$` (set in `~/.bashrc` — only in interactive shells)
- **PATH**: `~/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin`
- **Aliases**: `ls` aliased to `ls --color=auto` (only in interactive shells)
- **Color**: `TERM=xterm-256color`, `COLORTERM=truecolor`
- **Env vars**: `PYTHONUSERBASE`, `NPM_CONFIG_PREFIX`, `PI_CODING_AGENT_DIR` (set by entrypoint — available in all sessions)

---

## Common Operations

### Install a Python package
```bash
pip install --user <package>
# or with uv
uv pip install --user <package>
```

### Install a Node.js package globally
```bash
npm install -g <package>    # Goes to ~/.local/
```

### Install project dependencies
```bash
cd /workspace
npm install                  # Local, in /workspace/node_modules/
```

### Run the pi agent
```bash
pi -p "Your prompt here"
```

### Check what tools are available
```bash
which <tool>                 # Check if installed
command -v <tool>            # More robust check
```

### View environment variables
```bash
env                          # All variables
printenv <VAR_NAME>          # Specific variable
```

---

## Troubleshooting

| Problem                                  | Solution                                     |
|------------------------------------------|----------------------------------------------|
| Command not found                        | Install with `pip install --user` or `npm install -g` |
| Permission denied writing to `/usr`      | Rootfs is read-only. Install to `~/.local/` or `/workspace` instead. |
| npm install fails on native modules      | Run with `--ignore-scripts=false` to allow lifecycle scripts |
| Can't reach host service on localhost    | Separate network namespace. Host services aren't reachable. |
| Session data lost                        | Check that you're writing to `~/.pi-agent-data/sessions/` not `/tmp` |
