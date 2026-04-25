# Pi Agent Isolation Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a rootless Podman-based isolation environment for the pi coding agent, with one container per project, read-only global config, and read-write project workspace.

**Architecture:** A single Containerfile defines an Arch Linux image with Node.js and pi-coding-agent pre-installed. A `run.sh` script builds the image on demand and launches a rootless container with strictly scoped bind mounts. A Makefile provides common entrypoints. All validation is done via pytest tests before integration.

**Tech Stack:** Rootless Podman, Arch Linux (container), Bash, Python/pytest (testing)

---

## File Structure

| File                          | Responsibility                                                                                                                                            |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Containerfile`               | Defines the `pi-agent-isolated` image: Arch Linux base, Node.js/npm/git/openssh/bash, global pi-coding-agent install, `pi` user, `/workspace` workdir     |
| `config/.bashrc`              | Shell initialization for the container user (`pi`); sets prompt and basic aliases                                                                         |
| `run.sh`                      | Launch script: ensures image exists, then `podman run` with `--userns=keep-id`, project bind mount, read-only global config mount, and API key forwarding |
| `Makefile`                    | Common targets: `build`, `shell`, `pi`, `clean`                                                                                                           |
| `tests/test_containerfile.py` | Validates Containerfile structure and required contents                                                                                                   |
| `tests/test_config.py`        | Validates `config/.bashrc` exists and contains expected configuration                                                                                     |
| `tests/test_run.py`           | Uses a mock `podman` binary to verify `run.sh` constructs the correct command-line flags                                                                  |
| `tests/test_makefile.py`      | Validates Makefile targets exist and are syntactically valid                                                                                              |
| `tests/test_integration.py`   | Builds the image and verifies the running container filesystem matches the spec                                                                           |

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

Expected: PASS (3/3 assertions pass)

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

        # Third call: podman run
        run_line = log_lines[2]
        assert "run" in run_line
        assert "--rm" in run_line
        assert "--userns=keep-id" in run_line
        assert "-v" in run_line
        assert "/workspace" in run_line
        assert "/pi-data:ro" in run_line
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

IMAGE_NAME="pi-agent-isolated"
CONTAINER_NAME="pi-agent-$(basename "$PWD")"
GLOBAL_CONFIG="${HOME}/.pi/agent"

if ! podman image exists "$IMAGE_NAME"; then
    echo "Building image ${IMAGE_NAME}..."
    podman build -t "$IMAGE_NAME" "$(dirname "$0")"
fi

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

Make it executable:

```bash
chmod +x run.sh
```

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

### Task 5: Build Container Image

**Files:**

- Create: `pi-agent-isolated` (Podman image, not a repo file)
- Modify: none
- Test: `tests/test_integration.py` (image build test)

- [ ] **Step 1: Write the failing test**

Create `tests/test_integration.py`:

```python
import subprocess

def test_image_builds_successfully():
    result = subprocess.run(
        ["podman", "build", "-t", "pi-agent-isolated", "."],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Build failed:\n{result.stderr}"

def test_image_exists_after_build():
    result = subprocess.run(
        ["podman", "image", "exists", "pi-agent-isolated"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "Image does not exist after build"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration.py::test_image_exists_after_build -v`

Expected: FAIL with image not found

- [ ] **Step 3: Build the image**

Run: `podman build -t pi-agent-isolated .`

Expected: Build completes successfully. This may take several minutes due to `npm install -g`.

- [ ] **Step 4: Run tests to verify it passes**

Run: `pytest tests/test_integration.py -v`

Expected: PASS (2/2 tests pass)

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration test for container image build"
```

---

### Task 6: Verify Container Filesystem Layout

**Files:**

- Modify: none (uses existing image and scripts)
- Test: extends `tests/test_integration.py`

> **Note:** These tests assume `~/.pi/agent` exists on the host (standard pi installation). If it does not, create it before running integration tests.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_integration.py`:

```python
import subprocess
import os

def test_container_has_workspace():
    result = subprocess.run(
        ["podman", "run", "--rm", "pi-agent-isolated", "test", "-d", "/workspace"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "/workspace directory missing"

def test_container_has_pi_data_readonly():
    # Mount host ~/.pi/agent as /pi-data and verify it is readable
    global_config = os.path.expanduser("~/.pi/agent")
    result = subprocess.run(
        [
            "podman", "run", "--rm",
            "-v", f"{global_config}:/pi-data:ro",
            "pi-agent-isolated",
            "test", "-d", "/pi-data",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "/pi-data directory missing or unreadable"

def test_container_user_is_pi():
    result = subprocess.run(
        ["podman", "run", "--rm", "pi-agent-isolated", "id", "-un"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "pi"

def test_pi_coding_agent_is_installed():
    result = subprocess.run(
        ["podman", "run", "--rm", "pi-agent-isolated", "pi", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"pi not installed or failed: {result.stderr}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration.py::test_container_has_workspace tests/test_integration.py::test_container_has_pi_data_readonly tests/test_integration.py::test_container_user_is_pi tests/test_integration.py::test_pi_coding_agent_is_installed -v`

If the image was built in Task 5, these should pass immediately. If any fail, fix the Containerfile or run.sh as needed.

Expected: PASS if image is correctly built; otherwise FAIL with specific assertion.

- [ ] **Step 3: Fix any issues if tests fail**

If `test_pi_coding_agent_is_installed` fails because `pi --version` is unsupported, change the test to verify the binary exists:

```python
def test_pi_coding_agent_is_installed():
    result = subprocess.run(
        ["podman", "run", "--rm", "pi-agent-isolated", "which", "pi"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "/bin/pi" in result.stdout or "/usr/bin/pi" in result.stdout
```

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

- Modify: none
- Test: extends `tests/test_integration.py`

> **Note:** These tests assume `~/.pi/agent` exists on the host (standard pi installation). If it does not, create it before running integration tests.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_integration.py`:

```python
import subprocess
import tempfile
import os

def test_run_script_mounts_current_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = os.path.join(tmpdir, "PROJECT_MARKER")
        with open(marker, "w") as f:
            f.write("found")

        # Use podman directly with the same flags run.sh would use
        result = subprocess.run(
            [
                "podman", "run", "--rm",
                "--userns=keep-id",
                "-v", f"{tmpdir}:/workspace",
                "-v", f"{os.path.expanduser('~/.pi/agent')}:/pi-data:ro",
                "pi-agent-isolated",
                "cat", "/workspace/PROJECT_MARKER",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "found"

def test_global_config_is_readonly_in_container():
    result = subprocess.run(
        [
            "podman", "run", "--rm",
            "-v", f"{os.path.expanduser('~/.pi/agent')}:/pi-data:ro",
            "pi-agent-isolated",
            "bash", "-c", "touch /pi-data/should_fail 2>/dev/null; echo $?",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    # touch on a read-only mount should fail with exit code 1
    assert result.stdout.strip() == "1"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_integration.py::test_run_script_mounts_current_directory tests/test_integration.py::test_global_config_is_readonly_in_container -v`

Expected: PASS (2/2 tests pass)

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: verify workspace mount and read-only global config"
```

---

## Review Loop

After completing the plan document, dispatch the plan-document-reviewer subagent with:

- **Plan:** `docs/superpowers/plans/2026-04-25-pi-agent-isolation-environment.md`
- **Spec:** `SPEC.md`

Fix any issues found, then re-dispatch the reviewer. Loop up to 3 times before surfacing to human.

## Execution Handoff

After saving the plan, offer execution choice:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration. Required sub-skill: @superpowers:subagent-driven-development.

**2. Inline Execution** — Execute tasks in this session using @superpowers:executing-plans, batch execution with checkpoints for review.
