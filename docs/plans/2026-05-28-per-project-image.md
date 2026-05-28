# Per-Project Sandbox Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable projects to declare system packages via `.pi-packages` with per-project isolated sandbox images and user approval before rebuild.

**Architecture:** `run.sh` detects `.pi-packages` in the project root, derives a per-project image name (`pi-agent-isolated-<project>-<hash>`), prompts the user for approval, and passes packages as `--build-arg EXTRA_PACKAGES` to the Containerfile. Projects without `.pi-packages` use the shared base image.

**Tech Stack:** Bash, podman, Dockerfile

**Feature spec:** `docs/design/2026-05-28-per-project-image-spec.md`

**Delta spec:** `docs/design/2026-05-28-per-project-image-delta.md`

---

### Task 1: Package parsing and validation

**Delta requirement:** Package declaration file format + Input validation

**Files:**
- Modify: `run.sh` (add helper functions)
- Modify: `tests/test_run.py` (add parsing/validation tests)

- [ ] **Step 1: Write failing tests for package parsing and validation**

Add to `tests/test_run.py`:

```python
def test_run_script_parses_packages_from_file():
    """Verifies run.sh extracts package names from .pi-packages, ignoring comments and blanks."""
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

        # Create a .pi-packages with mixed content
        (tmpdir / ".pi-packages").write_text("# build tools\ncmake\n\n  pkgconf  \n")

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "echo", "test"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmpdir),
        )
        # The build command should contain both packages
        build_line = log_file.read_text()
        assert "cmake" in build_line, f"Expected cmake in build args, got: {build_line}"
        assert "pkgconf" in build_line, f"Expected pkgconf in build args, got: {build_line}"


def test_run_script_rejects_dangerous_characters_in_packages():
    """Verifies run.sh rejects .pi-packages containing shell metacharacters."""
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

        (tmpdir / ".pi-packages").write_text("cmake; rm -rf /\n")

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "echo", "test"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmpdir),
        )
        assert result.returncode != 0, f"Expected non-zero exit, got {result.returncode}: {result.stderr}"
        output = result.stdout + result.stderr
        assert "invalid" in output.lower() or "error" in output.lower() or "dangerous" in output.lower(), \
            f"Expected error message about invalid content, got: {output}"


def test_run_script_uses_shared_image_without_packages():
    """Verifies run.sh uses pi-agent-isolated when no .pi-packages exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        log_file = tmpdir / "podman.log"
        fake_config = tmpdir / "pi-config"
        fake_config.mkdir()

        fake_podman.write_text(
            f'#!/bin/bash\n'
            f'echo "$@" >> "{log_file}"\n'
            f'exit 1\n'
        )
        fake_podman.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "echo", "test"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmpdir),
        )
        assert result.returncode != 0  # expected — fake podman always fails
        build_line = log_file.read_text()
        assert "pi-agent-isolated" in build_line, f"Expected shared base image in build, got: {build_line}"


def test_run_script_uses_shared_image_with_empty_packages_file():
    """Verifies run.sh uses pi-agent-isolated when .pi-packages is empty or comment-only."""
    for content, label in [("", "empty"), ("# only comments\n", "comments-only")]:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            fake_podman = tmpdir / "podman"
            log_file = tmpdir / "podman.log"
            fake_config = tmpdir / "pi-config"
            fake_config.mkdir()

            fake_podman.write_text(
                f'#!/bin/bash\n'
                f'echo "$@" >> "{log_file}"\n'
                f'exit 1\n'
            )
            fake_podman.chmod(0o755)

            (tmpdir / ".pi-packages").write_text(content)

            env = os.environ.copy()
            env["PATH"] = f"{tmpdir}:{env['PATH']}"
            env["HOME"] = str(tmpdir)
            env["PI_AGENT_CONFIG"] = str(fake_config)

            result = subprocess.run(
                [str(REPO_ROOT / "run.sh"), "echo", "test"],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(tmpdir),
            )
            build_line = log_file.read_text()
            assert "pi-agent-isolated" in build_line, \
                f"Expected shared base for {label} .pi-packages, got: {build_line}"


def test_run_script_strips_crlf_from_packages():
    """Verifies run.sh handles Windows-style CRLF line endings in .pi-packages."""
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

        # Write with CRLF line endings
        (tmpdir / ".pi-packages").write_text("cmake\r\npkgconf\r\n")

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "echo", "test"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmpdir),
        )
        build_line = log_file.read_text()
        assert "cmake" in build_line, f"Expected cmake in build args, got: {build_line}"
        assert "pkgconf" in build_line, f"Expected pkgconf in build args, got: {build_line}"
        # Should not contain \r
        assert "\r" not in build_line, f"CRLF not stripped properly: {build_line}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /workspace && uv run pytest tests/test_run.py::test_run_script_parses_packages_from_file -v
uv run pytest tests/test_run.py::test_run_script_rejects_dangerous_characters_in_packages -v
uv run pytest tests/test_run.py::test_run_script_uses_shared_image_without_packages -v
uv run pytest tests/test_run.py::test_run_script_uses_shared_image_with_empty_packages_file -v
```

Expected: All FAIL (functions don't exist yet)

- [ ] **Step 3: Implement package parsing and validation in run.sh**

Add after the existing variables section (after `PERSIST_VOLUME=...`), before the `--reset` handler:

```bash
# --- Per-project package handling ---

parse_packages() {
    # Parse .pi-packages: strip whitespace, CRLF, skip comments/blanks.
    # Output: space-separated package list on stdout.
    local file="$1"
    if [ ! -f "$file" ]; then
        echo ""
        return
    fi
    sed 's/\r$//' "$file" | \
        sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | \
        grep -v '^#' | \
        grep -v '^$' | \
        tr '\n' ' '
}

validate_packages() {
    # Reject .pi-packages lines containing shell metacharacters.
    # Returns 1 and prints error if dangerous characters found.
    local file="$1"
    if [ ! -f "$file" ]; then
        return 0
    fi
    local invalid_line
    invalid_line=$(sed 's/\r$//' "$file" | \
        grep -n '[;|$\`&><*?~\\!]' || true)
    if [ -n "$invalid_line" ]; then
        echo "Error: .pi-packages contains dangerous characters:" >&2
        echo "$invalid_line" >&2
        echo "Only alphanumeric characters, hyphens, dots, and underscores are allowed." >&2
        return 1
    fi
    return 0
}

compute_hash() {
    # Compute deterministic hash of .pi-packages raw bytes.
    # Output: first 8 hex chars of SHA-256.
    local file="$1"
    if [ ! -f "$file" ]; then
        echo ""
        return
    fi
    sha256sum "$file" | cut -c1-8
}

# Read packages only if PI_AGENT_IMAGE is not set (override bypasses .pi-packages entirely)
EXTRA_PACKAGES=""
HAS_PACKAGES=0
if [ -z "${PI_AGENT_IMAGE:-}" ] && [ -f ".pi-packages" ]; then
    if ! validate_packages ".pi-packages"; then
        exit 1
    fi
    EXTRA_PACKAGES=$(parse_packages ".pi-packages")
    if [ -n "$(echo "$EXTRA_PACKAGES" | tr -d '[:space:]')" ]; then
        HAS_PACKAGES=1
    fi
fi
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /workspace && uv run pytest tests/test_run.py::test_run_script_parses_packages_from_file -v
uv run pytest tests/test_run.py::test_run_script_rejects_dangerous_characters_in_packages -v
uv run pytest tests/test_run.py::test_run_script_uses_shared_image_without_packages -v
uv run pytest tests/test_run.py::test_run_script_uses_shared_image_with_empty_packages_file -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add run.sh tests/test_run.py
git commit -m "feat: parse and validate .pi-packages in run.sh"
```

---

### Task 2: Per-project image name derivation

**Delta requirement:** Per-project image naming

**Files:**
- Modify: `run.sh` (image name derivation)
- Modify: `tests/test_run.py` (image name tests)

- [ ] **Step 1: Write failing tests for image name derivation**

Add to `tests/test_run.py`:

```python
def test_run_script_derives_per_project_image_name():
    """Verifies run.sh uses pi-agent-isolated-<project>-<hash> when .pi-packages exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        log_file = tmpdir / "podman.log"
        fake_config = tmpdir / "pi-config"
        fake_config.mkdir()

        fake_podman.write_text(
            f'#!/bin/bash\n'
            f'echo "$@" >> "{log_file}"\n'
            f'exit 1\n'
        )
        fake_podman.chmod(0o755)

        (tmpdir / ".pi-packages").write_text("cmake\n")

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "echo", "test"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmpdir),
        )
        build_line = log_file.read_text()
        # Should contain pi-agent-isolated-<basename>-<hash>
        assert "pi-agent-isolated-" in build_line, f"Expected per-project image name, got: {build_line}"
        # Should NOT be just pi-agent-isolated
        for line in build_line.splitlines():
            if "build" in line or "run" in line:
                assert line.strip() != "pi-agent-isolated", \
                    f"Should not use bare shared base, got: {line}"


def test_pi_agent_image_overrides_per_project_naming():
    """Verifies PI_AGENT_IMAGE takes precedence over .pi-packages derivation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        log_file = tmpdir / "podman.log"
        fake_config = tmpdir / "pi-config"
        fake_config.mkdir()

        fake_podman.write_text(
            f'#!/bin/bash\n'
            f'echo "$@" >> "{log_file}"\n'
            f'exit 1\n'
        )
        fake_podman.chmod(0o755)

        (tmpdir / ".pi-packages").write_text("cmake\n")

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)
        env["PI_AGENT_IMAGE"] = "my-custom-image"

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "echo", "test"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmpdir),
        )
        build_line = log_file.read_text()
        assert "my-custom-image" in build_line, f"Expected PI_AGENT_IMAGE override, got: {build_line}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /workspace && uv run pytest tests/test_run.py::test_run_script_derives_per_project_image_name -v
uv run pytest tests/test_run.py::test_pi_agent_image_overrides_per_project_naming -v
```

Expected: All FAIL

- [ ] **Step 3: Implement image name derivation in run.sh**

Replace the existing `IMAGE_NAME` line and update the build block:

```bash
# Derive image name
# PI_AGENT_IMAGE overrides everything. Otherwise, use per-project naming
# when .pi-packages has valid packages, else shared base.
if [ -n "${PI_AGENT_IMAGE:-}" ]; then
    IMAGE_NAME="$PI_AGENT_IMAGE"
elif [ "$HAS_PACKAGES" -eq 1 ]; then
    PKG_HASH=$(compute_hash ".pi-packages")
    IMAGE_NAME="pi-agent-isolated-${PROJECT_NAME}-${PKG_HASH}"
else
    IMAGE_NAME="pi-agent-isolated"
fi
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /workspace && uv run pytest tests/test_run.py::test_run_script_derives_per_project_image_name -v
uv run pytest tests/test_run.py::test_pi_agent_image_overrides_per_project_naming -v
```

Expected: All PASS

- [ ] **Step 5: Verify existing tests still pass**

```bash
cd /workspace && uv run pytest tests/test_run.py -v
```

Expected: All PASS (existing tests use default env, no .pi-packages → shared base)

- [ ] **Step 6: Commit**

```bash
git add run.sh tests/test_run.py
git commit -m "feat: per-project image name derivation with PI_AGENT_IMAGE override"
```

---

### Task 3: Approval prompt and build arg wiring

**Delta requirement:** User approval before rebuild

**Files:**
- Modify: `run.sh` (approval prompt, build arg passing)
- Modify: `tests/test_run.py` (approval tests)

- [ ] **Step 1: Write failing test for approval prompt**

Add to `tests/test_run.py`:

```python
def test_run_script_prints_rebuild_notice_with_packages():
    """Verifies run.sh prints a notice when rebuilding with extra packages."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        log_file = tmpdir / "podman.log"
        fake_config = tmpdir / "pi-config"
        fake_config.mkdir()

        # First call: volume create. Second: image exists (returns 1). Third: build. Rest: run.
        fake_podman.write_text(
            f'#!/bin/bash\n'
            f'echo "$@" >> "{log_file}"\n'
            f'if [ "$1" = "image" ] && [ "$2" = "exists" ]; then\n'
            f'    exit 1\n'
            f'fi\n'
            f'exit 0\n'
        )
        fake_podman.chmod(0o755)

        (tmpdir / ".pi-packages").write_text("cmake\n")

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "echo", "test"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmpdir),
            input="y\n",
        )
        output = result.stdout + result.stderr
        # Should mention the packages and/or "extra" or "package"
        assert "extra" in output.lower() or "package" in output.lower(), \
            f"Expected rebuild notice mentioning packages, got: {output}"


def test_run_script_passes_extra_packages_build_arg():
    """Verifies run.sh passes EXTRA_PACKAGES as --build-arg to podman build.
    Note: This test uses pty to provide a TTY so the approval prompt can be answered."""
    import pty, select, os as _os

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

        (tmpdir / ".pi-packages").write_text("cmake\npkgconf\n")

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)

        # Use pty to provide a TTY for the approval prompt
        master_fd, slave_fd = pty.openpty()
        proc = subprocess.Popen(
            [str(REPO_ROOT / "run.sh"), "echo", "test"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            cwd=str(tmpdir),
        )
        _os.close(slave_fd)

        # Send 'y\n' to approve
        _os.write(master_fd, b"y\n")
        proc.wait()

        # Read output
        output = b""
        while True:
            try:
                ready, _, _ = select.select([master_fd], [], [], 0.1)
                if not ready:
                    break
                output += _os.read(master_fd, 4096)
            except OSError:
                break
        _os.close(master_fd)

        build_lines = log_file.read_text().splitlines()
        build_line = ""
        for line in build_lines:
            if "build" in line:
                build_line = line
                break
        assert "--build-arg" in build_line, f"Expected --build-arg in build command, got: {build_line}"
        assert "cmake" in build_line, f"Expected cmake in build args, got: {build_line}"
        assert "pkgconf" in build_line, f"Expected pkgconf in build args, got: {build_line}"


def test_run_script_refuses_rebuild_without_tty():
    """Verifies run.sh refuses to rebuild when stdin is not a terminal (non-interactive mode).
    The interactive approval prompt cannot be tested with subprocess (no TTY), so this tests
    the non-interactive error path instead."""
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

        (tmpdir / ".pi-packages").write_text("cmake\n")

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "echo", "test"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmpdir),
        )
        output = result.stdout + result.stderr
        assert result.returncode != 0, f"Expected non-zero exit for non-interactive rebuild"
        assert "terminal" in output.lower() or "interactive" in output.lower() or "tty" in output.lower(), \
            f"Expected non-interactive error message, got: {output}"


def test_run_script_non_terminal_requires_approval():
    """Verifies run.sh errors out when .pi-packages needs rebuild but stdin is not a terminal."""
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

        (tmpdir / ".pi-packages").write_text("cmake\n")

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)

        # Run without a TTY and without input — simulates non-interactive pipe
        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "echo", "test"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmpdir),
            input="",
        )
        output = result.stdout + result.stderr
        assert result.returncode != 0, f"Expected non-zero exit for non-interactive approval"
        assert "error" in output.lower() or "terminal" in output.lower() or "interactive" in output.lower(), \
            f"Expected error about non-interactive mode, got: {output}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /workspace && uv run pytest tests/test_run.py::test_run_script_prints_rebuild_notice_with_packages -v
uv run pytest tests/test_run.py::test_run_script_passes_extra_packages_build_arg -v
uv run pytest tests/test_run.py::test_run_script_requires_approval_on_new_packages -v
```

Expected: All FAIL

- [ ] **Step 3: Implement approval prompt and build arg in run.sh**

Replace the existing image build block:

```bash
# Build image if it doesn't exist
if ! podman image exists "$IMAGE_NAME"; then
    if [ "$HAS_PACKAGES" -eq 1 ] && [ -t 0 ]; then
        echo ""
        echo "[!] Building sandbox image with extra packages:"
        for pkg in $EXTRA_PACKAGES; do
            echo "       $pkg"
        done
        echo ""
        read -r -p "Approve? [y/N] " APPROVAL
        if [ "$APPROVAL" != "y" ] && [ "$APPROVAL" != "Y" ]; then
            echo "Aborted. Extra packages not installed." >&2
            exit 1
        fi
    elif [ "$HAS_PACKAGES" -eq 1 ]; then
        echo "" >&2
        echo "Error: .pi-packages requires image rebuild but stdin is not a terminal." >&2
        echo "Run interactively or set PI_AGENT_IMAGE to bypass." >&2
        exit 1
    fi

    echo "Building image ${IMAGE_NAME}..."
    if [ "$HAS_PACKAGES" -eq 1 ]; then
        podman build \
            --build-arg EXTRA_PACKAGES="$EXTRA_PACKAGES" \
            -t "$IMAGE_NAME" "$(dirname "$0")"
    else
        podman build -t "$IMAGE_NAME" "$(dirname "$0")"
    fi
fi
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /workspace && uv run pytest tests/test_run.py::test_run_script_prints_rebuild_notice_with_packages -v
uv run pytest tests/test_run.py::test_run_script_passes_extra_packages_build_arg -v
uv run pytest tests/test_run.py::test_run_script_requires_approval_on_new_packages -v
```

Expected: All PASS

- [ ] **Step 5: Verify all test_run.py tests pass**

```bash
cd /workspace && uv run pytest tests/test_run.py -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add run.sh tests/test_run.py
git commit -m "feat: approval prompt and build-arg for extra packages"
```

---

### Task 4: Containerfile EXTRA_PACKAGES support

**Delta requirement:** Package declaration file format (packages installed in image)

**Files:**
- Modify: `Containerfile`
- Modify: `tests/test_containerfile.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_containerfile.py`:

```python
def test_containerfile_accepts_extra_packages_arg():
    """Verifies Containerfile defines EXTRA_PACKAGES build arg."""
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "ARG EXTRA_PACKAGES" in content, "Missing ARG EXTRA_PACKAGES"
    assert "EXTRA_PACKAGES" in content, "EXTRA_PACKAGES must be used in the build"


def test_containerfile_installs_extra_packages():
    """Verifies Containerfile conditionally installs EXTRA_PACKAGES."""
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "EXTRA_PACKAGES" in content, "Must reference EXTRA_PACKAGES"
    assert "pacman" in content, "Must use pacman for package installation"


def test_containerfile_has_build_error_handling():
    """Verifies Containerfile has error handling for package installation failures."""
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "exit 1" in content, "Must have explicit error exit on package failure"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /workspace && uv run pytest tests/test_containerfile.py::test_containerfile_accepts_extra_packages_arg -v
```

Expected: FAIL

- [ ] **Step 3: Implement in Containerfile**

Add `ARG EXTRA_PACKAGES=""` near the top and append to the pacman install line:

```dockerfile
ARG PI_AGENT_VERSION=0.73.1
ARG EXTRA_PACKAGES=""

RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm nodejs npm git openssh bash fd ripgrep diffutils python python-pip uv gcc make ast-grep rsync ${EXTRA_PACKAGES} || \
    { echo "Error: Failed to install one or more packages. Check the package names in .pi-packages." >&2; exit 1; } && \
    pacman -Scc --noconfirm
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /workspace && uv run pytest tests/test_containerfile.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add Containerfile tests/test_containerfile.py
git commit -m "feat: accept EXTRA_PACKAGES build arg in Containerfile"
```

---

### Task 5: Makefile images target

**Delta requirement:** Image listing

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add images target to Makefile**

```makefile
IMAGE_NAME := pi-agent-isolated

.PHONY: build shell pi clean volumes reset images

install:
	./install.sh

build:
	podman build -t $(IMAGE_NAME) .

shell:
	./run.sh bash

pi:
	./run.sh pi

clean:
	podman rmi $(IMAGE_NAME) || true

volumes:
	@podman volume ls --filter name=pi-agent-persist- --format '{{.Name}}'

reset:
	./run.sh --reset

images:
	@podman images --filter "reference=pi-agent-isolated-*" --format "{{.Repository}}:{{.Tag}}" 2>/dev/null || true
```

- [ ] **Step 2: Add test for images target in test_makefile.py**

Add to `tests/test_makefile.py`:

```python
def test_makefile_has_images_target():
    """Verifies the Makefile includes the images target for listing per-project images."""
    content = (REPO_ROOT / "Makefile").read_text()
    assert "images:" in content, "Missing images target in Makefile"
```

- [ ] **Step 2: Commit**

```bash
git add Makefile
git commit -m "feat: add make images target for listing per-project images"
```

---

### Task 6: Update APPEND_SYSTEM.md

**Delta requirement:** Agent documentation

**Files:**
- Modify: `config/APPEND_SYSTEM.md`

- [ ] **Step 1: Add .pi-packages documentation to APPEND_SYSTEM.md**

Append to the "Installed Tools" or "Package Managers" section, or add a new section:

```markdown
## Per-Project System Dependencies

If the project needs system-level packages (CMake, libffi, ffmpeg) that are not available via npm/pip/uv:

1. Create or edit `.pi-packages` in the project root. One package per line, `#` for comments.
2. The user must approve the packages on their next sandbox session (interactive prompt).
3. On approval, the sandbox image is rebuilt with those packages installed.

Example `.pi-packages`:
```
# Build tools
cmake
pkgconf
```

After writing `.pi-packages`, tell the user: "I've added packages to `.pi-packages`. Re-enter the sandbox to approve and rebuild."
```

- [ ] **Step 2: Verify APPEND_SYSTEM.md contains the text**

```bash
grep -c "\.pi-packages" config/APPEND_SYSTEM.md
```

Expected: At least 1 match

- [ ] **Step 3: Commit**

```bash
git add config/APPEND_SYSTEM.md
git commit -m "docs: document .pi-packages workflow in APPEND_SYSTEM.md"
```

---

### Task 7: Integration and cleanup tests

**Delta requirement:** Full flow verification, build failure handling

**Files:**
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Write integration tests**

Add to `tests/test_integration.py`:

```python
def test_integration_per_project_image_with_packages():
    """End-to-end: .pi-packages triggers per-project image naming."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        log_file = tmpdir / "podman.log"
        fake_config = tmpdir / "pi-config"
        fake_config.mkdir()

        # Simulate: volume create, image exists (not found), build, run
        fake_podman.write_text(
            f'#!/bin/bash\n'
            f'echo "$@" >> "{log_file}"\n'
            f'if [ "$1" = "image" ] && [ "$2" = "exists" ]; then\n'
            f'    exit 1\n'
            f'fi\n'
            f'exit 0\n'
        )
        fake_podman.chmod(0o755)

        (tmpdir / ".pi-packages").write_text("cmake\npkgconf\n")

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "echo", "test"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmpdir),
            input="y\n",
        )
        assert result.returncode == 0, f"Expected success, got: {result.stderr}"

        lines = log_file.read_text().strip().splitlines()
        # Verify per-project image name in build command
        build_line = [l for l in lines if "build" in l][0]
        assert "pi-agent-isolated-" in build_line, f"Expected per-project name: {build_line}"
        assert "--build-arg" in build_line, f"Expected build-arg: {build_line}"
        assert "EXTRA_PACKAGES" in build_line, f"Expected EXTRA_PACKAGES: {build_line}"


def test_integration_no_rebuild_when_image_exists():
    """Verifies no rebuild when matching per-project image already exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        log_file = tmpdir / "podman.log"
        fake_config = tmpdir / "pi-config"
        fake_config.mkdir()

        # Image exists returns 0 (found) — no build
        fake_podman.write_text(
            f'#!/bin/bash\n'
            f'echo "$@" >> "{log_file}"\n'
            f'exit 0\n'
        )
        fake_podman.chmod(0o755)

        (tmpdir / ".pi-packages").write_text("cmake\n")

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "echo", "test"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmpdir),
        )
        assert result.returncode == 0, f"Expected success: {result.stderr}"
        lines = log_file.read_text().strip().splitlines()
        # No build command should be present
        # No "podman build" (without "exists") should be present
        build_lines = [l for l in lines if "build" in l.lower() and "exists" not in l.lower() and "image" not in l.lower()]
        assert len(build_lines) == 0, f"Expected no build when image exists, got: {build_lines}"
```

- [ ] **Step 2: Run integration tests**

```bash
cd /workspace && uv run pytest tests/test_integration.py::test_integration_per_project_image_with_packages -v
uv run pytest tests/test_integration.py::test_integration_no_rebuild_when_image_exists -v
```

Expected: All PASS

- [ ] **Step 3: Run full test suite**

```bash
cd /workspace && uv run pytest -v
```

Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: integration tests for per-project image flow"
```

---

### Task 8: Final verification and cleanup

**Files:**
- All modified files

- [ ] **Step 1: Run the full test suite**

```bash
cd /workspace && uv run pytest -v
```

Expected: All PASS

- [ ] **Step 2: Verify install.sh still works**

`install.sh` references `PI_AGENT_IMAGE` and builds the image. It should still work since `PI_AGENT_IMAGE` defaults to `pi-agent-isolated` when unset and `.pi-packages` doesn't exist. The `install.sh` uses `podman build -t "$IMAGE_NAME" "$SCRIPT_DIR"` directly, not through `run.sh`. It should be fine since the Containerfile's `ARG EXTRA_PACKAGES=""` defaults to empty.

- [ ] **Step 3: Verify Makefile build target still works**

The `Makefile` `build` target uses `podman build -t $(IMAGE_NAME) .` without `EXTRA_PACKAGES`. This is intentional — it builds the shared base. Per-project builds happen through `run.sh`.

- [ ] **Step 4: Review git diff**

```bash
cd /workspace && git diff --stat HEAD
```

Expected changes:
- `run.sh` — package parsing, validation, image naming, approval, build args
- `Containerfile` — ARG EXTRA_PACKAGES, conditional install
- `Makefile` — images target
- `config/APPEND_SYSTEM.md` — .pi-packages documentation
- `tests/test_run.py` — parsing, validation, naming, approval tests
- `tests/test_containerfile.py` — EXTRA_PACKAGES test
- `tests/test_integration.py` — end-to-end flow tests

- [ ] **Step 5: Final commit (squash if needed)**

```bash
git add -A
git commit -m "feat: per-project sandbox images via .pi-packages with user approval"
```
