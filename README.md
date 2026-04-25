# Pi Agent Isolation Environment

Per-project isolation for the [pi-coding-agent](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent) using rootless Podman containers.

Each project runs in its own container with access only to its own directory. No cross-project leaks, no host filesystem exposure, no root privileges.

## The Problem

AI coding agents execute arbitrary shell commands, read files, and install packages. Running them directly on the host means:

- An agent on `project-a` can read secrets from `project-b`
- A compromised npm package can access SSH keys, dotfiles, and every project on the machine

This project solves both problems with a simple container-per-project model.

## Quick Start

```bash
# From any project directory
../pi-sandbox/run.sh                    # interactive shell
../pi-sandbox/run.sh pi -p "Review code" # run pi directly
../pi-sandbox/run.sh npm test           # run any command
```

Or use the Makefile targets:

```bash
make shell    # interactive shell in the container
make pi       # run pi in the container
make build    # build the container image
make clean    # remove the image
```

The first run builds the Arch Linux container image automatically. Subsequent runs start instantly.

## How It Works

```
Host filesystem                    Container
───────────────                   ─────────

~/Projects/my-project/    ──────►  /workspace     (read-write)
~/.pi/agent/              ──────►  /pi-data       (read-only)
~/.pi/agent/sessions/     ──────►  /pi-data/sessions (read-write)

(other projects, ~/.ssh, /etc)  ✗ not visible
```

- **One project, one container.** Only the current working directory is mounted.
- **Read-only global config.** The agent can use global skills and settings but cannot modify them.
- **Rootless.** Even a full container escape yields only the host user's unprivileged permissions.
- **Transparent pair-coding.** Because the project directory is a bind mount, your host editor and the container agent see the same files simultaneously — no sync step needed.

## Architecture

| Component        | Description                                                  |
| ---------------- | ------------------------------------------------------------ |
| `Containerfile`  | Arch Linux image with Node.js, git, and pi installed         |
| `run.sh`         | Launch script — builds image, sets up mounts, runs container |
| `Makefile`       | Convenience targets (`build`, `shell`, `pi`, `clean`)        |
| `config/.bashrc` | Shell prompt and aliases inside the container                |
| `tests/`         | Pytest suite covering build, filesystem, and integration     |

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

### Container Filesystem

| Path                | Source                  | Permissions |
| ------------------- | ----------------------- | ----------- |
| `/workspace`        | Current directory       | Read-write  |
| `/pi-data`          | `~/.pi/agent/`          | Read-only   |
| `/pi-data/sessions` | `~/.pi/agent/sessions/` | Read-write  |

## Security Model

| Threat                            | Mitigation                                                |
| --------------------------------- | --------------------------------------------------------- |
| Agent reads other projects        | Only current directory is mounted                         |
| Agent modifies global config      | `/pi-data` is mounted read-only                           |
| Compromised dependency `rm -rf /` | Destroys the container, not the host                      |
| Container escape to host          | Rootless — yields only current user's permissions         |
| Network exfiltration              | ⚠️ Inherent limitation of container isolation (see below) |

### Network Limitation

The container shares the host network namespace by default. A compromised dependency can make outbound requests with the current project's data. Mitigation options:

1. **Accept the risk** (standard practice for development containers)
2. **`--network=none`** for fully offline work (breaks LLM API calls)
3. **`--network=slirp4netns`** for a separate network namespace (future enhancement)

For a detailed threat analysis, see [SPEC.md](SPEC.md).

## Self-Improvement

The agent can create **project-local skills** in `.pi/skills/` within the project directory. These travel with the repository under version control and do not affect other projects.

Global skills in `~/.pi/agent/skills/` are read-only — an agent cannot corrupt shared configuration.

## Testing

```bash
pytest tests/
```

The test suite covers:

- **Unit tests** — script existence, Containerfile directives, Makefile targets, config files
- **Integration tests** — image build, filesystem layout, mount correctness (read-only global config, writable sessions), end-to-end `run.sh` workflow

Integration tests require Podman. Tests are automatically skipped when Podman is not available.

## Requirements

- [Podman](https://podman.io/) (rootless mode)
- Bash 4+

## See Also

- [SPEC.md](SPEC.md) — Full specification with architecture diagrams, security analysis, and design rationale
- [Pi Coding Agent](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent)
- [Podman Rootless Tutorial](https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md)
