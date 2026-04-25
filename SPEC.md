# Pi Agent Isolation Environment — Specification

> **Document Version:** 1.0  
> **Last Updated:** 2026-04-22

---

## 1. Motivation

### 1.1 The Problem

AI coding agents like pi-coding-agent are powerful autonomous tools that execute arbitrary shell commands, read and write files, and install npm packages. This creates two distinct risks:

1. **Cross-project contamination.** An agent working on `project-a` should not be able to read secrets, source code, or configuration from `project-b`.
2. **Compromised dependency attacks.** A malicious or hijacked npm package can execute arbitrary code during `npm install` or at runtime, potentially exfiltrating data, modifying source files, or running destructive commands.

### 1.2 Why Existing Approaches Are Insufficient

- **Running directly on the host:** The agent has access to the entire host filesystem, all SSH keys, all environment variables, and all projects.
- **Virtual machines (Firecracker/QEMU):** Provides strong kernel-level isolation but introduces enormous operational complexity — networking, storage synchronization, boot management, image building — that makes the security model opaque and error-prone. If you cannot hold the entire system in your head, you cannot reason about its security.
- **System-wide container (Docker/Podman without project isolation):** Protects the host kernel but still exposes all projects and global configuration to the agent.

### 1.3 Design Goal

The simplest possible system that satisfies both isolation requirements, where the entire security model can be understood by reading a single shell command.

---

## 2. Principles

| Principle                        | Implication                                                                                                               |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **One project, one environment** | Each project runs in an entirely separate filesystem namespace.                                                           |
| **Explicit visibility**          | The agent sees _only_ directories explicitly mounted into its environment.                                                |
| **Read-only global config**      | The agent can use global settings and skills but cannot mutate them.                                                      |
| **Mutable project workspace**    | The agent can read and write project files, which persist on the host.                                                    |
| **No root privileges**           | The container runtime is rootless. Even a complete container escape yields only the host user's unprivileged permissions. |
| **Transparent to the user**      | Pair-coding works naturally: host editor and container agent see the same files simultaneously.                           |

---

## 3. Architecture

### 3.1 High-Level Model

```
┌─────────────────────────────────────────────┐
│                  HOST (Arch Linux)           │
│                                              │
│  ┌─────────────────┐  ┌─────────────────┐   │
│  │ ~/.pi/agent/    │  │ ~/Projects/      │   │
│  │ (global config) │  │                  │   │
│  └────────┬────────┘  │  ├─ project-a/   │   │
│           │           │  ├─ project-b/   │   │
│           │           │  └─ project-c/   │   │
│           │           └─────────────────┘   │
│           │                                  │
│  ┌────────▼──────────────────────┐           │
│  │  Container A (project-a)      │           │
│  │  /pi-data → ~/.pi/agent (ro)  │           │
│  │  /workspace → project-a (rw)  │           │
│  │  [no access to project-b]     │           │
│  └───────────────────────────────┘           │
│                                              │
│  ┌───────────────────────────────┐           │
│  │  Container B (project-b)      │           │
│  │  /pi-data → ~/.pi/agent (ro)  │           │
│  │  /workspace → project-b (rw)  │           │
│  │  [no access to project-a]     │           │
│  └───────────────────────────────┘           │
└─────────────────────────────────────────────┘
```

### 3.2 What the Agent Can See

Inside any container:

| Path                | Source                  | Permissions           | Contents                                     |
| ------------------- | ----------------------- | --------------------- | -------------------------------------------- |
| `/workspace`        | `~/Projects/<project>/` | read-write            | Entire project directory                     |
| `/pi-data`          | `~/.pi/agent/`          | read-only             | Global settings, skills, sessions (optional) |
| `/pi-data/sessions` | `~/.pi/agent/sessions/` | read-write (optional) | Shared session history                       |

The agent **cannot** see:

- Any other project directory
- Host home directory outside the above mounts
- Host SSH keys (`~/.ssh/`)
- Host system configuration (`/etc`, `/var`)
- Other users' files

### 3.3 What the Agent Can Do

| Action                                       | Allowed?   | Notes                                                                 |
| -------------------------------------------- | ---------- | --------------------------------------------------------------------- |
| Read/write project source                    | ✅ Yes     | Persisted on host immediately                                         |
| Install project dependencies (`npm install`) | ✅ Yes     | Within `/workspace` only                                              |
| Create project-local skills                  | ✅ Yes     | Written to `.pi/skills/` inside project                               |
| Modify project settings                      | ✅ Yes     | Written to `.pi/settings.json` inside project                         |
| Read global skills/settings                  | ✅ Yes     | Via read-only `/pi-data` mount                                        |
| Modify global skills/settings                | ❌ No      | `/pi-data` is mounted read-only                                       |
| Access other projects                        | ❌ No      | Not mounted, does not exist in container                              |
| Access host SSH keys                         | ❌ No      | Not mounted                                                           |
| Escalate to root on host                     | ❌ No      | Rootless container; host kernel would need a privilege escalation bug |
| Exfiltrate data over network                 | ⚠️ Partial | Can make network requests, but only has access to this project's data |

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

### 4.3 Init System: Bash

No systemd. No custom init scripts. The container starts a shell. When the shell exits, the container stops. This is the default container behavior.

---

## 5. Directory Structure

### 5.1 Host-Side (This Repository)

```
~/Projects/pi-sandbox/          # Repository root
├── SPEC.md                         # This document
├── Containerfile                   # Image definition
├── run.sh                          # Launch script
├── Makefile                        # Common commands
└── config/
    └── .bashrc                     # Shell initialization for the container
```

### 5.2 Host-Side (Runtime State)

Podman stores its rootless data in `~/.local/share/containers/` automatically. No manual state management required.

### 5.3 Guest-Side (Inside Container)

```
/
├── bin/                            # System binaries
├── workspace/                      # Bind mount: current project
│   ├── src/
│   ├── .pi/                        # Project-local settings and skills
│   │   ├── settings.json
│   │   └── skills/
│   └── package.json
├── pi-data/                        # Bind mount: ~/.pi/agent (ro)
│   ├── settings.json
│   ├── skills/
│   └── sessions/                   # Optionally rw-mounted
├── home/
│   └── pi/                         # Container user home
│       └── .bashrc                 # Container shell config
└── ... (standard Arch Linux root)
```

---

## 6. Container Image (`Containerfile`)

```dockerfile
FROM archlinux:latest

# Install base tools and Node.js LTS
RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm nodejs npm git openssh bash && \
    pacman -Scc --noconfirm

# Install pi-coding-agent globally
RUN npm install -g @mariozechner/pi-coding-agent

# Container user (matches typical host UID for file ownership simplicity)
RUN useradd -m -u 1000 -s /bin/bash pi

# Environment
ENV PI_CODING_AGENT_DIR=/pi-data
ENV HOME=/home/pi
ENV TERM=xterm-256color

USER pi
WORKDIR /workspace

CMD ["/bin/bash", "--login"]
```

### 6.1 Build

```bash
podman build -t pi-agent-isolated .
```

### 6.2 Why No Multi-Stage Optimization

Simplicity. The image is built once and cached. A single `pacman -S` layer is acceptable for a development environment.

---

## 7. Launch Script (`run.sh`)

```bash
#!/bin/bash
set -euo pipefail

# Configuration
IMAGE_NAME="pi-agent-isolated"
CONTAINER_NAME="pi-agent-$(basename "$PWD")"
GLOBAL_CONFIG="${HOME}/.pi/agent"

# Ensure the image exists
if ! podman image exists "$IMAGE_NAME"; then
    echo "Building image ${IMAGE_NAME}..."
    podman build -t "$IMAGE_NAME" "$(dirname "$0")"
fi

# Run container with explicit mounts only
exec podman run -it --rm \
    --name "$CONTAINER_NAME" \
    --userns=keep-id \
    -v "$(pwd):/workspace" \
    -v "${GLOBAL_CONFIG}:/pi-data:ro" \
    -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
    -e OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
    "$IMAGE_NAME" \
    "$@"
```

### 7.1 Key Flags Explained

| Flag                         | Purpose                                                                                     |
| ---------------------------- | ------------------------------------------------------------------------------------------- |
| `--rm`                       | Container is deleted when exited. No stale state.                                           |
| `--userns=keep-id`           | Maps container UID to host UID. Files written by the agent appear owned by you on the host. |
| `-v $(pwd):/workspace`       | The _entire_ project directory, read-write.                                                 |
| `-v ~/.pi/agent:/pi-data:ro` | Global pi config, read-only.                                                                |
| `-e ANTHROPIC_API_KEY=...`   | API keys injected from host environment. Never written to disk.                             |

### 7.2 Usage

```bash
cd ~/Projects/my-project

# Drop into a shell in the isolated environment
../pi-sandbox/run.sh

# Run pi directly
../pi-sandbox/run.sh pi -p "Review the codebase"

# Run arbitrary commands
../pi-sandbox/run.sh npm test
```

---

## 8. Security Model

### 8.1 Threat: Agent Reads Other Projects

**Mitigation:** The container's filesystem namespace contains only the current project directory mounted at `/workspace`. Other project directories do not exist in the container's mount namespace. This is enforced by the Linux kernel; no application-level sandboxing is involved.

### 8.2 Threat: Agent Modifies Global Config

**Mitigation:** The `~/.pi/agent` mount is tagged `:ro` (read-only). Any write attempt fails with `EPERM`. The agent can read global skills and settings, preserving consistency, but cannot break shared configuration.

### 8.3 Threat: Compromised Dependency Runs `rm -rf /`

**Mitigation:** The container has its own root filesystem (from the Arch image). Deleting `/` destroys the container, not the host. The only host-mounted paths are the project directory and read-only global config; both are protected by standard Linux permissions.

### 8.4 Threat: Container Escape to Host

**Mitigation:** Rootless Podman runs the container as the invoking user via user namespaces. A container escape yields the same privileges the user already has. There is no root privilege to escalate to. Container escapes are still serious (the user could access their own files), but this project's design ensures that even a complete escape only exposes the current project directory, because that is the only sensitive data mounted into the container.

### 8.5 Threat: Network Exfiltration

**Limitation:** The container shares the host network namespace by default (unless `--network=none` or `--network=slirp4netns` is used). A compromised dependency can make network requests and exfiltrate the project's data. This is the inherent limitation of container-based isolation versus VM-based isolation.

**Mitigation options (in order of complexity):**

1. **Accept the risk** for development work (standard industry practice).
2. **Use `--network=none`** for fully offline work (breaks API calls to LLM providers).
3. **Use `--network=slirp4netns`** for a separate network namespace with controlled forwarding (future enhancement).
4. **Run a local HTTP proxy** that logs/inspects all outbound traffic (future enhancement).

---

## 9. Pair-Coding Workflow

Because the project directory is a bind mount, host and container share the same files:

| Action                                        | Host                                              | Container                                         |
| --------------------------------------------- | ------------------------------------------------- | ------------------------------------------------- |
| Edit `src/foo.ts`                             | ✅ In your editor (Neovim, VS Code, etc.)         | ✅ Visible immediately at `/workspace/src/foo.ts` |
| Agent edits `src/foo.ts`                      | ✅ Visible immediately on host                    | ✅ Written to `/workspace/src/foo.ts`             |
| Agent creates `.pi/skills/new-skill/SKILL.md` | ✅ Visible at `~/Projects/my-project/.pi/skills/` | ✅ Created at `/workspace/.pi/skills/`            |

No synchronization step. No image copies. No `rsync`. The kernel handles coherence.

---

## 10. Self-Improvement Workflow

The agent can improve itself in two scopes:

### 10.1 Project-Local (Preferred)

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

**Benefits:**

- Travels with the repository (version control, code review)
- Does not affect other projects
- Host pi instance also loads project-local `.pi/` configuration

### 10.2 Global (Read-Only)

The agent reads global skills from `/pi-data/skills/` but cannot write to them.

**Rationale:** Global skills are shared across all projects. An agent bug or prompt injection that corrupted global skills would affect every future agent session. Project-local skills are the safe default.

---

## 11. Operational Commands

### 11.1 Makefile Targets (Planned)

```makefile
build:          Build the container image
shell:          Start an interactive shell in the container for the current project
pi:             Run pi in the container for the current project
clean:          Remove the container image
```

### 11.2 Manual Podman Commands

```bash
# List running agent containers
podman ps --filter "name=pi-agent-"

# Stop a specific container
podman stop pi-agent-my-project

# Remove the image to force rebuild
podman rmi pi-agent-isolated

# Inspect what a container can see
podman run --rm -v "$(pwd):/workspace" pi-agent-isolated ls -la /
```

---

## 12. Future Enhancements (Out of Scope for v1)

| Feature | Description                                          | Motivation                         |
| ------- | ---------------------------------------------------- | ---------------------------------- |
| FE-001  | Per-project API key injection via `.env`             | Avoid passing keys via environment |
| FE-002  | `--network=slirp4netns` with outbound logging        | Reduce network exfiltration risk   |
| FE-003  | Pre-built image caching / registry                   | Faster startup on new machines     |
| FE-004  | Container health check / auto-restart                | Long-running agent sessions        |
| FE-005  | Integration with pi extensions for sandbox signaling | Agent knows it's in a sandbox      |

---

## 13. References

- [Pi Coding Agent Documentation](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent/docs)
- [Podman Rootless Tutorial](https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md)
- [Arch Linux Docker Image](https://hub.docker.com/_/archlinux/)

---

## 14. Glossary

| Term               | Definition                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------ |
| Bind mount         | A mount point that maps a host directory into a container directory                        |
| Mount namespace    | A Linux kernel feature that gives a process its own isolated view of the filesystem mounts |
| Rootless container | A container that runs without root privileges on the host, using user namespaces           |
| User namespace     | A Linux kernel feature that maps container UIDs to different host UIDs                     |
| OCI                | Open Container Initiative, the standard format for container images                        |
