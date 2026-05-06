# Pi Agent Isolation Environment

Per-project isolation for the [pi-coding-agent](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent) using rootless Podman containers.

Each project runs in its own container with a persistent volume. Sessions, installed tools, and shell customizations survive across runs. Projects remain isolated from each other.

## The Problem

AI coding agents execute arbitrary shell commands, read files, and install packages. Running them directly on the host means:

- An agent on `project-a` can read secrets from `project-b`
- A compromised npm package can access SSH keys, dotfiles, and every project on the machine
- Sessions, installed tools, and settings are lost every time the container exits

This project solves all three problems with a simple container-per-project model backed by persistent volumes.

## Quick Start

```bash
git clone https://github.com/naripok/pi-sandbox.git ~/pi-sandbox
cd ~/pi-sandbox && ./install.sh
```

Add the printed alias to your `~/.bashrc` or `~/.zshrc`, then use it from any project:

```bash
cd ~/Projects/my-project
pi-sandbox pi -p "Review this codebase"   # run pi
pi-sandbox bash                           # interactive shell
pi-sandbox npm test                       # any command inside
pi-sandbox --reset                        # wipe persistent volume
```

The first run builds the Arch Linux container image automatically. Subsequent runs start instantly.

## How It Works

```
Host filesystem                     Container
───────────────                    ─────────

~/Projects/my-project/     ──────►  /workspace       (read-write bind mount)
~/.pi/agent/               ──────►  /pi-source       (read-only, host immutable)
                                    /home/pi         (persistent podman volume, writable)

podman volume: pi-agent-persist-myproject-a1b2c3d4
```

- **One project, one container, one volume.** Each project gets its own persistent volume named `pi-agent-persist-<project>-<hash>`.
- **Read-only host config.** The agent can use global skills and settings but cannot modify them. Host config changes are synced into the volume on every start.
- **Persistent state.** Sessions, globally-installed tools (npm, pip), and shell customizations survive across container runs.
- **Rootless.** Even a full container escape yields only the host user's unprivileged permissions.
- **Transparent pair-coding.** Because the project directory is a bind mount, your host editor and the container agent see the same files simultaneously — no sync step.

## Architecture

| Component                 | Description                                                           |
| ------------------------- | --------------------------------------------------------------------- |
| `Containerfile`           | Arch Linux image with Node.js, git, pi, rsync, and entrypoint         |
| `config/entrypoint.sh`    | Syncs config, sets up volume, drops privileges to pi user             |
| `config/.bashrc`          | Shell prompt, aliases, and persistent PATH configuration              |
| `config/APPEND_SYSTEM.md` | Agent environment reference — auto-injected into the system prompt    |
| `run.sh`                  | Launch script — builds image, creates volume, runs container          |
| `install.sh`              | Prerequisite checks, image build, and alias setup for host-wide use   |
| `Makefile`                | Convenience targets (`build`, `shell`, `pi`, `clean`, `reset`)        |
| `tests/`                  | Pytest suite covering build, filesystem, persistence, and integration |

## Agent Environment Awareness

The sandboxed agent knows it is in a container — and exactly what it can and cannot do. This is not guessed or inferred; it is explicitly told via system prompt injection.

The entrypoint copies `config/APPEND_SYSTEM.md` into the agent's config directory on every container start. pi automatically includes this file in the system prompt, so every agent session receives a complete description of the sandbox: filesystem layout, installed tools, security boundaries, network configuration, resource limits, persistence behavior, and troubleshooting tips.

The file is committed in the repository and overwritten on every start, so it stays in sync with the actual container configuration. When the Containerfile adds a new tool or `run.sh` changes a flag, `APPEND_SYSTEM.md` is updated to match.

## Configuration

All settings are controlled via environment variables:

| Variable            | Default             | Description                                |
| ------------------- | ------------------- | ------------------------------------------ |
| `PI_AGENT_IMAGE`    | `pi-agent-isolated` | Container image name                       |
| `PI_AGENT_CONFIG`   | `~/.pi/agent`       | Path to global pi config directory         |
| `PI_AGENT_ENV_FILE` | `~/.env`            | Env file to forward variables to container |

### Environment Variables

Variables defined in `~/.env` (or the path set by `PI_AGENT_ENV_FILE`) are automatically forwarded into the container. This is how you pass API keys (`VLLM_API_KEY`, `OPENROUTER_API_KEY`, etc.) without baking them into the image.

Example `~/.env`:

```
OPENROUTER_API_KEY=sk-or-...
VLLM_API_KEY=...
```

### Sandbox Environment Variables

In addition to forwarded host variables, the entrypoint injects two sandbox-specific environment variables on every container start:

| Variable       | Description                                                           |
| -------------- | --------------------------------------------------------------------- |
| `PI_OFFLINE`   | Disables all outbound network calls from the pi agent                 |
| `PI_TELEMETRY` | Prevents the agent from sending usage or telemetry data to any server |

These ensure the sandboxed agent never leaks data outside the container, regardless of what the host `~/.env` contains. They are set in `config/entrypoint.sh` alongside other persistent sandbox defaults.

### Container Filesystem

| Path                                | Source                      | Permissions |
| ----------------------------------- | --------------------------- | ----------- |
| `/workspace`                        | Current directory           | Read-write  |
| `/pi-source`                        | `~/.pi/agent/`              | Read-only   |
| `/home/pi`                          | Persistent podman volume    | Read-write  |
| `/home/pi/.pi-agent-data/`          | Synced from `/pi-source/`   | Read-write  |
| `/home/pi/.pi-agent-data/sessions/` | Session history             | Read-write  |
| `/home/pi/.local/`                  | User-level package installs | Read-write  |

### Config Sync

On every container start, the entrypoint syncs host config into the persistent volume:

| Synced from host                    | Preserved in volume         |
| ----------------------------------- | --------------------------- |
| New skills in `~/.pi/agent/skills/` | Sessions in `sessions/`     |
| Updated `AGENTS.md`                 | Lock files (`*.lock`)       |
| New/changed settings files          | Any container-created files |

Files deleted from the host are **not** removed from the volume (to avoid accidentally deleting user data). Use `./run.sh --reset` for a clean slate.

## Security Model

| Threat                             | Mitigation                                                                                                                                          |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Agent reads other projects         | Only current directory mounted as `/workspace`                                                                                                      |
| Agent modifies host config         | Mounted `:ro` at `/pi-source` — writes go to volume only                                                                                            |
| Agent escapes to host filesystem   | All existing hardening unchanged (`--cap-drop=ALL`, `--read-only`, `--security-opt=no-new-privileges`, user namespaces)                             |
| Persistent volume as attack vector | Volume is podman-managed, not a host bind mount. No host filesystem access. Intra-project persistence of malicious files is possible but contained. |
| Volume ownership escalation        | `:U` flag ensures correct ownership; entrypoint also chowns as defense-in-depth                                                                     |

## Reset

```bash
./run.sh --reset
```

This removes the project's persistent volume. **All persistent data is destroyed**: sessions, installed tools, custom `.bashrc` edits, and any other state. The next run will re-initialize from current host config.

## Testing

```bash
pytest tests/
```

The test suite covers:

- **Unit tests** — script existence, Containerfile directives, Makefile targets, config files, run.sh flag generation
- **Integration tests** — image build, filesystem layout, mount correctness, config sync, persistence across runs, volume isolation
- **Security tests** — read-only rootfs, dropped capabilities, no-new-privileges, no host socket access

Integration tests require Podman. Tests are automatically skipped when Podman is not available.

## Requirements

- [Podman](https://podman.io/) (rootless mode)
- Bash 4+

## See Also

- [docs/SPEC.md](docs/SPEC.md) — Full specification with architecture diagrams, security analysis, and design rationale
- [Persistent Volume Design](docs/specs/2026-05-05-persistent-volume-design.md) — Design doc for the persistent volume feature
- [Pi Coding Agent](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent)
- [Podman Rootless Tutorial](https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md)
