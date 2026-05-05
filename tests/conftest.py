"""Shared test infrastructure for pi-agent-isolation tests."""
import hashlib
import pathlib
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


@pytest.fixture
def volume_cleanup(tmp_path):
    """Remove the persistent volume created for a test project directory.

    Derives the volume name from the temporary project path, matching
    the logic in run.sh. Yields the tmp_path, then cleans up on exit.
    """
    yield tmp_path
    # Derive volume name matching run.sh logic
    project_path = str(tmp_path.resolve())
    project_name = tmp_path.name
    hash_suffix = hashlib.sha256(project_path.encode()).hexdigest()[:8]
    volume_name = f"pi-agent-persist-{project_name}-{hash_suffix}"
    subprocess.run(
        ["podman", "volume", "rm", volume_name],
        capture_output=True,
    )
