# Persistent Per-Project Volume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ephemeral `/home/pi` tmpfs mount with a per-project persistent podman volume, enabling sessions, installed tools, and shell customizations to survive across container runs while maintaining isolation between projects.

**Architecture:** A podman-managed volume named `pi-agent-persist-<project>-<hash>` is mounted at `/home/pi` with the `:U` ownership flag. An entrypoint script runs as root, syncs host config from `/pi-source` (read-only mount of `~/.pi/agent`) into `/home/pi/.pi-agent-data/`, performs first-run setup (`.bashrc` copy, package manager config, `.bash_profile` creation), then drops privileges to the `pi` user via `su -l`. The `run.sh` script gains a `--reset` flag to destroy the volume and start fresh.

**Tech Stack:** Bash, Podman (rootless), Arch Linux container, Python (pytest), rsync

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `config/entrypoint.sh` | **Create** | Container entrypoint: config sync via rsync, first-run setup, privilege drop |
| `config/.bashrc` | **Modify** | Add PATH, PYTHONUSERBASE, NPM_CONFIG_PREFIX, PI_CODING_AGENT_DIR exports |
| `Containerfile` | **Modify** | Add rsync/shadow packages, copy entrypoint, set ENTRYPOINT, change USER to root |
| `run.sh` | **Modify** | Volume derivation/creation, `/pi-source:ro` mount, persistent volume mount, `--reset` flag |
| `tests/test_containerfile.py` | **Modify** | Assert rsync, shadow, ENTRYPOINT, entrypoint.sh COPY |
| `tests/test_config.py` | **Modify** | Assert PATH, PYTHONUSERBASE, NPM_CONFIG_PREFIX, PI_CODING_AGENT_DIR in .bashrc |
| `tests/test_run.py` | **Modify** | Assert `/pi-source:ro`, `/home/pi:U`, `volume create`, no tmpfs for /home/pi, no /pi-data/sessions, `--reset` |
| `tests/test_integration.py` | **Modify** | Update existing tests for new paths, add persistence/volume isolation/config sync tests |
| `tests/conftest.py` | **Modify** | Add volume cleanup fixture |
| `Makefile` | **Modify** | Add `volumes` and `reset` targets |
| `tests/test_makefile.py` | **Modify** | Assert new targets |
| `README.md` | **Modify** | Update architecture, security model, requirements, filesystem table |

---

## Task 1: Create config/entrypoint.sh

**Files:**
- Create: `config/entrypoint.sh`

- [ ] **Step 1: Create the entrypoint script**

```bash
cat > config/entrypoint.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# Container entrypoint for persistent per-project volume.
# Runs as root (USER root in Containerfile), drops to pi via su -l.

DATA_DIR=/home/pi/.pi-agent-data

# Sync host config into persistent volume on every start.
# Propagates new/modified files while preserving user-generated data.
# Excludes sessions/ and lock files to avoid overwriting runtime state.
rsync -au --exclude='sessions/' --exclude='*.lock' /pi-source/. "$DATA_DIR/"

# Ensure sessions directory exists
mkdir -p "$DATA_DIR/sessions"

# Copy .bashrc on first run only
if [ ! -f /home/pi/.bashrc ]; then
    cp /etc/pi/.bashrc /home/pi/.bashrc
fi

# Create .bash_profile that sources .bashrc on first run.
# Required for non-interactive login shells (su -l) to load PATH and env vars.
if [ ! -f /home/pi/.bash_profile ]; then
    printf 'if [ -f ~/.bashrc ]; then\n  . ~/.bashrc\nfi\n' > /home/pi/.bash_profile
fi

# Ensure pi user owns their home directory.
# The :U volume mount flag should handle this, but chown is defense-in-depth
# for the first run and any ownership drift.
chown -R pi:pi /home/pi

# Configure package managers for user-level installs on first run
if [ ! -d /home/pi/.local ]; then
    mkdir -p /home/pi/.local
    su -l pi -c 'npm config set prefix "$HOME/.local"'
fi

# Drop privileges and exec the user command
exec su -l pi -- "$@"
SCRIPT
chmod +x config/entrypoint.sh
```

- [ ] **Step 2: Verify the script is executable**

Run: `ls -la config/entrypoint.sh`
Expected: `-rwxr-xr-x` permissions

- [ ] **Step 3: Commit**

```bash
git add config/entrypoint.sh
git commit -m "feat: add container entrypoint for persistent volume setup"
```

---

## Task 2: Update Containerfile

**Files:**
- Modify: `Containerfile`
- Test: `tests/test_containerfile.py`

The Containerfile changes add the `rsync` and `shadow` packages (for config sync and `su`), copy the entrypoint script, set `ENTRYPOINT`, and change `USER` from `pi` to `root` so the entrypoint can perform privileged setup before dropping to `pi`.

- [ ] **Step 1: Write the failing test**

Add assertions to `tests/test_containerfile.py` for the new directives:

```python
def test_containerfile_has_rsync_package():
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "rsync" in content, "Missing rsync package for config sync"


def test_containerfile_has_shadow_package():
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "shadow" in content, "Missing shadow package for su command"


def test_containerfile_has_entrypoint():
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "entrypoint.sh" in content, "Missing entrypoint.sh reference"
    assert "ENTRYPOINT" in content, "Missing ENTRYPOINT directive"


def test_containerfile_has_user_root():
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "USER root" in content, "Missing USER root directive"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tau/Projects/pi-sandbox && .venv/bin/python -m pytest tests/test_containerfile.py -v`
Expected: FAIL — new assertions fail because the current Containerfile doesn't have rsync, shadow, ENTRYPOINT, or USER root.

- [ ] **Step 3: Update the Containerfile**

Replace the entire `Containerfile` with:

```dockerfile
FROM archlinux:latest

RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm nodejs npm git openssh bash fd ripgrep python uv gcc make ast-grep rsync shadow && \
    pacman -Scc --noconfirm

# Strip setuid/setgid bits — hardening the image
RUN find / \( -path /proc -o -path /sys \) -prune -o -perm /6000 -type f -exec chmod a-s {} +

RUN npm install -g @mariozechner/pi-coding-agent

RUN useradd -m -u 1000 -s /bin/bash pi

# Store .bashrc outside $HOME — it gets copied into the persistent volume at startup.
RUN mkdir -p /etc/pi
COPY config/.bashrc /etc/pi/.bashrc

# Copy and install entrypoint script.
# Runs as root to set up the persistent volume, then drops to pi via su.
COPY config/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh

ENV HOME=/home/pi
ENV TERM=xterm-256color
ENV COLORTERM=truecolor

USER root
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
```

Key changes from current Containerfile:
- Added `rsync` and `shadow` to `pacman -S`
- Added `COPY config/entrypoint.sh` and `chmod 755`
- Changed `USER pi` → `USER root`
- Changed `CMD ["sh", "-c", "cp /etc/pi/.bashrc $HOME/.bashrc && exec /bin/bash --login"]` → `ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]`
- Removed `ENV PI_CODING_AGENT_DIR=/pi-data` (now set in `.bashrc`)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tau/Projects/pi-sandbox && .venv/bin/python -m pytest tests/test_containerfile.py -v`
Expected: PASS — all assertions succeed.

- [ ] **Step 5: Commit**

```bash
git add Containerfile tests/test_containerfile.py
git commit -m "feat: wire entrypoint into Containerfile with persistent volume support"
```

---

## Task 3: Update config/.bashrc

**Files:**
- Modify: `config/.bashrc`
- Test: `tests/test_config.py`

The `.bashrc` needs PATH and environment variable exports so that tools installed into `/home/pi/.local/` are immediately available, and `PI_CODING_AGENT_DIR` points to the synced config directory inside the persistent volume.

- [ ] **Step 1: Write the failing test**

Add assertions to `tests/test_config.py`:

```python
def test_bashrc_sets_local_bin_in_path():
    content = (REPO_ROOT / "config" / ".bashrc").read_text()
    assert '$HOME/.local/bin' in content, "Missing $HOME/.local/bin in PATH"


def test_bashrc_sets_pythonuserbase():
    content = (REPO_ROOT / "config" / ".bashrc").read_text()
    assert 'PYTHONUSERBASE' in content, "Missing PYTHONUSERBASE export"


def test_bashrc_sets_npm_config_prefix():
    content = (REPO_ROOT / "config" / ".bashrc").read_text()
    assert 'NPM_CONFIG_PREFIX' in content, "Missing NPM_CONFIG_PREFIX export"


def test_bashrc_sets_pi_coding_agent_dir():
    content = (REPO_ROOT / "config" / ".bashrc").read_text()
    assert 'PI_CODING_AGENT_DIR' in content, "Missing PI_CODING_AGENT_DIR export"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tau/Projects/pi-sandbox && .venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — new assertions fail because `.bashrc` doesn't have the new exports.

- [ ] **Step 3: Update config/.bashrc**

Replace `config/.bashrc` with:

```bash
# Pi Agent Isolation Environment shell configuration

export PS1='[\u@pi-agent \W]\$ '
alias ls='ls --color=auto'

# Persistent volume paths — tools installed in the container survive across runs.
export PATH="$HOME/.local/bin:$PATH"
export PYTHONUSERBASE="$HOME/.local"
export NPM_CONFIG_PREFIX="$HOME/.local"

# Point pi-coding-agent at the synced config inside the persistent volume.
export PI_CODING_AGENT_DIR="$HOME/.pi-agent-data"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tau/Projects/pi-sandbox && .venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS — all assertions succeed.

- [ ] **Step 5: Commit**

```bash
git add config/.bashrc tests/test_config.py
git commit -m "feat: configure package manager paths and PI_CODING_AGENT_DIR in .bashrc"
```

---

## Task 4: Update run.sh

**Files:**
- Modify: `run.sh`
- Test: `tests/test_run.py`

This is the core change: replace the tmpfs mount for `/home/pi` with a persistent podman volume, rename `/pi-data` to `/pi-source`, remove the sessions bind mount, add volume creation, and add the `--reset` flag.

- [ ] **Step 1: Write the failing test**

Update `tests/test_run.py` — replace the entire file:

```python
import os
import pathlib
import subprocess
import tempfile

REPO_ROOT = pathlib.Path(__file__).parent.parent


def test_run_script_exists_and_executable():
    script = REPO_ROOT / "run.sh"
    assert script.exists()
    assert os.access(script, os.X_OK)


def test_run_script_generates_correct_podman_command():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        log_file = tmpdir / "podman.log"
        fake_config = tmpdir / "pi-config"
        fake_config.mkdir()

        fake_podman.write_text(
            f'#!/bin/bash\n'
            f'echo "$@" >> "{log_file}"\n'
            f'if [ "$1" = "image" ] && [ "$2" = "exists" ]; then\n'
            f'    exit 1\n'
            f'fi\n'
            f'exit 0\n'
        )
        fake_podman.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)

        # Create a fake ~/.env with test API keys
        (tmpdir / ".env").write_text("VLLM_API_KEY=test-vllm-key\nOPENROUTER_API_KEY=test-openrouter-key\n")

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "pi", "-p", "hello"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        log_lines = log_file.read_text().strip().splitlines()
        assert len(log_lines) >= 4, f"Expected at least 4 podman invocations, got: {log_lines}"

        # First call: podman volume create
        assert "volume create" in log_lines[0], f"Expected volume create, got: {log_lines[0]}"
        assert "pi-agent-persist-" in log_lines[0], f"Expected persistent volume name, got: {log_lines[0]}"

        # Second call: podman image exists
        assert "image exists" in log_lines[1], f"Expected image exists, got: {log_lines[1]}"

        # Third call: podman build
        assert "build" in log_lines[2], f"Expected build, got: {log_lines[2]}"

        # Fourth call: podman run — verify all required flags and mounts
        run_line = log_lines[3]
        assert "run" in run_line
        assert "--rm" in run_line
        assert "--userns=keep-id" in run_line
        assert "--cap-drop=ALL" in run_line
        assert "--security-opt=no-new-privileges" in run_line
        assert "--read-only" in run_line
        assert "--tmpfs" in run_line
        assert "/tmp" in run_line
        assert "--pids-limit" in run_line
        assert "--memory" in run_line
        assert "--cpus" in run_line
        assert "--name" in run_line
        assert "pi-agent-" in run_line

        # New persistent volume mount
        assert "/home/pi:U" in run_line, "Missing persistent volume mount /home/pi:U"

        # Renamed config mount (was /pi-data:ro, now /pi-source:ro)
        assert "/pi-source:ro" in run_line, "Missing read-only config mount /pi-source:ro"

        # Project workspace mount
        assert "/workspace" in run_line

        # Environment variable forwarding
        assert "VLLM_API_KEY" in run_line
        assert "OPENROUTER_API_KEY" in run_line

        # Image name and command
        assert "pi-agent-isolated" in run_line
        assert "pi -p hello" in run_line

        # Removed mounts that should NOT appear
        assert "/pi-data:ro" not in run_line, "Old /pi-data mount should be replaced by /pi-source"
        assert "--mount type=tmpfs" not in run_line, "tmpfs mount for /home/pi should be replaced by persistent volume"
        assert "/pi-data/sessions" not in run_line, "Separate sessions mount should not exist"


def test_run_script_reset_removes_volume():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        log_file = tmpdir / "podman.log"
        fake_config = tmpdir / "pi-config"
        fake_config.mkdir()

        fake_podman.write_text(
            f'#!/bin/bash\n'
            f'echo "$@" >> "{log_file}"\n'
            f'exit 0\n'
        )
        fake_podman.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "--reset"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        log_content = log_file.read_text()
        assert "volume rm" in log_content, f"Expected volume rm, got: {log_content}"
        assert "pi-agent-persist-" in log_content, f"Expected persistent volume name, got: {log_content}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tau/Projects/pi-sandbox && .venv/bin/python -m pytest tests/test_run.py -v`
Expected: FAIL — assertions for `/pi-source:ro`, `/home/pi:U`, `volume create`, and `--reset` fail because the current `run.sh` doesn't have these features.

- [ ] **Step 3: Update run.sh**

Replace `run.sh` with:

```bash
#!/bin/bash
set -euo pipefail

IMAGE_NAME="${PI_AGENT_IMAGE:-pi-agent-isolated}"
CONTAINER_NAME="pi-agent-$(basename "$PWD")-${RANDOM}"
GLOBAL_CONFIG="${PI_AGENT_CONFIG:-${HOME}/.pi/agent}"
ENV_FILE="${PI_AGENT_ENV_FILE:-${HOME}/.env}"

# Derive persistent volume name from project path.
# The basename makes "podman volume ls" output meaningful.
# The 8-char hash suffix guarantees uniqueness.
PROJECT_PATH="$(realpath "$(pwd)")"
PROJECT_NAME="$(basename "$PROJECT_PATH")"
PERSIST_VOLUME="pi-agent-persist-${PROJECT_NAME}-$(echo "$PROJECT_PATH" | sha256sum | cut -c1-8)"

# Handle --reset flag: remove the persistent volume and exit.
if [ "${1:-}" = "--reset" ]; then
    podman volume rm "$PERSIST_VOLUME" 2>/dev/null || true
    echo "Volume $PERSIST_VOLUME removed."
    exit 0
fi

# Ensure mount source exists
mkdir -p "${GLOBAL_CONFIG}"

# Create persistent volume (idempotent — no-op if exists).
# Stores sessions, installed tools, and shell config across runs.
podman volume create "$PERSIST_VOLUME" >/dev/null

# Build image if it doesn't exist
if ! podman image exists "$IMAGE_NAME"; then
    echo "Building image ${IMAGE_NAME}..."
    podman build -t "$IMAGE_NAME" "$(dirname "$0")"
fi

# Forward all variables defined in the env file
ENV_ARGS=()
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a

    while IFS= read -r key; do
        [[ -z "$key" ]] && continue
        ENV_ARGS+=(-e "$key")
    done < <(awk '
        /^[[:space:]]*#/ { next }
        /^[[:space:]]*$/ { next }
        {
            gsub(/^[[:space:]]*export[[:space:]]+/, "")
            match($0, /^[[:space:]]*[^=[:space:]]+/)
            if (RLENGTH > 0) {
                key = substr($0, RSTART, RLENGTH)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
                print key
            }
        }
    ' "$ENV_FILE")
fi

# Allocate TTY only when stdin is a terminal
TTY_FLAG=""
[ -t 0 ] && TTY_FLAG="-t"

exec podman run -i ${TTY_FLAG} --rm \
    --name "$CONTAINER_NAME" \
    --userns=keep-id \
    --cap-drop=ALL \
    --security-opt=no-new-privileges \
    --read-only \
    --tmpfs /tmp \
    --pids-limit 1024 \
    --memory 8g \
    --cpus 4 \
    -v "$(pwd):/workspace" \
    -v "${GLOBAL_CONFIG}:/pi-source:ro" \
    -v "${PERSIST_VOLUME}:/home/pi:U" \
    "${ENV_ARGS[@]}" \
    "$IMAGE_NAME" \
    "$@"
```

Key changes from current `run.sh`:
- Added `PERSIST_VOLUME` derivation from project path (basename + sha256 hash suffix)
- Added `--reset` flag handler (removes volume and exits)
- Added `podman volume create "$PERSIST_VOLUME"` before container start
- Changed `-v "${GLOBAL_CONFIG}:/pi-data:ro"` → `-v "${GLOBAL_CONFIG}:/pi-source:ro"`
- Removed `--mount type=tmpfs,destination=/home/pi,chown=true`
- Removed `-v "${GLOBAL_CONFIG}/sessions:/pi-data/sessions:rw"`
- Added `-v "${PERSIST_VOLUME}:/home/pi:U"`
- Removed `mkdir -p "${GLOBAL_CONFIG}/sessions"`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tau/Projects/pi-sandbox && .venv/bin/python -m pytest tests/test_run.py -v`
Expected: PASS — all assertions succeed.

- [ ] **Step 5: Commit**

```bash
git add run.sh tests/test_run.py
git commit -m "feat: persistent per-project podman volume with --reset flag"
```

---

## Task 5: Update existing integration tests

**Files:**
- Modify: `tests/test_integration.py`
- Modify: `tests/conftest.py`

The existing integration tests reference `/pi-data` (the old mount point) and `/pi-data/sessions` (the old writable sessions path). These must be updated to `/pi-source` and `/home/pi/.pi-agent-data/sessions` respectively. The `conftest.py` needs a volume cleanup fixture.

- [ ] **Step 1: Add volume cleanup fixture to conftest.py**

Add a fixture to `tests/conftest.py` that removes any persistent volumes created during testing:

```python
"""Shared test infrastructure for pi-agent-isolation tests."""
import hashlib
import pathlib
import shutil
import subprocess
import pytest

TEST_IMAGE = "pi-agent-isolated-test"

skip_without_podman = pytest.mark.skipif(
    not shutil.which("podman"),
    reason="podman not found in PATH",
)


@pytest.fixture(scope="session")
def built_image():
    """Build the test image once per session; remove it on teardown."""
    if not shutil.which("podman"):
        pytest.skip("podman not found in PATH")
    result = subprocess.run(
        ["podman", "build", "-t", TEST_IMAGE, "."],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Image build failed:\n{result.stderr}"
    yield TEST_IMAGE
    subprocess.run(["podman", "rmi", TEST_IMAGE], capture_output=True)


@pytest.fixture
def volume_cleanup(tmp_path):
    """Remove the persistent volume created for a test project directory.

    Derives the volume name from the temporary project path, matching
    the logic in run.sh. Yields the tmp_path, then cleans up on exit.
    """
    yield tmp_path
    # Derive volume name matching run.sh logic
    project_path = str(tmp_path.resolve())
    project_name = tmp_path.name
    hash_suffix = hashlib.sha256(project_path.encode()).hexdigest()[:8]
    volume_name = f"pi-agent-persist-{project_name}-{hash_suffix}"
    subprocess.run(
        ["podman", "volume", "rm", volume_name],
        capture_output=True,
    )
```

- [ ] **Step 2: Update test_integration.py existing tests**

Replace `tests/test_integration.py` with updated tests that use `/pi-source` instead of `/pi-data` and test against the new persistent volume paths:

```python
import os
import pathlib
import subprocess
import tempfile

REPO_ROOT = pathlib.Path(__file__).parent.parent
TEST_IMAGE = "pi-agent-isolated-test"


# --- Image build ---

def test_image_builds_successfully(built_image):
    """Fixture already asserts build success; this test confirms the image exists."""
    result = subprocess.run(
        ["podman", "image", "exists", built_image],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "Image does not exist after build"


# --- Container filesystem layout ---

def test_container_has_workspace(built_image):
    result = subprocess.run(
        ["podman", "run", "--rm", built_image, "test", "-d", "/workspace"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "/workspace directory missing"


def test_container_has_pi_source_mount(built_image):
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [
                "podman", "run", "--rm",
                "-v", f"{tmpdir}:/pi-source:ro",
                built_image,
                "test", "-d", "/pi-source",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, "/pi-source directory missing or unreadable"


def test_container_user_is_pi(built_image):
    result = subprocess.run(
        ["podman", "run", "--rm", built_image, "id", "-un"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "pi"


def test_pi_coding_agent_is_installed(built_image):
    result = subprocess.run(
        ["podman", "run", "--rm", built_image, "bash", "-c", "command -v pi"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "pi" in result.stdout


def test_container_has_rsync(built_image):
    result = subprocess.run(
        ["podman", "run", "--rm", built_image, "command", "-v", "rsync"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "rsync not found in container"


def test_container_has_su(built_image):
    result = subprocess.run(
        ["podman", "run", "--rm", built_image, "command", "-v", "su"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "su not found in container"


# --- End-to-end workflow via run.sh ---


def _run_env(tmpdir):
    """Build the environment dict for run.sh invocations."""
    env = os.environ.copy()
    env["PI_AGENT_IMAGE"] = TEST_IMAGE
    env["PI_AGENT_CONFIG"] = str(pathlib.Path(tmpdir) / "pi-config")

    # Create a fake env file and point run.sh to it via PI_AGENT_ENV_FILE
    env_file = pathlib.Path(tmpdir) / ".env"
    env_file.write_text("VLLM_API_KEY=\nOPENROUTER_API_KEY=\n")
    env["PI_AGENT_ENV_FILE"] = str(env_file)
    return env


def test_run_script_mounts_current_directory(built_image):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        marker = tmpdir / "PROJECT_MARKER"
        marker.write_text("found")

        env = _run_env(tmpdir)

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "cat", "/workspace/PROJECT_MARKER"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmpdir),
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "found"


def test_global_config_is_readonly_in_container(built_image):
    """Host config mounted at /pi-source must be read-only inside the container.
    Writes to /home/pi/.pi-agent-data should succeed (persistent volume)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        config_dir = tmpdir / "pi-config"
        config_dir.mkdir()
        (config_dir / "settings.json").write_text("{}")

        env = _run_env(tmpdir)

        result = subprocess.run(
            [
                str(REPO_ROOT / "run.sh"),
                "bash", "-c",
                "touch /pi-source/should_fail 2>/dev/null; echo $?",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        # touch on a read-only mount should fail with exit code 1
        assert result.stdout.strip() == "1"


def test_sessions_dir_is_writable_in_container(built_image):
    """Sessions directory at /home/pi/.pi-agent-data/sessions must be writable."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        config_dir = tmpdir / "pi-config"
        config_dir.mkdir()
        (config_dir / "sessions").mkdir()

        env = _run_env(tmpdir)

        result = subprocess.run(
            [
                str(REPO_ROOT / "run.sh"),
                "bash", "-c",
                "touch /home/pi/.pi-agent-data/sessions/test_write && echo ok",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        assert "ok" in result.stdout
```

- [ ] **Step 3: Run tests to verify they pass (unit-level)**

Run: `cd /home/tau/Projects/pi-sandbox && .venv/bin/python -m pytest tests/test_integration.py -v -k "not persistence and not isolation and not config_sync" --ignore-glob="*skip*"`
Expected: PASS — all existing tests updated for new paths.

Note: The integration tests that use `built_image` require podman and a successful image build. If podman is not available, these tests are skipped. If the image hasn't been rebuilt with the new Containerfile, the container-level tests will fail. This is expected until the full pipeline is complete.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py tests/conftest.py
git commit -m "test: update integration tests for persistent volume paths"
```

---

## Task 6: Add persistence, volume isolation, and config sync integration tests

**Files:**
- Modify: `tests/test_integration.py`

These new tests verify the key behaviors unique to the persistent volume: data survives across container runs, different projects get isolated volumes, and host config changes sync into the volume without overwriting user data.

- [ ] **Step 1: Add new integration tests**

Append to `tests/test_integration.py`:

```python
# --- Persistent volume tests ---


def test_persistence_across_runs(built_image):
    """Files written to /home/pi/.local/ should survive across container runs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        config_dir = tmpdir / "pi-config"
        config_dir.mkdir()

        env = _run_env(tmpdir)

        try:
            # First run: write a marker file
            result = subprocess.run(
                [
                    str(REPO_ROOT / "run.sh"),
                    "bash", "-c",
                    "echo persisted > /home/pi/.local/marker.txt",
                ],
                capture_output=True, text=True, env=env, cwd=str(tmpdir),
            )
            assert result.returncode == 0, result.stderr

            # Second run: verify marker file still exists
            result = subprocess.run(
                [
                    str(REPO_ROOT / "run.sh"),
                    "cat", "/home/pi/.local/marker.txt",
                ],
                capture_output=True, text=True, env=env, cwd=str(tmpdir),
            )
            assert result.returncode == 0, result.stderr
            assert result.stdout.strip() == "persisted"
        finally:
            # Cleanup: remove the persistent volume
            subprocess.run(
                [str(REPO_ROOT / "run.sh"), "--reset"],
                capture_output=True, text=True, env=env, cwd=str(tmpdir),
            )


def test_volume_isolation(built_image):
    """Project A's persistent volume should not contain project B's data."""
    with tempfile.TemporaryDirectory() as project_a, \
         tempfile.TemporaryDirectory() as project_b:
        project_a = pathlib.Path(project_a)
        project_b = pathlib.Path(project_b)

        config_dir_a = project_a / "pi-config"
        config_dir_a.mkdir()
        config_dir_b = project_b / "pi-config"
        config_dir_b.mkdir()

        env_a = _run_env(project_a)
        env_b = _run_env(project_b)

        try:
            # Write marker in project A's volume
            result = subprocess.run(
                [
                    str(REPO_ROOT / "run.sh"),
                    "bash", "-c",
                    "echo project-a-secret > /home/pi/.local/secret.txt",
                ],
                capture_output=True, text=True, env=env_a, cwd=str(project_a),
            )
            assert result.returncode == 0, result.stderr

            # Verify project B cannot see project A's data
            result = subprocess.run(
                [
                    str(REPO_ROOT / "run.sh"),
                    "bash", "-c",
                    "cat /home/pi/.local/secret.txt 2>/dev/null; echo exit:$?",
                ],
                capture_output=True, text=True, env=env_b, cwd=str(project_b),
            )
            assert result.returncode == 0, result.stderr
            # Either the file doesn't exist (exit:1) or it's empty/different content
            output = result.stdout.strip()
            if "exit:0" in output:
                content = output.rsplit("exit:0", 1)[0].strip()
                assert "project-a-secret" not in content, (
                    "Project B's volume contains project A's data — volumes are not isolated"
                )
        finally:
            # Cleanup both volumes
            subprocess.run(
                [str(REPO_ROOT / "run.sh"), "--reset"],
                capture_output=True, text=True, env=env_a, cwd=str(project_a),
            )
            subprocess.run(
                [str(REPO_ROOT / "run.sh"), "--reset"],
                capture_output=True, text=True, env=env_b, cwd=str(project_b),
            )


def test_config_sync(built_image):
    """Host config changes should sync into the persistent volume on next run,
    while preserving sessions and other user data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        config_dir = tmpdir / "pi-config"
        config_dir.mkdir()
        (config_dir / "skills").mkdir()
        (config_dir / "skills" / "old-skill.md").write_text("# Old Skill")

        env = _run_env(tmpdir)

        try:
            # First run: create a session file in the volume
            result = subprocess.run(
                [
                    str(REPO_ROOT / "run.sh"),
                    "bash", "-c",
                    "echo session-data > /home/pi/.pi-agent-data/sessions/test-session.json && "
                    "echo ok",
                ],
                capture_output=True, text=True, env=env, cwd=str(tmpdir),
            )
            assert result.returncode == 0, result.stderr
            assert "ok" in result.stdout

            # Modify config on host: add a new skill file
            (config_dir / "skills" / "new-skill.md").write_text("# New Skill")

            # Second run: verify new skill is synced AND session is preserved
            result = subprocess.run(
                [
                    str(REPO_ROOT / "run.sh"),
                    "bash", "-c",
                    "cat /home/pi/.pi-agent-data/skills/new-skill.md && "
                    "echo --- && "
                    "cat /home/pi/.pi-agent-data/sessions/test-session.json",
                ],
                capture_output=True, text=True, env=env, cwd=str(tmpdir),
            )
            assert result.returncode == 0, result.stderr
            assert "New Skill" in result.stdout, "Host config changes not synced into volume"
            assert "session-data" in result.stdout, "Session data not preserved across runs"
        finally:
            # Cleanup
            subprocess.run(
                [str(REPO_ROOT / "run.sh"), "--reset"],
                capture_output=True, text=True, env=env, cwd=str(tmpdir),
            )
```

- [ ] **Step 2: Run the new tests**

Run: `cd /home/tau/Projects/pi-sandbox && .venv/bin/python -m pytest tests/test_integration.py -v -k "persistence or isolation or config_sync" --ignore-glob="*skip*"`

Note: These tests require podman and a built image. They will be skipped if podman is not available. They will fail if the image hasn't been rebuilt with the new Containerfile. This is expected during incremental development — all tests should pass once the full pipeline is complete.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add persistence, volume isolation, and config sync integration tests"
```

---

## Task 7: Update Makefile and test_makefile.py

**Files:**
- Modify: `Makefile`
- Modify: `tests/test_makefile.py`

Add `volumes` and `reset` makefile targets, and add test assertions for them.

- [ ] **Step 1: Write the failing test**

Add assertions to `tests/test_makefile.py`:

```python
def test_makefile_has_volumes_target():
    content = (REPO_ROOT / "Makefile").read_text()
    assert "volumes:" in content, "Missing volumes target"


def test_makefile_has_reset_target():
    content = (REPO_ROOT / "Makefile").read_text()
    assert "reset:" in content, "Missing reset target"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tau/Projects/pi-sandbox && .venv/bin/python -m pytest tests/test_makefile.py -v -k "volumes or reset"`
Expected: FAIL — new assertions fail because the Makefile doesn't have these targets.

- [ ] **Step 3: Update Makefile**

Replace `Makefile` with:

```makefile
IMAGE_NAME := pi-agent-isolated

.PHONY: build shell pi clean volumes reset

build:
	podman build -t $(IMAGE_NAME) .

shell:
	./run.sh

pi:
	./run.sh pi

clean:
	podman rmi $(IMAGE_NAME) || true

volumes:
	@podman volume ls --filter name=pi-agent-persist- --format '{{.Name}}'

reset:
	./run.sh --reset
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tau/Projects/pi-sandbox && .venv/bin/python -m pytest tests/test_makefile.py -v`
Expected: PASS — all assertions succeed.

- [ ] **Step 5: Commit**

```bash
git add Makefile tests/test_makefile.py
git commit -m "feat: add volumes and reset makefile targets"
```

---

## Task 8: Update README.md

**Files:**
- Modify: `README.md`

Update the architecture diagram, filesystem table, security model, and requirements to reflect the persistent volume design.

- [ ] **Step 1: Update README.md**

Replace the entire `README.md` with updated content reflecting persistent volumes:

```markdown
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
# From any project directory
../pi-sandbox/run.sh                    # interactive shell
../pi-sandbox/run.sh pi -p "Review code" # run pi directly
../pi-sandbox/run.sh npm test           # run any command

# Reset persistent state (destroys sessions, installed tools, etc.)
../pi-sandbox/run.sh --reset
```

Or use the Makefile targets:

```bash
make shell    # interactive shell in the container
make pi       # run pi in the container
make build    # build the container image
make clean    # remove the image
make volumes  # list all persistent volumes
make reset    # reset persistent state for current project
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

| Component             | Description                                                        |
| --------------------- | ------------------------------------------------------------------ |
| `Containerfile`       | Arch Linux image with Node.js, git, pi, rsync, and entrypoint      |
| `config/entrypoint.sh`| Syncs config, sets up volume, drops privileges to pi user          |
| `config/.bashrc`      | Shell prompt, aliases, and persistent PATH configuration          |
| `run.sh`              | Launch script — builds image, creates volume, runs container      |
| `Makefile`            | Convenience targets (`build`, `shell`, `pi`, `clean`, `reset`)    |
| `tests/`              | Pytest suite covering build, filesystem, persistence, and integration |

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

| Path                          | Source                     | Permissions |
| ----------------------------- | -------------------------- | ----------- |
| `/workspace`                  | Current directory          | Read-write  |
| `/pi-source`                  | `~/.pi/agent/`            | Read-only   |
| `/home/pi`                    | Persistent podman volume   | Read-write  |
| `/home/pi/.pi-agent-data/`    | Synced from `/pi-source/` | Read-write  |
| `/home/pi/.pi-agent-data/sessions/` | Session history    | Read-write  |
| `/home/pi/.local/`            | User-level package installs | Read-write |

### Config Sync

On every container start, the entrypoint syncs host config into the persistent volume:

| Synced from host               | Preserved in volume           |
| ------------------------------ | ----------------------------- |
| New skills in `~/.pi/agent/skills/` | Sessions in `sessions/`  |
| Updated `AGENTS.md`            | Lock files (`*.lock`)         |
| New/changed settings files     | Any container-created files   |

Files deleted from the host are **not** removed from the volume (to avoid accidentally deleting user data). Use `./run.sh --reset` for a clean slate.

## Security Model

| Threat                            | Mitigation                                                |
| --------------------------------- | --------------------------------------------------------- |
| Agent reads other projects        | Only current directory mounted as `/workspace`           |
| Agent modifies host config        | Mounted `:ro` at `/pi-source` — writes go to volume only |
| Agent escapes to host filesystem  | All existing hardening unchanged (`--cap-drop=ALL`, `--read-only`, `--security-opt=no-new-privileges`, user namespaces) |
| Persistent volume as attack vector | Volume is podman-managed, not a host bind mount. No host filesystem access. Intra-project persistence of malicious files is possible but contained. |
| Volume ownership escalation       | `:U` flag ensures correct ownership; entrypoint also chowns as defense-in-depth |

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

- [SPEC.md](SPEC.md) — Full specification with architecture diagrams, security analysis, and design rationale
- [Persistent Volume Design](docs/specs/2026-05-05-persistent-volume-design.md) — Design doc for the persistent volume feature
- [Pi Coding Agent](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent)
- [Podman Rootless Tutorial](https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md)
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README for persistent volume architecture"
```

---

## Task 9: Update security tests

**Files:**
- Modify: `tests/test_security.py`

The security tests reference `/pi-data` in their container invocations (via `run.sh`). Since `run.sh` now mounts at `/pi-source` instead of `/pi-data`, any tests that explicitly reference `/pi-data` inside the container need updating. Additionally, the `_run_env` helper in this file needs no changes since it only sets `PI_AGENT_CONFIG` and `PI_AGENT_ENV_FILE`.

- [ ] **Step 1: Review security tests for /pi-data references**

Review `tests/test_security.py` for any references to `/pi-data` that should now be `/pi-source`.

After review, the existing security tests don't directly reference `/pi-data` or `/pi-source` — they test container security properties (read-only rootfs, dropped capabilities, etc.) through `run.sh` invocations and don't inspect mount paths directly. The `_run_env` helper only sets environment variables, not container paths. No changes are needed.

- [ ] **Step 2: Run security tests to verify they still pass**

Run: `cd /home/tau/Projects/pi-sandbox && .venv/bin/python -m pytest tests/test_security.py -v`
Expected: PASS — security tests should pass without modification since they test container hardening properties, not mount paths.

Note: Security tests require podman and a rebuilt image. They may fail if the image hasn't been rebuilt with the new Containerfile. This is expected during incremental development.

---

## Task 10: Full integration smoke test

**Files:** None (verification only)

After all implementation and test changes are complete, rebuild the image and run the full test suite to verify everything works together.

- [ ] **Step 1: Rebuild the container image**

Run: `cd /home/tau/Projects/pi-sandbox && podman build -t pi-agent-isolated .`
Expected: Build succeeds with no errors.

- [ ] **Step 2: Run the full test suite**

Run: `cd /home/tau/Projects/pi-sandbox && .venv/bin/python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 3: Run a manual smoke test**

```bash
cd /home/tau/Projects/pi-sandbox
./run.sh echo "Container started successfully"
```

Expected: Output "Container started successfully".

- [ ] **Step 4: Test persistence manually**

```bash
# Write a marker file
./run.sh bash -c "echo test-persist > /home/pi/.local/marker.txt"

# Verify it persists
./run.sh cat /home/pi/.local/marker.txt
# Expected output: test-persist

# Clean up
./run.sh --reset
```

- [ ] **Step 5: Test --reset**

```bash
./run.sh --reset
# Expected output: Volume pi-agent-persist-<project>-<hash> removed.
```

- [ ] **Step 6: Final commit if any README adjustments are needed**

```bash
git add -A
git commit -m "chore: final adjustments after smoke test"
```

---

## Spec Coverage Check

| Spec Section | Task | Status |
|-------------|------|--------|
| D1: Persistent volume replaces fuse-overlayfs | Task 4 (run.sh removes tmpfs mount) | ✅ |
| D2: Volume mounted at /home/pi | Task 4 (run.sh adds `/home/pi:U` mount) | ✅ |
| D3: Volume name derived from project path | Task 4 (run.sh derives `PERSIST_VOLUME`) | ✅ |
| D4: Config sync on every start (not unconditional overwrite) | Task 1 (entrypoint.sh rsync with `-au --exclude`) | ✅ |
| D5: Package manager paths configured | Task 3 (.bashrc) + Task 1 (entrypoint first-run npm config) | ✅ |
| D6: Volume ownership via :U flag | Task 4 (run.sh mount flag) + Task 1 (entrypoint chown defense-in-depth) | ✅ |
| D7: Reset mechanism | Task 4 (run.sh `--reset` flag) + Task 7 (Makefile `reset` target) | ✅ |
| D8: Config sync merges host changes | Task 1 (entrypoint rsync) + Task 6 (test_config_sync) | ✅ |
| run.sh changes | Task 4 | ✅ |
| config/entrypoint.sh (new) | Task 1 | ✅ |
| Containerfile changes | Task 2 | ✅ |
| config/.bashrc changes | Task 3 | ✅ |
| tests/test_integration.py updates | Task 5 + Task 6 | ✅ |
| tests/test_run.py updates | Task 4 | ✅ |
| Makefile changes | Task 7 | ✅ |
| README.md changes | Task 8 | ✅ |