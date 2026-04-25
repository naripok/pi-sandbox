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
        ["podman", "run", "--rm", built_image, "bash", "-c", "command -v pi"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "pi" in result.stdout
