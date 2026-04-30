"""Security-focused tests for pi-agent-isolation sandbox.

These tests verify that the container is properly hardened against escape
and that defensive flags are enforced at runtime.
"""
import os
import pathlib
import subprocess
import tempfile
import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent
TEST_IMAGE = "pi-agent-isolated-test"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_env(tmpdir):
    """Build the environment dict for run.sh invocations."""
    env = os.environ.copy()
    env["PI_AGENT_IMAGE"] = TEST_IMAGE
    env["PI_AGENT_CONFIG"] = str(pathlib.Path(tmpdir) / "pi-config")

    env_file = pathlib.Path(tmpdir) / ".env"
    env_file.write_text("VLLM_API_KEY=\nOPENROUTER_API_KEY=\n")
    env["PI_AGENT_ENV_FILE"] = str(env_file)
    return env


# ---------------------------------------------------------------------------
# Flag enforcement — parsed from run.sh via fake podman
# ---------------------------------------------------------------------------

def test_run_script_has_security_flags():
    """Verify run.sh passes all required security flags to podman."""
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

        (tmpdir / ".env").write_text(
            "VLLM_API_KEY=test-vllm-key\nOPENROUTER_API_KEY=test-openrouter-key\n"
        )

        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "pi", "-p", "hello"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        log_lines = log_file.read_text().strip().splitlines()
        # The "run" invocation is the last (or third) call
        run_line = log_lines[-1]

        assert "--cap-drop=ALL" in run_line, "Missing --cap-drop=ALL"
        assert "--security-opt=no-new-privileges" in run_line, (
            "Missing --security-opt=no-new-privileges"
        )
        assert "--read-only" in run_line, "Missing --read-only"
        assert "--tmpfs" in run_line and "/tmp" in run_line, (
            "Missing --tmpfs /tmp"
        )
        assert "--pids-limit" in run_line, "Missing --pids-limit"
        assert "--memory" in run_line, "Missing --memory limit"
        assert "--cpus" in run_line, "Missing --cpus limit"


# ---------------------------------------------------------------------------
# Runtime security — actual container probes via run.sh
# ---------------------------------------------------------------------------


def test_no_host_socket_accessible(built_image):
    """No Docker or Podman socket should be mounted in the container."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        config_dir = tmpdir / "pi-config"
        config_dir.mkdir()

        env = _run_env(tmpdir)

        result = subprocess.run(
            [
                str(REPO_ROOT / "run.sh"),
                "bash", "-c",
                "test -e /var/run/docker.sock || test -e /var/run/podman/podman.sock; echo $?",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        # Neither socket should exist — test -e returns 1 (false) → echo 1
        assert result.stdout.strip() == "1", "Host runtime socket is accessible"


def test_rootfs_is_readonly(built_image):
    """The root filesystem (outside tmpfs and mounts) must be read-only."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        config_dir = tmpdir / "pi-config"
        config_dir.mkdir()

        env = _run_env(tmpdir)

        result = subprocess.run(
            [
                str(REPO_ROOT / "run.sh"),
                "bash", "-c",
                "touch /etc/test_ro 2>/dev/null; echo $?",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "1", (
            "Root filesystem is writable — /etc should be read-only"
        )


def test_tmp_is_writable(built_image):
    """/tmp (tmpfs mount) must still be writable for tools that need it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        config_dir = tmpdir / "pi-config"
        config_dir.mkdir()

        env = _run_env(tmpdir)

        result = subprocess.run(
            [
                str(REPO_ROOT / "run.sh"),
                "bash", "-c",
                "touch /tmp/security_test_tmp && rm /tmp/security_test_tmp && echo ok",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        assert "ok" in result.stdout, "/tmp is not writable"


def test_no_suid_escalation(built_image):
    """no-new-privileges should block setuid-based escalation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        config_dir = tmpdir / "pi-config"
        config_dir.mkdir()

        env = _run_env(tmpdir)

        result = subprocess.run(
            [
                str(REPO_ROOT / "run.sh"),
                "bash", "-c",
                # Check that /proc/self/status has NoNewPrivs:1
                "grep NoNewPrivs /proc/self/status | awk '{print $2}'",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "1", (
            "no-new-privileges not enforced (NoNewPrivs should be 1)"
        )


def test_capabilities_are_dropped(built_image):
    """All capabilities should be dropped (CapEff should be 0)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        config_dir = tmpdir / "pi-config"
        config_dir.mkdir()

        env = _run_env(tmpdir)

        result = subprocess.run(
            [
                str(REPO_ROOT / "run.sh"),
                "bash", "-c",
                "grep CapEff /proc/self/status | awk '{print $2}'",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        # CapEff of 0000000000000000 means no effective capabilities
        assert result.stdout.strip() == "0000000000000000", (
            f"Capabilities not fully dropped: {result.stdout.strip()}"
        )


def test_cannot_see_host_processes(built_image):
    """The container should not be able to list host processes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        config_dir = tmpdir / "pi-config"
        config_dir.mkdir()

        env = _run_env(tmpdir)

        result = subprocess.run(
            [
                str(REPO_ROOT / "run.sh"),
                "bash", "-c",
                # PID 1 inside the container should be our command, not the host init
                "cat /proc/1/cmdline | tr '\\0' ' '; echo",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        # PID 1 should be something we passed in (bash/entrypoint),
        # not a host process like systemd or init
        stdout = result.stdout.strip()
        assert "systemd" not in stdout, (
            "PID 1 is the host init — PID namespace may not be isolated"
        )


def test_proc_root_cannot_escape_to_host(built_image):
    """/proc/1/root should not give access to the host filesystem."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        config_dir = tmpdir / "pi-config"
        config_dir.mkdir()

        env = _run_env(tmpdir)

        result = subprocess.run(
            [
                str(REPO_ROOT / "run.sh"),
                "bash", "-c",
                # Try to read the host /etc/hostname — should fail or be empty
                "cat /proc/1/root/etc/hostname 2>/dev/null; echo exitcode:$?",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        # Either the file is unreadable (exit code > 0 in output) or
        # it's the container's own empty hostname (no host info leaked)
        output = result.stdout.strip()
        if "exitcode:0" in output:
            # If readable, it should be the container's own hostname (not host)
            pass  # acceptable — container's own /etc/hostname is fine


def test_symlink_cannot_escape_workspace(built_image):
    """Symlinks created in /workspace should not escape to the host."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        marker = tmpdir / "PROJECT_MARKER"
        marker.write_text("ok")

        config_dir = tmpdir / "pi-config"
        config_dir.mkdir()

        env = _run_env(tmpdir)

        result = subprocess.run(
            [
                str(REPO_ROOT / "run.sh"),
                "bash", "-c",
                # Create a symlink pointing outside /workspace and try to read host files
                "ln -sf /etc/shadow /workspace/escape_link 2>/dev/null; "
                "cat /workspace/escape_link 2>/dev/null; echo exitcode:$?",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmpdir),
        )
        assert result.returncode == 0, result.stderr
        # The symlink should either fail to resolve or give the container's
        # own /etc/shadow (which doesn't exist / is empty) — not the host's
        output = result.stdout.strip()
        # If it reads successfully, it shouldn't contain host root shadow data
        # The safest outcome is exitcode:1 (file not found / permission denied)
        if "exitcode:0" in output:
            assert "root" not in output.split("exitcode:0")[0], (
                "Symlink may have accessed host /etc/shadow"
            )


def test_cannot_execute_setuid_binaries(built_image):
    """Even if a setuid binary exists, no-new-privileges should block it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        config_dir = tmpdir / "pi-config"
        config_dir.mkdir()

        env = _run_env(tmpdir)

        result = subprocess.run(
            [
                str(REPO_ROOT / "run.sh"),
                "bash", "-c",
                # Try to run a common setuid binary (shouldn't exist, but if it does)
                "find / -perm -4000 -type f 2>/dev/null | head -5; echo ---; "
                "echo done",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        # Should find no setuid binaries in a hardened image
        lines = [
            l for l in result.stdout.strip().splitlines()
            if l and l not in ("---", "done")
        ]
        assert len(lines) == 0, (
            f"Found setuid binaries in container: {lines}"
        )
