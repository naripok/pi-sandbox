import os
import os as _os
import pathlib
import pty
import select
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
        ["podman", "run", "--rm", built_image, "bash", "-c", "command -v rsync"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "rsync not found in container"


def test_container_has_setpriv(built_image):
    result = subprocess.run(
        ["podman", "run", "--rm", built_image, "bash", "-c", "command -v setpriv"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "setpriv not found in container"


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


# --- Persistent volume tests ---


def test_persistence_across_runs(built_image):
    """Files written inside the container persist across separate run.sh invocations.
    Cleaned up with --reset."""
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
                    "mkdir -p /home/pi/.local && echo persisted > /home/pi/.local/marker.txt",
                ],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(tmpdir),
            )
            assert result.returncode == 0, result.stderr

            # Second run: verify the marker file persists
            result = subprocess.run(
                [
                    str(REPO_ROOT / "run.sh"),
                    "cat", "/home/pi/.local/marker.txt",
                ],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(tmpdir),
            )
            assert result.returncode == 0, result.stderr
            assert result.stdout.strip() == "persisted"
        finally:
            subprocess.run(
                [str(REPO_ROOT / "run.sh"), "--reset"],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(tmpdir),
            )


def test_volume_isolation(built_image):
    """Two separate project directories get isolated persistent volumes.
    Data written in project A's volume is not visible from project B."""
    with tempfile.TemporaryDirectory() as tmpdir_a, tempfile.TemporaryDirectory() as tmpdir_b:
        tmpdir_a = pathlib.Path(tmpdir_a)
        tmpdir_b = pathlib.Path(tmpdir_b)

        (tmpdir_a / "pi-config").mkdir()
        (tmpdir_b / "pi-config").mkdir()

        env_a = _run_env(tmpdir_a)
        env_b = _run_env(tmpdir_b)

        try:
            # Write data in project A's volume
            result = subprocess.run(
                [
                    str(REPO_ROOT / "run.sh"),
                    "bash", "-c",
                    "echo project-a-data > /home/pi/.local/project_id.txt",
                ],
                capture_output=True,
                text=True,
                env=env_a,
                cwd=str(tmpdir_a),
            )
            assert result.returncode == 0, result.stderr

            # Verify project B cannot see project A's data
            result = subprocess.run(
                [
                    str(REPO_ROOT / "run.sh"),
                    "bash", "-c",
                    "cat /home/pi/.local/project_id.txt 2>/dev/null; echo exit=$?",
                ],
                capture_output=True,
                text=True,
                env=env_b,
                cwd=str(tmpdir_b),
            )
            assert result.returncode == 0, result.stderr
            assert "project-a-data" not in result.stdout
        finally:
            subprocess.run(
                [str(REPO_ROOT / "run.sh"), "--reset"],
                capture_output=True,
                text=True,
                env=env_a,
                cwd=str(tmpdir_a),
            )
            subprocess.run(
                [str(REPO_ROOT / "run.sh"), "--reset"],
                capture_output=True,
                text=True,
                env=env_b,
                cwd=str(tmpdir_b),
            )


def test_config_sync(built_image):
    """Host config changes (new skill file) are synced into the container on next run,
    while session data written to the volume is preserved."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        config_dir = tmpdir / "pi-config"
        config_dir.mkdir()

        # Initial config: one skill file
        skills_dir = config_dir / "skills"
        skills_dir.mkdir()
        (skills_dir / "old-skill.md").write_text("# Old Skill")

        env = _run_env(tmpdir)

        try:
            # First run: create a session file in the volume
            result = subprocess.run(
                [
                    str(REPO_ROOT / "run.sh"),
                    "bash", "-c",
                    "mkdir -p /home/pi/.pi-agent-data/sessions && echo session-data > /home/pi/.pi-agent-data/sessions/test-session.json",
                ],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(tmpdir),
            )
            assert result.returncode == 0, result.stderr

            # Modify host config: add a new skill file
            (skills_dir / "new-skill.md").write_text("# New Skill")

            # Second run: verify new skill is synced AND session is preserved
            result = subprocess.run(
                [
                    str(REPO_ROOT / "run.sh"),
                    "bash", "-c",
                    "cat /home/pi/.pi-agent-data/skills/new-skill.md && "
                    "cat /home/pi/.pi-agent-data/sessions/test-session.json",
                ],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(tmpdir),
            )
            assert result.returncode == 0, result.stderr
            assert "# New Skill" in result.stdout, "New skill was not synced"
            assert "session-data" in result.stdout, "Session data was not preserved"
        finally:
            subprocess.run(
                [str(REPO_ROOT / "run.sh"), "--reset"],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(tmpdir),
            )


# --- Per-project image integration tests ---


def test_integration_per_project_image_with_packages():
    """End-to-end: .pi-packages triggers per-project image naming and build-arg passing.
    Uses pty to provide a TTY for the approval prompt."""
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

        # Use pty to provide a TTY for the approval prompt
        master_fd, slave_fd = pty.openpty()
        proc = subprocess.Popen(
            [str(REPO_ROOT / "run.sh"), "echo", "test"],
            stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            env=env, cwd=str(tmpdir),
        )
        _os.close(slave_fd)
        _os.write(master_fd, b"y\n")
        proc.wait(timeout=30)

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

        assert proc.returncode == 0, f"Expected success, got: {output.decode('utf-8', errors='replace')}"

        lines = log_file.read_text().strip().splitlines()
        build_line = ""
        for line in lines:
            if "build" in line:
                build_line = line
                break
        assert "pi-agent-isolated-" in build_line, f"Expected per-project image name, got: {build_line}"
        assert "--build-arg" in build_line, f"Expected --build-arg, got: {build_line}"
        assert "EXTRA_PACKAGES" in build_line, f"Expected EXTRA_PACKAGES arg, got: {build_line}"


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
        # No "podman build" (without "exists") should be present
        build_lines = [l for l in lines if "build" in l.lower() and "exists" not in l.lower() and "image" not in l.lower()]
        assert len(build_lines) == 0, f"Expected no build when image exists, got: {build_lines}"
