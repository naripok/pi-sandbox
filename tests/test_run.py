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
        assert "/workspace" in run_line
        assert "/pi-data:ro" in run_line
        assert "/pi-data/sessions" in run_line
        assert "VLLM_API_KEY" in run_line
        assert "OPENROUTER_API_KEY" in run_line
        assert "pi-agent-isolated" in run_line
        assert "pi -p hello" in run_line
