# Prototype C: Persistent Per-Project Volume

## Problem

Prototypes A and B provide ephemeral writable layers — all state (sessions, lock files, settings changes) is discarded when the container exits. This means:

- Sessions are lost between runs
- Globally-installed tools (npm, pip, uv) must be reinstalled each time
- Shell customizations (.bashrc, env vars) don't persist
- Lock files must be recreated on every invocation

The user needs a persistent layer per project that survives across container runs while maintaining isolation between projects.

## Architecture

```
Host filesystem                     Container
───────────────                    ─────────

~/Projects/my-project/     ──────►  /workspace       (read-write bind mount)
~/.pi/agent/               ──────►  /pi-source       (read-only, host immutable)
                                     /home/pi         (persistent podman volume, writable)

podman volume: pi-agent-persist-myproject-a1b2c3d4
```

The persistent volume is a podman-managed volume stored in `~/.local/share/containers/storage/volumes/`. It is **not** a host bind mount — the agent cannot reach the host filesystem through it. It contains:

- `/home/pi/.pi-agent-data/` — pi config, sessions, lock files (synced from host config on every start)
- `/home/pi/.bashrc` — shell configuration
- `/home/pi/.local/` — user-level package installations (npm, pip, uv)

On every container start, the entrypoint runs `rsync` to merge host config changes (`/pi-source`) into `.pi-agent-data/`, propagating new and modified files (skills, settings, AGENTS.md) while preserving user-generated data (sessions, state, installed tools).

## Design Decisions

### D1: Persistent volume replaces fuse-overlayfs (not combined)

The persistent volume is the sole writable layer. No `fuse-overlayfs` dependency.

**Rationale**: The persistent volume already solves the lock-file problem (it's writable). One writable volume is simpler than two. All per-project state lives in one place. Host config is still protected — mounted `:ro` at `/pi-source`, never directly bound as a writable target.

### D2: Volume mounted at `/home/pi`

**Rationale**: This is the natural writable directory in the container. It's where `$HOME` points, where npm/pip install user-level packages, where shell configs live. Replacing the tmpfs mount with a persistent volume means all "dependencies and env changes" naturally persist without special configuration.

### D3: Volume name derived from project path

```bash
PROJECT_PATH="$(realpath "$(pwd)")"
PROJECT_NAME="$(basename "$PROJECT_PATH")"
PERSIST_VOLUME="pi-agent-persist-${PROJECT_NAME}-$(echo "$PROJECT_PATH" | sha256sum | cut -c1-8)"
```

The basename makes `podman volume ls` output meaningful. The 8-char hash suffix (32 bits) guarantees uniqueness. Example: `pi-agent-persist-myproject-a1b2c3d4`.

### D4: Entrypoint syncs config on every start (not unconditional overwrite)

The entrypoint must NOT unconditionally copy from `/pi-source` — that would overwrite sessions, installed tools, and user state on every run. Instead it uses `rsync` (see D8) to merge only new/modified config files while preserving user data. `.bashrc` and package manager setup remain first-run-only since they don't change on the host.

**Rationale**: Unlike prototypes A and B (which are always fresh), the persistent volume accumulates state. We need a merge strategy, not a replace strategy.

### D5: Package manager paths configured for persistence

With `--read-only` rootfs, `npm install -g` and `pip install` write to `/usr/` which is blocked. The entrypoint configures package managers to use `/home/pi/.local/` on first run:

```bash
if [ ! -d /home/pi/.local ]; then
    mkdir -p /home/pi/.local
    npm config set prefix "$HOME/.local"
fi
```

And `.bashrc` / the entrypoint ensures `PATH` includes `$HOME/.local/bin` and `PYTHONUSERBASE=$HOME/.local`.

### D6: Volume ownership handled by podman `:U` flag

Podman volumes are initialized as `root:root 0755`. The `:U` suffix on the mount (`-v "${PERSIST_VOLUME}:/home/pi:U"`) tells podman to recursively chown the mount point to the container user. This is simpler and more reliable than a root entrypoint chown.

### D7: Reset mechanism

`./run.sh --reset` removes the project's persistent volume so the next run starts fresh. **This destroys all persistent data**: sessions, installed tools (`npm -g`, `pip`), custom `.bashrc` edits, and any other state accumulated in the volume. The next run will re-initialize from current host config.

This is a nuclear option — needed for accumulated state cleanup or when the volume is corrupted. Normal config drift is handled by the automatic sync (D8).

### D8: Config sync merges host changes into persistent volume

On every container start, the entrypoint runs:

```bash
rsync -au --exclude='sessions/' --exclude='*.lock' /pi-source/. /home/pi/.pi-agent-data/
```

This propagates new and modified config files (skills, AGENTS.md, settings) from the host into the persistent volume, while preserving user-generated data:

| Synced from host | Preserved in volume |
|------------------|-------------------|
| New skills added to `~/.pi/agent/skills/` | Sessions in `sessions/` |
| Updated `AGENTS.md` | Lock files (`*.lock`) |
| New/changed settings files | Any files created inside the container |

**Not handled**: Files deleted from the host are not removed from the volume. This is intentional — it avoids accidentally deleting user data that happens to share a name. If cleanup is needed, `--reset` provides a clean slate.

**Rationale**: Eliminates the stale config problem without requiring the user to nuke their persistent data. The `rsync` is fast when nothing has changed (typical case), so the overhead is negligible.

## File Changes

### `run.sh`

- Derive `PERSIST_VOLUME` from project path
- `podman volume create "$PERSIST_VOLUME"` (idempotent — no-op if exists)
- Remove `fuse-overlayfs` logic and tmpfs mount for `/home/pi`
- Add `-v "${GLOBAL_CONFIG}:/pi-source:ro"` (was `/pi-data:ro`)
- Add `-v "${PERSIST_VOLUME}:/home/pi:U"` (persistent, auto-chowned)
- Remove `-v "${GLOBAL_CONFIG}/sessions:/pi-data/sessions:rw"` (no longer needed)
- Add `--reset` flag to delete the volume and exit
- Keep all security flags (`--read-only`, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--tmpfs /tmp`, `--pids-limit`, `--memory`, `--cpus`)
- Update `OVERLAY_*` cleanup trap → no-op or remove

### `config/entrypoint.sh`

New file. The Containerfile sets `USER root` so the entrypoint runs as root. It drops to `pi` via `su`:

```bash
#!/bin/bash
set -euo pipefail

# Initialize persistent volume on first run only.
# This preserves user customizations, sessions, and installed tools across runs.
DATA_DIR=/home/pi/.pi-agent-data

# Sync host config into persistent volume on every start.
# Propagates new/modified files while preserving user-generated data.
rsync -au --exclude='sessions/' --exclude='*.lock' /pi-source/. "$DATA_DIR/"

# Copy .bashrc on first run only
if [ ! -f /home/pi/.bashrc ]; then
    cp /etc/pi/.bashrc /home/pi/.bashrc
fi

# Ensure pi user owns their home directory (paranoia — :U should handle this)
chown -R pi:pi /home/pi

# Configure package managers for user-level installs on first run
if [ ! -d /home/pi/.local ]; then
    mkdir -p /home/pi/.local
    su -l pi -c 'npm config set prefix "$HOME/.local"'
fi

export PI_CODING_AGENT_DIR="$DATA_DIR"

# Drop privileges and exec the user command
exec su -l pi -- "$@"
```

### `Containerfile`

- Add `shadow` package (for `su` command) and `rsync` (for config sync)
- Copy entrypoint script, set permissions
- Set `ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]`
- Remove `ENV PI_CODING_AGENT_DIR=/pi-data` (set by entrypoint instead)
- Keep `COPY config/.bashrc /etc/pi/.bashrc` (source for first-run copy)
- Keep all hardening (setuid stripping, USER pi, etc.)
- Remove `--mount type=tmpfs,destination=/home/pi` documentation references

### `config/.bashrc`

Add to the existing content:

```bash
export PATH="$HOME/.local/bin:$PATH"
export PYTHONUSERBASE="$HOME/.local"
export NPM_CONFIG_PREFIX="$HOME/.local"
```

This ensures that tools installed into `/home/pi/.local/` are immediately available.

### `tests/test_integration.py`

- Update `test_global_config_is_readonly_in_container`: writes to `/home/pi/.pi-agent-data` succeed in container, host config unchanged on host
- Update `test_sessions_dir_is_writable_in_container`: sessions at `/home/pi/.pi-agent-data/sessions`
- Add `test_persistence_across_runs`: write marker, exit, run again, verify marker still present
- Add `test_volume_isolation`: project A's volume doesn't contain project B's data
- Add `test_config_sync`: modify a config file on host, start container, verify updated file present while sessions/lock files are preserved

### `tests/test_run.py`

- Assert `:/pi-source:ro` in podman command (was `:/pi-data:ro`)
- Assert `:/home/pi:U` in podman command (persistent volume)
- Assert no `--mount type=tmpfs,destination=/home/pi`
- Assert `podman volume create` is called

### `Makefile`

Add targets:

```makefile
volumes:
	@podman volume ls --filter name=pi-agent-persist- --format '{{.Name}}'

reset:
	./run.sh --reset
```

### `README.md`

Update architecture table, security model, requirements section. Remove `fuse-overlayfs` dependency. Document persistence behavior, volume naming, automatic config sync, reset mechanism.

## Security Model

| Threat | Mitigation |
|--------|-----------|
| Agent reads other projects | Only current directory mounted as `/workspace` |
| Agent modifies host config | Mounted `:ro` at `/pi-source` — writes go to persistent volume only |
| Agent escapes to host filesystem | All existing hardening unchanged (`--cap-drop=ALL`, `--read-only`, `--security-opt=no-new-privileges`, user namespaces) |
| Persistent volume as attack vector | Volume is podman-managed, not a host bind mount. No host filesystem access. Intra-project persistence of malicious files is possible (acceptable for dev sandbox). |
| Volume ownership escalation | `:U` flag ensures correct ownership; entrypoint also chowns as defense-in-depth |

**New consideration**: A compromised container can persist malicious files in the volume that survive into the next run of the same project's sandbox. This is an intra-project concern (not a host escape) and is the inherent trade-off of persistence. The ephemeral prototypes don't have this surface.

## Trade-offs vs. Prototypes A/B

| Aspect | A (copy-to-tmp) | B (overlay-mount) | C (persistent volume) |
|--------|----------------|-------------------|----------------------|
| Lock files | ✅ writable | ✅ writable | ✅ writable |
| Host config protection | ✅ ephemeral copy | ✅ COW overlay | ✅ `:ro` mount + first-run copy |
| Sessions persistence | ❌ lost on exit | ❌ lost on exit | ✅ survive across runs |
| Installed tools persistence | ❌ lost on exit | ❌ lost on exit | ✅ survive in `/home/pi/.local` |
| Host dependency | None | `fuse-overlayfs` + `user_allow_other` | None |
| Host config drift | Fresh copy each run | Fresh overlay each run | Auto-synced on start (rsync, preserves user data) |
| Attack surface | Ephemeral only | Ephemeral only | Persistent intra-project |