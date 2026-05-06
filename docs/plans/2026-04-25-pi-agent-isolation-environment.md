# Pi Agent Isolation Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a rootless Podman-based isolation environment for the pi coding agent, with one container per project, read-only global config, and read-write project workspace.

**Architecture:** A single Containerfile defines an Arch Linux image with Node.js and pi-coding-agent pre-installed. A `run.sh` script builds the image on demand and launches a rootless container with strictly scoped bind mounts. A Makefile provides common entrypoints. All validation is done via pytest tests before integration.

**Tech Stack:** Rootless Podman, Arch Linux (container), Bash, Python/pytest (testing)

---

## File Structure

| File                          | Responsibility                                                                                                                                                                                              |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Containerfile`               | Defines the `pi-agent-isolated` image: Arch Linux base, Node.js/npm/git/openssh/bash, global pi-coding-agent install, `pi` user, `/workspace` workdir                                                       |
| `config/.bashrc`              | Shell initialization for the container user (`pi`); sets prompt and basic aliases                                                                                                                           |
| `run.sh`                      | Launch script: ensures image and mount sources exist, then `podman run` with `--userns=keep-id`, project bind mount, read-only global config mount with read-write sessions overlay, and API key forwarding |
| `Makefile`                    | Common targets: `build`, `shell`, `pi`, `clean`                                                                                                                                                             |
| `tests/conftest.py`           | Shared fixtures: Podman availability check, session-scoped image build with dedicated test tag                                                                                                              |
| `tests/test_containerfile.py` | Validates Containerfile structure and required contents                                                                                                                                                     |
| `tests/test_config.py`        | Validates `config/.bashrc` exists and contains expected configuration                                                                                                                                       |
| `tests/test_run.py`           | Uses a mock `podman` binary to verify `run.sh` constructs the correct command-line flags                                                                                                                    |
| `tests/test_makefile.py`      | Validates Makefile targets exist and are syntactically valid                                                                                                                                                |
| `tests/test_integration.py`   | Verifies container filesystem layout and end-to-end workflow; uses dedicated test image tag and temp directories to avoid mutating host state                                                               |

---

### Task 1: Containerfile

**Files:**

- Create: `Containerfile`
- Test: `tests/test_containerfile.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_containerfile.py`:

```python
import pathlib

REPO_ROOT = pathlib.Path(__file__).parent.parent

def test_containerfile_exists():
    assert (REPO_ROOT / "Containerfile").exists()

def test_containerfile_has_required_directives():
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "FROM archlinux" in content
    assert "nodejs" in content
    assert "npm" in content
    assert "git" in content
    assert "openssh" in content
    assert "bash" in content
    assert "@mariozechner/pi-coding-agent" in content
    assert "useradd" in content
    assert "USER pi" in content
    assert "WORKDIR /workspace" in content
    assert "config/.bashrc" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_containerfile.py -v`

Expected: FAIL with `AssertionError` on `test_containerfile_exists`

- [ ] **Step 3: Write minimal implementation**

Create `Containerfile`:

```dockerfile
FROM archlinux:latest

RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm nodejs npm git openssh bash && \
    pacman -Scc --noconfirm

RUN npm install -g @mariozechner/pi-coding-agent

RUN useradd -m -u 1000 -s /bin/bash pi

COPY config/.bashrc /home/pi/.bashrc
RUN chown pi:pi /home/pi/.bashrc

ENV PI_CODING_AGENT_DIR=/pi-data
ENV HOME=/home/pi
ENV TERM=xterm-256color

USER pi
WORKDIR /workspace

CMD ["/bin/bash", "--login"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_containerfile.py -v`

Expected: PASS (4/4 assertions pass)

- [ ] **Step 5: Commit**

```bash
git add tests/test_containerfile.py Containerfile
git commit -m "feat: add Containerfile with Arch Linux base and pi-coding-agent"
```

---

### Task 2: Container Shell Configuration

**Files:**

- Create: `config/.bashrc`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
import pathlib

REPO_ROOT = pathlib.Path(__file__).parent.parent

def test_bashrc_exists():
    assert (REPO_ROOT / "config" / ".bashrc").exists()

def test_bashrc_sets_prompt():
    content = (REPO_ROOT / "config" / ".bashrc").read_text()
    assert "PS1" in content

def test_bashrc_enables_color_ls():
    content = (REPO_ROOT / "config" / ".bashrc").read_text()
    assert "ls --color=auto" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`

Expected: FAIL with `AssertionError` on `test_bashrc_exists`

- [ ] **Step 3: Write minimal implementation**

Create `config/.bashrc`:

```bash
# Pi Agent Isolation Environment shell configuration

export PS1='[\u@pi-agent \W]\$ '
alias ls='ls --color=auto'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`

Expected: PASS (3/3 tests pass)

- [ ] **Step 5: Commit**

```bash
git add tests/test_config.py config/.bashrc
git commit -m "feat: add container .bashrc with prompt and ls alias"
```

---

### Task 3: Launch Script

**Files:**

- Create: `run.sh`
- Test: `tests/test_run.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_run.py`:

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
        env["ANTHROPIC_API_KEY"] = "test-anthropic-key"
        env["OPENAI_API_KEY"] = "test-openai-key"
        env["PI_AGENT_CONFIG"] = str(fake_config)

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "pi", "-p", "hello"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        log_lines = log_file.read_text().strip().splitlines()
        assert len(log_lines) >= 3, f"Expected at least 3 podman invocations, got: {log_lines}"

        # First call: podman image exists
        assert "image exists pi-agent-isolated" in log_lines[0]

        # Second call: podman build
        assert "build -t pi-agent-isolated" in log_lines[1]

        # Third call: podman run — verify all required flags and mounts
        run_line = log_lines[2]
        assert "run" in run_line
        assert "--rm" in run_line
        assert "--userns=keep-id" in run_line
        assert "--name" in run_line
        assert "pi-agent-" in run_line
        assert "/workspace" in run_line
        assert "/pi-data:ro" in run_line
        assert "/pi-data/sessions" in run_line
        assert "ANTHROPIC_API_KEY" in run_line
        assert "OPENAI_API_KEY" in run_line
        assert "pi-agent-isolated" in run_line
        assert "pi -p hello" in run_line
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_run.py -v`

Expected: FAIL with `AssertionError` on `test_run_script_exists_and_executable` (file missing or not executable)

- [ ] **Step 3: Write minimal implementation**

Create `run.sh`:

```bash
#!/bin/bash
set -euo pipefail

IMAGE_NAME="${PI_AGENT_IMAGE:-pi-agent-isolated}"
CONTAINER_NAME="pi-agent-$(basename "$PWD")"
GLOBAL_CONFIG="${PI_AGENT_CONFIG:-${HOME}/.pi/agent}"

# Ensure mount sources exist
mkdir -p "${GLOBAL_CONFIG}"
mkdir -p "${GLOBAL_CONFIG}/sessions"

# Build image if it doesn't exist
if ! podman image exists "$IMAGE_NAME"; then
    echo "Building image ${IMAGE_NAME}..."
    podman build -t "$IMAGE_NAME" "$(dirname "$0")"
fi

# Allocate TTY only when stdin is a terminal
TTY_FLAG=""
[ -t 0 ] && TTY_FLAG="-t"

exec podman run -i ${TTY_FLAG} --rm \
    --name "$CONTAINER_NAME" \
    --userns=keep-id \
    -v "$(pwd):/workspace" \
    -v "${GLOBAL_CONFIG}:/pi-data:ro" \
    -v "${GLOBAL_CONFIG}/sessions:/pi-data/sessions:rw" \
    -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
    -e OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
    "$IMAGE_NAME" \
    "$@"
```

Make it executable:

```bash
chmod +x run.sh
```

#### Key Flags and Environment Explained

| Flag / Env Var                                    | Purpose                                                                                                                                                                          |
| ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--rm`                                            | Container is deleted when exited. No stale state.                                                                                                                                |
| `--userns=keep-id`                                | Maps container UID to host UID. Files written by the agent appear owned by you on the host.                                                                                      |
| `-v $(pwd):/workspace`                            | The _entire_ project directory, read-write.                                                                                                                                      |
| `-v $GLOBAL_CONFIG:/pi-data:ro`                   | Global pi config, read-only. Agent cannot mutate shared skills or settings.                                                                                                      |
| `-v $GLOBAL_CONFIG/sessions:/pi-data/sessions:rw` | Sessions overlay: read-write mount that supersedes the read-only parent at this path. Session data (conversation history) is the only part of global config the agent can write. |
| `-e ANTHROPIC_API_KEY=...`                        | API keys injected from host environment. Never written to disk.                                                                                                                  |
| `-e OPENAI_API_KEY=...`                           | API keys injected from host environment. Never written to disk.                                                                                                                  |
| `PI_AGENT_IMAGE`                                  | Override the container image name (default: `pi-agent-isolated`). Used by tests to point at a dedicated test image.                                                              |
| `PI_AGENT_CONFIG`                                 | Override the host config directory (default: `~/.pi/agent`). Used by tests to avoid touching real config.                                                                        |
| Conditional `-t`                                  | TTY allocated only when stdin is a terminal. Allows `run.sh` to work in scripted/CI contexts.                                                                                    |

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_run.py -v`

Expected: PASS (2/2 tests pass)

- [ ] **Step 5: Commit**

```bash
git add tests/test_run.py run.sh
git commit -m "feat: add run.sh launch script with rootless podman and scoped mounts"
```

---

### Task 4: Makefile

**Files:**

- Create: `Makefile`
- Test: `tests/test_makefile.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_makefile.py`:

```python
import pathlib
import subprocess

REPO_ROOT = pathlib.Path(__file__).parent.parent

def test_makefile_exists():
    assert (REPO_ROOT / "Makefile").exists()

def test_makefile_has_required_targets():
    content = (REPO_ROOT / "Makefile").read_text()
    for target in ("build:", "shell:", "pi:", "clean:"):
        assert target in content, f"Missing target: {target}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_makefile.py -v`

Expected: FAIL with `AssertionError` on `test_makefile_exists`

- [ ] **Step 3: Write minimal implementation**

Create `Makefile`:

```makefile
IMAGE_NAME := pi-agent-isolated

.PHONY: build shell pi clean

build:
	podman build -t $(IMAGE_NAME) .

shell:
	./run.sh

pi:
	./run.sh pi

clean:
	podman rmi $(IMAGE_NAME) || true
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_makefile.py -v`

Expected: PASS (2/2 tests pass)

- [ ] **Step 5: Commit**

```bash
git add tests/test_makefile.py Makefile
git commit -m "feat: add Makefile with build, shell, pi, and clean targets"
```

---

### Task 5: Test Infrastructure and Image Build

**Files:**

- Create: `tests/conftest.py`
- Create: `tests/test_integration.py`
- Modify: none (uses Containerfile from Task 1)

> **Note:** Integration tests use the dedicated `pi-agent-isolated-test` image tag. They never build, overwrite, or remove the user's real `pi-agent-isolated` image.

- [ ] **Step 1: Write the failing test**

Create `tests/conftest.py`:

```python
"""Shared test infrastructure for pi-agent-isolation tests."""
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
```

Create `tests/test_integration.py`:

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration.py -v`

Expected: FAIL — `built_image` fixture cannot build image (Containerfile may not be ready, or podman unavailable)

- [ ] **Step 3: Build the image**

Run: `podman build -t pi-agent-isolated-test .`

Expected: Build completes successfully. This may take several minutes due to `npm install -g`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_integration.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_integration.py
git commit -m "test: add integration test infrastructure and image build test"
```

---

### Task 6: Verify Container Filesystem Layout

**Files:**

- Modify: `tests/test_integration.py`

> **Note:** These tests use a temporary directory instead of `~/.pi/agent` for mount sources, avoiding any dependency on host state.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_integration.py`:

```python


# --- Container filesystem layout ---


def test_container_has_workspace(built_image):
    result = subprocess.run(
        ["podman", "run", "--rm", built_image, "test", "-d", "/workspace"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "/workspace directory missing"


def test_container_has_pi_data_mount(built_image):
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [
                "podman", "run", "--rm",
                "-v", f"{tmpdir}:/pi-data:ro",
                built_image,
                "test", "-d", "/pi-data",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, "/pi-data directory missing or unreadable"


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
        ["podman", "run", "--rm", built_image, "which", "pi"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "/bin/pi" in result.stdout or "/usr/bin/pi" in result.stdout
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_integration.py -v`

If the image was built in Task 5, these should pass immediately. If any fail, fix the Containerfile as needed.

Expected: PASS if image is correctly built; otherwise FAIL with specific assertion.

- [ ] **Step 3: Fix any issues if tests fail**

Adjust Containerfile or config as needed and rebuild: `podman build -t pi-agent-isolated-test .`

- [ ] **Step 4: Run all tests to verify everything passes**

Run: `pytest tests/ -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: verify container filesystem layout and pi installation"
```

---

### Task 7: End-to-End Workflow Verification

**Files:**

- Modify: `tests/test_integration.py`

> **Note:** These tests invoke `run.sh` directly, verifying the complete script-to-container path. They use `PI_AGENT_IMAGE` and `PI_AGENT_CONFIG` env vars to point at the test image and a temporary config directory, avoiding any mutation of the user's real image or `~/.pi/agent`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_integration.py`:

```python


# --- End-to-end workflow via run.sh ---


def _run_env(tmpdir):
    """Build the environment dict for run.sh invocations."""
    env = os.environ.copy()
    env["PI_AGENT_IMAGE"] = TEST_IMAGE
    env["PI_AGENT_CONFIG"] = str(pathlib.Path(tmpdir) / "pi-config")
    env["ANTHROPIC_API_KEY"] = ""
    env["OPENAI_API_KEY"] = ""
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
                "touch /pi-data/should_fail 2>/dev/null; echo $?",
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
                "touch /pi-data/sessions/test_write && echo ok",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        assert "ok" in result.stdout
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_integration.py -v`

Expected: PASS (all integration tests)

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: verify workspace mount, read-only global config, and sessions writability via run.sh"
```

---

## Review Loop

After completing the plan document, dispatch the plan-document-reviewer subagent with:

- **Plan:** `docs/superpowers/plans/2026-04-25-pi-agent-isolation-environment.md`
- **Spec:** `SPEC.md`

Fix any issues found, then re-dispatch the reviewer. Loop up to 3 times before surfacing to human.
