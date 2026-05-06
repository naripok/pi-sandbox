# Pi Agent Isolation Environment — Specification

> **Document Version:** 2.0  
> **Last Updated:** 2026-05-06

---

## 1. Motivation

### 1.1 The Problem

AI coding agents like pi-coding-agent are powerful autonomous tools that execute arbitrary shell commands, read and write files, and install npm packages. This creates three distinct risks:

1. **Cross-project contamination.** An agent working on `project-a` should not be able to read secrets, source code, or configuration from `project-b`.
2. **Compromised dependency attacks.** A malicious or hijacked npm package can execute arbitrary code during `npm install` or at runtime, potentially exfiltrating data, modifying source files, or running destructive commands.
3. **Lost state.** Ephemeral containers discard sessions, installed tools, and shell customizations on every exit, making repeated work frustrating and inefficient.

### 1.2 Why Existing Approaches Are Insufficient

- **Running directly on the host:** The agent has access to the entire host filesystem, all SSH keys, all environment variables, and all projects.
- **Virtual machines (Firecracker/QEMU):** Provides strong kernel-level isolation but introduces enormous operational complexity — networking, storage synchronization, boot management, image building — that makes the security model opaque and error-prone. If you cannot hold the entire system in your head, you cannot reason about its security.
- **System-wide container (Docker/Podman without project isolation):** Protects the host kernel but still exposes all projects and global configuration to the agent.

### 1.3 Design Goal

The simplest possible system that satisfies all three requirements (isolation, security, persistence), where the entire security model can be understood by reading a single shell command.

---

## 2. Principles

| Principle                        | Implication                                                                                                                        |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **One project, one environment** | Each project runs in an entirely separate filesystem namespace with its own persistent volume.                                     |
| **Explicit visibility**          | The agent sees _only_ directories explicitly mounted into its environment.                                                         |
| **Read-only global config**      | The agent can use global settings and skills but cannot mutate host config. Changes are synced via rsync on every start.           |
| **Mutable project workspace**    | The agent can read and write project files, which persist on the host.                                                             |
| **Persistent per-project state** | Sessions, installed tools, and shell customizations survive across container runs via a podman-managed volume.                     |
| **No root privileges**           | The container runtime is rootless. All capabilities are dropped. Even a complete container escape yields unprivileged permissions. |
| **Transparent to the user**      | Pair-coding works naturally: host editor and container agent see the same files simultaneously.                                    |

---

## 3. Architecture

### 3.1 High-Level Model

```
┌─────────────────────────────────────────────────────────────────┐
│                      HOST (Arch Linux)                          │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │ ~/.pi/agent/     │  │ ~/Projects/      │                     │
│  │ (global config)  │  │                  │                     │
│  └────────┬─────────┘  │  ├─ project-a/   │                     │
│           │            │  ├─ project-b/   │                     │
│           │            │  └─ project-c/   │                     │
│           │            └──────────────────┘                     │
│           │                                                     │
│  ┌────────▼──────────────────────────────────────┐              │
│  │  Container A (project-a)                      │              │
│  │  /pi-source → ~/.pi/agent (ro)                │              │
│  │  /workspace → project-a (rw)                  │              │
│  │  /home/pi → podman volume (rw, persistent)    │              │
│  │  [no access to project-b]                     │              │
│  └───────────────────────────────────────────────┘              │
│                                                                 │
│  ┌───────────────────────────────────────────────┐              │
│  │  Container B (project-b)                      │              │
│  │  /pi-source → ~/.pi/agent (ro)                │              │
│  │  /workspace → project-b (rw)                  │              │
│  │  /home/pi → podman volume (rw, persistent)    │              │
│  │  [no access to project-a]                     │              │
│  └───────────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 What the Agent Can See

Inside any container:

| Path                                | Source                   | Permissions | Contents                                         |
| ----------------------------------- | ------------------------ | ----------- | ------------------------------------------------ |
| `/workspace`                        | `~/Projects/<project>/`  | read-write  | Entire project directory (bind mount from host)  |
| `/pi-source`                        | `~/.pi/agent/`           | read-only   | Host's global pi config (skills, settings, etc.) |
| `/home/pi`                          | Persistent podman volume | read-write  | Persistent per-project state                     |
| `/home/pi/.pi-agent-data/`          | Synced from `/pi-source` | read-write  | Agent config, sessions, lock files               |
| `/home/pi/.pi-agent-data/sessions/` | Persistent volume        | read-write  | Session history (survives across runs)           |
| `/home/pi/.local/`                  | Persistent volume        | read-write  | User-level package installs (npm, pip, uv)       |
| `/tmp`                              | tmpfs                    | read-write  | Ephemeral scratch space (lost on exit)           |
| `/` (rootfs)                        | Arch Linux image         | read-only   | Base system (cannot be modified)                 |

The agent **cannot** see:

- Any other project directory
- Host home directory outside the above mounts
- Host SSH keys (`~/.ssh/`)
- Host system configuration (`/etc`, `/var`)
- Other users' files
- Docker/Podman sockets (`/var/run/docker.sock`, `/var/run/podman/podman.sock`)

### 3.3 What the Agent Can Do

| Action                                       | Allowed?   | Notes                                                                                |
| -------------------------------------------- | ---------- | ------------------------------------------------------------------------------------ |
| Read/write project source                    | ✅ Yes     | Persisted on host immediately via bind mount                                         |
| Install project dependencies (`npm install`) | ✅ Yes     | Within `/workspace` only                                                             |
| Create project-local skills                  | ✅ Yes     | Written to `.pi/skills/` inside project                                              |
| Modify project settings                      | ✅ Yes     | Written to `.pi/settings.json` inside project                                        |
| Read global skills/settings                  | ✅ Yes     | Via read-only `/pi-source` mount                                                     |
| Modify host global config                    | ❌ No      | `/pi-source` is mounted read-only                                                    |
| Access other projects                        | ❌ No      | Not mounted, does not exist in container                                             |
| Access host SSH keys                         | ❌ No      | Not mounted                                                                          |
| Modify system files                          | ❌ No      | Root filesystem is read-only (`--read-only`)                                         |
| Escalate privileges                          | ❌ No      | `--cap-drop=ALL`, `--security-opt=no-new-privileges`, rootless                       |
| Install global tools                         | ✅ Yes     | To `~/.local/` via npm/pip/uv — persists in volume                                   |
| Exfiltrate data over network                 | ⚠️ Partial | Can make outbound requests (slirp4netns), but only has access to this project's data |

---

## 4. Technology Selection

### 4.1 Container Runtime: Rootless Podman

| Alternative          | Why Rejected                                                                                                                                                      |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Docker               | Requires root daemon. Rootless Docker exists but is a second-class feature with rough edges.                                                                      |
| bubblewrap (`bwrap`) | Single-purpose sandbox; managing a full development environment (Node.js, git, etc.) requires manually binding every system library. Too low-level for daily use. |
| Firecracker/QEMU     | Strong isolation but unacceptable complexity for the threat model (see §1.2).                                                                                     |
| **Rootless Podman**  | ✅ No daemon, no root. OCI-compatible. User namespaces by default. Native `podman` command works identically to `docker`.                                         |

### 4.2 Base Image: Arch Linux

| Alternative    | Why Rejected                                                                                                                                                                         |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Alpine         | musl libc causes friction with npm packages containing native binaries (e.g. `koffi`, `sharp`, etc.). Busybox coreutils differ from GNU coreutils, breaking agent-generated scripts. |
| Debian/Ubuntu  | Heavier than necessary. The host runs Arch; keeping the guest on Arch means identical package names and behavior.                                                                    |
| **Arch Linux** | ✅ Matches host environment. Minimal base image available. `pacman` package ecosystem aligned with host.                                                                             |

### 4.3 Init System: Entrypoint Script

No systemd. No custom init scripts. The container uses a bash entrypoint (`config/entrypoint.sh`) that performs first-run setup and config sync, then execs the user command. When the shell exits, the container stops.

---

## 5. Directory Structure

### 5.1 Host-Side (This Repository)

```
~/Projects/pi-sandbox/          # Repository root
├── README.md                   # Quick start and overview
├── Containerfile               # Image definition
├── run.sh                      # Launch script
├── Makefile                    # Common commands
├── tests/                      # Pytest suite
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_containerfile.py
│   ├── test_integration.py
│   ├── test_makefile.py
│   ├── test_run.py
│   └── test_security.py
├── docs/
│   ├── specs/
│   │   └── 2026-05-05-persistent-volume-design.md
│   └── plans/
│       ├── 2026-04-25-pi-agent-isolation-environment.md
│       ├── 2026-04-25-env-var-forwarding.md
│       └── 2026-05-05-persistent-volume.md
└── config/
    ├── .bashrc                 # Shell initialization for the container
    ├── entrypoint.sh           # Container entrypoint (config sync, first-run setup)
    └── APPEND_SYSTEM.md        # Agent environment reference (injected into system prompt)
```

### 5.2 Host-Side (Runtime State)

Podman stores its rootless data in `~/.local/share/containers/` automatically. Persistent volumes are stored in `~/.local/share/containers/storage/volumes/`. No manual state management required.

### 5.3 Guest-Side (Inside Container)

```
/
├── bin/                            # System binaries (read-only rootfs)
├── workspace/                      # Bind mount: current project (rw)
│   ├── src/
│   ├── .pi/                        # Project-local settings and skills
│   │   ├── settings.json
│   │   └── skills/
│   └── package.json
├── pi-source/                      # Bind mount: ~/.pi/agent (ro)
│   ├── AGENTS.md
│   ├── settings.json
│   └── skills/
├── home/
│   └── pi/                         # Persistent podman volume (rw)
│       ├── .bashrc                 # Shell config (copied on first run)
│       ├── .bash_profile           # Login shell wrapper (first run)
│       ├── .pi-agent-data/         # Synced from /pi-source on every start
│       │   ├── AGENTS.md
│       │   ├── APPEND_SYSTEM.md
│       │   ├── settings.json
│       │   ├── skills/
│       │   └── sessions/           # Session history (preserved across runs)
│       └── .local/                 # User-level package installs
│           ├── bin/
│           ├── lib/
│           └── ...
└── ... (standard Arch Linux root, read-only)
```

---

## 6. Container Image (`Containerfile`)

### 6.1 Image Contents

```dockerfile
FROM archlinux:latest

# Install base tools and runtimes
RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm nodejs npm git openssh bash fd ripgrep \
                          python python-pip uv gcc make ast-grep \
                          rsync && \
    pacman -Scc --noconfirm

# Strip setuid/setgid bits — hardening the image
RUN find / \( -path /proc -o -path /sys \) -prune -o -perm /6000 -type f -exec chmod a-s {} +

# Install pi-coding-agent globally
RUN npm install -g @mariozechner/pi-coding-agent

# Container user (UID 1000 for file ownership matching)
RUN useradd -m -u 1000 -s /bin/bash pi

# Clean up root-owned artifacts in /home/pi
RUN rm -rf /home/pi/.npm /home/pi/.npmrc

# Store .bashrc outside $HOME — it gets copied into the persistent volume at startup.
RUN mkdir -p /etc/pi
COPY config/.bashrc /etc/pi/.bashrc

# Copy and install entrypoint script
COPY config/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh

# Environment
ENV HOME=/home/pi
ENV TERM=xterm-256color
ENV COLORTERM=truecolor

USER pi

# Disable npm lifecycle scripts by default
RUN npm config set ignore-scripts true

WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
```

### 6.2 Installed Tools

| Category  | Tools                                                       |
| --------- | ----------------------------------------------------------- |
| Languages | Node.js, npm, Python, pip, uv                               |
| System    | bash, git, gcc, make, rsync, fd, ripgrep, ast-grep, openssh |
| Agent     | pi-coding-agent                                             |

### 6.3 Hardening

- **Setuid/setgid stripped:** All setuid/setgid bits removed from the image filesystem.
- **npm lifecycle scripts disabled:** `ignore-scripts=true` prevents compromised packages from executing arbitrary code during install. Users can opt-in with `npm install --ignore-scripts=false`.
- **Non-root user:** Container runs as `pi` (UID 1000).

### 6.4 Build

```bash
podman build -t pi-agent-isolated .
# or
make build
```

### 6.5 Why No Multi-Stage Optimization

Simplicity. The image is built once and cached. A single `pacman -S` layer is acceptable for a development environment.

---

## 7. Entrypoint Script (`config/entrypoint.sh`)

The entrypoint runs as the `pi` user (set by `USER pi` in the Containerfile). It performs setup on every container start, then execs the user command.

### 7.1 Responsibilities

| Step | Action                                         | Frequency                |
| ---- | ---------------------------------------------- | ------------------------ |
| 1    | Sync host config via rsync                     | Every start              |
| 2    | Copy `APPEND_SYSTEM.md` to data dir            | Every start (overwrites) |
| 3    | Copy `.bashrc` from image                      | First run only           |
| 4    | Create `.bash_profile`                         | First run only           |
| 5    | Configure package manager paths                | First run only           |
| 6    | Set `PI_CODING_AGENT_DIR` environment variable | Every start              |
| 7    | `exec "$@"` — run the user command             | Every start              |

### 7.2 Config Sync

On every container start, the entrypoint runs:

```bash
rsync -rltDp --no-o --no-g --exclude='sessions/' --exclude='*.lock' /pi-source/. "$DATA_DIR/"
```

This propagates new and modified config files from the host into the persistent volume, while preserving user-generated data:

| Synced from host (`/pi-source`) | Preserved in volume         |
| ------------------------------- | --------------------------- |
| New skills in `skills/`         | Sessions in `sessions/`     |
| Updated `AGENTS.md`             | Lock files (`*.lock`)       |
| New/changed settings files      | Any container-created files |

**Not handled:** Files deleted from the host are not removed from the volume. This avoids accidentally deleting user data. Use `./run.sh --reset` for a clean slate.

### 7.3 Agent Prompt Injection (`APPEND_SYSTEM.md`)

The entrypoint copies `config/APPEND_SYSTEM.md` from the repository into `$DATA_DIR/` on every container start. Because `$DATA_DIR` is the value of `PI_CODING_AGENT_DIR`, pi automatically loads this file as part of its configuration.

**How it works:** pi-coding-agent reads all markdown files in its config directory (`$PI_CODING_AGENT_DIR`) and includes them in the system prompt. By placing `APPEND_SYSTEM.md` in this directory, the sandbox description is automatically injected into every agent session — no CLI flags, no wrapper scripts, no external tooling required.

**What the agent learns:** `APPEND_SYSTEM.md` is written directly to the agent in second person ("You are running inside a rootless Podman container"). It describes:

- **Filesystem layout** — what paths exist, what is read-only, what does not exist
- **Identity and privileges** — the `pi` user, dropped capabilities, no-new-privileges enforcement
- **Installed tools** — languages (Node.js, Python), system tools (git, gcc, ripgrep, ast-grep), package managers
- **Network configuration** — slirp4netns mode, outbound-only access, no host service reachability
- **Resource limits** — CPU, memory, PID constraints
- **Persistence behavior** — what survives across runs, what is synced, what is ephemeral
- **Security model summary** — threats, mitigations, and known limitations
- **Shell configuration** — PATH, env vars, prompt, aliases
- **Common operations** — how to install packages, run pi, check available tools
- **Troubleshooting** — common errors and their solutions

**Why this matters:** Without prompt injection, the agent operates blind — it doesn't know it's in a sandbox, doesn't know which tools are available, and may attempt operations that are impossible in the container (e.g., running `pacman`, editing `/etc`, reaching host services on `localhost`). With `APPEND_SYSTEM.md`, the agent makes informed decisions about what to do and how to do it.

**Update mechanism:** The file lives in the repository, not in the persistent volume. The entrypoint overwrites it on every start, ensuring the agent always receives the latest description. If the Containerfile or `run.sh` flags change, updating `APPEND_SYSTEM.md` propagates the change to all containers on next run.

**Source:** See [`config/APPEND_SYSTEM.md`](config/APPEND_SYSTEM.md) for the full prompt text.

### 7.4 Source

See [`config/entrypoint.sh`](config/entrypoint.sh) for the full implementation.

---

## 8. Launch Script (`run.sh`)

### 8.1 Source

See [`run.sh`](run.sh) for the full implementation.

### 8.2 Volume Naming

```bash
PROJECT_PATH="$(realpath "$(pwd)")"
PROJECT_NAME="$(basename "$PROJECT_PATH")"
PERSIST_VOLUME="pi-agent-persist-${PROJECT_NAME}-$(echo "$PROJECT_PATH" | sha256sum | cut -c1-8)"
```

The basename makes `podman volume ls` output meaningful. The 8-char hash suffix (32 bits) guarantees uniqueness across projects with the same name on different paths. Example: `pi-agent-persist-myproject-a1b2c3d4`.

### 8.3 Container Naming

```bash
CONTAINER_NAME="pi-agent-$(basename "$PWD")-${RANDOM}"
```

The random suffix prevents name collisions when running multiple containers for the same project simultaneously.

### 8.4 Key Flags

| Flag                               | Purpose                                                                         |
| ---------------------------------- | ------------------------------------------------------------------------------- |
| `--rm`                             | Container is deleted when exited. No stale state.                               |
| `--userns=keep-id`                 | Maps container UID to host UID. Files written by the agent appear owned by you. |
| `--network=slirp4netns`            | Separate network namespace with outbound access. Not reachable from host.       |
| `--cap-drop=ALL`                   | Drop all Linux capabilities. No privilege escalation possible.                  |
| `--security-opt=no-new-privileges` | Kernel enforces NoNewPrivs. `setuid`/`setgid` calls fail.                       |
| `--read-only`                      | Root filesystem is read-only. Only writable paths are explicit mounts.          |
| `--tmpfs /tmp`                     | Ephemeral tmpfs for temporary files. Lost on exit.                              |
| `--pids-limit 1024`                | Maximum 1024 processes. Prevents fork bombs.                                    |
| `--memory 8g`                      | Memory limit.                                                                   |
| `--cpus 4`                         | CPU limit.                                                                      |
| `-v $(pwd):/workspace`             | The current project directory, read-write.                                      |
| `-v ~/.pi/agent:/pi-source:ro`     | Global pi config, read-only.                                                    |
| `-v ${PERSIST_VOLUME}:/home/pi:U`  | Persistent podman volume, writable. `:U` ensures correct ownership.             |
| `-i` (always)                      | Keep stdin open.                                                                |
| `-t` (conditional)                 | Allocate TTY only when stdin is a terminal.                                     |
| `~/.env` → `-e <var>`              | All variables from `~/.env` are forwarded to the container.                     |

### 8.5 Configuration

All settings are controlled via environment variables:

| Variable            | Default             | Description                                |
| ------------------- | ------------------- | ------------------------------------------ |
| `PI_AGENT_IMAGE`    | `pi-agent-isolated` | Container image name                       |
| `PI_AGENT_CONFIG`   | `~/.pi/agent`       | Path to global pi config directory         |
| `PI_AGENT_ENV_FILE` | `~/.env`            | Env file to forward variables to container |

### 8.6 Usage

```bash
cd ~/Projects/my-project

# Drop into a shell in the isolated environment
../pi-sandbox/run.sh

# Run pi directly
../pi-sandbox/run.sh pi -p "Review the codebase"

# Run arbitrary commands
../pi-sandbox/run.sh npm test

# Reset persistent state (destroys sessions, installed tools, etc.)
../pi-sandbox/run.sh --reset
```

### 8.7 Reset

`./run.sh --reset` removes the project's persistent volume. **All persistent data is destroyed**: sessions, installed tools (npm -g, pip), custom `.bashrc` edits, and any other state. The next run will re-initialize from current host config.

---

## 9. Security Model

### 9.1 Threat: Agent Reads Other Projects

**Mitigation:** The container's filesystem namespace contains only the current project directory mounted at `/workspace`. Other project directories do not exist in the container's mount namespace. This is enforced by the Linux kernel.

### 9.2 Threat: Agent Modifies Host Config

**Mitigation:** The `~/.pi/agent` mount is tagged `:ro` (read-only) at `/pi-source`. Any write attempt fails with `EPERM`. The agent reads global skills/settings from the synced copy in `/home/pi/.pi-agent-data/`, which is writable but isolated in the persistent volume.

### 9.3 Threat: Compromised Dependency Runs `rm -rf /`

**Mitigation:** The root filesystem is read-only (`--read-only`). Deleting system paths fails. The only writable paths are `/workspace` (project directory), `/home/pi` (persistent volume), and `/tmp` (ephemeral tmpfs).

### 9.4 Threat: Privilege Escalation

**Mitigation:** Multiple layers:

- `--cap-drop=ALL` — all Linux capabilities dropped
- `--security-opt=no-new-privileges` — kernel enforces NoNewPrivs
- Setuid/setgid bits stripped from the image
- Rootless container — user namespaces, no root on host

### 9.5 Threat: Container Escape to Host

**Mitigation:** Rootless Podman runs the container as the invoking user via user namespaces. A container escape yields only the host user's unprivileged permissions. The persistent volume is podman-managed (not a host bind mount), so it provides no path to the host filesystem.

### 9.6 Threat: Network Exfiltration

**Mitigation:** The container uses `--network=slirp4netns`, providing outbound access in a separate network namespace. The container is not reachable from the host or external network on any port.

**Limitation:** Outbound network is still allowed. A compromised package could exfiltrate project data from `/workspace`. This is the inherent trade-off of container-based isolation versus VM-based isolation.

**Additional mitigation:** npm lifecycle scripts are disabled by default (`ignore-scripts=true`), blocking the most common vector for post-install network callbacks.

### 9.7 Threat: Persistent Volume as Attack Vector

**Mitigation:** The volume is podman-managed, not a host bind mount. No host filesystem access. A compromised container can persist malicious files within the persistent volume (intra-project concern), but cannot reach the host. Use `./run.sh --reset` for a clean slate.

### 9.8 Threat: Resource Exhaustion

**Mitigation:** Resource limits prevent runaway processes:

| Resource | Limit   | Flag                |
| -------- | ------- | ------------------- |
| CPU      | 4 cores | `--cpus 4`          |
| Memory   | 8 GB    | `--memory 8g`       |
| PIDs     | 1024    | `--pids-limit 1024` |

### 9.9 Summary

| Threat                          | Mitigation                                           |
| ------------------------------- | ---------------------------------------------------- |
| Reading other projects          | Only `/workspace` is mounted                         |
| Modifying host config           | `/pi-source` is read-only                            |
| Modifying system files          | Root filesystem is read-only                         |
| Privilege escalation            | `--cap-drop=ALL`, `--security-opt=no-new-privileges` |
| setuid exploits                 | All setuid bits stripped from the image              |
| Host process visibility         | Separate PID namespace                               |
| Container runtime escape        | `--cap-drop=ALL` + rootless (user namespaces)        |
| Malicious npm scripts           | `ignore-scripts=true` by default                     |
| Fork bomb / resource exhaustion | `--pids-limit 1024`, `--memory 8g`, `--cpus 4`       |

---

## 10. Pair-Coding Workflow

Because the project directory is a bind mount, host and container share the same files:

| Action                                        | Host                                              | Container                                         |
| --------------------------------------------- | ------------------------------------------------- | ------------------------------------------------- |
| Edit `src/foo.ts`                             | ✅ In your editor (Neovim, VS Code, etc.)         | ✅ Visible immediately at `/workspace/src/foo.ts` |
| Agent edits `src/foo.ts`                      | ✅ Visible immediately on host                    | ✅ Written to `/workspace/src/foo.ts`             |
| Agent creates `.pi/skills/new-skill/SKILL.md` | ✅ Visible at `~/Projects/my-project/.pi/skills/` | ✅ Created at `/workspace/.pi/skills/`            |

No synchronization step. No image copies. No `rsync`. The kernel handles coherence.

---

## 11. Self-Improvement Workflow

### 11.1 Project-Local (Preferred)

The agent creates or modifies files in `.pi/` within the project directory:

```
/workspace/.pi/
├── settings.json          # Project-specific model, theme, etc.
├── skills/
│   └── my-project-skill/
│       ├── SKILL.md
│       └── scripts/
└── sessions/              # Optional: project-local session storage
```

**Benefits:** Travels with the repository (version control, code review). Does not affect other projects.

### 11.2 Global Config (Read-Only on Host, Writable in Volume)

The agent reads global skills from `/pi-source` (read-only mount) and has a writable copy at `/home/pi/.pi-agent-data/` (in the persistent volume). Any modifications are local to the container session and do not affect the host or other projects.

### 11.3 Agent Environment Awareness

The agent doesn't guess its environment — it is told explicitly via system prompt injection. The `config/APPEND_SYSTEM.md` file is copied into `$DATA_DIR/` by the entrypoint on every container start. Because `$DATA_DIR` is set as `PI_CODING_AGENT_DIR`, pi automatically includes it in the system prompt for every session (see §7.3).

This means the agent knows:

- It is running in a sandboxed container
- Exactly which tools are available (and which are not)
- The filesystem layout and what paths are writable
- Network constraints (outbound-only, no host access)
- Resource limits and persistence behavior
- Security boundaries (what it can and cannot access)

The file is committed in the repository and overwritten on every start, so it stays in sync with the actual container configuration. When the Containerfile adds a new tool or `run.sh` changes a flag, `APPEND_SYSTEM.md` is updated to match — and every subsequent container run reflects the change.

---

## 12. Operational Commands

### 12.1 Makefile Targets

```makefile
build:          Build the container image
shell:          Start an interactive shell in the container for the current project
pi:             Run pi in the container for the current project
clean:          Remove the container image
volumes:        List all persistent volumes
reset:          Reset persistent state for current project (destroys volume)
```

### 12.2 Manual Podman Commands

```bash
# List running agent containers
podman ps --filter "name=pi-agent-"

# List persistent volumes
podman volume ls --filter name=pi-agent-persist-

# Stop a specific container
podman stop pi-agent-my-project-12345

# Remove the image to force rebuild
podman rmi pi-agent-isolated

# Inspect what a container can see
podman run --rm -v "$(pwd):/workspace" pi-agent-isolated ls -la /
```

---

## 13. Testing

The test suite is organized as follows:

| Test File                     | Scope                                                                              |
| ----------------------------- | ---------------------------------------------------------------------------------- |
| `tests/test_config.py`        | Config file existence and content validation                                       |
| `tests/test_containerfile.py` | Containerfile directive assertions                                                 |
| `tests/test_run.py`           | `run.sh` flag generation, volume naming, env var forwarding                        |
| `tests/test_makefile.py`      | Makefile target validation                                                         |
| `tests/test_integration.py`   | Image build, filesystem layout, mounts, config sync, persistence, volume isolation |
| `tests/test_security.py`      | Read-only rootfs, dropped capabilities, no-new-privileges, socket access           |

Integration and security tests require Podman and are automatically skipped when Podman is not available.

```bash
pytest tests/
```

---

## 14. Future Enhancements (Out of Scope for v2)

| Feature | Description                                          | Motivation                         |
| ------- | ---------------------------------------------------- | ---------------------------------- |
| FE-002  | Outbound traffic logging/proxy                       | Reduce network exfiltration risk   |
| FE-003  | Pre-built image caching / registry                   | Faster startup on new machines     |
| FE-004  | Container health check / auto-restart                | Long-running agent sessions        |
| FE-005  | Integration with pi extensions for sandbox signaling | Agent knows it's in a sandbox      |
| FE-006  | Volume backup / snapshot mechanism                   | Safe experimentation with rollback |

### Implemented

| Feature | Description                                                                                                                     |
| ------- | ------------------------------------------------------------------------------------------------------------------------------- |
| FE-001  | Env file forwarding via `~/.env` — variables in `~/.env` are auto-forwarded to the container; override with `PI_AGENT_ENV_FILE` |

---

## 15. Glossary

| Term               | Definition                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------ |
| Bind mount         | A mount point that maps a host directory into a container directory                        |
| Mount namespace    | A Linux kernel feature that gives a process its own isolated view of the filesystem mounts |
| Persistent volume  | A podman-managed storage volume that survives container removal                            |
| Read-only rootfs   | Container flag (`--read-only`) that makes the base image filesystem immutable              |
| Rootless container | A container that runs without root privileges on the host, using user namespaces           |
| Slirp4netns        | A userspace network stack for containers, providing outbound access without host exposure  |
| tmpfs              | A temporary filesystem stored in RAM, lost when the mount is removed                       |
| User namespace     | A Linux kernel feature that maps container UIDs to different host UIDs                     |
| OCI                | Open Container Initiative, the standard format for container images                        |
| NoNewPrivs         | A Linux security flag that prevents a process from gaining new privileges                  |

---

## 16. References

- [Pi Coding Agent Documentation](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent/docs)
- [Podman Rootless Tutorial](https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md)
- [Arch Linux Docker Image](https://hub.docker.com/_/archlinux/)
- [Persistent Volume Design Doc](docs/specs/2026-05-05-persistent-volume-design.md)
- [Persistent Volume Implementation Plan](docs/plans/2026-05-05-persistent-volume.md)
- [Env Var Forwarding Plan](docs/plans/2026-04-25-env-var-forwarding.md)
