import pathlib
import subprocess

REPO_ROOT = pathlib.Path(__file__).parent.parent

def test_makefile_exists():
    assert (REPO_ROOT / "Makefile").exists()

def test_makefile_has_required_targets():
    content = (REPO_ROOT / "Makefile").read_text()
    for target in ("build:", "shell:", "pi:", "clean:", "volumes:", "reset:"):
        assert target in content, f"Missing target: {target}"


def test_makefile_has_volumes_target():
    content = (REPO_ROOT / "Makefile").read_text()
    assert "volumes:" in content, "Missing volumes target"


def test_makefile_has_reset_target():
    content = (REPO_ROOT / "Makefile").read_text()
    assert "reset:" in content, "Missing reset target"
