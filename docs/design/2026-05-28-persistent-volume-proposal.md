# Proposal: Persistent Per-Project Volume

## Intent

The current sandbox uses an ephemeral `/home/pi` tmpfs mount — all state (sessions, installed tools, shell customizations) is discarded when the container exits. This means sessions are lost between runs, globally-installed tools (`npm -g`, `pip`) must be reinstalled each time, and lock files must be recreated on every invocation.

This change replaces the ephemeral tmpfs with a per-project persistent podman volume, enabling sessions, installed tools, and shell customizations to survive across container runs while maintaining isolation between projects.

## Scope

**In scope:**
- Per-project persistent podman volume (`pi-agent-persist-<project>-<hash>`)
- Volume mounted at `/home/pi` with `:U` ownership flag
- Entrypoint script for config sync (rsync) and first-run setup
- Automatic config sync from host (`/pi-source:ro`) into persistent volume
- First-run package manager configuration (`npm`, `pip` → `$HOME/.local`)
- `--reset` flag to destroy the persistent volume
- Volume isolation between projects (unique volume per project path)
- Updated `run.sh`, `Containerfile`, `config/.bashrc`, `Makefile`
- Integration tests for persistence, isolation, and config sync

**Out of scope:**
- Cross-project volume sharing
- Automatic volume pruning or cleanup
- Volume encryption
- Backup/restore of persistent volumes

## Approach

A podman-managed volume named `pi-agent-persist-<project>-<hash>` is created for each project and mounted at `/home/pi` with the `:U` ownership flag. The volume name is derived from the project path (basename for readability, 8-char SHA-256 hash suffix for uniqueness).

On every container start, the entrypoint script:
1. Syncs host config from `/pi-source` (read-only mount of `~/.pi/agent`) into `/home/pi/.pi-agent-data/` using `rsync`, preserving user-generated data (sessions, lock files)
2. Performs first-run setup (`.bashrc` copy, `.bash_profile` creation, package manager config)
3. Exports environment variables and execs the user command

The `run.sh` script derives the volume name, creates it idempotently, and mounts it. A `--reset` flag removes the volume for a clean slate.

## Impact

- `run.sh` — volume derivation/creation, `/pi-source:ro` mount, persistent volume mount, `--reset` flag
- `Containerfile` — add `rsync` package, copy entrypoint, set `ENTRYPOINT`
- `config/entrypoint.sh` — new file: config sync, first-run setup, environment exports
- `config/.bashrc` — add `PATH`, `PYTHONUSERBASE`, `NPM_CONFIG_PREFIX`, `PI_CODING_AGENT_DIR` exports
- `Makefile` — add `volumes` and `reset` targets
- `tests/test_integration.py` — persistence, volume isolation, config sync tests
- `tests/test_run.py` — assertions for volume mount, `--reset`, no tmpfs
- `tests/conftest.py` — volume cleanup fixture
- `README.md` — update architecture, security model, filesystem table
