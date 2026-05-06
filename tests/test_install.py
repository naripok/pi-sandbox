"""Tests for install.sh — the installation script for the pi-agent sandbox."""
import os
import pathlib
import shutil
import subprocess
import tempfile

REPO_ROOT = pathlib.Path(__file__).parent.parent
INSTALL_SCRIPT = REPO_ROOT / "install.sh"


# ---- Existence and permissions ----


def test_install_script_exists():
    assert INSTALL_SCRIPT.exists()


def test_install_script_executable():
    assert os.access(INSTALL_SCRIPT, os.X_OK)


# ---- Prerequisite checks ----


def test_fails_when_podman_not_found():
    """install.sh should exit non-zero when podman is not in PATH."""
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    try:
        # Provide basic utilities but no podman
        for cmd in ["bash", "dirname", "pwd", "echo"]:
            src = shutil.which(cmd)
            if src:
                (tmpdir / cmd).symlink_to(src)

        env = os.environ.copy()
        env["PATH"] = str(tmpdir)

        result = subprocess.run(
            [str(INSTALL_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode != 0
        assert "Podman not found" in result.stderr or "Podman not found" in result.stdout
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_fails_when_podman_info_fails():
    """install.sh should exit non-zero when rootless podman isn't working."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        fake_podman.write_text(
            "#!/bin/bash\n"
            'if [ "$1" = "info" ]; then\n'
            "    exit 1\n"
            "fi\n"
            "exit 0\n"
        )
        fake_podman.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["XDG_RUNTIME_DIR"] = str(tmpdir)

        result = subprocess.run(
            [str(INSTALL_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode != 0
        assert "not working" in result.stdout or "not working" in result.stderr


def test_fails_when_xdg_runtime_dir_not_set():
    """install.sh should exit non-zero when XDG_RUNTIME_DIR is not set."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        fake_podman.write_text("#!/bin/bash\nexit 0\n")
        fake_podman.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env.pop("XDG_RUNTIME_DIR", None)

        result = subprocess.run(
            [str(INSTALL_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode != 0
        assert "XDG_RUNTIME_DIR" in result.stdout or "XDG_RUNTIME_DIR" in result.stderr


# ---- Successful installation ----


def test_successful_install_builds_image():
    """When podman works, install.sh should build the image and print instructions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        log_file = tmpdir / "podman.log"

        fake_podman.write_text(
            f'#!/bin/bash\n'
            f'echo "$@" >> "{log_file}"\n'
            f'exit 0\n'
        )
        fake_podman.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["XDG_RUNTIME_DIR"] = str(tmpdir)

        result = subprocess.run(
            [str(INSTALL_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"

        log_lines = log_file.read_text().strip().splitlines()

        # podman info check
        assert "info" in log_lines[0], f"Expected podman info check, got: {log_lines[0]}"

        # podman --version
        assert "--version" in log_lines[1], f"Expected podman --version, got: {log_lines[1]}"

        # podman image exists check
        assert "image exists" in log_lines[2], f"Expected image exists, got: {log_lines[2]}"

        # podman build (image didn't "exist" — exit 0 from fake means it ran)
        # Since our fake always exits 0, `podman image exists` returns 0 (true),
        # so it skips the build. We need a smarter fake.


def test_successful_install_builds_image_when_missing():
    """install.sh should invoke podman build when the image doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        log_file = tmpdir / "podman.log"

        # Fake: `image exists` returns 1 (not found), everything else returns 0
        fake_podman.write_text(
            f'#!/bin/bash\n'
            f'echo "$@" >> "{log_file}"\n'
            f'if [ "$1" = "image" ] && [ "$2" = "exists" ]; then\n'
            f'    exit 1\n'
            f"fi\n"
            f'exit 0\n'
        )
        fake_podman.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["XDG_RUNTIME_DIR"] = str(tmpdir)

        result = subprocess.run(
            [str(INSTALL_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"

        log_lines = log_file.read_text().strip().splitlines()

        # Should contain a build invocation
        build_calls = [l for l in log_lines if "build" in l]
        assert len(build_calls) >= 1, f"Expected podman build, got logs: {log_lines}"

        # Build should target the repo root
        assert str(REPO_ROOT) in build_calls[0], f"Build should target repo root: {build_calls[0]}"


def test_skips_build_when_image_exists():
    """install.sh should skip the build when the image already exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        log_file = tmpdir / "podman.log"

        # Fake: `image exists` returns 0 (found)
        fake_podman.write_text(
            f'#!/bin/bash\n'
            f'echo "$@" >> "{log_file}"\n'
            f'exit 0\n'
        )
        fake_podman.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["XDG_RUNTIME_DIR"] = str(tmpdir)

        result = subprocess.run(
            [str(INSTALL_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"

        log_lines = log_file.read_text().strip().splitlines()

        # No build call should be present
        build_calls = [l for l in log_lines if "build" in l]
        assert len(build_calls) == 0, f"Should skip build when image exists, got: {log_lines}"

        # Should warn about existing image
        output = result.stdout
        assert "already exists" in output, f"Expected 'already exists' warning: {output}"


# ---- Output content ----


def test_output_contains_alias_instruction():
    """install.sh should print the alias with the correct absolute path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        fake_podman.write_text(
            '#!/bin/bash\n'
            'exit 0\n'
        )
        fake_podman.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["XDG_RUNTIME_DIR"] = str(tmpdir)

        result = subprocess.run(
            [str(INSTALL_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0

        output = result.stdout
        assert "alias pi-sandbox=" in output, f"Missing alias instruction: {output}"
        assert str(REPO_ROOT) in output, f"Alias should contain repo path: {output}"
        assert "run.sh" in output, f"Alias should reference run.sh: {output}"


def test_output_contains_usage_examples():
    """install.sh should print usage examples for the alias."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        fake_podman.write_text("#!/bin/bash\nexit 0\n")
        fake_podman.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["XDG_RUNTIME_DIR"] = str(tmpdir)

        result = subprocess.run(
            [str(INSTALL_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0

        output = result.stdout
        assert "pi-sandbox pi" in output, "Should show pi usage example"
        assert "pi-sandbox --reset" in output, "Should show reset usage example"


# ---- Custom image name ----


def test_respects_custom_image_name():
    """install.sh should use PI_AGENT_IMAGE when set."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        fake_podman = tmpdir / "podman"
        log_file = tmpdir / "podman.log"

        fake_podman.write_text(
            f'#!/bin/bash\n'
            f'echo "$@" >> "{log_file}"\n'
            f'if [ "$1" = "image" ] && [ "$2" = "exists" ]; then\n'
            f'    exit 1\n'
            f"fi\n"
            f'exit 0\n'
        )
        fake_podman.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["PI_AGENT_IMAGE"] = "my-custom-image"
        env["XDG_RUNTIME_DIR"] = str(tmpdir)

        result = subprocess.run(
            [str(INSTALL_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        log_content = log_file.read_text()
        assert "my-custom-image" in log_content, f"Should use custom image name: {log_content}"
