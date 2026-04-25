import pathlib
import subprocess

REPO_ROOT = pathlib.Path(__file__).parent.parent

def test_makefile_exists():
    assert (REPO_ROOT / "Makefile").exists()

def test_makefile_has_required_targets():
    content = (REPO_ROOT / "Makefile").read_text()
    for target in ("build:", "shell:", "pi:", "clean:"):
        assert target in content, f"Missing target: {target}"
