import pathlib

REPO_ROOT = pathlib.Path(__file__).parent.parent

def test_containerfile_exists():
    assert (REPO_ROOT / "Containerfile").exists()

def test_containerfile_has_required_directives():
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "FROM archlinux" in content
    assert "nodejs" in content
    assert "npm" in content
    assert "git" in content
    assert "openssh" in content
    assert "bash" in content
    assert "@mariozechner/pi-coding-agent" in content
    assert "useradd" in content
    assert "USER pi" in content
    assert "WORKDIR /workspace" in content
    assert "config/.bashrc" in content
