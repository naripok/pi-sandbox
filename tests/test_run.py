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
            f'if [ "$1" = "image" ] && [ "$2" = "exists" ]; then\n'
            f'    exit 1\n'
            f'fi\n'
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
            f'if [ "$1" = "image" ] && [ "$2" = "exists" ]; then\n'
            f'    exit 1\n'
            f'fi\n'
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


def test_run_script_pi_agent_image_bypasses_packages():
    """Verifies PI_AGENT_IMAGE bypasses .pi-packages entirely, even with dangerous content."""
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

        # .pi-packages contains dangerous characters — would normally be rejected
        (tmpdir / ".pi-packages").write_text("cmake; rm -rf /\n")

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
        # Should NOT error about dangerous characters (PI_AGENT_IMAGE bypasses .pi-packages)
        output = result.stdout + result.stderr
        assert "dangerous" not in output.lower(), f"PI_AGENT_IMAGE should bypass validation, got: {output}"
        build_line = log_file.read_text()
        assert "my-custom-image" in build_line, f"Expected PI_AGENT_IMAGE override, got: {build_line}"
