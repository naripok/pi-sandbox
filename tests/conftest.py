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
